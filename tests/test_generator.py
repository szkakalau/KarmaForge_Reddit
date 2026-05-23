"""Tests for generator module — SubredditMatcher, PatternSelector, TitleGenerator,
BodyGenerator, SelfChecker, MetadataSuggester, GeneratorOrchestrator."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from karmaforge.generator import CandidateTitle, GenerationResult, SelfCheckReport
from karmaforge.generator.subreddit_matcher import SubredditMatcher
from karmaforge.generator.pattern_selector import PatternSelector
from karmaforge.generator.title_generator import TitleGenerator
from karmaforge.generator.body_generator import BodyGenerator
from karmaforge.generator.self_checker import SelfChecker
from karmaforge.generator.metadata_suggester import MetadataSuggester
from karmaforge.generator.orchestrator import GeneratorOrchestrator


# ── Helpers ──────────────────────────────────────────────────────

def _make_patterns_json(path: Path) -> None:
    patterns = [
        {
            "pattern_id": "pattern_01",
            "name": "How-to Tutorial",
            "hook_type": "tutorial_howto",
            "description": "Step-by-step guides that teach a skill",
            "title_template": "How to|do|the",
            "body_structure_template": "Intro\n\nSteps\n\nConclusion",
            "narrative_mode": "tutorial_howto",
            "applicable_subreddits": ["programming", "productivity", "selfhosted"],
            "historical_viral_rate": 0.45,
            "sample_size": 120,
            "recommended_metrics": {
                "title_words": [6, 18],
                "body_words": [100, 600],
            },
            "tier_effectiveness": {"t1": 0.3, "t2": 0.5, "t3": 0.7},
        },
        {
            "pattern_id": "pattern_02",
            "name": "Personal Story",
            "hook_type": "story_opener",
            "description": "Personal experience narratives",
            "title_template": "My journey|with|something",
            "body_structure_template": "Setup\n\nConflict\n\nResolution\n\nLesson",
            "narrative_mode": "story_personal",
            "applicable_subreddits": ["productivity", "Fitness", "getdisciplined", "Entrepreneur"],
            "historical_viral_rate": 0.62,
            "sample_size": 200,
            "recommended_metrics": {
                "title_words": [8, 22],
                "body_words": [150, 800],
            },
            "tier_effectiveness": {"t1": 0.5, "t2": 0.7, "t3": 0.4},
        },
        {
            "pattern_id": "pattern_03",
            "name": "Resource Share",
            "hook_type": "resource_share",
            "description": "Share a free tool or resource",
            "title_template": "I built|a tool|for",
            "body_structure_template": "Problem\n\nSolution\n\nLink/Details\n\nFeedback ask",
            "narrative_mode": "resource_showcase",
            "applicable_subreddits": ["programming", "SideProject", "indiehackers", "selfhosted"],
            "historical_viral_rate": 0.38,
            "sample_size": 85,
            "recommended_metrics": {
                "title_words": [5, 20],
                "body_words": [80, 500],
            },
            "tier_effectiveness": {"t1": 0.3, "t2": 0.4, "t3": 0.8},
        },
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(patterns, f, ensure_ascii=False, indent=2)


def _make_anti_patterns_json(path: Path) -> None:
    anti_patterns = [
        {
            "pattern_id": "anti_very_short_title",
            "name": "Very Short Title",
            "why_it_fails": "Titles under 5 words lack hook space",
        },
        {
            "pattern_id": "anti_very_long_title",
            "name": "Very Long Title",
            "why_it_fails": "Titles over 30 words dilute hook impact",
        },
        {
            "pattern_id": "anti_generic_low_engagement",
            "name": "Generic Low Engagement",
            "why_it_fails": "Generic phrasing fails to engage readers",
        },
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(anti_patterns, f, ensure_ascii=False, indent=2)


@pytest.fixture
def temp_patterns_file():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    _make_patterns_json(path)
    yield path
    path.unlink(missing_ok=True)


@pytest.fixture
def temp_anti_patterns_file():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    _make_anti_patterns_json(path)
    yield path
    path.unlink(missing_ok=True)


# ── SubredditMatcher ─────────────────────────────────────────────

class TestSubredditMatcher:
    def test_direct_subreddit_mention(self):
        matcher = SubredditMatcher()
        result = matcher.match("r/productivity tips for beginners")
        assert result[0][0] == "productivity"
        assert result[0][1] == 1.0

    def test_topic_hint_matching(self):
        matcher = SubredditMatcher()
        result = matcher.match("I built a SaaS tool")
        sub_names = [s for s, _ in result]
        assert "SaaS" in sub_names or "startups" in sub_names

    def test_keyword_matching(self):
        matcher = SubredditMatcher()
        result = matcher.match("automation script for daily tasks")
        assert len(result) > 0
        assert all(0 <= score <= 1.0 for _, score in result)

    def test_empty_input_fallback(self):
        matcher = SubredditMatcher()
        result = matcher.match("xyzxyz nothing relevant here")
        assert len(result) > 0  # fallback subs always returned

    def test_limit_parameter(self):
        matcher = SubredditMatcher()
        result = matcher.match("programming", limit=2)
        assert len(result) <= 2

    def test_tokenize_bigrams(self):
        tokens = SubredditMatcher._tokenize("machine learning automation")
        assert "machinelearning" in tokens


# ── PatternSelector ──────────────────────────────────────────────

class TestPatternSelector:
    def test_load_patterns(self, temp_patterns_file):
        selector = PatternSelector(temp_patterns_file)
        assert len(selector._patterns) == 3

    def test_select_by_subreddit(self, temp_patterns_file):
        selector = PatternSelector(temp_patterns_file)
        result = selector.select("programming", n=3)
        assert len(result) >= 1
        assert all("pattern_id" in p for p in result)

    def test_select_deduplicates_hooks(self, temp_patterns_file):
        selector = PatternSelector(temp_patterns_file)
        result = selector.select("programming", n=3)
        hooks = [p["hook_type"] for p in result]
        assert len(hooks) == len(set(hooks))  # no duplicate hook types

    def test_select_with_topic_keywords(self, temp_patterns_file):
        selector = PatternSelector(temp_patterns_file)
        result = selector.select(
            "productivity", topic_keywords=["guide", "how", "tutorial"], n=3
        )
        assert len(result) >= 1

    def test_no_matching_subreddit_fallback(self, temp_patterns_file):
        selector = PatternSelector(temp_patterns_file)
        result = selector.select("nonexistent_sub", n=2)
        assert len(result) <= 2  # generic fallback

    def test_missing_file_graceful(self):
        selector = PatternSelector("/nonexistent/patterns.json")
        assert selector._patterns == []

    def test_score_pattern_applicable_sub(self, temp_patterns_file):
        selector = PatternSelector(temp_patterns_file)
        pattern = selector._patterns[0]  # pattern_01
        score = selector._score_pattern(pattern, "programming", ["how", "guide"])
        assert score > 30  # applicable sub + decent viral rate

    def test_inactive_patterns_skipped(self, tmp_path):
        """Patterns with status='inactive' are skipped when active ones available."""
        patterns_path = tmp_path / "patterns.json"
        patterns = [
            {
                "pattern_id": "active_01",
                "name": "Active Pattern",
                "hook_type": "tutorial_howto",
                "applicable_subreddits": ["programming"],
                "historical_viral_rate": 0.5,
                "sample_size": 100,
                "tier_effectiveness": {},
            },
            {
                "pattern_id": "inactive_01",
                "name": "Inactive Pattern",
                "hook_type": "story_opener",
                "status": "inactive",
                "applicable_subreddits": ["programming"],
                "historical_viral_rate": 0.7,
                "sample_size": 200,
                "tier_effectiveness": {},
            },
        ]
        patterns_path.write_text(json.dumps(patterns), encoding="utf-8")

        selector = PatternSelector(patterns_path)
        result = selector.select("programming", n=3)

        assert len(result) == 1
        assert result[0]["pattern_id"] == "active_01"

    def test_success_rate_blends_with_historical(self, tmp_path):
        """success_rate from evolution blends into the scoring."""
        patterns_path = tmp_path / "patterns.json"
        patterns = [
            {
                "pattern_id": "p_low_success",
                "name": "Low Success Pattern",
                "hook_type": "tutorial_howto",
                "applicable_subreddits": ["programming"],
                "historical_viral_rate": 0.8,
                "success_rate": 0.1,
                "sample_size": 100,
                "tier_effectiveness": {},
            },
            {
                "pattern_id": "p_high_success",
                "name": "High Success Pattern",
                "hook_type": "story_opener",
                "applicable_subreddits": ["programming"],
                "historical_viral_rate": 0.5,
                "success_rate": 0.9,
                "sample_size": 100,
                "tier_effectiveness": {},
            },
        ]
        patterns_path.write_text(json.dumps(patterns), encoding="utf-8")

        selector = PatternSelector(patterns_path)
        result = selector.select("programming", n=3)

        # p_high_success (0.7*0.5 + 0.3*0.9 = 0.62) > p_low_success (0.7*0.8 + 0.3*0.1 = 0.59)
        # So p_high_success should rank first despite lower historical rate
        assert result[0]["pattern_id"] == "p_high_success"


# ── TitleGenerator ───────────────────────────────────────────────

class TestTitleGenerator:
    def test_heuristic_generates_all_hook_types(self):
        gen = TitleGenerator()
        patterns = [
            {"pattern_id": "p1", "hook_type": "tutorial_howto"},
            {"pattern_id": "p2", "hook_type": "story_opener"},
            {"pattern_id": "p3", "hook_type": "controversial_opinion"},
        ]
        results = gen.generate("test topic", patterns, "productivity")
        assert len(results) == 3

    def test_heuristic_uses_template_when_available(self):
        gen = TitleGenerator()
        pattern = {
            "pattern_id": "p1",
            "hook_type": "tutorial_howto",
            "title_template": "How to|master|Python",
        }
        results = gen.generate("coding", [pattern], "programming")
        assert "How To" in results[0].title

    def test_heuristic_unknown_hook_fallback(self):
        gen = TitleGenerator()
        pattern = {"pattern_id": "p1", "hook_type": "unknown_hook_type"}
        results = gen.generate("something", [pattern], "test")
        assert len(results) == 1
        assert "my experience" in results[0].title.lower()

    def test_scores_sorted_descending(self):
        gen = TitleGenerator()
        patterns = [
            {"pattern_id": "p1", "hook_type": "tutorial_howto", "recommended_metrics": {"title_words": [6, 18]}},
            {"pattern_id": "p2", "hook_type": "story_opener", "recommended_metrics": {"title_words": [8, 22]}},
        ]
        results = gen.generate("test topic", patterns, "productivity")
        assert results[0].score >= results[-1].score

    def test_clickbait_penalty(self):
        gen = TitleGenerator()
        score = gen._score_title(
            "You won't believe this one trick that changed everything!!!",
            {"hook_type": "tutorial_howto"},
            "t2",
        )
        # Base 50 + 30 (word count in range) - 20 (2 clickbait markers) - 5 (!!) + 10 (caps) = 65
        assert score < 70

    def test_good_title_scores_high(self):
        gen = TitleGenerator()
        score = gen._score_title(
            "How to automate your daily workflow with Python",
            {"hook_type": "tutorial_howto", "recommended_metrics": {"title_words": [6, 18]}},
            "t2",
        )
        assert score >= 70

    def test_too_short_title_penalty(self):
        gen = TitleGenerator()
        score = gen._score_title("Hi", {"hook_type": "tutorial_howto"}, "t2")
        # Base 50 + 10 (first letter caps) - 20 (words < 3) = 40
        assert score <= 40

    def test_llm_fallback_on_error(self, mock_llm_client):
        mock_llm_client.complete.side_effect = RuntimeError("LLM down")
        gen = TitleGenerator(mock_llm_client)
        pattern = {"pattern_id": "p1", "hook_type": "story_opener"}
        results = gen.generate("test", [pattern], "productivity")
        assert len(results) == 1  # falls back to heuristic
        assert "experience" in results[0].title.lower()

    def test_llm_generate_success(self, mock_llm_client):
        mock_llm_client.complete.return_value = "How to master Python in 30 days"
        gen = TitleGenerator(mock_llm_client)
        pattern = {"pattern_id": "p1", "hook_type": "tutorial_howto"}
        results = gen.generate("Python", [pattern], "programming")
        assert results[0].title == "How to master Python in 30 days"
        assert results[0].score > 0


# ── BodyGenerator ────────────────────────────────────────────────

class TestBodyGenerator:
    def test_heuristic_tutorial_howto(self):
        gen = BodyGenerator()
        pattern = {"hook_type": "tutorial_howto", "narrative_mode": "tutorial_howto"}
        body, metrics = gen.generate("Python testing", pattern, "testing", "programming")
        assert "step-by-step" in body.lower()
        assert "1." in body
        assert metrics["word_count"] > 0
        assert metrics["paragraphs"] >= 2

    def test_heuristic_story_personal(self):
        gen = BodyGenerator()
        pattern = {"hook_type": "story_opener", "narrative_mode": "story_personal"}
        body, metrics = gen.generate("weight loss", pattern, "fitness journey", "Fitness")
        assert "experience" in body.lower() or "journey" in body.lower()

    def test_heuristic_resource_share(self):
        gen = BodyGenerator()
        pattern = {"hook_type": "resource_share", "narrative_mode": "resource_showcase"}
        body, metrics = gen.generate("CLI tool", pattern, "a new CLI tool", "programming")
        assert "I built" in body or "built a" in body

    def test_heuristic_curious_question(self):
        gen = BodyGenerator()
        pattern = {"hook_type": "curious_question", "narrative_mode": "opinion_argument"}
        body, metrics = gen.generate("AI ethics", pattern, "AI ethics", "philosophy")
        assert "thinking about" in body.lower() or "perspective" in body.lower()

    def test_no_body_pattern(self):
        gen = BodyGenerator()
        pattern = {
            "hook_type": "resource_share",
            "recommended_metrics": {"body_words": [0, 0]},
        }
        body, metrics = gen.generate("image post", pattern, "cool pic", "pics")
        assert body != ""  # no_body patterns now fall back to tier defaults

    def test_engagement_hook_detection(self):
        gen = BodyGenerator()
        assert gen._check_engagement("Here is my story. What do you think?")
        assert gen._check_engagement("My project. Would love feedback")
        assert not gen._check_engagement("Just a statement. No questions here.")

    def test_generic_fallback_body(self):
        gen = BodyGenerator()
        pattern = {"hook_type": "unknown_type", "narrative_mode": "unknown"}
        body, metrics = gen.generate("some topic", pattern, "some topic", "test")
        assert len(body) > 0
        assert metrics["word_count"] > 0

    def test_llm_fallback_on_error(self, mock_llm_client):
        mock_llm_client.complete.side_effect = RuntimeError("LLM down")
        gen = BodyGenerator(mock_llm_client)
        pattern = {"hook_type": "tutorial_howto", "narrative_mode": "tutorial_howto"}
        body, metrics = gen.generate("test", pattern, "testing", "programming")
        assert "step-by-step" in body.lower()

    def test_llm_generate_success(self, mock_llm_client):
        mock_llm_client.complete.return_value = "This is a detailed tutorial body.\n\nStep 1: Start here.\n\nStep 2: Continue."
        gen = BodyGenerator(mock_llm_client)
        pattern = {
            "hook_type": "tutorial_howto",
            "narrative_mode": "tutorial_howto",
            "recommended_metrics": {"body_words": [50, 600]},
        }
        body, metrics = gen.generate("test", pattern, "testing", "programming")
        assert "detailed tutorial" in body


# ── SelfChecker ──────────────────────────────────────────────────

class TestSelfChecker:
    def test_all_pass_for_good_content(self, temp_anti_patterns_file):
        checker = SelfChecker(temp_anti_patterns_file)
        pattern = {
            "hook_type": "tutorial_howto",
            "recommended_metrics": {"title_words": [6, 18], "body_words": [50, 600]},
        }
        report = checker.check(
            "How to write better Python code today",
            "Here is a detailed guide about writing better Python code. "
            + "I have been programming for years and learned many lessons. "
            + "Let me share the most important ones with you today. " * 5,
            pattern,
            "programming",
        )
        assert report.passed

    def test_title_too_short_fails(self, temp_anti_patterns_file):
        checker = SelfChecker(temp_anti_patterns_file)
        pattern = {
            "hook_type": "tutorial_howto",
            "recommended_metrics": {"title_words": [10, 20], "body_words": [50, 600]},
        }
        report = checker.check("Hi", "Some body text that is long enough for the check", pattern, "programming")
        assert not report.passed or report.dimensions["title_length"]["status"] == "fail"

    def test_body_too_short_warns(self, temp_anti_patterns_file):
        checker = SelfChecker(temp_anti_patterns_file)
        pattern = {
            "hook_type": "tutorial_howto",
            "recommended_metrics": {"title_words": [6, 18], "body_words": [200, 600]},
        }
        report = checker.check(
            "How to write better code",
            "Short body.",
            pattern,
            "programming",
        )
        dim = report.dimensions.get("body_length", {})
        assert dim.get("status") in ("warn", "fail")

    def test_anti_pattern_detected(self, temp_anti_patterns_file):
        checker = SelfChecker(temp_anti_patterns_file)
        pattern = {
            "hook_type": "tutorial_howto",
            "recommended_metrics": {"title_words": [6, 18], "body_words": [50, 600]},
        }
        report = checker.check(
            "Hi",  # triggers anti_very_short_title
            "just wanted to say thanks for reading. anyone else agree?",
            pattern,
            "programming",
        )
        triggered = report.dimensions.get("anti_patterns", {}).get("triggered", [])
        assert len(triggered) > 0

    def test_no_body_pattern_passes(self, temp_anti_patterns_file):
        checker = SelfChecker(temp_anti_patterns_file)
        pattern = {
            "hook_type": "resource_share",
            "recommended_metrics": {"title_words": [5, 20], "body_words": [0, 0]},
        }
        report = checker.check(
            "Check out this cool image",
            "",
            pattern,
            "pics",
        )
        assert report.dimensions["body_length"]["status"] == "ok"

    def test_readability_check(self, temp_anti_patterns_file):
        checker = SelfChecker(temp_anti_patterns_file)
        pattern = {
            "hook_type": "story_opener",
            "recommended_metrics": {"title_words": [8, 22], "body_words": [50, 600]},
        }
        report = checker.check(
            "My journey learning to code over the past year",
            "I started coding about a year ago and it has been quite a ride. "
            + "There were many ups and downs along the way that I want to share. " * 10,
            pattern,
            "programming",
        )
        assert "readability" in report.dimensions

    def test_hook_presence_check(self, temp_anti_patterns_file):
        checker = SelfChecker(temp_anti_patterns_file)
        pattern = {
            "hook_type": "tutorial_howto",
            "recommended_metrics": {"title_words": [6, 18], "body_words": [50, 600]},
        }
        report = checker.check(
            "Something completely unrelated to any tutorial",
            "This body has no how-to signals or guide language at all. " * 5,
            pattern,
            "programming",
        )
        hook_dim = report.dimensions.get("hook_presence", {})
        assert hook_dim.get("score", 100) < 80  # weak hook presence


# ── MetadataSuggester ────────────────────────────────────────────

class TestMetadataSuggester:
    def test_suggest_by_tier(self):
        suggester = MetadataSuggester()
        result = suggester.suggest("productivity", "t2", "automation script")
        assert "recommended_day" in result
        assert "recommended_hour_utc" in result
        assert "recommended_flair" in result
        assert isinstance(result["should_mark_oc"], bool)

    def test_flair_matches_topic(self):
        suggester = MetadataSuggester()
        result = suggester.suggest("programming", "t2", "I built a new tool for automation")
        assert result["recommended_flair"] in ("Resource", "I made this")

    def test_flair_fallback_to_first(self):
        suggester = MetadataSuggester()
        result = suggester.suggest("productivity", "t2", "random topic")
        assert result["recommended_flair"] in ["Technique", "Tool", "Discussion", "Story"]

    def test_oc_marking_for_personal_content(self):
        suggester = MetadataSuggester()
        result = suggester.suggest("programming", "t2", "I built my first web app")
        assert result["should_mark_oc"] is True

    def test_no_oc_for_impersonal_content(self):
        suggester = MetadataSuggester()
        result = suggester.suggest("programming", "t2", "a discussion about Python types")
        assert result["should_mark_oc"] is False

    def test_unknown_subreddit_defaults(self):
        suggester = MetadataSuggester()
        result = suggester.suggest("nonexistent_sub", "t2", "some topic")
        assert result["recommended_flair"] in ("Discussion", "Question")


# ── GeneratorOrchestrator ────────────────────────────────────────

class TestGeneratorOrchestrator:
    def test_generate_titles_pipeline(self, temp_patterns_file):
        orch = GeneratorOrchestrator(
            patterns_path=str(temp_patterns_file),
        )
        result = orch.generate_titles(
            "I built an automation script",
            target_subreddit="programming",
        )
        assert isinstance(result, GenerationResult)
        assert len(result.candidate_titles) > 0
        assert len(result.matched_subreddits) > 0
        assert result.metadata is not None

    def test_generate_titles_without_subreddit(self, temp_patterns_file):
        orch = GeneratorOrchestrator(
            patterns_path=str(temp_patterns_file),
        )
        result = orch.generate_titles("automation script for daily workflow")
        assert len(result.candidate_titles) > 0
        assert len(result.matched_subreddits) > 0

    def test_generate_full_with_body_and_check(self, temp_patterns_file, temp_anti_patterns_file):
        orch = GeneratorOrchestrator(
            patterns_path=str(temp_patterns_file),
            anti_patterns_path=str(temp_anti_patterns_file),
        )
        result = orch.generate_full(
            "I built a Python CLI tool",
            target_subreddit="programming",
        )
        assert result.body is not None
        assert result.self_check is not None
        assert isinstance(result.self_check, SelfCheckReport)

    def test_save_generation(self, temp_patterns_file):
        orch = GeneratorOrchestrator(
            patterns_path=str(temp_patterns_file),
            output_dir=Path(tempfile.mkdtemp()),
        )
        result = orch.generate_titles("test topic", target_subreddit="programming")
        path = orch.save_generation(result)
        assert path.exists()
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["generation_id"] == result.generation_id

    def test_no_patterns_for_subreddit(self, temp_patterns_file):
        orch = GeneratorOrchestrator(
            patterns_path=str(temp_patterns_file),
        )
        result = orch.generate_titles(
            "random stuff",
            target_subreddit="AskReddit",
        )
        # AskReddit is not in any pattern's applicable_subreddits
        # but fallback generic patterns should still work
        assert isinstance(result, GenerationResult)

    def test_llm_mode_generates(self, temp_patterns_file, mock_llm_client):
        mock_llm_client.complete.return_value = "How to build better software"
        orch = GeneratorOrchestrator(
            patterns_path=str(temp_patterns_file),
            llm_client=mock_llm_client,
        )
        result = orch.generate_titles("software development", target_subreddit="programming")
        assert len(result.candidate_titles) > 0
