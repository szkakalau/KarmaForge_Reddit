"""Tests for analysis utility functions."""

from karmaforge.analyzer.analysis_utils import (
    compute_distribution,
    correlation_test,
    find_optimal_range,
    text_length_metrics,
    readability_scores,
    keyword_extraction,
    remove_outliers_iqr,
    bootstrap_confidence_interval,
    cohens_d,
)


class TestComputeDistribution:
    def test_basic(self):
        result = compute_distribution([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], bins=5)
        assert "bins" in result
        assert "counts" in result
        assert "percentiles" in result
        assert result["n"] == 10
        assert result["percentiles"]["p50"] > 0

    def test_empty(self):
        result = compute_distribution([], bins=5)
        assert result["n"] == 0

    def test_with_nan(self):
        result = compute_distribution([1, 2, float("nan"), 4, 5], bins=3)
        assert result["n"] == 4  # NaN removed


class TestCorrelationTest:
    def test_positive(self):
        result = correlation_test([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        assert result["pearson_r"] > 0.9
        assert result["n"] == 10

    def test_small_sample(self):
        result = correlation_test([1, 2], [3, 4])
        assert result["n"] == 2


class TestFindOptimalRange:
    def test_basic(self):
        values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        upvotes = [5, 10, 50, 100, 200, 100, 50, 10, 5, 1]
        low, high = find_optimal_range(values, upvotes, window_pct=0.3)
        assert low < high


class TestTextLengthMetrics:
    def test_basic(self):
        result = text_length_metrics("Hello world. This is a test.")
        assert result["char_count"] > 0
        assert result["word_count"] == 6
        assert result["sentence_count"] == 2

    def test_empty(self):
        result = text_length_metrics("")
        assert result["word_count"] == 0


class TestReadability:
    def test_basic(self):
        result = readability_scores("The cat sat on the mat. It was a nice day.")
        assert isinstance(result["flesch_kincaid_grade"], (int, float))

    def test_empty(self):
        result = readability_scores("")
        assert result["flesch_kincaid_grade"] == 0


class TestKeywordExtraction:
    def test_basic(self):
        texts = ["hello world test", "hello again world", "test post title"]
        result = keyword_extraction(texts, top_n=5, min_freq=1)
        assert len(result) > 0
        assert any(kw["word"] == "hello" for kw in result)


class TestRemoveOutliers:
    def test_basic(self):
        result = remove_outliers_iqr([1, 2, 3, 4, 5, 100], multiplier=1.5)
        assert 100 not in result


class TestBootstrapCI:
    def test_basic(self):
        import numpy as np
        lower, mean, upper = bootstrap_confidence_interval(
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            np.mean, n_bootstrap=500,
        )
        assert lower <= mean <= upper


class TestCohensD:
    def test_large_effect(self):
        d = cohens_d([10, 11, 12, 13, 14], [1, 2, 3, 4, 5])
        assert d > 2.0

    def test_no_effect(self):
        d = cohens_d([5, 5, 5, 5, 5], [5, 5, 5, 5, 5])
        assert d == 0.0
