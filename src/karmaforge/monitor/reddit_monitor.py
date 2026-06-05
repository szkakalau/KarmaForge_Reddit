"""Reddit post monitor — auto-fetch upvotes/comments via PRAW.

Closes the most critical gap in the feedback loop: manual data entry.
Takes Reddit post URLs from feedback.jsonl, fetches current stats,
and updates entries via PostTracker.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Regex to extract Reddit post ID from various URL formats
_REDDIT_URL_RE = re.compile(
    r"(?:reddit\.com|redd\.it)/(?:r/\w+/comments/)?(\w+)(?:/.*)?"
)


class RedditMonitor:
    """Fetch live Reddit post stats and sync to feedback.jsonl."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        user_agent: str | None = None,
        feedback_path: str | Path = "data/tracking/feedback.jsonl",
    ) -> None:
        self._client_id = client_id or os.environ.get("REDDIT_CLIENT_ID", "")
        self._client_secret = client_secret or os.environ.get("REDDIT_CLIENT_SECRET", "")
        self._user_agent = user_agent or "karmaforge-v1-monitor/0.1 by u/your_username"
        self._feedback_path = Path(feedback_path)
        self._reddit = None
        self._authenticated = False

    # ── Authentication ───────────────────────────────────────────

    def authenticate(self) -> bool:
        """Connect to Reddit API via PRAW. Returns True on success."""
        if not self._client_id or not self._client_secret:
            logger.warning(
                "Reddit API credentials not configured. "
                "Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET env vars."
            )
            return False

        try:
            import praw
            self._reddit = praw.Reddit(
                client_id=self._client_id,
                client_secret=self._client_secret,
                user_agent=self._user_agent,
                ratelimit_seconds=600,
            )
            self._reddit.user.me()
            self._authenticated = True
            logger.info("RedditMonitor authenticated successfully")
            return True
        except Exception as e:
            logger.error("RedditMonitor authentication failed: %s", e)
            self._reddit = None
            return False

    @property
    def is_available(self) -> bool:
        return self._authenticated and self._reddit is not None

    # ── Main operation ───────────────────────────────────────────

    def fetch_and_update(
        self,
        tracker=None,  # PostTracker instance, injected to avoid circular import
        dry_run: bool = False,
    ) -> dict:
        """Fetch live stats for all tracked Reddit posts and update feedback.

        Args:
            tracker: PostTracker instance for recording updated stats.
            dry_run: If True, fetch but don't write.

        Returns:
            Dict with counts: {checked, updated, failed, skipped}.
        """
        if not self.is_available:
            return {"checked": 0, "updated": 0, "failed": 0, "skipped": 0,
                    "error": "Not authenticated"}

        entries = self._load_entries()
        checked = 0
        updated = 0
        failed = 0
        skipped = 0

        for entry in entries:
            url = entry.get("url", "")
            post_id = self._extract_post_id(url)
            if not post_id:
                skipped += 1
                continue

            checked += 1
            try:
                stats = self._fetch_post_stats(post_id)
                if stats is None:
                    failed += 1
                    continue

                # Only update if values changed meaningfully
                old_upvotes = entry.get("actual_upvotes", 0)
                old_comments = entry.get("num_comments", 0)
                old_ratio = entry.get("upvote_ratio", 0)

                if (
                    stats["upvotes"] == old_upvotes
                    and stats["num_comments"] == old_comments
                    and abs(stats["upvote_ratio"] - old_ratio) < 0.01
                ):
                    skipped += 1
                    continue

                if not dry_run and tracker is not None:
                    tracker.track(
                        generation_id=entry.get("generation_id", "monitor"),
                        subreddit=entry.get("subreddit", ""),
                        title=entry.get("title", ""),
                        body=entry.get("body", ""),
                        pattern_id=entry.get("pattern_id", ""),
                        upvotes=stats["upvotes"],
                        num_comments=stats["num_comments"],
                        upvote_ratio=stats["upvote_ratio"],
                        url=url,
                        quality_scores=entry.get("quality_scores"),
                    )

                # Update entry in-place for rewrite
                entry["actual_upvotes"] = stats["upvotes"]
                entry["num_comments"] = stats["num_comments"]
                entry["upvote_ratio"] = stats["upvote_ratio"]
                entry["last_monitored_at"] = datetime.now(timezone.utc).isoformat()
                updated += 1

                logger.info(
                    "Updated %s: %d→%d upvotes, %d→%d comments",
                    entry.get("generation_id", "?"),
                    old_upvotes, stats["upvotes"],
                    old_comments, stats["num_comments"],
                )
            except Exception as e:
                logger.error("Failed to fetch %s: %s", post_id, e)
                failed += 1

        # Rewrite feedback file with updated entries (unless dry run)
        if updated > 0 and not dry_run:
            self._rewrite_entries(entries)

        return {
            "checked": checked,
            "updated": updated,
            "failed": failed,
            "skipped": skipped,
        }

    # ── Internals ────────────────────────────────────────────────

    def _fetch_post_stats(self, post_id: str) -> dict | None:
        """Fetch current stats for a single Reddit post."""
        if not self._reddit:
            return None

        try:
            submission = self._reddit.submission(id=post_id)
            # Access attributes to trigger lazy loading
            _ = submission.title
            return {
                "upvotes": submission.score,
                "num_comments": submission.num_comments,
                "upvote_ratio": getattr(submission, "upvote_ratio", 0.0),
            }
        except Exception as e:
            logger.debug("PRAW fetch failed for %s: %s", post_id, e)
            return None

    def _load_entries(self) -> list[dict]:
        """Load all feedback entries with Reddit URLs."""
        entries = []
        if not self._feedback_path.exists():
            return entries

        with open(self._feedback_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Only include entries with a Reddit URL
                if entry.get("url") and "reddit.com" in entry.get("url", ""):
                    entries.append(entry)
        return entries

    def _rewrite_entries(self, entries: list[dict]) -> None:
        """Rewrite the full feedback file with updated entries."""
        tmp_path = self._feedback_path.with_suffix(".jsonl.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        tmp_path.replace(self._feedback_path)

    @staticmethod
    def _extract_post_id(url: str) -> str | None:
        """Extract Reddit post ID from a URL like
        https://reddit.com/r/sub/comments/abc123/title.
        """
        if not url:
            return None
        match = _REDDIT_URL_RE.search(url)
        if match:
            return match.group(1)
        return None
