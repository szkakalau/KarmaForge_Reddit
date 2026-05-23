"""Viral pattern extraction — clusters posts and identifies statistically significant patterns.

Algorithm:
1. Cluster posts by (hook_type, narrative_mode, content_type, tier)
2. Compute viral_rate per cluster
3. Chi-square test for significance
4. Extract title/body templates from significant clusters
5. Also extract anti-patterns from bottom-performing posts
"""

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
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
    ) -> None:
        self.llm = llm_client
        self.alpha = significance_level
        self.min_cluster_size = min_cluster_size
        self.viral_percentile = viral_percentile
        self.max_patterns = max_patterns
        self.title_threshold = title_similarity_threshold

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
        narrative_modes = [self._heuristic_narrative_mode(b) for b in bodies]

        clusters: dict[tuple, dict] = {}
        for i, p in enumerate(posts):
            tier = p.tier.value if p.tier else "unknown"
            hook_type = hook_types[i]
            narrative_mode = narrative_modes[i]
            content_type = p.content_type.value if p.content_type else "text"
            key = (tier, hook_type, narrative_mode, content_type)

            clusters.setdefault(key, {
                "viral": 0, "total": 0, "total_upvotes": 0, "posts": [],
                "tier": tier, "hook_type": hook_type,
                "narrative_mode": narrative_mode, "content_type": content_type,
            })
            clusters[key]["total"] += 1
            clusters[key]["total_upvotes"] += p.upvotes
            clusters[key]["posts"].append(p)

        viral_ids = {p.post_id for p in viral_posts}
        for key, stats in clusters.items():
            for p in stats["posts"]:
                if p.post_id in viral_ids:
                    stats["viral"] += 1

        result = []
        for key, stats in clusters.items():
            result.append({
                "tier": stats["tier"],
                "hook_type": stats["hook_type"],
                "narrative_mode": stats["narrative_mode"],
                "content_type": stats["content_type"],
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

            titles = [p.title for p in viral_posts_in_cluster if p.title]
            title_template = self._extract_title_template(titles)

            viral_rates = []
            for _ in range(100):
                sample = np.random.choice(all_upvotes, size=cluster["total"], replace=True)
                viral_rates.append(sum(1 for s in sample if s >= viral_threshold) / len(sample))

            ci_lower = round(float(np.percentile(viral_rates, 2.5)), 4)
            ci_upper = round(float(np.percentile(viral_rates, 97.5)), 4)

            pattern_id = f"pattern_{i:02d}"
            exemplar_ids = [p.post_id for p in viral_posts_in_cluster[:5]]

            pattern = ViralPattern(
                pattern_id=pattern_id,
                name=f"Pattern {i+1}: {cluster.get('hook_type', '')} + {cluster.get('narrative_mode', '')}",
                description=f"{cluster.get('hook_type', '')} × {cluster.get('narrative_mode', '')} in {cluster['tier']}/{cluster.get('content_type', 'any')}",
                applicable_subreddits=list(set(p.subreddit for p in cluster["posts"])),
                title_template=title_template,
                historical_viral_rate=round(cluster["viral_rate"], 3),
                confidence_interval=(ci_lower, ci_upper),
                avg_upvotes=round(cluster["avg_upvotes"], 1),
                p_value=p_value,
                exemplar_posts=exemplar_ids,
                hook_type=cluster.get("hook_type", ""),
                narrative_mode=cluster.get("narrative_mode", ""),
                tier_effectiveness={cluster["tier"]: cluster["viral_rate"]},
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
        """Extract discriminative bigrams from viral cluster titles.

        Returns pipe-separated bigrams that appear across multiple titles.
        These are used for matching: a post matches if its title contains any bigram.
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
        }

        bigram_counts: Counter = Counter()
        for title in titles:
            words = [w.lower().strip(".,!?:;\"'()[]") for w in title.split()]
            words = [w for w in words if w and w not in STOP and len(w) > 2]
            for i in range(len(words) - 1):
                bg = f"{words[i]} {words[i+1]}"
                bigram_counts[bg] += 1

        # Take bigrams that appear in at least 15% of titles, up to 5
        min_count = max(2, int(len(titles) * 0.15))
        top_bigrams = [
            bg for bg, count in bigram_counts.most_common(10)
            if count >= min_count
        ][:5]

        return "|".join(top_bigrams)

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
