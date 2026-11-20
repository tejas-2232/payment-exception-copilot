import hashlib
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.notes import store


CASES = Path("data/cases")


@pytest.fixture()
def notes_db(tmp_path, monkeypatch):
    monkeypatch.setenv("CASE_NOTES_DB", str(tmp_path / "notes.sqlite"))
    return TestClient(app)


def _case_digest() -> str:
    digest = hashlib.sha256()
    for path in sorted(CASES.glob("*.json")):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_draft_does_not_change_case_file(notes_db):
    before = notes_db.get("/cases/CASE-001").json()
    digest = _case_digest()
    draft = notes_db.post("/cases/CASE-001/note-drafts")
    assert draft.status_code == 200
    body = draft.json()
    assert body["case_id"] == "CASE-001"
    assert body["status"] == "open"
    assert body["revision"] == 1
    assert "CASE-001" in body["body"]
    assert body["evidence"]
    assert "does not repair, release, return, or block" in body["body"]
    after = notes_db.get("/cases/CASE-001").json()
    assert after["notes"] == before["notes"]
    assert _case_digest() == digest
    history = notes_db.get("/cases/CASE-001/note-history").json()
    assert history["file_notes"] == before["notes"]
    assert history["approved_notes"] == []


def test_only_reviewed_wording_is_filed(notes_db):
    draft = notes_db.post("/cases/CASE-001/note-drafts").json()
    reviewed = "Analyst reviewed CASE-001. Request the bank identifier. Do not release the payment."
    saved = notes_db.patch(f"/note-drafts/{draft['draft_id']}", json={"body": reviewed, "expected_revision": 1})
    assert saved.status_code == 200
    assert saved.json()["revision"] == 2
    assert saved.json()["body"] == reviewed
    stale = notes_db.post(f"/note-drafts/{draft['draft_id']}/approve",
                          json={"body": draft["body"], "expected_revision": 1})
    assert stale.status_code == 409
    assert notes_db.get("/cases/CASE-001/note-history").json()["approved_notes"] == []
    filed = notes_db.post(f"/note-drafts/{draft['draft_id']}/approve",
                          json={"body": reviewed, "expected_revision": 2})
    assert filed.status_code == 200
    note = filed.json()
    assert note["body"] == reviewed
    assert note["body"] != draft["body"]
    history = notes_db.get("/cases/CASE-001/note-history").json()
    assert [item["body"] for item in history["approved_notes"]] == [reviewed]
    assert notes_db.get("/cases/CASE-001").json()["notes"] == history["file_notes"]


def test_approve_files_the_edited_wording_without_a_separate_save(notes_db):
    draft = notes_db.post("/cases/CASE-003/note-drafts").json()
    reviewed = "CASE-003 stays with the analyst. Conflicting details were not resolved."
    filed = notes_db.post(f"/note-drafts/{draft['draft_id']}/approve",
                          json={"body": reviewed, "expected_revision": 1})
    assert filed.status_code == 200
    assert filed.json()["body"] == reviewed
    history = notes_db.get("/cases/CASE-003/note-history").json()
    assert [item["body"] for item in history["approved_notes"]] == [reviewed]
    assert reviewed not in notes_db.get("/cases/CASE-003").json()["notes"]


def test_duplicate_and_discarded_submissions_do_not_write_twice(notes_db):
    draft = notes_db.post("/cases/CASE-002/note-drafts").json()
    payload = {"body": draft["body"], "expected_revision": 1}
    first = notes_db.post(f"/note-drafts/{draft['draft_id']}/approve", json=payload)
    second = notes_db.post(f"/note-drafts/{draft['draft_id']}/approve", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["note_id"] == first.json()["note_id"]
    changed = notes_db.post(f"/note-drafts/{draft['draft_id']}/approve",
                            json={"body": "A different note for CASE-002.", "expected_revision": 1})
    assert changed.status_code == 409
    assert len(notes_db.get("/cases/CASE-002/note-history").json()["approved_notes"]) == 1
    other = notes_db.post("/cases/CASE-002/note-drafts").json()
    discarded = notes_db.post(f"/note-drafts/{other['draft_id']}/discard", json={"expected_revision": 1})
    assert discarded.status_code == 200
    assert discarded.json()["status"] == "discarded"
    again = notes_db.post(f"/note-drafts/{other['draft_id']}/discard", json={"expected_revision": 1})
    assert again.status_code == 200
    filed_after_discard = notes_db.post(
        f"/note-drafts/{other['draft_id']}/approve", json={"body": other["body"], "expected_revision": 1})
    assert filed_after_discard.status_code == 409
    assert len(notes_db.get("/cases/CASE-002/note-history").json()["approved_notes"]) == 1


def test_unknown_case_and_invalid_note_are_rejected(notes_db):
    assert notes_db.post("/cases/CASE-999/note-drafts").status_code == 404
    draft = notes_db.post("/cases/CASE-001/note-drafts").json()
    assert notes_db.patch(f"/note-drafts/{draft['draft_id']}",
                          json={"body": "   ", "expected_revision": 1}).status_code == 422
    assert notes_db.post(f"/note-drafts/{draft['draft_id']}/approve",
                         json={"body": "x" * 4001, "expected_revision": 1}).status_code == 422
    assert notes_db.post(f"/note-drafts/{draft['draft_id']}/approve",
                         json={"body": "ok", "expected_revision": 1, "release": True}).status_code == 422
    assert notes_db.get("/cases/CASE-001/note-history").json()["approved_notes"] == []


def test_concurrent_approval_files_one_note(notes_db):
    draft = notes_db.post("/cases/CASE-004/note-drafts").json()
    body = "Reviewed CASE-004. Keep it with an analyst."
    barrier = threading.Barrier(2)
    results = []

    def file_note():
        barrier.wait()
        try:
            results.append(store.approve_draft(draft["draft_id"], body, 1))
        except store.NoteError as exc:
            results.append(exc)

    threads = [threading.Thread(target=file_note) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    notes = [item for item in results if isinstance(item, dict)]
    errors = [item for item in results if isinstance(item, store.NoteError)]
    assert len(store.list_notes("CASE-004")) == 1
    assert notes
    assert all(item["note_id"] == notes[0]["note_id"] and item["body"] == body for item in notes)
    assert all(item.status == 409 for item in errors)


def test_agents_have_no_note_write_tool():
    investigator = Path("app/agent/langchain_agent.py").read_text(encoding="utf-8")
    fraud = Path("app/agent/fraud_agent.py").read_text(encoding="utf-8")
    for source in (investigator, fraud):
        assert "sqlite" not in source.lower()
        assert "approve_draft" not in source
        assert "save_draft" not in source
    assert "app.notes" not in fraud
    assert "prepare_draft" in investigator and "list_notes" in investigator
