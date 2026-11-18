"""SQLite store for note drafts and analyst-approved case notes."""
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


class NoteError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def database_path() -> Path:
    configured = os.getenv("CASE_NOTES_DB")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "data" / "runtime" / "case_notes.sqlite"


def _connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS drafts (
            draft_id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL,
            body TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            revision INTEGER NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('open', 'discarded', 'approved')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS case_notes (
            note_id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL,
            draft_id TEXT NOT NULL UNIQUE,
            body TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            revision INTEGER NOT NULL,
            approved_at TEXT NOT NULL
        )""")
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _draft(row: sqlite3.Row) -> dict:
    return {"draft_id": row["draft_id"], "case_id": row["case_id"], "body": row["body"],
            "evidence": json.loads(row["evidence_json"]), "revision": row["revision"], "status": row["status"]}


def _note(row: sqlite3.Row) -> dict:
    return {"note_id": row["note_id"], "case_id": row["case_id"], "draft_id": row["draft_id"],
            "body": row["body"], "evidence": json.loads(row["evidence_json"]),
            "revision": row["revision"], "approved_at": row["approved_at"]}


def create_draft(case_id: str, body: str, evidence: list[dict[str, str]]) -> dict:
    draft_id = uuid.uuid4().hex
    now = _now()
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                "INSERT INTO drafts (draft_id, case_id, body, evidence_json, revision, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 1, 'open', ?, ?)",
                (draft_id, case_id, body, json.dumps(evidence), now, now))
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        row = connection.execute("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,)).fetchone()
    return _draft(row)


def get_draft(draft_id: str) -> dict:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,)).fetchone()
    if row is None:
        raise NoteError(404, "Draft not found")
    return _draft(row)


def update_draft(draft_id: str, body: str, expected_revision: int) -> dict:
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            row = connection.execute("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,)).fetchone()
            if row is None:
                raise NoteError(404, "Draft not found")
            if row["status"] != "open" or row["revision"] != expected_revision:
                raise NoteError(409, "This draft changed. Review the latest wording before saving.")
            revision = expected_revision + 1
            connection.execute(
                "UPDATE drafts SET body = ?, revision = ?, updated_at = ? WHERE draft_id = ? AND revision = ? AND status = 'open'",
                (body, revision, _now(), draft_id, expected_revision))
            if connection.execute("SELECT changes()").fetchone()[0] != 1:
                raise NoteError(409, "This draft changed. Review the latest wording before saving.")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        row = connection.execute("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,)).fetchone()
    return _draft(row)


def discard_draft(draft_id: str, expected_revision: int) -> dict:
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            row = connection.execute("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,)).fetchone()
            if row is None:
                raise NoteError(404, "Draft not found")
            if row["status"] == "discarded" and row["revision"] == expected_revision:
                connection.execute("COMMIT")
                return _draft(row)
            if row["status"] != "open" or row["revision"] != expected_revision:
                raise NoteError(409, "This draft changed and was not discarded.")
            connection.execute(
                "UPDATE drafts SET status = 'discarded', updated_at = ? WHERE draft_id = ? AND revision = ? AND status = 'open'",
                (_now(), draft_id, expected_revision))
            if connection.execute("SELECT changes()").fetchone()[0] != 1:
                raise NoteError(409, "This draft changed and was not discarded.")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        row = connection.execute("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,)).fetchone()
    return _draft(row)


def approve_draft(draft_id: str, body: str, expected_revision: int) -> dict:
    """File the exact reviewed wording once. A repeat of that same submission returns the filed note."""
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            row = connection.execute("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,)).fetchone()
            if row is None:
                raise NoteError(404, "Draft not found")
            existing = connection.execute("SELECT * FROM case_notes WHERE draft_id = ?", (draft_id,)).fetchone()
            if row["status"] == "approved" or existing is not None:
                if existing is not None and existing["body"] == body and existing["revision"] == expected_revision:
                    connection.execute("COMMIT")
                    return _note(existing)
                raise NoteError(409, "This draft was already filed with different wording.")
            if row["status"] != "open" or row["revision"] != expected_revision:
                raise NoteError(409, "This draft is out of date. Review the latest wording before filing.")
            note_id = uuid.uuid4().hex
            approved_at = _now()
            connection.execute(
                "INSERT INTO case_notes (note_id, case_id, draft_id, body, evidence_json, revision, approved_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (note_id, row["case_id"], draft_id, body, row["evidence_json"], expected_revision, approved_at))
            connection.execute(
                "UPDATE drafts SET body = ?, status = 'approved', updated_at = ? "
                "WHERE draft_id = ? AND revision = ? AND status = 'open'",
                (body, approved_at, draft_id, expected_revision))
            if connection.execute("SELECT changes()").fetchone()[0] != 1:
                raise NoteError(409, "This draft is out of date. Review the latest wording before filing.")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        row = connection.execute("SELECT * FROM case_notes WHERE draft_id = ?", (draft_id,)).fetchone()
    return _note(row)


def list_notes(case_id: str) -> list[dict]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM case_notes WHERE case_id = ? ORDER BY approved_at, note_id", (case_id,)).fetchall()
    return [_note(row) for row in rows]
