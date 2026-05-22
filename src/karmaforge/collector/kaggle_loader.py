"""Kaggle dataset loader — UCSD Reddit Submissions + Stanford SNAP Hyperlinks.

Loads academic Reddit datasets and normalizes to unified Post/Comment schemas.
Handles column mapping auto-detection since different dataset versions have different columns.
"""

import csv
import gzip
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from ..storage import Post, Comment, ContentType

logger = logging.getLogger(__name__)

UCSD_COLUMN_MAP = {
    "id": ["id", "post_id", "submission_id", "name"],
    "subreddit": ["subreddit", "subreddit_name", "sub"],
    "title": ["title", "post_title"],
    "body": ["selftext", "body", "text", "content", "post_body"],
    "author": ["author", "author_name", "username", "user"],
    "created_utc": ["created_utc", "created", "timestamp", "created_at", "date"],
    "upvotes": ["score", "upvotes", "ups", "points", "net_upvotes"],
    "upvote_ratio": ["upvote_ratio", "ratio", "up_ratio"],
    "num_comments": ["num_comments", "comments", "comment_count", "n_comments"],
    "flair": ["link_flair_text", "flair", "post_flair"],
    "is_oc": ["is_oc", "oc", "original_content"],
    "is_nsfw": ["over_18", "nsfw", "is_nsfw"],
    "url": ["url", "permalink", "link"],
}


class KaggleLoader:
    def __init__(
        self,
        ucsd_path: Optional[Path] = None,
        snap_path: Optional[Path] = None,
        subreddit_filter: Optional[list[str]] = None,
        time_window_years: int = 2,
    ) -> None:
        self.ucsd_path = Path(ucsd_path) if ucsd_path else None
        self.snap_path = Path(snap_path) if snap_path else None
        self.subreddit_filter = set(s.lower() for s in subreddit_filter) if subreddit_filter else None
        self.time_window_years = time_window_years
        self._column_map: Optional[dict[str, str]] = None

    def load_posts(self) -> list[Post]:
        if not self.ucsd_path or not self.ucsd_path.exists():
            logger.warning("UCSD dataset not found at %s", self.ucsd_path)
            return []

        logger.info("Loading UCSD dataset from %s", self.ucsd_path)
        df = self._read_csv(self.ucsd_path)
        self._column_map = self.detect_schema(df.columns.tolist())
        logger.info("Detected column mapping: %s", self._column_map)

        posts = []
        cutoff = datetime.now(timezone.utc).replace(year=datetime.now().year - self.time_window_years)

        for _, row in df.iterrows():
            try:
                post = self._row_to_post(row)
                if post.created_utc and post.created_utc < cutoff:
                    continue
                if self.subreddit_filter and post.subreddit.lower() not in self.subreddit_filter:
                    continue
                posts.append(post)
            except Exception:
                continue

        logger.info("Loaded %d posts from UCSD dataset", len(posts))
        return posts

    def load_crossref_data(self) -> list[dict]:
        if not self.snap_path or not self.snap_path.exists():
            logger.warning("Stanford SNAP dataset not found at %s", self.snap_path)
            return []

        logger.info("Loading SNAP cross-reference data from %s", self.snap_path)
        crossrefs = []
        opener = gzip.open if self.snap_path.suffix == ".gz" else open
        mode = "rt" if self.snap_path.suffix == ".gz" else "r"

        with opener(str(self.snap_path), mode, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                parts = line.strip().split("\t")
                if len(parts) >= 2:
                    crossrefs.append({
                        "source_subreddit": parts[0],
                        "target_post_id": parts[1],
                    })

        logger.info("Loaded %d cross-references", len(crossrefs))
        return crossrefs

    def _row_to_post(self, row: pd.Series) -> Post:
        col = self._column_map or {}
        row_dict = row.to_dict()

        def get_val(*keys):
            for k in keys:
                if k in col and col[k] in row_dict:
                    val = row_dict[col[k]]
                    if pd.notna(val):
                        return val
            return None

        created = get_val("created_utc")
        if created is not None:
            try:
                if isinstance(created, (int, float)):
                    created = datetime.fromtimestamp(float(created), tz=timezone.utc)
                else:
                    created = pd.to_datetime(created).to_pydatetime()
            except Exception:
                created = None

        url = str(get_val("url") or "")
        content_type = ContentType.TEXT
        if url:
            if any(x in url.lower() for x in [".jpg", ".png", ".gif", "imgur.com", "i.redd.it"]):
                if ".gif" in url.lower() or "gfycat" in url.lower():
                    content_type = ContentType.VIDEO
                else:
                    content_type = ContentType.IMAGE
            elif any(x in url.lower() for x in ["youtube.com", "youtu.be", "v.redd.it"]):
                content_type = ContentType.VIDEO
            elif url.startswith("http"):
                content_type = ContentType.LINK

        post_id = str(get_val("id") or "")
        if post_id and not post_id.startswith("t3_"):
            post_id = f"t3_{post_id}" if not post_id.startswith("t3_") else post_id

        return Post(
            post_id=post_id,
            subreddit=str(get_val("subreddit") or "unknown").replace("r/", ""),
            title=str(get_val("title") or ""),
            body=str(get_val("body") or ""),
            author=str(get_val("author") or "[deleted]"),
            created_utc=created,
            upvotes=int(get_val("upvotes") or 0),
            upvote_ratio=float(get_val("upvote_ratio") or 0.0),
            num_comments=int(get_val("num_comments") or 0),
            flair=str(get_val("flair")) if get_val("flair") else None,
            is_oc=bool(int(get_val("is_oc") or 0)),
            is_nsfw=bool(int(get_val("is_nsfw") or 0)),
            content_type=content_type,
            url=url if url else None,
            source_dataset="kaggle_ucsd",
        )

    def _read_csv(self, path: Path) -> pd.DataFrame:
        opener = gzip.open if path.suffix == ".gz" else open
        mode = "rt" if path.suffix == ".gz" else "r"

        with opener(str(path), mode, encoding="utf-8", errors="replace") as f:
            sample = f.read(4096)
            f.seek(0)
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(sample)
            delimiter = dialect.delimiter

        kwargs = {"sep": delimiter, "low_memory": False, "on_bad_lines": "skip"}
        if path.suffix == ".gz":
            kwargs["compression"] = "gzip"

        return pd.read_csv(str(path), **kwargs)

    @staticmethod
    def detect_schema(columns: list[str]) -> dict[str, str]:
        mapping = {}
        columns_lower = [c.lower().strip() for c in columns]

        for target, candidates in UCSD_COLUMN_MAP.items():
            for candidate in candidates:
                if candidate in columns_lower:
                    idx = columns_lower.index(candidate)
                    mapping[target] = columns[idx]
                    break

        logger.info("Schema detection: found %d/%d fields", len(mapping), len(UCSD_COLUMN_MAP))
        missing = [k for k in UCSD_COLUMN_MAP if k not in mapping]
        if missing:
            logger.info("Missing fields (will use defaults): %s", missing)
        return mapping
