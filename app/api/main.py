from pathlib import Path
from fastapi import FastAPI, HTTPException
from starlette.concurrency import run_in_threadpool
from app.agent.orchestrator import ProviderError, investigate
from app.agent.langchain_agent import investigate_with_agent
from app.schemas import Case, InvestigationRequest, Recommendation

CASES_DIR = Path(__file__).resolve().parents[2] / "data" / "cases"
app = FastAPI(title="Fictional Payment Exception Assistant")




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
        return await run_in_threadpool(investigate_with_agent if request.mode == "agent" else investigate, case)
    except (ProviderError, OSError, ValueError):
        raise HTTPException(status_code=503, detail="Investigation unavailable; please ask an analyst to review the case.")
