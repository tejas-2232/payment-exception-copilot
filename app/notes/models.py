"""Request and response models for analyst-approved case notes."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _note_text(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("Note text is required")
    if len(text) > 4000:
        raise ValueError("Note text is too long")
    return text


class NoteEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    excerpt: str


class NoteDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft_id: str
    case_id: str
    body: str
    evidence: list[NoteEvidence]
    revision: int
    status: Literal["open", "discarded", "approved"]


class ApprovedNote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note_id: str
    case_id: str
    draft_id: str
    body: str
    evidence: list[NoteEvidence]
    revision: int
    approved_at: str


class NoteHistory(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    file_notes: list[str]
    approved_notes: list[ApprovedNote]


class NoteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(max_length=4000)
    expected_revision: int = Field(ge=1)

    @field_validator("body")
    @classmethod
    def require_text(cls, value: str) -> str:
        return _note_text(value)


class DiscardDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
