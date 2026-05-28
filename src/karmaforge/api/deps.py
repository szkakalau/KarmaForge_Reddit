"""FastAPI application factory and dependency injection."""

import logging
import os
from typing import Generator

import jwt
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from .models import Base, User, create_engine_from_url, get_session
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
        self.jwt_secret = os.getenv("JWT_SECRET", "dev-secret-change-me-in-production-use-32-bytes")
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


def create_app(state: AppState | None = None) -> FastAPI:
    from .routes_auth import router as auth_router
    from .routes_generate import router as generate_router
    from .routes_track import router as track_router

    app = FastAPI(
        title="KarmaForge API",
        description="Reddit Growth Co-pilot for Indie Developers",
        version="3.0.0",
    )
    app.state.app_state = state or get_state()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router)
    app.include_router(generate_router)
    app.include_router(track_router)

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "service": "karmaforge-api", "version": "3.0.0"}

    return app
