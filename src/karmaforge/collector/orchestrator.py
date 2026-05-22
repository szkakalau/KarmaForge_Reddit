"""Collection orchestrator — priority-based multi-source data collection.

Priority: Kaggle → PRAW → Third-party → Browser
Each source fills gaps left by higher-priority sources.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import yaml

from ..storage import Database, Post, Comment, SubredditMeta, Tier, read_jsonl, write_jsonl
from ..llm import LLMClient, LLMConfig, LLMProvider
from .kaggle_loader import KaggleLoader
from .praw_collector import PRAWCollector
from .thirdparty_scraper import ThirdPartyScraper
from .browser_collector import BrowserCollector

logger = logging.getLogger(__name__)


@dataclass
class CollectionReport:
    total_posts: int = 0
    total_comments: int = 0
    posts_per_subreddit: dict[str, int] = field(default_factory=dict)
    posts_per_source: dict[str, int] = field(default_factory=dict)
    posts_per_tier: dict[str, int] = field(default_factory=dict)
    gaps: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Collection Report: {self.total_posts} posts, {self.total_comments} comments",
            f"By source: {self.posts_per_source}",
            f"By tier: {self.posts_per_tier}",
            f"Per subreddit: {self.posts_per_subreddit}",
        ]
        return "\n".join(lines)


class CollectionOrchestrator:
    def __init__(self, config_path: Union[str, Path]) -> None:
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.db = Database(Path(self.config["paths"]["data_processed"]) / "karmaforge.db")
        self._llm_client: Optional[LLMClient] = None

    def run(self) -> CollectionReport:
        logger.info("Starting collection pipeline")
        self.db.create_schema()

        # Step 1: Kaggle (always first, zero cost)
        posts, comments, crossrefs = [], [], []
        if self.config["collection"]["sources"]["kaggle_enabled"]:
            posts, crossrefs = self._run_kaggle()

        # Step 2: PRAW (if credentials available)
        if self.config["collection"]["sources"]["praw_enabled"]:
            praw_posts, praw_comments = self._run_praw(posts)
            posts = self._merge_posts(posts, praw_posts)
            comments.extend(praw_comments)

        # Step 3: Third-party (fill remaining gaps)
        if self.config["collection"]["sources"]["thirdparty_enabled"]:
            tp_posts = self._run_thirdparty(posts)
            posts = self._merge_posts(posts, tp_posts)

        # Step 4: Browser (last resort for critical gaps)
        if self.config["collection"]["sources"]["browser_enabled"]:
            br_posts = self._run_browser(posts)
            posts = self._merge_posts(posts, br_posts)

        # Deduplicate and stratify
        posts = self._deduplicate(posts)
        self._assign_tiers(posts)

        # Store
        self.db.insert_posts(posts)
        self.db.insert_comments(comments)

        # Export JSONL
        processed_dir = Path(self.config["paths"]["data_processed"])
        processed_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(processed_dir / "posts_all.jsonl", [p.to_dict() for p in posts])
        write_jsonl(processed_dir / "comments_sample.jsonl", [c.to_dict() for c in comments])

        # Crossrefs as JSONL
        if crossrefs:
            write_jsonl(processed_dir / "crossrefs.jsonl", crossrefs)

        # Build report
        report = CollectionReport(
            total_posts=len(posts),
            total_comments=len(comments),
            posts_per_subreddit=self.db.count_by_subreddit(),
            posts_per_source=self._count_by_source(posts),
            posts_per_tier=self._count_by_tier(posts),
            gaps=self._find_gaps(posts),
        )

        logger.info(report.summary())
        return report

    def _run_kaggle(self) -> tuple[list[Post], list[dict]]:
        kaggle_cfg = self.config["paths"]["kaggle"]
        all_subreddits = self._all_target_subreddits()

        loader = KaggleLoader(
            ucsd_path=Path(kaggle_cfg["ucsd_dataset"]) if kaggle_cfg.get("ucsd_dataset") else None,
            snap_path=Path(kaggle_cfg["snap_dataset"]) if kaggle_cfg.get("snap_dataset") else None,
            subreddit_filter=all_subreddits,
            time_window_years=self.config["collection"]["time_window_years"],
        )

        posts = loader.load_posts()
        crossrefs = loader.load_crossref_data()
        return posts, crossrefs

    def _run_praw(self, existing_posts: list[Post]) -> tuple[list[Post], list[Comment]]:
        creds = self.config["credentials"]["reddit"]
        if not creds.get("client_id") or creds["client_id"] == "${REDDIT_CLIENT_ID}":
            logger.warning("Reddit API credentials not configured, skipping PRAW")
            return [], []

        all_subreddits = self._all_target_subreddits()
        existing_subs = {p.subreddit.lower() for p in existing_posts}
        needed_subs = [s for s in all_subreddits if s.lower() not in existing_subs]

        if not needed_subs:
            logger.info("All subreddits covered by Kaggle, skipping PRAW")
            return [], []

        collector = PRAWCollector(
            client_id=creds["client_id"],
            client_secret=creds["client_secret"],
            user_agent=creds.get("user_agent", "karmaforge-v1/0.1"),
            subreddits=needed_subs,
            posts_per_subreddit=self.config["collection"]["posts_per_subreddit"],
        )

        if not collector.authenticate():
            return [], []

        return collector.collect_all()

    def _run_thirdparty(self, existing_posts: list[Post]) -> list[Post]:
        existing_subs = {p.subreddit.lower() for p in existing_posts}
        posts_per_sub = self.config["collection"]["posts_per_subreddit"]
        undercovered = [
            sub for sub, count in self._count_by_subreddit(existing_posts).items()
            if count < posts_per_sub * 0.5
        ]

        if not undercovered:
            logger.info("All subreddits have sufficient coverage, skipping third-party")
            return []

        scraper = ThirdPartyScraper(request_delay=2.0)
        all_posts = []
        for sub in undercovered:
            posts = scraper.scrape_subreddit_top_posts(sub, limit=posts_per_sub)
            all_posts.extend(posts)

        return all_posts

    def _run_browser(self, existing_posts: list[Post]) -> list[Post]:
        posts_per_sub = self.config["collection"]["posts_per_subreddit"]
        critical_subs = self._all_target_subreddits()
        existing_counts = self._count_by_subreddit(existing_posts)
        needed_subs = [s for s in critical_subs if existing_counts.get(s, 0) < 100]

        if not needed_subs:
            logger.info("No critical gaps, skipping browser collection")
            return []

        collector = BrowserCollector(headless=True, request_delay=(3.0, 8.0))
        if not collector.initialize():
            return []

        all_posts = []
        for sub in needed_subs[:3]:  # Max 3 subreddits via browser (very slow)
            posts = collector.collect_subreddit_top_posts(sub, limit=posts_per_sub)
            all_posts.extend(posts)

        return all_posts

    def _merge_posts(self, existing: list[Post], new: list[Post]) -> list[Post]:
        existing_ids = {p.post_id for p in existing}
        added = [p for p in new if p.post_id not in existing_ids]
        return existing + added

    def _deduplicate(self, posts: list[Post]) -> list[Post]:
        seen: dict[str, Post] = {}
        for p in posts:
            if p.post_id in seen:
                existing = seen[p.post_id]
                if p.upvotes > existing.upvotes:
                    seen[p.post_id] = p
            else:
                seen[p.post_id] = p

        # Crosspost dedup: same post in multiple subreddits, keep highest upvotes
        url_map: dict[str, Post] = {}
        for p in seen.values():
            if p.url:
                if p.url in url_map:
                    if p.upvotes > url_map[p.url].upvotes:
                        url_map[p.url] = p
                else:
                    url_map[p.url] = p

        # Build final: keep posts with unique post_ids
        final_ids = {p.post_id for p in url_map.values()} | {p.post_id for p in seen.values()}
        return [seen[pid] for pid in final_ids if pid in seen]

    def _assign_tiers(self, posts: list[Post]) -> None:
        tier_map = {}
        for tier_name, subs in self.config["collection"]["subreddits"].items():
            for sub in subs:
                tier_map[sub.lower()] = Tier(tier_name)

        for p in posts:
            p.tier = tier_map.get(p.subreddit.lower())

    def _all_target_subreddits(self) -> list[str]:
        subs = []
        for tier_subs in self.config["collection"]["subreddits"].values():
            subs.extend(tier_subs)
        exclude = set(s.lower() for s in self.config["collection"].get("exclude_subreddits", []))
        return [s for s in subs if s.lower() not in exclude]

    @staticmethod
    def _count_by_subreddit(posts: list[Post]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for p in posts:
            counts[p.subreddit.lower()] = counts.get(p.subreddit.lower(), 0) + 1
        return counts

    @staticmethod
    def _count_by_source(posts: list[Post]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for p in posts:
            counts[p.source_dataset] = counts.get(p.source_dataset, 0) + 1
        return counts

    @staticmethod
    def _count_by_tier(posts: list[Post]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for p in posts:
            tier = p.tier.value if p.tier else "unknown"
            counts[tier] = counts.get(tier, 0) + 1
        return counts

    def _find_gaps(self, posts: list[Post]) -> list[dict]:
        gaps = []
        posts_per_sub = self.config["collection"]["posts_per_subreddit"]
        counts = self._count_by_subreddit(posts)
        for sub in self._all_target_subreddits():
            count = counts.get(sub.lower(), 0)
            if count < posts_per_sub:
                gaps.append({
                    "subreddit": sub,
                    "current_count": count,
                    "target_count": posts_per_sub,
                    "shortfall": posts_per_sub - count,
                })
        return gaps

    def _load_config(self) -> dict:
        with open(self.config_path, "r", encoding="utf-8") as f:
            raw = f.read()
        raw = self._substitute_env_vars(raw)
        return yaml.safe_load(raw)

    @staticmethod
    def _substitute_env_vars(text: str) -> str:
        import os
        import re
        pattern = r'\$\{(\w+)\}'

        def replacer(match):
            var_name = match.group(1)
            value = os.environ.get(var_name, "")
            if not value:
                logger.debug("Environment variable %s not set, using empty string", var_name)
            return value

        return re.sub(pattern, replacer, text)
