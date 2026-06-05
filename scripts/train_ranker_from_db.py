"""Train ML TitleRanker from database posts (no feedback.jsonl needed).

Uses the 9,560 posts in the SQLite database as training data. Posts above
the 80th upvote percentile are labeled as viral (positive), others as
non-viral (negative). The model learns which title characteristics predict
viral performance across subreddits and hook types.

Usage:
    python scripts/train_ranker_from_db.py
    python scripts/train_ranker_from_db.py --output data/models/title_ranker_v2.joblib
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.karmaforge.storage import Database
from src.karmaforge.analyzer.analysis_utils import (
    batch_classify_heuristic, HOOK_KEYWORDS, HOOK_CATEGORIES,
)
from src.karmaforge.generator.ml_ranker import (
    TitleRanker, _extract_title_features,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Config ──
VIRAL_PERCENTILE = 80  # top 20% = viral
MIN_TITLE_WORDS = 3
OUTPUT_PATH = Path("data/models/title_ranker.joblib")
PATTERNS_PATH = Path("data/patterns/patterns.json")
DB_PATH = Path("data/processed/karmaforge.db")

_BODY_MODES = {
    "story_personal", "tutorial_howto", "opinion_argument",
    "question_discussion", "resource_showcase", "news_event",
    "humor_satire", "review_critique",
}


def _classify_narrative(body: str) -> str:
    if not body or len(body) < 20:
        return "no_body"
    return "has_body"


def main():
    # Load patterns for historical_viral_rate lookup
    patterns = []
    if PATTERNS_PATH.exists():
        with open(PATTERNS_PATH, "r", encoding="utf-8") as f:
            patterns = json.load(f)
    pattern_map = {}
    for p in patterns:
        hid = p.get("hook_type", "")
        nid = p.get("narrative_mode", "")
        pattern_map[(hid, nid)] = p

    # Load posts from DB
    db = Database(DB_PATH)
    posts = db.get_all_posts()
    logger.info("Loaded %d posts from database", len(posts))

    if len(posts) < 50:
        logger.error("Need at least 50 posts, got %d", len(posts))
        return 1

    # Classify hooks with heuristic (fast, no API cost)
    titles = [p.title for p in posts if p.title and len(p.title.split()) >= MIN_TITLE_WORDS]
    hook_types = batch_classify_heuristic(
        titles, list(HOOK_KEYWORDS.keys()), HOOK_KEYWORDS
    )

    # Compute viral threshold
    upvotes_list = [p.upvotes for p in posts]
    viral_threshold = np.percentile(upvotes_list, VIRAL_PERCENTILE)
    logger.info(
        "Viral threshold: %d upvotes (top %d%%)",
        int(viral_threshold), 100 - VIRAL_PERCENTILE,
    )

    # Compute per-subreddit viral rates
    sub_stats: dict[str, tuple[int, int]] = {}
    for p in posts:
        sub = p.subreddit.lower()
        if sub not in sub_stats:
            sub_stats[sub] = [0, 0]
        sub_stats[sub][0] += 1
        if p.upvotes >= viral_threshold:
            sub_stats[sub][1] += 1
    subreddit_viral_rates = {
        sub: viral / max(total, 1)
        for sub, (total, viral) in sub_stats.items()
    }

    # Build feature matrix
    X_rows = []
    y_rows = []
    skipped = 0
    for i, p in enumerate(posts):
        title = p.title
        if not title or len(title.split()) < MIN_TITLE_WORDS:
            skipped += 1
            continue

        hook_type = hook_types[i] if i < len(hook_types) else "curious_question"
        body_narrative = _classify_narrative(p.body or "")
        tier = p.tier.value if p.tier else "t2"
        sub = p.subreddit.lower()

        # Look up pattern historical rate
        pattern = pattern_map.get((hook_type, body_narrative), {})
        historical_rate = pattern.get("historical_viral_rate", 0.25)

        features = _extract_title_features(
            title=title,
            hook_type=hook_type,
            narrative_mode=body_narrative,
            tier=tier,
            subreddit_viral_rate=subreddit_viral_rates.get(sub, 0.2),
            pattern_historical_viral_rate=historical_rate,
        )
        X_rows.append(features)

        # Label: viral = 1, non-viral = 0
        y_rows.append(1 if p.upvotes >= viral_threshold else 0)

    if len(X_rows) < 20:
        logger.error("Need at least 20 samples, got %d (skipped %d)", len(X_rows), skipped)
        return 1

    X = np.array(X_rows, dtype=np.float64)
    y = np.array(y_rows, dtype=np.int64)

    pos_count = int(y.sum())
    logger.info(
        "Training set: %d samples, %d viral (%.1f%%), %d skipped",
        len(X_rows), pos_count,
        100 * pos_count / len(X_rows), skipped,
    )

    # Train
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import cross_val_score

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = LogisticRegression(
        C=1.0, class_weight="balanced",
        max_iter=1000, random_state=42,
    )
    model.fit(X_scaled, y)

    # Evaluate
    try:
        cv_scores = cross_val_score(model, X_scaled, y, cv=5, scoring="roc_auc")
        cv_mean = float(cv_scores.mean())
        cv_std = float(cv_scores.std())
        logger.info("5-fold CV ROC-AUC: %.3f (±%.3f)", cv_mean, cv_std)
    except Exception as e:
        logger.warning("CV failed: %s", e)
        cv_mean = 0.0

    # Show top feature weights
    from src.karmaforge.generator.ml_ranker import FEATURE_NAMES
    coef = model.coef_[0]
    top_idx = np.argsort(np.abs(coef))[::-1][:8]
    logger.info("Top features by weight:")
    for idx in top_idx:
        logger.info(
            "  %-30s %+.4f",
            FEATURE_NAMES[idx] if idx < len(FEATURE_NAMES) else f"feat_{idx}",
            coef[idx],
        )

    # Save
    ranker = TitleRanker()
    ranker._model = model
    ranker._scaler = scaler
    ranker._trained = True
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ranker.save(OUTPUT_PATH)
    logger.info("Model saved to %s", OUTPUT_PATH)

    return 0


if __name__ == "__main__":
    sys.exit(main())
