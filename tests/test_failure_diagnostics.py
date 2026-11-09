from fastapi.testclient import TestClient

from app.agent.orchestrator import ProviderError
from app.api.main import app


def test_api_returns_safe_error_code_without_leaking_details(monkeypatch, caplog):
    def fail(case):
        raise ProviderError("private provider message", code="model_rate_or_credit_limit")

    monkeypatch.setattr("app.api.main.investigate_with_agent", fail)
    response = TestClient(app).post("/investigations", json={"case_id": "CASE-001", "mode": "agent"})
    assert response.status_code == 503
    assert response.headers["X-Investigation-Error"] == "model_rate_or_credit_limit"
    assert "billing" in response.json()["detail"]
    assert "private provider message" not in response.text
    assert "private provider message" not in caplog.text


def test_missing_model_configuration_has_actionable_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    response = TestClient(app).post("/investigations", json={"case_id": "CASE-001", "mode": "agent"})
    assert response.status_code == 503
    assert response.headers["X-Investigation-Error"] == "model_not_configured"
    assert "OPENAI_MODEL" in response.json()["detail"]


def test_comparison_keeps_safe_provider_error_code(monkeypatch):
    import json
    from pathlib import Path
    from evaluations.compare_investigators import run_one

    item = json.loads(Path("evaluations/comparison_cases.json").read_text())[0]
    def fail(case):
        raise ProviderError("private detail", code="agent_response_invalid")
    monkeypatch.setattr("evaluations.compare_investigators.investigate_with_agent", fail)
    result = run_one(item, "agent")
    assert result["error_code"] == "agent_response_invalid"
    assert "private detail" not in str(result)


def test_agent_distinguishes_provider_rate_limit_without_exposing_message():
    import httpx
    import pytest
    from langchain_openai import ChatOpenAI
    from app.agent.langchain_agent import investigate_with_agent
    from app.api.main import load_cases

    transport = httpx.MockTransport(lambda request: httpx.Response(429, json={"error": {"message": "private provider detail", "code": "credit_balance_exhausted", "type": "insufficient_quota"}}))
    client = httpx.Client(transport=transport)
    model = ChatOpenAI(model="test-model", api_key="not-a-real-key", http_client=client,
                       streaming=True, stream_usage=True, max_retries=0)
    with pytest.raises(ProviderError) as error:
        investigate_with_agent(load_cases()[0], model)
    assert error.value.code == "model_rate_or_credit_limit"
    assert "private provider detail" not in str(error.value)
