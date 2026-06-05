"""Auto-evolution trigger — check and run evolution after tracking.

Hooks into the PostTracker flow to automatically trigger pattern
evolution when enough unprocessed feedback has accumulated.
"""

import logging
from pathlib import Path

from ..evolution.evolution_engine import EvolutionEngine, EVOLUTION_THRESHOLD

logger = logging.getLogger(__name__)

DEFAULT_FEEDBACK_PATH = Path("data/tracking/feedback.jsonl")
DEFAULT_PATTERNS_PATH = Path("data/patterns/patterns.json")


class AutoEvolver:
    """Checks whether evolution should run and triggers it."""

    def __init__(
        self,
        llm_client=None,
        feedback_path: str | Path | None = None,
        patterns_path: str | Path | None = None,
    ) -> None:
        self._engine = EvolutionEngine(llm_client=llm_client)
        self._feedback_path = Path(feedback_path) if feedback_path else DEFAULT_FEEDBACK_PATH
        self._patterns_path = Path(patterns_path) if patterns_path else DEFAULT_PATTERNS_PATH

    def check_and_evolve(self, force: bool = False) -> dict | None:
        """Check if enough unprocessed feedback exists and run evolution.

        Args:
            force: If True, run even below threshold (useful for testing).

        Returns:
            Dict with evolution result summary, or None if skipped.
        """
        if not self._feedback_path.exists():
            logger.info("No feedback file at %s, skipping evolution", self._feedback_path)
            return None

        if not self._patterns_path.exists():
            logger.warning("No patterns file at %s, skipping evolution", self._patterns_path)
            return None

        if not force and not self._engine.should_evolve(self._feedback_path):
            count = self._engine._count_entries(self._feedback_path, unprocessed_only=True)
            logger.info(
                "Not enough unprocessed feedback (%d/%d), skipping evolution",
                count, EVOLUTION_THRESHOLD,
            )
            return None

        logger.info("Triggering auto-evolution...")
        log = self._engine.evolve(
            feedback_path=self._feedback_path,
            patterns_path=self._patterns_path,
            output_path=self._patterns_path,
        )

        if log is None:
            return {"evolved": False, "reason": "evolution returned no changes"}

        return {
            "evolved": True,
            "feedback_processed": log.feedback_count,
            "patterns_updated": log.patterns_updated,
            "patterns_inactivated": log.patterns_marked_inactive,
            "run_at": log.run_at,
        }

    @property
    def threshold(self) -> int:
        return EVOLUTION_THRESHOLD

    def count_unprocessed(self) -> int:
        return self._engine._count_entries(self._feedback_path, unprocessed_only=True)
