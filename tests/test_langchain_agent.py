import json

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from app.agent.langchain_agent import investigate_with_agent
from app.agent.orchestrator import ProviderError
from app.api.main import load_cases


class ToolFake(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def fake(category="missing_bank_identifier", citations=None):
    if citations is None:
        citations = ["P-01-001"]
    return ToolFake(responses=[
        AIMessage(content="", tool_calls=[{"name": "get_case", "args": {}, "id": "1"}]),
        AIMessage(content="", tool_calls=[{"name": "get_partner_profile", "args": {}, "id": "2"}]),
        AIMessage(content="", tool_calls=[{"name": "search_partner_procedures", "args": {"query": "missing beneficiary bank identifier"}, "id": "3"}]),
        AIMessage(content=json.dumps({"category": category, "passage_ids": citations, "source_ids": ["payment.beneficiary_bank_identifier"]})),
    ])


def test_agent_calls_scoped_tools_and_validates_result():
    result = investigate_with_agent(load_cases()[0], fake())
    assert result.case_id == "CASE-001"
    assert result.tool_activity == ["get_case", "get_partner_profile", "search_partner_procedures"]
    assert result.evidence[0].document_id == "P-01"
    assert result.escalate_to_human


def test_agent_rejects_invented_evidence_and_unverified_result():
    with pytest.raises(ProviderError):
        investigate_with_agent(load_cases()[0], fake(citations=["P-99-001"]))
    with pytest.raises(ProviderError):
        investigate_with_agent(load_cases()[0], fake(category="conflicting_information"))


def test_agent_rejects_answer_without_tool_calls():
    model = ToolFake(responses=[AIMessage(content='{"category":"missing_bank_identifier","passage_ids":[]}')])
    with pytest.raises(ProviderError):
        investigate_with_agent(load_cases()[0], model)


def test_agent_api_without_model_configuration(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.main import app

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    response = TestClient(app).post("/investigations", json={"case_id": "CASE-001", "mode": "agent"})
    assert response.status_code == 503
    assert "analyst" in response.json()["detail"]


def test_agent_connects_partner_response_note_and_procedure():
    model = ToolFake(responses=[
        AIMessage(content="", tool_calls=[{"name": "get_case", "args": {}, "id": "1"}]),
        AIMessage(content="", tool_calls=[{"name": "get_partner_profile", "args": {}, "id": "2"}]),
        AIMessage(content="", tool_calls=[{"name": "search_partner_procedures", "args": {"query": "Northstar reference mismatch"}, "id": "3"}]),
        AIMessage(content=json.dumps({"category": "partner_reference_mismatch", "passage_ids": ["N-01-001"], "source_ids": ["partner_response", "note.1"]})),
    ])
    result = investigate_with_agent(load_cases()[5], model)
    assert result.category == "partner_reference_mismatch"
    assert [x.source_id for x in result.case_evidence] == ["partner_response", "note.1"]
    assert "NS-481" in result.case_evidence[0].excerpt
    assert "NS-418" in result.case_evidence[1].excerpt
    assert result.evidence[0].document_id == "N-01"


def test_agent_rejects_other_partners_procedure():
    model = ToolFake(responses=[
        AIMessage(content="", tool_calls=[{"name": "get_case", "args": {}, "id": "1"}]),
        AIMessage(content="", tool_calls=[{"name": "get_partner_profile", "args": {}, "id": "2"}]),
        AIMessage(content="", tool_calls=[{"name": "search_partner_procedures", "args": {"query": "Northstar reference Harbor beneficiary mismatch"}, "id": "3"}]),
        AIMessage(content=json.dumps({"category": "partner_beneficiary_mismatch", "passage_ids": ["H-01-001"], "source_ids": ["partner_response", "note.1"]})),
    ])
    with pytest.raises(ProviderError):
        investigate_with_agent(load_cases()[5], model)


def test_comparison_finds_baseline_misses():
    from pathlib import Path
    from evaluations.compare_investigators import run_one

    items = json.loads(Path("evaluations/comparison_cases.json").read_text())
    runs = [run_one(item, "offline") for item in items[:3]]
    assert [run["passed"] for run in runs] == [False, False, True]
    assert [run["category"] for run in runs] == ["insufficient_evidence"] * 3


def test_cmp003_unsupported_mismatch_abstains_even_if_procedure_retrieved():
    from pathlib import Path
    from app.schemas import Case

    case = Case.model_validate(json.loads(Path("evaluations/comparison_cases.json").read_text())[2]["case"])
    model = ToolFake(responses=[
        AIMessage(content="", tool_calls=[{"name": "get_case", "args": {}, "id": "1"}]),
        AIMessage(content="", tool_calls=[{"name": "get_partner_profile", "args": {}, "id": "2"}]),
        AIMessage(content="", tool_calls=[{"name": "search_partner_procedures", "args": {"query": "Field beneficiary mismatch"}, "id": "3"}]),
        AIMessage(content=json.dumps({"category": "partner_beneficiary_mismatch", "passage_ids": ["H-01-001"], "source_ids": ["partner_response", "note.1", "payment.beneficiary_name"]})),
    ])
    result = investigate_with_agent(case, model)
    assert result.category == "insufficient_evidence"
    assert result.evidence == []
    assert result.escalate_to_human


def test_generic_search_and_case_specific_retry_abstains():
    from pathlib import Path
    from app.schemas import Case

    case = Case.model_validate(json.loads(Path("evaluations/comparison_cases.json").read_text())[2]["case"])
    model = ToolFake(responses=[
        AIMessage(content="", tool_calls=[{"name": "get_case", "args": {}, "id": "1"}]),
        AIMessage(content="", tool_calls=[{"name": "get_partner_profile", "args": {}, "id": "2"}]),
        AIMessage(content="", tool_calls=[{"name": "search_partner_procedures", "args": {"query": "case procedure"}, "id": "3"}]),
        AIMessage(content="", tool_calls=[{"name": "search_partner_procedures", "args": {"query": "status QZ"}, "id": "4"}]),
        AIMessage(content=json.dumps({"category": "insufficient_evidence", "passage_ids": [], "source_ids": []})),
    ])
    result = investigate_with_agent(case, model)
    assert result.category == "insufficient_evidence"
    assert result.evidence == []
    assert result.tool_activity.count("search_partner_procedures") == 2


def test_harbor_positive_and_negated_mismatch_conditions():
    from app.agent.langchain_agent import supports_category

    case = load_cases()[6]
    ids = ["partner_response", "note.1", "payment.beneficiary_name"]
    assert supports_category("partner_beneficiary_mismatch", case, ids)
    assert not supports_category("partner_beneficiary_mismatch", case.model_copy(update={"partner_response": "No beneficiary-name mismatch found."}), ids)


def test_excessive_search_stops_and_abstains():
    from pathlib import Path
    from app.schemas import Case

    case = Case.model_validate(json.loads(Path("evaluations/comparison_cases.json").read_text())[2]["case"])
    calls = [
        AIMessage(content="", tool_calls=[{"name": "get_case", "args": {}, "id": "1"}]),
        AIMessage(content="", tool_calls=[{"name": "get_partner_profile", "args": {}, "id": "2"}]),
        AIMessage(content="", tool_calls=[{"name": "search_partner_procedures", "args": {"query": "case procedure"}, "id": "3"}]),
        AIMessage(content="", tool_calls=[{"name": "search_partner_procedures", "args": {"query": "status QZ"}, "id": "4"}]),
        AIMessage(content="", tool_calls=[{"name": "search_partner_procedures", "args": {"query": "status QZ"}, "id": "5"}]),
    ]
    result = investigate_with_agent(case, ToolFake(responses=calls))
    assert result.category == "insufficient_evidence"
    assert result.tool_activity.count("search_partner_procedures") == 2
    assert "search limit" in result.uncertainties[0].lower()
    assert result.escalate_to_human


def harbor_fake(source_ids):
    return ToolFake(responses=[
        AIMessage(content="", tool_calls=[{"name": "get_case", "args": {}, "id": "1"}]),
        AIMessage(content="", tool_calls=[{"name": "get_partner_profile", "args": {}, "id": "2"}]),
        AIMessage(content="", tool_calls=[{"name": "search_partner_procedures", "args": {"query": "beneficiary name mismatch"}, "id": "3"}]),
        AIMessage(content=json.dumps({"category": "partner_beneficiary_mismatch", "passage_ids": ["H-01-001"], "source_ids": source_ids})),
    ])


def test_valid_redundant_document_id_is_not_treated_as_case_source():
    from pathlib import Path
    from app.schemas import Case

    case = Case.model_validate(json.loads(Path("evaluations/comparison_cases.json").read_text())[1]["case"])
    result = investigate_with_agent(case, harbor_fake(["partner_response", "note.1", "H-01", "payment.beneficiary_name"]))
    assert result.category == "partner_beneficiary_mismatch"
    assert {source.source_id for source in result.case_evidence} == {"partner_response", "note.1", "payment.beneficiary_name"}
    assert result.evidence[0].document_id == "H-01"


def test_unknown_or_uncited_source_is_still_rejected():
    case = load_cases()[6]
    with pytest.raises(ProviderError):
        investigate_with_agent(case, harbor_fake(["partner_response", "note.1", "P-01", "payment.beneficiary_name"]))


def test_first_search_uses_reported_issue_and_shows_abstention_context():
    from pathlib import Path
    from app.schemas import Case

    case = Case.model_validate(json.loads(Path("evaluations/comparison_cases.json").read_text())[2]["case"])
    model = ToolFake(responses=[
        AIMessage(content="", tool_calls=[{"name": "get_case", "args": {}, "id": "1"}]),
        AIMessage(content="", tool_calls=[{"name": "get_partner_profile", "args": {}, "id": "2"}]),
        AIMessage(content="", tool_calls=[{"name": "search_partner_procedures", "args": {"query": "beneficiary name mismatch"}, "id": "3"}]),
        AIMessage(content=json.dumps({"category": "insufficient_evidence", "passage_ids": [], "source_ids": []})),
    ])
    result = investigate_with_agent(case, model)
    assert result.category == "insufficient_evidence"
    assert result.search_attempts[0].query == "Status QZ has no explanation."
    assert result.search_attempts[0].status == "no_results"
    assert {source.source_id: source.excerpt for source in result.case_evidence}["partner_response"] == case.partner_response
    assert not result.evidence


def test_reference_matching_and_alternative_wording_are_conservative():
    from pathlib import Path
    from app.agent.langchain_agent import supports_category
    from app.schemas import Case

    items = json.loads(Path("evaluations/comparison_cases.json").read_text())
    matching = Case.model_validate(items[3]["case"])
    assert not supports_category("partner_reference_mismatch", matching, ["partner_response", "note.1"])
    alternative = Case.model_validate(items[5]["case"])
    assert not supports_category("partner_beneficiary_mismatch", alternative, ["partner_response", "note.1", "payment.beneficiary_name"])


def test_harbor_mismatch_requires_different_name_in_note():
    from app.agent.langchain_agent import supports_category

    case = load_cases()[6]
    ids = ["partner_response", "note.1", "payment.beneficiary_name"]
    matching = case.model_copy(update={"notes": ["Beneficiary document shows Example Fern."]})
    missing = case.model_copy(update={"notes": ["No details were supplied."]})
    assert not supports_category("partner_beneficiary_mismatch", matching, ids)
    assert not supports_category("partner_beneficiary_mismatch", missing, ids)
