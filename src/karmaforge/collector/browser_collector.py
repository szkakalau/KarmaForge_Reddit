"""Browser-based collector — last-resort fallback when API and datasets are unavailable.

SLOW (5-10 sec/post). Only used to fill critical gaps.
Requires `browser-use` and `playwright` (optional dependencies).
"""

import logging
import random
import time
from datetime import datetime, timezone
from typing import Optional

from ..storage import Post, Comment, ContentType

logger = logging.getLogger(__name__)


class BrowserCollector:
    def __init__(
        self,
        headless: bool = True,
        request_delay: tuple[float, float] = (3.0, 8.0),
    ) -> None:
        self.headless = headless
        self.request_delay = request_delay
        self._browser = None
        self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def initialize(self) -> bool:
        try:
            import playwright  # noqa: F401
            self._available = True
            logger.info("Browser collector initialized (playwright available)")
            return True
        except ImportError:
            logger.warning(
                "playwright not installed. Browser collector disabled. "
                "Install with: pip install karmaforge[browser]"
            )
            self._available = False
            return False

    def collect_subreddit_top_posts(
        self, subreddit: str, limit: int = 500
    ) -> list[Post]:
        if not self._available:
            return []

        logger.info("Browser collecting top %d posts from r/%s (slow)", limit, subreddit)
        posts = []
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                page = browser.new_page()
                url = f"https://old.reddit.com/r/{subreddit}/top/?sort=top&t=year"
                page.goto(url, wait_until="networkidle")
                self._simulate_scroll(page, limit)
                posts = self._extract_posts_from_page(page, subreddit)
                browser.close()

            logger.info("Browser collected %d posts from r/%s", len(posts), subreddit)
        except Exception as e:
            logger.error("Browser collection failed for r/%s: %s", subreddit, e)

        return posts

    def collect_post_comments(
        self, post_url: str, top_n: int = 20
    ) -> list[Comment]:
        if not self._available:
            return []

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                page = browser.new_page()
                page.goto(post_url, wait_until="networkidle")
                self._random_delay(1.0, 2.0)
                comments = self._extract_comments_from_page(page, post_url, top_n)
                browser.close()
            return comments
        except Exception as e:
            logger.error("Browser comment collection failed: %s", e)
            return []

    def _simulate_scroll(self, page, target_count: int) -> None:
        last_height = 0
        scrolls = 0
        max_scrolls = target_count // 25

        for _ in range(max_scrolls):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self._random_delay(2.0, 5.0)
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            scrolls += 1

    def _extract_posts_from_page(self, page, subreddit: str) -> list[Post]:
        posts = []
        entries = page.query_selector_all(".thing.link")
        for i, entry in enumerate(entries):
            try:
                title_el = entry.query_selector("a.title")
                title = title_el.inner_text() if title_el else ""
                score_el = entry.query_selector(".score.unvoted")
                score = int(score_el.get_attribute("title") or "0") if score_el else 0
                comments_el = entry.query_selector("a.comments")
                comments_text = comments_el.inner_text() if comments_el else "0"
                num_comments = int("".join(c for c in comments_text if c.isdigit()) or "0")
                post_id = entry.get_attribute("data-fullname") or f"browser_{subreddit}_{i}"

                posts.append(Post(
                    post_id=post_id,
                    subreddit=subreddit,
                    title=title,
                    body="",
                    upvotes=score,
                    num_comments=num_comments,
                    content_type=ContentType.TEXT,
                    source_dataset="browser",
                ))
            except Exception:
                continue

        return posts

    def _extract_comments_from_page(self, page, post_url: str, top_n: int) -> list[Comment]:
        comments = []
        entries = page.query_selector_all(".comment")
        for entry in entries[:top_n]:
            try:
                comment_id = entry.get_attribute("data-fullname") or "browser_comment"
                body_el = entry.query_selector(".md")
                body = body_el.inner_text() if body_el else ""
                score_el = entry.query_selector(".score")
                score = int(score_el.inner_text().split()[0]) if score_el else 0

                comments.append(Comment(
                    comment_id=comment_id,
                    post_id=post_url,
                    parent_id=post_url,
                    body=body,
                    upvotes=score,
                ))
            except Exception:
                continue

        return comments

    def _random_delay(self, min_s: float, max_s: float) -> None:
        time.sleep(random.uniform(min_s, max_s))
