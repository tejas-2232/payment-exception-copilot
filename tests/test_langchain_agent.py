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
        AIMessage(content=json.dumps({"category": category, "passage_ids": citations})),
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
