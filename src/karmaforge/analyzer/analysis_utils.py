"""Shared statistical and NLP utilities for all KarmaForge analyzers."""

import json
import logging
import math
import re
from collections import Counter
from typing import Callable, Optional, Union

import numpy as np
from scipy import stats as scipy_stats

logger = logging.getLogger(__name__)


def compute_distribution(
    values: list[float], bins: int = 20, label_inflections: bool = True
) -> dict:
    arr = np.array(values)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return {"bins": [], "counts": [], "inflection_points": [], "percentiles": {}, "n": 0}

    counts, bin_edges = np.histogram(arr, bins=bins)
    result = {
        "bins": [round(e, 2) for e in bin_edges.tolist()],
        "counts": counts.tolist(),
        "percentiles": {
            "p10": round(float(np.percentile(arr, 10)), 2),
            "p25": round(float(np.percentile(arr, 25)), 2),
            "p50": round(float(np.percentile(arr, 50)), 2),
            "p75": round(float(np.percentile(arr, 75)), 2),
            "p90": round(float(np.percentile(arr, 90)), 2),
            "p95": round(float(np.percentile(arr, 95)), 2),
            "p99": round(float(np.percentile(arr, 99)), 2),
        },
        "mean": round(float(np.mean(arr)), 2),
        "std": round(float(np.std(arr)), 2),
        "n": len(arr),
        "inflection_points": [],
    }

    if label_inflections and len(counts) >= 5:
        result["inflection_points"] = _find_inflection_points(counts)

    return result


def inflection_points(values: list[float]) -> list[int]:
    return _find_inflection_points(values)


def _find_inflection_points(counts: list[int]) -> list[int]:
    if len(counts) < 5:
        return []
    second_deriv = np.diff(counts, n=2)
    sign_changes = []
    for i in range(1, len(second_deriv)):
        if second_deriv[i - 1] * second_deriv[i] < 0:
            sign_changes.append(i + 1)
    return sign_changes


def correlation_test(metric: list[float], upvotes: list[float]) -> dict:
    x = np.array(metric, dtype=float)
    y = np.array(upvotes, dtype=float)
    mask = ~(np.isnan(x) | np.isnan(y))
    x, y = x[mask], y[mask]

    if len(x) < 10:
        return {"pearson_r": 0, "spearman_rho": 0, "p_value": 1.0, "n": len(x)}

    pearson_r, pearson_p = scipy_stats.pearsonr(x, y)
    spearman_rho, spearman_p = scipy_stats.spearmanr(x, y)

    return {
        "pearson_r": round(float(pearson_r), 4),
        "pearson_p": round(float(pearson_p), 6),
        "spearman_rho": round(float(spearman_rho), 4),
        "spearman_p": round(float(spearman_p), 6),
        "n": len(x),
    }


def chi_square_test(observed: list[list[int]]) -> dict:
    arr = np.array(observed)
    try:
        chi2, p, dof, expected = scipy_stats.chi2_contingency(arr)
        n = arr.sum()
        cramers_v = math.sqrt(chi2 / (n * min(arr.shape[0] - 1, arr.shape[1] - 1))) if n > 0 else 0
        return {
            "chi2": round(float(chi2), 4),
            "p_value": round(float(p), 6),
            "dof": dof,
            "cramers_v": round(float(cramers_v), 4),
        }
    except ValueError:
        return {"chi2": 0, "p_value": 1.0, "dof": 0, "cramers_v": 0}


def bootstrap_confidence_interval(
    data: list[float],
    statistic: Callable[[np.ndarray], float],
    n_bootstrap: int = 10000,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float, float]:
    if len(data) == 0:
        return (0.0, 0.0, 0.0)

    rng = np.random.default_rng(seed)
    arr = np.array(data, dtype=float)
    arr = arr[~np.isnan(arr)]

    boot_stats = []
    for _ in range(n_bootstrap):
        sample = rng.choice(arr, size=len(arr), replace=True)
        boot_stats.append(statistic(sample))

    alpha = (1 - ci) / 2
    lower = float(np.percentile(boot_stats, alpha * 100))
    upper = float(np.percentile(boot_stats, (1 - alpha) * 100))
    mean_val = float(np.mean(boot_stats))
    return (round(lower, 4), round(mean_val, 4), round(upper, 4))


def cohens_d(group1: list[float], group2: list[float]) -> float:
    a1 = np.array(group1, dtype=float)
    a2 = np.array(group2, dtype=float)
    a1, a2 = a1[~np.isnan(a1)], a2[~np.isnan(a2)]
    if len(a1) < 2 or len(a2) < 2:
        return 0.0

    n1, n2 = len(a1), len(a2)
    s1, s2 = np.var(a1, ddof=1), np.var(a2, ddof=1)
    pooled_std = math.sqrt(((n1 - 1) * s1 + (n2 - 1) * s2) / (n1 + n2 - 2))
    if pooled_std == 0:
        return 0.0
    return round(float((np.mean(a1) - np.mean(a2)) / pooled_std), 4)


def remove_outliers_iqr(data: list[float], multiplier: float = 1.5) -> list[float]:
    arr = np.array(data, dtype=float)
    arr = arr[~np.isnan(arr)]
    q1, q3 = np.percentile(arr, 25), np.percentile(arr, 75)
    iqr = q3 - q1
    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr
    return arr[(arr >= lower) & (arr <= upper)].tolist()


def text_length_metrics(text: str) -> dict:
    if not text:
        return {"char_count": 0, "word_count": 0, "sentence_count": 0, "avg_words_per_sentence": 0}

    char_count = len(text)
    words = text.split()
    word_count = len(words)
    sentences = re.split(r"[.!?]+", text)
    sentences = [s for s in sentences if s.strip()]
    sentence_count = len(sentences)
    avg_wps = word_count / sentence_count if sentence_count > 0 else 0

    return {
        "char_count": char_count,
        "word_count": word_count,
        "sentence_count": sentence_count,
        "avg_words_per_sentence": round(avg_wps, 2),
    }


def readability_scores(text: str) -> dict:
    if not text or not text.strip():
        return {
            "flesch_kincaid_grade": 0,
            "flesch_reading_ease": 0,
            "gunning_fog": 0,
            "smog_index": 0,
        }

    try:
        import textstat
        return {
            "flesch_kincaid_grade": round(textstat.flesch_kincaid_grade(text), 2),
            "flesch_reading_ease": round(textstat.flesch_reading_ease(text), 2),
            "gunning_fog": round(textstat.gunning_fog(text), 2),
            "smog_index": round(textstat.smog_index(text), 2),
        }
    except ImportError:
        return _simple_readability(text)


def _simple_readability(text: str) -> dict:
    words = text.split()
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    if not words or not sentences:
        return {"flesch_kincaid_grade": 0, "flesch_reading_ease": 0, "gunning_fog": 0, "smog_index": 0}

    syllables = sum(_count_syllables(w) for w in words)
    asl = len(words) / len(sentences)
    asw = syllables / len(words)
    fk_grade = 0.39 * asl + 11.8 * asw - 15.59
    fre = 206.835 - 1.015 * asl - 84.6 * asw

    return {
        "flesch_kincaid_grade": round(max(0, fk_grade), 2),
        "flesch_reading_ease": round(max(0, min(100, fre)), 2),
        "gunning_fog": 0,
        "smog_index": 0,
    }


def _count_syllables(word: str) -> int:
    word = word.lower().strip(".:;?!")
    if not word:
        return 1
    count = 0
    vowels = "aeiouy"
    prev_vowel = False
    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    if word.endswith("e"):
        count = max(1, count - 1)
    return max(1, count)


def compute_percentile_rank(value: float, population: list[float]) -> float:
    arr = np.array(population, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return 50.0
    return round(float(scipy_stats.percentileofscore(arr, value)), 2)


def find_optimal_range(
    metric_values: list[float],
    upvotes: list[float],
    window_pct: float = 0.2,
    min_window: int = 5,
) -> tuple[float, float]:
    arr_m = np.array(metric_values, dtype=float)
    arr_u = np.array(upvotes, dtype=float)
    mask = ~(np.isnan(arr_m) | np.isnan(arr_u))
    arr_m, arr_u = arr_m[mask], arr_u[mask]

    if len(arr_m) < min_window * 2:
        return (0.0, 0.0)

    window_size = max(min_window, int(len(arr_m) * window_pct))
    sorted_idx = np.argsort(arr_m)
    arr_m_sorted = arr_m[sorted_idx]
    arr_u_sorted = arr_u[sorted_idx]

    best_mean = 0.0
    best_range = (0.0, 0.0)

    for i in range(len(arr_m_sorted) - window_size):
        window_mean = np.mean(arr_u_sorted[i : i + window_size])
        if window_mean > best_mean:
            best_mean = window_mean
            best_range = (float(arr_m_sorted[i]), float(arr_m_sorted[i + window_size - 1]))

    return (round(best_range[0], 2), round(best_range[1], 2))


def keyword_extraction(
    texts: list[str], top_n: int = 50, min_freq: int = 5
) -> list[dict]:
    all_words: Counter = Counter()
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "shall", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "as", "into", "through", "during",
        "before", "after", "above", "below", "between", "and", "but", "or",
        "nor", "not", "so", "yet", "both", "either", "neither", "each", "every",
        "all", "any", "few", "more", "most", "other", "some", "such", "no",
        "only", "own", "same", "than", "too", "very", "just", "about", "also",
        "if", "then", "else", "this", "that", "these", "those", "it", "its",
        "i", "me", "my", "we", "our", "you", "your", "he", "she", "they",
        "him", "his", "her", "them", "what", "which", "who", "whom", "when",
        "where", "why", "how", "am", "don", "didn", "doesn", "isn", "aren",
        "wasn", "weren", "haven", "hasn", "hadn", "won", "wouldn", "can", "couldn",
    }

    for text in texts:
        if not text:
            continue
        words = re.findall(r"[a-zA-Z]{3,}", text.lower())
        for w in words:
            if w not in stop_words:
                all_words[w] += 1

    return [
        {"word": word, "frequency": count}
        for word, count in all_words.most_common(top_n)
        if count >= min_freq
    ]


def batch_classify_heuristic(
    texts: list[str], categories: list[str], keywords: dict[str, list[str]]
) -> list[str]:
    results = []
    for text in texts:
        text_lower = text.lower()

        # Structural features first (more reliable than keywords)
        has_question = "?" in text
        has_number = any(c.isdigit() for c in text)
        has_dollar = "$" in text
        has_how_to = text_lower.startswith("how to") or "how to" in text_lower[:30]
        has_i_word = bool(re.search(r"\bi\b", text_lower)) and len(text_lower) > 50
        has_vs = " vs " in text_lower or " versus " in text_lower

        # Structural classification
        if has_question and not has_number:
            results.append("curious_question")
            continue
        if has_vs:
            results.append("comparison_analysis")
            continue
        if has_how_to:
            results.append("tutorial_howto")
            continue

        # Keyword scoring
        scored = []
        for cat in categories:
            score = sum(1 for kw in keywords.get(cat, []) if kw in text_lower)
            scored.append((cat, score))
        best = max(scored, key=lambda x: x[1])

        if best[1] > 0:
            results.append(best[0])
        elif has_number or has_dollar:
            results.append("number_shock")
        elif has_i_word:
            results.append("story_opener")
        else:
            results.append("curious_question")

    return results


HOOK_KEYWORDS = {
    "counterintuitive_discovery": ["discovered", "i found", "changed everything", "i realized", "secret", "no one tells", "nobody tells"],
    "suspense_mystery": ["you won't believe", "what happened next", "wait until", "plot twist", "unexpected"],
    "pain_point": ["sick of", "tired of", "frustrated", "hate", "worst", "problem with", "annoying", "struggle"],
    "identity_label": ["as a", "if you're a", "anyone else", "fellow", "we all"],
    "number_shock": ["things", "ways", "reasons", "tips", "secrets", "lessons", "rules", "$", "%", "times"],
    "story_opener": ["my journey", "my experience", "i spent", "after years", "i finally", "i built"],
    "resource_share": ["resource", "free", "tool", "template", "open source", "i made", "i created", "check out"],
    "controversial_opinion": ["unpopular opinion", "hot take", "controversial", "change my mind", "i don't care"],
    "comparison_analysis": [" vs ", " versus ", "compared to", "difference between", "better than"],
    "curious_question": ["why does", "how does", "what is", "eli5", "can someone", "anyone know", "has anyone"],
}

HOOK_CATEGORIES = [
    "counterintuitive_discovery",
    "suspense_mystery",
    "pain_point",
    "identity_label",
    "number_shock",
    "story_opener",
    "resource_share",
    "controversial_opinion",
    "comparison_analysis",
    "curious_question",
]

HOOK_DESCRIPTIONS = {
    "counterintuitive_discovery": '"I just discovered X...", "X changed everything", unexpected findings',
    "suspense_mystery": 'Cliffhangers, "you won\'t believe what happened", unresolved tension',
    "pain_point": "Addresses a common frustration, problem, or annoyance",
    "identity_label": 'Appeals to a specific identity/group ("as a developer...", "if you\'re a parent...")',
    "number_shock": 'Uses specific numbers to grab attention ("10 things...", "$50,000 in 3 months")',
    "story_opener": 'Begins a personal narrative ("My journey...", "After 5 years of...")',
    "resource_share": 'Offers a tool, guide, or resource ("[Resource] I built...", "Free template for...")',
    "controversial_opinion": '"Unpopular opinion:", "Hot take:", deliberately provocative',
    "comparison_analysis": '"X vs Y", side-by-side comparisons',
    "curious_question": '"ELI5:", "Why does X?", "Has anyone else...", genuine curiosity',
}


# Module-level cache to avoid re-classifying the same texts across pipeline phases
_classification_cache: dict[str, str] = {}


def clear_classification_cache() -> None:
    """Clear the in-memory classification cache (useful for testing)."""
    _classification_cache.clear()


def batch_classify_llm(
    texts: list[str],
    categories: list[str],
    category_descriptions: dict[str, str],
    llm_client,
    batch_size: int = 20,
    task_name: str = "title",
) -> list[str]:
    """Classify texts using LLM in batches, falling back to heuristic on failure.

    Batches texts into groups of batch_size, sends a single numbered prompt per batch,
    and parses the "N: category" response format. Uses a module-level cache to avoid
    re-classifying the same text across pipeline phases.
    """
    if not llm_client or not texts:
        return batch_classify_heuristic(texts, categories, HOOK_KEYWORDS)

    results: list[Optional[str]] = [None] * len(texts)
    uncached_indices: list[int] = []

    for i, text in enumerate(texts):
        if text in _classification_cache:
            results[i] = _classification_cache[text]
        else:
            uncached_indices.append(i)

    if not uncached_indices:
        return [r for r in results if r is not None]

    cat_desc = "\n".join(
        f"- {cat}: {category_descriptions.get(cat, cat)}"
        for cat in categories
    )

    # Batch only the uncached texts
    batch_groups = [
        uncached_indices[i : i + batch_size]
        for i in range(0, len(uncached_indices), batch_size)
    ]

    for batch_indices in batch_groups:
        # Build numbered prompt
        items = "\n".join(
            f'{i+1}. "{texts[idx]}"'
            for i, idx in enumerate(batch_indices)
        )
        prompt = (
            f"Classify each of the following Reddit post {task_name}s into exactly one category.\n\n"
            f"Categories:\n{cat_desc}\n\n"
            f"For each {task_name}, respond with just the number and category on one line, like:\n"
            f"1: category_name\n"
            f"2: category_name\n\n"
            f"{task_name.capitalize()}s:\n{items}\n\n"
            f"Respond with exactly {len(batch_indices)} lines, one per {task_name}."
        )

        try:
            response = llm_client.complete(prompt)
            parsed = _parse_numbered_classifications(response, categories)
            for i, idx in enumerate(batch_indices):
                if i < len(parsed) and parsed[i] in categories:
                    results[idx] = parsed[i]
                    _classification_cache[texts[idx]] = parsed[i]
        except Exception:
            logger.warning(
                "LLM classification failed for batch starting at %d, using heuristic fallback",
                batch_indices[0] if batch_indices else 0,
            )

    # Fall back to heuristic for any still-unclassified texts
    missing_indices = [i for i, r in enumerate(results) if r is None]
    if missing_indices:
        missing_texts = [texts[i] for i in missing_indices]
        fallback = batch_classify_heuristic(missing_texts, categories, HOOK_KEYWORDS)
        for j, idx in enumerate(missing_indices):
            results[idx] = fallback[j]
            _classification_cache[texts[idx]] = fallback[j]

    return [r for r in results if r is not None]


def _parse_numbered_classifications(response: str, categories: list[str]) -> list[str]:
    """Parse LLM response in 'N: category_name' format."""
    parsed = []
    cat_set = set(categories)
    for line in response.strip().split("\n"):
        line = line.strip()
        match = re.match(r"(\d+)[:.)]\s*(\S+)", line)
        if match:
            cat = match.group(2).lower().strip(".,;:!?\"'")
            # Try to find the category (may have extra chars)
            for valid_cat in cat_set:
                if valid_cat.lower() in cat or cat in valid_cat.lower():
                    cat = valid_cat
                    break
            if cat in cat_set:
                parsed.append(cat)
            else:
                parsed.append(categories[0])  # Default to first category
    return parsed
