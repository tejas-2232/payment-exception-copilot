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


class SearchAttempt(BaseModel):
    query: str
    status: str


class InvestigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str = Field(min_length=1, max_length=100)
    mode: Literal["offline", "agent"] = "offline"


class InvestigationMetrics(BaseModel):
    total_duration_ms: float | None = None
    first_model_output_ms: float | None = None
    model_calls: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    estimated_cost_usd: float | None = None
    pricing_status: str = "Not available"


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
    search_attempts: list[SearchAttempt] = Field(default_factory=list)
    metrics: InvestigationMetrics | None = None
