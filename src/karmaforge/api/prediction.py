"""E1: Prediction engine — heuristic title ranking based on historical performance."""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session
from sqlalchemy import func

from .models import Feedback, Generation

logger = logging.getLogger(__name__)


@dataclass
class TitlePrediction:
    title: str
    score: float
    hook_type: str
    pattern_id: str
    predicted_range: str
    confidence: str
    reasoning: str


def predict_titles(
    session: Session,
    user_id: str,
    subreddit: str,
    titles: list[dict],
) -> list[TitlePrediction]:
    """Score title candidates based on user's historical performance in this subreddit."""

    history = (
        session.query(Feedback)
        .filter(
            Feedback.user_id == user_id,
            Feedback.subreddit == subreddit,
            Feedback.actual_upvotes > 0,
        )
        .all()
    )

    if len(history) < 3:
        return [_fallback_prediction(t) for t in titles]

    pattern_stats: dict[str, list[int]] = {}
    for h in history:
        pid = h.pattern_id or "unknown"
        pattern_stats.setdefault(pid, []).append(h.actual_upvotes)

    subreddit_avg = sum(h.actual_upvotes for h in history) / len(history)
    subreddit_max = max(h.actual_upvotes for h in history)

    predictions = []
    for t in titles:
        pid = t.get("pattern_id", "unknown")
        scores = pattern_stats.get(pid, [])
        if scores:
            avg = sum(scores) / len(scores)
            hit_rate = sum(1 for s in scores if s > subreddit_avg) / len(scores)
            score = min(95, max(5, int((avg / max(subreddit_avg, 1)) * 60 + hit_rate * 30)))
        else:
            score = 40

        predicted_range = _range_estimate(score, subreddit_avg, subreddit_max)
        confidence, reasoning = _confidence_and_reasoning(score, len(scores) if scores else 0, pid)

        predictions.append(TitlePrediction(
            title=t["title"],
            score=float(score),
            hook_type=t.get("hook_type", "unknown"),
            pattern_id=pid,
            predicted_range=predicted_range,
            confidence=confidence,
            reasoning=reasoning,
        ))

    return predictions


def _fallback_prediction(t: dict) -> TitlePrediction:
    return TitlePrediction(
        title=t["title"],
        score=50.0,
        hook_type=t.get("hook_type", "unknown"),
        pattern_id=t.get("pattern_id", "unknown"),
        predicted_range="insufficient data",
        confidence="low",
        reasoning="Need 3+ tracked posts in this subreddit for personalized predictions.",
    )


def _range_estimate(score: float, avg: float, max_upvotes: float) -> str:
    if score >= 80:
        low, high = int(max_upvotes * 0.6), int(max_upvotes * 1.2)
    elif score >= 60:
        low, high = int(avg * 0.8), int(avg * 1.5)
    elif score >= 40:
        low, high = int(avg * 0.4), int(avg)
    else:
        low, high = 0, int(avg * 0.4)
    return f"{low}-{high}"


def _confidence_and_reasoning(score: float, sample_count: int, pattern_id: str) -> tuple[str, str]:
    if sample_count >= 10:
        conf = "high"
    elif sample_count >= 5:
        conf = "medium"
    else:
        conf = "low"

    if sample_count > 0:
        reason = f"Pattern '{pattern_id}' has {sample_count} tracked posts in this subreddit."
    else:
        reason = f"No history for pattern '{pattern_id}' — using global baseline."

    return conf, reason
