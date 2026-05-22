"""Temporal backtesting — train on earlier period, test on later period.

Splits data by time: extracts patterns from training period (e.g. 2023),
then measures recall and precision on test period (e.g. 2024).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np

from ..storage import Post, Tier
from ..analyzer.title_analyzer import TitleAnalyzer
from ..analyzer.content_analyzer import ContentAnalyzer
from ..analyzer.meta_analyzer import MetaAnalyzer
from ..analyzer.visual_analyzer import VisualAnalyzer
from ..analyzer.pattern_extractor import PatternExtractor, ViralPattern

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    train_period: tuple = ("", "")
    test_period: tuple = ("", "")
    train_post_count: int = 0
    test_post_count: int = 0
    patterns_extracted: int = 0
    recall: float = 0.0
    precision: float = 0.0
    f1_score: float = 0.0
    baseline_precision: float = 0.0
    confusion_matrix: dict = field(default_factory=lambda: {"tp": 0, "fp": 0, "tn": 0, "fn": 0})
    per_tier_results: dict = field(default_factory=dict)
    pass_recall: bool = False
    pass_precision: bool = False

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            d[k] = list(v) if isinstance(v, tuple) else v
        return d


class Backtester:
    def __init__(
        self,
        pattern_extractor: PatternExtractor,
        train_start: str = "2023-01-01",
        train_end: str = "2023-12-31",
        test_start: str = "2024-01-01",
        test_end: str = "2024-12-31",
        viral_percentile: float = 90.0,
        match_threshold: float = 0.6,
        min_recall: float = 0.60,
        min_precision: float = 0.40,
    ) -> None:
        self.pattern_extractor = pattern_extractor
        self.train_start = datetime.fromisoformat(train_start)
        self.train_end = datetime.fromisoformat(train_end)
        self.test_start = datetime.fromisoformat(test_start)
        self.test_end = datetime.fromisoformat(test_end)
        self.viral_percentile = viral_percentile
        self.match_threshold = match_threshold
        self.min_recall = min_recall
        self.min_precision = min_precision

    def run(self, all_posts: list[Post]) -> BacktestResult:
        train_posts, test_posts = self._split_temporal(all_posts)
        if len(train_posts) < 30 or len(test_posts) < 30:
            logger.error("Insufficient posts for backtesting: train=%d test=%d", len(train_posts), len(test_posts))
            return BacktestResult(
                train_period=(self.train_start.isoformat()[:10], self.train_end.isoformat()[:10]),
                test_period=(self.test_start.isoformat()[:10], self.test_end.isoformat()[:10]),
                train_post_count=len(train_posts),
                test_post_count=len(test_posts),
            )

        logger.info("Backtesting: %d train posts, %d test posts", len(train_posts), len(test_posts))

        title_results = TitleAnalyzer(use_llm=False).analyze(train_posts)
        content_results = ContentAnalyzer(use_llm=False).analyze(train_posts)
        meta_results = MetaAnalyzer().analyze(train_posts)
        visual_results = VisualAnalyzer().analyze(train_posts)

        patterns, _ = self.pattern_extractor.extract(
            train_posts, title_results, content_results, meta_results, visual_results
        )

        if not patterns:
            logger.warning("No patterns extracted from training set")
            return BacktestResult(
                train_period=(self.train_start.isoformat()[:10], self.train_end.isoformat()[:10]),
                test_period=(self.test_start.isoformat()[:10], self.test_end.isoformat()[:10]),
                train_post_count=len(train_posts),
                test_post_count=len(test_posts),
                patterns_extracted=0,
            )

        predictions, actuals = self._match_and_evaluate(test_posts, patterns)
        metrics = self._compute_metrics(predictions, actuals)

        viral_rate = sum(actuals) / max(len(actuals), 1)
        baseline_precision = viral_rate

        per_tier = {}
        for tier in [Tier.T1, Tier.T2, Tier.T3]:
            tier_posts = [p for p in test_posts if p.tier == tier]
            if tier_posts and len(tier_posts) >= 20:
                tier_preds, tier_actuals = self._match_and_evaluate(tier_posts, patterns)
                tier_metrics = self._compute_metrics(tier_preds, tier_actuals)
                per_tier[tier.value] = tier_metrics

        f1 = 2 * metrics["precision"] * metrics["recall"] / max(metrics["precision"] + metrics["recall"], 0.001)

        result = BacktestResult(
            train_period=(self.train_start.isoformat()[:10], self.train_end.isoformat()[:10]),
            test_period=(self.test_start.isoformat()[:10], self.test_end.isoformat()[:10]),
            train_post_count=len(train_posts),
            test_post_count=len(test_posts),
            patterns_extracted=len(patterns),
            recall=round(metrics["recall"], 4),
            precision=round(metrics["precision"], 4),
            f1_score=round(f1, 4),
            baseline_precision=round(baseline_precision, 4),
            confusion_matrix=metrics["confusion"],
            per_tier_results=per_tier,
            pass_recall=metrics["recall"] >= self.min_recall,
            pass_precision=metrics["precision"] >= self.min_precision,
        )

        logger.info("Backtest: recall=%.3f precision=%.3f f1=%.3f", result.recall, result.precision, result.f1_score)
        return result

    def _split_temporal(self, posts: list[Post]) -> tuple[list[Post], list[Post]]:
        train, test = [], []
        for p in posts:
            if not p.created_utc:
                continue
            if self.train_start <= p.created_utc <= self.train_end:
                train.append(p)
            elif self.test_start <= p.created_utc <= self.test_end:
                test.append(p)
        return train, test

    def _match_and_evaluate(
        self, posts: list[Post], patterns: list[ViralPattern]
    ) -> tuple[list[bool], list[bool]]:
        upvotes = [p.upvotes for p in posts]
        threshold = np.percentile(upvotes, self.viral_percentile) if upvotes else 0

        predictions = []
        actuals = []

        for p in posts:
            is_viral = p.upvotes >= threshold
            actuals.append(is_viral)

            matched = False
            for pattern in patterns:
                if self._post_matches_pattern(p, pattern):
                    matched = True
                    break
            predictions.append(matched)

        return predictions, actuals

    def _post_matches_pattern(self, post: Post, pattern: ViralPattern) -> bool:
        score = 0.0

        if pattern.title_template:
            sim = self._title_similarity(post.title, pattern.title_template)
            score += sim * 0.5

        if pattern.recommended_metrics:
            metrics = pattern.recommended_metrics
            title_words = len(post.title.split())
            if "title_words" in metrics:
                low, high = metrics["title_words"]
                if low <= title_words <= high:
                    score += 0.25
            body_words = len(post.body.split()) if post.body else 0
            if "body_words" in metrics:
                low, high = metrics["body_words"]
                if low <= body_words <= high:
                    score += 0.25

        return score >= self.match_threshold

    @staticmethod
    def _title_similarity(title: str, template: str) -> float:
        title_words = set(title.lower().split())
        template_words = set(template.lower().replace("{var}", "").split())

        if not template_words:
            return 0.0

        intersection = title_words & template_words
        union = title_words | template_words
        return len(intersection) / max(len(union), 1)

    @staticmethod
    def _compute_metrics(predictions: list[bool], actuals: list[bool]) -> dict:
        tp = sum(1 for p, a in zip(predictions, actuals) if p and a)
        fp = sum(1 for p, a in zip(predictions, actuals) if p and not a)
        tn = sum(1 for p, a in zip(predictions, actuals) if not p and not a)
        fn = sum(1 for p, a in zip(predictions, actuals) if not p and a)

        recall = tp / max(tp + fn, 1)
        precision = tp / max(tp + fp, 1)

        return {
            "recall": recall,
            "precision": precision,
            "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        }
