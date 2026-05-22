"""SQLite database layer for KarmaForge v1."""

import sqlite3
import json
from pathlib import Path
from typing import Optional, Union

from .schemas import Post, Comment, SubredditMeta, Tier


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS posts (
    post_id TEXT PRIMARY KEY,
    subreddit TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    author TEXT DEFAULT '[deleted]',
    created_utc TIMESTAMP,
    upvotes INTEGER NOT NULL DEFAULT 0,
    upvote_ratio REAL DEFAULT 0.0,
    num_comments INTEGER DEFAULT 0,
    awards_json TEXT DEFAULT '{}',
    flair TEXT,
    is_oc INTEGER DEFAULT 0,
    is_nsfw INTEGER DEFAULT 0,
    content_type TEXT DEFAULT 'text',
    is_crosspost INTEGER DEFAULT 0,
    crosspost_source TEXT,
    url TEXT,
    source_dataset TEXT NOT NULL DEFAULT 'unknown',
    tier TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS comments (
    comment_id TEXT PRIMARY KEY,
    post_id TEXT NOT NULL REFERENCES posts(post_id),
    parent_id TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    author TEXT DEFAULT '[deleted]',
    created_utc TIMESTAMP,
    upvotes INTEGER DEFAULT 0,
    depth INTEGER DEFAULT 0,
    thread_root_id TEXT
);

CREATE TABLE IF NOT EXISTS subreddit_meta (
    name TEXT PRIMARY KEY,
    description TEXT DEFAULT '',
    subscriber_count INTEGER DEFAULT 0,
    tier TEXT NOT NULL,
    daily_activity INTEGER DEFAULT 0,
    content_type_tags_json TEXT DEFAULT '[]',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_posts_subreddit ON posts(subreddit);
CREATE INDEX IF NOT EXISTS idx_posts_tier ON posts(tier);
CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_utc);
CREATE INDEX IF NOT EXISTS idx_posts_upvotes ON posts(upvotes);
CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
CREATE INDEX IF NOT EXISTS idx_comments_depth ON comments(depth);
"""


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def create_schema(self) -> None:
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()

    def insert_posts(self, posts: list[Post]) -> int:
        columns = [
            "post_id", "subreddit", "title", "body", "author", "created_utc",
            "upvotes", "upvote_ratio", "num_comments", "awards_json", "flair",
            "is_oc", "is_nsfw", "content_type", "is_crosspost", "crosspost_source",
            "url", "source_dataset", "tier",
        ]
        rows = []
        for p in posts:
            d = p.to_dict()
            awards = json.dumps(d.pop("awards", {}))
            d["awards_json"] = awards
            row = tuple(d.get(col) for col in columns)
            rows.append(row)
        placeholders = ", ".join("?" * len(columns))
        sql = f"INSERT OR REPLACE INTO posts ({', '.join(columns)}) VALUES ({placeholders})"
        self.conn.executemany(sql, rows)
        self.conn.commit()
        return len(rows)

    def insert_comments(self, comments: list[Comment]) -> int:
        rows = [[
            c.comment_id, c.post_id, c.parent_id, c.body, c.author,
            c.created_utc.isoformat() if c.created_utc else None,
            c.upvotes, c.depth, c.thread_root_id,
        ] for c in comments]
        sql = (
            "INSERT OR REPLACE INTO comments "
            "(comment_id, post_id, parent_id, body, author, created_utc, upvotes, depth, thread_root_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        self.conn.executemany(sql, rows)
        self.conn.commit()
        return len(rows)

    def insert_subreddit_meta(self, metas: list[SubredditMeta]) -> int:
        rows = [[
            m.name, m.description, m.subscriber_count,
            m.tier.value if m.tier else "t2",
            m.daily_activity, json.dumps(m.content_type_tags),
        ] for m in metas]
        sql = (
            "INSERT OR REPLACE INTO subreddit_meta "
            "(name, description, subscriber_count, tier, daily_activity, content_type_tags_json) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        self.conn.executemany(sql, rows)
        self.conn.commit()
        return len(rows)

    def get_posts_by_subreddit(self, subreddit: str, limit: Optional[int] = None) -> list[Post]:
        sql = "SELECT * FROM posts WHERE subreddit = ? ORDER BY upvotes DESC"
        if limit:
            sql += f" LIMIT {limit}"
        rows = self.conn.execute(sql, (subreddit,)).fetchall()
        return [self._row_to_post(r) for r in rows]

    def get_posts_by_tier(self, tier: Union[Tier, str]) -> list[Post]:
        tier_str = tier.value if isinstance(tier, Tier) else tier
        rows = self.conn.execute(
            "SELECT * FROM posts WHERE tier = ? ORDER BY upvotes DESC", (tier_str,)
        ).fetchall()
        return [self._row_to_post(r) for r in rows]

    def get_all_posts(self) -> list[Post]:
        rows = self.conn.execute("SELECT * FROM posts").fetchall()
        return [self._row_to_post(r) for r in rows]

    def get_comments_for_post(self, post_id: str, limit: int = 20) -> list[Comment]:
        rows = self.conn.execute(
            "SELECT * FROM comments WHERE post_id = ? ORDER BY upvotes DESC LIMIT ?",
            (post_id, limit),
        ).fetchall()
        return [self._row_to_comment(r) for r in rows]

    def get_deep_threads(self, post_id: str, min_depth: int = 3, limit: int = 5) -> list[Comment]:
        rows = self.conn.execute(
            "SELECT * FROM comments WHERE post_id = ? AND depth >= ? ORDER BY depth DESC LIMIT ?",
            (post_id, min_depth, limit),
        ).fetchall()
        return [self._row_to_comment(r) for r in rows]

    def count_by_subreddit(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT subreddit, COUNT(*) as cnt FROM posts GROUP BY subreddit"
        ).fetchall()
        return {r["subreddit"]: r["cnt"] for r in rows}

    def count_posts(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @staticmethod
    def _row_to_post(row: sqlite3.Row) -> Post:
        d = dict(row)
        d["content_type"] = d.get("content_type", "text")
        awards_json = d.pop("awards_json", "{}")
        d["awards"] = json.loads(awards_json) if awards_json else {}
        tier_val = d.pop("tier", None)
        d["tier"] = Tier(tier_val) if tier_val else None
        d.pop("created_at", None)
        created = d.get("created_utc")
        if created and isinstance(created, str):
            d["created_utc"] = None  # Will be parsed if needed
        return Post(**{k: v for k, v in d.items() if k in Post.__dataclass_fields__})

    @staticmethod
    def _row_to_comment(row: sqlite3.Row) -> Comment:
        d = dict(row)
        return Comment(**{k: v for k, v in d.items() if k in Comment.__dataclass_fields__})
