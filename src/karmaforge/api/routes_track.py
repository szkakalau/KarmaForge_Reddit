"""Track endpoint — wraps tracker.post_tracker."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..tracker.post_tracker import PostTracker
from .deps import get_current_user, get_db
from .models import Feedback, Generation, User
from .timing import get_best_times
from .notifications import get_milestones_achieved, MILESTONES

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/track", tags=["track"])


class TrackRequest(BaseModel):
    generation_id: str = Field(..., min_length=1)
    subreddit: str = Field(..., min_length=2, max_length=64)
    title: str = Field(..., min_length=1, max_length=512)
    body: str = Field(default="", max_length=40000)
    pattern_id: str = Field(default="")
    upvotes: int = Field(default=0, ge=0)
    num_comments: int = Field(default=0, ge=0)
    upvote_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    url: str = Field(default="", max_length=512)


class TrackResponse(BaseModel):
    generation_id: str
    performance: str
    subreddit_median: float
    upvotes: int
    num_comments: int


@router.post("/", response_model=TrackResponse)
def track_post(req: TrackRequest, session: Session = Depends(get_db), current_user: User | None = Depends(get_current_user)):
    try:
        tracker = PostTracker(db_path="data/processed/karmaforge.db")
        entry = tracker.track(
            generation_id=req.generation_id,
            subreddit=req.subreddit,
            title=req.title,
            body=req.body,
            pattern_id=req.pattern_id,
            upvotes=req.upvotes,
            num_comments=req.num_comments,
            upvote_ratio=req.upvote_ratio,
            url=req.url,
        )

        feedback = Feedback(
            user_id=current_user.id if current_user else "_anonymous",
            generation_id=req.generation_id,
            url=req.url,
            subreddit=req.subreddit,
            title=req.title,
            body=req.body,
            pattern_id=req.pattern_id,
            actual_upvotes=req.upvotes,
            num_comments=req.num_comments,
            upvote_ratio=req.upvote_ratio,
            performance=entry.performance,
            subreddit_median=entry.subreddit_median,
        )
        session.add(feedback)
        session.commit()

        return TrackResponse(
            generation_id=req.generation_id,
            performance=entry.performance,
            subreddit_median=entry.subreddit_median,
            upvotes=req.upvotes,
            num_comments=req.num_comments,
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.exception("Track post failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/history")
def get_history(limit: int = 20, session: Session = Depends(get_db), current_user: User | None = Depends(get_current_user)):
    query = session.query(Feedback).order_by(Feedback.tracked_at.desc())
    if current_user:
        query = query.filter(Feedback.user_id == current_user.id)
    rows = query.limit(limit).all()
    return [
        {
            "generation_id": r.generation_id,
            "subreddit": r.subreddit,
            "title": r.title,
            "upvotes": r.actual_upvotes,
            "num_comments": r.num_comments,
            "upvote_ratio": r.upvote_ratio,
            "performance": r.performance,
            "tracked_at": r.tracked_at.isoformat() if r.tracked_at else None,
        }
        for r in rows
    ]


@router.get("/analytics")
def get_analytics(session: Session = Depends(get_db), current_user: User | None = Depends(get_current_user)):
    """Aggregate analytics for dashboard: totals, trends, milestones."""
    query = session.query(Feedback).filter(Feedback.actual_upvotes > 0)
    if current_user:
        query = query.filter(Feedback.user_id == current_user.id)
    rows = query.all()

    if not rows:
        return {
            "total_posts": 0,
            "total_upvotes": 0,
            "avg_upvotes": 0,
            "survival_rate": 0,
            "best_subreddit": None,
            "milestones_hit": [],
            "recent_posts": [],
        }

    total = len(rows)
    total_upvotes = sum(r.actual_upvotes for r in rows)
    avg = total_upvotes / total if total else 0

    subreddit_stats: dict[str, list[int]] = {}
    for r in rows:
        subreddit_stats.setdefault(r.subreddit, []).append(r.actual_upvotes)
    best_sub = max(subreddit_stats, key=lambda s: sum(subreddit_stats[s]) / len(subreddit_stats[s]))

    all_upvotes = [r.actual_upvotes for r in rows]
    milestones_hit = [m for m in MILESTONES if any(u >= m for u in all_upvotes)]

    recent = sorted(rows, key=lambda r: r.tracked_at or "", reverse=True)[:5]

    return {
        "total_posts": total,
        "total_upvotes": total_upvotes,
        "avg_upvotes": round(avg, 1),
        "survival_rate": round(sum(1 for r in rows if r.performance not in ("failed",)) / total * 100, 1),
        "best_subreddit": best_sub,
        "milestones_hit": milestones_hit,
        "recent_posts": [
            {
                "subreddit": r.subreddit,
                "title": r.title[:80],
                "upvotes": r.actual_upvotes,
                "performance": r.performance,
            }
            for r in recent
        ],
    }


@router.get("/timing")
def get_timing(subreddit: str, session: Session = Depends(get_db), current_user: User | None = Depends(get_current_user)):
    """Get best posting times for a subreddit."""
    user_id = current_user.id if current_user else "_anonymous"
    windows = get_best_times(session, user_id, subreddit)
    return {
        "subreddit": subreddit,
        "best_times": [{"day": w.day, "window": w.window, "score": w.score, "reason": w.reason} for w in windows],
    }
