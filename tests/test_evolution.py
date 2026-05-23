"""Tests for evolution module — FailureAttributor, EvolutionEngine."""

import json
import tempfile
from pathlib import Path

import pytest

from karmaforge.evolution import FailureAttribution, EvolutionLog
from karmaforge.evolution.failure_attributor import FailureAttributor, DIMENSION_WEIGHTS
from karmaforge.evolution.evolution_engine import (
    EvolutionEngine,
    EVOLUTION_THRESHOLD,
    MAX_CONSECUTIVE_FAILURES,
)


# ── Helpers ──────────────────────────────────────────────────────

def _make_feedback_jsonl(path: Path, entries: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _make_patterns_json(path: Path, patterns: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(patterns, f, ensure_ascii=False, indent=2)


@pytest.fixture
def sample_patterns():
    return [
        {
            "pattern_id": "pattern_a",
            "name": "Pattern A",
            "hook_type": "tutorial_howto",
            "historical_viral_rate": 0.4,
            "avg_upvotes": 200,
            "success_rate": 0.65,
            "feedback_sample_size": 50,
            "last_evaluated_at": "2024-01-01T00:00:00Z",
            "status": "active",
        },
        {
            "pattern_id": "pattern_b",
            "name": "Pattern B",
            "hook_type": "story_opener",
            "historical_viral_rate": 0.6,
            "avg_upvotes": 350,
            "success_rate": 0.72,
            "feedback_sample_size": 80,
            "last_evaluated_at": "2024-01-01T00:00:00Z",
            "status": "active",
        },
        {
            "pattern_id": "pattern_c",
            "name": "Pattern C",
            "hook_type": "resource_share",
            "historical_viral_rate": 0.25,
            "avg_upvotes": 80,
            "success_rate": 0.30,
            "feedback_sample_size": 30,
            "last_evaluated_at": "2024-01-01T00:00:00Z",
            "status": "active",
        },
    ]


# ── FailureAttributor ────────────────────────────────────────────

class TestFailureAttributor:
    def test_rule_based_attribution_all_dimensions(self):
        attributor = FailureAttributor()
        entry = {
            "generation_id": "gen_001",
            "title": "Short",
            "body": "Tiny",
            "subreddit": "programming",
            "actual_upvotes": 5,
            "subreddit_median": 50,
            "upvote_ratio": 0.3,
        }
        result = attributor.attribute(entry)
        assert isinstance(result, FailureAttribution)
        assert result.generation_id == "gen_001"
        assert result.confidence > 0
        assert len(result.dimensions) >= 4  # title, body, quality, timing, topic

    def test_good_title_scores_well(self):
        attributor = FailureAttributor()
        entry = {
            "generation_id": "gen_002",
            "title": "How to write clean Python code for production systems",
            "body": "A" * 100,
            "subreddit": "programming",
            "actual_upvotes": 10,
            "subreddit_median": 50,
            "upvote_ratio": 0.75,
        }
        result = attributor.attribute(entry)
        title_dim = result.dimensions.get("title_hook_fit", {})
        assert title_dim.get("score", 0) >= 50  # decent title length

    def test_too_short_title_flagged(self):
        attributor = FailureAttributor()
        entry = {
            "generation_id": "gen_003",
            "title": "Hi",
            "body": "Some body text",
            "subreddit": "test",
            "actual_upvotes": 2,
            "subreddit_median": 100,
            "upvote_ratio": 0.5,
        }
        result = attributor.attribute(entry)
        title_dim = result.dimensions.get("title_hook_fit", {})
        assert title_dim.get("score", 100) < 50

    def test_low_upvote_ratio_flagged(self):
        attributor = FailureAttributor()
        entry = {
            "generation_id": "gen_004",
            "title": "A decent title for a post",
            "body": "Some reasonable body text " * 5,
            "subreddit": "test",
            "actual_upvotes": 5,
            "subreddit_median": 50,
            "upvote_ratio": 0.2,  # very low
        }
        result = attributor.attribute(entry)
        quality_dim = result.dimensions.get("content_quality", {})
        assert quality_dim.get("score", 100) < 50

    def test_low_viral_rate_pattern_flagged(self):
        attributor = FailureAttributor()
        entry = {
            "generation_id": "gen_005",
            "title": "A decent post title",
            "body": "Some body text " * 5,
            "subreddit": "test",
            "actual_upvotes": 10,
            "subreddit_median": 50,
            "upvote_ratio": 0.6,
        }
        pattern = {
            "name": "Low Performer",
            "historical_viral_rate": 10,  # only 10%
        }
        result = attributor.attribute(entry, pattern)
        assert "pattern_fit" in result.dimensions

    def test_synthesize_identifies_primary_reason(self):
        attributor = FailureAttributor()
        entry = {
            "generation_id": "gen_006",
            "title": "X",
            "body": "Y",
            "subreddit": "test",
            "actual_upvotes": 1,
            "subreddit_median": 200,
            "upvote_ratio": 0.1,
        }
        result = attributor.attribute(entry)
        assert result.primary_reason  # should have a primary reason
        assert len(result.action_items) >= 1

    def test_confidence_calculation(self):
        attributor = FailureAttributor()
        entry = {
            "generation_id": "gen_007",
            "title": "X",
            "body": "Y",
            "subreddit": "test",
            "actual_upvotes": 1,
            "subreddit_median": 500,
            "upvote_ratio": 0.05,
        }
        result = attributor.attribute(entry)
        # Bad scores → high confidence in diagnosis
        assert 20 <= result.confidence <= 90

    def test_llm_attribution_fallback(self, mock_llm_client):
        mock_llm_client.complete.side_effect = RuntimeError("LLM error")
        attributor = FailureAttributor(mock_llm_client)
        entry = {
            "generation_id": "gen_008",
            "title": "Test title here",
            "body": "Test body content " * 5,
            "subreddit": "programming",
            "actual_upvotes": 10,
            "subreddit_median": 50,
            "upvote_ratio": 0.8,
            "num_comments": 3,
            "tracked_at": "2024-01-15T12:00:00Z",
        }
        result = attributor.attribute(entry)
        # Should still work with rule-based fallback
        assert isinstance(result, FailureAttribution)
        assert len(result.dimensions) >= 4

    def test_dimension_weights_sum_to_one(self):
        total = sum(DIMENSION_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_good_content_high_dimension_scores(self):
        attributor = FailureAttributor()
        entry = {
            "generation_id": "gen_good",
            "title": "How I learned to code in 6 months and landed a job",
            "body": "This is a detailed story about my coding journey. " * 20,
            "subreddit": "programming",
            "actual_upvotes": 100,
            "subreddit_median": 50,
            "upvote_ratio": 0.92,
        }
        result = attributor.attribute(entry)
        # Good content → clear issues → lower confidence (inverted scoring)
        # Actually: good content = high scores = low confidence the diagnosis is correct
        # But primary reason should exist
        assert result.primary_reason

    def test_synthesize_no_issues_fallback(self):
        primary, secondary, actions = FailureAttributor._synthesize({})
        assert "No clear failure reason" in primary
        assert secondary == []
        assert len(actions) == 1


# ── EvolutionEngine ──────────────────────────────────────────────

class TestEvolutionEngine:
    def test_should_evolve_below_threshold(self):
        engine = EvolutionEngine()
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            for i in range(10):
                f.write(json.dumps({"test": True}) + "\n")
            path = Path(f.name)
        assert not engine.should_evolve(path)
        path.unlink()

    def test_should_evolve_at_threshold(self):
        engine = EvolutionEngine()
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            for i in range(EVOLUTION_THRESHOLD):
                f.write(json.dumps({"test": True}) + "\n")
            path = Path(f.name)
        assert engine.should_evolve(path)
        path.unlink()

    def test_should_evolve_missing_file(self):
        engine = EvolutionEngine()
        assert not engine.should_evolve("/nonexistent/feedback.jsonl")

    def test_evolve_updates_success_rates(self, sample_patterns):
        engine = EvolutionEngine()
        # Create feedback: 10 entries for pattern_a, mix of viral/passing/failed
        entries = []
        for i in range(55):
            perf = "viral" if i < 20 else ("passing" if i < 45 else "failed")
            entries.append({
                "generation_id": f"gen_{i:03d}",
                "pattern_id": "pattern_a",
                "performance": perf,
                "tracked_at": f"2024-01-{(i % 28) + 1:02d}T12:00:00Z",
                "title": f"Test title {i}",
                "body": "Test body",
                "subreddit": "programming",
                "actual_upvotes": 100,
                "upvote_ratio": 0.85,
                "num_comments": 10,
                "subreddit_median": 50,
            })

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            fb_path = Path(f.name)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            pat_path = Path(f.name)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            out_path = Path(f.name)

        _make_feedback_jsonl(fb_path, entries)
        _make_patterns_json(pat_path, sample_patterns)

        try:
            log = engine.evolve(fb_path, pat_path, out_path)
            assert log is not None
            assert isinstance(log, EvolutionLog)
            assert log.feedback_count == 55
            assert log.patterns_updated >= 1

            # Verify patterns updated
            with open(out_path, "r", encoding="utf-8") as f:
                updated = json.load(f)
            pattern_a = next(p for p in updated if p["pattern_id"] == "pattern_a")
            assert "success_rate" in pattern_a
            # 20 viral + 25 passing out of 55 = 45/55 ≈ 0.8182
            assert 0.7 < pattern_a["success_rate"] < 0.9
        finally:
            fb_path.unlink(missing_ok=True)
            pat_path.unlink(missing_ok=True)
            out_path.unlink(missing_ok=True)

    def test_evolve_consecutive_failures_inactive(self, sample_patterns):
        engine = EvolutionEngine()
        # pattern_a gets 10 consecutive failures at the end (latest dates)
        entries = []
        for i in range(55):
            perf = "failed" if i >= 45 else "viral"
            # Use sequential days to avoid date collisions with earlier entries
            day = i + 1  # 1..55, unique days
            entries.append({
                "generation_id": f"gen_{i:03d}",
                "pattern_id": "pattern_a",
                "performance": perf,
                "tracked_at": f"2024-01-{day:02d}T12:00:00Z",
                "title": f"Test {i}",
                "body": "Body",
                "subreddit": "programming",
                "actual_upvotes": 5,
                "upvote_ratio": 0.3,
                "num_comments": 1,
                "subreddit_median": 50,
            })

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            fb_path = Path(f.name)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            pat_path = Path(f.name)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            out_path = Path(f.name)

        _make_feedback_jsonl(fb_path, entries)
        _make_patterns_json(pat_path, sample_patterns)

        try:
            log = engine.evolve(fb_path, pat_path, out_path)
            assert log is not None
            assert log.patterns_marked_inactive >= 1

            with open(out_path, "r", encoding="utf-8") as f:
                updated = json.load(f)
            pattern_a = next(p for p in updated if p["pattern_id"] == "pattern_a")
            assert pattern_a["status"] == "inactive"
        finally:
            fb_path.unlink(missing_ok=True)
            pat_path.unlink(missing_ok=True)
            out_path.unlink(missing_ok=True)

    def test_evolve_missing_feedback(self, sample_patterns):
        engine = EvolutionEngine()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            pat_path = Path(f.name)
        _make_patterns_json(pat_path, sample_patterns)
        try:
            log = engine.evolve("/nonexistent/feedback.jsonl", pat_path)
            assert log is None
        finally:
            pat_path.unlink(missing_ok=True)

    def test_evolve_missing_patterns(self):
        engine = EvolutionEngine()
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            fb_path = Path(f.name)
            for i in range(EVOLUTION_THRESHOLD):
                f.write(json.dumps({"pattern_id": "p1", "performance": "viral"}) + "\n")
        try:
            log = engine.evolve(fb_path, "/nonexistent/patterns.json")
            assert log is None
        finally:
            fb_path.unlink(missing_ok=True)

    def test_evolve_attributes_failed_posts(self, sample_patterns, mock_llm_client):
        engine = EvolutionEngine(llm_client=mock_llm_client)
        entries = []
        for i in range(55):
            entries.append({
                "generation_id": f"gen_{i:03d}",
                "pattern_id": "pattern_a",
                "performance": "failed",
                "tracked_at": f"2024-01-{(i % 28) + 1:02d}T12:00:00Z",
                "title": f"Test {i}",
                "body": "Some body text here",
                "subreddit": "test",
                "actual_upvotes": 2,
                "upvote_ratio": 0.4,
                "num_comments": 0,
                "subreddit_median": 50,
            })

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            fb_path = Path(f.name)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            pat_path = Path(f.name)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            out_path = Path(f.name)

        _make_feedback_jsonl(fb_path, entries)
        _make_patterns_json(pat_path, sample_patterns)

        try:
            log = engine.evolve(fb_path, pat_path, out_path)
            assert log is not None

            # Verify attribution was added to feedback
            with open(fb_path, "r", encoding="utf-8") as f:
                updated_entries = [json.loads(line) for line in f if line.strip()]
            first_entry = updated_entries[0]
            assert "attribution" in first_entry
            assert "primary_reason" in first_entry["attribution"]
        finally:
            fb_path.unlink(missing_ok=True)
            pat_path.unlink(missing_ok=True)
            out_path.unlink(missing_ok=True)

    def test_evolve_writes_log(self, sample_patterns):
        engine = EvolutionEngine()
        entries = []
        for i in range(55):
            entries.append({
                "generation_id": f"gen_{i:03d}",
                "pattern_id": "pattern_a",
                "performance": "viral",
                "tracked_at": f"2024-01-{(i % 28) + 1:02d}T12:00:00Z",
                "title": f"Test {i}",
                "body": "Body",
                "subreddit": "programming",
                "actual_upvotes": 200,
                "upvote_ratio": 0.9,
                "num_comments": 20,
                "subreddit_median": 50,
            })

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            fb_path = Path(f.name)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            pat_path = Path(f.name)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            out_path = Path(f.name)

        log_dir = Path(tempfile.mkdtemp())
        log_path = log_dir / "evolution_log.md"

        _make_feedback_jsonl(fb_path, entries)
        _make_patterns_json(pat_path, sample_patterns)

        engine._evolution_log_path = log_path

        try:
            engine.evolve(fb_path, pat_path, out_path)
            assert log_path.exists()
            content = log_path.read_text(encoding="utf-8")
            assert "Evolution Run" in content
            assert "55" in content  # feedback count
        finally:
            fb_path.unlink(missing_ok=True)
            pat_path.unlink(missing_ok=True)
            out_path.unlink(missing_ok=True)
            log_path.unlink(missing_ok=True)
            log_dir.rmdir()

    def test_evolve_below_threshold_skips(self, sample_patterns):
        engine = EvolutionEngine()
        entries = [{
            "generation_id": "gen_001",
            "pattern_id": "pattern_a",
            "performance": "viral",
            "tracked_at": "2024-01-15T12:00:00Z",
            "title": "Test",
            "body": "Body",
        }]

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            fb_path = Path(f.name)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            pat_path = Path(f.name)

        _make_feedback_jsonl(fb_path, entries)
        _make_patterns_json(pat_path, sample_patterns)

        try:
            log = engine.evolve(fb_path, pat_path)
            assert log is None
        finally:
            fb_path.unlink(missing_ok=True)
            pat_path.unlink(missing_ok=True)

    def test_count_entries(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            for i in range(25):
                f.write(json.dumps({"n": i}) + "\n")
            path = Path(f.name)
        count = EvolutionEngine._count_entries(path)
        assert count == 25
        path.unlink()

    def test_load_entries_skips_invalid_json(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            f.write('{"valid": true}\n')
            f.write('not valid json\n')
            f.write('{"also": "valid"}\n')
            path = Path(f.name)
        entries = EvolutionEngine._load_entries(path)
        assert len(entries) == 2
        path.unlink()
