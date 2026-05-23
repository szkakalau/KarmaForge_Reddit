"""Tests for tracker module — metrics, PostTracker."""

import json
import tempfile
from pathlib import Path

import pytest

from karmaforge.tracker import TrackingRecord, FeedbackEntry
from karmaforge.tracker.metrics import (
    classify_performance,
    get_subreddit_median,
    get_performance_label,
)
from karmaforge.tracker.post_tracker import PostTracker


# ── classify_performance ─────────────────────────────────────────

class TestClassifyPerformance:
    def test_super_viral(self):
        assert classify_performance(1000, 50) == "super_viral"  # 20x

    def test_viral(self):
        assert classify_performance(200, 50) == "viral"  # 4x

    def test_passing(self):
        assert classify_performance(80, 50) == "passing"  # 1.6x

    def test_failed(self):
        assert classify_performance(30, 50) == "failed"  # 0.6x

    def test_boundary_super_viral(self):
        assert classify_performance(500, 50) == "super_viral"  # exactly 10x

    def test_boundary_viral(self):
        assert classify_performance(150, 50) == "viral"  # exactly 3x

    def test_boundary_passing(self):
        assert classify_performance(75, 50) == "passing"  # exactly 1.5x

    def test_zero_votes(self):
        assert classify_performance(0, 50) == "failed"

    def test_zero_median_no_votes(self):
        assert classify_performance(0, 0) == "failed"

    def test_zero_median_some_votes(self):
        assert classify_performance(10, 0) == "passing"


# ── get_subreddit_median ─────────────────────────────────────────

class TestGetSubredditMedian:
    def test_missing_db_returns_default(self):
        median = get_subreddit_median("/nonexistent/path.db", "productivity")
        assert median == 50.0

    def test_returns_float(self, temp_db):
        median = get_subreddit_median(temp_db.db_path, "productivity")
        assert isinstance(median, float)
        assert median > 0


# ── get_performance_label ────────────────────────────────────────

class TestGetPerformanceLabel:
    def test_all_labels(self):
        assert "super viral" in get_performance_label(1000, 50)
        assert "viral" in get_performance_label(200, 50)
        assert "passing" in get_performance_label(80, 50)
        assert "failed" in get_performance_label(10, 50)

    def test_label_includes_numbers(self):
        label = get_performance_label(100, 40)
        assert "100" in label
        assert "40" in label


# ── PostTracker ──────────────────────────────────────────────────

class TestPostTracker:
    def test_initialize_without_playwright(self):
        tracker = PostTracker()
        # playwright may or may not be installed; initialize returns bool
        result = tracker.initialize()
        assert isinstance(result, bool)

    def test_url_to_old_reddit(self):
        result = PostTracker._to_old_reddit("https://www.reddit.com/r/programming/comments/abc123")
        assert result.startswith("https://old.reddit.com")
        assert "/r/programming/comments/abc123" in result

    def test_url_to_old_reddit_already_old(self):
        result = PostTracker._to_old_reddit("https://old.reddit.com/r/programming/comments/abc123")
        assert result == "https://old.reddit.com/r/programming/comments/abc123"

    def test_url_to_old_reddit_no_protocol(self):
        result = PostTracker._to_old_reddit("reddit.com/r/test/comments/xyz")
        assert result.startswith("https://old.reddit.com")

    def test_save_and_load_feedback(self):
        tracker = PostTracker()
        # Manually create a feedback entry via _save_feedback
        from karmaforge.tracker import FeedbackEntry
        entry = FeedbackEntry(
            generation_id="test_gen_001",
            tracked_at="2024-01-15T12:00:00Z",
            url="https://old.reddit.com/r/test/comments/abc",
            subreddit="test",
            title="Test Title",
            body="Test body content here",
            pattern_id="pattern_01",
            actual_upvotes=100,
            num_comments=20,
            upvote_ratio=0.85,
            performance="viral",
            subreddit_median=50.0,
        )
        tracker._save_feedback(entry)

        entries = tracker.load_feedback()
        assert len(entries) >= 1
        found = any(e["generation_id"] == "test_gen_001" for e in entries)
        assert found

        # Cleanup: remove test entry
        tracker._feedback_path.unlink()

    def test_feedback_count(self):
        tracker = PostTracker()
        # Start from scratch
        if tracker._feedback_path.exists():
            tracker._feedback_path.unlink()

        assert tracker.feedback_count() == 0

        from karmaforge.tracker import FeedbackEntry
        entry = FeedbackEntry(
            generation_id="count_test",
            tracked_at="2024-01-15T12:00:00Z",
            url="https://old.reddit.com/r/test/comments/xyz",
            subreddit="test",
            title="T",
            body="B",
            pattern_id="p1",
            actual_upvotes=10,
            num_comments=2,
            upvote_ratio=0.7,
            performance="passing",
            subreddit_median=50.0,
        )
        tracker._save_feedback(entry)
        assert tracker.feedback_count() == 1

        tracker._feedback_path.unlink()

    def test_load_feedback_empty_file(self):
        tracker = PostTracker()
        # Ensure clean state
        if tracker._feedback_path.exists():
            tracker._feedback_path.unlink()
        tracker._feedback_path.write_text("", encoding="utf-8")
        entries = tracker.load_feedback()
        assert entries == []
        tracker._feedback_path.unlink()

    def test_load_feedback_missing_file(self):
        tracker = PostTracker(feedback_path="/nonexistent/path/feedback.jsonl")
        entries = tracker.load_feedback()
        assert entries == []

    def test_save_feedback_truncates_body(self):
        tracker = PostTracker()
        from karmaforge.tracker import FeedbackEntry
        long_body = "x" * 500
        entry = FeedbackEntry(
            generation_id="trunc_test",
            tracked_at="2024-01-15T12:00:00Z",
            url="https://old.reddit.com/r/test/comments/abc",
            subreddit="test",
            title="T",
            body=long_body,
            pattern_id="p1",
            actual_upvotes=10,
            num_comments=2,
            upvote_ratio=0.7,
            performance="passing",
            subreddit_median=50.0,
        )
        tracker._save_feedback(entry)

        entries = tracker.load_feedback()
        saved = next(e for e in entries if e["generation_id"] == "trunc_test")
        assert len(saved["body"]) <= 200
        assert saved["body"] == long_body[:200]

        tracker._feedback_path.unlink()

    def test_track_requires_playwright(self):
        tracker = PostTracker()
        tracker._available = False
        result = tracker.track(
            "https://reddit.com/r/test/comments/abc",
            "gen_001", "test", "Title", "Body", "pat_01",
        )
        assert result is None
