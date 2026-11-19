import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.agent.fraud_review import load_context, review_fraud, score_band
from app.agent.orchestrator import investigate
from app.api.main import load_cases
from app.retrieval.search import search_procedures

client = TestClient(__import__("app.api.main", fromlist=["app"]).app)


def test_shared_procedures_explain_when_they_apply():
    for name, marker in (
        ("P-01.md", "leaves the beneficiary bank identifier blank"),
        ("P-02.md", "has no beneficiary name"),
        ("P-03.md", "Show both values to the analyst"),
    ):
        text = Path("data/procedures", name).read_text(encoding="utf-8")
        assert "Version: 1" in text
        assert marker in text
    bank = search_procedures("missing beneficiary bank identifier")
    assert bank[0].document_id == "P-01"
    assert bank[0].passage_id == "P-01-001"


def test_new_partners_use_their_own_procedures_offline():
    cases = {case.case_id: case for case in load_cases()}
    lumen = investigate(cases["CASE-015"])
    assert lumen.category == "partner_account_mismatch"
    assert {item.document_id for item in lumen.evidence} == {"L-01"}
    assert lumen.escalate_to_human
    matched = investigate(cases["CASE-016"])
    assert matched.category == "insufficient_evidence"
    assert matched.evidence == []
    keystone = investigate(cases["CASE-017"])
    assert keystone.category == "partner_remittance_mismatch"
    assert {item.document_id for item in keystone.evidence} == {"K-01"}
    shared = investigate(cases["CASE-018"])
    assert shared.category == "missing_bank_identifier"
    assert {item.document_id for item in shared.evidence} == {"P-01"}
    listed = {case["partner_id"] for case in client.get("/cases").json()}
    assert {"northstar", "harbor", "lumen", "keystone"} <= listed


def test_review_rubric_shows_fired_and_silent_checks():
    cases = {case.case_id: case for case in load_cases()}
    from app.agent.fraud_review import load_context
    review = review_fraud(cases["CASE-001"], load_context("CASE-001"))
    assert review.score == 25
    assert review.score_band == "watch"
    assert score_band(0) == "routine"
    assert score_band(40) == "elevated"
    assert score_band(100) == "priority"
    fired = {item.signal_id: item.fired for item in review.rubric}
    assert fired == {"new_beneficiary": True, "recent_change": False, "unusual_amount": False}
    quiet = review_fraud(cases["CASE-016"], load_context("CASE-016"))
    assert quiet.score == 0
    assert quiet.score_band == "routine"
    assert quiet.status == "no_signals_identified"
    assert all(not item.fired for item in quiet.rubric)
    api = client.post("/fraud-reviews", json={"case_id": "CASE-015", "mode": "offline"}).json()
    assert api["score_band"] == "watch"
    assert len(api["rubric"]) == 3


def test_name_check_cites_v01_and_close_result_abstains():
    cases = {case.case_id: case for case in load_cases()}
    matched = investigate(cases["CASE-020"])
    assert matched.category == "name_check_mismatch"
    assert {item.document_id for item in matched.evidence} == {"V-01"}
    assert matched.escalate_to_human
    close = investigate(cases["CASE-021"])
    assert close.category == "insufficient_evidence"
    assert close.evidence == []
    for partner in ("northstar.json", "harbor.json", "lumen.json", "keystone.json"):
        text = Path("data/partners", partner).read_text(encoding="utf-8")
        assert "V-01" in text
    first = review_fraud(cases["CASE-019"], load_context("CASE-019"))
    assert first.score == 25
    assert "first payment to this beneficiary" in first.review_summary
    assert any("first payment" in step for step in first.checklist)
    young = review_fraud(cases["CASE-024"], load_context("CASE-024"))
    assert young.score == 25
    assert "newly opened payee account" in young.review_summary
    many = review_fraud(cases["CASE-022"], load_context("CASE-022"))
    assert any("new payees" in step for step in many.checklist)
    assert {signal.signal_id for signal in many.signals} <= {"new_beneficiary", "recent_change", "unusual_amount"}


def test_every_case_uses_the_same_review_explanation():
    expected = {item["case_id"]: item for item in json.loads(Path("evaluations/fraud_review_cases.json").read_text())}
    cases = load_cases()
    assert len(cases) >= len(expected)
    for case in cases:
        review = review_fraud(case, load_context(case.case_id))
        assert case.exception_message in review.review_summary
        assert review.checklist[-1].startswith("Record the analyst decision")
        assert "case.exception" in review.evidence
        if review.score is not None:
            assert review.amount_multiple is not None
            assert "supplied" in review.history_note
            amount_check = next(item for item in review.rubric if item.signal_id == "unusual_amount")
            assert f"{review.amount_multiple:.1f} times" in amount_check.explanation
        if case.case_id in expected:
            assert review.score == expected[case.case_id]["score"]
            assert {signal.signal_id for signal in review.signals} == set(expected[case.case_id]["signals"])
    high = review_fraud(next(case for case in cases if case.case_id == "CASE-018"), load_context("CASE-018"))
    assert high.case_id == "CASE-018"
    assert high.amount_multiple == 11.1
    assert high.checklist[0].startswith("Confirm the missing bank identifier")
    quiet = next(case for case in cases if case.case_id == "CASE-016")
    quiet_review = review_fraud(quiet, load_context(quiet.case_id))
    assert quiet_review.score == 0
    assert "does not establish that the payment is safe" in quiet_review.checklist[-2]
