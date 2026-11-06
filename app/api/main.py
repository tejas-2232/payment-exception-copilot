from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

CASES_DIR = Path(__file__).resolve().parents[2] / "data" / "cases"
app = FastAPI(title="Fictional Payment Exception Assistant")


class Payment(BaseModel):
    payment_id: str
    amount: float
    currency: str
    beneficiary_name: str | None
    beneficiary_bank_identifier: str | None


class Case(BaseModel):
    case_id: str
    status: str
    exception_message: str
    payment: Payment
    notes: list[str]


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
