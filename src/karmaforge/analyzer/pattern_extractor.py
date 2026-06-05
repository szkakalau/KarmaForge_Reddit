"""Viral pattern extraction — clusters posts and identifies statistically significant patterns.

Algorithm:
1. Cluster posts by (tier, hook_type, narrative_mode)
2. Compute time-weighted viral_rate per cluster
3. Chi-square test for significance
4. Extract title/body templates from significant clusters
5. Also extract anti-patterns from bottom-performing posts
6. Optional: extract per-subreddit patterns + merge across subs
"""

import json
import logging
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Optional

import numpy as np

from ..storage import Post, Tier
from ..llm import LLMClient
from ..llm.prompts import PATTERN_SUMMARIZE
from .analysis_utils import (
    chi_square_test, bootstrap_confidence_interval,
    batch_classify_heuristic, batch_classify_llm,
    HOOK_KEYWORDS, HOOK_CATEGORIES, HOOK_DESCRIPTIONS,
)
from .title_analyzer import TitleAnalyzer, TitleAnalysisResult
from .content_analyzer import ContentAnalyzer, ContentAnalysisResult
from .meta_analyzer import MetaAnalyzer, MetaAnalysisResult
from .visual_analyzer import VisualAnalyzer, VisualAnalysisResult
from .lifecycle_analyzer import LifecycleAnalyzer, LifecycleAnalysisResult

logger = logging.getLogger(__name__)

# ── Time-decay constants ──
DEFAULT_HALF_LIFE_DAYS = 180  # 6 months — patterns older than this lose 50% weight
MIN_POSTS_PER_SUBREDDIT = 100  # Minimum posts for per-subreddit pattern extraction


@dataclass
class ViralPattern:
    pattern_id: str
    name: str
    description: str
    applicable_subreddits: list[str] = field(default_factory=list)
    title_template: str = ""
    body_structure_template: str = ""
    historical_viral_rate: float = 0.0
    confidence_interval: tuple = (0.0, 0.0)
    avg_upvotes: float = 0.0
    p_value: float = 1.0
    exemplar_posts: list[str] = field(default_factory=list)
    hook_type: str = ""
    narrative_mode: str = ""
    recommended_metrics: dict = field(default_factory=dict)
    tier_effectiveness: dict = field(default_factory=dict)
    sample_size: int = 0

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            if isinstance(v, tuple):
                d[k] = list(v)
            else:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ViralPattern":
        d = dict(d)
        d["confidence_interval"] = tuple(d.get("confidence_interval", [0, 0]))
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class AntiPattern:
    pattern_id: str
    name: str
    description: str
    failure_rate: float = 0.0
    exemplar_posts: list[str] = field(default_factory=list)
    why_it_fails: str = ""
    sample_size: int = 0

    def to_dict(self) -> dict:
        return self.__dict__

    @classmethod
    def from_dict(cls, d: dict) -> "AntiPattern":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class PatternExtractor:
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        significance_level: float = 0.05,
        min_cluster_size: int = 30,
        viral_percentile: float = 90.0,
        max_patterns: int = 8,
        title_similarity_threshold: float = 0.6,
        use_time_decay: bool = True,
        half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
        min_posts_per_subreddit: int = MIN_POSTS_PER_SUBREDDIT,
    ) -> None:
        self.llm = llm_client
        self.alpha = significance_level
        self.min_cluster_size = min_cluster_size
        self.viral_percentile = viral_percentile
        self.max_patterns = max_patterns
        self.title_threshold = title_similarity_threshold
        self.use_time_decay = use_time_decay
        self.half_life_days = half_life_days
        self.min_posts_per_sub = min_posts_per_subreddit
        self._decay_lambda = math.log(2) / half_life_days if half_life_days > 0 else 0.0

    def extract(
        self,
        posts: list[Post],
        title_results: TitleAnalysisResult,
        content_results: ContentAnalysisResult,
        meta_results: MetaAnalysisResult,
        visual_results: VisualAnalysisResult,
        lifecycle_results: Optional[LifecycleAnalysisResult] = None,
    ) -> tuple[list[ViralPattern], list[AntiPattern]]:
        if len(posts) < self.min_cluster_size * 3:
            logger.warning("Too few posts (%d) for pattern extraction", len(posts))
            return [], []

        viral_posts, non_viral_posts = self._split_viral(posts)
        if len(viral_posts) < self.min_cluster_size:
            logger.warning("Too few viral posts for pattern extraction")
            return [], []

        clusters = self._cluster_posts(posts, viral_posts, non_viral_posts)
        patterns = self._extract_patterns_from_clusters(clusters, posts, title_results)
        anti_patterns = self._extract_anti_patterns(non_viral_posts, posts)

        # Score patterns by (time-weighted viral rate) × log(sample_size)
        # Recency bonus gives edge to patterns that perform better recently
        patterns.sort(key=lambda p: p.historical_viral_rate * np.log(max(p.sample_size, 1)), reverse=True)
        patterns = patterns[:self.max_patterns]

        if self.llm:
            patterns = self._enrich_with_llm(patterns)

        return patterns, anti_patterns

    def extract_by_tier(
        self,
        posts_by_tier: dict[Tier, list[Post]],
        title_results: dict[Tier, TitleAnalysisResult],
        content_results: dict[Tier, ContentAnalysisResult],
        meta_results: dict[Tier, MetaAnalysisResult],
        visual_results: dict[Tier, VisualAnalysisResult],
    ) -> dict[Tier, list[ViralPattern]]:
        results = {}
        for tier in [Tier.T1, Tier.T2, Tier.T3]:
            if tier in posts_by_tier:
                patterns, _ = self.extract(
                    posts_by_tier[tier],
                    title_results.get(tier, TitleAnalysisResult()),
                    content_results.get(tier, ContentAnalysisResult()),
                    meta_results.get(tier, MetaAnalysisResult()),
                    visual_results.get(tier, VisualAnalysisResult()),
                )
                results[tier] = patterns
        return results

    def extract_by_subreddit(
        self,
        posts: list[Post],
        title_results: TitleAnalysisResult,
        content_results: ContentAnalysisResult,
        meta_results: MetaAnalysisResult,
        visual_results: VisualAnalysisResult,
        lifecycle_results: Optional[LifecycleAnalysisResult] = None,
    ) -> tuple[list[ViralPattern], list[AntiPattern]]:
        """Extract patterns per subreddit, then merge similar ones across subs.

        Unlike tier-level extraction which produces generic patterns
        (e.g., "curious_question + no_body in t2"), per-subreddit patterns
        capture subreddit-specific dynamics (e.g., "story_opener + has_body
        in r/productivity").

        Subreddits with < min_posts_per_sub are pooled into "other" and
        extracted together to avoid wasting their signal.
        """
        # Group posts by subreddit
        by_sub: dict[str, list[Post]] = defaultdict(list)
        for p in posts:
            by_sub[p.subreddit.lower()].append(p)

        # Split into "has enough" and "too few"
        solo_subs = {s: ps for s, ps in by_sub.items() if len(ps) >= self.min_posts_per_sub}
        small_subs_posts = [p for s, ps in by_sub.items() if s not in solo_subs for p in ps]

        logger.info(
            "Per-subreddit extraction: %d solo subs (≥%d posts), %d pooled subs (%d posts)",
            len(solo_subs), self.min_posts_per_sub,
            len(by_sub) - len(solo_subs), len(small_subs_posts),
        )

        all_patterns: list[ViralPattern] = []

        # Extract patterns per well-covered subreddit
        for sub, sub_posts in solo_subs.items():
            if len(sub_posts) < self.min_cluster_size * 3:
                continue
            try:
                patterns, _ = self.extract(
                    sub_posts, title_results, content_results,
                    meta_results, visual_results, lifecycle_results,
                )
                # Tag with subreddit specificity
                for p in patterns:
                    p.applicable_subreddits = [sub]
                    p.description = f"[r/{sub}] {p.description}"
                all_patterns.extend(patterns)
            except Exception:
                logger.debug("Skipping r/%s — insufficient data for patterns", sub)

        # Extract from the pooled small subreddits
        if len(small_subs_posts) >= self.min_cluster_size * 3:
            try:
                pooled_patterns, _ = self.extract(
                    small_subs_posts, title_results, content_results,
                    meta_results, visual_results, lifecycle_results,
                )
                all_patterns.extend(pooled_patterns)
            except Exception:
                pass

        # Merge similar patterns across subreddits
        merged = self._merge_similar_patterns(all_patterns)

        # Keep top N by score
        merged.sort(
            key=lambda p: p.historical_viral_rate * np.log(max(p.sample_size, 1)),
            reverse=True,
        )
        merged = merged[:self.max_patterns]

        # Anti-patterns still use global extraction
        _, anti_patterns = self.extract(
            posts, title_results, content_results,
            meta_results, visual_results, lifecycle_results,
        )

        return merged, anti_patterns

    def _merge_similar_patterns(
        self, patterns: list[ViralPattern]
    ) -> list[ViralPattern]:
        """Merge patterns that share (hook_type, narrative_mode) and have
        overlapping subreddits.  Keeps the highest-scoring pattern as the
        base and absorbs applicable_subreddits from merged patterns.
        """
        if len(patterns) <= self.max_patterns:
            return patterns

        # Group by (hook_type, narrative_mode)
        groups: dict[tuple, list[ViralPattern]] = defaultdict(list)
        for p in patterns:
            key = (p.hook_type, p.narrative_mode)
            groups[key].append(p)

        merged = []
        for key, group in groups.items():
            if len(group) == 1:
                merged.append(group[0])
            else:
                # Sort by score, keep highest as base
                group.sort(
                    key=lambda p: p.historical_viral_rate * np.log(max(p.sample_size, 1)),
                    reverse=True,
                )
                base = group[0]
                # Absorb subreddits from lower-scoring patterns
                all_subs = set(base.applicable_subreddits)
                for other in group[1:]:
                    all_subs.update(other.applicable_subreddits)
                    base.sample_size += other.sample_size
                base.applicable_subreddits = sorted(all_subs)
                merged.append(base)

        return merged

    # ── Time-decay weighting ──────────────────────────────────────────────
    def _compute_time_weights(
        self, posts: list[Post], reference_date: Optional[datetime] = None
    ) -> np.ndarray:
        """Compute exponential time-decay weights for a list of posts.

        weight = exp(-λ × days_ago)
        λ = ln(2) / half_life_days

        A post from 180 days ago gets 0.5× weight; 360 days → 0.25×.
        Posts without timestamps get the median weight.
        """
        if not self.use_time_decay or not posts:
            return np.ones(len(posts))

        if reference_date is None:
            timestamps = [p.created_utc for p in posts if p.created_utc is not None]
            reference_date = max(timestamps) if timestamps else datetime.now(timezone.utc)

        days_ago = np.array([
            (reference_date - (p.created_utc or reference_date)).days
            for p in posts
        ], dtype=float)

        weights = np.exp(-self._decay_lambda * np.maximum(days_ago, 0))
        return weights

    def _split_viral(self, posts: list[Post]) -> tuple[list[Post], list[Post]]:
        viral, non_viral = [], []
        upvotes_list = [p.upvotes for p in posts]
        threshold = np.percentile(upvotes_list, self.viral_percentile)

        for p in posts:
            if p.upvotes >= threshold:
                viral.append(p)
            else:
                non_viral.append(p)

        return viral, non_viral

    def _cluster_posts(
        self, posts: list[Post], viral_posts: list[Post], non_viral_posts: list[Post]
    ) -> list[dict]:
        titles = [p.title for p in posts]
        if self.llm:
            hook_types = batch_classify_llm(
                titles, HOOK_CATEGORIES, HOOK_DESCRIPTIONS,
                self.llm, batch_size=20, task_name="title",
            )
        else:
            hook_types = batch_classify_heuristic(titles, list(HOOK_KEYWORDS.keys()), HOOK_KEYWORDS)

        bodies = [p.body or "" for p in posts]
        raw_narrative_modes = [self._heuristic_narrative_mode(b) for b in bodies]

        # Collapse 8 body-text narrative modes into "has_body" to prevent
        # fragmentation. With 5+ distinct body modes × 11 hook types = 55+
        # combinations, body-text posts were spread too thin to reach
        # min_cluster_size.  Collapsing to has_body/no_body yields ~11
        # combinations each, allowing body-text patterns to emerge.
        # This directly fixes the recall ceiling (~27%) caused by all
        # patterns being locked to "no_body".
        _BODY_MODES = {
            "story_personal", "tutorial_howto", "opinion_argument",
            "question_discussion", "resource_showcase", "news_event",
            "humor_satire", "review_critique",
        }
        narrative_modes = [
            "has_body" if m in _BODY_MODES else m
            for m in raw_narrative_modes
        ]

        clusters: dict[tuple, dict] = {}
        for i, p in enumerate(posts):
            tier = p.tier.value if p.tier else "unknown"
            hook_type = hook_types[i]
            narrative_mode = narrative_modes[i]
            content_type = p.content_type.value if p.content_type else "text"
            # Drop content_type from cluster key: fragmenting 3×11×2=66 combos
            # across 4 content_types → 264 buckets was preventing body-text
            # patterns from reaching min_cluster_size.  Content type is still
            # tracked per cluster as the dominant type.
            key = (tier, hook_type, narrative_mode)

            clusters.setdefault(key, {
                "viral": 0, "total": 0, "total_upvotes": 0, "posts": [],
                "tier": tier, "hook_type": hook_type,
                "narrative_mode": narrative_mode,
                "content_types": {},
            })
            clusters[key]["total"] += 1
            clusters[key]["total_upvotes"] += p.upvotes
            clusters[key]["posts"].append(p)
            # Track dominant content type per cluster
            ct = clusters[key]["content_types"]
            ct[content_type] = ct.get(content_type, 0) + 1

        viral_ids = {p.post_id for p in viral_posts}
        for key, stats in clusters.items():
            for p in stats["posts"]:
                if p.post_id in viral_ids:
                    stats["viral"] += 1

        result = []
        for key, stats in clusters.items():
            # Use dominant content type for the cluster description
            dominant_ct = max(stats["content_types"], key=stats["content_types"].get) if stats["content_types"] else "text"
            result.append({
                "tier": stats["tier"],
                "hook_type": stats["hook_type"],
                "narrative_mode": stats["narrative_mode"],
                "content_type": dominant_ct,
                "viral_count": stats["viral"],
                "total": stats["total"],
                "viral_rate": stats["viral"] / max(stats["total"], 1),
                "avg_upvotes": stats["total_upvotes"] / max(stats["total"], 1),
                "posts": stats["posts"],
            })

        return result

    @staticmethod
    def _heuristic_narrative_mode(body: str) -> str:
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

    def _extract_patterns_from_clusters(
        self,
        clusters: list[dict],
        all_posts: list[Post],
        title_results: TitleAnalysisResult,
    ) -> list[ViralPattern]:
        all_upvotes = [p.upvotes for p in all_posts]
        viral_threshold = np.percentile(all_upvotes, self.viral_percentile) if all_upvotes else 0
        v_all = sum(c["viral_count"] for c in clusters)
        t_all = sum(c["total"] for c in clusters)
        patterns = []

        for i, cluster in enumerate(clusters):
            if cluster["total"] < self.min_cluster_size:
                continue
            if cluster["viral_count"] < 5:
                continue

            v_in = cluster["viral_count"]
            t_in = cluster["total"]
            observed = [
                [v_in, t_in - v_in],
                [v_all - v_in, (t_all - t_in) - (v_all - v_in)],
            ]
            chi_result = chi_square_test(observed)
            p_value = chi_result.get("p_value", 1.0)

            if p_value > self.alpha:
                continue

            viral_posts_in_cluster = [p for p in cluster["posts"] if p.upvotes >= viral_threshold]

            # ── Time-weighted viral rate ──
            cluster_weights = self._compute_time_weights(cluster["posts"])
            weighted_viral = sum(
                w for p, w in zip(cluster["posts"], cluster_weights)
                if p.upvotes >= viral_threshold
            )
            weighted_total = sum(cluster_weights)
            time_weighted_viral_rate = weighted_viral / max(weighted_total, 1e-9)
            # Blend: 70% time-weighted + 30% raw (avoids over-penalizing
            # small clusters with one old viral post)
            blended_rate = 0.7 * time_weighted_viral_rate + 0.3 * cluster["viral_rate"]

            titles = [p.title for p in viral_posts_in_cluster if p.title]
            title_template = self._extract_title_template(titles)

            # Bootstrap CI from cluster's own posts (not global population)
            cluster_upvotes = [p.upvotes for p in cluster["posts"]]
            viral_rates = []
            rng = np.random.default_rng(42)
            n_iter = min(1000, len(cluster_upvotes) * 10)
            for _ in range(n_iter):
                sample = rng.choice(cluster_upvotes, size=len(cluster_upvotes), replace=True)
                viral_rates.append(
                    sum(1 for s in sample if s >= viral_threshold) / len(sample)
                )

            ci_lower = round(float(np.percentile(viral_rates, 2.5)), 4)
            ci_upper = round(float(np.percentile(viral_rates, 97.5)), 4)

            # ── Recency bonus for scoring ──
            # Patterns with higher time-weighted rate (vs raw) are more current
            recency_bonus = max(0.0, time_weighted_viral_rate - cluster["viral_rate"])

            pattern_id = f"pattern_{i:02d}"
            exemplar_ids = [p.post_id for p in viral_posts_in_cluster[:5]]

            pattern = ViralPattern(
                pattern_id=pattern_id,
                name=f"Pattern {i+1}: {cluster.get('hook_type', '')} + {cluster.get('narrative_mode', '')}",
                description=f"{cluster.get('hook_type', '')} × {cluster.get('narrative_mode', '')} in {cluster['tier']}/{cluster.get('content_type', 'any')}",
                applicable_subreddits=list(set(p.subreddit for p in cluster["posts"])),
                title_template=title_template,
                historical_viral_rate=round(blended_rate, 3),
                confidence_interval=(ci_lower, ci_upper),
                avg_upvotes=round(cluster["avg_upvotes"], 1),
                p_value=p_value,
                exemplar_posts=exemplar_ids,
                hook_type=cluster.get("hook_type", ""),
                narrative_mode=cluster.get("narrative_mode", ""),
                tier_effectiveness={cluster["tier"]: round(blended_rate, 3)},
                sample_size=cluster["total"],
            )

            # Extract recommended metrics from the cluster
            word_counts = [len(p.title.split()) for p in viral_posts_in_cluster if p.title]
            body_lengths = [len(p.body.split()) for p in viral_posts_in_cluster if p.body]
            if word_counts:
                pattern.recommended_metrics["title_words"] = (
                    int(np.percentile(word_counts, 25)),
                    int(np.percentile(word_counts, 75)),
                )
            if body_lengths:
                pattern.recommended_metrics["body_words"] = (
                    int(np.percentile(body_lengths, 25)),
                    int(np.percentile(body_lengths, 75)),
                )

            patterns.append(pattern)

        return patterns

    def _extract_title_template(self, titles: list[str]) -> str:
        """Extract discriminative n-grams (bigrams + trigrams) from viral cluster titles.

        Returns pipe-separated n-grams that appear across multiple titles.
        Lowered threshold (15% → 5%) and added trigrams to fix the empty-template
        problem where 5/8 patterns had no title template at all.
        """
        if not titles or len(titles) < 3:
            return ""

        from collections import Counter

        STOP = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "have", "has", "had", "do", "does", "did", "will", "would",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "and", "but", "or", "not", "so", "if", "this", "that", "it",
            "i", "me", "my", "we", "our", "you", "your", "he", "she",
            "what", "which", "who", "when", "where", "why", "how",
            "just", "about", "like", "all", "can", "get", "one", "really",
            # Reddit-specific noise words
            "anyone", "else", "know", "think", "need", "help", "please",
            "does", "don't", "didn't", "won't", "isn't", "aren't",
            "there", "here", "some", "more", "much", "very", "even",
            "still", "also", "than", "then", "now", "only", "too",
        }

        bigram_counts: Counter = Counter()
        trigram_counts: Counter = Counter()

        for title in titles:
            words = [w.lower().strip(".,!?:;\"'()[]") for w in title.split()]
            words = [w for w in words if w and w not in STOP and len(w) > 2]

            # Bigrams
            for i in range(len(words) - 1):
                bg = f"{words[i]} {words[i+1]}"
                bigram_counts[bg] += 1

            # Trigrams (higher weight — more discriminative)
            for i in range(len(words) - 2):
                tg = f"{words[i]} {words[i+1]} {words[i+2]}"
                trigram_counts[tg] += 1

        # Lowered threshold: 5% (was 15%), min 2 occurrences
        min_count = max(2, int(len(titles) * 0.05))

        # Collect top n-grams — trigrams weighted higher (×1.5)
        scored: list[tuple[str, float]] = []
        for bg, count in bigram_counts.most_common(15):
            if count >= min_count:
                scored.append((bg, count))
        for tg, count in trigram_counts.most_common(10):
            if count >= min_count:
                scored.append((tg, count * 1.5))  # weight bonus for trigrams

        # Sort by weighted frequency, take top 6
        scored.sort(key=lambda x: x[1], reverse=True)
        top_ngrams = [ng for ng, _ in scored[:6]]

        return "|".join(top_ngrams)

    def _extract_anti_patterns(
        self, non_viral_posts: list[Post], all_posts: list[Post]
    ) -> list[AntiPattern]:
        if len(non_viral_posts) < self.min_cluster_size:
            return []

        # Group non-viral posts by cluster features
        clusters: dict[str, list[Post]] = defaultdict(list)
        for p in non_viral_posts:
            word_count = len(p.title.split())
            body_count = len(p.body.split())
            if word_count < 5:
                clusters["very_short_title"].append(p)
            elif word_count > 30:
                clusters["very_long_title"].append(p)
            elif body_count == 0:
                clusters["no_body_text"].append(p)
            elif body_count > 1000:
                clusters["very_long_body"].append(p)
            else:
                clusters["generic_low_engagement"].append(p)

        anti_patterns = []
        all_upvotes = [p.upvotes for p in all_posts]
        median_upvote = np.median(all_upvotes) if all_upvotes else 1.0

        for key, cluster_posts in clusters.items():
            if len(cluster_posts) < 10:
                continue

            failure_rate = sum(1 for p in cluster_posts if p.upvotes < median_upvote) / len(cluster_posts)

            explanations = {
                "very_short_title": "Titles under 5 words fail to provide enough information to attract clicks",
                "very_long_title": "Titles over 30 words overwhelm readers; most subreddits prefer concise hooks (12-22 words)",
                "no_body_text": "Posts with no body text (link/image-only with no context) generate less discussion",
                "very_long_body": "Bodies over 1000 words lose reader attention; break into sections or add a TL;DR",
                "generic_low_engagement": "Posts without a clear hook type, narrative mode, or structural pattern fail to compete for attention",
            }

            anti_patterns.append(AntiPattern(
                pattern_id=f"anti_{key}",
                name=key.replace("_", " ").title(),
                description=f"Posts with {key.replace('_', ' ')} consistently underperform",
                failure_rate=round(failure_rate, 3),
                exemplar_posts=[p.post_id for p in cluster_posts[:3]],
                why_it_fails=explanations.get(key, ""),
                sample_size=len(cluster_posts),
            ))

        return anti_patterns

    def _enrich_with_llm(self, patterns: list[ViralPattern]) -> list[ViralPattern]:
        for pattern in patterns:
            if not self.llm:
                break
            try:
                titles_str = "\n".join(f"- {pid}" for pid in pattern.exemplar_posts[:3])
                prompt = PATTERN_SUMMARIZE.format(
                    hook_type="mixed",
                    narrative_mode="mixed",
                    avg_upvotes=pattern.avg_upvotes,
                    viral_rate=pattern.historical_viral_rate * 100,
                    subreddits=", ".join(pattern.applicable_subreddits[:5]),
                    titles=titles_str,
                    bodies="See exemplar posts for details",
                )
                response = self.llm.complete(prompt)
                parsed = json.loads(response) if response.startswith("{") else {}
                if parsed:
                    pattern.name = parsed.get("name", pattern.name)
                    pattern.description = parsed.get("description", pattern.description)
                    pattern.title_template = parsed.get("title_formula", pattern.title_template)
                    if "body_structure" in parsed:
                        pattern.body_structure_template = json.dumps(parsed["body_structure"])
            except Exception:
                continue

        return patterns

    def save_patterns(
        self, patterns: list[ViralPattern], anti_patterns: list[AntiPattern], output_dir: Path
    ) -> None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        with open(output_dir / "patterns.json", "w", encoding="utf-8") as f:
            json.dump([p.to_dict() for p in patterns], f, ensure_ascii=False, indent=2)

        with open(output_dir / "anti_patterns.json", "w", encoding="utf-8") as f:
            json.dump([ap.to_dict() for ap in anti_patterns], f, ensure_ascii=False, indent=2)

        logger.info("Saved %d patterns and %d anti-patterns to %s", len(patterns), len(anti_patterns), output_dir)

    @classmethod
    def load_patterns(cls, output_dir: Path) -> tuple[list[ViralPattern], list[AntiPattern]]:
        output_dir = Path(output_dir)
        patterns, anti_patterns = [], []

        patterns_file = output_dir / "patterns.json"
        if patterns_file.exists():
            with open(patterns_file, "r", encoding="utf-8") as f:
                patterns = [ViralPattern.from_dict(d) for d in json.load(f)]

        anti_file = output_dir / "anti_patterns.json"
        if anti_file.exists():
            with open(anti_file, "r", encoding="utf-8") as f:
                anti_patterns = [AntiPattern.from_dict(d) for d in json.load(f)]

        return patterns, anti_patterns
