"""Body content analysis — length, structure, narrative mode, openings, readability."""

import re
from dataclasses import dataclass, field
from typing import Optional

from ..storage import Post, Tier
from ..llm import LLMClient
from ..llm.prompts import NARRATIVE_MODE_CLASSIFY, OPENING_PATTERN_CLASSIFY
from .analysis_utils import (
    compute_distribution,
    correlation_test,
    find_optimal_range,
    text_length_metrics,
    readability_scores,
)


@dataclass
class ContentAnalysisResult:
    word_count_distribution: dict = field(default_factory=dict)
    optimal_word_range: tuple = (0, 0)
    paragraph_count_distribution: dict = field(default_factory=dict)
    list_usage_rate: float = 0.0
    tldr_usage_rate: float = 0.0
    bold_usage_rate: float = 0.0
    quote_usage_rate: float = 0.0
    narrative_mode_distribution: dict = field(default_factory=dict)
    opening_pattern_distribution: dict = field(default_factory=dict)
    opening_templates: list[dict] = field(default_factory=list)
    question_ending_rate: float = 0.0
    call_to_action_rate: float = 0.0
    engagement_correlation: dict = field(default_factory=dict)
    readability_distribution: dict = field(default_factory=dict)
    readability_correlation: dict = field(default_factory=dict)
    optimal_readability_range: tuple = (0.0, 0.0)
    n: int = 0

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            d[k] = list(v) if isinstance(v, tuple) else v
        return d


class ContentAnalyzer:
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        use_llm: bool = True,
        significance_level: float = 0.05,
    ) -> None:
        self.llm = llm_client
        self.use_llm = use_llm and llm_client is not None
        self.alpha = significance_level

    def analyze(self, posts: list[Post]) -> ContentAnalysisResult:
        posts = [p for p in posts if p.body and len(p.body) >= 20]
        if not posts:
            return ContentAnalysisResult()

        bodies = [p.body for p in posts]
        upvotes = [p.upvotes for p in posts]
        comments = [p.num_comments for p in posts]

        result = ContentAnalysisResult()
        result.n = len(bodies)

        word_counts = [text_length_metrics(b)["word_count"] for b in bodies]
        result.word_count_distribution = compute_distribution(word_counts)
        result.optimal_word_range = find_optimal_range(word_counts, upvotes)

        para_counts = [max(1, b.count("\n\n") + 1) for b in bodies]
        result.paragraph_count_distribution = compute_distribution(para_counts)

        result.list_usage_rate = sum(1 for b in bodies if re.search(r"^[\-\*\d+\.]\s", b, re.MULTILINE)) / len(bodies)
        result.tldr_usage_rate = sum(1 for b in bodies if re.search(r"\bTL[;:]?DR\b", b, re.IGNORECASE)) / len(bodies)
        result.bold_usage_rate = sum(1 for b in bodies if "**" in b) / len(bodies)
        result.quote_usage_rate = sum(1 for b in bodies if b.startswith(">") or "\n>" in b) / len(bodies)

        result.question_ending_rate = sum(1 for b in bodies if b.strip().endswith("?")) / len(bodies)
        cta_keywords = ["let me know", "what do you think", "share your", "would love to hear", "comments below", "thoughts?", "agree?", "discuss"]
        result.call_to_action_rate = sum(1 for b in bodies if any(kw in b.lower() for kw in cta_keywords)) / len(bodies)

        engagement_indicators = [int(b.strip().endswith("?") or any(kw in b.lower() for kw in cta_keywords)) for b in bodies]
        result.engagement_correlation = correlation_test(engagement_indicators, comments)

        result.narrative_mode_distribution = self._classify_narrative_modes(bodies, upvotes)
        result.opening_pattern_distribution = self._classify_opening_patterns(bodies, upvotes)

        fk_scores = [readability_scores(b)["flesch_kincaid_grade"] for b in bodies]
        fre_scores = [readability_scores(b)["flesch_reading_ease"] for b in bodies]
        result.readability_distribution = {
            "flesch_kincaid_grade": compute_distribution(fk_scores),
            "flesch_reading_ease": compute_distribution(fre_scores),
        }
        result.readability_correlation = correlation_test(fk_scores, upvotes)
        result.optimal_readability_range = find_optimal_range(fk_scores, upvotes)

        return result

    def analyze_by_subreddit(self, posts: list[Post]) -> dict[str, ContentAnalysisResult]:
        groups: dict[str, list[Post]] = {}
        for p in posts:
            groups.setdefault(p.subreddit.lower(), []).append(p)
        return {sub: self.analyze(ps) for sub, ps in groups.items()}

    def analyze_by_tier(self, posts: list[Post]) -> dict[Tier, ContentAnalysisResult]:
        groups: dict[Tier, list[Post]] = {}
        for p in posts:
            if p.tier:
                groups.setdefault(p.tier, []).append(p)
        return {tier: self.analyze(ps) for tier, ps in groups.items()}

    def _classify_narrative_modes(self, bodies: list[str], upvotes: list[float]) -> dict:
        modes = ["story_personal", "tutorial_howto", "opinion_argument", "question_discussion",
                  "resource_showcase", "news_event", "humor_satire", "review_critique"]

        if self.use_llm and len(bodies) <= 200:
            excerpts = [b[:500] for b in bodies]
            results = self.llm.classify(excerpts, modes)
        else:
            results = self._heuristic_narrative_mode(bodies)

        dist: dict = {}
        for mode, upv in zip(results, upvotes):
            if mode not in dist:
                dist[mode] = {"count": 0, "total_upvotes": 0}
            dist[mode]["count"] += 1
            dist[mode]["total_upvotes"] += upv

        for mode in dist:
            dist[mode]["avg_upvotes"] = round(dist[mode]["total_upvotes"] / dist[mode]["count"], 1)
            dist[mode]["pct"] = round(dist[mode]["count"] / len(bodies), 3)

        return dist

    def _classify_opening_patterns(self, bodies: list[str], upvotes: list[float]) -> dict:
        patterns = ["hook_first", "background_first", "conflict_first", "personal_intro",
                     "direct_answer", "rhetorical_question", "quote_reference"]

        if self.use_llm and len(bodies) <= 200:
            openings = [b[:200] for b in bodies]
            results = self.llm.classify(openings, patterns)
        else:
            results = [self._heuristic_opening(b[:200]) for b in bodies]

        dist: dict = {}
        for pat, upv in zip(results, upvotes):
            if pat not in dist:
                dist[pat] = {"count": 0, "total_upvotes": 0}
            dist[pat]["count"] += 1
            dist[pat]["total_upvotes"] += upv

        for pat in dist:
            dist[pat]["avg_upvotes"] = round(dist[pat]["total_upvotes"] / dist[pat]["count"], 1)
            dist[pat]["pct"] = round(dist[pat]["count"] / len(bodies), 3)

        return dist

    @staticmethod
    def _heuristic_narrative_mode(bodies: list[str]) -> list[str]:
        results = []
        for b in bodies:
            b_lower = b.lower()
            if any(kw in b_lower for kw in ["step 1", "how to", "tutorial", "guide", "here's how"]):
                results.append("tutorial_howto")
            elif any(kw in b_lower for kw in ["i think", "in my opinion", "unpopular", "should be"]):
                results.append("opinion_argument")
            elif any(kw in b_lower for kw in ["i built", "i made", "i created", "check out my", "github.com"]):
                results.append("resource_showcase")
            elif b.strip().endswith("?") or "anyone else" in b_lower:
                results.append("question_discussion")
            elif any(kw in b_lower for kw in ["i ", "my ", "me ", "we "]) and len(b_lower) > 200:
                results.append("story_personal")
            else:
                results.append("opinion_argument")
        return results

    @staticmethod
    def _heuristic_opening(opening: str) -> str:
        first_sentence = opening.split(".")[0] if "." in opening else opening
        first_sentence = first_sentence.lower()
        if first_sentence.endswith("?"):
            return "rhetorical_question"
        if any(kw in first_sentence for kw in ["i am", "i'm", "my name", "a bit about"]):
            return "personal_intro"
        if any(kw in first_sentence for kw in ["i discovered", "you won't believe", "this changed", "imagine"]):
            return "hook_first"
        if any(kw in first_sentence for kw in ["the problem", "i was struggling", "i was frustrated"]):
            return "conflict_first"
        if any(kw in first_sentence for kw in ["here's", "let me", "first", "to start"]):
            return "direct_answer"
        if any(kw in first_sentence for kw in ["according to", "as ["]):
            return "quote_reference"
        return "background_first"
