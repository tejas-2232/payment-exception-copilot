import json
from pathlib import Path

import pytest

from app.agent.langchain_agent import supports_category
from app.agent.orchestrator import DeterministicProvider, investigate
from app.api.main import load_cases
from app.schemas import Case
from evaluations.compare_investigators import summarize


@pytest.mark.parametrize("response", [
    "Beneficiary-name mismatch was resolved.",
    "Beneficiary-name mismatch was previously reported.",
    "No beneficiary-name mismatch found.",
])
def test_ambiguous_or_old_mismatch_needs_review(response):
    case = load_cases()[6].model_copy(update={"partner_response": response})
    assert not supports_category("partner_beneficiary_mismatch", case,
                                 ["partner_response", "note.1", "payment.beneficiary_name"])
    assert investigate(case, DeterministicProvider()).category == "insufficient_evidence"


def test_multiple_missing_fields_and_closed_cases_need_review():
    case = load_cases()[0]
    payment = case.payment.model_copy(update={"beneficiary_name": None})
    multiple = case.model_copy(update={"payment": payment, "exception_message": "Conflicting information"})
    assert investigate(multiple, DeterministicProvider()).category == "insufficient_evidence"
    assert investigate(case.model_copy(update={"status": "closed"}), DeterministicProvider()).category == "insufficient_evidence"


def test_evaluation_counts_wrong_specific_recommendations_and_errors():
    ok = {"procedure": True, "case_sources": True}
    runs = [
        {"category": "missing_beneficiary_name", "expected_category": "missing_bank_identifier", "checks": ok, "passed": False, "elapsed_ms": 5},
        {"category": "conflicting_information", "expected_category": "insufficient_evidence", "checks": ok, "passed": False, "elapsed_ms": 7},
        {"error": "investigation failed", "passed": False, "elapsed_ms": 9},
    ]
    result = summarize(runs, "agent")
    assert result["wrong_non_abstaining_recommendations"] == 2
    assert result["wrong_non_abstaining_when_specific_expected"] == 1
    assert result["false_recommendations_when_abstention_expected"] == 1
    assert result["completed"] == 2 and result["errors"] == 1


def test_dataset_cases_have_distinct_ids_and_reviewable_labels():
    root = Path("evaluations")
    development = json.loads((root / "comparison_cases.json").read_text())
    candidates = json.loads((root / "candidate_cases.json").read_text())
    assert len(development) == 32 and len(candidates) == 10
    cases = development + candidates
    ids = [row["case"]["case_id"] for row in cases]
    assert len(ids) == len(set(ids))
    for row in cases:
        Case.model_validate(row["case"])
        assert row["scenario"] and row["acceptable_next_actions"]
        assert row["expected_abstention"] == (row["category"] == "insufficient_evidence")
        assert row["label_status"] == "provisional; human review required"
        assert bool(row["procedure"]) != row["expected_abstention"]
