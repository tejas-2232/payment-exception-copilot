import os
import logging
from pathlib import Path
from time import perf_counter
from fastapi import FastAPI, HTTPException
from starlette.concurrency import run_in_threadpool
from app.agent.orchestrator import ProviderError, investigate
from app.agent.fraud_review import FraudReview, load_context, review_fraud
from app.agent.fraud_agent import fraud_review_with_agent
from app.agent.langchain_agent import investigate_with_agent
from app.schemas import Case, InvestigationMetrics, InvestigationRequest, Recommendation

CASES_DIR = Path(__file__).resolve().parents[2] / "data" / "cases"
app = FastAPI(title="Fictional Payment Exception Assistant")
logger = logging.getLogger(__name__)
SAFE_ERRORS = {
    "model_not_configured": "The AI model is not configured. Check OPENAI_API_KEY and OPENAI_MODEL.",
    "model_authentication_failed": "The model provider rejected authentication or access. Check the API key and model access.",
    "model_rate_or_credit_limit": "The model provider reported a rate or credit limit. Check API billing and limits.",
    "model_not_found": "The model provider could not find the selected model. Check OPENAI_MODEL and account access.",
    "model_request_rejected": "The model provider rejected the request. Check the selected model and provider configuration.",
    "model_service_unavailable": "The model provider is unavailable. Please retry later.",
    "model_connection_failed": "The model provider could not be reached or timed out. Check your connection and retry.",
    "agent_response_invalid": "The agent response could not be verified against the case and evidence.",
    "investigation_failed": "The investigation could not be completed.",
}




def load_cases() -> list[Case]:
    return [Case.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(CASES_DIR.glob("*.json"))]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/cases", response_model=list[Case])
async def list_cases() -> list[Case]:
    return load_cases()


@app.get("/cases/{case_id}", response_model=Case)
async def get_case(case_id: str) -> Case:
    for case in load_cases():
        if case.case_id == case_id:
            return case
    raise HTTPException(status_code=404, detail="Case not found")


@app.post("/investigations", response_model=Recommendation)
async def create_investigation(request: InvestigationRequest) -> Recommendation:
    case = await get_case(request.case_id)
    try:
        started = perf_counter()
        result = await run_in_threadpool(investigate_with_agent if request.mode == "agent" else investigate, case)
        if request.mode == "offline":
            deterministic = os.getenv("INVESTIGATION_PROVIDER", "deterministic") == "deterministic"
            result.metrics = InvestigationMetrics(total_duration_ms=round((perf_counter() - started) * 1000, 1),
                model_calls=0 if deterministic else None, input_tokens=0 if deterministic else None,
                output_tokens=0 if deterministic else None, cached_input_tokens=0 if deterministic else None,
                estimated_cost_usd=0.0 if deterministic else None,
                pricing_status="No model calls" if deterministic else "Usage unavailable")
        return result
    except (ProviderError, OSError, ValueError) as exc:
        code = exc.code if isinstance(exc, ProviderError) else "investigation_failed"
        if code not in SAFE_ERRORS:
            code = "investigation_failed"
        logger.warning("Investigation failed: %s", code)
        raise HTTPException(status_code=503, detail=f"{SAFE_ERRORS[code]} Ask an analyst to review the case.",
                            headers={"X-Investigation-Error": code}) from None


@app.post("/fraud-reviews", response_model=FraudReview)
async def create_fraud_review(request: InvestigationRequest) -> FraudReview:
    case = await get_case(request.case_id)
    try:
        started = perf_counter()
        context = await run_in_threadpool(load_context, case.case_id)
        if request.mode == "agent":
            return await run_in_threadpool(fraud_review_with_agent, case, context)
        result = await run_in_threadpool(review_fraud, case, context)
        result.metrics = InvestigationMetrics(total_duration_ms=round((perf_counter() - started) * 1000, 1),
            model_calls=0, input_tokens=0, output_tokens=0, cached_input_tokens=0,
            estimated_cost_usd=0.0, pricing_status="No model calls")
        return result
    except (ProviderError, OSError, ValueError) as exc:
        code = exc.code if isinstance(exc, ProviderError) else "investigation_failed"
        if code not in SAFE_ERRORS:
            code = "investigation_failed"
        logger.warning("Fraud review failed: %s", code)
        raise HTTPException(status_code=503, detail=f"{SAFE_ERRORS[code]} Ask an analyst to review the case.",
                            headers={"X-Investigation-Error": code}) from None


@app.get("/fraud-review-queue")
async def get_fraud_review_queue() -> list[dict]:
    """Fictional offline review scores; unscored cases are surfaced first."""
    def build_queue():
        rows = []
        for case in load_cases():
            review = review_fraud(case, load_context(case.case_id))
            rows.append({"case_id": case.case_id, "status": review.status, "score": review.score})
        return sorted(rows, key=lambda row: (row["score"] is not None, -(row["score"] or 0), row["case_id"]))
    try:
        return await run_in_threadpool(build_queue)
    except (OSError, ValueError):
        logger.warning("Fraud review queue unavailable")
        raise HTTPException(status_code=503, detail="Review queue unavailable; ask an analyst to review cases.") from None
