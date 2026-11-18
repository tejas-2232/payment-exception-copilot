"""Fictional, read-only fraud-review priority signals. Not a fraud classifier."""
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from math import isfinite

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import Case, InvestigationMetrics

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "fraud_context"


class HistoricalPayment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: float = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class FraudContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    as_of: datetime
    beneficiary_added_at: datetime | None
    change_history_complete: bool
    instructions_changed_at: datetime | None
    payment_history_complete: bool
    prior_payments: list[HistoricalPayment]
    analyst_context: str | None = None


class FraudSignal(BaseModel):
    signal_id: str
    title: str
    points: int
    evidence_ids: list[str]
    explanation: str


class RubricCheck(BaseModel):
    signal_id: str
    title: str
    points: int
    fired: bool
    explanation: str


class FraudReview(BaseModel):
    case_id: str
    status: Literal["signals_identified", "no_signals_identified", "insufficient_data"]
    score: int | None = Field(default=None, ge=0, le=100)
    score_max: int = 100
    score_band: str = "not scored"
    signals: list[FraudSignal] = Field(default_factory=list)
    rubric: list[RubricCheck] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    evidence: dict[str, str] = Field(default_factory=dict)
    procedure_id: str = "F-01"
    procedure_excerpt: str
    next_step: str
    human_review_required: bool = True
    tool_activity: list[str] = Field(default_factory=list)
    metrics: InvestigationMetrics | None = None


PROCEDURE = (Path(__file__).resolve().parents[2] / "data" / "fraud_procedures" / "F-01.md").read_text(encoding="utf-8").split("\n\n", 1)[1].strip()


def load_context(case_id: str) -> FraudContext | None:
    if not re.fullmatch(r"CASE-\d{3}", case_id):
        return None
    path = DATA_DIR / f"{case_id}.json"
    if not path.is_file():
        return None
    context = FraudContext.model_validate_json(path.read_text(encoding="utf-8"))
    if context.case_id != case_id:
        raise ValueError("Case and context do not match")
    return context


def _aware(value: datetime | None) -> bool:
    return value is not None and value.utcoffset() is not None


def score_band(score: int | None) -> str:
    """Queue label only. A band is not a fraud probability or a payment decision."""
    if score is None:
        return "not scored"
    if score == 0:
        return "routine"
    if score < 40:
        return "watch"
    if score < 75:
        return "elevated"
    return "priority"


def _rubric(fired: dict[str, str], unavailable: str | None = None) -> list[RubricCheck]:
    catalog = (
        ("new_beneficiary", "Recently added beneficiary", 25,
         "Beneficiary added within 30 days of the review timestamp."),
        ("recent_change", "Recent instruction change", 35,
         "Payment instructions changed within 24 hours of the review timestamp."),
        ("unusual_amount", "Amount above fictional history", 40,
         "Amount is above three times the average of the supplied same-currency history."),
    )
    checks = []
    for signal_id, title, points, plain in catalog:
        if unavailable:
            explanation = unavailable
            hit = False
        elif signal_id in fired:
            explanation = fired[signal_id]
            hit = True
        else:
            explanation = f"Not identified. {plain}"
            hit = False
        checks.append(RubricCheck(signal_id=signal_id, title=title, points=points, fired=hit, explanation=explanation))
    return checks


def review_fraud(case: Case, context: FraudContext | None) -> FraudReview:
    """Compute a fixed toy priority score only when all inputs are comparable."""
    evidence = {"payment.amount": f"{case.payment.currency} {case.payment.amount:.2f}"}
    missing = []
    if context is None:
        missing.append("Fictional review context is unavailable")
    else:
        if context.case_id != case.case_id:
            raise ValueError("Case and context do not match")
        if case.status.lower().strip() != "open":
            missing.append("Current open-case status needs review")
        if not _aware(context.as_of):
            missing.append("A timezone-aware review timestamp is required")
        if not _aware(context.beneficiary_added_at):
            missing.append("A timezone-aware beneficiary creation date is required")
        if not context.change_history_complete:
            missing.append("Instruction-change history is incomplete")
        if context.instructions_changed_at is not None and not _aware(context.instructions_changed_at):
            missing.append("A timezone-aware instruction-change timestamp is required")
        if not context.payment_history_complete or len(context.prior_payments) < 3:
            missing.append("At least three comparable historical payments and complete history are required")
        if any(not isfinite(p.amount) for p in context.prior_payments):
            missing.append("Historical payment amounts must be finite")
        if any(p.currency != case.payment.currency for p in context.prior_payments):
            missing.append("Historical payment currencies are not comparable")
        if not isfinite(case.payment.amount) or case.payment.amount <= 0:
            missing.append("A positive payment amount is required")
        if _aware(context.as_of):
            if _aware(context.beneficiary_added_at) and context.beneficiary_added_at > context.as_of:
                missing.append("Beneficiary creation date is after the review timestamp")
            if _aware(context.instructions_changed_at) and context.instructions_changed_at > context.as_of:
                missing.append("Instruction change is after the review timestamp")
        if context.analyst_context:
            evidence["context.analyst_note"] = context.analyst_context

    if missing:
        return FraudReview(case_id=case.case_id, status="insufficient_data", score=None, score_band="not scored",
            rubric=_rubric({}, "Not evaluated. The review data is incomplete, so no priority points are assigned."),
            missing_information=missing, evidence=evidence, procedure_excerpt=PROCEDURE,
            next_step="Ask an analyst to obtain or verify the missing information before prioritizing review.")

    # No score is a probability. Weights are invented solely for this prototype.
    signals = []
    elapsed = context.as_of - context.beneficiary_added_at
    evidence["context.beneficiary_added_at"] = context.beneficiary_added_at.isoformat()
    evidence["context.as_of"] = context.as_of.isoformat()
    evidence["context.instructions_changed_at"] = (context.instructions_changed_at.isoformat()
                                                    if context.instructions_changed_at else "No change recorded in complete history")
    evidence["context.prior_payments"] = ", ".join(f"{p.currency} {p.amount:.2f}" for p in context.prior_payments)
    fired = {}
    if elapsed <= timedelta(days=30):
        explanation = "The beneficiary was added within 30 days of the review timestamp."
        fired["new_beneficiary"] = explanation
        signals.append(FraudSignal(signal_id="new_beneficiary", title="Recently added beneficiary", points=25,
            evidence_ids=["context.beneficiary_added_at", "context.as_of"], explanation=explanation))
    if context.instructions_changed_at and context.as_of - context.instructions_changed_at <= timedelta(hours=24):
        explanation = "Payment instructions changed within 24 hours of the review timestamp."
        fired["recent_change"] = explanation
        signals.append(FraudSignal(signal_id="recent_change", title="Recent instruction change", points=35,
            evidence_ids=["context.instructions_changed_at", "context.as_of"], explanation=explanation))
    average = sum(p.amount for p in context.prior_payments) / len(context.prior_payments)
    if case.payment.amount > 3 * average:
        explanation = f"Amount exceeds three times the average of {len(context.prior_payments)} supplied prior payments."
        fired["unusual_amount"] = explanation
        signals.append(FraudSignal(signal_id="unusual_amount", title="Amount above fictional history", points=40,
            evidence_ids=["payment.amount", "context.prior_payments"], explanation=explanation))
    score = sum(s.points for s in signals)
    return FraudReview(case_id=case.case_id, status="signals_identified" if signals else "no_signals_identified",
        score=score, score_band=score_band(score), signals=signals, rubric=_rubric(fired), evidence=evidence,
        procedure_excerpt=PROCEDURE,
        next_step="Ask an analyst to verify the signals and context; no payment action is performed." if signals
                  else "Review the case normally; no signals identified does not establish that a payment is safe.")
