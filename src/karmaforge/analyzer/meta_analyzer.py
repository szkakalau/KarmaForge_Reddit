"""Meta data analysis — time, author, subreddit specificity, flair, velocity, controversy."""

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Union

import numpy as np

from ..storage import Post, Tier
from .analysis_utils import correlation_test, compute_distribution, chi_square_test


@dataclass
class MetaAnalysisResult:
    day_of_week_distribution: dict = field(default_factory=dict)
    hour_of_day_distribution: dict = field(default_factory=dict)
    best_time_matrix: dict = field(default_factory=dict)
    author_karma_correlation: dict = field(default_factory=dict)
    author_age_correlation: dict = field(default_factory=dict)
    author_factors_summary: dict = field(default_factory=dict)
    subreddit_preferences: dict = field(default_factory=dict)
    subreddit_specificity_scores: dict = field(default_factory=dict)
    flair_usage_rate: float = 0.0
    flair_type_distribution: dict = field(default_factory=dict)
    first_hour_velocity_correlation: dict = field(default_factory=dict)
    velocity_threshold: float = 0.0
    controversy_profile: dict = field(default_factory=dict)
    n: int = 0

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            if isinstance(v, tuple):
                d[k] = list(v)
            else:
                d[k] = v
        return d


class MetaAnalyzer:
    def __init__(self, significance_level: float = 0.05) -> None:
        self.alpha = significance_level

    def analyze(self, posts: list[Post]) -> MetaAnalysisResult:
        if not posts:
            return MetaAnalysisResult()

        result = MetaAnalysisResult()
        result.n = len(posts)

        result.day_of_week_distribution = self._analyze_day_of_week(posts)
        result.hour_of_day_distribution = self._analyze_hour_of_day(posts)
        result.best_time_matrix = self._build_time_matrix(posts)
        result.flair_usage_rate, result.flair_type_distribution = self._analyze_flair(posts)
        result.subreddit_preferences = self._analyze_subreddit_preferences(posts)
        result.subreddit_specificity_scores = self._compute_specificity_scores(posts)
        result.first_hour_velocity_correlation, result.velocity_threshold = self._first_hour_velocity(posts)
        result.controversy_profile = self._controversy_analysis(posts)

        return result

    def analyze_by_tier(self, posts: list[Post]) -> dict[Tier, MetaAnalysisResult]:
        groups: dict[Tier, list[Post]] = {}
        for p in posts:
            if p.tier:
                groups.setdefault(p.tier, []).append(p)
        return {tier: self.analyze(ps) for tier, ps in groups.items()}

    def _analyze_day_of_week(self, posts: list[Post]) -> dict:
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        dist = {}
        for day in days:
            dist[day] = {"count": 0, "total_upvotes": 0, "pct_viral": 0.0}

        timed_posts = [p for p in posts if p.created_utc]
        if not timed_posts:
            return dist

        for p in timed_posts:
            day = days[p.created_utc.weekday()]
            dist[day]["count"] += 1
            dist[day]["total_upvotes"] += p.upvotes

        viral = sorted([p.upvotes for p in timed_posts], reverse=True)[:max(1, len(timed_posts) // 10)]
        viral_threshold = viral[-1] if viral else 0

        for day in days:
            day_posts = [p for p in timed_posts if days[p.created_utc.weekday()] == day]
            if day_posts:
                dist[day]["avg_upvotes"] = round(dist[day]["total_upvotes"] / dist[day]["count"], 1)
                dist[day]["pct_viral"] = round(sum(1 for p in day_posts if p.upvotes >= viral_threshold) / len(day_posts), 3)
            else:
                dist[day]["avg_upvotes"] = 0
                dist[day]["pct_viral"] = 0.0

        return dist

    def _analyze_hour_of_day(self, posts: list[Post]) -> dict:
        dist = {}
        for h in range(24):
            dist[h] = {"count": 0, "total_upvotes": 0}

        timed_posts = [p for p in posts if p.created_utc]
        if not timed_posts:
            return dist

        for p in timed_posts:
            h = p.created_utc.hour
            dist[h]["count"] += 1
            dist[h]["total_upvotes"] += p.upvotes

        for h in range(24):
            if dist[h]["count"] > 0:
                dist[h]["avg_upvotes"] = round(dist[h]["total_upvotes"] / dist[h]["count"], 1)

        return dist

    def _build_time_matrix(self, posts: list[Post]) -> dict:
        timed_posts = [p for p in posts if p.created_utc]
        if not timed_posts:
            return {}

        all_upvotes = [p.upvotes for p in timed_posts]
        median = statistics.median(all_upvotes) if all_upvotes else 1.0

        matrix = defaultdict(list)
        for p in timed_posts:
            key = f"{p.created_utc.strftime('%a')}_{p.created_utc.hour:02d}"
            matrix[key].append(p.upvotes)

        result = {}
        for key, upvotes_list in matrix.items():
            result[key] = {
                "avg_upvotes": round(statistics.mean(upvotes_list), 1),
                "median_upvotes": round(statistics.median(upvotes_list), 1),
                "count": len(upvotes_list),
                "relative_score": round(statistics.median(upvotes_list) / max(median, 1), 2),
            }

        return result

    def _analyze_flair(self, posts: list[Post]) -> tuple[float, dict]:
        flaired = [p for p in posts if p.flair]
        rate = len(flaired) / max(len(posts), 1)

        flair_stats: dict = {}
        for p in flaired:
            flair = p.flair.lower()
            if flair not in flair_stats:
                flair_stats[flair] = {"count": 0, "total_upvotes": 0}
            flair_stats[flair]["count"] += 1
            flair_stats[flair]["total_upvotes"] += p.upvotes

        for flair in flair_stats:
            flair_stats[flair]["avg_upvotes"] = round(
                flair_stats[flair]["total_upvotes"] / flair_stats[flair]["count"], 1
            )

        return round(rate, 3), flair_stats

    def _analyze_subreddit_preferences(self, posts: list[Post]) -> dict:
        by_sub: dict = defaultdict(list)
        for p in posts:
            by_sub[p.subreddit.lower()].append(p)

        preferences = {}
        for sub, sub_posts in by_sub.items():
            title_words = [len(p.title.split()) for p in sub_posts if p.title]
            body_words = [len(p.body.split()) for p in sub_posts if p.body]
            preferences[sub] = {
                "optimal_title_length": (int(np.percentile(title_words, 25)), int(np.percentile(title_words, 75))) if title_words else (0, 0),
                "optimal_body_length": (int(np.percentile(body_words, 25)), int(np.percentile(body_words, 75))) if body_words else (0, 0),
                "median_upvotes": statistics.median([p.upvotes for p in sub_posts]) if sub_posts else 0,
                "sample_size": len(sub_posts),
            }

        return preferences

    def _compute_specificity_scores(self, posts: list[Post]) -> dict:
        by_sub: dict = defaultdict(list)
        for p in posts:
            by_sub[p.subreddit.lower()].append(p)

        global_title_words = [len(p.title.split()) for p in posts if p.title]
        global_body_words = [len(p.body.split()) for p in posts if p.body]
        global_title_median = statistics.median(global_title_words) if global_title_words else 0
        global_body_median = statistics.median(global_body_words) if global_body_words else 0

        scores = {}
        for sub, sub_posts in by_sub.items():
            if len(sub_posts) < 20:
                continue
            title_words = [len(p.title.split()) for p in sub_posts if p.title]
            body_words = [len(p.body.split()) for p in sub_posts if p.body]
            title_med = statistics.median(title_words) if title_words else 0
            body_med = statistics.median(body_words) if body_words else 0

            title_dev = abs(title_med - global_title_median) / max(global_title_median, 1)
            body_dev = abs(body_med - global_body_median) / max(global_body_median, 1)
            scores[sub] = round(min(1.0, (title_dev + body_dev) / 2), 3)

        return scores

    def _first_hour_velocity(self, posts: list[Post]) -> tuple[dict, float]:
        timed_posts = [p for p in posts if p.created_utc]
        if not timed_posts:
            return {}, 0.0

        velocities = []
        for p in timed_posts:
            hours_up = max(1, (datetime.now(timezone.utc) - p.created_utc).total_seconds() / 3600)
            velocity = p.upvotes / hours_up
            velocities.append(velocity)

        upvotes = [p.upvotes for p in timed_posts]
        correlation = correlation_test(velocities, upvotes[:len(velocities)])

        viral = sorted(upvotes, reverse=True)[:max(1, len(upvotes) // 10)]
        viral_velocities = sorted([velocities[i] for i in range(len(upvotes)) if upvotes[i] >= viral[-1]], reverse=True) if viral else [0]
        threshold = np.percentile(viral_velocities, 20) if viral_velocities else 0.0

        return correlation, round(float(threshold), 2)

    def _controversy_analysis(self, posts: list[Post]) -> dict:
        controversial = [p for p in posts if p.upvote_ratio > 0 and p.upvote_ratio < 0.75 and p.num_comments > 0]
        if not controversial:
            return {"description": "No controversial posts found", "avg_upvotes": 0, "avg_comments": 0}

        return {
            "description": "Low upvote ratio + high comment count posts",
            "count": len(controversial),
            "avg_upvotes": round(statistics.mean([p.upvotes for p in controversial]), 1),
            "avg_comments": round(statistics.mean([p.num_comments for p in controversial]), 1),
            "median_upvote_ratio": round(statistics.median([p.upvote_ratio for p in controversial]), 3),
            "avg_flair_usage": round(sum(1 for p in controversial if p.flair) / len(controversial), 3),
            "engagement_per_upvote": round(
                statistics.mean([p.num_comments / max(p.upvotes, 1) for p in controversial]), 3
            ),
        }
