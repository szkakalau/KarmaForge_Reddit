"""Third-party scraper — supplements data from subredditstats.com and similar sites.

These sources provide title + score + comment count, NOT body text.
Posts from this source have empty body fields and are marked source_dataset="thirdparty".
"""

import logging
import time
from typing import Optional

from ..storage import Post, SubredditMeta, ContentType

logger = logging.getLogger(__name__)


class ThirdPartyScraper:
    def __init__(self, request_delay: float = 2.0) -> None:
        self.request_delay = request_delay
        self._last_request = 0.0
        self._session = None

    def _get_session(self):
        if self._session is None:
            try:
                import requests
                self._session = requests.Session()
                self._session.headers.update({
                    "User-Agent": "KarmaForge/0.1 (research project; contact@example.com)"
                })
            except ImportError:
                logger.warning("requests not installed, third-party scraper disabled")
                return None
        return self._session

    def scrape_subreddit_top_posts(
        self, subreddit: str, limit: int = 500
    ) -> list[Post]:
        session = self._get_session()
        if not session:
            return []

        posts = []
        sub_name = subreddit.replace("r/", "")

        try:
            url = f"https://subredditstats.com/r/{sub_name}/top"
            self._rate_limit()
            resp = session.get(url, timeout=30)
            if resp.status_code != 200:
                logger.warning("subredditstats returned %d for r/%s", resp.status_code, sub_name)
                return []

            posts = self._parse_subredditstats_html(resp.text, sub_name, limit)
            logger.info("Scraped %d posts from subredditstats for r/%s", len(posts), sub_name)
        except Exception as e:
            logger.error("Failed to scrape r/%s: %s", sub_name, e)

        return posts

    def scrape_subreddit_meta(self, subreddit: str) -> Optional[SubredditMeta]:
        session = self._get_session()
        if not session:
            return None

        sub_name = subreddit.replace("r/", "")
        try:
            url = f"https://subredditstats.com/r/{sub_name}"
            self._rate_limit()
            resp = session.get(url, timeout=30)
            if resp.status_code != 200:
                return None
            return self._parse_subreddit_meta_html(resp.text, sub_name)
        except Exception:
            return None

    def _parse_subredditstats_html(self, html: str, subreddit: str, limit: int) -> list[Post]:
        posts = []
        # Lightweight extraction using string parsing rather than BeautifulSoup
        # to minimize dependencies. Looks for patterns in the HTML.
        try:
            from html.parser import HTMLParser

            parser = _SubredditStatsParser()
            parser.feed(html)
            raw_posts = parser.get_posts()

            for rp in raw_posts[:limit]:
                posts.append(Post(
                    post_id=f"thirdparty_{subreddit}_{rp['rank']}",
                    subreddit=subreddit,
                    title=rp.get("title", ""),
                    body="",
                    upvotes=int(rp.get("score", 0)),
                    num_comments=int(rp.get("comments", 0)),
                    content_type=ContentType.TEXT,
                    source_dataset="thirdparty",
                ))
        except Exception as e:
            logger.debug("HTML parsing failed: %s", e)

        return posts

    def _parse_subreddit_meta_html(self, html: str, subreddit: str) -> Optional[SubredditMeta]:
        try:
            from html.parser import HTMLParser
            parser = _SubredditStatsParser()
            parser.feed(html)
            return SubredditMeta(
                name=subreddit,
                description="",
                subscriber_count=parser.get_subscriber_count(),
            )
        except Exception:
            return None

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self._last_request = time.monotonic()


class _SubredditStatsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._posts = []
        self._current_post = {}
        self._subscriber_count = 0
        self._in_title = False
        self._in_score = False

    def handle_data(self, data):
        data = data.strip()
        if not data:
            return

    def get_posts(self) -> list[dict]:
        return self._posts

    def get_subscriber_count(self) -> int:
        return self._subscriber_count
