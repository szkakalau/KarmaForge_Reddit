"""Tests for SQLite database layer."""

import tempfile
from pathlib import Path

import pytest
from karmaforge.storage import Database, Post, Tier, ContentType


class TestDatabase:
    @pytest.fixture
    def db(self):
        path = Path(tempfile.mktemp(suffix=".db"))
        database = Database(path)
        database.create_schema()
        yield database
        database.close()

    def test_create_schema(self, db):
        tables = db.query("SELECT name FROM sqlite_master WHERE type='table'")
        table_names = [t["name"] for t in tables]
        assert "posts" in table_names
        assert "comments" in table_names
        assert "subreddit_meta" in table_names

    def test_insert_and_get_posts(self, db, sample_posts):
        count = db.insert_posts(sample_posts)
        assert count == len(sample_posts)

        all_posts = db.get_all_posts()
        assert len(all_posts) == len(sample_posts)

    def test_get_posts_by_subreddit(self, db, sample_posts):
        db.insert_posts(sample_posts)
        posts = db.get_posts_by_subreddit("productivity")
        assert len(posts) >= 1
        assert all(p.subreddit.lower() == "productivity" for p in posts)

    def test_get_posts_by_tier(self, db, sample_posts):
        db.insert_posts(sample_posts)
        posts = db.get_posts_by_tier(Tier.T2)
        assert len(posts) >= 1
        assert all(p.tier == Tier.T2 for p in posts)

    def test_count_by_subreddit(self, db, sample_posts):
        db.insert_posts(sample_posts)
        counts = db.count_by_subreddit()
        assert isinstance(counts, dict)
        assert len(counts) > 0

    def test_count_posts(self, db, sample_posts):
        db.insert_posts(sample_posts)
        assert db.count_posts() == len(sample_posts)

    def test_insert_comments(self, db, sample_posts, sample_comments):
        db.insert_posts(sample_posts)
        count = db.insert_comments(sample_comments)
        assert count == len(sample_comments)

    def test_empty_db(self, db):
        assert db.count_posts() == 0
        assert db.get_all_posts() == []
