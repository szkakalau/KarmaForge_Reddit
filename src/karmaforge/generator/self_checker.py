"""Quality self-check for generated posts — deterministic rules only."""

import json
import logging
from pathlib import Path

from ..analyzer.analysis_utils import readability_scores
from . import SelfCheckReport

logger = logging.getLogger(__name__)


class SelfChecker:
    """Validate generated content against known patterns and anti-patterns."""

    def __init__(self, anti_patterns_path: str | Path | None = None) -> None:
        self._anti_patterns: list[dict] = []
        if anti_patterns_path:
            self._load_anti_patterns(anti_patterns_path)

    def _load_anti_patterns(self, path: str | Path) -> None:
        ap_path = Path(path)
        if ap_path.exists():
            with open(ap_path, "r", encoding="utf-8") as f:
                self._anti_patterns = json.load(f)

    def check(
        self, title: str, body: str, pattern: dict, subreddit: str
    ) -> SelfCheckReport:
        """Run all checks and return a report."""
        dimensions: dict = {}
        suggestions: list[str] = []

        # 1. Title length check
        title_words = len(title.split())
        title_range = pattern.get("recommended_metrics", {}).get("title_words", [5, 25])
        if title_range[0] <= title_words <= title_range[1]:
            dimensions["title_length"] = {"score": 100, "status": "ok"}
        elif abs(title_words - title_range[0]) <= 3 or abs(title_words - title_range[1]) <= 3:
            dimensions["title_length"] = {"score": 70, "status": "warn"}
            suggestions.append(f"Title is {title_words} words (target: {title_range[0]}-{title_range[1]})")
        else:
            dimensions["title_length"] = {"score": 30, "status": "fail"}
            suggestions.append(f"Title is {title_words} words, outside target {title_range[0]}-{title_range[1]}")

        # 2. Body length check (skip for no-body patterns)
        body_words = len(body.split()) if body else 0
        body_range = pattern.get("recommended_metrics", {}).get("body_words", [50, 600])
        if body_range[1] <= 1 and body_words <= 1:
            dimensions["body_length"] = {"score": 100, "status": "ok"}
        elif body_range[0] <= body_words <= body_range[1]:
            dimensions["body_length"] = {"score": 100, "status": "ok"}
        elif body_words < body_range[0] and body_words > 0:
            dimensions["body_length"] = {"score": 50, "status": "warn"}
            suggestions.append(f"Body is {body_words} words (target: {body_range[0]}-{body_range[1]})")
        elif body_words == 0:
            dimensions["body_length"] = {"score": 100, "status": "ok"}  # intentional
        else:
            dimensions["body_length"] = {"score": 40, "status": "warn"}
            suggestions.append(f"Body is {body_words} words, above target {body_range[0]}-{body_range[1]}")

        # 3. Readability (if body present)
        if body and len(body.split()) >= 20:
            try:
                scores = readability_scores(body)
                fre = scores.get("flesch_reading_ease", 70)
                if 50 <= fre <= 85:
                    dimensions["readability"] = {"score": 100, "status": "ok"}
                elif 40 <= fre <= 90:
                    dimensions["readability"] = {"score": 70, "status": "warn"}
                    suggestions.append(f"Readability score {fre:.0f} (target: 50-85)")
                else:
                    dimensions["readability"] = {"score": 40, "status": "warn"}
                    suggestions.append(f"Readability score {fre:.0f} is outside comfortable range")
            except Exception:
                dimensions["readability"] = {"score": 50, "status": "warn"}
        else:
            dimensions["readability"] = {"score": 100, "status": "ok"}

        # 4. Hook presence check
        expected_hook = pattern.get("hook_type", "")
        if expected_hook and body:
            hook_signals = self._hook_signals(expected_hook)
            hook_score = self._check_hook_presence(title, body, hook_signals)
            dimensions["hook_presence"] = {"score": hook_score, "status": "ok" if hook_score >= 50 else "warn"}
            if hook_score < 50:
                suggestions.append(f"Hook type '{expected_hook}' not clearly present")
        else:
            dimensions["hook_presence"] = {"score": 80, "status": "ok"}

        # 5. Anti-pattern check
        anti_triggers: list[str] = []
        is_no_body_pattern = body_range[1] <= 1
        for ap in self._anti_patterns:
            if self._matches_anti_pattern(title, body, ap, is_no_body_pattern):
                anti_triggers.append(ap.get("name", ap.get("pattern_id", "unknown")))
                suggestions.append(f"Triggered anti-pattern: {ap.get('name', '')} — {ap.get('why_it_fails', '')}")

        ap_score = 100 if not anti_triggers else max(0, 100 - len(anti_triggers) * 30)
        dimensions["anti_patterns"] = {
            "score": ap_score,
            "status": "ok" if not anti_triggers else "fail",
            "triggered": anti_triggers,
        }

        # Aggregate
        dimension_scores = [d["score"] for d in dimensions.values()]
        avg_score = sum(dimension_scores) / len(dimension_scores) if dimension_scores else 0
        passed = all(
            d["status"] != "fail" for d in dimensions.values()
        )

        return SelfCheckReport(
            passed=passed,
            dimensions=dimensions,
            suggestions=suggestions,
        )

    def _check_title(self, title: str, expected_hook_type: str) -> dict:
        """Quick title-only validation. Returns dict compatible with web UI."""
        title_words = len(title.split())

        # Word count score
        if 5 <= title_words <= 25:
            wc_score = 100
        elif 3 <= title_words <= 30:
            wc_score = 70
        else:
            wc_score = 30

        # Hook presence score (check title text against hook signals)
        signals = self._hook_signals(expected_hook_type)
        hook_score = self._check_hook_presence(title, "", signals)

        # Anti-pattern check (title only)
        anti_triggers = []
        for ap in self._anti_patterns:
            ap_id = ap.get("pattern_id", "")
            if ap_id == "anti_very_short_title" and title_words < 5:
                anti_triggers.append(ap.get("name", ap_id))
            elif ap_id == "anti_very_long_title" and title_words > 30:
                anti_triggers.append(ap.get("name", ap_id))
            elif ap_id == "anti_generic_low_engagement":
                generic = ["just wanted to say", "what do you think", "anyone else"]
                if any(m in title.lower() for m in generic):
                    anti_triggers.append(ap.get("name", ap_id))

        anti_score = 100 if not anti_triggers else max(0, 100 - len(anti_triggers) * 30)

        overall = (wc_score * 0.3 + hook_score * 0.4 + anti_score * 0.3)

        return {
            "overall_score": round(overall, 1),
            "word_count": title_words,
            "hook_clarity": hook_score,
            "anti_patterns_triggered": anti_triggers,
            "suggestion": "" if overall >= 60 else "Title may need improvement",
        }

    @staticmethod
    def _hook_signals(hook_type: str) -> list[str]:
        """Words/phrases that signal each hook type."""
        return {
            "tutorial_howto": ["how to", "guide", "step", "learn", "tutorial"],
            "story_opener": ["i ", "my ", "journey", "experience", "learned", "year"],
            "resource_share": ["i built", "i made", "i created", "tool", "app", "resource", "share"],
            "curious_question": ["?", "why ", "how does", "anyone", "question"],
            "counterintuitive_discovery": ["discovered", "unexpected", "changed", "surprising", "found"],
            "controversial_opinion": ["unpopular", "opinion", "controversial", "unlike"],
            "pain_point": ["problem", "struggle", "frustration", "hard", "difficult", "nobody"],
            "comparison_analysis": ["vs", "versus", "compared", "better", "worse", "differ"],
            "identity_label": ["as a", "as an", "developer", "engineer", "founder"],
            "number_shock": [str(n) for n in range(1, 100)] + ["percent", "%"],
        }.get(hook_type, [])

    @staticmethod
    def _check_hook_presence(title: str, body: str, signals: list[str]) -> float:
        """Score 0-100 whether hook signals are present."""
        text = (title + " " + body[:200]).lower()
        hits = sum(1 for s in signals if s.lower() in text)
        if hits >= 3:
            return 100
        elif hits >= 1:
            return 60
        return 25

    @staticmethod
    def _matches_anti_pattern(title: str, body: str, ap: dict, is_no_body: bool = False) -> bool:
        """Check if content matches an anti-pattern."""
        ap_id = ap.get("pattern_id", "")

        if ap_id == "anti_very_short_title":
            return len(title.split()) < 5
        if ap_id == "anti_very_long_title":
            return len(title.split()) > 30
        if ap_id == "anti_no_body_text":
            if is_no_body:
                return False  # no-body patterns are intentional
            return len(body.strip()) < 10 if body else True
        if ap_id == "anti_generic_low_engagement":
            generic_markers = ["just wanted to say", "what do you think", "anyone else"]
            return any(m in (title + body).lower() for m in generic_markers) and len(body.split()) < 50

        return False
