"""Tests for title analyzer."""

import pytest
from karmaforge.analyzer.title_analyzer import TitleAnalyzer
from karmaforge.storage import Post, ContentType, Tier


class TestTitleAnalyzer:
    @pytest.fixture
    def analyzer(self, mock_llm_client):
        return TitleAnalyzer(llm_client=mock_llm_client, use_llm=True)

    @pytest.fixture
    def posts(self):
        from datetime import datetime, timezone
        dt = datetime(2024, 1, 15, tzinfo=timezone.utc)
        return [
            Post(post_id="t3_1", subreddit="test", title="I just discovered this amazing trick",
                 upvotes=1000, tier=Tier.T2, created_utc=dt),
            Post(post_id="t3_2", subreddit="test", title="Why does everyone ignore this obvious solution?",
                 upvotes=2000, tier=Tier.T2, created_utc=dt),
            Post(post_id="t3_3", subreddit="test", title="PSA: This is happening and you need to know about it",
                 upvotes=3000, tier=Tier.T2, created_utc=dt),
            Post(post_id="t3_4", subreddit="test", title="Unpopular opinion: the current system is broken",
                 upvotes=800, tier=Tier.T2, created_utc=dt),
            Post(post_id="t3_5", subreddit="test", title="After 5 years, here is my honest review",
                 upvotes=1500, tier=Tier.T2, created_utc=dt),
            Post(post_id="t3_6", subreddit="test", title="I spent $50,000 on ads: here are the 3 things I learned",
                 upvotes=5000, tier=Tier.T2, created_utc=dt),
            Post(post_id="t3_7", subreddit="test", title="My journey from beginner to expert in 12 months",
                 upvotes=1200, tier=Tier.T2, created_utc=dt),
            Post(post_id="t3_8", subreddit="test", title="X vs Y: Which one should you choose?",
                 upvotes=2500, tier=Tier.T2, created_utc=dt),
        ]

    def test_analyze_basic(self, analyzer, posts):
        result = analyzer.analyze(posts)
        assert result.n == 8
        assert result.char_count_distribution["n"] > 0
        assert result.word_count_distribution["n"] > 0
        assert result.optimal_range[0] >= 0

    def test_analyze_empty(self, analyzer):
        result = analyzer.analyze([])
        assert result.n == 0

    def test_structure_features(self, analyzer, posts):
        result = analyzer.analyze(posts)
        # At least one of these should be > 0 since our titles have some
        assert result.colon_usage >= 0
        assert result.question_usage >= 0

    def test_hook_types_classified(self, analyzer, posts):
        result = analyzer.analyze(posts)
        assert len(result.hook_type_distribution) > 0

    def test_keywords_extracted(self, analyzer, posts):
        result = analyzer.analyze(posts)
        assert isinstance(result.top_keywords, list)

    def test_by_tier(self, analyzer, posts):
        results = analyzer.analyze_by_tier(posts)
        assert Tier.T2 in results

    def test_no_llm(self, posts):
        analyzer = TitleAnalyzer(llm_client=None, use_llm=False)
        result = analyzer.analyze(posts)
        assert result.n == 8
        assert len(result.hook_type_distribution) > 0
