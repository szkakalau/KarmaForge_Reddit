"""Failure attributor — diagnose why a generated post underperformed."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from . import FailureAttribution

logger = logging.getLogger(__name__)

# Weight of each dimension in the composite score
DIMENSION_WEIGHTS = {
    "标题钩子适配": 0.30,
    "正文结构适配": 0.25,
    "发布时间适配": 0.15,
    "主题相关度": 0.15,
    "内容质量": 0.15,
}


class FailureAttributor:
    """Analyze why a post underperformed using deterministic rules + optional LLM."""

    def __init__(self, llm_client=None) -> None:
        self._llm = llm_client

    def attribute(self, entry: dict, pattern: dict | None = None) -> FailureAttribution:
        """Run attribution analysis on a failed feedback entry."""
        dimensions = self._rule_based_attribution(entry, pattern)

        llm_result = None
        if self._llm:
            llm_result = self._llm_attribution(entry, pattern)

        primary, secondary, actions = self._synthesize(dimensions, llm_result)
        confidence = llm_result.get("confidence", self._confidence(dimensions)) if llm_result else self._confidence(dimensions)

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

        # 1. 标题钩子适配度
        title_words = len(title.split())
        if title_words < 5:
            dims["标题钩子适配"] = {
                "score": 20, "issue": "标题过短 — 缺少钩子发挥空间"
            }
        elif title_words > 30:
            dims["标题钩子适配"] = {
                "score": 30, "issue": "标题过长 — 分散读者注意力，削弱钩子效果"
            }
        else:
            dims["标题钩子适配"] = {"score": 70, "issue": None}

        # 2. 正文结构适配度
        body_words = len(body.split()) if body else 0
        if body_words < 20:
            dims["正文结构适配"] = {
                "score": 20, "issue": "正文过短 — 缺乏实质性内容，难以引发讨论"
            }
        elif body_words > 1000:
            dims["正文结构适配"] = {
                "score": 30, "issue": "正文过长 — 可能让读者失去耐心"
            }
        else:
            dims["正文结构适配"] = {"score": 70, "issue": None}

        # 3. 内容质量 — 基于 upvote ratio
        upvote_ratio = entry.get("upvote_ratio", 0.0)
        if upvote_ratio > 0 and upvote_ratio < 0.5:
            dims["内容质量"] = {
                "score": 20,
                "issue": f"赞成率过低 ({upvote_ratio:.0%}) — 内容可能引发争议或质量不佳",
            }
        elif upvote_ratio >= 0.7:
            dims["内容质量"] = {"score": 75, "issue": None}
        else:
            dims["内容质量"] = {"score": 50, "issue": "赞成率一般"}

        # 4. 发布时间适配度
        dims["发布时间适配"] = {"score": 60, "issue": None}

        # 5. 主题相关度
        dims["主题相关度"] = {"score": 60, "issue": None}

        if pattern:
            pattern_name = pattern.get("name", "")
            pattern_vr = pattern.get("historical_viral_rate", 0)
            if pattern_vr < 20:
                dims["模式匹配度"] = {
                    "score": 25,
                    "issue": f"模式「{pattern_name}」本身爆款率较低 ({pattern_vr}%)",
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
            return _parse_llm_json(result)
        except Exception as e:
            logger.warning("LLM attribution failed: %s", e)
            return None

    @staticmethod
    def _contains_chinese(text: str) -> bool:
        """Check if text contains at least one Chinese character."""
        return any('一' <= c <= '鿿' for c in text)

    @staticmethod
    def _synthesize(dimensions: dict, llm_result: dict | None = None) -> tuple[str, list[str], list[str]]:
        """Synthesize dimension scores into primary reason and action items.

        If llm_result is available and in Chinese, use its narrative fields directly.
        Falls back to rule-based when LLM returns English.
        """
        if llm_result:
            primary = llm_result.get("primary_reason", "")
            # Only use LLM output if it's in Chinese; otherwise fall back to rules
            if primary and FailureAttributor._contains_chinese(primary):
                secondary = llm_result.get("secondary_reasons", [])
                actions = llm_result.get("action_items", [])
                return primary, secondary[:2] if secondary else [], actions[:3] if actions else []

        issues = [
            (k, v["issue"])
            for k, v in dimensions.items()
            if isinstance(v, dict) and v.get("issue") and v.get("score", 100) < 50
        ]
        issues.sort(key=lambda x: dimensions[x[0]].get("score", 100))

        primary = issues[0][1] if issues else "未发现明显失败原因 — 可能是运气或时机问题"
        secondary = [i[1] for i in issues[1:3]]

        actions = []
        action_map = {
            "标题钩子适配": "修改标题：检查钩子类型是否明确，字数是否在推荐范围",
            "正文结构适配": "调整正文长度和结构，确保符合模式推荐格式",
            "内容质量": "提升内容深度和真实感，加入具体细节或个人经历",
            "模式匹配度": "换一个爆款率更高的模式重试",
            "发布时间适配": "在该 subreddit 推荐的日期/时段发帖",
            "主题相关度": "确保主题与 subreddit 受众兴趣高度匹配",
        }
        for dim, issue in issues[:3]:
            if dim in action_map:
                actions.append(action_map[dim])

        if not actions:
            actions.append("换一个模式或 subreddit 重试")

        return primary, secondary, actions

    @staticmethod
    def _confidence(dimensions: dict) -> float:
        """Calculate overall confidence in the attribution."""
        if not dimensions:
            return 30.0
        scores = [v.get("score", 50) for v in dimensions.values() if isinstance(v, dict)]
        avg = sum(scores) / len(scores)
        # Higher scores = more clear issues = higher confidence in diagnosis
        # Invert: low dimension score means confident about the problem
        return min(90, max(20, 100 - avg))


def _parse_llm_json(raw: str) -> dict:
    """Extract JSON from LLM output, handling markdown fences and extra text."""
    import re

    cleaned = raw.strip()

    # Try direct parse first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try extracting from ```json ... ``` or ``` ... ``` fences
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding the outermost JSON object
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM response: {raw[:200]}")
