"""Admin endpoints — user stats, cost monitoring."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from .deps import get_current_user, get_db
from .models import Generation, Subscription, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])

ADMIN_EMAILS = {"admin@karmaforge.local"}  # TODO: make configurable via env var


def _require_admin(request: Request, session: Session = Depends(get_db)) -> User:
    user = get_current_user(request, session)
    if user is None:
        raise HTTPException(status_code=401)
    # Simple admin check — in production, use a proper role system
    if user.email not in ADMIN_EMAILS and not user.email.endswith("@karmaforge.local"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/stats")
def admin_stats(
    user: User = Depends(_require_admin),
    session: Session = Depends(get_db),
):
    """Return aggregate platform stats for the admin dashboard."""
    total_users = session.query(func.count(User.id)).scalar() or 0
    free_users = session.query(func.count(User.id)).filter(User.tier == "free").scalar() or 0
    pro_users = session.query(func.count(User.id)).filter(User.tier == "pro").scalar() or 0
    total_generations = session.query(func.count(Generation.id)).scalar() or 0

    # Estimate API cost (DeepSeek: $0.14/M in, $0.28/M out)
    # Approximate: ~2,300 tokens per generation → $0.000476
    estimated_cost = total_generations * 0.000476

    return {
        "total_users": total_users,
        "free_users": free_users,
        "pro_users": pro_users,
        "total_generations": total_generations,
        "estimated_cost": round(estimated_cost, 4),
    }
