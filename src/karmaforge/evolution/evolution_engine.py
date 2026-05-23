"""Evolution engine — batch feedback processing to update pattern weights."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from . import EvolutionLog
from .failure_attributor import FailureAttributor

logger = logging.getLogger(__name__)

EVOLUTION_THRESHOLD = 50
MAX_CONSECUTIVE_FAILURES = 10
EVOLUTION_LOG_PATH_DEFAULT = Path("data/tracking/evolution_log.md")


class EvolutionEngine:
    """Process feedback data to update pattern effectiveness scores."""

    def __init__(
        self,
        llm_client=None,
        evolution_log_path: str | Path | None = None,
    ) -> None:
        self._attributor = FailureAttributor(llm_client)
        self._evolution_log_path = (
            Path(evolution_log_path) if evolution_log_path else EVOLUTION_LOG_PATH_DEFAULT
        )

    def should_evolve(self, feedback_path: str | Path) -> bool:
        """Check if enough feedback has accumulated for evolution."""
        count = self._count_entries(feedback_path)
        return count >= EVOLUTION_THRESHOLD

    def evolve(
        self,
        feedback_path: str | Path,
        patterns_path: str | Path,
        output_path: str | Path | None = None,
    ) -> EvolutionLog | None:
        """Run one evolution cycle: analyze feedback, update patterns.

        Returns EvolutionLog if changes were made, None otherwise.
        """
        fb_path = Path(feedback_path)
        pat_path = Path(patterns_path)
        out_path = Path(output_path) if output_path else pat_path

        if not fb_path.exists():
            logger.warning("No feedback file at %s", fb_path)
            return None

        entries = self._load_entries(fb_path)
        if len(entries) < EVOLUTION_THRESHOLD:
            logger.info(
                "Only %d entries (threshold: %d). Not evolving.",
                len(entries), EVOLUTION_THRESHOLD,
            )
            return None

        if not pat_path.exists():
            logger.warning("No patterns file at %s", pat_path)
            return None

        with open(pat_path, "r", encoding="utf-8") as f:
            patterns = json.load(f)

        # Attribute failed posts
        attributed = 0
        for entry in entries:
            if entry.get("performance") == "failed" and not entry.get("attribution"):
                pattern = self._find_pattern(patterns, entry.get("pattern_id", ""))
                attribution = self._attributor.attribute(entry, pattern)
                entry["attribution"] = {
                    "primary_reason": attribution.primary_reason,
                    "secondary_reasons": attribution.secondary_reasons,
                    "action_items": attribution.action_items,
                    "confidence": attribution.confidence,
                    "dimensions": attribution.dimensions,
                    "attributed_at": attribution.attributed_at,
                }
                attributed += 1

        if attributed:
            self._rewrite_feedback(fb_path, entries)
            logger.info("Attributed %d failed posts", attributed)

        # Group by pattern_id
        by_pattern: dict[str, list[dict]] = {}
        for entry in entries:
            pid = entry.get("pattern_id", "unknown")
            by_pattern.setdefault(pid, []).append(entry)

        # Compute per-pattern stats
        updates = 0
        inactivations = 0
        changes_log: list[str] = []

        for pattern in patterns:
            pid = pattern.get("pattern_id", "")
            entries_for_pat = by_pattern.get(pid, [])
            if not entries_for_pat:
                continue

            total = len(entries_for_pat)
            viral = sum(1 for e in entries_for_pat if e.get("performance") in ("viral", "super_viral"))
            passing = sum(1 for e in entries_for_pat if e.get("performance") == "passing")
            failed = total - viral - passing

            new_success_rate = round((viral + passing) / total, 4) if total > 0 else 0
            old_rate = pattern.get("success_rate", 0)

            pattern["success_rate"] = new_success_rate
            pattern["feedback_sample_size"] = total
            pattern["last_evaluated_at"] = datetime.now(timezone.utc).isoformat()

            if abs(new_success_rate - old_rate) > 0.05:
                direction = "up" if new_success_rate > old_rate else "down"
                changes_log.append(
                    f"  - `{pattern.get('name', pid)}`: "
                    f"success_rate {old_rate:.2f}→{new_success_rate:.2f} ({direction})"
                )
            updates += 1

            # Check for consecutive failures
            recent = sorted(
                entries_for_pat,
                key=lambda e: e.get("tracked_at", ""),
                reverse=True,
            )
            consecutive_fails = 0
            for e in recent:
                if e.get("performance") == "failed":
                    consecutive_fails += 1
                else:
                    break

            if consecutive_fails >= MAX_CONSECUTIVE_FAILURES:
                pattern["status"] = "inactive"
                changes_log.append(
                    f"  - `{pattern.get('name', pid)}`: MARKED INACTIVE "
                    f"({consecutive_fails} consecutive failures)"
                )
                inactivations += 1

        # Save updated patterns
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(patterns, f, ensure_ascii=False, indent=2)
        logger.info("Saved updated patterns to %s (%d updated, %d inactivated)", out_path, updates, inactivations)

        # Write evolution log
        summary = f"Processed {len(entries)} feedback entries.\n"
        summary += f"Updated {updates} patterns, marked {inactivations} inactive.\n"
        if changes_log:
            summary += "\nChanges:\n" + "\n".join(changes_log)

        log = EvolutionLog(
            run_at=datetime.now(timezone.utc).isoformat(),
            feedback_count=len(entries),
            patterns_updated=updates,
            patterns_marked_inactive=inactivations,
            summary=summary,
        )

        self._write_evolution_log(log)
        return log

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

    @staticmethod
    def _count_entries(path: str | Path) -> int:
        if not Path(path).exists():
            return 0
        count = 0
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count

    @staticmethod
    def _find_pattern(patterns: list[dict], pattern_id: str) -> dict | None:
        for p in patterns:
            if p.get("pattern_id") == pattern_id:
                return p
        return None

    def _rewrite_feedback(self, path: Path, entries: list[dict]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _write_evolution_log(self, log: EvolutionLog) -> None:
        """Append to evolution_log.md."""
        self._evolution_log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = (
            f"## Evolution Run — {log.run_at}\n\n"
            f"- Feedback entries processed: **{log.feedback_count}**\n"
            f"- Patterns updated: **{log.patterns_updated}**\n"
            f"- Patterns marked inactive: **{log.patterns_marked_inactive}**\n"
            f"\n{log.summary}\n\n---\n"
        )
        existing = ""
        if self._evolution_log_path.exists():
            existing = self._evolution_log_path.read_text(encoding="utf-8")
        self._evolution_log_path.write_text(entry + existing, encoding="utf-8")
        logger.info("Evolution log written to %s", self._evolution_log_path)
