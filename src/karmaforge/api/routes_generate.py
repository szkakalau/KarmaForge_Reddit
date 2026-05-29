"""Generate endpoint — wraps generator.orchestrator."""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..generator.orchestrator import GeneratorOrchestrator
from ..llm import LLMClient
from .deps import get_current_user, get_db, get_llm_client
from .models import Generation, User
from .prediction import predict_titles

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/generate", tags=["generate"])


class GenerateRequest(BaseModel):
    user_input: str = Field(..., min_length=2, max_length=2000, description="Product description or topic")
    target_subreddit: str | None = Field(None, min_length=3, max_length=64)
    n_titles: int = Field(3, ge=1, le=8)


class TitleItem(BaseModel):
    title: str
    score: float
    hook_type: str
    pattern_id: str


class GenerationResponse(BaseModel):
    generation_id: str
    matched_subreddits: list[dict]
    titles: list[TitleItem]
    metadata: dict | None = None


class FullGenerationResponse(GenerationResponse):
    selected_title: str | None = None
    body: str | None = None
    self_check: dict | None = None


class PredictRequest(BaseModel):
    user_input: str = Field(..., min_length=2, max_length=2000)
    target_subreddit: str = Field(..., min_length=3, max_length=64)
    n_titles: int = Field(3, ge=1, le=8)


class PredictionItem(BaseModel):
    title: str
    score: float
    hook_type: str
    pattern_id: str
    predicted_range: str
    confidence: str
    reasoning: str


class PredictResponse(BaseModel):
    generation_id: str
    subreddit: str
    predictions: list[PredictionItem]


_db_path = os.getenv("KARMAFORGE_DB_PATH", "data/processed/karmaforge.db")


def _new_orchestrator() -> GeneratorOrchestrator:
    return GeneratorOrchestrator(db_path=_db_path)


@router.post("/titles", response_model=GenerationResponse)
def generate_titles(
    req: GenerateRequest,
    llm: LLMClient = Depends(get_llm_client),
    session: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
):
    orch = _new_orchestrator()
    orch._llm = llm

    try:
        result = orch.generate_titles(req.user_input, req.target_subreddit, req.n_titles)
    except Exception as e:
        logger.exception("Generation failed")
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")

    titles = [
        TitleItem(title=t.title, score=t.score, hook_type=t.hook_type, pattern_id=t.pattern_id)
        for t in result.candidate_titles
    ]

    try:
        gen_record = Generation(
            user_id=current_user.id if current_user else "_anonymous",
            generation_id=result.generation_id,
            user_input=req.user_input,
            target_subreddit=req.target_subreddit,
            titles_json=[t.model_dump() for t in titles],
        )
        session.add(gen_record)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.exception("Failed to save generation record")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return GenerationResponse(
        generation_id=result.generation_id,
        matched_subreddits=[{"subreddit": s, "score": sc} for s, sc in result.matched_subreddits],
        titles=titles,
        metadata=result.metadata,
    )


@router.post("/full", response_model=FullGenerationResponse)
def generate_full(
    req: GenerateRequest,
    title_index: int = 0,
    llm: LLMClient = Depends(get_llm_client),
    session: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
):
    orch = _new_orchestrator()
    orch._llm = llm

    try:
        result = orch.generate_full(req.user_input, req.target_subreddit, title_index, req.n_titles)
    except Exception as e:
        logger.exception("Full generation failed")
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")

    titles = [
        TitleItem(title=t.title, score=t.score, hook_type=t.hook_type, pattern_id=t.pattern_id)
        for t in result.candidate_titles
    ]

    try:
        gen_record = Generation(
            user_id=current_user.id if current_user else "_anonymous",
            generation_id=result.generation_id,
            user_input=req.user_input,
            target_subreddit=req.target_subreddit,
            titles_json=[t.model_dump() for t in titles],
            selected_title=result.selected_title.title if result.selected_title else None,
            body=result.body,
            pattern_id=result.selected_title.pattern_id if result.selected_title else None,
            metadata_json=result.metadata,
            self_check_json={
                "passed": result.self_check.passed,
                "dimensions": result.self_check.dimensions,
                "suggestions": result.self_check.suggestions,
            } if result.self_check else {},
        )
        session.add(gen_record)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.exception("Failed to save full generation record")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return FullGenerationResponse(
        generation_id=result.generation_id,
        matched_subreddits=[{"subreddit": s, "score": sc} for s, sc in result.matched_subreddits],
        titles=titles,
        metadata=result.metadata,
        selected_title=result.selected_title.title if result.selected_title else None,
        body=result.body,
        self_check={
            "passed": result.self_check.passed,
            "dimensions": result.self_check.dimensions,
            "suggestions": result.self_check.suggestions,
        } if result.self_check else None,
    )


@router.post("/predict", response_model=PredictResponse)
def predict(
    req: PredictRequest,
    llm: LLMClient = Depends(get_llm_client),
    session: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
):
    """Generate titles AND rank them with historical performance predictions."""
    orch = _new_orchestrator()
    orch._llm = llm

    try:
        result = orch.generate_titles(req.user_input, req.target_subreddit, req.n_titles)
    except Exception as e:
        logger.exception("Prediction generation failed")
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")

    titles_dicts = [
        {"title": t.title, "score": t.score, "hook_type": t.hook_type, "pattern_id": t.pattern_id}
        for t in result.candidate_titles
    ]

    user_id = current_user.id if current_user else "_anonymous"
    predictions = predict_titles(
        session, user_id, req.target_subreddit, titles_dicts
    )

    try:
        gen_record = Generation(
            user_id=user_id,
            generation_id=result.generation_id,
            user_input=req.user_input,
            target_subreddit=req.target_subreddit,
            titles_json=titles_dicts,
        )
        session.add(gen_record)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.exception("Failed to save predict generation record")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return PredictResponse(
        generation_id=result.generation_id,
        subreddit=req.target_subreddit,
        predictions=[
            PredictionItem(
                title=p.title,
                score=p.score,
                hook_type=p.hook_type,
                pattern_id=p.pattern_id,
                predicted_range=p.predicted_range,
                confidence=p.confidence,
                reasoning=p.reasoning,
            )
            for p in predictions
        ],
    )
