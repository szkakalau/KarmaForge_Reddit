"""Tests for data schemas."""

from datetime import datetime, timezone
from karmaforge.storage import Post, Comment, SubredditMeta, ContentType, Tier


class TestContentType:
    def test_from_string_text(self):
        assert ContentType.from_string("text") == ContentType.TEXT
        assert ContentType.from_string("self") == ContentType.TEXT

    def test_from_string_image(self):
        assert ContentType.from_string("image") == ContentType.IMAGE
        assert ContentType.from_string("photo") == ContentType.IMAGE

    def test_from_string_unknown(self):
        assert ContentType.from_string("unknown") == ContentType.TEXT


class TestTier:
    def test_from_subscriber_count_t1(self):
        assert Tier.from_subscriber_count(50_000_000) == Tier.T1
        assert Tier.from_subscriber_count(20_000_000) == Tier.T1

    def test_from_subscriber_count_t2(self):
        assert Tier.from_subscriber_count(5_000_000) == Tier.T2
        assert Tier.from_subscriber_count(1_000_000) == Tier.T2

    def test_from_subscriber_count_t3(self):
        assert Tier.from_subscriber_count(500_000) == Tier.T3
        assert Tier.from_subscriber_count(100_000) == Tier.T3


class TestPost:
    def test_create_minimal(self):
        p = Post(post_id="t3_abc", subreddit="test", title="Hello")
        assert p.post_id == "t3_abc"
        assert p.title == "Hello"
        assert p.content_type == ContentType.TEXT

    def test_to_dict_and_back(self):
        p = Post(
            post_id="t3_xyz",
            subreddit="test",
            title="Test Post",
            body="Some content",
            upvotes=100,
            content_type=ContentType.IMAGE,
            tier=Tier.T2,
            created_utc=datetime(2024, 1, 15, tzinfo=timezone.utc),
        )
        d = p.to_dict()
        p2 = Post.from_dict(d)
        assert p2.post_id == p.post_id
        assert p2.title == p.title
        assert p2.upvotes == p.upvotes
        assert p2.content_type == ContentType.IMAGE
        assert p2.tier == Tier.T2


class TestComment:
    def test_create(self):
        c = Comment(comment_id="t1_a", post_id="t3_b", parent_id="t3_b", body="Nice post", upvotes=5)
        assert c.comment_id == "t1_a"
        assert c.depth == 0

    def test_to_dict(self):
        c = Comment(
            comment_id="t1_x", post_id="t3_y", parent_id="t1_z",
            body="Reply", depth=2, upvotes=10,
        )
        d = c.to_dict()
        assert d["comment_id"] == "t1_x"
        assert d["depth"] == 2
