"""Reddit API collector via PRAW — gated behind API approval.

The entire v1 pipeline must work without this module.
Only activate when Reddit API credentials are approved and available.
"""

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..storage import Post, Comment, ContentType

logger = logging.getLogger(__name__)


class PRAWCollector:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
        subreddits: list[str],
        posts_per_subreddit: int = 500,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent
        self.subreddits = [s.replace("r/", "") for s in subreddits]
        self.posts_per_subreddit = posts_per_subreddit
        self._reddit = None
        self._last_request_time = 0.0

    def authenticate(self) -> bool:
        try:
            import praw
            self._reddit = praw.Reddit(
                client_id=self.client_id,
                client_secret=self.client_secret,
                user_agent=self.user_agent,
                ratelimit_seconds=600,
            )
            self._reddit.user.me()
            logger.info("PRAW authentication successful")
            return True
        except Exception as e:
            logger.error("PRAW authentication failed: %s", e)
            self._reddit = None
            return False

    @property
    def is_available(self) -> bool:
        return self._reddit is not None

    def collect_posts(self) -> list[Post]:
        if not self._reddit:
            logger.warning("PRAW not authenticated, skipping collection")
            return []

        posts = []
        for sub_name in self.subreddits:
            try:
                sub_posts = self._collect_subreddit_posts(sub_name)
                posts.extend(sub_posts)
                logger.info("Collected %d posts from r/%s", len(sub_posts), sub_name)
            except Exception as e:
                logger.error("Failed to collect from r/%s: %s", sub_name, e)
                continue

        return posts

    def collect_comments(self, post_ids: list[str]) -> list[Comment]:
        if not self._reddit:
            return []

        comments = []
        for pid in post_ids:
            try:
                self._rate_limit()
                submission = self._reddit.submission(id=pid.replace("t3_", ""))
                submission.comments.replace_more(limit=0)
                for c in submission.comments.list():
                    comments.append(self._comment_to_schema(c, pid))
            except Exception as e:
                logger.debug("Failed to collect comments for %s: %s", pid, e)
                continue

        return comments

    def collect_all(self) -> tuple[list[Post], list[Comment]]:
        posts = self.collect_posts()
        post_ids = [p.post_id for p in posts]
        comments = self.collect_comments(post_ids)
        return posts, comments

    def _collect_subreddit_posts(self, sub_name: str) -> list[Post]:
        subreddit = self._reddit.subreddit(sub_name)
        posts = []
        for submission in subreddit.top(time_filter="year", limit=self.posts_per_subreddit):
            self._rate_limit()
            posts.append(self._submission_to_post(submission))
        return posts

    def _submission_to_post(self, s) -> Post:
        created = datetime.fromtimestamp(s.created_utc, tz=timezone.utc)
        content_type = ContentType.TEXT
        if s.is_video:
            content_type = ContentType.VIDEO
        elif s.url and not s.is_self:
            if any(x in (s.url or "").lower() for x in [".jpg", ".png", ".gif", "imgur"]):
                content_type = ContentType.IMAGE
            else:
                content_type = ContentType.LINK

        return Post(
            post_id=f"t3_{s.id}",
            subreddit=str(s.subreddit.display_name),
            title=s.title,
            body=s.selftext or "",
            author=str(s.author) if s.author else "[deleted]",
            created_utc=created,
            upvotes=s.score,
            upvote_ratio=getattr(s, "upvote_ratio", 0.0),
            num_comments=s.num_comments,
            awards=self._extract_awards(s),
            flair=s.link_flair_text or None,
            is_oc=getattr(s, "is_original_content", False),
            is_nsfw=s.over_18,
            content_type=content_type,
            is_crosspost=hasattr(s, "crosspost_parent"),
            crosspost_source=self._crosspost_source(s),
            url=s.url if not s.is_self else None,
            source_dataset="praw",
        )

    def _comment_to_schema(self, c, post_id: str, depth: int = 0) -> Comment:
        return Comment(
            comment_id=f"t1_{c.id}",
            post_id=post_id,
            parent_id=f"t1_{c.parent_id}" if not c.is_root else post_id,
            body=c.body or "",
            author=str(c.author) if c.author else "[deleted]",
            created_utc=datetime.fromtimestamp(c.created_utc, tz=timezone.utc),
            upvotes=c.score,
            depth=depth,
        )

    def _extract_awards(self, s) -> dict:
        awards = {}
        if hasattr(s, "all_awardings"):
            for award in s.all_awardings:
                awards[award.get("name", "unknown")] = award.get("count", 1)
        return awards

    def _crosspost_source(self, s) -> Optional[str]:
        if hasattr(s, "crosspost_parent"):
            try:
                parent = self._reddit.submission(id=s.crosspost_parent.split("_")[1])
                return str(parent.subreddit.display_name)
            except Exception:
                pass
        return None

    def _rate_limit(self, min_delay: float = 0.6) -> None:
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < min_delay:
            time.sleep(min_delay - elapsed)
        self._last_request_time = time.monotonic()
