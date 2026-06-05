"""ML-based title ranking model for candidate selection.

Trains a lightweight classifier on feedback data using only features
available at generation time (title characteristics + pattern metadata
+ subreddit tier).  Deployed as a re-ranker after heuristic scoring.

Unlike the full MLValidator (42 features), this model uses 16 features
that are all computable from a candidate title + pattern + subreddit
without needing body text, VADER sentiment, or time-of-posting.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

import numpy as np

from . import CandidateTitle

logger = logging.getLogger(__name__)

# ── Hook / narrative index mappings (must match ml_validator.py) ──
_HOOK_INDEX = {
    "tutorial_howto": 0, "story_opener": 1, "resource_share": 2,
    "curious_question": 3, "counterintuitive_discovery": 4,
    "controversial_opinion": 5, "pain_point": 6, "comparison_analysis": 7,
    "identity_label": 8, "number_shock": 9, "suspense_mystery": 10,
}
_NARRATIVE_INDEX = {
    "tutorial_howto": 0, "opinion_argument": 1, "story_personal": 2,
    "question_discussion": 3, "resource_showcase": 4, "no_body": 5,
}

FEATURE_NAMES = [
    "title_word_count", "title_char_count", "avg_word_length_title",
    "title_has_question", "title_has_number", "title_has_exclamation",
    "title_caps_ratio", "title_starts_how", "title_starts_why",
    "title_exclamation_count",
    "hook_type_index", "narrative_mode_index",
    "subreddit_viral_rate",
    "tier_t1", "tier_t2", "tier_t3",
    "pattern_historical_viral_rate",
]

DEFAULT_MODEL_PATH = Path("data/models/title_ranker.joblib")


def _extract_title_features(
    title: str,
    hook_type: str,
    narrative_mode: str,
    tier: str,
    subreddit_viral_rate: float,
    pattern_historical_viral_rate: float,
) -> np.ndarray:
    """Extract the 17-feature vector for a single title candidate."""
    title_wc = len(title.split())
    title_len = len(title)
    avg_word_len = title_len / max(title_wc, 1)

    title_lower = title.lower()
    has_question = 1 if "?" in title else 0
    has_number = 1 if any(c.isdigit() for c in title) else 0
    has_exclamation = 1 if "!" in title else 0
    exclamation_count = title.count("!")
    upper_chars = sum(1 for c in title if c.isupper())
    caps_ratio = upper_chars / max(len(title), 1)
    starts_how = 1 if title_lower.startswith("how ") or title_lower.startswith("how to") else 0
    starts_why = 1 if title_lower.startswith("why ") else 0

    hook_idx = _HOOK_INDEX.get(hook_type, -1)
    narr_idx = _NARRATIVE_INDEX.get(narrative_mode, -1)

    tier_t1 = 1 if tier == "t1" else 0
    tier_t2 = 1 if tier == "t2" else 0
    tier_t3 = 1 if tier == "t3" else 0

    return np.array([
        title_wc, title_len, avg_word_len,
        has_question, has_number, has_exclamation,
        caps_ratio, starts_how, starts_why,
        exclamation_count,
        hook_idx, narr_idx,
        subreddit_viral_rate,
        tier_t1, tier_t2, tier_t3,
        pattern_historical_viral_rate,
    ], dtype=np.float64)


class TitleRanker:
    """A lightweight ML model that ranks candidate titles by predicted
    viral probability, using only generation-time-available features.

    Train on feedback.jsonl data, deploy as a re-ranker in TitleGenerator.
    """

    def __init__(self) -> None:
        self._model = None
        self._scaler = None
        self._trained = False

    # ── Training ─────────────────────────────────────────────────

    def train(
        self,
        feedback_path: str | Path,
        patterns: list[dict],
        subreddit_viral_rates: dict[str, float] | None = None,
    ) -> dict:
        """Train the ranking model from feedback.jsonl data.

        Args:
            feedback_path: Path to feedback.jsonl.
            patterns: Loaded pattern definitions (for historical_viral_rate).
            subreddit_viral_rates: Optional {subreddit: viral_rate} map.
                If not provided, computed from feedback data.

        Returns:
            Dict with training metrics (n_samples, pos_rate, cv_score).
        """
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        from sklearn.model_selection import cross_val_score

        fb_path = Path(feedback_path)
        if not fb_path.exists():
            raise FileNotFoundError(f"Feedback file not found: {fb_path}")

        # Build pattern lookup
        pattern_map: dict[str, dict] = {}
        for p in patterns:
            pattern_map[p.get("pattern_id", "")] = p

        # Compute subreddit viral rates from feedback if not provided
        if subreddit_viral_rates is None:
            subreddit_viral_rates = self._compute_viral_rates(fb_path)

        # Build training data
        X_rows = []
        y_rows = []
        skipped = 0
        with open(fb_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                title = entry.get("title", "")
                if not title or len(title.split()) < 3:
                    skipped += 1
                    continue

                pid = entry.get("pattern_id", "")
                pattern = pattern_map.get(pid, {})
                hook_type = pattern.get("hook_type", entry.get("hook_type", "curious_question"))
                narrative_mode = pattern.get("narrative_mode", "opinion_argument")
                sub = entry.get("subreddit", "").lower()

                # Infer tier from feedback subreddit (default t2)
                tier = "t2"
                historical_rate = pattern.get("historical_viral_rate", 0.3)

                features = _extract_title_features(
                    title=title,
                    hook_type=hook_type,
                    narrative_mode=narrative_mode,
                    tier=tier,
                    subreddit_viral_rate=subreddit_viral_rates.get(sub, 0.3),
                    pattern_historical_viral_rate=historical_rate,
                )
                X_rows.append(features)

                # Label: viral/passing = positive, failed = negative
                perf = entry.get("performance", "failed")
                y_rows.append(1 if perf in ("viral", "super_viral", "passing") else 0)

        if len(X_rows) < 20:
            raise ValueError(f"Need at least 20 training samples, got {len(X_rows)}")

        X = np.array(X_rows, dtype=np.float64)
        y = np.array(y_rows, dtype=np.int64)

        pos_count = int(y.sum())
        neg_count = len(y) - pos_count
        logger.info(
            "TitleRanker training: %d samples, %d positive (%.1f%%), %d skipped",
            len(X_rows), pos_count, 100 * pos_count / len(X_rows), skipped,
        )

        # Standardize features
        self._scaler = StandardScaler()
        X_scaled = self._scaler.fit_transform(X)

        # Lightweight model: L2-regularized logistic regression
        self._model = LogisticRegression(
            C=1.0, class_weight="balanced",
            max_iter=1000, random_state=42,
        )
        self._model.fit(X_scaled, y)

        # Quick CV estimate
        try:
            cv_scores = cross_val_score(self._model, X_scaled, y, cv=3, scoring="roc_auc")
            cv_mean = float(cv_scores.mean())
        except Exception:
            cv_mean = 0.0

        self._trained = True

        return {
            "n_samples": len(X_rows),
            "n_positive": pos_count,
            "n_negative": neg_count,
            "positive_rate": round(pos_count / len(X_rows), 3),
            "cv_roc_auc_mean": round(cv_mean, 3),
        }

    # ── Persistence ──────────────────────────────────────────────

    def save(self, path: str | Path | None = None) -> Path:
        """Serialize model, scaler, and metadata to disk."""
        import joblib

        if not self._trained:
            raise RuntimeError("TitleRanker must be trained before saving")

        save_path = Path(path) if path else DEFAULT_MODEL_PATH
        save_path.parent.mkdir(parents=True, exist_ok=True)

        joblib.dump(
            {
                "model": self._model,
                "scaler": self._scaler,
                "feature_names": FEATURE_NAMES,
                "hook_index": _HOOK_INDEX,
                "narrative_index": _NARRATIVE_INDEX,
            },
            save_path,
        )
        logger.info("TitleRanker saved to %s", save_path)
        return save_path

    def load(self, path: str | Path | None = None) -> bool:
        """Load a previously saved model.  Returns True on success."""
        import joblib

        load_path = Path(path) if path else DEFAULT_MODEL_PATH
        if not load_path.exists():
            logger.warning("TitleRanker model not found at %s", load_path)
            return False

        try:
            bundle = joblib.load(load_path)
            self._model = bundle["model"]
            self._scaler = bundle["scaler"]
            self._trained = True
            logger.info("TitleRanker loaded from %s", load_path)
            return True
        except Exception as e:
            logger.error("Failed to load TitleRanker: %s", e)
            return False

    # ── Inference ────────────────────────────────────────────────

    def score_title(
        self,
        title: str,
        hook_type: str,
        narrative_mode: str,
        tier: str,
        subreddit_viral_rate: float,
        pattern_historical_viral_rate: float,
    ) -> float:
        """Return predicted viral probability (0.0–1.0) for a single title."""
        if not self._trained or self._model is None:
            return 0.5  # untrained → neutral

        features = _extract_title_features(
            title=title,
            hook_type=hook_type,
            narrative_mode=narrative_mode,
            tier=tier,
            subreddit_viral_rate=subreddit_viral_rate,
            pattern_historical_viral_rate=pattern_historical_viral_rate,
        )
        X = features.reshape(1, -1)
        if self._scaler:
            X = self._scaler.transform(X)

        try:
            proba = self._model.predict_proba(X)[0, 1]
            return float(proba)
        except Exception:
            return 0.5

    def rank(
        self,
        candidates: list[CandidateTitle],
        subreddit: str,
        tier: str,
        pattern: dict,
        subreddit_viral_rate: float = 0.3,
        blend_weight: float = 0.5,
    ) -> list[CandidateTitle]:
        """Re-rank candidates by blending heuristic score with ML probability.

        Args:
            candidates: Scored candidates from TitleGenerator.
            subreddit: Target subreddit name.
            tier: Subreddit tier (t1/t2/t3).
            pattern: The pattern used to generate these candidates.
            subreddit_viral_rate: Pre-computed viral rate for this subreddit.
            blend_weight: Weight for ML score (0=heuristic only, 1=ML only).

        Returns:
            Re-scored candidates sorted by blended score descending.
        """
        if not self._trained or self._model is None:
            return candidates  # untrained → pass through

        hook_type = pattern.get("hook_type", "unknown")
        narrative_mode = pattern.get("narrative_mode", "opinion_argument")
        historical_rate = pattern.get("historical_viral_rate", 0.3)

        for c in candidates:
            ml_prob = self.score_title(
                title=c.title,
                hook_type=hook_type,
                narrative_mode=narrative_mode,
                tier=tier,
                subreddit_viral_rate=subreddit_viral_rate,
                pattern_historical_viral_rate=historical_rate,
            )
            ml_score = ml_prob * 100.0  # convert to 0-100 scale
            c.score = (1 - blend_weight) * c.score + blend_weight * ml_score

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates

    @staticmethod
    def _compute_viral_rates(fb_path: Path) -> dict[str, float]:
        """Compute per-subreddit viral rate from feedback data."""
        by_sub: dict[str, list[int]] = {}
        with open(fb_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sub = entry.get("subreddit", "").lower()
                if not sub:
                    continue
                perf = entry.get("performance", "failed")
                by_sub.setdefault(sub, []).append(
                    1 if perf in ("viral", "super_viral", "passing") else 0
                )

        rates: dict[str, float] = {}
        for sub, outcomes in by_sub.items():
            rates[sub] = sum(outcomes) / len(outcomes) if outcomes else 0.3
        return rates

    @property
    def is_trained(self) -> bool:
        return self._trained
