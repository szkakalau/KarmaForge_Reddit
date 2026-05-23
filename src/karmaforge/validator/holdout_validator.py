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
from ..analyzer.analysis_utils import (
    batch_classify_heuristic, batch_classify_llm,
    HOOK_KEYWORDS, HOOK_CATEGORIES, HOOK_DESCRIPTIONS,
)

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
        llm_client = None,
    ) -> None:
        self.pattern_extractor = pattern_extractor
        self.num_holdout = num_holdout
        self.viral_percentile = viral_percentile
        self.min_precision_ratio = min_precision_ratio
        self.llm = llm_client
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

        titles = [p.title for p in posts]
        if self.llm:
            post_hooks = batch_classify_llm(
                titles, HOOK_CATEGORIES, HOOK_DESCRIPTIONS,
                self.llm, batch_size=20, task_name="title",
            )
        else:
            post_hooks = batch_classify_heuristic(titles, list(HOOK_KEYWORDS.keys()), HOOK_KEYWORDS)
        post_narratives = [_classify_narrative(p.body or "") for p in posts]

        tp, fp, fn = 0, 0, 0
        for i, p in enumerate(posts):
            is_viral = p.upvotes >= threshold
            matched = any(
                _post_matches_pattern(p, pat, post_hooks[i], post_narratives[i])
                for pat in patterns
            )

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

def _post_matches_pattern(
    post: Post, pattern: ViralPattern, post_hook: str, post_narrative: str
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

    return score >= 0.45


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
