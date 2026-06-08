"""Generate endpoint — wraps generator.orchestrator."""

import asyncio
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..generator.orchestrator import GeneratorOrchestrator
from ..generator.self_checker import SelfChecker
from ..llm import LLMClient
from ..llm.prompts import BODY_REVISE
from .deps import check_rate_limit, get_current_user, get_db, get_llm_client, require_quota
from .models import Generation, User
from .prediction import predict_titles

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/generate", tags=["generate"])

# ── Async Generation Job Store ─────────────────────────────────────

_executor = ThreadPoolExecutor(max_workers=4)
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


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
    selected_pattern_id: str | None = None
    body: str | None = None
    self_check: dict | None = None


class RecheckRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=500)
    body: str = Field(..., max_length=10000)
    pattern_id: str = Field(..., min_length=1, max_length=128)
    subreddit: str = Field("", max_length=64)


class ReviseRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=500)
    body: str = Field(..., max_length=10000)
    suggestions: list[str] = Field(..., min_length=1)
    subreddit: str = Field("", max_length=64)


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
    request: Request,
    llm: LLMClient = Depends(get_llm_client),
    session: Session = Depends(get_db),
    current_user: User = Depends(require_quota),
):
    try:
        check_rate_limit(request, current_user)

        orch = _new_orchestrator()
        orch._llm = llm

        result = orch.generate_titles(req.user_input, req.target_subreddit, req.n_titles)

        titles = [
            TitleItem(title=t.title, score=t.score, hook_type=t.hook_type, pattern_id=t.pattern_id)
            for t in result.candidate_titles
        ]

        gen_record = Generation(
            user_id=current_user.id,
            generation_id=result.generation_id,
            user_input=req.user_input,
            target_subreddit=req.target_subreddit,
            titles_json=[t.model_dump() for t in titles],
        )
        session.add(gen_record)
        session.commit()

        return GenerationResponse(
            generation_id=result.generation_id,
            matched_subreddits=[{"subreddit": s, "score": sc} for s, sc in result.matched_subreddits],
            titles=titles,
            metadata=result.metadata,
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.exception("Generate titles failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/full", response_model=FullGenerationResponse)
def generate_full(
    req: GenerateRequest,
    request: Request,
    title_index: int = 0,
    llm: LLMClient = Depends(get_llm_client),
    session: Session = Depends(get_db),
    current_user: User = Depends(require_quota),
):
    try:
        check_rate_limit(request, current_user)

        orch = _new_orchestrator()
        orch._llm = llm

        result = orch.generate_full(req.user_input, req.target_subreddit, title_index, req.n_titles)

        titles = [
            TitleItem(title=t.title, score=t.score, hook_type=t.hook_type, pattern_id=t.pattern_id)
            for t in result.candidate_titles
        ]

        gen_record = Generation(
            user_id=current_user.id,
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

        return FullGenerationResponse(
            generation_id=result.generation_id,
            matched_subreddits=[{"subreddit": s, "score": sc} for s, sc in result.matched_subreddits],
            titles=titles,
            metadata=result.metadata,
            selected_title=result.selected_title.title if result.selected_title else None,
            selected_pattern_id=result.selected_title.pattern_id if result.selected_title else None,
            body=result.body,
            self_check={
                "passed": result.self_check.passed,
                "dimensions": result.self_check.dimensions,
                "suggestions": result.self_check.suggestions,
            } if result.self_check else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.exception("Generate full failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


def _load_pattern_by_id(pattern_id: str) -> dict | None:
    """Load a single pattern from patterns.json by its pattern_id."""
    import json
    from pathlib import Path
    patterns_path = Path(os.getenv("KARMAFORGE_PATTERNS_PATH", "data/patterns/patterns.json"))
    if not patterns_path.exists():
        return None
    with open(patterns_path, "r", encoding="utf-8") as f:
        patterns = json.load(f)
    for p in patterns:
        if p.get("pattern_id") == pattern_id:
            return p
    return None


@router.post("/recheck")
def recheck(req: RecheckRequest):
    """Re-run quality self-check on user-edited content (no LLM cost, deterministic)."""
    try:
        pattern = _load_pattern_by_id(req.pattern_id)
        if not pattern:
            raise HTTPException(status_code=404, detail=f"Pattern not found: {req.pattern_id}")

        anti_patterns_path = os.getenv(
            "KARMAFORGE_ANTI_PATTERNS_PATH", "data/patterns/anti_patterns.json"
        )
        checker = SelfChecker(anti_patterns_path)
        report = checker.check(req.title, req.body, pattern, req.subreddit or "")

        return {
            "passed": report.passed,
            "dimensions": report.dimensions,
            "suggestions": report.suggestions,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Recheck failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/revise")
def revise(req: ReviseRequest, llm: LLMClient = Depends(get_llm_client)):
    """Ask LLM to revise body text targeting specific quality issues, then re-check."""
    try:
        if not llm:
            raise HTTPException(status_code=503, detail="LLM client not available")

        suggestions_text = "\n".join(f"- {s}" for s in req.suggestions)
        prompt = BODY_REVISE.format(
            title=req.title,
            body=req.body,
            suggestions=suggestions_text,
            subreddit=req.subreddit or "",
        )

        revised_body = llm.complete(prompt, "").strip()

        return {
            "revised_body": revised_body,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Revise failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ── Async Generation ───────────────────────────────────────────────


class AsyncJobStatus(BaseModel):
    generation_id: str
    status: str  # "pending" | "processing" | "done" | "failed"
    result: dict | None = None
    error: str | None = None


def _run_full_generation(
    job_id: str,
    user_input: str,
    target_subreddit: str | None,
    n_titles: int,
    title_index: int,
    user_id: str,
    db_path: str,
) -> None:
    """Run the full generation pipeline in a background thread."""
    with _jobs_lock:
        _jobs[job_id]["status"] = "processing"

    try:
        orch = GeneratorOrchestrator(db_path=db_path)
        result = orch.generate_full(user_input, target_subreddit, title_index, n_titles)

        titles = [
            {
                "title": t.title,
                "score": t.score,
                "hook_type": t.hook_type,
                "pattern_id": t.pattern_id,
            }
            for t in result.candidate_titles
        ]

        output = {
            "generation_id": result.generation_id,
            "matched_subreddits": [
                {"subreddit": s, "score": sc}
                for s, sc in result.matched_subreddits
            ],
            "titles": titles,
            "metadata": result.metadata,
            "selected_title": result.selected_title.title if result.selected_title else None,
            "selected_pattern_id": result.selected_title.pattern_id if result.selected_title else None,
            "body": result.body,
            "self_check": {
                "passed": result.self_check.passed,
                "dimensions": result.self_check.dimensions,
                "suggestions": result.self_check.suggestions,
            } if result.self_check else None,
        }

        with _jobs_lock:
            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["result"] = output

    except Exception as e:
        logger.exception("Async generation failed for job %s", job_id)
        with _jobs_lock:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = f"{type(e).__name__}: {e}"


@router.post("/async", status_code=202)
def generate_async(
    req: GenerateRequest,
    request: Request,
    title_index: int = 0,
    llm: LLMClient = Depends(get_llm_client),
    session: Session = Depends(get_db),
    current_user: User = Depends(require_quota),
):
    """Start async full generation. Returns 202 with generation_id immediately.

    Poll GET /api/generate/{generation_id}/status for results.
    Free users: max 1 concurrent job. Pro users: max 3.
    """
    check_rate_limit(request, current_user)

    max_jobs = 3 if current_user.tier == "pro" else 1
    user_jobs = sum(
        1 for j in _jobs.values()
        if j.get("user_id") == current_user.id and j["status"] in ("pending", "processing")
    )
    if user_jobs >= max_jobs:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "too_many_jobs",
                "max_concurrent": max_jobs,
                "current": user_jobs,
            },
        )

    # Create job entry — use a temporary ID, replaced after orch runs
    import uuid
    job_id = f"async_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    with _jobs_lock:
        _jobs[job_id] = {
            "generation_id": job_id,
            "status": "pending",
            "user_id": current_user.id,
            "created_at": now.isoformat(),
        }

    # Save placeholder Generation record
    gen_record = Generation(
        user_id=current_user.id,
        generation_id=job_id,
        user_input=req.user_input,
        target_subreddit=req.target_subreddit,
    )
    session.add(gen_record)
    session.commit()

    # Run generation in background thread
    _executor.submit(
        _run_full_generation,
        job_id=job_id,
        user_input=req.user_input,
        target_subreddit=req.target_subreddit,
        n_titles=req.n_titles,
        title_index=title_index,
        user_id=current_user.id,
        db_path=_db_path,
    )

    return {
        "generation_id": job_id,
        "status": "pending",
        "message": "Generation started. Poll GET /api/generate/{id}/status for results.",
    }


@router.get("/{generation_id}/status", response_model=AsyncJobStatus)
def get_generation_status(
    generation_id: str,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_quota),
):
    """Poll the status of an async generation job."""
    with _jobs_lock:
        job = _jobs.get(generation_id)

    if job is None:
        # Check if it's a completed sync generation in the DB
        gen = session.query(Generation).filter(
            Generation.generation_id == generation_id,
            Generation.user_id == current_user.id,
        ).first()
        if gen:
            return AsyncJobStatus(
                generation_id=generation_id,
                status="done",
                result={
                    "generation_id": gen.generation_id,
                    "titles": gen.titles_json or [],
                    "selected_title": gen.selected_title,
                    "body": gen.body,
                    "self_check": gen.self_check_json,
                },
            )
        raise HTTPException(status_code=404, detail="Generation job not found")

    if job.get("user_id") != current_user.id:
        raise HTTPException(status_code=403, detail="Not your generation job")

    return AsyncJobStatus(
        generation_id=generation_id,
        status=job["status"],
        result=job.get("result"),
        error=job.get("error"),
    )


# ── Legacy Sync Endpoints ──────────────────────────────────────────


@router.post("/predict", response_model=PredictResponse)
def predict(
    req: PredictRequest,
    request: Request,
    llm: LLMClient = Depends(get_llm_client),
    session: Session = Depends(get_db),
    current_user: User = Depends(require_quota),
):
    """Generate titles AND rank them with historical performance predictions."""
    try:
        check_rate_limit(request, current_user)

        orch = _new_orchestrator()
        orch._llm = llm

        result = orch.generate_titles(req.user_input, req.target_subreddit, req.n_titles)

        titles_dicts = [
            {"title": t.title, "score": t.score, "hook_type": t.hook_type, "pattern_id": t.pattern_id}
            for t in result.candidate_titles
        ]

        user_id = current_user.id
        predictions = predict_titles(
            session, user_id, req.target_subreddit, titles_dicts
        )

        gen_record = Generation(
            user_id=user_id,
            generation_id=result.generation_id,
            user_input=req.user_input,
            target_subreddit=req.target_subreddit,
            titles_json=titles_dicts,
        )
        session.add(gen_record)
        session.commit()

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
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.exception("Predict generation failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
