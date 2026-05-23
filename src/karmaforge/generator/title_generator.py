"""Generate Reddit post titles from viral patterns + LLM."""

import logging

from ..llm.prompts import TITLE_GENERATE
from . import CandidateTitle

logger = logging.getLogger(__name__)

# Default title word count ranges by subreddit tier
TIER_TITLE_RANGES = {
    "t1": (10, 25),
    "t2": (8, 22),
    "t3": (6, 18),
}


class TitleGenerator:
    """Generate and score candidate Reddit post titles."""

    def __init__(self, llm_client=None) -> None:
        self._llm = llm_client

    def generate(
        self,
        user_topic: str,
        patterns: list[dict],
        subreddit: str,
        subreddit_tier: str = "t2",
    ) -> list[CandidateTitle]:
        """Generate one title per pattern, return scored candidates."""
        candidates: list[CandidateTitle] = []

        for pattern in patterns:
            if self._llm:
                title = self._generate_with_llm(
                    user_topic, pattern, subreddit, subreddit_tier
                )
            else:
                title = self._generate_heuristic(
                    user_topic, pattern, subreddit
                )

            if not title:
                continue

            score = self._score_title(title, pattern, subreddit_tier)
            candidates.append(CandidateTitle(
                title=title.strip(),
                score=score,
                hook_type=pattern.get("hook_type", "unknown"),
                pattern_id=pattern.get("pattern_id", ""),
            ))

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates

    def _generate_with_llm(
        self, user_topic: str, pattern: dict, subreddit: str, tier: str
    ) -> str:
        """Use LLM to generate a title following the pattern."""
        metrics = pattern.get("recommended_metrics", {})
        title_range = metrics.get("title_words") or TIER_TITLE_RANGES.get(tier, (8, 22))

        subreddit_notes = self._subreddit_style_notes(subreddit, tier)

        prompt = TITLE_GENERATE.format(
            pattern_name=pattern.get("name", ""),
            pattern_description=pattern.get("description", ""),
            hook_type=pattern.get("hook_type", ""),
            user_topic=user_topic,
            subreddit=subreddit,
            subreddit_notes=subreddit_notes,
            min_words=title_range[0],
            max_words=title_range[1],
        )

        try:
            result = self._llm.complete(prompt, "")
            return result.strip().strip('"').strip("'")
        except Exception as e:
            logger.warning("LLM title generation failed: %s", e)
            return self._generate_heuristic(user_topic, pattern, subreddit)

    def _generate_heuristic(
        self, user_topic: str, pattern: dict, subreddit: str
    ) -> str:
        """Rule-based title from pattern hook_type + user topic."""
        hook = pattern.get("hook_type", "")
        title_tmpl = pattern.get("title_template", "")

        # Use extracted title template if available (pipe-separated bigrams)
        if title_tmpl and "|" in title_tmpl:
            phrases = title_tmpl.split("|")
            if phrases:
                return f"{phrases[0].strip().title()} — {user_topic}"

        topic = f'"{user_topic}"'
        templates = {
            "tutorial_howto": f"A practical guide to {topic}",
            "resource_share": f"I built {topic} and wanted to share it",
            "story_opener": f"My experience with {topic}: what I learned along the way",
            "curious_question": f"{topic} — why does it work the way it does?",
            "counterintuitive_discovery": f"I discovered something unexpected about {topic}",
            "controversial_opinion": f"Unpopular opinion: {topic}",
            "pain_point": f"The real problem with {topic} that nobody talks about",
            "comparison_analysis": f"{topic}: a comprehensive comparison",
            "identity_label": f"As someone who works with {topic}, here's my take",
            "number_shock": f"10 things I learned about {topic}",
            "suspense_mystery": f"What nobody tells you about {topic}",
        }
        return templates.get(hook, f"{topic} — my experience and insights")

    def _score_title(self, title: str, pattern: dict, tier: str) -> float:
        """Score a title on 0-100 scale. Deterministic rules only."""
        score = 50.0
        words = len(title.split())
        metrics = pattern.get("recommended_metrics", {})
        title_range = metrics.get("title_words") or TIER_TITLE_RANGES.get(tier, (8, 22))

        # Word count fit (+/- 30)
        if title_range[0] <= words <= title_range[1]:
            score += 30
        elif abs(words - title_range[0]) <= 3 or abs(words - title_range[1]) <= 3:
            score += 15

        # Anti-clickbait signals (-20)
        clickbait_markers = [
            "you won't believe", "mind blown", "this one trick",
            "doctors hate", "shocking truth", "???",
        ]
        for marker in clickbait_markers:
            if marker.lower() in title.lower():
                score -= 10

        # Punctuation sanity (no excessive ! or ?)
        if title.count("!") > 1:
            score -= 5
        if title.count("?") > 1:
            score -= 3

        # First letter capitalized
        if title[0].isupper():
            score += 10

        # Length sanity
        if words < 3:
            score -= 20
        if words > 50:
            score -= 15

        return max(0.0, min(100.0, score))

    @staticmethod
    def _subreddit_style_notes(subreddit: str, tier: str) -> str:
        """Brief style guidance for the subreddit."""
        notes = {
            "AskReddit": "Must be an open-ended question. No body text in the post itself.",
            "Showerthoughts": "A profound or clever observation. Short and universal.",
            "todayilearned": "Start with 'TIL' or 'TIL that'. Factual, specific.",
            "worldnews": "Factual headline style. No opinion. Cite sources.",
            "Fitness": "Specific, actionable. Numbers and progress are valued.",
            "science": "Cite the study. Objective tone. No anecdotal claims.",
            "programming": "Technical depth appreciated. Specific language/framework if relevant.",
            "personalfinance": "Specific numbers. Realistic. Not get-rich-quick.",
            "getdisciplined": "Actionable, personal experience. Not preachy.",
            "LifeProTips": "Start with 'LPT:' prefix. Universally useful tip.",
            "Entrepreneur": "Concrete business insight. Not motivational fluff.",
            "SaaS": "Specific metrics. Technical or business detail.",
            "kubernetes": "Technical depth. Specific versions/configs.",
            "selfhosted": "Practical setup. Docker/compose examples valued.",
        }

        base = notes.get(subreddit, "")
        tier_note = {
            "t1": "Broad appeal, avoid jargon.",
            "t2": "Some domain knowledge expected.",
            "t3": "Niche audience, technical depth welcome.",
        }.get(tier, "")

        return f"{base} {tier_note}".strip()
