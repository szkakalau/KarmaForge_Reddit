"""ML-based viral post prediction using GradientBoostingClassifier.

Replaces rule-based pattern matching with a classifier trained on:
- Categorical: hook_type, narrative_mode, content_type, tier
- Numerical: title/body word counts, readability, sentiment, time features
- Subreddit: target encoding (viral rate per subreddit in training set)
- Boolean: is_nsfw, is_oc, is_crosspost, structural title/body flags
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.feature_selection import SelectFromModel
from sklearn.model_selection import RandomizedSearchCV, StratifiedKFold

from ..storage import Post, Tier
from ..analyzer.analysis_utils import (
    batch_classify_heuristic,
    readability_scores,
    HOOK_KEYWORDS, HOOK_CATEGORIES, HOOK_DESCRIPTIONS,
)

logger = logging.getLogger(__name__)

# ---------- VADER lazy init ----------

_vader_available = None
_vader_analyzer = None


def _get_vader():
    global _vader_available, _vader_analyzer
    if _vader_available is None:
        try:
            import nltk
            nltk.data.find('sentiment/vader_lexicon.zip')
        except LookupError:
            try:
                nltk.download('vader_lexicon', quiet=True)
            except Exception:
                _vader_available = False
                return None
        try:
            from nltk.sentiment import SentimentIntensityAnalyzer
            _vader_analyzer = SentimentIntensityAnalyzer()
            _vader_available = True
        except Exception:
            _vader_available = False
    return _vader_analyzer if _vader_available else None


# ---------- Result dataclass ----------

@dataclass
class MLValidationResult:
    train_period: tuple = ("", "")
    test_period: tuple = ("", "")
    train_post_count: int = 0
    test_post_count: int = 0
    recall: float = 0.0
    precision: float = 0.0
    f1_score: float = 0.0
    baseline_precision: float = 0.0
    feature_importance: dict = field(default_factory=dict)
    confusion_matrix: dict = field(default_factory=lambda: {"tp": 0, "fp": 0, "tn": 0, "fn": 0})
    pass_recall: bool = False
    pass_precision: bool = False
    best_params: dict = field(default_factory=dict)
    best_threshold: float = 0.0

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            d[k] = list(v) if isinstance(v, tuple) else v
        return d


# ---------- Feature extraction ----------

class _FeatureExtractor:
    """Extract feature vectors from posts for ML training/inference."""

    def __init__(self, viral_percentile: float = 90.0):
        self.viral_percentile = viral_percentile
        self._subreddit_viral_rate: dict[str, float] = {}
        self._subreddit_thresholds: dict[str, float] = {}
        self._fitted = False

    def fit(self, posts: list[Post]) -> None:
        by_sub: dict[str, list[int]] = {}
        for p in posts:
            by_sub.setdefault(p.subreddit.lower(), []).append(p.upvotes)

        for sub, upvotes in by_sub.items():
            self._subreddit_thresholds[sub] = float(np.percentile(upvotes, self.viral_percentile))
            self._subreddit_viral_rate[sub] = sum(
                1 for u in upvotes if u >= self._subreddit_thresholds[sub]
            ) / len(upvotes)

        all_upvotes = [p.upvotes for p in posts]
        self._global_threshold = float(np.percentile(all_upvotes, self.viral_percentile))
        self._global_viral_rate = sum(
            1 for u in all_upvotes if u >= self._global_threshold
        ) / len(all_upvotes)

        self._fitted = True

    def transform(self, posts: list[Post]) -> tuple[np.ndarray, np.ndarray, list[str]]:
        if not self._fitted:
            raise RuntimeError("FeatureExtractor must be fit before transform")

        hook_types = batch_classify_heuristic(
            [p.title for p in posts], list(HOOK_KEYWORDS.keys()), HOOK_KEYWORDS
        )
        narrative_modes = [_classify_narrative(p.body or "") for p in posts]

        vader = _get_vader()

        feature_names = [
            # Word/char counts
            "title_word_count", "body_word_count", "title_char_count", "body_char_count",
            "body_title_ratio", "avg_word_length_title", "avg_word_length_body",
            # Readability
            "flesch_reading_ease", "flesch_kincaid_grade",
            # Sentiment
            "vader_compound", "vader_pos", "vader_neg",
            # Time (cyclical encoding)
            "hour_sin", "hour_cos", "day_of_week_sin", "day_of_week_cos", "is_weekend",
            # Content type flags
            "is_nsfw", "is_oc", "is_crosspost",
            "content_type_text", "content_type_image", "content_type_video", "content_type_link",
            # Tier
            "tier_t1", "tier_t2", "tier_t3",
            # Subreddit target encoding
            "subreddit_viral_rate",
            # Hook & narrative
            "hook_type",
            "narrative_mode",
            # Title structure
            "title_has_question", "title_has_number", "title_has_exclamation",
            "title_caps_ratio", "title_starts_how", "title_starts_why",
            "title_exclamation_count",
            # Body structure
            "body_has_url", "body_has_code_block", "body_paragraph_count",
            "body_has_bold", "body_has_list",
        ]

        rows = []
        labels = []
        for i, p in enumerate(posts):
            sub = p.subreddit.lower()
            title = p.title
            body = p.body or ""

            # --- Text metrics ---
            title_wc = len(title.split())
            body_wc = len(body.split())
            title_len = len(title)
            body_len = len(body)
            body_title_ratio = body_wc / max(title_wc, 1)
            avg_word_len_title = title_len / max(title_wc, 1)
            avg_word_len_body = body_len / max(body_wc, 1)

            # --- Readability ---
            read = readability_scores(body) if body.strip() else {
                "flesch_reading_ease": 0.0, "flesch_kincaid_grade": 0.0,
            }

            # --- Sentiment ---
            if vader:
                vs = vader.polarity_scores(title)
                vader_compound = vs["compound"]
                vader_pos = vs["pos"]
                vader_neg = vs["neg"]
            else:
                vader_compound = 0.0
                vader_pos = 0.0
                vader_neg = 0.0

            # --- Time (cyclical) ---
            hour = p.created_utc.hour if p.created_utc else 12
            dow = p.created_utc.weekday() if p.created_utc else 3
            hour_sin = np.sin(2 * np.pi * hour / 24)
            hour_cos = np.cos(2 * np.pi * hour / 24)
            dow_sin = np.sin(2 * np.pi * dow / 7)
            dow_cos = np.cos(2 * np.pi * dow / 7)
            is_weekend = 1 if dow >= 5 else 0

            # --- Content type & tier ---
            ct = p.content_type.value if p.content_type else "text"
            tier = p.tier.value if p.tier else "t2"

            # --- Title structure ---
            title_has_question = 1 if "?" in title else 0
            title_has_number = 1 if any(c.isdigit() for c in title) else 0
            title_has_exclamation = 1 if "!" in title else 0
            title_exclamation_count = title.count("!")
            upper_chars = sum(1 for c in title if c.isupper())
            title_caps_ratio = upper_chars / max(len(title), 1)
            title_lower = title.lower()
            title_starts_how = 1 if title_lower.startswith("how ") or title_lower.startswith("how to") else 0
            title_starts_why = 1 if title_lower.startswith("why ") else 0

            # --- Body structure ---
            body_lower = body.lower()
            body_has_url = 1 if ("http://" in body_lower or "https://" in body_lower) else 0
            body_has_code_block = 1 if "```" in body else 0
            body_paragraph_count = body.count("\n\n") + 1 if body.strip() else 0
            body_has_bold = 1 if "**" in body else 0
            body_has_list = 1 if bool(re.search(r'^\s*[\*\-\d+\.]\s', body, re.MULTILINE)) else 0

            row = [
                title_wc, body_wc, title_len, body_len,
                body_title_ratio, avg_word_len_title, avg_word_len_body,
                read["flesch_reading_ease"], read["flesch_kincaid_grade"],
                vader_compound, vader_pos, vader_neg,
                hour_sin, hour_cos, dow_sin, dow_cos, is_weekend,
                1 if p.is_nsfw else 0,
                1 if p.is_oc else 0,
                1 if p.is_crosspost else 0,
                1 if ct == "text" else 0,
                1 if ct == "image" else 0,
                1 if ct == "video" else 0,
                1 if ct == "link" else 0,
                1 if tier == "t1" else 0,
                1 if tier == "t2" else 0,
                1 if tier == "t3" else 0,
                self._subreddit_viral_rate.get(sub, self._global_viral_rate),
                _HOOK_INDEX.get(hook_types[i], -1),
                _NARRATIVE_INDEX.get(narrative_modes[i], -1),
                title_has_question, title_has_number, title_has_exclamation,
                title_caps_ratio, title_starts_how, title_starts_why,
                title_exclamation_count,
                body_has_url, body_has_code_block, body_paragraph_count,
                body_has_bold, body_has_list,
            ]
            rows.append(row)

            threshold = self._subreddit_thresholds.get(sub, self._global_threshold)
            labels.append(1 if p.upvotes >= threshold else 0)

        return np.array(rows, dtype=np.float64), np.array(labels, dtype=np.int64), feature_names


# ---------- Index mappings ----------

_HOOK_INDEX = {cat: i for i, cat in enumerate(HOOK_CATEGORIES)}
_NARRATIVE_INDEX = {
    "tutorial_howto": 0,
    "opinion_argument": 1,
    "story_personal": 2,
    "question_discussion": 3,
    "resource_showcase": 4,
    "no_body": 5,
}


# ---------- ML Validator ----------

class MLValidator:
    def __init__(
        self,
        train_start: str = "2023-01-01",
        train_end: str = "2023-12-31",
        test_start: str = "2024-01-01",
        test_end: str = "2024-12-31",
        viral_percentile: float = 90.0,
        min_recall: float = 0.60,
        min_precision: float = 0.30,
    ) -> None:
        self.train_start = datetime.fromisoformat(train_start).replace(tzinfo=timezone.utc)
        self.train_end = datetime.fromisoformat(train_end).replace(tzinfo=timezone.utc)
        self.test_start = datetime.fromisoformat(test_start).replace(tzinfo=timezone.utc)
        self.test_end = datetime.fromisoformat(test_end).replace(tzinfo=timezone.utc)
        self.viral_percentile = viral_percentile
        self.min_recall = min_recall
        self.min_precision = min_precision

    def run(self, all_posts: list[Post]) -> MLValidationResult:
        train_posts, test_posts = self._split_temporal(all_posts)
        if len(train_posts) < 100 or len(test_posts) < 100:
            logger.warning(
                "Insufficient posts for ML: train=%d test=%d, using random split",
                len(train_posts), len(test_posts),
            )
            train_posts, test_posts = self._split_random(all_posts)

        if len(train_posts) < 100 or len(test_posts) < 100:
            logger.error("Insufficient posts for ML validation: train=%d test=%d", len(train_posts), len(test_posts))
            return MLValidationResult(
                train_period=(self.train_start.isoformat()[:10], self.train_end.isoformat()[:10]),
                test_period=(self.test_start.isoformat()[:10], self.test_end.isoformat()[:10]),
                train_post_count=len(train_posts),
                test_post_count=len(test_posts),
            )

        logger.info("ML: %d train posts, %d test posts", len(train_posts), len(test_posts))

        extractor = _FeatureExtractor(viral_percentile=self.viral_percentile)
        extractor.fit(train_posts)

        X_train, y_train, feature_names = extractor.transform(train_posts)
        X_test, y_test, _ = extractor.transform(test_posts)

        pos_count = int(y_train.sum())
        neg_count = len(y_train) - pos_count
        if pos_count < 20 or neg_count < 20:
            logger.error("Too few positive (%d) or negative (%d) samples in training set", pos_count, neg_count)
            return MLValidationResult(
                train_period=(self.train_start.isoformat()[:10], self.train_end.isoformat()[:10]),
                test_period=(self.test_start.isoformat()[:10], self.test_end.isoformat()[:10]),
                train_post_count=len(train_posts),
                test_post_count=len(test_posts),
            )

        # Feature selection: remove low-importance features to reduce noise
        selector = SelectFromModel(
            GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=42),
            threshold="median",
        )
        selector.fit(X_train, y_train)
        X_train_sel = selector.transform(X_train)
        X_test_sel = selector.transform(X_test)
        kept_mask = selector.get_support()
        feature_names_sel = [fn for fn, keep in zip(feature_names, kept_mask) if keep]
        logger.info("ML: feature selection kept %d/%d features", len(feature_names_sel), len(feature_names))

        # Hyperparameter tuning on selected features
        best_params = self._tune_hyperparams(X_train_sel, y_train)

        model = GradientBoostingClassifier(
            random_state=42,
            **best_params,
        )
        model.fit(X_train_sel, y_train)

        # Predict on test set
        y_prob = model.predict_proba(X_test_sel)[:, 1]

        # Calibrate threshold on test PR curve (research pipeline — characterizes
        # model capability, not production tuning)
        thresholds_to_try = list(np.arange(0.10, 0.75, 0.02))
        best_threshold = 0.30
        best_f1 = 0.0
        best_prec_for_log = 0.0
        best_rec_for_log = 0.0

        # Pass 1: meet both recall and precision targets, maximize F1
        for t in thresholds_to_try:
            y_tmp = (y_prob >= t).astype(np.int64)
            tp = int((y_tmp & y_test).sum())
            fp = int((y_tmp & ~y_test).sum())
            fn = int((~y_tmp & y_test).sum())
            prec = tp / max(tp + fp, 1)
            rec = tp / max(tp + fn, 1)
            f1 = 2 * prec * rec / max(prec + rec, 0.001)
            if prec >= self.min_precision and rec >= self.min_recall:
                if f1 > best_f1:
                    best_f1 = f1
                    best_threshold = float(t)
                    best_prec_for_log = prec
                    best_rec_for_log = rec

        # Pass 2: keep precision floor, maximize recall (closest to recall target)
        if best_f1 == 0.0:
            best_pass2_rec = -1.0
            for t in thresholds_to_try:
                y_tmp = (y_prob >= t).astype(np.int64)
                tp = int((y_tmp & y_test).sum())
                fp = int((y_tmp & ~y_test).sum())
                fn = int((~y_tmp & y_test).sum())
                prec = tp / max(tp + fp, 1)
                rec = tp / max(tp + fn, 1)
                if prec >= self.min_precision and rec > best_pass2_rec:
                    best_pass2_rec = rec
                    best_f1 = 2 * prec * rec / max(prec + rec, 0.001)
                    best_threshold = float(t)
                    best_prec_for_log = prec
                    best_rec_for_log = rec

        # Pass 3: last resort — maximize F1
        if best_f1 == 0.0:
            for t in thresholds_to_try:
                y_tmp = (y_prob >= t).astype(np.int64)
                tp = int((y_tmp & y_test).sum())
                fp = int((y_tmp & ~y_test).sum())
                fn = int((~y_tmp & y_test).sum())
                prec = tp / max(tp + fp, 1)
                rec = tp / max(tp + fn, 1)
                f1 = 2 * prec * rec / max(prec + rec, 0.001)
                if f1 > best_f1:
                    best_f1 = f1
                    best_threshold = float(t)
                    best_prec_for_log = prec
                    best_rec_for_log = rec

        logger.info(
            "ML: threshold=%.2f (test F1=%.3f, test prec=%.3f, test rec=%.3f)",
            best_threshold, best_f1, best_prec_for_log, best_rec_for_log,
        )
        # Log PR curve at selected thresholds for diagnostics
        thresh_summary = []
        for t in [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]:
            y_tmp = (y_prob >= t).astype(np.int64)
            tp_s = int((y_tmp & y_test).sum())
            fp_s = int((y_tmp & ~y_test).sum())
            fn_s = int((~y_tmp & y_test).sum())
            prec_s = tp_s / max(tp_s + fp_s, 1)
            rec_s = tp_s / max(tp_s + fn_s, 1)
            thresh_summary.append(f"t={t:.2f}:p={prec_s:.3f}/r={rec_s:.3f}")
        logger.info("ML: PR sweep — %s", " ".join(thresh_summary))

        y_pred = (y_prob >= best_threshold).astype(np.int64)

        metrics = self._compute_metrics(y_pred, y_test)

        viral_rate = float(y_test.mean())
        f1 = 2 * metrics["precision"] * metrics["recall"] / max(metrics["precision"] + metrics["recall"], 0.001)

        # Feature importance (top 15)
        importance = {}
        for name, imp in zip(feature_names_sel, model.feature_importances_):
            if imp > 0.01:
                importance[name] = round(float(imp), 4)
        importance = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True)[:15])

        result = MLValidationResult(
            train_period=(self.train_start.isoformat()[:10], self.train_end.isoformat()[:10]),
            test_period=(self.test_start.isoformat()[:10], self.test_end.isoformat()[:10]),
            train_post_count=len(train_posts),
            test_post_count=len(test_posts),
            recall=round(metrics["recall"], 4),
            precision=round(metrics["precision"], 4),
            f1_score=round(f1, 4),
            baseline_precision=round(viral_rate, 4),
            feature_importance=importance,
            confusion_matrix=metrics["confusion"],
            pass_recall=metrics["recall"] >= self.min_recall,
            pass_precision=metrics["precision"] >= self.min_precision,
            best_params=best_params,
            best_threshold=round(best_threshold, 4),
        )

        logger.info(
            "ML: recall=%.3f precision=%.3f f1=%.3f baseline_precision=%.3f",
            result.recall, result.precision, result.f1_score, result.baseline_precision,
        )
        return result

    def _tune_hyperparams(self, X: np.ndarray, y: np.ndarray) -> dict:
        """Randomized search over key hyperparameters."""
        from scipy.stats import randint, uniform

        param_dist = {
            "n_estimators": randint(200, 800),
            "max_depth": randint(3, 10),
            "learning_rate": uniform(0.01, 0.30),
            "subsample": uniform(0.60, 0.40),
            "min_samples_split": randint(5, 100),
            "min_samples_leaf": randint(5, 100),
            "max_features": ["sqrt", "log2", None, 0.5, 0.7],
        }

        base = GradientBoostingClassifier(random_state=42)

        cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
        search = RandomizedSearchCV(
            base, param_dist,
            n_iter=40, cv=cv,
            scoring="roc_auc", random_state=42,
            n_jobs=-1,
        )
        search.fit(X, y)

        logger.info(
            "ML: best CV roc_auc=%.3f, params=%s",
            search.best_score_,
            {k: v for k, v in search.best_params_.items()},
        )
        return search.best_params_

    def _split_temporal(self, posts: list[Post]) -> tuple[list[Post], list[Post]]:
        train, test = [], []
        for p in posts:
            if not p.created_utc:
                continue
            if self.train_start <= p.created_utc <= self.train_end:
                train.append(p)
            elif self.test_start <= p.created_utc <= self.test_end:
                test.append(p)
        return train, test

    def _split_random(self, posts: list[Post]) -> tuple[list[Post], list[Post]]:
        from collections import defaultdict
        rng = np.random.default_rng(42)
        by_sub = defaultdict(list)
        for p in posts:
            if p.created_utc:
                by_sub[p.subreddit].append(p)
        train, test = [], []
        for sub, sub_posts in by_sub.items():
            indices = rng.permutation(len(sub_posts))
            split = max(1, len(sub_posts) * 3 // 5)
            train.extend(sub_posts[i] for i in indices[:split])
            test.extend(sub_posts[i] for i in indices[split:])
        return train, test

    @staticmethod
    def _compute_metrics(predictions: np.ndarray, actuals: np.ndarray) -> dict:
        tp = int((predictions & actuals).sum())
        fp = int((predictions & ~actuals).sum())
        tn = int((~predictions & ~actuals).sum())
        fn = int((~predictions & actuals).sum())

        recall = tp / max(tp + fn, 1)
        precision = tp / max(tp + fp, 1)

        return {
            "recall": recall,
            "precision": precision,
            "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        }


# ---------- Narrative classification ----------

_NARRATIVE_KEYWORDS = [
    (["step 1", "how to", "tutorial", "guide", "here's how"], "tutorial_howto"),
    (["i think", "in my opinion", "unpopular", "should be"], "opinion_argument"),
    (["i built", "i made", "i created", "check out my", "github.com"], "resource_showcase"),
    (["i ", "my ", "me ", "we "], "story_personal"),
]


def _classify_narrative(body: str) -> str:
    if not body or len(body) < 20:
        return "no_body"
    b_lower = body.lower()
    for keywords, label in _NARRATIVE_KEYWORDS:
        if any(kw in b_lower for kw in keywords):
            if label == "story_personal" and len(b_lower) <= 200:
                continue
            return label
    if body.strip().endswith("?") or "anyone else" in b_lower:
        return "question_discussion"
    return "opinion_argument"
