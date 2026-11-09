import json
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from app.agent.fraud_agent import fraud_review_with_agent
from app.agent.fraud_review import load_context, review_fraud
from app.agent.orchestrator import ProviderError
from app.api.main import app, load_cases


class ToolFake(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def fake_model(status, signal_ids):
    return ToolFake(responses=[
        AIMessage(content="", tool_calls=[{"name": "get_fraud_review_context", "args": {}, "id": "1"}]),
        AIMessage(content="", tool_calls=[{"name": "get_fraud_review_guidance", "args": {}, "id": "2"}]),
        AIMessage(content=json.dumps({"status": status, "signal_ids": signal_ids})),
    ])


def test_offline_fictional_cases_against_expected_outcomes():
    examples = json.loads(Path("evaluations/fraud_review_cases.json").read_text())
    cases = {case.case_id: case for case in load_cases()}
    assert len(examples) == 14
    for expected in examples:
        case = cases[expected["case_id"]]
        result = review_fraud(case, load_context(case.case_id))
        assert result.status == expected["status"]
        assert result.score == expected["score"]
        assert {signal.signal_id for signal in result.signals} == set(expected["signals"])
        assert result.human_review_required
        assert result.procedure_id == "F-01"
        assert all(set(signal.evidence_ids).issubset(result.evidence) for signal in result.signals)


def test_score_boundaries_and_incomplete_data():
    case = load_cases()[0]
    context = load_context(case.case_id)
    at_boundary = context.model_copy(update={"beneficiary_added_at": context.as_of - timedelta(days=30)})
    outside = context.model_copy(update={"beneficiary_added_at": context.as_of - timedelta(days=30, seconds=1)})
    assert review_fraud(case, at_boundary).score == 25
    assert review_fraud(case, outside).score == 0
    changed = outside.model_copy(update={"instructions_changed_at": context.as_of - timedelta(hours=24)})
    assert review_fraud(case, changed).score == 35
    assert review_fraud(case, changed.model_copy(update={"instructions_changed_at": context.as_of + timedelta(seconds=1)})).score is None
    assert review_fraud(case, None).status == "insufficient_data"
    assert review_fraud(case, context.model_copy(update={"payment_history_complete": False})).score is None
    assert review_fraud(case.model_copy(update={"status": "closed"}), context).score is None


def test_context_must_match_selected_case():
    with pytest.raises(ValueError):
        review_fraud(load_cases()[0], load_context("CASE-002"))
    assert load_context("../CASE-001") is None


def test_agent_uses_scoped_tools_and_cannot_change_score():
    case = load_cases()[0]
    result = fraud_review_with_agent(case, load_context(case.case_id), fake_model("signals_identified", ["new_beneficiary"]))
    assert result.score == 25
    assert result.tool_activity == ["get_fraud_review_context", "get_fraud_review_guidance"]
    assert result.human_review_required
    with pytest.raises(ProviderError):
        fraud_review_with_agent(case, load_context(case.case_id), fake_model("signals_identified", ["unusual_amount"]))
    with pytest.raises(ProviderError):
        fraud_review_with_agent(case, load_context(case.case_id), fake_model("no_signals_identified", []))


def test_agent_abstains_when_history_incomplete():
    case = load_cases()[5]
    result = fraud_review_with_agent(case, load_context(case.case_id), fake_model("insufficient_data", []))
    assert result.status == "insufficient_data" and result.score is None
    assert result.missing_information


def test_agent_must_use_both_tools_and_cannot_invent_fields():
    case = load_cases()[0]
    model = ToolFake(responses=[AIMessage(content=json.dumps({"status": "signals_identified", "signal_ids": ["new_beneficiary"], "score": 100}))])
    with pytest.raises(ProviderError):
        fraud_review_with_agent(case, load_context(case.case_id), model)


def test_api_returns_score_and_rejects_write_attempts(monkeypatch):
    client = TestClient(app)
    response = client.post("/fraud-reviews", json={"case_id": "CASE-004", "mode": "offline"})
    assert response.status_code == 200
    assert response.json()["score"] == 100
    assert response.json()["metrics"]["model_calls"] == 0
    assert client.post("/fraud-reviews", json={"case_id": "UNKNOWN"}).status_code == 404
    assert client.post("/fraud-reviews", json={"case_id": "CASE-004", "action": "block"}).status_code == 422
    assert client.post("/cases/CASE-004/block").status_code == 404
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    assert client.post("/fraud-reviews", json={"case_id": "CASE-004", "mode": "agent"}).status_code == 503


def test_priority_queue_keeps_unscored_cases_visible_before_scores():
    response = TestClient(app).get("/fraud-review-queue")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 14
    first_scored = next(index for index, row in enumerate(rows) if row["score"] is not None)
    assert all(row["score"] is None for row in rows[:first_scored])
    scores = [row["score"] for row in rows[first_scored:]]
    assert scores == sorted(scores, reverse=True)
    assert any(row["case_id"] == "CASE-004" and row["score"] == 100 for row in rows)


def test_exactly_three_times_average_is_not_amount_signal():
    case = load_cases()[2]
    context = load_context(case.case_id)
    average = sum(item.amount for item in context.prior_payments) / len(context.prior_payments)
    at_limit = case.model_copy(update={"payment": case.payment.model_copy(update={"amount": average * 3})})
    over_limit = case.model_copy(update={"payment": case.payment.model_copy(update={"amount": average * 3 + 0.01})})
    assert "unusual_amount" not in {s.signal_id for s in review_fraud(at_limit, context).signals}
    assert "unusual_amount" in {s.signal_id for s in review_fraud(over_limit, context).signals}


def test_untrusted_instructions_cannot_set_agent_score():
    case = load_cases()[12]
    result = fraud_review_with_agent(case, load_context(case.case_id), fake_model("no_signals_identified", []))
    assert result.score == 0
    with pytest.raises(ProviderError):
        fraud_review_with_agent(case, load_context(case.case_id), fake_model("signals_identified", ["unusual_amount"]))


def test_api_agent_mode_with_simulated_model(monkeypatch):
    def simulated(case, context):
        return fraud_review_with_agent(case, context, fake_model("signals_identified", ["new_beneficiary"]))
    monkeypatch.setattr("app.api.main.fraud_review_with_agent", simulated)
    response = TestClient(app).post("/fraud-reviews", json={"case_id": "CASE-001", "mode": "agent"})
    assert response.status_code == 200
    result = response.json()
    assert result["score"] == 25
    assert result["tool_activity"] == ["get_fraud_review_context", "get_fraud_review_guidance"]
    assert result["metrics"]["model_calls"] == 3


def test_api_agent_failure_does_not_return_a_score(monkeypatch):
    def fail(case, context):
        raise ProviderError("unverified output", code="agent_response_invalid")
    monkeypatch.setattr("app.api.main.fraud_review_with_agent", fail)
    response = TestClient(app).post("/fraud-reviews", json={"case_id": "CASE-001", "mode": "agent"})
    assert response.status_code == 503
    assert "score" not in response.json()


def test_fraud_agent_accepts_text_block_answer_and_validates_signals():
    case = load_cases()[0]
    model = ToolFake(responses=[
        AIMessage(content="", tool_calls=[{"name": "get_fraud_review_context", "args": {}, "id": "1"}]),
        AIMessage(content="", tool_calls=[{"name": "get_fraud_review_guidance", "args": {}, "id": "2"}]),
        AIMessage(content=[{"type": "text", "text": json.dumps({"status": "signals_identified", "signal_ids": ["new_beneficiary"]})}]),
    ])
    result = fraud_review_with_agent(case, load_context(case.case_id), model)
    assert result.score == 25
    assert result.human_review_required
