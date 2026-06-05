"""Cross-subreddit transfer learning.

When a subreddit has little or no performance data, this module finds
similar subreddits whose pattern performance can serve as a warm start.

Builds a similarity matrix from pattern performance vectors, then
recommends patterns from the nearest-neighbor subreddit.
"""

import json
import logging
from collections import defaultdict
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Minimum feedback samples before a subreddit's own data takes over
WARM_START_MIN_SAMPLES = 10
# Transfer weight decay: as own data grows, transfer weight → 0
# own_weight = min(1.0, own_samples / WARM_START_DECAY)
WARM_START_DECAY = 30


class SubredditTransfer:
    """Cross-subreddit knowledge transfer for cold-start scenarios."""

    def __init__(self) -> None:
        self._similarity: dict[str, dict[str, float]] = {}
        self._built = False

    # ── Building ─────────────────────────────────────────────────

    def build_similarity(self, patterns: list[dict]) -> dict[str, dict[str, float]]:
        """Build subreddit similarity matrix from pattern performance vectors.

        Each subreddit is represented as a vector of per-pattern success_rates.
        Cosine similarity is computed between all subreddit pairs.

        Returns:
            {subreddit: {similar_subreddit: similarity_score}}
        """
        # Collect all subreddits and their pattern performance vectors
        sub_vectors: dict[str, dict[str, float]] = defaultdict(dict)
        all_pids = {p.get("pattern_id", "") for p in patterns}

        for pattern in patterns:
            pid = pattern.get("pattern_id", "")
            sub_perf = pattern.get("subreddit_performance", {})
            for sub, perf in sub_perf.items():
                sub_vectors[sub][pid] = perf.get("success_rate", 0.0)

        if len(sub_vectors) < 2:
            logger.info("Not enough subreddits for transfer learning (need >= 2)")
            return {}

        # Build vectors as numpy arrays
        subs = sorted(sub_vectors.keys())
        n = len(subs)
        pid_list = sorted(all_pids)

        matrix = np.zeros((n, len(pid_list)))
        for i, sub in enumerate(subs):
            for j, pid in enumerate(pid_list):
                matrix[i, j] = sub_vectors[sub].get(pid, 0.0)

        # Cosine similarity
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0  # avoid division by zero
        normalized = matrix / norms
        sim_matrix = normalized @ normalized.T

        # Build result dict
        self._similarity = {}
        for i, sub_i in enumerate(subs):
            neighbors = {}
            for j, sub_j in enumerate(subs):
                if i == j:
                    continue
                score = float(sim_matrix[i, j])
                if score > 0.1:  # minimum similarity threshold
                    neighbors[sub_j] = round(score, 4)
            # Sort by similarity descending
            self._similarity[sub_i] = dict(
                sorted(neighbors.items(), key=lambda x: x[1], reverse=True)
            )

        self._built = True
        logger.info(
            "Transfer learning: built similarity for %d subreddits", len(self._similarity),
        )
        return self._similarity

    # ── Querying ─────────────────────────────────────────────────

    def get_similar(
        self, subreddit: str, top_k: int = 3
    ) -> list[tuple[str, float]]:
        """Get the most similar subreddits with known performance data."""
        if not self._built:
            return []
        neighbors = self._similarity.get(subreddit.lower(), {})
        return list(neighbors.items())[:top_k]

    def warm_start_patterns(
        self,
        target_subreddit: str,
        patterns: list[dict],
        top_k: int = 3,
    ) -> list[dict]:
        """Recommend patterns for a subreddit with little to no own data.

        Uses the most similar subreddit's pattern performance as a proxy.
        Falls back to global historical_viral_rate if no similar subreddits exist.

        Returns:
            Patterns sorted by transferred relevance (best first).
        """
        # Check if target has enough own data
        own_samples = self._count_own_samples(target_subreddit, patterns)

        if own_samples >= WARM_START_MIN_SAMPLES:
            # Sufficient own data — use transfer as tiebreaker, not primary
            logger.debug(
                "r/%s has %d own samples, using transfer as tiebreaker",
                target_subreddit, own_samples,
            )
            return patterns

        # Find best source subreddit
        similar = self.get_similar(target_subreddit, top_k=1)
        if not similar:
            logger.info("No similar subreddit for r/%s, using global ranking", target_subreddit)
            return sorted(
                patterns,
                key=lambda p: p.get("historical_viral_rate", 0),
                reverse=True,
            )

        source_sub, similarity = similar[0]
        logger.info(
            "Transfer: r/%s → r/%s (similarity=%.3f, own_samples=%d)",
            source_sub, target_subreddit, similarity, own_samples,
        )

        # Score patterns by source subreddit's performance
        scored = []
        for p in patterns:
            sub_perf = p.get("subreddit_performance", {})
            source_data = sub_perf.get(source_sub, {})
            transfer_rate = source_data.get("success_rate", 0.0)
            source_samples = source_data.get("sample_size", 0)

            # Blend: transfer_rate weighted by source confidence × similarity
            global_rate = p.get("historical_viral_rate", 0.0)
            success_rate = p.get("success_rate", global_rate)

            # Final score: weighted mix with transfer component
            transfer_weight = similarity * min(1.0, source_samples / 10)
            blended = (
                (1 - transfer_weight) * (0.6 * global_rate + 0.4 * success_rate)
                + transfer_weight * transfer_rate
            )

            scored.append((p, blended))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [p for p, _ in scored]

    def transfer_weight(self, subreddit: str, patterns: list[dict]) -> float:
        """How much should we rely on transfer vs own data? 0.0–1.0.

        1.0 = fully rely on transfer (no own data).
        0.0 = fully rely on own data.
        """
        own = self._count_own_samples(subreddit, patterns)
        if own >= WARM_START_DECAY:
            return 0.0
        return 1.0 - (own / WARM_START_DECAY)

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _count_own_samples(subreddit: str, patterns: list[dict]) -> int:
        """Count total feedback samples for a subreddit across all patterns."""
        sub = subreddit.lower()
        total = 0
        for p in patterns:
            sub_perf = p.get("subreddit_performance", {})
            total += sub_perf.get(sub, {}).get("sample_size", 0)
        return total
