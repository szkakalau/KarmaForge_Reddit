"""Post tracking — record and classify Reddit post performance."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


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

    # Actual performance (entered manually by user)
    actual_upvotes: int
    num_comments: int
    upvote_ratio: float

    # Classification
    performance: str  # "super_viral" | "viral" | "passing" | "failed"
    subreddit_median: float

    # Attribution (populated for failed posts)
    attribution: Optional[dict] = None
