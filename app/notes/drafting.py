"""Prepare a case-note draft from the read-only investigation. Nothing is written here."""
from app.agent.orchestrator import investigate
from app.schemas import Case


def prepare_draft(case: Case) -> tuple[str, list[dict[str, str]]]:
    result = investigate(case)
    evidence = [{"source_id": item.document_id, "excerpt": item.excerpt} for item in result.evidence]
    if not evidence:
        evidence = [{"source_id": "case.exception_message", "excerpt": case.exception_message}]
    cited = ", ".join(item["source_id"] for item in evidence)
    amount = f"{case.payment.currency} {case.payment.amount:,.2f}"
    step = result.recommended_next_steps[0]
    body = (
        f"Case {case.case_id}. Payment {case.payment.payment_id} for {amount} via {case.partner_id}.\n"
        f"Exception: {case.exception_message}\n"
        f"Review: {result.case_summary}\n"
        f"Evidence checked: {cited}.\n"
        f"Analyst check: {step}\n"
        "Filed for the case record only. This note does not repair, release, return, or block the payment."
    )
    return body, evidence
