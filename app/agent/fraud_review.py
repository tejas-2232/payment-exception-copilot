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
    review_summary: str = ""
    amount_multiple: float | None = None
    history_note: str = ""
    checklist: list[str] = Field(default_factory=list)
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


def _rubric(fired: dict[str, str], silent: dict[str, str] | None = None, unavailable: str | None = None) -> list[RubricCheck]:
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
            explanation = (silent or {}).get(signal_id, f"Not identified. {plain}")
            hit = False
        checks.append(RubricCheck(signal_id=signal_id, title=title, points=points, fired=hit, explanation=explanation))
    return checks


def _history_note(count: int | None) -> str:
    if count is None:
        return ""
    if count < 6:
        return f"The amount baseline uses {count} supplied payments, so the comparison is thin."
    return f"The amount baseline uses {count} supplied payments."


def _case_text(case: Case) -> str:
    return " ".join([case.exception_message, case.partner_response or "", *case.notes]).lower()


def _pattern_steps(case: Case) -> list[str]:
    text = _case_text(case)
    response = (case.partner_response or "").lower()
    steps = []
    if "first payment to this beneficiary" in text:
        steps.append("This is the first payment to this beneficiary. Confirm the destination with a contact already on file.")
    if "new payees were added in one day" in text:
        steps.append("Several new payees were added in one day. Review them together before any repair.")
    if "payee account is" in text and "days old" in text:
        steps.append("The payee account was opened recently. Confirm it is the intended account before any repair.")
    if "name check result: no match" in response:
        steps.append("The name check did not match. Compare the payment name with the account name and do not replace either one.")
    if "name check result: close" in response:
        steps.append("The name check is only close. Compare the spellings and do not treat that as a confirmed mismatch.")
    return steps


def _checklist(case: Case, signal_ids: set[str], *, missing: bool, multiple: float | None, history_count: int | None) -> list[str]:
    steps = _pattern_steps(case)
    if not case.payment.beneficiary_bank_identifier:
        steps.append("Confirm the missing bank identifier with a contact already on file before any repair.")
    if not case.payment.beneficiary_name:
        steps.append("Confirm the missing beneficiary name with a contact already on file before any repair.")
    if "conflict" in case.exception_message.lower():
        steps.append("Show both conflicting values to an analyst and do not pick one.")
    if "new_beneficiary" in signal_ids or "recent_change" in signal_ids:
        steps.append("Verify the change with a known contact. Do not use the phone number or email that arrived with the request, and require a second approver.")
    if "unusual_amount" in signal_ids and multiple is not None:
        steps.append(f"Ask why this payment is {multiple:.1f} times the supplied average before treating it as routine.")
    if history_count is not None and history_count < 6:
        steps.append(f"The amount baseline uses {history_count} payments. Treat the comparison as thin until more history is available.")
    if missing:
        steps.append("Obtain the missing review data before using a queue score.")
    elif not signal_ids:
        steps.append("No configured signal fired. That does not establish that the payment is safe.")
    steps.append("Record the analyst decision on the case note. Do not block, release, or repair the payment from this score.")
    return steps


def _summary(case: Case, score: int | None, band: str, signal_ids: set[str], multiple: float | None) -> str:
    fired = ", ".join(signal_ids) if signal_ids else "no configured signal"
    amount = f" Amount is {multiple:.1f} times the supplied average." if multiple is not None else ""
    score_text = "not scored" if score is None else f"{score}/100 {band}"
    noted = []
    text = _case_text(case)
    response = (case.partner_response or "").lower()
    if "first payment to this beneficiary" in text:
        noted.append("first payment to this beneficiary")
    if "new payees were added in one day" in text:
        noted.append("several new payees in one day")
    if "payee account is" in text and "days old" in text:
        noted.append("newly opened payee account")
    if "name check result: no match" in response:
        noted.append("name check no match")
    if "name check result: close" in response:
        noted.append("name check close")
    extra = f" Also noted: {', '.join(noted)}." if noted else ""
    return f"{case.case_id}: {case.exception_message}. Queue priority {score_text}; {fired}.{amount}{extra}"


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

    evidence["case.exception"] = case.exception_message
    if missing:
        checklist = _checklist(case, set(), missing=True, multiple=None, history_count=None)
        return FraudReview(case_id=case.case_id, status="insufficient_data", score=None, score_band="not scored",
            review_summary=_summary(case, None, "not scored", set(), None),
            checklist=checklist,
            rubric=_rubric({}, unavailable="Not evaluated. The review data is incomplete, so no priority points are assigned."),
            missing_information=missing, evidence=evidence, procedure_excerpt=PROCEDURE,
            next_step=checklist[0])

    # No score is a probability. Weights are invented solely for this prototype.
    signals = []
    elapsed = context.as_of - context.beneficiary_added_at
    evidence["context.beneficiary_added_at"] = context.beneficiary_added_at.isoformat()
    evidence["context.as_of"] = context.as_of.isoformat()
    evidence["context.instructions_changed_at"] = (context.instructions_changed_at.isoformat()
                                                    if context.instructions_changed_at else "No change recorded in complete history")
    evidence["context.prior_payments"] = ", ".join(f"{p.currency} {p.amount:.2f}" for p in context.prior_payments)
    fired = {}
    silent = {}
    beneficiary_days = elapsed.days
    if elapsed <= timedelta(days=30):
        explanation = f"The beneficiary was added {beneficiary_days} days before the review timestamp, inside the 30-day window."
        fired["new_beneficiary"] = explanation
        signals.append(FraudSignal(signal_id="new_beneficiary", title="Recently added beneficiary", points=25,
            evidence_ids=["context.beneficiary_added_at", "context.as_of"], explanation=explanation))
    else:
        silent["new_beneficiary"] = (
            f"Not identified. The beneficiary was added {beneficiary_days} days before the review timestamp, "
            "outside the 30-day window.")
    if context.instructions_changed_at:
        change_hours = (context.as_of - context.instructions_changed_at).total_seconds() / 3600
        if change_hours <= 24:
            explanation = f"Payment instructions changed {change_hours:.1f} hours before the review timestamp, inside the 24-hour window."
            fired["recent_change"] = explanation
            signals.append(FraudSignal(signal_id="recent_change", title="Recent instruction change", points=35,
                evidence_ids=["context.instructions_changed_at", "context.as_of"], explanation=explanation))
        else:
            silent["recent_change"] = (
                f"Not identified. Instructions changed {change_hours:.1f} hours before the review timestamp, "
                "outside the 24-hour window.")
    else:
        silent["recent_change"] = "Not identified. No instruction change is recorded in the complete history."
    count = len(context.prior_payments)
    average = sum(p.amount for p in context.prior_payments) / count
    multiple = case.payment.amount / average
    threshold = 3 * average
    evidence["context.amount_average"] = f"{case.payment.currency} {average:.2f}"
    evidence["context.amount_multiple"] = f"{multiple:.1f}x"
    if case.payment.amount > threshold:
        explanation = (
            f"Amount is {multiple:.1f} times the average of {count} supplied prior payments "
            f"({case.payment.currency} {average:.2f}). The review line is three times that average "
            f"({case.payment.currency} {threshold:.2f}).")
        fired["unusual_amount"] = explanation
        signals.append(FraudSignal(signal_id="unusual_amount", title="Amount above fictional history", points=40,
            evidence_ids=["payment.amount", "context.prior_payments"], explanation=explanation))
    else:
        silent["unusual_amount"] = (
            f"Not identified. Amount is {multiple:.1f} times the average of {count} supplied prior payments "
            f"({case.payment.currency} {average:.2f}), which is not above three times that average "
            f"({case.payment.currency} {threshold:.2f}).")
    score = sum(s.points for s in signals)
    band = score_band(score)
    signal_ids = set(fired)
    checklist = _checklist(case, signal_ids, missing=False, multiple=round(multiple, 1), history_count=count)
    return FraudReview(case_id=case.case_id, status="signals_identified" if signals else "no_signals_identified",
        score=score, score_band=band, review_summary=_summary(case, score, band, signal_ids, round(multiple, 1)),
        amount_multiple=round(multiple, 1), history_note=_history_note(count), checklist=checklist,
        signals=signals, rubric=_rubric(fired, silent), evidence=evidence, procedure_excerpt=PROCEDURE,
        next_step=checklist[0])
