"""Pattern mining engine — discover new viral patterns from feedback data.

Uses statistical tests (chi-square / Fisher's exact) to identify
significant (hook_type × narrative_mode × tier) combinations that
are not yet captured by existing patterns.

Candidate patterns start with status="candidate" and are promoted to
active after accumulating enough successful feedback.
"""

import json
import logging
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats as scipy_stats

from ..analyzer.analysis_utils import (
    batch_classify_heuristic,
    HOOK_KEYWORDS,
    HOOK_CATEGORIES,
)

logger = logging.getLogger(__name__)

# Significance threshold for new pattern discovery
P_VALUE_THRESHOLD = 0.05
# Minimum samples per combination to consider it
MIN_COMBO_SAMPLES = 10
# Minimum viral rate to consider a combination promising
MIN_VIRAL_RATE = 0.30
# Feedback samples needed to promote candidate → active
PROMOTION_SAMPLES = 30
PROMOTION_MIN_RATE = 0.30


class PatternMiner:
    """Discover new viral patterns from feedback data using statistical tests.

    A "pattern" is a (hook_type × narrative_mode × tier) combination
    that shows statistically significant above-chance viral rates.
    """

    # Narrative mode classification (mirrors ml_validator.py)
    _NARRATIVE_KEYWORDS = [
        (["step 1", "how to", "tutorial", "guide", "here's how"], "tutorial_howto"),
        (["i think", "in my opinion", "unpopular", "should be"], "opinion_argument"),
        (["i built", "i made", "i created", "check out my", "github.com"], "resource_showcase"),
        (["i ", "my ", "me ", "we "], "story_personal"),
    ]

    def __init__(self, p_threshold: float = P_VALUE_THRESHOLD) -> None:
        self._p_threshold = p_threshold

    # ── Main API ─────────────────────────────────────────────────

    def mine(
        self,
        feedback_path: str | Path,
        existing_patterns: list[dict],
    ) -> list[dict]:
        """Discover candidate patterns from feedback data.

        Returns a list of new candidate pattern dicts ready to be
        appended to patterns.json.
        """
        fb_path = Path(feedback_path)
        if not fb_path.exists():
            logger.warning("Feedback file not found: %s", fb_path)
            return []

        entries = self._load_entries(fb_path)
        if len(entries) < 50:
            logger.info("Need >= 50 feedback entries for mining (got %d)", len(entries))
            return []

        # Classify each entry's hook_type and narrative_mode
        for e in entries:
            e["_hook"] = self._classify_hook(e.get("title", ""))
            e["_narrative"] = self._classify_narrative(e.get("body", ""))
            e["_tier"] = self._infer_tier(e.get("subreddit", ""))

        # Cross-tabulate: (hook × narrative × tier) → performance
        combo_stats = self._cross_tabulate(entries)

        # Filter: significant + high enough viral rate + not existing
        existing_ids = {p.get("pattern_id", "") for p in existing_patterns}
        existing_combos = {
            (p.get("hook_type", ""), p.get("narrative_mode", ""), self._dominant_tier(p))
            for p in existing_patterns
        }

        candidates = []
        for combo, stats in combo_stats.items():
            hook, narrative, tier = combo

            # Skip if already covered by existing pattern
            if combo in existing_combos:
                continue
            # Skip combos too similar to existing (same hook+narrative, different tier)
            if any(
                hook == eh and narrative == en
                for eh, en, _ in existing_combos
            ):
                continue

            n_total = stats["total"]
            n_success = stats["success"]
            if n_total < MIN_COMBO_SAMPLES:
                continue

            viral_rate = n_success / n_total
            if viral_rate < MIN_VIRAL_RATE:
                continue

            # Statistical test: is this rate significantly above baseline?
            baseline_rate = self._baseline_rate(entries)
            p_value = self._fisher_test(n_success, n_total, baseline_rate)

            if p_value >= self._p_threshold:
                continue

            # Create candidate pattern
            pattern_id = f"candidate_{hook}_{narrative}_{tier}"
            candidate = {
                "pattern_id": pattern_id,
                "name": f"Candidate: {hook} + {narrative} ({tier})",
                "description": f"Auto-discovered: {hook} × {narrative} in {tier}",
                "applicable_subreddits": stats.get("subreddits", []),
                "title_template": "",
                "body_structure_template": "",
                "historical_viral_rate": round(viral_rate, 4),
                "confidence_interval": self._binomial_ci(n_success, n_total),
                "avg_upvotes": round(stats.get("avg_upvotes", 0), 1),
                "p_value": round(p_value, 6),
                "exemplar_posts": stats.get("exemplars", [])[:5],
                "hook_type": hook,
                "narrative_mode": narrative,
                "recommended_metrics": self._estimate_metrics(stats.get("entries", [])),
                "tier_effectiveness": {tier: viral_rate},
                "sample_size": n_total,
                "status": "candidate",
                "mined_at": stats.get("mined_at", ""),
            }
            candidates.append(candidate)
            logger.info(
                "Mined candidate: %s (n=%d, rate=%.2f, p=%.4f)",
                pattern_id, n_total, viral_rate, p_value,
            )

        # Sort by viral_rate descending
        candidates.sort(key=lambda c: c["historical_viral_rate"], reverse=True)
        logger.info("Pattern mining: discovered %d candidates", len(candidates))
        return candidates

    def promote_candidates(
        self,
        patterns: list[dict],
        feedback_path: str | Path,
    ) -> tuple[list[dict], int]:
        """Promote qualified candidate patterns to active status.

        A candidate is promoted when it has >= PROMOTION_SAMPLES
        feedback entries and success_rate >= PROMOTION_MIN_RATE.

        Returns:
            (updated_patterns, number_promoted)
        """
        fb_path = Path(feedback_path)
        entries = self._load_entries(fb_path) if fb_path.exists() else []

        # Count feedback per candidate pattern
        candidate_stats: dict[str, dict] = defaultdict(
            lambda: {"total": 0, "success": 0}
        )
        for e in entries:
            pid = e.get("pattern_id", "")
            if pid.startswith("candidate_"):
                stats = candidate_stats[pid]
                stats["total"] += 1
                if e.get("performance") in ("viral", "super_viral", "passing"):
                    stats["success"] += 1

        promoted = 0
        for pattern in patterns:
            if pattern.get("status") != "candidate":
                continue
            pid = pattern.get("pattern_id", "")
            stats = candidate_stats.get(pid, {"total": 0, "success": 0})

            if stats["total"] < PROMOTION_SAMPLES:
                continue

            success_rate = stats["success"] / stats["total"]
            if success_rate >= PROMOTION_MIN_RATE:
                pattern["status"] = "active"
                pattern["success_rate"] = round(success_rate, 4)
                pattern["feedback_sample_size"] = stats["total"]
                promoted += 1
                logger.info(
                    "Promoted %s → active (n=%d, rate=%.2f)",
                    pid, stats["total"], success_rate,
                )

        return patterns, promoted

    # ── Internals ────────────────────────────────────────────────

    def _cross_tabulate(self, entries: list[dict]) -> dict:
        """Build contingency table for all (hook × narrative × tier) combos."""
        from datetime import datetime, timezone

        combos: dict = defaultdict(lambda: {
            "total": 0, "success": 0,
            "subreddits": [],
            "avg_upvotes": 0.0,
            "upvote_sum": 0.0,
            "exemplars": [],
            "entries": [],
        })

        now = datetime.now(timezone.utc).isoformat()

        for e in entries:
            hook = e.get("_hook", "unknown")
            narrative = e.get("_narrative", "unknown")
            tier = e.get("_tier", "t2")
            combo = (hook, narrative, tier)

            stats = combos[combo]
            stats["total"] += 1
            perf = e.get("performance", "failed")
            if perf in ("viral", "super_viral", "passing"):
                stats["success"] += 1

            upvotes = e.get("actual_upvotes", 0)
            stats["upvote_sum"] += upvotes

            sub = e.get("subreddit", "")
            if sub and sub not in stats["subreddits"]:
                stats["subreddits"].append(sub)

            if perf in ("viral", "super_viral"):
                gen_id = e.get("generation_id", "")
                if gen_id and gen_id not in stats["exemplars"]:
                    stats["exemplars"].append(gen_id)

            stats["entries"].append(e)
            stats["mined_at"] = now

        # Compute averages
        for stats in combos.values():
            if stats["total"] > 0:
                stats["avg_upvotes"] = stats["upvote_sum"] / stats["total"]

        return dict(combos)

    @classmethod
    def _classify_hook(cls, title: str) -> str:
        """Classify a single title's hook type."""
        if not title:
            return "curious_question"
        result = batch_classify_heuristic(
            [title], list(HOOK_KEYWORDS.keys()), HOOK_KEYWORDS
        )
        return result[0] if result else "curious_question"

    @classmethod
    def _classify_narrative(cls, body: str) -> str:
        """Classify body narrative mode."""
        if not body or len(body) < 20:
            return "no_body"
        b_lower = body.lower()
        for keywords, label in cls._NARRATIVE_KEYWORDS:
            if any(kw in b_lower for kw in keywords):
                if label == "story_personal" and len(b_lower) <= 200:
                    continue
                return label
        if body.strip().endswith("?") or "anyone else" in b_lower:
            return "question_discussion"
        return "opinion_argument"

    @staticmethod
    def _infer_tier(subreddit: str) -> str:
        """Infer tier from subreddit name."""
        t1 = {"askreddit", "showerthoughts", "todayilearned", "worldnews",
              "funny", "pics", "gaming", "videos", "music", "movies",
              "aww", "gifs", "news", "sports", "television"}
        t3 = {"saas", "kubernetes", "digitalnomad", "selfhosted",
              "indiehackers", "startups", "sideproject", "solopreneur"}
        sub = subreddit.lower()
        if sub in t1:
            return "t1"
        if sub in t3:
            return "t3"
        return "t2"

    @staticmethod
    def _dominant_tier(pattern: dict) -> str:
        """Get the dominant tier from a pattern's tier_effectiveness."""
        tier_eff = pattern.get("tier_effectiveness", {})
        if not tier_eff:
            return "t2"
        return max(tier_eff, key=tier_eff.get)

    @staticmethod
    def _baseline_rate(entries: list[dict]) -> float:
        """Global success rate across all entries."""
        if not entries:
            return 0.5
        success = sum(
            1 for e in entries
            if e.get("performance") in ("viral", "super_viral", "passing")
        )
        return success / len(entries)

    @staticmethod
    def _fisher_test(n_success: int, n_total: int, baseline: float) -> float:
        """Fisher's exact test for combo vs baseline.

        Builds a 2×2 table:
                          success  fail
        combo              a        b
        rest (baseline)    c        d
        """
        a = n_success
        b = n_total - n_success
        # Estimate rest from baseline
        rest_total = max(100, n_total * 10)
        c = int(baseline * rest_total)
        d = rest_total - c

        table = [[a, b], [c, d]]
        try:
            _, p_value = scipy_stats.fisher_exact(table, alternative="greater")
            return float(p_value)
        except Exception:
            return 1.0

    @staticmethod
    def _binomial_ci(success: int, total: int) -> list[float]:
        """Wilson score confidence interval for a proportion."""
        if total == 0:
            return [0.0, 0.0]
        z = 1.96
        p = success / total
        denom = 1 + z * z / total
        center = (p + z * z / (2 * total)) / denom
        margin = z * np.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
        return [round(max(0, center - margin), 4), round(min(1, center + margin), 4)]

    @staticmethod
    def _estimate_metrics(entries: list[dict]) -> dict:
        """Estimate recommended title/body word ranges from entries."""
        title_wcs = []
        body_wcs = []
        for e in entries:
            title = e.get("title", "")
            body = e.get("body", "")
            if title:
                title_wcs.append(len(title.split()))
            if body:
                body_wcs.append(len(body.split()))

        metrics = {}
        if len(title_wcs) >= 5:
            arr = np.array(title_wcs)
            metrics["title_words"] = [
                max(3, int(np.percentile(arr, 25))),
                max(5, int(np.percentile(arr, 75))),
            ]
        else:
            metrics["title_words"] = [8, 22]

        if len(body_wcs) >= 5:
            arr = np.array(body_wcs)
            metrics["body_words"] = [
                max(0, int(np.percentile(arr, 25))),
                max(10, int(np.percentile(arr, 75))),
            ]
        else:
            metrics["body_words"] = [50, 600]

        return metrics

    @staticmethod
    def _load_entries(path: Path) -> list[dict]:
        entries = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return entries
