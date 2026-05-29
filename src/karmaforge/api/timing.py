"""E2: Timing optimization — best posting time recommendations per subreddit."""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session
from sqlalchemy import func

from .models import Feedback

logger = logging.getLogger(__name__)

# Crowdsourced best-practice defaults for popular subreddits (UTC hour ranges)
SUBREDDIT_DEFAULTS: dict[str, list[dict]] = {
    "SaaS": [
        {"day": "Tuesday", "window": "14:00-17:00 UTC", "score": 85, "reason": "B2B audiences active during work hours"},
        {"day": "Wednesday", "window": "13:00-16:00 UTC", "score": 80, "reason": "Mid-week peak engagement"},
        {"day": "Thursday", "window": "15:00-18:00 UTC", "score": 75, "reason": "Pre-weekend browsing"},
    ],
    "ExperiencedDevs": [
        {"day": "Tuesday", "window": "15:00-18:00 UTC", "score": 90, "reason": "Peak developer activity post-lunch"},
        {"day": "Wednesday", "window": "14:00-17:00 UTC", "score": 82, "reason": "Strong mid-week discussion"},
        {"day": "Monday", "window": "16:00-19:00 UTC", "score": 70, "reason": "Start-of-week career reflection"},
    ],
    "webdev": [
        {"day": "Monday", "window": "14:00-17:00 UTC", "score": 80, "reason": "Start-of-week productivity spike"},
        {"day": "Thursday", "window": "13:00-16:00 UTC", "score": 78, "reason": "Pre-weekend show-and-tell"},
        {"day": "Saturday", "window": "10:00-14:00 UTC", "score": 65, "reason": "Weekend project time"},
    ],
    "SideProject": [
        {"day": "Saturday", "window": "12:00-16:00 UTC", "score": 88, "reason": "Weekend builders most active"},
        {"day": "Sunday", "window": "14:00-18:00 UTC", "score": 82, "reason": "Sunday project showcase"},
        {"day": "Wednesday", "window": "16:00-20:00 UTC", "score": 65, "reason": "Mid-week motivation"},
    ],
}

_GENERIC_DEFAULTS = [
    {"day": "Tuesday", "window": "14:00-17:00 UTC", "score": 70, "reason": "Generally highest Reddit activity"},
    {"day": "Wednesday", "window": "13:00-16:00 UTC", "score": 68, "reason": "Strong mid-week engagement"},
    {"day": "Thursday", "window": "15:00-18:00 UTC", "score": 65, "reason": "Pre-weekend traffic bump"},
]


@dataclass
class TimeWindow:
    day: str
    window: str
    score: int
    reason: str


def get_best_times(session: Session, user_id: str, subreddit: str) -> list[TimeWindow]:
    """Get best posting times for a subreddit, blending user history with defaults."""

    history = (
        session.query(Feedback)
        .filter(
            Feedback.user_id == user_id,
            Feedback.subreddit == subreddit,
            Feedback.actual_upvotes > 0,
        )
        .all()
    )

    subreddit_key = subreddit.replace("r/", "").split("/")[0]
    defaults = SUBREDDIT_DEFAULTS.get(subreddit_key, _GENERIC_DEFAULTS)

    if len(history) < 5:
        return [
            TimeWindow(day=d["day"], window=d["window"], score=d["score"], reason=d["reason"])
            for d in defaults
        ]

    day_stats: dict[str, list[int]] = {}
    for h in history:
        if h.tracked_at:
            day_name = h.tracked_at.strftime("%A")
            day_stats.setdefault(day_name, []).append(h.actual_upvotes)

    results: list[TimeWindow] = []
    for d in defaults:
        scores = day_stats.get(d["day"], [])
        if scores:
            boost = min(20, int(sum(scores) / len(scores) / 5))
            score = min(99, d["score"] + boost)
            reason = f"{d['reason']}. Your avg: {sum(scores)//len(scores)} upvotes on {d['day']}s."
        else:
            score = d["score"]
            reason = d["reason"]
        results.append(TimeWindow(day=d["day"], window=d["window"], score=score, reason=reason))

    results.sort(key=lambda x: x.score, reverse=True)
    return results
