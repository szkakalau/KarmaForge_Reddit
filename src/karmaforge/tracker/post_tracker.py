"""Post tracker — extract Reddit post performance via Playwright browser."""

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from . import TrackingRecord, FeedbackEntry
from .metrics import classify_performance, get_subreddit_median

logger = logging.getLogger(__name__)

FEEDBACK_PATH_DEFAULT = Path("data/tracking/feedback.jsonl")
EXTRACTION_TIMEOUT_MS = 15000


class PostTracker:
    """Extract post stats from old.reddit.com via Playwright."""

    def __init__(
        self,
        db_path: str = "data/processed/karmaforge.db",
        feedback_path: str | Path | None = None,
        headless: bool = True,
    ) -> None:
        self._db_path = db_path
        self._feedback_path = Path(feedback_path) if feedback_path else FEEDBACK_PATH_DEFAULT
        self._feedback_path.parent.mkdir(parents=True, exist_ok=True)
        self._headless = headless
        self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def initialize(self) -> bool:
        try:
            import playwright  # noqa: F401
            self._available = True
            logger.info("PostTracker initialized (playwright available)")
            return True
        except ImportError:
            logger.warning(
                "playwright not installed. PostTracker disabled. "
                "Install with: pip install karmaforge[browser]"
            )
            return False

    def fetch_post_stats(self, url: str) -> TrackingRecord | None:
        """Open old.reddit.com URL and extract upvotes/comments/ratio."""
        if not self._available:
            logger.error("Playwright not available. Cannot fetch post stats.")
            return None

        old_url = self._to_old_reddit(url)

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self._headless)
                page = browser.new_page()
                page.goto(old_url, wait_until="domcontentloaded", timeout=EXTRACTION_TIMEOUT_MS)
                time.sleep(1.5)

                upvotes = self._extract_upvotes(page)
                num_comments = self._extract_comments(page)
                upvote_ratio = self._extract_ratio(page)

                browser.close()

                record = TrackingRecord(
                    url=url,
                    upvotes=upvotes,
                    num_comments=num_comments,
                    upvote_ratio=upvote_ratio,
                    extracted_at=datetime.now(timezone.utc).isoformat(),
                )
                logger.info(
                    "Extracted: %d upvotes, %d comments, %.0f%% ratio from %s",
                    upvotes, num_comments, upvote_ratio * 100, url,
                )
                return record
        except Exception as e:
            logger.error("Failed to extract post stats from %s: %s", url, e)
            return None

    def track(
        self,
        url: str,
        generation_id: str,
        subreddit: str,
        title: str,
        body: str,
        pattern_id: str,
    ) -> FeedbackEntry | None:
        """Fetch stats, classify, and save feedback entry."""
        record = self.fetch_post_stats(url)
        if not record:
            return None

        median = get_subreddit_median(self._db_path, subreddit)
        performance = classify_performance(record.upvotes, median)

        entry = FeedbackEntry(
            generation_id=generation_id,
            tracked_at=datetime.now(timezone.utc).isoformat(),
            url=url,
            subreddit=subreddit,
            title=title,
            body=body,
            pattern_id=pattern_id,
            actual_upvotes=record.upvotes,
            num_comments=record.num_comments,
            upvote_ratio=record.upvote_ratio,
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

    # ── Private ──────────────────────────────────────────────────

    @staticmethod
    def _to_old_reddit(url: str) -> str:
        """Convert any Reddit URL to old.reddit.com."""
        return re.sub(
            r"(?:https?://)?(?:www\.|old\.|new\.)?reddit\.com",
            "https://old.reddit.com",
            url,
        )

    @staticmethod
    def _extract_upvotes(page) -> int:
        """Extract upvote count from old.reddit.com post page."""
        try:
            score_el = page.query_selector(".score.unvoted")
            if not score_el:
                score_el = page.query_selector(".score")
            if score_el:
                text = score_el.inner_text().strip()
                nums = re.findall(r"[\d,]+", text)
                if nums:
                    return int(nums[0].replace(",", ""))

            # Fallback: look for the post's score in the linkinfo panel
            midcol = page.query_selector(".midcol")
            if midcol:
                score_div = midcol.query_selector(".score")
                if score_div:
                    text = score_div.inner_text().strip()
                    nums = re.findall(r"\d+", text)
                    if nums:
                        return int(nums[0])

            return 0
        except Exception as e:
            logger.debug("Failed to extract upvotes: %s", e)
            return 0

    @staticmethod
    def _extract_comments(page) -> int:
        """Extract comment count from old.reddit.com."""
        try:
            comments_el = page.query_selector("a.comments")
            if comments_el:
                text = comments_el.inner_text().strip()
                nums = re.findall(r"\d+", text)
                if nums:
                    return int(nums[0])
            return 0
        except Exception as e:
            logger.debug("Failed to extract comment count: %s", e)
            return 0

    @staticmethod
    def _extract_ratio(page) -> float:
        """Extract upvote ratio from old.reddit.com side panel."""
        try:
            # Look for the ratio text like "96% upvoted"
            body_text = page.inner_text("body")
            match = re.search(r"(\d+)%\s*upvoted", body_text)
            if match:
                return int(match.group(1)) / 100.0
            return 0.0
        except Exception as e:
            logger.debug("Failed to extract upvote ratio: %s", e)
            return 0.0

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
