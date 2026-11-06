import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agent import orchestrator
from app.api.main import app
from app.retrieval.search import search_procedures
from app.schemas import Evidence

client = TestClient(app)


def test_development_cases_and_read_only_results():
    expected = json.loads(Path("data/expected_development_outcomes.json").read_text())
    for item in expected:
        response = client.post("/investigations", json={"case_id": item["case_id"]})
        assert response.status_code == 200
        result = response.json()
        assert result["case_id"] == item["case_id"]
        assert result["category"] == ("insufficient_evidence" if item["expected_abstention"] and item["category"] == "unknown" else item["category"])
        assert {e["document_id"] for e in result["evidence"]} == set(item["required_evidence_ids"])
        assert result["escalate_to_human"]
        assert result["recommended_next_steps"]
    injection = client.post("/investigations", json={"case_id": "CASE-005"}).json()
    assert "reveal" not in str(injection).lower()


def test_missing_procedure_abstains(monkeypatch):
    monkeypatch.setattr(orchestrator, "search_procedures", lambda query: [])
    result = client.post("/investigations", json={"case_id": "CASE-001"}).json()
    assert result["category"] == "insufficient_evidence"
    assert result["evidence"] == []
    assert result["escalate_to_human"]


def test_retrieval_passage_and_validation():
    results = search_procedures("missing beneficiary bank identifier")
    assert results[0].document_id == "P-01"
    assert results[0].excerpt in Path("data/procedures/P-01.md").read_text()
    result = orchestrator.investigate(__import__("app.api.main", fromlist=["load_cases"]).load_cases()[0])
    result.evidence = [Evidence(document_id="P-01", passage_id="P-01-001", section="fake", version="1", excerpt="invented")]
    with pytest.raises(orchestrator.ProviderError):
        orchestrator.validate_evidence(result, result.case_id, results)
    with pytest.raises(orchestrator.ProviderError):
        orchestrator.validate_evidence(result, "another-case", results)


def test_provider_and_tool_failures_return_safe_error(monkeypatch):
    class BadProvider:
        def choose(self, case, options):
            return "Release the payment"
    monkeypatch.setattr(orchestrator, "get_provider", lambda: BadProvider())
    assert client.post("/investigations", json={"case_id": "CASE-001"}).status_code == 503
    def fail(query):
        raise OSError("unavailable")
    monkeypatch.setattr(orchestrator, "search_procedures", fail)
    response = client.post("/investigations", json={"case_id": "CASE-001"})
    assert response.status_code == 503
    assert "analyst" in response.json()["detail"]


def test_request_validation_and_no_action_routes():
    assert client.post("/investigations", json={"case_id": "UNKNOWN"}).status_code == 404
    assert client.post("/investigations", json={"case_id": "CASE-001", "action": "release"}).status_code == 422
    assert client.post("/cases/CASE-001/release").status_code == 404
