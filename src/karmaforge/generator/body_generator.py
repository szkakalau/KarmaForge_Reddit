"""Generate Reddit post body from pattern structure + LLM."""

import logging

from ..llm.prompts import BODY_GENERATE

logger = logging.getLogger(__name__)

# Default body word count targets by tier
TIER_BODY_RANGES = {
    "t1": (50, 400),
    "t2": (100, 600),
    "t3": (150, 800),
}


class BodyGenerator:
    """Generate post body text guided by pattern structure."""

    def __init__(self, llm_client=None) -> None:
        self._llm = llm_client

    def generate(
        self,
        title: str,
        pattern: dict,
        user_topic: str,
        subreddit: str,
        subreddit_tier: str = "t2",
    ) -> tuple[str, dict]:
        """Generate body text. Returns (body_text, metrics_dict)."""
        if self._llm:
            body = self._generate_with_llm(
                title, pattern, user_topic, subreddit, subreddit_tier
            )
        else:
            body = self._generate_heuristic(title, pattern, user_topic, subreddit)

        metrics = {
            "word_count": len(body.split()),
            "paragraphs": len([p for p in body.split("\n\n") if p.strip()]),
            "has_engagement_hook": self._check_engagement(body),
        }

        return body, metrics

    def _generate_with_llm(
        self, title: str, pattern: dict, user_topic: str, subreddit: str, tier: str
    ) -> str:
        """LLM-powered body generation."""
        metrics = pattern.get("recommended_metrics", {})
        body_range = metrics.get("body_words") or TIER_BODY_RANGES.get(tier, (100, 600))

        # Fall back to tier defaults for no_body patterns (image/link posts)
        if body_range[1] <= 1:
            body_range = TIER_BODY_RANGES.get(tier, (100, 600))

        body_structure = pattern.get("body_structure_template", "")
        narrative = pattern.get("narrative_mode", "")
        hook = pattern.get("hook_type", "")

        structure_reqs = []
        if narrative == "tutorial_howto":
            structure_reqs.append("Structure as step-by-step. Each step clearly labeled.")
        elif narrative == "story_personal":
            structure_reqs.append("Personal narrative style. Open with the moment of realization.")
        elif narrative == "opinion_argument":
            structure_reqs.append("State your position clearly, then defend with evidence.")
        elif narrative == "resource_showcase":
            structure_reqs.append("Describe what you built, why, and how others can use it.")
        structure_reqs.append("Use natural paragraph breaks, not markdown headings.")

        subreddit_notes = self._subreddit_style_notes(subreddit, tier)

        prompt = BODY_GENERATE.format(
            title=title,
            pattern_name=pattern.get("name", ""),
            hook_type=hook,
            narrative_mode=narrative,
            body_structure=body_structure or "Standard Reddit post structure",
            user_topic=user_topic,
            subreddit=subreddit,
            subreddit_notes=subreddit_notes,
            min_words=body_range[0],
            max_words=body_range[1],
            target_readability_min=60,
            target_readability_max=80,
            structure_requirements="\n- ".join(structure_reqs) if structure_reqs else "",
        )

        try:
            result = self._llm.complete(prompt, "")
            return result.strip()
        except Exception as e:
            logger.warning("LLM body generation failed: %s", e)
            return self._generate_heuristic(title, pattern, user_topic, subreddit)

    def _generate_heuristic(
        self, title: str, pattern: dict, user_topic: str, subreddit: str
    ) -> str:
        """Template-based body fallback when no LLM."""
        metrics = pattern.get("recommended_metrics", {})
        body_range = metrics.get("body_words", [50, 600])
        # Fall back to tier defaults for no_body patterns (image/link posts)
        if body_range[1] <= 1:
            body_range = [100, 600]

        hook = pattern.get("hook_type", "")
        narrative = pattern.get("narrative_mode", "")

        topic = f'"{user_topic}"'
        if narrative == "tutorial_howto":
            return (
                f"I wanted to share a practical guide about {topic}.\n\n"
                f"Here's the step-by-step process I followed:\n\n"
                f"1. First, understand the core problem\n"
                f"2. Then, find the right approach\n"
                f"3. Finally, execute and iterate\n\n"
                f"I hope this helps anyone dealing with similar challenges. "
                f"Happy to answer questions in the comments."
            )
        elif hook == "story_opener" or narrative == "story_personal":
            return (
                f"I've been working on {topic} for a while now, "
                f"and I wanted to share my experience.\n\n"
                f"The journey hasn't been straightforward — there were "
                f"plenty of lessons along the way.\n\n"
                f"The key insight I gained was that most advice out there "
                f"misses the mark. What actually worked for me was different.\n\n"
                f"Would love to hear if others have had similar experiences."
            )
        elif hook == "resource_share" or narrative == "resource_showcase":
            return (
                f"I built {topic} and wanted to share it with this community.\n\n"
                f"The motivation was simple: I couldn't find an existing solution "
                f"that worked well, so I decided to create my own.\n\n"
                f"Here's what makes it different: [specific differentiator].\n\n"
                f"Let me know what you think — feedback and suggestions welcome."
            )
        elif hook == "curious_question":
            return (
                f"I've been thinking about {topic} lately "
                f"and wanted to get the community's perspective.\n\n"
                f"Specifically, I'm curious about [specific aspect]. "
                f"Has anyone here looked into this?\n\n"
                f"Would appreciate any insights or resources."
            )
        else:
            return (
                f"I wanted to share some thoughts on {topic}.\n\n"
                f"This is something I've spent time on and learned from.\n\n"
                f"I'm curious what others in r/{subreddit} think about this — "
                f"have you had similar experiences?"
            )

    @staticmethod
    def _check_engagement(body: str) -> bool:
        """Check if body ends with a question or community call."""
        last_sentence = body.strip().split(".")[-1].strip()
        return "?" in last_sentence or any(
            phrase in last_sentence.lower()
            for phrase in ["thoughts", "feedback", "experience", "let me know", "would love"]
        )

    @staticmethod
    def _subreddit_style_notes(subreddit: str, tier: str) -> str:
        """Body-specific subreddit style guidance."""
        notes = {
            "Fitness": "Include specific numbers (weight, reps, duration). Be honest about timeline.",
            "programming": "Include code snippets or architecture details. Link to repo if relevant.",
            "personalfinance": "Use specific dollar amounts. Be transparent about numbers.",
            "Entrepreneur": "Share metrics (revenue, users, churn). Be concrete, not motivational.",
            "SaaS": "Include MRR, churn, CAC if possible. Technical detail expected.",
            "science": "Cite specific papers. Distinguish findings from speculation.",
            "AskHistorians": "Cite sources. In-depth analysis expected. No layperson speculation.",
        }
        return notes.get(subreddit, "")
