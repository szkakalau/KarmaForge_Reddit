"""Arctic Shift (Pushshift successor) collector — fetches full Reddit posts with body text.

Arctic Shift is a free, community-maintained Reddit data API. Unlike Kaggle UCSD
datasets (which skew heavily toward link/image posts with empty selftext), this API
returns complete post data including body/selftext for text-heavy subreddits.

API docs: https://arctic-shift.photon-reddit.com/
Rate limit: ~60 requests/minute (no auth required)
"""

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import requests

from ..storage import Post, ContentType

logger = logging.getLogger(__name__)

ARCTIC_SHIFT_BASE = "https://arctic-shift.photon-reddit.com"
REQUEST_DELAY = 1.2  # seconds between requests (polite scraping)
MAX_PER_REQUEST = 100  # Arctic Shift limit per page
MAX_PAGES = 5  # Max pages per subreddit (500 posts max)


class PushshiftCollector:
    """Fetch Reddit posts from Arctic Shift API with full body/selftext.

    Usage:
        collector = PushshiftCollector(subreddits=["productivity", "SaaS"])
        posts = collector.collect_all(posts_per_subreddit=100, sort="top", time_frame="year")
    """

    def __init__(
        self,
        subreddits: Optional[list[str]] = None,
        request_delay: float = REQUEST_DELAY,
        max_per_request: int = MAX_PER_REQUEST,
        max_pages: int = MAX_PAGES,
    ) -> None:
        self.subreddits = [s.lower().replace("r/", "") for s in (subreddits or [])]
        self.delay = request_delay
        self.max_per_request = max_per_request
        self.max_pages = max_pages
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "KarmaForge/1.0 (research project; contact@einprag.com)",
            "Accept": "application/json",
        })
        self._last_request = 0.0
        self._stats = {"requests": 0, "posts_fetched": 0, "errors": 0}

    def collect_all(
        self,
        posts_per_subreddit: int = 100,
        sort: str = "desc",
        time_frame: str = "",
    ) -> list[Post]:
        """Fetch posts for all configured subreddits.

        Args:
            posts_per_subreddit: Target number of posts per subreddit.
            sort: Sorting — "desc" (top all-time), "asc" (new).
            time_frame: Ignored (Arctic Shift doesn't support this param).
        """
        all_posts: list[Post] = []
        for sub in self.subreddits:
            try:
                posts = self.collect_subreddit(sub, limit=posts_per_subreddit, sort=sort, time_frame=time_frame)
                all_posts.extend(posts)
                logger.info(
                    "Pushshift: fetched %d posts from r/%s (body rate: %.0f%%)",
                    len(posts),
                    sub,
                    100 * sum(1 for p in posts if p.body and len(p.body) >= 20) / max(len(posts), 1),
                )
            except Exception:
                logger.exception("Failed to fetch r/%s from Arctic Shift", sub)
        logger.info("Pushshift done: %d posts, %d requests, %d errors",
                     self._stats["posts_fetched"], self._stats["requests"], self._stats["errors"])
        return all_posts

    def collect_subreddit(
        self,
        subreddit: str,
        limit: int = 100,
        sort: str = "desc",
        time_frame: str = "",
    ) -> list[Post]:
        """Fetch posts from a single subreddit.

        Uses cursor-based pagination via the response `after` field.
        Arctic Shift API sort values: "desc" (top), "asc" (new).
        """
        sub = subreddit.lower().replace("r/", "")
        posts: list[Post] = []
        after: Optional[str] = None
        pages = 0
        needed = min(limit, self.max_per_request * self.max_pages)

        while len(posts) < needed and pages < self.max_pages:
            params = {
                "subreddit": sub,
                "sort": sort,
                "limit": min(self.max_per_request, needed - len(posts)),
            }
            # Arctic Shift doesn't support time_frame — omit it
            # (adds 400 error if included)
            if after:
                params["after"] = after

            data = self._request("/api/posts/search", params)
            if not data:
                break

            page_posts = data.get("data", [])
            if not page_posts:
                break

            for raw in page_posts:
                try:
                    post = self._parse_post(raw)
                    if post:
                        posts.append(post)
                except Exception:
                    continue

            after = data.get("after") or data.get("cursor")
            pages += 1

            if len(page_posts) < self.max_per_request:
                break  # No more data

        self._stats["posts_fetched"] += len(posts)
        return posts

    def _request(self, path: str, params: dict) -> Optional[dict]:
        """Make a rate-limited request to Arctic Shift."""
        # Enforce rate limit
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

        url = f"{ARCTIC_SHIFT_BASE}{path}"
        try:
            resp = self._session.get(url, params=params, timeout=30)
            self._last_request = time.monotonic()
            self._stats["requests"] += 1

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", 5))
                logger.warning("Arctic Shift rate limit, waiting %.0fs", retry_after)
                time.sleep(retry_after)
                return self._request(path, params)

            if resp.status_code != 200:
                logger.warning("Arctic Shift returned %d for %s", resp.status_code, path)
                return None

            return resp.json()
        except requests.RequestException as e:
            self._stats["errors"] += 1
            logger.warning("Arctic Shift request failed: %s", e)
            return None

    def _parse_post(self, raw: dict) -> Optional[Post]:
        """Convert Arctic Shift post JSON to KarmaForge Post dataclass."""
        post_id = raw.get("id", "")
        if not post_id:
            return None

        # Normalize Reddit ID format
        if not post_id.startswith("t3_"):
            post_id = f"t3_{post_id}"

        # Parse timestamp — Arctic Shift uses created_utc (int, unix timestamp)
        created = raw.get("created_utc")
        if created is not None:
            try:
                created = datetime.fromtimestamp(float(created), tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                created = None

        # Content type detection
        url = raw.get("url", "") or ""
        content_type = self._detect_content_type(url, raw)

        # Body/selftext — this is the key field that Kaggle dataset often misses
        body = raw.get("selftext", "") or raw.get("body", "") or ""

        # Subreddit normalization
        subreddit = raw.get("subreddit", "")
        if isinstance(subreddit, str):
            subreddit = subreddit.replace("r/", "")

        return Post(
            post_id=post_id,
            subreddit=subreddit,
            title=raw.get("title", ""),
            body=body,
            author=raw.get("author", "[deleted]"),
            created_utc=created,
            upvotes=int(raw.get("score", 0) or raw.get("ups", 0) or 0),
            upvote_ratio=float(raw.get("upvote_ratio", 0.0) or 0.0),
            num_comments=int(raw.get("num_comments", 0) or raw.get("comms_num", 0) or 0),
            flair=raw.get("link_flair_text") or raw.get("flair"),
            is_oc=bool(raw.get("is_original_content", False)),
            is_nsfw=bool(raw.get("over_18", False)),
            content_type=content_type,
            url=url if url else None,
            source_dataset="pushshift_arctic",
        )

    @staticmethod
    def _detect_content_type(url: str, raw: dict) -> ContentType:
        """Detect content type from URL and post hints."""
        # Check Reddit's own metadata first
        post_hint = raw.get("post_hint", "")
        if post_hint == "image":
            return ContentType.IMAGE
        if post_hint in ("video", "gif"):
            return ContentType.VIDEO
        if post_hint == "link":
            return ContentType.LINK

        # Self posts have is_self=True or empty url
        if raw.get("is_self", False) or not url:
            return ContentType.TEXT

        # URL-based detection
        url_lower = url.lower()
        if any(ext in url_lower for ext in [".jpg", ".png", ".gif", ".webp", "imgur.com", "i.redd.it"]):
            if ".gif" in url_lower or "gfycat" in url_lower:
                return ContentType.VIDEO
            return ContentType.IMAGE
        if any(domain in url_lower for domain in ["youtube.com", "youtu.be", "v.redd.it"]):
            return ContentType.VIDEO
        if any(domain in url_lower for domain in ["reddit.com/r/", "redd.it"]):
            return ContentType.TEXT  # Crosspost
        if url_lower.startswith("http"):
            return ContentType.LINK

        return ContentType.TEXT

    @property
    def stats(self) -> dict:
        return dict(self._stats)
