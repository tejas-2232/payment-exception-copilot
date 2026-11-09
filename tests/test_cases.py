from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_case_list_and_detail():
    assert client.get("/health").json() == {"status": "ok"}
    cases = client.get("/cases").json()
    assert len(cases) == 14
    assert len({case["case_id"] for case in cases}) == 14
    for case in cases:
        response = client.get(f"/cases/{case['case_id']}")
        assert response.status_code == 200
        assert response.json() == case


def test_unknown_case_and_read_only_api():
    assert client.get("/cases/UNKNOWN").status_code == 404
    assert client.post("/cases", json={}).status_code == 405
    assert client.post("/investigations", json={"case_id": "UNKNOWN"}).status_code == 404
