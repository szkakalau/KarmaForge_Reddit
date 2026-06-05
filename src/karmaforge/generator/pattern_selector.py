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
        """Score a pattern for a subreddit + topic combination.

        Phase 2: Uses time-decayed success_rate, subreddit-level performance,
        drift penalty, and calibrated metrics when available.
        """
        score = 0.0

        # 1. Subreddit applicability (0-40 points)
        #    Check subreddit-level performance first (Phase 2.2)
        subreddit_perf = pattern.get("subreddit_performance", {})
        sub = subreddit.lower()
        if sub in subreddit_perf:
            # Direct subreddit match with live performance data
            sub_rate = subreddit_perf[sub].get("success_rate", 0)
            sub_samples = subreddit_perf[sub].get("sample_size", 0)
            # Boost: 40 base + up to 10 extra for strong sub-specific performance
            score += 40 + min(sub_rate * 15, 10)
            if sub_samples >= 10:
                score += 5  # confidence bonus for sufficient sub-specific data
        else:
            applicable = pattern.get("applicable_subreddits", [])
            if subreddit in applicable:
                score += 40
            else:
                tier_eff = pattern.get("tier_effectiveness", {})
                if tier_eff:
                    score += 10

        # 2. Blended viral rate (0-30 points)
        #    Phase 2.1: success_rate already time-decayed from evolution
        historical_rate = pattern.get("historical_viral_rate", 0)
        success_rate = pattern.get("success_rate")
        if success_rate is not None:
            # Weighted blend: 60% historical + 40% live (increased live weight)
            viral_rate = 0.6 * historical_rate + 0.4 * success_rate
        else:
            viral_rate = historical_rate
        score += min(viral_rate * 40, 30)

        # 3. Sample size confidence (0-15 points)
        sample = pattern.get("sample_size", 0)
        feedback_samples = pattern.get("feedback_sample_size", 0)
        effective_sample = sample + feedback_samples
        if effective_sample >= 100:
            score += 15
        elif effective_sample >= 30:
            score += 8
        else:
            score += 3

        # 4. Drift penalty (Phase 2.3)
        drift_status = pattern.get("drift_status", "stable")
        if drift_status == "declining":
            drift_score = pattern.get("drift_score", 0.5)
            penalty = int((1.0 - drift_score) * 20)  # up to 20 point penalty
            score -= penalty
            logger.debug(
                "Pattern %s declining (drift=%.2f), penalized %d points",
                pattern.get("pattern_id", "?"), drift_score, penalty,
            )

        # 5. Hook type vs topic keyword relevance (0-15 points)
        hook = pattern.get("hook_type", "")
        if keywords and hook:
            if any(kw.lower() in hook.lower() for kw in keywords):
                score += 15
            elif self._hook_topic_match(hook, keywords):
                score += 8

        return max(0.0, score)

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
