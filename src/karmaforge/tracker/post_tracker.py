"""Post tracker — record and classify Reddit post performance."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from . import FeedbackEntry
from .metrics import classify_performance, get_subreddit_median

logger = logging.getLogger(__name__)

FEEDBACK_PATH_DEFAULT = Path("data/tracking/feedback.jsonl")


class PostTracker:
    """Record post stats manually and classify performance."""

    def __init__(
        self,
        db_path: str = "data/processed/karmaforge.db",
        feedback_path: str | Path | None = None,
    ) -> None:
        self._db_path = db_path
        self._feedback_path = Path(feedback_path) if feedback_path else FEEDBACK_PATH_DEFAULT
        self._feedback_path.parent.mkdir(parents=True, exist_ok=True)

    def track(
        self,
        generation_id: str,
        subreddit: str,
        title: str,
        body: str,
        pattern_id: str,
        upvotes: int,
        num_comments: int,
        upvote_ratio: float,
        url: str = "",
    ) -> FeedbackEntry:
        """Classify performance and save feedback entry."""
        median = get_subreddit_median(self._db_path, subreddit)
        performance = classify_performance(upvotes, median)

        entry = FeedbackEntry(
            generation_id=generation_id,
            tracked_at=datetime.now(timezone.utc).isoformat(),
            url=url,
            subreddit=subreddit,
            title=title,
            body=body,
            pattern_id=pattern_id,
            actual_upvotes=upvotes,
            num_comments=num_comments,
            upvote_ratio=upvote_ratio,
            performance=performance,
            subreddit_median=median,
        )

        self._save_feedback(entry)
        return entry

    def load_feedback(self) -> list[dict]:
        """Load all feedback entries from JSONL."""
        entries = []
        if self._feedback_path.exists():
            with open(self._feedback_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        return entries

    def feedback_count(self) -> int:
        """Count entries in feedback file."""
        if not self._feedback_path.exists():
            return 0
        count = 0
        with open(self._feedback_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count

    def _save_feedback(self, entry: FeedbackEntry) -> None:
        """Append feedback entry to JSONL file."""
        data = {
            "generation_id": entry.generation_id,
            "tracked_at": entry.tracked_at,
            "url": entry.url,
            "subreddit": entry.subreddit,
            "title": entry.title,
            "body": entry.body[:200] if entry.body else "",
            "pattern_id": entry.pattern_id,
            "actual_upvotes": entry.actual_upvotes,
            "num_comments": entry.num_comments,
            "upvote_ratio": entry.upvote_ratio,
            "performance": entry.performance,
            "subreddit_median": entry.subreddit_median,
            "attribution": entry.attribution,
        }
        with open(self._feedback_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
        logger.info("Saved feedback for %s → %s", entry.generation_id, entry.performance)
