"""Evolution engine — feedback-driven pattern weight updates."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FailureAttribution:
    """Diagnosis of why a generated post underperformed."""

    generation_id: str
    primary_reason: str
    secondary_reasons: list[str]
    action_items: list[str]
    confidence: float  # 0-100
    dimensions: dict  # per-dimension scores
    attributed_at: str  # ISO 8601


@dataclass
class EvolutionLog:
    """Record of an evolution run."""

    run_at: str  # ISO 8601
    feedback_count: int
    patterns_updated: int
    patterns_marked_inactive: int
    summary: str
