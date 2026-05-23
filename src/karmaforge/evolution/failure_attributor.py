"""Failure attributor — diagnose why a generated post underperformed."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from . import FailureAttribution

logger = logging.getLogger(__name__)

# Weight of each dimension in the composite score
DIMENSION_WEIGHTS = {
    "title_hook_fit": 0.30,
    "body_structure_fit": 0.25,
    "timing_fit": 0.15,
    "topic_relevance": 0.15,
    "content_quality": 0.15,
}


class FailureAttributor:
    """Analyze why a post underperformed using deterministic rules + optional LLM."""

    def __init__(self, llm_client=None) -> None:
        self._llm = llm_client

    def attribute(self, entry: dict, pattern: dict | None = None) -> FailureAttribution:
        """Run attribution analysis on a failed feedback entry."""
        dimensions = self._rule_based_attribution(entry, pattern)

        if self._llm:
            llm_result = self._llm_attribution(entry, pattern)
            if llm_result:
                dimensions.update(llm_result)

        primary, secondary, actions = self._synthesize(dimensions)
        confidence = self._confidence(dimensions)

        return FailureAttribution(
            generation_id=entry.get("generation_id", "unknown"),
            primary_reason=primary,
            secondary_reasons=secondary,
            action_items=actions,
            confidence=confidence,
            dimensions=dimensions,
            attributed_at=datetime.now(timezone.utc).isoformat(),
        )

    def _rule_based_attribution(self, entry: dict, pattern: dict | None) -> dict:
        """Deterministic checks for common failure causes."""
        dims = {}

        title = entry.get("title", "")
        body = entry.get("body", "")
        subreddit = entry.get("subreddit", "")
        actual_upvotes = entry.get("actual_upvotes", 0)
        subreddit_median = entry.get("subreddit_median", 50)

        # 1. Title hook fit
        title_words = len(title.split())
        if title_words < 5:
            dims["title_hook_fit"] = {
                "score": 20, "issue": "Title too short — lacks hook space"
            }
        elif title_words > 30:
            dims["title_hook_fit"] = {
                "score": 30, "issue": "Title too long — dilutes hook impact"
            }
        else:
            dims["title_hook_fit"] = {"score": 70, "issue": None}

        # 2. Body structure fit
        body_words = len(body.split()) if body else 0
        if body_words < 20:
            dims["body_structure_fit"] = {
                "score": 20, "issue": "Body too short — lacks substance for engagement"
            }
        elif body_words > 1000:
            dims["body_structure_fit"] = {
                "score": 30, "issue": "Body too long — may overwhelm readers"
            }
        else:
            dims["body_structure_fit"] = {"score": 70, "issue": None}

        # 3. Content quality — basic signal from ratio
        upvote_ratio = entry.get("upvote_ratio", 0.0)
        if upvote_ratio > 0 and upvote_ratio < 0.5:
            dims["content_quality"] = {
                "score": 20,
                "issue": f"Low upvote ratio ({upvote_ratio:.0%}) — content likely polarizing or low quality",
            }
        elif upvote_ratio >= 0.7:
            dims["content_quality"] = {"score": 75, "issue": None}
        else:
            dims["content_quality"] = {"score": 50, "issue": "Moderate upvote ratio"}

        # 4. Timing fit — rough heuristic
        dims["timing_fit"] = {"score": 60, "issue": None}

        # 5. Topic relevance
        dims["topic_relevance"] = {"score": 60, "issue": None}

        if pattern:
            pattern_name = pattern.get("name", "")
            pattern_vr = pattern.get("historical_viral_rate", 0)
            if pattern_vr < 20:
                dims["pattern_fit"] = {
                    "score": 25,
                    "issue": f"Pattern '{pattern_name}' has inherently low viral rate ({pattern_vr}%)",
                }

        return dims

    def _llm_attribution(self, entry: dict, pattern: dict | None) -> dict | None:
        """Use LLM for deeper attribution analysis."""
        from ..llm.prompts import FAILURE_ATTRIBUTE_V2

        prompt = FAILURE_ATTRIBUTE_V2.format(
            title=entry.get("title", ""),
            body_excerpt=(entry.get("body", "") or "")[:500],
            subreddit=entry.get("subreddit", ""),
            actual_upvotes=entry.get("actual_upvotes", 0),
            upvote_ratio=entry.get("upvote_ratio", 0.0),
            num_comments=entry.get("num_comments", 0),
            posted_at=entry.get("tracked_at", "unknown"),
            recommended_time="unknown",
            pattern_name=pattern.get("name", "unknown") if pattern else "unknown",
            viral_rate=pattern.get("historical_viral_rate", 0) if pattern else 0,
            avg_upvotes=pattern.get("avg_upvotes", 0) if pattern else 0,
            subreddit_median=entry.get("subreddit_median", 50),
        )

        try:
            result = self._llm.complete(prompt, "")
            return json.loads(result)
        except Exception as e:
            logger.warning("LLM attribution failed: %s", e)
            return None

    @staticmethod
    def _synthesize(dimensions: dict) -> tuple[str, list[str], list[str]]:
        """Synthesize dimension scores into primary reason and action items."""
        issues = [
            (k, v["issue"])
            for k, v in dimensions.items()
            if v.get("issue") and v.get("score", 100) < 50
        ]
        issues.sort(key=lambda x: dimensions[x[0]].get("score", 100))

        primary = issues[0][1] if issues else "No clear failure reason — may be luck/timing"
        secondary = [i[1] for i in issues[1:3]]

        actions = []
        action_map = {
            "title_hook_fit": "Revise title: check hook clarity and word count against pattern",
            "body_structure_fit": "Adjust body length/structure to match pattern recommendations",
            "content_quality": "Improve content depth and authenticity",
            "pattern_fit": "Try a different pattern with higher historical viral rate",
            "timing_fit": "Post at the recommended day/hour for this subreddit",
            "topic_relevance": "Ensure topic tightly aligns with subreddit interests",
        }
        for dim, issue in issues[:3]:
            if dim in action_map:
                actions.append(action_map[dim])

        if not actions:
            actions.append("Review and retry with a different pattern or subreddit")

        return primary, secondary, actions

    @staticmethod
    def _confidence(dimensions: dict) -> float:
        """Calculate overall confidence in the attribution."""
        if not dimensions:
            return 30.0
        scores = [v.get("score", 50) for v in dimensions.values()]
        avg = sum(scores) / len(scores)
        # Higher scores = more clear issues = higher confidence in diagnosis
        # Invert: low dimension score means confident about the problem
        return min(90, max(20, 100 - avg))
