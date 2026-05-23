"""Temporal backtesting — train on earlier period, test on later period.

Splits data by time: extracts patterns from training period (e.g. 2023),
then measures recall and precision on test period (e.g. 2024).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from ..storage import Post, Tier
from ..analyzer.title_analyzer import TitleAnalyzer
from ..analyzer.content_analyzer import ContentAnalyzer
from ..analyzer.meta_analyzer import MetaAnalyzer
from ..analyzer.visual_analyzer import VisualAnalyzer
from ..analyzer.pattern_extractor import PatternExtractor, ViralPattern
from ..analyzer.analysis_utils import (
    batch_classify_heuristic, batch_classify_llm,
    HOOK_KEYWORDS, HOOK_CATEGORIES, HOOK_DESCRIPTIONS,
)

DEFAULT_SEED = 42

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
        llm_client = None,
    ) -> None:
        self.pattern_extractor = pattern_extractor
        self.train_start = datetime.fromisoformat(train_start).replace(tzinfo=timezone.utc)
        self.train_end = datetime.fromisoformat(train_end).replace(tzinfo=timezone.utc)
        self.test_start = datetime.fromisoformat(test_start).replace(tzinfo=timezone.utc)
        self.test_end = datetime.fromisoformat(test_end).replace(tzinfo=timezone.utc)
        self.viral_percentile = viral_percentile
        self.match_threshold = match_threshold
        self.min_recall = min_recall
        self.min_precision = min_precision
        self.llm = llm_client

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

        use_llm = self.llm is not None
        title_results = TitleAnalyzer(use_llm=use_llm).analyze(train_posts)
        content_results = ContentAnalyzer(use_llm=use_llm).analyze(train_posts)
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
        # Fall back to random stratified split if temporal split is too imbalanced
        if len(train) < 30 or len(test) < 30:
            logger.info("Temporal split insufficient (train=%d, test=%d), using random split", len(train), len(test))
            return self._split_random(posts)
        return train, test

    def _split_random(self, posts: list[Post]) -> tuple[list[Post], list[Post]]:
        from collections import defaultdict
        rng = np.random.default_rng(DEFAULT_SEED)
        by_sub = defaultdict(list)
        for p in posts:
            if p.created_utc:
                by_sub[p.subreddit].append(p)
        train, test = [], []
        for sub, sub_posts in by_sub.items():
            indices = rng.permutation(len(sub_posts))
            split = max(1, len(sub_posts) * 3 // 5)
            train.extend(sub_posts[i] for i in indices[:split])
            test.extend(sub_posts[i] for i in indices[split:])
        return train, test

    def _match_and_evaluate(
        self, posts: list[Post], patterns: list[ViralPattern]
    ) -> tuple[list[bool], list[bool]]:
        upvotes = [p.upvotes for p in posts]
        threshold = np.percentile(upvotes, self.viral_percentile) if upvotes else 0

        titles = [p.title for p in posts]
        if self.llm:
            post_hooks = batch_classify_llm(
                titles, HOOK_CATEGORIES, HOOK_DESCRIPTIONS,
                self.llm, batch_size=20, task_name="title",
            )
        else:
            post_hooks = batch_classify_heuristic(titles, list(HOOK_KEYWORDS.keys()), HOOK_KEYWORDS)
        post_narratives = [_classify_narrative(p.body or "") for p in posts]

        predictions = []
        actuals = []

        for i, p in enumerate(posts):
            is_viral = p.upvotes >= threshold
            actuals.append(is_viral)

            matched = False
            for pattern in patterns:
                if _post_matches_pattern(p, pattern, post_hooks[i], post_narratives[i], self.match_threshold):
                    matched = True
                    break
            predictions.append(matched)

        return predictions, actuals

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


_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "and", "but", "or",
    "nor", "not", "so", "yet", "both", "either", "neither", "each", "every",
    "all", "any", "few", "more", "most", "other", "some", "such", "no",
    "only", "own", "same", "than", "too", "very", "just", "about", "also",
    "if", "then", "else", "this", "that", "these", "those", "it", "its",
    "i", "me", "my", "we", "our", "you", "your", "he", "she", "they",
    "him", "his", "her", "them", "what", "which", "who", "whom", "when",
    "where", "why", "how", "am", "don", "didn", "doesn", "isn", "aren",
    "wasn", "weren", "haven", "hasn", "hadn", "won", "wouldn", "can", "couldn",
    "{var}", "up", "out", "get", "one", "like", "really", "make", "know",
    "think", "people", "time", "day", "thing", "even", "still", "back",
    "way", "well", "also", "much", "new", "good", "first",
}


def _post_matches_pattern(
    post: Post, pattern: ViralPattern, post_hook: str, post_narrative: str, match_threshold: float
) -> bool:
    score = 0.0

    if pattern.hook_type:
        if post_hook == pattern.hook_type:
            score += 0.20

    if pattern.narrative_mode:
        if post_narrative == pattern.narrative_mode:
            score += 0.20

    if pattern.title_template:
        sim = _title_match(post.title, pattern.title_template)
        score += sim * 0.35

    if pattern.recommended_metrics:
        metrics = pattern.recommended_metrics
        title_words = len(post.title.split())
        if "title_words" in metrics:
            low, high = metrics["title_words"]
            if low <= title_words <= high:
                score += 0.125
        body_words = len(post.body.split()) if post.body else 0
        if "body_words" in metrics:
            low, high = metrics["body_words"]
            if low <= body_words <= high:
                score += 0.125

    return score >= match_threshold


def _title_match(title: str, template: str) -> float:
    """Score how well a title matches a pattern template (pipe-separated bigrams).

    Returns 0.0 to 1.0 based on how many signature bigrams appear in the title.
    """
    if not template:
        return 0.0
    title_lower = title.lower()
    bigrams = [bg.strip() for bg in template.split("|") if bg.strip()]
    if not bigrams:
        return 0.0
    matches = sum(1 for bg in bigrams if bg in title_lower)
    # At least 1 bigram match to contribute; scale by fraction matched
    if matches == 0:
        return 0.0
    return 0.4 + 0.6 * (matches / len(bigrams))


def _classify_narrative(body: str) -> str:
    if not body or len(body) < 20:
        return "no_body"
    b_lower = body.lower()
    if any(kw in b_lower for kw in ["step 1", "how to", "tutorial", "guide", "here's how"]):
        return "tutorial_howto"
    if any(kw in b_lower for kw in ["i think", "in my opinion", "unpopular", "should be"]):
        return "opinion_argument"
    if any(kw in b_lower for kw in ["i built", "i made", "i created", "check out my", "github.com"]):
        return "resource_showcase"
    if body.strip().endswith("?") or "anyone else" in b_lower:
        return "question_discussion"
    if any(kw in b_lower for kw in ["i ", "my ", "me ", "we "]) and len(b_lower) > 200:
        return "story_personal"
    return "opinion_argument"
