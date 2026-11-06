from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Payment(BaseModel):
    payment_id: str
    amount: float
    currency: str
    beneficiary_name: str | None
    beneficiary_bank_identifier: str | None


class Case(BaseModel):
    case_id: str
    status: str
    partner_id: str
    exception_message: str
    payment: Payment
    notes: list[str]
    partner_response: str | None = None


class Evidence(BaseModel):
    document_id: str
    passage_id: str
    section: str
    version: str
    excerpt: str


class CaseEvidence(BaseModel):
    source_id: str
    excerpt: str


class InvestigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str = Field(min_length=1, max_length=100)
    mode: Literal["offline", "agent"] = "offline"


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    case_summary: str
    category: str
    recommended_next_steps: list[str]
    evidence: list[Evidence]
    missing_information: list[str]
    uncertainties: list[str]
    escalate_to_human: bool
    tool_activity: list[str] = Field(default_factory=list)
    case_evidence: list[CaseEvidence] = Field(default_factory=list)
