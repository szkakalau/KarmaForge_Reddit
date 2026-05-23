"""Post tracking — extract Reddit post performance via browser."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TrackingRecord:
    """Raw stats extracted from a Reddit post page."""

    url: str
    upvotes: int
    num_comments: int
    upvote_ratio: float  # 0.0-1.0
    extracted_at: str  # ISO 8601


@dataclass
class FeedbackEntry:
    """Combined generation + tracking data for evolution."""

    generation_id: str
    tracked_at: str  # ISO 8601
    url: str
    subreddit: str
    title: str
    body: str
    pattern_id: str

    # Actual performance
    actual_upvotes: int
    num_comments: int
    upvote_ratio: float

    # Classification
    performance: str  # "super_viral" | "viral" | "passing" | "failed"
    subreddit_median: float

    # Attribution (populated for failed posts)
    attribution: Optional[dict] = None
