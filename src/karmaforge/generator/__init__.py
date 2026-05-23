"""Post generation engine — templates + LLM to create Reddit content."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CandidateTitle:
    title: str
    score: float  # 0-100
    hook_type: str
    pattern_id: str


@dataclass
class SelfCheckReport:
    passed: bool
    dimensions: dict  # {dimension: {"score": float, "status": "ok"|"warn"|"fail"}}
    suggestions: list[str]


@dataclass
class GenerationResult:
    generation_id: str
    matched_subreddits: list  # list[tuple[str, float]] — (subreddit, score)
    selected_patterns: list  # list[ViralPattern]
    candidate_titles: list  # list[CandidateTitle]
    selected_title: Optional[CandidateTitle] = None
    body: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    self_check: Optional[SelfCheckReport] = None
