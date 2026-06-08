"""FastAPI application factory and dependency injection."""

import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Generator

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Engine, func
from sqlalchemy.orm import Session

from .models import Base, Generation, Subscription, User, create_engine_from_url, get_session
from ..llm import LLMClient, LLMConfig, LLMProvider

logger = logging.getLogger(__name__)


def _engine(db_url: str) -> Engine:
    engine = create_engine_from_url(db_url)
    Base.metadata.create_all(engine)
    return engine


class AppState:
    engine: Engine
    db_url: str
    llm_api_key: str
    llm_model: str
    jwt_secret: str

    def __init__(self) -> None:
        self.db_url = os.getenv("DATABASE_URL", "sqlite:///data/processed/karmaforge.db")
        self.llm_api_key = os.getenv("LLM_API_KEY", "")
        self.llm_model = os.getenv("LLM_MODEL", "deepseek-chat")
        raw_jwt = os.getenv("JWT_SECRET", "")
        if not raw_jwt:
            if os.getenv("KF_DEV_MODE") == "1":
                raw_jwt = "dev-secret-change-me-in-production-use-32-bytes"
            else:
                raise RuntimeError(
                    "JWT_SECRET must be set in production.\n"
                    "Generate: python -c \"import secrets; print(secrets.token_hex(32))\"\n"
                    "Or set KF_DEV_MODE=1 for local development."
                )
        self.jwt_secret = raw_jwt
        self.engine = _engine(self.db_url)


_state: AppState | None = None


def get_state() -> AppState:
    global _state
    if _state is None:
        _state = AppState()
    return _state


def reset_state() -> None:
    global _state
    _state = None


def override_state(db_url: str) -> AppState:
    global _state
    _state = AppState()
    _state.db_url = db_url
    _state.engine = _engine(db_url)
    return _state


def get_db(request: Request) -> Generator[Session, None, None]:
    state: AppState = request.app.state.app_state
    session = get_session(state.engine)
    try:
        yield session
    finally:
        session.close()


def get_llm_client(request: Request) -> LLMClient:
    state: AppState = request.app.state.app_state
    return LLMClient(LLMConfig(
        provider=LLMProvider.DEEPSEEK,
        api_key=state.llm_api_key,
        model=state.llm_model,
    ))


def get_current_user(request: Request, session: Session = Depends(get_db)) -> User | None:
    state: AppState = request.app.state.app_state
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(auth[7:], state.jwt_secret, algorithms=["HS256"])
        return session.query(User).filter(User.id == payload["sub"]).first()
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


# ── Quota System ────────────────────────────────────────────────────

PLAN_LIMITS = {"free": 20, "pro": 300}


def require_quota(
    request: Request,
    session: Session = Depends(get_db),
) -> User:
    """FastAPI dependency: raises 402 if user has exhausted their generation quota.

    Quota is computed from the Generation table (COUNT query for current
    calendar month) — single source of truth, no counter drift.
    """
    user = get_current_user(request, session)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    limit = PLAN_LIMITS.get(user.tier, 20)

    now = datetime.now(timezone.utc)
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    count = session.query(func.count(Generation.id)).filter(
        Generation.user_id == user.id,
        Generation.created_at >= period_start,
    ).scalar() or 0

    if count >= limit:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "quota_exceeded",
                "used": count,
                "limit": limit,
                "tier": user.tier,
                "upgrade_url": "/pricing",
            },
        )

    return user


def get_quota_info(
    request: Request,
    session: Session = Depends(get_db),
) -> dict:
    """Non-blocking quota info — returns usage without raising on exhaustion."""
    user = get_current_user(request, session)
    if user is None:
        return {"used": 0, "limit": 20, "tier": "free", "remaining": 20}

    limit = PLAN_LIMITS.get(user.tier, 20)

    now = datetime.now(timezone.utc)
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    count = session.query(func.count(Generation.id)).filter(
        Generation.user_id == user.id,
        Generation.created_at >= period_start,
    ).scalar() or 0

    return {
        "used": count,
        "limit": limit,
        "tier": user.tier,
        "remaining": max(0, limit - count),
    }


# ── Rate Limiter ────────────────────────────────────────────────────

# Per-user rate limit buckets: user_id → list of request timestamps
_rate_buckets: dict[str, list[float]] = defaultdict(list)
_RATE_WINDOW_S = 60  # 60-second sliding window
_FREE_RATE_LIMIT = 3   # free users: 3 requests/minute
_PRO_RATE_LIMIT = 10   # pro users: 10 requests/minute


def _clean_rate_bucket(user_id: str) -> None:
    """Remove timestamps outside the sliding window."""
    now = time.time()
    cutoff = now - _RATE_WINDOW_S
    _rate_buckets[user_id] = [t for t in _rate_buckets[user_id] if t > cutoff]


def check_rate_limit(request: Request, user: User) -> None:
    """Raise 429 if user has exceeded their per-minute request limit.

    Call after require_quota() so user is already authenticated.
    """
    _clean_rate_bucket(user.id)
    limit = _PRO_RATE_LIMIT if user.tier == "pro" else _FREE_RATE_LIMIT

    if len(_rate_buckets[user.id]) >= limit:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "retry_after_seconds": _RATE_WINDOW_S,
                "limit": limit,
                "window_seconds": _RATE_WINDOW_S,
            },
        )

    _rate_buckets[user.id].append(time.time())


def create_app(state: AppState | None = None) -> FastAPI:
    from .routes_admin import router as admin_router
    from .routes_auth import router as auth_router
    from .routes_billing import router as billing_router
    from .routes_generate import router as generate_router
    from .routes_track import router as track_router

    app = FastAPI(
        title="KarmaForge API",
        description="Reddit Growth Co-pilot for Indie Developers",
        version="3.0.0",
    )
    app.state.app_state = state or get_state()

    # Sentry — only active when SENTRY_DSN is configured
    sentry_dsn = os.getenv("SENTRY_DSN", "")
    if sentry_dsn:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[FastApiIntegration()],
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_RATE", "0.1")),
            environment=os.getenv("SENTRY_ENV", "production"),
            release=f"karmaforge@{os.getenv('RENDER_GIT_COMMIT', 'dev')}",
        )
        logger.info("Sentry initialized — environment=%s", os.getenv("SENTRY_ENV", "production"))

    allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
    allowed_origins = [o.strip() for o in allowed_origins_raw.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(admin_router)
    app.include_router(auth_router)
    app.include_router(billing_router)
    app.include_router(generate_router)
    app.include_router(track_router)

    # Health check MUST be registered before the static mount,
    # otherwise the catch-all mount at "/" intercepts it → 404.
    @app.get("/api/health")
    async def health():
        return {"status": "ok", "service": "karmaforge-api", "version": "3.0.0"}

    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static")
    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
