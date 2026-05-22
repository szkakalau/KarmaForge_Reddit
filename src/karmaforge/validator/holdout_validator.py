"""Holdout validation — test patterns on subreddits not seen during training.

Stratified holdout: 1 from T1, 1-2 from T2, 1 from T3.
"""

import logging
import random
from dataclasses import dataclass, field

import numpy as np

from ..storage import Post, Tier
from ..analyzer.title_analyzer import TitleAnalyzer
from ..analyzer.content_analyzer import ContentAnalyzer
from ..analyzer.meta_analyzer import MetaAnalyzer
from ..analyzer.visual_analyzer import VisualAnalyzer
from ..analyzer.pattern_extractor import PatternExtractor, ViralPattern

logger = logging.getLogger(__name__)


@dataclass
class HoldoutResult:
    holdout_subreddits: list[str] = field(default_factory=list)
    training_subreddits: list[str] = field(default_factory=list)
    training_precision: float = 0.0
    holdout_precision: float = 0.0
    precision_ratio: float = 0.0
    recall_training: float = 0.0
    recall_holdout: float = 0.0
    transferability_score: float = 0.0
    per_subreddit_metrics: dict = field(default_factory=dict)
    pass_threshold: bool = False

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            d[k] = list(v) if isinstance(v, tuple) else v
        return d


class HoldoutValidator:
    def __init__(
        self,
        pattern_extractor: PatternExtractor,
        num_holdout: int = 4,
        viral_percentile: float = 90.0,
        min_precision_ratio: float = 0.70,
        seed: int = 42,
    ) -> None:
        self.pattern_extractor = pattern_extractor
        self.num_holdout = num_holdout
        self.viral_percentile = viral_percentile
        self.min_precision_ratio = min_precision_ratio
        random.seed(seed)
        np.random.seed(seed)

    def run(self, all_posts: list[Post]) -> HoldoutResult:
        if len(all_posts) < 200:
            logger.error("Insufficient posts for holdout validation: %d", len(all_posts))
            return HoldoutResult()

        # Group subreddits by tier
        tiers = self._group_subreddits_by_tier(all_posts)
        holdout_subs = self._select_holdout_subreddits(tiers)

        training_subs = []
        for tier_subs in tiers.values():
            for sub in tier_subs:
                if sub not in holdout_subs:
                    training_subs.append(sub)

        train_posts = [p for p in all_posts if p.subreddit.lower() in training_subs]
        holdout_posts = [p for p in all_posts if p.subreddit.lower() in holdout_subs]

        logger.info("Holdout: %d train subs, %d holdout subs: %s", len(training_subs), len(holdout_subs), holdout_subs)

        # Extract patterns from training subreddits only
        title_results = TitleAnalyzer(use_llm=False).analyze(train_posts)
        content_results = ContentAnalyzer(use_llm=False).analyze(train_posts)
        meta_results = MetaAnalyzer().analyze(train_posts)
        visual_results = VisualAnalyzer().analyze(train_posts)

        patterns, _ = self.pattern_extractor.extract(
            train_posts, title_results, content_results, meta_results, visual_results
        )

        if not patterns:
            logger.warning("No patterns extracted from training set")
            return HoldoutResult(
                holdout_subreddits=holdout_subs,
                training_subreddits=training_subs,
            )

        train_metrics = self._evaluate_on_set(train_posts, patterns)
        holdout_metrics = self._evaluate_on_set(holdout_posts, patterns)

        training_precision = train_metrics["precision"]
        holdout_precision = holdout_metrics["precision"]
        precision_ratio = holdout_precision / max(training_precision, 0.001)

        per_sub = {}
        for sub in holdout_subs:
            sub_posts = [p for p in holdout_posts if p.subreddit.lower() == sub]
            if sub_posts:
                sub_metrics = self._evaluate_on_set(sub_posts, patterns)
                per_sub[sub] = sub_metrics

        result = HoldoutResult(
            holdout_subreddits=holdout_subs,
            training_subreddits=training_subs,
            training_precision=round(training_precision, 4),
            holdout_precision=round(holdout_precision, 4),
            precision_ratio=round(precision_ratio, 4),
            recall_training=round(train_metrics["recall"], 4),
            recall_holdout=round(holdout_metrics["recall"], 4),
            transferability_score=round(min(precision_ratio, 1.0), 4),
            per_subreddit_metrics=per_sub,
            pass_threshold=precision_ratio >= self.min_precision_ratio,
        )

        logger.info(
            "Holdout: training_precision=%.3f holdout_precision=%.3f ratio=%.3f pass=%s",
            training_precision, holdout_precision, precision_ratio, result.pass_threshold,
        )
        return result

    def _group_subreddits_by_tier(self, posts: list[Post]) -> dict[str, list[str]]:
        tiers: dict[str, set[str]] = {}
        for p in posts:
            tier = p.tier.value if p.tier else "unknown"
            tiers.setdefault(tier, set()).add(p.subreddit.lower())
        return {t: list(s) for t, s in tiers.items()}

    def _select_holdout_subreddits(self, tiers: dict[str, list[str]]) -> list[str]:
        holdout = []
        # 1 from T1
        if "t1" in tiers and tiers["t1"]:
            holdout.append(random.choice(tiers["t1"]))
        # 1 from T3
        if "t3" in tiers and tiers["t3"]:
            holdout.append(random.choice(tiers["t3"]))
        # Remaining from T2 (or any tier to fill)
        available = []
        for tier_name, subs in tiers.items():
            for sub in subs:
                if sub not in holdout:
                    available.append(sub)

        remaining = self.num_holdout - len(holdout)
        if available and remaining > 0:
            holdout.extend(random.sample(available, min(remaining, len(available))))

        return holdout

    def _evaluate_on_set(
        self, posts: list[Post], patterns: list[ViralPattern]
    ) -> dict:
        if not posts:
            return {"precision": 0.0, "recall": 0.0}

        upvotes = [p.upvotes for p in posts]
        threshold = np.percentile(upvotes, self.viral_percentile) if upvotes else 0

        tp, fp, fn = 0, 0, 0
        for p in posts:
            is_viral = p.upvotes >= threshold
            matched = any(self._post_matches_pattern(p, pat) for pat in patterns)

            if matched and is_viral:
                tp += 1
            elif matched and not is_viral:
                fp += 1
            elif not matched and is_viral:
                fn += 1

        return {
            "precision": tp / max(tp + fp, 1),
            "recall": tp / max(tp + fn, 1),
            "tp": tp, "fp": fp, "fn": fn,
        }

    @staticmethod
    def _post_matches_pattern(post: Post, pattern: ViralPattern) -> bool:
        score = 0.0
        if pattern.title_template:
            title_words = set(post.title.lower().split())
            template_words = set(pattern.title_template.lower().replace("{var}", "").split())
            if template_words:
                intersection = title_words & template_words
                score += (len(intersection) / max(len(template_words), 1)) * 0.5

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

        return score >= 0.6
