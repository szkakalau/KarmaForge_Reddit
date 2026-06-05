"""Evolution engine — batch feedback processing to update pattern weights.

Phase 2 adds: time-decay weighting, subreddit-level performance tracking,
pattern drift detection, and auto-calibration of recommended metrics.
"""

import json
import logging
import math
import os
import tempfile
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import EvolutionLog
from .failure_attributor import FailureAttributor

logger = logging.getLogger(__name__)

EVOLUTION_THRESHOLD = 50
MAX_CONSECUTIVE_FAILURES = 10
EVOLUTION_LOG_PATH_DEFAULT = Path("data/tracking/evolution_log.md")
LOCK_TIMEOUT_SECONDS = 600  # stale lock cleanup after 10 minutes

# Time-decay: half-life in days for feedback weight
HALF_LIFE_DAYS = 90
# Drift detection: if recent (30d) success_rate < overall * (1 - DRIFT_THRESHOLD), flag declining
DRIFT_THRESHOLD = 0.3
DRIFT_WINDOW_DAYS = 30
# Auto-calibration: min successful posts needed to update recommended_metrics
CALIBRATION_MIN_SAMPLES = 15


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
        """Check if enough unprocessed feedback has accumulated for evolution."""
        count = self._count_entries(feedback_path, unprocessed_only=True)
        return count >= EVOLUTION_THRESHOLD

    def evolve(
        self,
        feedback_path: str | Path,
        patterns_path: str | Path,
        output_path: str | Path | None = None,
    ) -> EvolutionLog | None:
        """Run one evolution cycle: analyze feedback, update patterns.

        Returns EvolutionLog if changes were made, None otherwise.
        Uses a lock file to prevent concurrent evolution runs.
        """
        fb_path = Path(feedback_path)
        pat_path = Path(patterns_path)
        out_path = Path(output_path) if output_path else pat_path

        lock_path = fb_path.parent / ".evolution.lock"
        if not self._acquire_lock(lock_path):
            logger.warning("Evolution already in progress (lock held at %s). Skipping.", lock_path)
            return None

        try:
            return self._evolve_impl(fb_path, pat_path, out_path)
        finally:
            self._release_lock(lock_path)

    def _evolve_impl(
        self,
        fb_path: Path,
        pat_path: Path,
        out_path: Path,
    ) -> EvolutionLog | None:
        """Internal evolve implementation — caller must hold the lock."""
        if not fb_path.exists():
            logger.warning("No feedback file at %s", fb_path)
            return None

        # Generate a unique run ID to mark processed entries
        run_id = uuid.uuid4().hex[:12]
        evolved_at = datetime.now(timezone.utc).isoformat()

        # Only load unprocessed entries (Fix 1: prevent infinite reprocessing)
        entries = self._load_entries(fb_path, unprocessed_only=True)
        if len(entries) < EVOLUTION_THRESHOLD:
            logger.info(
                "Only %d unprocessed entries (threshold: %d). Not evolving.",
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

        # Mark all entries as processed with this run ID (Fix 1)
        for entry in entries:
            entry["evolution_run_id"] = run_id
            entry["evolved_at"] = evolved_at

        # Always rewrite feedback to persist run_id marks + attributions
        self._rewrite_feedback(fb_path, entries)
        if attributed:
            logger.info("Attributed %d failed posts", attributed)
        logger.info("Marked %d entries with evolution_run_id=%s", len(entries), run_id)

        # Group by pattern_id
        by_pattern: dict[str, list[dict]] = {}
        for entry in entries:
            pid = entry.get("pattern_id", "unknown")
            by_pattern.setdefault(pid, []).append(entry)

        # Compute per-pattern stats (Phase 2: time-decay + subreddit + drift + calibration)
        now = datetime.now(timezone.utc)
        updates = 0
        inactivations = 0
        changes_log: list[str] = []

        for pattern in patterns:
            pid = pattern.get("pattern_id", "")
            entries_for_pat = by_pattern.get(pid, [])
            if not entries_for_pat:
                continue

            total = len(entries_for_pat)

            # ── Phase 2.1: Time-decayed success rate ──
            time_decayed_rate = self._compute_time_decayed_rate(entries_for_pat, now)
            old_rate = pattern.get("success_rate", 0)

            # ── Phase 2.2: Subreddit-level performance ──
            subreddit_perf = self._compute_subreddit_performance(entries_for_pat, now)
            pattern["subreddit_performance"] = subreddit_perf

            # ── Phase 2.3: Pattern drift detection ──
            drift_status, drift_score = self._detect_drift(entries_for_pat, time_decayed_rate, now)
            pattern["drift_status"] = drift_status
            pattern["drift_score"] = round(drift_score, 4)

            # ── Phase 2.4: Auto-calibrate recommended metrics ──
            self._calibrate_metrics(pattern, entries_for_pat)

            # Update core fields
            pattern["success_rate"] = round(time_decayed_rate, 4)
            pattern["feedback_sample_size"] = total
            pattern["last_evaluated_at"] = now.isoformat()

            # Log significant changes
            if abs(time_decayed_rate - old_rate) > 0.05:
                direction = "up" if time_decayed_rate > old_rate else "down"
                changes_log.append(
                    f"  - `{pattern.get('name', pid)}`: "
                    f"success_rate {old_rate:.2f}→{time_decayed_rate:.2f} ({direction})"
                    f"{' [DRIFTING]' if drift_status == 'declining' else ''}"
                )
            elif drift_status == "declining":
                changes_log.append(
                    f"  - `{pattern.get('name', pid)}`: DRIFT DETECTED "
                    f"(drift_score={drift_score:.3f}, recent rate below threshold)"
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

        # Atomic write: temp file → rename (Fix 2: prevent write-write corruption)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(
            suffix=".json", prefix=".patterns_", dir=str(out_path.parent)
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(patterns, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(out_path))  # atomic on Windows & POSIX
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        logger.info("Saved updated patterns to %s (%d updated, %d inactivated)", out_path, updates, inactivations)

        # Write evolution log
        summary = f"Processed {len(entries)} feedback entries (run_id={run_id}).\n"
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
    def _load_entries(path: Path, unprocessed_only: bool = False) -> list[dict]:
        """Load feedback entries from JSONL.

        Args:
            path: Path to feedback.jsonl.
            unprocessed_only: If True, skip entries already marked with
                ``evolution_run_id`` (prevents reprocessing the same data).
        """
        entries = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if unprocessed_only and entry.get("evolution_run_id"):
                        continue
                    entries.append(entry)
        return entries

    @staticmethod
    def _count_entries(path: str | Path, unprocessed_only: bool = False) -> int:
        """Count entries in feedback file.

        Args:
            path: Path to feedback.jsonl.
            unprocessed_only: If True, only count entries not yet processed
                by an evolution run.
        """
        if not Path(path).exists():
            return 0
        count = 0
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if unprocessed_only:
                    try:
                        entry = json.loads(line)
                        if entry.get("evolution_run_id"):
                            continue
                    except json.JSONDecodeError:
                        continue
                count += 1
        return count

    @staticmethod
    def _find_pattern(patterns: list[dict], pattern_id: str) -> dict | None:
        for p in patterns:
            if p.get("pattern_id") == pattern_id:
                return p
        return None

    # ── Phase 2.1: Time-decay weighting ─────────────────────────

    @staticmethod
    def _compute_time_decayed_rate(entries: list[dict], now: datetime) -> float:
        """Compute success rate with exponential time decay.

        Recent feedback weighs more.  Half-life = HALF_LIFE_DAYS.
        Weight = exp(-λ * days_ago), where λ = ln(2) / half_life.
        """
        if not entries:
            return 0.0

        decay_lambda = math.log(2) / HALF_LIFE_DAYS
        weighted_success = 0.0
        total_weight = 0.0

        for e in entries:
            tracked_str = e.get("tracked_at", "")
            if not tracked_str:
                weight = 1.0
            else:
                try:
                    tracked_dt = datetime.fromisoformat(tracked_str.replace("Z", "+00:00"))
                    # Ensure timezone-aware comparison
                    if tracked_dt.tzinfo is None:
                        tracked_dt = tracked_dt.replace(tzinfo=timezone.utc)
                    if now.tzinfo is None:
                        now = now.replace(tzinfo=timezone.utc)
                    days_ago = (now - tracked_dt).total_seconds() / 86400.0
                    days_ago = max(0, days_ago)
                except (ValueError, TypeError):
                    days_ago = 0
                weight = math.exp(-decay_lambda * days_ago)

            perf = e.get("performance", "failed")
            if perf in ("viral", "super_viral", "passing"):
                weighted_success += weight
            total_weight += weight

        return round(weighted_success / total_weight, 4) if total_weight > 0 else 0.0

    # ── Phase 2.2: Subreddit-level performance ──────────────────

    @staticmethod
    def _compute_subreddit_performance(
        entries: list[dict], now: datetime
    ) -> dict[str, dict]:
        """Compute per-subreddit success rates with time decay.

        Returns:
            {subreddit_name: {success_rate, sample_size, last_updated}}
        """
        by_sub: dict[str, list[dict]] = defaultdict(list)
        for e in entries:
            sub = e.get("subreddit", "").lower()
            if sub:
                by_sub[sub].append(e)

        result = {}
        for sub, sub_entries in by_sub.items():
            decay_lambda = math.log(2) / HALF_LIFE_DAYS
            weighted_success = 0.0
            total_weight = 0.0
            for e in sub_entries:
                tracked_str = e.get("tracked_at", "")
                try:
                    tracked_dt = datetime.fromisoformat(tracked_str.replace("Z", "+00:00"))
                    if tracked_dt.tzinfo is None:
                        tracked_dt = tracked_dt.replace(tzinfo=timezone.utc)
                    if now.tzinfo is None:
                        now = now.replace(tzinfo=timezone.utc)
                    days_ago = max(0, (now - tracked_dt).total_seconds() / 86400.0)
                except (ValueError, TypeError):
                    days_ago = 0
                weight = math.exp(-decay_lambda * days_ago)

                perf = e.get("performance", "failed")
                if perf in ("viral", "super_viral", "passing"):
                    weighted_success += weight
                total_weight += weight

            rate = round(weighted_success / total_weight, 4) if total_weight > 0 else 0.0
            result[sub] = {
                "success_rate": rate,
                "sample_size": len(sub_entries),
                "last_updated": now.isoformat(),
            }

        return result

    # ── Phase 2.3: Pattern drift detection ──────────────────────

    @staticmethod
    def _detect_drift(
        entries: list[dict], overall_rate: float, now: datetime
    ) -> tuple[str, float]:
        """Detect if a pattern's recent performance is declining.

        Compares recent (DRIFT_WINDOW_DAYS) success rate against overall
        time-decayed rate.  If recent rate is significantly lower, flags
        the pattern as 'declining'.

        Returns:
            (drift_status, drift_score) where status is 'stable', 'declining',
            or 'insufficient_data', and score is recent_rate / overall_rate
            (1.0 = no change, < 0.7 = declining).
        """
        if not entries or overall_rate <= 0:
            return "insufficient_data", 1.0

        # Filter to recent entries
        recent_entries = []
        for e in entries:
            tracked_str = e.get("tracked_at", "")
            if not tracked_str:
                continue
            try:
                tracked_dt = datetime.fromisoformat(tracked_str.replace("Z", "+00:00"))
                if tracked_dt.tzinfo is None:
                    tracked_dt = tracked_dt.replace(tzinfo=timezone.utc)
                if now.tzinfo is None:
                    now = now.replace(tzinfo=timezone.utc)
                days_ago = (now - tracked_dt).total_seconds() / 86400.0
                if days_ago <= DRIFT_WINDOW_DAYS:
                    recent_entries.append(e)
            except (ValueError, TypeError):
                continue

        if len(recent_entries) < 5:
            return "insufficient_data", 1.0

        recent_success = sum(
            1 for e in recent_entries
            if e.get("performance") in ("viral", "super_viral", "passing")
        )
        recent_rate = recent_success / len(recent_entries)

        drift_score = recent_rate / overall_rate if overall_rate > 0 else 1.0

        if drift_score < (1.0 - DRIFT_THRESHOLD):
            return "declining", round(drift_score, 4)
        return "stable", round(drift_score, 4)

    # ── Phase 2.4: Auto-calibrate recommended metrics ────────────

    @staticmethod
    def _calibrate_metrics(pattern: dict, entries: list[dict]) -> None:
        """Update recommended title/body word ranges from successful posts.

        Uses the interquartile range (IQR) of successful posts' actual word
        counts to set optimal ranges.  Only updates when enough successful
        samples exist (>= CALIBRATION_MIN_SAMPLES).
        """
        successful = [
            e for e in entries
            if e.get("performance") in ("viral", "super_viral", "passing")
        ]
        if len(successful) < CALIBRATION_MIN_SAMPLES:
            return

        # Title word count calibration
        title_wcs = []
        for e in successful:
            title = e.get("title", "")
            if title:
                title_wcs.append(len(title.split()))

        if len(title_wcs) >= CALIBRATION_MIN_SAMPLES:
            arr = np.array(title_wcs)
            q1 = int(np.percentile(arr, 25))
            q3 = int(np.percentile(arr, 75))
            # Expand by 10% to avoid overfitting
            lower = max(3, int(q1 * 0.9))
            upper = max(lower + 2, int(q3 * 1.1))
            metrics = pattern.setdefault("recommended_metrics", {})
            metrics["title_words"] = [lower, upper]

        # Body word count calibration
        body_wcs = []
        for e in successful:
            body = e.get("body", "")
            if body:
                body_wcs.append(len(body.split()))

        if len(body_wcs) >= CALIBRATION_MIN_SAMPLES:
            arr = np.array(body_wcs)
            q1 = int(np.percentile(arr, 25))
            q3 = int(np.percentile(arr, 75))
            lower = max(0, int(q1 * 0.9))
            upper = max(lower + 10, int(q3 * 1.1))
            metrics = pattern.setdefault("recommended_metrics", {})
            metrics["body_words"] = [lower, upper]

    # ── Helpers ─────────────────────────────────────────────────

    def _rewrite_feedback(self, path: Path, entries: list[dict]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @staticmethod
    def _acquire_lock(lock_path: Path) -> bool:
        """Acquire a file lock to prevent concurrent evolution runs.

        Returns True if lock was acquired, False if another process holds it.
        Cleans up stale locks older than LOCK_TIMEOUT_SECONDS.
        """
        if lock_path.exists():
            try:
                lock_age = time.time() - lock_path.stat().st_mtime
                if lock_age > LOCK_TIMEOUT_SECONDS:
                    logger.warning("Removing stale evolution lock (%.0fs old)", lock_age)
                    lock_path.unlink(missing_ok=True)
                else:
                    return False
            except FileNotFoundError:
                pass  # race between exists() and stat(), retry acquire

        try:
            # Use O_CREAT | O_EXCL for atomic lock creation
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return True
        except FileExistsError:
            return False

    @staticmethod
    def _release_lock(lock_path: Path) -> None:
        """Release the evolution lock file."""
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass

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
