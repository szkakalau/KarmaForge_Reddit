"""Title dimension analysis — length, structure, sentiment, hooks, keywords, temporality."""

from dataclasses import dataclass, field
from typing import Optional, Union

from ..storage import Post, Tier
from ..llm import LLMClient
from ..llm.prompts import HOOK_TYPE_CLASSIFY, SENTIMENT_ANALYZE
from .analysis_utils import (
    compute_distribution,
    correlation_test,
    find_optimal_range,
    keyword_extraction,
    compute_percentile_rank,
    text_length_metrics,
    batch_classify_heuristic,
    HOOK_KEYWORDS,
)


@dataclass
class TitleAnalysisResult:
    char_count_distribution: dict = field(default_factory=dict)
    word_count_distribution: dict = field(default_factory=dict)
    optimal_range: tuple = (0, 0)
    colon_usage: float = 0.0
    dash_usage: float = 0.0
    parenthesis_usage: float = 0.0
    number_usage: float = 0.0
    question_usage: float = 0.0
    structure_templates: list[dict] = field(default_factory=list)
    sentiment_distribution: dict = field(default_factory=dict)
    sentiment_intensity_correlation: dict = field(default_factory=dict)
    hook_type_distribution: dict = field(default_factory=dict)
    hook_type_by_tier: dict = field(default_factory=dict)
    top_keywords: list[dict] = field(default_factory=list)
    capitalization_patterns: dict = field(default_factory=dict)
    temporality_rate: float = 0.0
    temporality_gain: float = 0.0
    n: int = 0

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            if isinstance(v, tuple):
                d[k] = list(v)
            else:
                d[k] = v
        return d


class TitleAnalyzer:
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        use_llm: bool = True,
        significance_level: float = 0.05,
    ) -> None:
        self.llm = llm_client
        self.use_llm = use_llm and llm_client is not None
        self.alpha = significance_level

    def analyze(self, posts: list[Post]) -> TitleAnalysisResult:
        if not posts:
            return TitleAnalysisResult()

        titles = [p.title for p in posts if p.title]
        lengths = [text_length_metrics(t) for t in titles]
        upvotes = [p.upvotes for p in posts if p.title]

        char_counts = [m["char_count"] for m in lengths]
        word_counts = [m["word_count"] for m in lengths]

        result = TitleAnalysisResult()
        result.n = len(titles)

        result.char_count_distribution = compute_distribution(char_counts)
        result.word_count_distribution = compute_distribution(word_counts)

        opt = find_optimal_range(word_counts, upvotes)
        result.optimal_range = opt

        result.colon_usage = sum(1 for t in titles if ":" in t) / len(titles)
        result.dash_usage = sum(1 for t in titles if "—" in t or " - " in t) / len(titles)
        result.parenthesis_usage = sum(1 for t in titles if "(" in t) / len(titles)
        result.number_usage = sum(1 for t in titles if any(c.isdigit() for c in t)) / len(titles)
        result.question_usage = sum(1 for t in titles if t.strip().endswith("?")) / len(titles)

        result.structure_templates = self._extract_structure_templates(titles, upvotes)
        result.sentiment_distribution, result.sentiment_intensity_correlation = self._analyze_sentiment(titles, upvotes)
        result.hook_type_distribution = self._classify_hooks(titles, upvotes)
        result.top_keywords = keyword_extraction(titles)
        result.capitalization_patterns = self._capitalization_analysis(titles)
        result.temporality_rate, result.temporality_gain = self._temporality_analysis(titles, upvotes)

        return result

    def analyze_by_subreddit(self, posts: list[Post]) -> dict[str, TitleAnalysisResult]:
        by_sub = _group_by_subreddit(posts)
        return {sub: self.analyze(ps) for sub, ps in by_sub.items()}

    def analyze_by_tier(self, posts: list[Post]) -> dict[Tier, TitleAnalysisResult]:
        by_tier = _group_by_tier(posts)
        return {tier: self.analyze(ps) for tier, ps in by_tier.items()}

    def _extract_structure_templates(self, titles: list[str], upvotes: list[float]) -> list[dict]:
        patterns = {}
        for title, upv in zip(titles, upvotes):
            pattern = (
                ("colon" if ":" in title else "") + "|" +
                ("dash" if "—" in title or " - " in title else "") + "|" +
                ("question" if title.endswith("?") else "") + "|" +
                ("number" if any(c.isdigit() for c in title) else "") + "|" +
                ("bracket" if "[" in title or "(" in title else "")
            )
            if pattern not in patterns:
                patterns[pattern] = {"count": 0, "total_upvotes": 0}
            patterns[pattern]["count"] += 1
            patterns[pattern]["total_upvotes"] += upv

        result = []
        for pattern, stats in sorted(patterns.items(), key=lambda x: x[1]["count"], reverse=True)[:10]:
            if stats["count"] >= 5:
                result.append({
                    "pattern": pattern,
                    "count": stats["count"],
                    "avg_upvotes": round(stats["total_upvotes"] / stats["count"], 1),
                })
        return result

    def _analyze_sentiment(self, titles: list[str], upvotes: list[float]) -> tuple[dict, dict]:
        if self.use_llm and len(titles) <= 200:
            sentiments = self.llm.analyze_sentiment(titles)
        else:
            sentiments = self._heuristic_sentiment(titles)

        pos = sum(1 for s in sentiments if s["polarity"] == "positive")
        neg = sum(1 for s in sentiments if s["polarity"] == "negative")
        neu = sum(1 for s in sentiments if s["polarity"] == "neutral")
        total = max(len(sentiments), 1)

        distribution = {
            "positive": round(pos / total, 3),
            "negative": round(neg / total, 3),
            "neutral": round(neu / total, 3),
        }

        intensities = [s["intensity"] for s in sentiments]
        correlation = correlation_test(intensities, upvotes[:len(intensities)])

        return distribution, correlation

    def _classify_hooks(self, titles: list[str], upvotes: list[float]) -> dict:
        hook_categories = list(HOOK_KEYWORDS.keys())

        if self.use_llm and len(titles) <= 200:
            hook_types = self.llm.classify(titles, hook_categories)
        else:
            hook_types = batch_classify_heuristic(titles, hook_categories, HOOK_KEYWORDS)

        dist = {}
        for ht, upv in zip(hook_types, upvotes):
            if ht not in dist:
                dist[ht] = {"count": 0, "total_upvotes": 0, "upvotes_list": []}
            dist[ht]["count"] += 1
            dist[ht]["total_upvotes"] += upv
            dist[ht]["upvotes_list"].append(upv)

        for ht in dist:
            dist[ht]["avg_upvotes"] = round(dist[ht]["total_upvotes"] / dist[ht]["count"], 1)
            dist[ht]["std_upvotes"] = round(float(__import__("numpy").std(dist[ht]["upvotes_list"])), 1) if dist[ht]["count"] > 1 else 0
            del dist[ht]["upvotes_list"]

        return dist

    def _capitalization_analysis(self, titles: list[str]) -> dict:
        all_caps = sum(1 for t in titles if t.isupper() and len(t) > 10)
        has_caps = sum(1 for t in titles if any(c.isupper() for c in t) and not t.isupper())

        return {
            "all_caps_rate": round(all_caps / max(len(titles), 1), 3),
            "mixed_case_rate": round(has_caps / max(len(titles), 1), 3),
        }

    def _temporality_analysis(self, titles: list[str], upvotes: list[float]) -> tuple[float, float]:
        time_words = {"today", "just", "finally", "now", "yesterday", "tonight", "this week",
                       "this month", "this year", "breaking", "update", "latest", "new"}

        temporal_idx = []
        for i, t in enumerate(titles):
            if any(tw in t.lower() for tw in time_words):
                temporal_idx.append(i)

        rate = len(temporal_idx) / max(len(titles), 1)
        if temporal_idx and len(temporal_idx) < len(titles):
            temporal_avg = sum(upvotes[i] for i in temporal_idx) / len(temporal_idx)
            non_temporal_avg = sum(upvotes[i] for i in range(len(upvotes)) if i not in temporal_idx) / max(len(upvotes) - len(temporal_idx), 1)
            gain = temporal_avg - non_temporal_avg
        else:
            gain = 0

        return round(rate, 3), round(gain, 1)

    @staticmethod
    def _heuristic_sentiment(titles: list[str]) -> list[dict]:
        positive = {"good", "great", "best", "amazing", "love", "awesome", "beautiful", "perfect", "thank", "win", "success", "happy", "wow", "incredible", "fantastic", "finally"}
        negative = {"bad", "worst", "hate", "terrible", "awful", "sucks", "horrible", "fail", "death", "never", "wrong", "ugly", "boring", "disappointed", "frustrated", "problem"}

        results = []
        for t in titles:
            t_lower = t.lower()
            pos_count = sum(1 for w in positive if w in t_lower)
            neg_count = sum(1 for w in negative if w in t_lower)
            if pos_count > neg_count:
                results.append({"polarity": "positive", "intensity": min(pos_count / 5, 1.0)})
            elif neg_count > pos_count:
                results.append({"polarity": "negative", "intensity": min(neg_count / 5, 1.0)})
            else:
                results.append({"polarity": "neutral", "intensity": 0.3})
        return results


def _group_by_subreddit(posts: list[Post]) -> dict[str, list[Post]]:
    groups: dict[str, list[Post]] = {}
    for p in posts:
        sub = p.subreddit.lower()
        groups.setdefault(sub, []).append(p)
    return groups


def _group_by_tier(posts: list[Post]) -> dict[Tier, list[Post]]:
    groups: dict[Tier, list[Post]] = {}
    for p in posts:
        tier = p.tier
        if tier:
            groups.setdefault(tier, []).append(p)
    return groups
