"""Select the best viral patterns for a given subreddit and topic."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PatternSelector:
    """Load patterns from V1 output and select the best matches."""

    def __init__(self, patterns_path: str | Path) -> None:
        self.patterns_path = Path(patterns_path)
        self._patterns: list[dict] = []
        self._load()

    def _load(self) -> None:
        if not self.patterns_path.exists():
            logger.warning("Patterns file not found: %s", self.patterns_path)
            return
        with open(self.patterns_path, "r", encoding="utf-8") as f:
            self._patterns = json.load(f)
        logger.info("Loaded %d patterns from %s", len(self._patterns), self.patterns_path)

    def select(
        self,
        subreddit: str,
        topic_keywords: list[str] | None = None,
        n: int = 3,
    ) -> list[dict]:
        """Select top N patterns for a subreddit.

        Scoring: applicability × viral_rate × hook_relevance.
        Inactive patterns (from evolution) are skipped unless no alternatives exist.
        """
        candidates: list[tuple[dict, float]] = []
        inactive_candidates: list[tuple[dict, float]] = []

        for p in self._patterns:
            score = self._score_pattern(p, subreddit, topic_keywords or [])
            if score <= 0:
                continue
            if p.get("status") == "inactive":
                inactive_candidates.append((p, score))
            else:
                candidates.append((p, score))

        # Fall back to inactive patterns only if no active ones available
        if not candidates:
            candidates = inactive_candidates

        candidates.sort(key=lambda x: x[1], reverse=True)

        if not candidates:
            return self._generic_patterns(n)

        # Deduplicate by hook_type — prefer variety in top N
        selected: list[dict] = []
        seen_hooks: set[str] = set()
        for pat, _score in candidates:
            hook = pat.get("hook_type", "")
            if hook not in seen_hooks or len(selected) < 1:
                selected.append(pat)
                seen_hooks.add(hook)
            if len(selected) >= n:
                break

        return selected[:n]

    def _score_pattern(self, pattern: dict, subreddit: str, keywords: list[str]) -> float:
        """Score a pattern for a subreddit + topic combination."""
        score = 0.0

        # 1. Subreddit applicability (0-40 points)
        applicable = pattern.get("applicable_subreddits", [])
        if subreddit in applicable:
            score += 40
        else:
            # Check if any similar sub in same tier has this pattern
            tier_eff = pattern.get("tier_effectiveness", {})
            if tier_eff:
                score += 10  # pattern works in some tier

        # 2. Blended viral rate (0-30 points)
        # Blend historical (v1 analysis) with live success_rate from evolution
        historical_rate = pattern.get("historical_viral_rate", 0)
        success_rate = pattern.get("success_rate")
        if success_rate is not None:
            # Weighted blend: 70% historical + 30% live feedback
            viral_rate = 0.7 * historical_rate + 0.3 * success_rate
        else:
            viral_rate = historical_rate
        score += min(viral_rate * 40, 30)  # cap at 30

        # 3. Sample size confidence (0-15 points)
        sample = pattern.get("sample_size", 0)
        if sample >= 100:
            score += 15
        elif sample >= 30:
            score += 8
        else:
            score += 3

        # 4. Hook type vs topic keyword relevance (0-15 points)
        hook = pattern.get("hook_type", "")
        if keywords and hook:
            if any(kw.lower() in hook.lower() for kw in keywords):
                score += 15
            elif self._hook_topic_match(hook, keywords):
                score += 8

        return score

    @staticmethod
    def _hook_topic_match(hook: str, keywords: list[str]) -> bool:
        """Check if hook type is relevant to the topic."""
        keyword_str = " ".join(keywords).lower()

        hook_topic_map = {
            "tutorial_howto": ["how", "guide", "tutorial", "build", "made", "created", "script", "tool"],
            "resource_share": ["tool", "resource", "free", "build", "made", "created", "app"],
            "story_opener": ["journey", "story", "experience", "year", "month", "learned"],
            "curious_question": ["why", "how", "question", "anyone", "else"],
            "counterintuitive_discovery": ["discovered", "found", "changed", "unexpected", "surprising"],
            "controversial_opinion": ["opinion", "unpopular", "hot", "take", "controversial"],
            "pain_point": ["problem", "struggle", "frustration", "hard", "difficult", "fail"],
            "comparison_analysis": ["vs", "compar", "versus", "differ", "better", "best"],
            "identity_label": ["as a", "developer", "engineer", "founder", "student", "parent"],
            "number_shock": ["number", "stat", "percent", "million", "thousand"],
            "suspense_mystery": ["secret", "nobody", "hidden", "mystery", "unknown"],
        }

        relevant_words = hook_topic_map.get(hook, [])
        return any(w in keyword_str for w in relevant_words)

    def _generic_patterns(self, n: int) -> list[dict]:
        """Return patterns with the highest viral rates across all subreddits."""
        sorted_patterns = sorted(
            self._patterns,
            key=lambda p: (p.get("historical_viral_rate", 0), p.get("sample_size", 0)),
            reverse=True,
        )
        return sorted_patterns[:n]
