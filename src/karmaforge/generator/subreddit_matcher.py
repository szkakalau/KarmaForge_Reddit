"""Match user topics to the best subreddits based on V1 keyword data."""

import json
import logging
from collections import Counter
from pathlib import Path

from ..analyzer.analysis_utils import keyword_extraction

logger = logging.getLogger(__name__)

# Topic → subreddit manual mapping for common themes (fallback when DB data is sparse)
TOPIC_HINTS: dict[str, list[str]] = {
    "productivity": ["productivity", "getdisciplined", "LifeProTips", "lifehacks"],
    "fitness": ["Fitness", "getdisciplined", "LifeProTips"],
    "health": ["Fitness", "science", "LifeProTips"],
    "money": ["personalfinance", "Entrepreneur", "LifeProTips"],
    "startup": ["startups", "Entrepreneur", "SideProject", "SaaS", "indiehackers"],
    "business": ["Entrepreneur", "startups", "SideProject", "SaaS"],
    "programming": ["programming", "selfhosted", "kubernetes", "SideProject"],
    "coding": ["programming", "selfhosted", "SideProject"],
    "developer": ["programming", "selfhosted", "kubernetes"],
    "devops": ["kubernetes", "selfhosted", "programming"],
    "homelab": ["selfhosted", "kubernetes", "programming"],
    "travel": ["travel", "digitalnomad"],
    "nomad": ["digitalnomad", "travel", "solopreneur"],
    "remote": ["digitalnomad", "solopreneur", "selfhosted"],
    "cooking": ["cooking", "lifehacks"],
    "food": ["cooking", "science", "lifehacks"],
    "recipe": ["cooking", "lifehacks"],
    "book": ["books", "philosophy", "history"],
    "reading": ["books", "philosophy"],
    "history": ["history", "AskHistorians", "todayilearned"],
    "philosophy": ["philosophy", "books", "AskHistorians"],
    "science": ["science", "todayilearned", "worldnews"],
    "psychology": ["science", "philosophy", "getdisciplined"],
    "finance": ["personalfinance", "Entrepreneur", "startups"],
    "investing": ["personalfinance", "Entrepreneur"],
    "career": ["getdisciplined", "Entrepreneur", "productivity", "digitalnomad"],
    "habit": ["getdisciplined", "productivity", "LifeProTips"],
    "discipline": ["getdisciplined", "productivity"],
    "motivation": ["GetMotivated", "getdisciplined", "Entrepreneur"],
    "life": ["LifeProTips", "Showerthoughts", "lifehacks", "getdisciplined"],
    "tip": ["LifeProTips", "lifehacks", "productivity"],
    "hack": ["lifehacks", "LifeProTips", "programming"],
    "saas": ["SaaS", "startups", "Entrepreneur", "SideProject", "indiehackers"],
    "sideproject": ["SideProject", "startups", "indiehackers", "programming"],
    "indie": ["indiehackers", "SideProject", "startups", "solopreneur"],
    "solopreneur": ["solopreneur", "indiehackers", "SideProject", "startups"],
    "selfhost": ["selfhosted", "kubernetes", "programming"],
    "server": ["selfhosted", "kubernetes", "programming"],
    "kubernetes": ["kubernetes", "selfhosted", "programming"],
    "docker": ["selfhosted", "kubernetes", "programming"],
    "automation": ["programming", "productivity", "selfhosted", "lifehacks"],
    "ai": ["programming", "SideProject", "startups", "science"],
    "machinelearning": ["programming", "science", "SideProject"],
    "question": ["AskReddit", "Showerthoughts", "todayilearned", "AskHistorians"],
    "story": ["AskReddit", "todayilearned", "Showerthoughts"],
    "news": ["worldnews", "todayilearned", "science"],
    "world": ["worldnews", "todayilearned", "travel"],
}


class SubredditMatcher:
    """Match user input text to the best-fit subreddits."""

    VALID_SUBREDDITS = {
        "AskReddit", "Showerthoughts", "todayilearned", "worldnews",
        "productivity", "Fitness", "personalfinance", "science", "books",
        "cooking", "lifehacks", "getdisciplined", "Entrepreneur", "GetMotivated",
        "LifeProTips", "history", "travel", "programming", "philosophy",
        "AskHistorians", "SaaS", "kubernetes", "digitalnomad", "selfhosted",
        "indiehackers", "startups", "SideProject", "solopreneur",
    }

    def __init__(self, db_path: str | None = None) -> None:
        self._sub_keywords: dict[str, list[str]] = {}
        self._sub_topics: dict[str, set[str]] = {}  # subreddit → known topic words

        if db_path:
            self._build_from_db(db_path)
        self._build_topic_hints()

    def _build_from_db(self, db_path: str) -> None:
        """Extract top keywords per subreddit from post titles in the database."""
        import sqlite3

        try:
            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT subreddit, GROUP_CONCAT(title, ' . ') "
                "FROM posts GROUP BY subreddit"
            ).fetchall()
            conn.close()
        except Exception:
            logger.warning("Failed to read DB for subreddit keyword index")
            return

        for subreddit, all_titles in rows:
            if not all_titles:
                continue
            titles = [t.strip() for t in all_titles.split(" . ") if t.strip()]
            if not titles:
                continue
            kw_list = keyword_extraction(titles, top_n=80, min_freq=3)
            self._sub_keywords[subreddit] = [k["word"] for k in kw_list]

    def _build_topic_hints(self) -> None:
        """Invert TOPIC_HINTS into subreddit → topics mapping."""
        for topic, subs in TOPIC_HINTS.items():
            for sub in subs:
                if sub not in self._sub_topics:
                    self._sub_topics[sub] = set()
                self._sub_topics[sub].add(topic)

    def match(self, input_text: str, limit: int = 5) -> list[tuple[str, float]]:
        """Match input text to subreddits. Returns [(subreddit, score), ...] sorted desc.

        Score: 0.0-1.0 where 1.0 = best match.
        """
        tokens = self._tokenize(input_text)

        # Direct subreddit name in input?  e.g. "r/productivity"
        for token in tokens:
            for sub in self.VALID_SUBREDDITS:
                if token.lower() == sub.lower():
                    return [(sub, 1.0)] + self._fallback_ranking(sub, limit - 1)

        # Check TOPIC_HINTS for exact topic matches
        hits: Counter = Counter()
        for topic, subs in TOPIC_HINTS.items():
            if topic.lower() in tokens or topic.lower() in input_text.lower():
                for s in subs:
                    hits[s] += 2  # strong signal

        # Check DB keyword index for partial matches
        for sub, keywords in self._sub_keywords.items():
            for kw in keywords[:30]:  # top 30 keywords per sub
                if kw.lower() in tokens:
                    hits[sub] += 1

        # Score: normalize by max possible and add tier bonus
        results: list[tuple[str, float]] = []
        for sub, raw in hits.most_common(limit * 2):
            score = min(raw / 5.0, 1.0)  # normalize
            results.append((sub, round(score, 2)))

        if not results:
            # Fallback: return popular general-interest subs
            return [("AskReddit", 0.4), ("LifeProTips", 0.3), ("Showerthoughts", 0.2)]

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def _fallback_ranking(self, exclude: str, limit: int) -> list[tuple[str, float]]:
        """Return additional subreddit suggestions after a direct match."""
        fallbacks = [
            ("LifeProTips", 0.5), ("getdisciplined", 0.4),
            ("productivity", 0.4), ("Showerthoughts", 0.3),
        ]
        return [(s, sc) for s, sc in fallbacks if s != exclude][:limit]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Lowercase tokenize and extract n-grams."""
        import re

        text = text.lower()
        tokens = set(re.findall(r"[a-z]{3,}", text))
        # Add 2-word bigrams
        words = re.findall(r"[a-z]{3,}", text)
        for i in range(len(words) - 1):
            tokens.add(f"{words[i]}{words[i+1]}")
        return tokens
