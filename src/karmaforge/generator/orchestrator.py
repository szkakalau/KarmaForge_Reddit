"""Generator orchestrator — wires the full generation pipeline."""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import CandidateTitle, GenerationResult, SelfCheckReport
from .subreddit_matcher import SubredditMatcher
from .pattern_selector import PatternSelector
from .title_generator import TitleGenerator
from .body_generator import BodyGenerator
from .metadata_suggester import MetadataSuggester
from .self_checker import SelfChecker

logger = logging.getLogger(__name__)

OUTPUT_DIR_DEFAULT = Path("data/generations")


class GeneratorOrchestrator:
    """Full post generation pipeline: input → title candidates → body → metadata → self-check."""

    def __init__(
        self,
        db_path: str = "data/processed/karmaforge.db",
        patterns_path: str = "data/patterns/patterns.json",
        anti_patterns_path: str = "data/patterns/anti_patterns.json",
        llm_client=None,
        output_dir: str | Path | None = None,
    ) -> None:
        self._llm = llm_client
        self._db_path = db_path
        self._output_dir = Path(output_dir) if output_dir else OUTPUT_DIR_DEFAULT
        self._output_dir.mkdir(parents=True, exist_ok=True)

        # Lazy init
        self._matcher: SubredditMatcher | None = None
        self._selector: PatternSelector | None = None
        self._title_gen: TitleGenerator | None = None
        self._body_gen: BodyGenerator | None = None
        self._metadata: MetadataSuggester | None = None
        self._checker: SelfChecker | None = None

        self._patterns_path = patterns_path
        self._anti_patterns_path = anti_patterns_path

    # ── Public API ──────────────────────────────────────────────

    def generate_titles(
        self,
        user_input: str,
        target_subreddit: str | None = None,
        n_titles: int = 3,
    ) -> GenerationResult:
        """Generate title candidates (no body)."""
        gen_id = f"gen_{uuid.uuid4().hex[:8]}"
        self._init_components()

        # 1. Match subreddits
        if target_subreddit:
            matched_subs = [(target_subreddit, 1.0)]
        else:
            matched_subs = self._matcher.match(user_input, limit=5)

        primary_sub = matched_subs[0][0]
        tier = self._get_tier(primary_sub)

        # 2. Select patterns
        patterns = self._selector.select(
            subreddit=primary_sub,
            topic_keywords=self._extract_keywords(user_input),
            n=n_titles,
        )

        if not patterns:
            logger.warning("No patterns found for r/%s", primary_sub)
            return GenerationResult(
                generation_id=gen_id,
                matched_subreddits=matched_subs,
                selected_patterns=[],
                candidate_titles=[],
            )

        # 3. Generate titles
        candidates = self._title_gen.generate(
            user_input, patterns, primary_sub, tier
        )

        return GenerationResult(
            generation_id=gen_id,
            matched_subreddits=matched_subs,
            selected_patterns=patterns,
            candidate_titles=candidates,
            metadata=self._metadata.suggest(primary_sub, tier, user_input),
        )

    def generate_full(
        self,
        user_input: str,
        target_subreddit: str | None = None,
        title_index: int = 0,
        n_titles: int = 3,
    ) -> GenerationResult:
        """Generate full post: titles + body + self-check."""
        result = self.generate_titles(user_input, target_subreddit, n_titles)

        if not result.candidate_titles:
            return result

        self._init_components()
        primary_sub = result.matched_subreddits[0][0]
        tier = self._get_tier(primary_sub)

        # Pick title
        idx = min(title_index, len(result.candidate_titles) - 1)
        selected = result.candidate_titles[idx]
        result.selected_title = selected

        # Find corresponding pattern
        pattern = next(
            (p for p in result.selected_patterns if p.get("pattern_id") == selected.pattern_id),
            result.selected_patterns[0] if result.selected_patterns else {},
        )

        # 4. Generate body
        body, body_metrics = self._body_gen.generate(
            selected.title, pattern, user_input, primary_sub, tier
        )
        result.body = body

        # 5. Self-check
        result.self_check = self._checker.check(
            selected.title, body, pattern, primary_sub
        )

        # Save
        self._save(result)

        return result

    def save_generation(self, result: GenerationResult) -> Path:
        """Save result to JSON."""
        return self._save(result)

    # ── Internals ─────────────────────────────────────────────

    def _init_components(self) -> None:
        if not self._matcher:
            self._matcher = SubredditMatcher(self._db_path)
        if not self._selector:
            self._selector = PatternSelector(self._patterns_path)
        if not self._title_gen:
            self._title_gen = TitleGenerator(self._llm)
        if not self._body_gen:
            self._body_gen = BodyGenerator(self._llm)
        if not self._metadata:
            self._metadata = MetadataSuggester()
        if not self._checker:
            self._checker = SelfChecker(self._anti_patterns_path)

    def _get_tier(self, subreddit: str) -> str:
        """Get tier for a subreddit from the DB."""
        import sqlite3
        try:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT tier FROM posts WHERE subreddit=? LIMIT 1",
                (subreddit,),
            ).fetchone()
            conn.close()
            return row[0] if row else "t2"
        except Exception:
            return "t2"

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Extract meaningful keywords from user input (supports CJK + English)."""
        import re
        words: list[str] = []

        # CJK characters: treat each 2+ char segment as a keyword
        cjk_chars = re.findall(r'[一-鿿㐀-䶿]{2,}', text)
        words.extend(cjk_chars)

        # English words
        en_words = re.findall(r"[a-z]{3,}", text.lower())
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "can", "shall", "to", "of", "in", "for",
            "on", "with", "at", "by", "from", "as", "into", "through", "during",
            "before", "after", "and", "but", "or", "nor", "not", "so", "yet",
            "this", "that", "these", "those", "it", "its", "i", "me", "my",
            "we", "our", "you", "your", "he", "she", "they", "him", "his",
            "her", "them", "what", "which", "who", "when", "where", "why", "how",
            "if", "then", "else", "just", "about", "also", "too", "very",
        }
        words.extend(w for w in en_words if w not in stop_words)

        return words[:15]

    def _save(self, result: GenerationResult) -> Path:
        """Save generation result to JSON."""
        path = self._output_dir / f"{result.generation_id}.json"
        data = {
            "generation_id": result.generation_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "matched_subreddits": [
                {"subreddit": s, "score": sc}
                for s, sc in result.matched_subreddits
            ],
            "selected_patterns": [
                {
                    "pattern_id": p.get("pattern_id"),
                    "name": p.get("name"),
                    "hook_type": p.get("hook_type"),
                    "viral_rate": p.get("historical_viral_rate"),
                }
                for p in result.selected_patterns
            ],
            "candidate_titles": [
                {
                    "title": t.title,
                    "score": t.score,
                    "hook_type": t.hook_type,
                    "pattern_id": t.pattern_id,
                }
                for t in result.candidate_titles
            ],
            "selected_title": (
                {
                    "title": result.selected_title.title,
                    "score": result.selected_title.score,
                }
                if result.selected_title else None
            ),
            "body": result.body,
            "metadata": result.metadata,
            "self_check": (
                {
                    "passed": result.self_check.passed,
                    "dimensions": result.self_check.dimensions,
                    "suggestions": result.self_check.suggestions,
                }
                if result.self_check else None
            ),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Saved generation to %s", path)
        return path
