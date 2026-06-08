from typing import Any

from pydantic import BaseModel, Field

from app.models.domain import AuditEvent, Document, RfpRequirement, UsageMetric


class DemoTokenResponse(BaseModel):
    api_key: str
    header_name: str = "X-API-Key"


class IngestRequest(BaseModel):
    fixture_path: str | None = None
    document_type: str = "unknown"
    source: str = "local"
    tags: list[str] = Field(default_factory=list)


class IngestResponse(BaseModel):
    document: Document
    chunk_count: int


class AnalyzeRequest(BaseModel):
    rfp_document_id: str | None = None
    fixture_path: str | None = None
    text: str | None = None


class AnalyzeResponse(BaseModel):
    requirements: list[RfpRequirement]
    deadlines: list[str] = Field(default_factory=list)
    compliance_asks: list[str] = Field(default_factory=list)
    security_questions: list[str] = Field(default_factory=list)
    pricing_mentions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    trace_id: str


class QueryRequest(BaseModel):
    question: str
    top_k: int = 4


class DraftRequest(BaseModel):
    requirement_ids: list[str] = Field(default_factory=list)
    section_names: list[str] = Field(default_factory=list)
    top_k: int = 5


class EvaluateRequest(BaseModel):
    dataset_path: str = "sample_data/eval_dataset.json"
    top_k: int = 4


class EvaluationMetrics(BaseModel):
    question_count: int
    retrieval_precision_at_k: float
    citation_coverage: float
    missing_evidence_detection_count: int
    average_latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    passed: bool
    details: list[dict[str, Any]] = Field(default_factory=list)


class UsageResponse(BaseModel):
    metrics: list[UsageMetric]
    totals: dict[str, float | int]


class AuditResponse(BaseModel):
    events: list[AuditEvent]


class HealthResponse(BaseModel):
    status: str
    provider_mode: str
    vector_store_mode: str
    version: str
