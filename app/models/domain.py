from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0


class Document(BaseModel):
    id: str = Field(default_factory=lambda: new_id("doc"))
    filename: str
    document_type: str = "unknown"
    source: str = "local"
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    status: str = "processed"
    metadata: dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    id: str = Field(default_factory=lambda: new_id("chk"))
    document_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding_id: str | None = None
    token_count: int = 0


class Citation(BaseModel):
    document_id: str
    chunk_id: str
    filename: str
    page: int | None = None
    snippet: str
    score: float


class RfpRequirement(BaseModel):
    id: str = Field(default_factory=lambda: new_id("req"))
    category: str
    text: str
    priority: str = "medium"
    due_date: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)


class RequirementMatrixRow(BaseModel):
    requirement_id: str
    category: str
    requirement_text: str
    priority: str
    owner_role: str
    status: str = "not_started"
    risk_level: str = "medium"
    evidence_refs: list[str] = Field(default_factory=list)
    suggested_response: str
    missing_evidence: list[str] = Field(default_factory=list)


class CustomerProfile(BaseModel):
    id: str
    name: str
    industry: str
    region: str
    security_priorities: list[str] = Field(default_factory=list)
    compliance_frameworks: list[str] = Field(default_factory=list)
    buyer_personas: list[str] = Field(default_factory=list)
    risk_tolerance: str = "medium"


class CustomerFitRequirement(BaseModel):
    requirement_id: str
    category: str
    requirement_text: str
    priority: str
    reason: str


class ApprovedResponseSnippet(BaseModel):
    id: str
    title: str
    category: str
    text: str
    tags: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    customer_profile_ids: list[str] = Field(default_factory=list)


class ResponseMemoryMatch(ApprovedResponseSnippet):
    confidence: float = 0.0


class ReviewFinding(BaseModel):
    finding_id: str = Field(default_factory=lambda: new_id("finding"))
    severity: str
    category: str
    message: str
    related_requirement_id: str | None = None
    related_question: str | None = None
    citation_refs: list[str] = Field(default_factory=list)
    recommendation: str


class ReviewReport(BaseModel):
    findings: list[ReviewFinding] = Field(default_factory=list)
    passed: bool
    summary: dict[str, Any] = Field(default_factory=dict)
    trace_id: str


class StakeholderTask(BaseModel):
    task_id: str = Field(default_factory=lambda: new_id("task"))
    owner_role: str
    title: str
    description: str
    priority: str
    due_hint: str
    source_requirement_id: str | None = None
    risk_level: str
    status: str
    evidence_refs: list[str] = Field(default_factory=list)


class EvidenceGap(BaseModel):
    gap_id: str
    title: str
    priority_rank: int
    severity: str
    owner_team: str
    missing_source_type: str
    impacted_sections: list[str] = Field(default_factory=list)
    requirement_ids: list[str] = Field(default_factory=list)
    contract_clause_ids: list[str] = Field(default_factory=list)
    due_date_recommendation: str
    suggested_sme_or_source_request: str
    related_citations: list[str] = Field(default_factory=list)
    red_team_risks: list[str] = Field(default_factory=list)
    closure_acceptance_criteria: list[str] = Field(default_factory=list)
    source_signals: list[str] = Field(default_factory=list)


class Answer(BaseModel):
    question: str
    answer_text: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = 0.0
    missing_evidence: list[str] = Field(default_factory=list)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    trace_id: str


class DraftSection(BaseModel):
    title: str
    body: str
    requirement_ids: list[str] = Field(default_factory=list)


class DraftResponse(BaseModel):
    sections: list[DraftSection]
    citations: list[Citation] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    revision_notes: list[str] = Field(default_factory=list)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    trace_id: str


class UsageMetric(BaseModel):
    trace_id: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    estimated_cost: float
    endpoint: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("evt"))
    trace_id: str
    actor: str = "demo-user"
    action: str
    resource_type: str
    resource_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)
