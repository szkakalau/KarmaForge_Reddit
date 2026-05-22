"""Visual content analysis — content type distribution, image-text coordination, media ROI."""

from dataclasses import dataclass, field
from typing import Optional

from ..storage import Post, ContentType, Tier


@dataclass
class VisualAnalysisResult:
    content_type_distribution: dict = field(default_factory=dict)
    image_text_coordination: dict = field(default_factory=dict)
    text_vs_rich_media_roi: dict = field(default_factory=dict)
    subreddit_content_preferences: dict = field(default_factory=dict)
    n: int = 0

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            d[k] = list(v) if isinstance(v, tuple) else v
        return d


class VisualAnalyzer:
    def __init__(self, llm_client=None) -> None:
        self.llm = llm_client

    def analyze(self, posts: list[Post]) -> VisualAnalysisResult:
        if not posts:
            return VisualAnalysisResult()

        result = VisualAnalysisResult()
        result.n = len(posts)
        result.content_type_distribution = self._content_type_stats(posts)
        result.subreddit_content_preferences = self._subreddit_preferences(posts)
        result.image_text_coordination = self._image_text_coordination(posts)
        result.text_vs_rich_media_roi = self._roi_comparison(posts)

        return result

    def analyze_by_subreddit(self, posts: list[Post]) -> dict[str, VisualAnalysisResult]:
        groups: dict[str, list[Post]] = {}
        for p in posts:
            groups.setdefault(p.subreddit.lower(), []).append(p)
        return {sub: self.analyze(ps) for sub, ps in groups.items()}

    def _content_type_stats(self, posts: list[Post]) -> dict:
        by_type: dict = {}
        for p in posts:
            ct = p.content_type.value
            if ct not in by_type:
                by_type[ct] = {"count": 0, "total_upvotes": 0}
            by_type[ct]["count"] += 1
            by_type[ct]["total_upvotes"] += p.upvotes

        total = len(posts)
        viral_90 = sorted([p.upvotes for p in posts], reverse=True)
        viral_threshold = viral_90[max(0, len(viral_90) // 10)] if viral_90 else 0

        for ct in by_type:
            ct_posts = [p for p in posts if p.content_type.value == ct]
            by_type[ct]["avg_upvotes"] = round(by_type[ct]["total_upvotes"] / by_type[ct]["count"], 1)
            by_type[ct]["pct_total"] = round(by_type[ct]["count"] / total, 3)
            by_type[ct]["pct_viral"] = round(
                sum(1 for p in ct_posts if p.upvotes >= viral_threshold) / max(len(ct_posts), 1), 3
            )

        return by_type

    def _subreddit_preferences(self, posts: list[Post]) -> dict:
        by_sub: dict = {}
        for p in posts:
            sub = p.subreddit.lower()
            if sub not in by_sub:
                by_sub[sub] = {}
            ct = p.content_type.value
            by_sub[sub][ct] = by_sub[sub].get(ct, 0) + 1

        preferences = {}
        for sub, ct_counts in by_sub.items():
            dominant = max(ct_counts, key=ct_counts.get)
            preferences[sub] = {
                "dominant_type": dominant,
                "dominant_pct": round(ct_counts[dominant] / sum(ct_counts.values()), 3),
                "type_distribution": ct_counts,
            }

        return preferences

    def _image_text_coordination(self, posts: list[Post]) -> dict:
        img_posts = [p for p in posts if p.content_type == ContentType.IMAGE]
        if not img_posts:
            return {"note": "No image posts to analyze"}

        title_lengths = [len(p.title.split()) for p in img_posts]
        has_number = sum(1 for p in img_posts if any(c.isdigit() for c in p.title))
        has_question = sum(1 for p in img_posts if p.title.strip().endswith("?"))

        return {
            "sample_size": len(img_posts),
            "avg_title_words": round(sum(title_lengths) / len(title_lengths), 1),
            "number_in_title_rate": round(has_number / len(img_posts), 3),
            "question_in_title_rate": round(has_question / len(img_posts), 3),
            "avg_upvotes": round(sum(p.upvotes for p in img_posts) / len(img_posts), 1),
            "image_posts_pct_viral": round(
                sum(1 for p in posts if p.content_type == ContentType.IMAGE and p.upvotes >= sum(p.upvotes for p in posts) / len(posts)) / max(len(img_posts), 1), 3
            ),
        }

    def _roi_comparison(self, posts: list[Post]) -> dict:
        text_posts = [p for p in posts if p.content_type == ContentType.TEXT]
        image_posts = [p for p in posts if p.content_type == ContentType.IMAGE]
        video_posts = [p for p in posts if p.content_type == ContentType.VIDEO]

        result = {}
        for label, ps in [("text", text_posts), ("image", image_posts), ("video", video_posts)]:
            if ps:
                result[label] = {
                    "count": len(ps),
                    "avg_upvotes": round(sum(p.upvotes for p in ps) / len(ps), 1),
                    "avg_comments": round(sum(p.num_comments for p in ps) / len(ps), 1),
                    "avg_upvote_ratio": round(sum(p.upvote_ratio for p in ps) / len(ps), 3),
                }

        if text_posts:
            text_avg = result.get("text", {}).get("avg_upvotes", 1)
            for ct in ["image", "video"]:
                if ct in result:
                    result[ct]["upvote_boost_vs_text"] = round(
                        result[ct]["avg_upvotes"] / max(text_avg, 1), 2
                    )

        return result
