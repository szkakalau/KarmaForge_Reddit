"""Lifecycle & propagation analysis — growth curves, cross-subreddit spread."""

import math
from collections import defaultdict
from dataclasses import dataclass, field

from ..storage import Post


@dataclass
class LifecycleAnalysisResult:
    growth_curve_types: dict = field(default_factory=dict)
    cross_subreddit_graph: dict = field(default_factory=dict)
    propagation_common_paths: list[dict] = field(default_factory=list)
    spread_probability_by_content: dict = field(default_factory=dict)
    n: int = 0

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            d[k] = list(v) if isinstance(v, tuple) else v
        return d


class LifecycleAnalyzer:
    def analyze(
        self,
        posts: list[Post],
        crossref_data: list[dict] | None = None,
    ) -> LifecycleAnalysisResult:
        result = LifecycleAnalysisResult()
        result.n = len(posts)

        result.growth_curve_types = self._classify_growth_curves(posts)

        if crossref_data:
            result.cross_subreddit_graph = self._build_propagation_graph(crossref_data)
            result.propagation_common_paths = self._find_propagation_paths(result.cross_subreddit_graph)
            result.spread_probability_by_content = self._spread_probability(posts, crossref_data)

        return result

    def _classify_growth_curves(self, posts: list[Post]) -> dict:
        curves = {"logarithmic": 0, "exponential": 0, "impulsive": 0, "linear": 0, "bimodal": 0, "unknown": 0}

        for p in posts:
            if p.upvotes <= 0:
                curves["unknown"] += 1
                continue

            if p.created_utc:
                import datetime as dt
                hours_up = max(1, (dt.datetime.now(dt.timezone.utc) - p.created_utc).total_seconds() / 3600)
                velocity = p.upvotes / hours_up
                comment_ratio = p.num_comments / max(p.upvotes, 1)

                if velocity > 100:
                    curves["exponential"] += 1
                elif comment_ratio > 1.5 and p.upvotes > 100:
                    curves["impulsive"] += 1
                elif comment_ratio > 0.5 and p.upvotes > 500:
                    curves["bimodal"] += 1
                elif 0.05 < comment_ratio < 0.5:
                    curves["linear"] += 1
                else:
                    curves["logarithmic"] += 1
            else:
                curves["unknown"] += 1

        total = max(sum(curves.values()), 1)
        return {
            k: {"count": v, "pct": round(v / total, 3)}
            for k, v in sorted(curves.items(), key=lambda x: x[1], reverse=True)
        }

    def _build_propagation_graph(self, crossref_data: list[dict]) -> dict:
        edges: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for ref in crossref_data:
            source = ref.get("source_subreddit", "").replace("r/", "")
            if source and "target_post_id" in ref:
                edges[source]["__count__"] += 1

        return {k: dict(v) for k, v in edges.items()}

    def _find_propagation_paths(self, graph: dict) -> list[dict]:
        paths = []
        for source, targets in graph.items():
            keys = [k for k in targets if k != "__count__"]
            if keys:
                total = max(targets.get("__count__", 1), 1)
                for target in keys:
                    paths.append({
                        "source": source,
                        "target": target,
                        "count": targets[target],
                        "pct_of_source": round(targets[target] / total, 3),
                    })

        return sorted(paths, key=lambda x: x["count"], reverse=True)[:20]

    def _spread_probability(self, posts: list[Post], crossref_data: list[dict]) -> dict:
        by_type: dict = defaultdict(lambda: {"total": 0, "crossposted": 0})

        post_ids_in_crossref = set()
        for ref in crossref_data:
            if "target_post_id" in ref:
                post_ids_in_crossref.add(ref["target_post_id"])

        for p in posts:
            ct = p.content_type.value
            by_type[ct]["total"] += 1
            if p.post_id and p.post_id in post_ids_in_crossref:
                by_type[ct]["crossposted"] += 1

        result = {}
        for ct, stats in by_type.items():
            result[ct] = {
                "total": stats["total"],
                "crossposted": stats["crossposted"],
                "spread_probability": round(stats["crossposted"] / max(stats["total"], 1), 4),
            }

        return result
