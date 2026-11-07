"""Conservative checks for cases that should be referred to an analyst."""
import re

from app.schemas import Case


def requires_context_review(case: Case) -> bool:
    """Abstain on ambiguous resolution/history or multiple missing fields.

    This deliberately favors review over a specific suggestion; it is not a
    general temporal or negation classifier.
    """
    if case.status.lower().strip() != "open":
        return True
    if not case.payment.beneficiary_name and not case.payment.beneficiary_bank_identifier:
        return True
    texts = [case.exception_message, case.partner_response or "", *case.notes]
    return any(re.search(r"\b(?:resolved|corrected|cleared|previously|historical|formerly|superseded|cancelled|canceled|withdrawn)\b", text, re.I) for text in texts)
