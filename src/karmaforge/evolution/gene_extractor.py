"""Gene extractor — mine structural templates from successful posts.

Extracts reusable "genetic material" from viral/super_viral posts:
1. Title structure templates (abstracted word patterns)
2. Body opening patterns (first-sentence type classification)
3. Call-to-action (CTA) patterns from post endings

These templates are injected into generation prompts so the LLM
learns from what actually worked, not just the statistical pattern.
"""

import json
import logging
import re
from collections import Counter
from pathlib import Path

logger = logging.getLogger(__name__)

# Maximum templates to store per pattern (prevents unbounded growth)
MAX_TEMPLATES_PER_PATTERN = 10
# Minimum upvotes to consider a post "successful" for gene extraction
MIN_SUCCESS_UPVOTES = 50


class GeneExtractor:
    """Extract and manage successful content templates from feedback data."""

    # ── Public API ───────────────────────────────────────────────

    def extract_from_feedback(
        self,
        feedback_path: str | Path,
        patterns: list[dict],
    ) -> list[dict]:
        """Extract gene templates from feedback and attach to patterns.

        Returns the modified patterns list (mutated in-place).
        """
        fb_path = Path(feedback_path)
        if not fb_path.exists():
            logger.warning("Feedback file not found: %s", fb_path)
            return patterns

        # Group successful entries by pattern_id
        by_pattern: dict[str, list[dict]] = {}
        with open(fb_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                perf = entry.get("performance", "")
                if perf not in ("viral", "super_viral"):
                    continue
                if entry.get("actual_upvotes", 0) < MIN_SUCCESS_UPVOTES:
                    continue

                pid = entry.get("pattern_id", "")
                if pid:
                    by_pattern.setdefault(pid, []).append(entry)

        # Build pattern lookup
        pattern_map = {p.get("pattern_id", ""): p for p in patterns}

        for pid, entries in by_pattern.items():
            pattern = pattern_map.get(pid)
            if not pattern:
                continue

            templates = pattern.setdefault("successful_templates", [])

            for entry in entries:
                title = entry.get("title", "")
                body = entry.get("body", "")

                gene = {
                    "title_template": self._abstract_title(title),
                    "title_original": title[:200],
                    "body_opening": self._classify_opening(body),
                    "cta_pattern": self._extract_cta(body),
                    "upvotes": entry.get("actual_upvotes", 0),
                    "subreddit": entry.get("subreddit", ""),
                }

                # Deduplicate — only add if title_template is new
                existing_templates = {
                    t.get("title_template", "") for t in templates
                }
                if gene["title_template"] not in existing_templates:
                    templates.append(gene)

            # Trim to max
            if len(templates) > MAX_TEMPLATES_PER_PATTERN:
                # Keep highest-upvote templates
                templates.sort(key=lambda t: t.get("upvotes", 0), reverse=True)
                pattern["successful_templates"] = templates[:MAX_TEMPLATES_PER_PATTERN]

            logger.info(
                "Gene extraction: pattern %s → %d templates",
                pid, len(pattern.get("successful_templates", [])),
            )

        return patterns

    def inject_into_title_prompt(
        self, base_prompt: str, pattern: dict, max_examples: int = 2
    ) -> str:
        """Augment a title generation prompt with successful templates."""
        templates = pattern.get("successful_templates", [])
        if not templates:
            return base_prompt

        # Sort by upvotes, pick top N
        best = sorted(templates, key=lambda t: t.get("upvotes", 0), reverse=True)
        best = best[:max_examples]

        lines = [
            base_prompt,
            "",
            "参考以下已验证成功的标题结构（不要直接复制，借鉴其节奏和模式）：",
        ]
        for i, t in enumerate(best, 1):
            lines.append(
                f"  {i}. 模板: {t['title_template']}\n"
                f"     原文: {t['title_original']}\n"
                f"     数据: {t['upvotes']} upvotes, r/{t['subreddit']}"
            )

        return "\n".join(lines)

    def inject_into_body_prompt(
        self, base_prompt: str, pattern: dict, max_examples: int = 2
    ) -> str:
        """Augment a body generation prompt with successful opening + CTA patterns."""
        templates = pattern.get("successful_templates", [])
        if not templates:
            return base_prompt

        best = sorted(templates, key=lambda t: t.get("upvotes", 0), reverse=True)
        best = best[:max_examples]

        openings = [t["body_opening"] for t in best if t.get("body_opening")]
        ctas = [t["cta_pattern"] for t in best if t.get("cta_pattern")]

        lines = [base_prompt]
        if openings:
            lines.append("\n成功的正文开头模式：")
            for o in set(openings):
                lines.append(f"  - {o}")
        if ctas:
            lines.append("\n成功的结尾互动模式：")
            for c in set(ctas):
                lines.append(f"  - {c}")

        return "\n".join(lines)

    # ── Title abstraction ────────────────────────────────────────

    @staticmethod
    def _abstract_title(title: str) -> str:
        """Convert a concrete title into an abstracted template.

        Replaces numbers with N, preserves key structural words,
        collapses specific nouns into category placeholders.
        """
        if not title:
            return ""

        template = title.strip()

        # Replace numbers (digits or word numbers)
        template = re.sub(r'\b\d+(?:[,.]\d+)*\b', 'N', template)
        template = re.sub(
            r'\b(one|two|three|four|five|six|seven|eight|nine|ten|'
            r'eleven|twelve|twenty|thirty|forty|fifty|hundred|thousand|'
            r'million|billion)\b',
            'N', template, flags=re.IGNORECASE,
        )

        # Collapse repeated N's
        template = re.sub(r'(N\s*)+N', 'N', template)
        # Fix "N N" → "N"
        template = re.sub(r'N\s+N', 'N', template)

        # Replace time expressions
        template = re.sub(
            r'\b(seconds?|minutes?|hours?|days?|weeks?|months?|years?)\b',
            '[time_unit]', template, flags=re.IGNORECASE,
        )
        template = re.sub(
            r'\b(today|yesterday|tomorrow|now|just|finally)\b',
            '[time]', template, flags=re.IGNORECASE,
        )

        # Replace dollar amounts
        template = re.sub(r'\$\s*N', '$N', template)
        template = re.sub(r'N\s*(dollars?|bucks?)', '$N', template, flags=re.IGNORECASE)

        # Replace percentages
        template = re.sub(r'N\s*%', 'N%', template)
        template = re.sub(r'N\s*percent', 'N%', template, flags=re.IGNORECASE)

        return template

    # ── Body analysis ────────────────────────────────────────────

    @staticmethod
    def _classify_opening(body: str) -> str:
        """Classify the opening style of a post body."""
        if not body or len(body) < 30:
            return "短正文/无正文开头"

        first_sentence = body.split(".")[0].strip()[:200].lower()

        # Data-driven opening
        if re.search(r'\d+', first_sentence) and any(
            w in first_sentence for w in ["tracked", "measured", "data", "stats", "numbers", "%", "hours", "days"]
        ):
            return "数据开头 (具体数字+追踪结果)"

        # Personal story opening
        if re.match(r'\b(i|my|we|our)\b', first_sentence):
            if any(w in first_sentence for w in ["built", "made", "created", "started", "launched", "learned", "discovered"]):
                return "个人成果开头 (I built/made/created → 结果)"
            if any(w in first_sentence for w in ["struggled", "failed", "tried", "quit", "lost"]):
                return "个人挣扎开头 (struggle → 转变 → 教训)"
            return "个人叙述开头 (第一人称经历)"

        # Question opening
        if "?" in first_sentence:
            return "提问开头 (以问题引发思考)"

        # Problem → solution opening
        if any(w in first_sentence for w in ["problem", "issue", "challenge", "pain", "hard", "difficult"]):
            return "问题-解决开头 (指出痛点 → 提供方案)"

        # Controversial/opinion opening
        if any(w in first_sentence for w in ["unpopular", "controversial", "hot take", "change my mind"]):
            return "争议观点开头 (挑衅性陈述)"

        return "通用开头"

    @staticmethod
    def _extract_cta(body: str) -> str:
        """Extract the call-to-action pattern from the end of a post body."""
        if not body or len(body) < 50:
            return ""

        # Take last ~200 chars as the ending
        ending = body[-200:].strip().lower()

        patterns = [
            (r"(what|how|has anyone|does anyone|anyone else).*\?$", "提问式CTA (开放问题结尾)"),
            (r"(let me know|tell me|share your|drop your|comment).*", "直接邀请CTA (tell me / share your)"),
            (r"(would love|curious|interested).*(hear|know|see|learn).*", "温和邀请CTA (would love to hear)"),
            (r"(hope this helps|hope you found|thanks for reading|tl;dr)", "价值总结CTA (hope this helps)"),
            (r"(what do you think|agree|disagree|thoughts).*\??$", "观点征求CTA (what do you think)"),
        ]

        for regex, label in patterns:
            if re.search(regex, ending, re.MULTILINE):
                return label

        # Detect if last sentence is a question
        last_sentence = body.strip().split(".")[-1].strip()
        if "?" in last_sentence:
            return "提问式CTA (以问题结尾)"

        return "自然结尾 (无明显CTA)"
