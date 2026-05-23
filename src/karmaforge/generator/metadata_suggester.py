"""Suggest posting metadata: best time, flair, OC tag based on V1 analysis."""

import logging

logger = logging.getLogger(__name__)

# 最佳发帖日 + 小时（基于 V1 meta_analyzer 结果 — UTC）
BEST_TIMES = {
    "t1": {"day": "周一", "hour": 9},
    "t2": {"day": "周二", "hour": 14},
    "t3": {"day": "周三", "hour": 15},
}

# Common flairs by subreddit (from V1 reports)
SUB_FLAIRS: dict[str, list[str]] = {
    "productivity": ["Technique", "Tool", "Discussion", "Story"],
    "Fitness": ["Progress", "Guide", "Discussion", "Question"],
    "personalfinance": ["Budgeting", "Investing", "Planning", "Discussion"],
    "programming": ["Resource", "Tutorial", "Discussion", "Help"],
    "Entrepreneur": ["Story", "Advice", "Resource", "Discussion"],
    "startups": ["I made this", "Discussion", "Question", "Advice"],
    "SaaS": ["Resource", "Discussion", "I made this", "Question"],
    "SideProject": ["I made this", "Resource", "Discussion", "Showcase"],
    "indiehackers": ["I made this", "Revenue", "Discussion", "Question"],
    "selfhosted": ["Guide", "Resource", "Discussion", "Question"],
    "kubernetes": ["Tutorial", "Discussion", "Help", "Resource"],
    "digitalnomad": ["Discussion", "Question", "Story", "Advice"],
    "science": ["Research", "Discussion", "Question", "Article"],
    "history": ["Discussion", "Article", "Question", "Image"],
    "books": ["Discussion", "Review", "Question", "Recommendation"],
    "cooking": ["Recipe", "Question", "Discussion", "Tip"],
    "lifehacks": ["Tip", "Discussion", "Request", "Resource"],
    "getdisciplined": ["Advice", "Story", "Plan", "Method"],
    "GetMotivated": ["Image", "Story", "Discussion", "Advice"],
    "LifeProTips": ["LPT", "Request", "Discussion", "Tip"],
    "travel": ["Advice", "Story", "Question", "Image"],
    "philosophy": ["Discussion", "Question", "Article", "Argument"],
    "AskHistorians": ["Question", "Discussion", "Meta", "Feature"],
    "todayilearned": ["TIL", "Discussion", "Article"],
    "worldnews": ["News", "Discussion", "Analysis"],
    "AskReddit": ["Serious", "Discussion", "Question"],
    "Showerthoughts": ["Thought", "Discussion"],
    "solopreneur": ["Discussion", "Story", "Question", "Resource"],
}


class MetadataSuggester:
    """Provide posting metadata recommendations."""

    def suggest(self, subreddit: str, tier: str, user_topic: str = "") -> dict:
        """Return recommended metadata for posting."""
        time_info = BEST_TIMES.get(tier, BEST_TIMES["t2"])
        flairs = SUB_FLAIRS.get(subreddit, ["Discussion", "Question"])
        recommended_flair = self._pick_flair(flairs, user_topic)

        return {
            "推荐发帖日": time_info["day"],
            "推荐发帖时间(UTC)": time_info["hour"],
            "推荐Flair": recommended_flair,
            "标记为OC": self._should_mark_oc(subreddit, user_topic),
        }

    @staticmethod
    def _pick_flair(available: list[str], topic: str) -> str:
        """Pick the best flair from available options based on topic."""
        topic_lower = topic.lower()
        priority_order = [
            ("Resource", ["tool", "resource", "build", "made", "app", "script", "guide", "template"]),
            ("Tutorial", ["tutorial", "guide", "how to", "learn", "step"]),
            ("I made this", ["build", "made", "created", "launched", "my", "project", "app"]),
            ("Guide", ["guide", "tutorial", "walkthrough", "setup"]),
            ("Story", ["journey", "story", "experience", "learned", "year"]),
            ("Advice", ["advice", "tip", "suggestion", "help", "question"]),
            ("Discussion", ["discuss", "think", "opinion", "thought"]),
            ("Question", ["question", "anyone", "help", "how do", "why"]),
        ]

        for flair, keywords in priority_order:
            if flair in available and any(kw in topic_lower for kw in keywords):
                return flair

        return available[0]

    @staticmethod
    def _should_mark_oc(subreddit: str, topic: str) -> bool:
        """Determine if post should be marked as OC (Original Content)."""
        oc_subs = {
            "programming", "selfhosted", "SideProject", "SaaS", "startups",
            "indiehackers", "Entrepreneur", "Fitness", "cooking",
        }
        personal_signals = ["my", "i built", "i made", "i created", "my project",
                           "i've been", "i started", "my journey"]
        topic_lower = topic.lower()
        return subreddit in oc_subs and any(s in topic_lower for s in personal_signals)
