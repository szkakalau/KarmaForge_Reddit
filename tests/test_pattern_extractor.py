"""Tests for pattern extractor."""

import pytest
from karmaforge.analyzer.pattern_extractor import PatternExtractor, ViralPattern, AntiPattern
from karmaforge.analyzer.title_analyzer import TitleAnalyzer
from karmaforge.analyzer.content_analyzer import ContentAnalyzer
from karmaforge.analyzer.meta_analyzer import MetaAnalyzer
from karmaforge.analyzer.visual_analyzer import VisualAnalyzer


class TestPatternExtractor:
    @pytest.fixture
    def extractor(self, mock_llm_client):
        return PatternExtractor(
            llm_client=mock_llm_client,
            min_cluster_size=2,
            max_patterns=4,
            viral_percentile=70,
        )

    def test_extract_basic(self, extractor, sample_posts):
        title_results = TitleAnalyzer(use_llm=False).analyze(sample_posts)
        content_results = ContentAnalyzer(use_llm=False).analyze(sample_posts)
        meta_results = MetaAnalyzer().analyze(sample_posts)
        visual_results = VisualAnalyzer().analyze(sample_posts)

        patterns, anti_patterns = extractor.extract(
            sample_posts, title_results, content_results, meta_results, visual_results
        )

        assert isinstance(patterns, list)
        assert isinstance(anti_patterns, list)

    def test_extract_too_few_posts(self, extractor, sample_posts):
        few = sample_posts[:5]
        title_results = TitleAnalyzer(use_llm=False).analyze(few)
        content_results = ContentAnalyzer(use_llm=False).analyze(few)
        meta_results = MetaAnalyzer().analyze(few)
        visual_results = VisualAnalyzer().analyze(few)

        patterns, anti_patterns = extractor.extract(
            few, title_results, content_results, meta_results, visual_results
        )

        assert patterns == []
        assert anti_patterns == []

    def test_viral_pattern_to_dict(self):
        p = ViralPattern(
            pattern_id="p1", name="Test", description="A test pattern",
            historical_viral_rate=0.5, confidence_interval=(0.4, 0.6),
            avg_upvotes=100, p_value=0.01,
        )
        d = p.to_dict()
        assert d["pattern_id"] == "p1"
        assert d["confidence_interval"] == [0.4, 0.6]

    def test_viral_pattern_from_dict(self):
        d = {
            "pattern_id": "p1", "name": "Test", "description": "Desc",
            "historical_viral_rate": 0.5, "confidence_interval": [0.4, 0.6],
            "avg_upvotes": 100, "p_value": 0.01, "sample_size": 50,
        }
        p = ViralPattern.from_dict(d)
        assert p.pattern_id == "p1"
        assert p.confidence_interval == (0.4, 0.6)

    def test_anti_pattern(self):
        ap = AntiPattern(
            pattern_id="ap1", name="Bad Pattern",
            description="Always fails", failure_rate=0.9,
            why_it_fails="Too verbose", sample_size=20,
        )
        d = ap.to_dict()
        ap2 = AntiPattern.from_dict(d)
        assert ap2.pattern_id == "ap1"
        assert ap2.failure_rate == 0.9

    def test_save_and_load(self, extractor, sample_posts, tmp_path):
        title_results = TitleAnalyzer(use_llm=False).analyze(sample_posts)
        content_results = ContentAnalyzer(use_llm=False).analyze(sample_posts)
        meta_results = MetaAnalyzer().analyze(sample_posts)
        visual_results = VisualAnalyzer().analyze(sample_posts)

        patterns, anti_patterns = extractor.extract(
            sample_posts, title_results, content_results, meta_results, visual_results
        )

        extractor.save_patterns(patterns, anti_patterns, tmp_path)
        assert (tmp_path / "patterns.json").exists()
        assert (tmp_path / "anti_patterns.json").exists()

        loaded_p, loaded_ap = PatternExtractor.load_patterns(tmp_path)
        assert len(loaded_p) == len(patterns)
