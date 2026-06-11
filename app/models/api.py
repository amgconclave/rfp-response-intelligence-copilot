from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.domain import (
    Answer,
    AuditEvent,
    Citation,
    CustomerFitRequirement,
    CustomerProfile,
    Document,
    DraftResponse,
    EvidenceGap,
    RequirementMatrixRow,
    ResponseMemoryMatch,
    ReviewFinding,
    ReviewReport,
    RfpRequirement,
    StakeholderTask,
    TokenUsage,
    UsageMetric,
)


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


class RequirementMatrixRequest(BaseModel):
    rfp_document_id: str | None = None
    analyzed_payload: AnalyzeResponse | None = None


class RequirementMatrixResponse(BaseModel):
    matrix: list[RequirementMatrixRow]
    trace_id: str


class CustomerProfilesResponse(BaseModel):
    profiles: list[CustomerProfile]


class CustomerFitRequest(BaseModel):
    customer_profile_id: str
    rfp_document_id: str | None = None
    analyzed_payload: AnalyzeResponse | None = None
    requirement_matrix: list[RequirementMatrixRow] | None = None


class CustomerFitResponse(BaseModel):
    customer_profile: CustomerProfile
    fit_score: float
    profile_risks: list[str] = Field(default_factory=list)
    recommended_positioning: list[str] = Field(default_factory=list)
    requirements_to_emphasize: list[CustomerFitRequirement] = Field(default_factory=list)
    requirements_needing_review: list[CustomerFitRequirement] = Field(default_factory=list)
    trace_id: str


class ResponseMemorySearchRequest(BaseModel):
    query: str
    category: str | None = None
    customer_profile_id: str | None = None
    top_k: int = 5


class ResponseMemorySearchResponse(BaseModel):
    matches: list[ResponseMemoryMatch]
    trace_id: str


class AnswerReuseLibraryRequest(BaseModel):
    category: str | None = None
    customer_profile_id: str | None = None
    include_expired: bool = True


class AnswerReuseSnippet(BaseModel):
    snippet_id: str
    title: str
    category: str
    reusable_text: str
    owner: str
    expires_at: str
    expiry_status: str
    approval_status: str
    reuse_decision: str
    confidence: float
    tags: list[str] = Field(default_factory=list)
    customer_profile_ids: list[str] = Field(default_factory=list)
    citation_refs: list[str] = Field(default_factory=list)
    citation_lineage: list[dict[str, Any]] = Field(default_factory=list)
    source_files: list[str] = Field(default_factory=list)
    reviewer_notes: list[str] = Field(default_factory=list)


class AnswerReuseLibraryResponse(BaseModel):
    title: str
    status: str
    snippets: list[AnswerReuseSnippet]
    summary: dict[str, Any]
    owner_queue: list[dict[str, Any]] = Field(default_factory=list)
    endpoint_references: list[dict[str, Any]] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_at: str
    trace_id: str


class AnswerReuseLibraryPackRequest(AnswerReuseLibraryRequest):
    library: AnswerReuseLibraryResponse | None = None
    write_artifact: bool = True


class AnswerReuseLibraryPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    library: AnswerReuseLibraryResponse
    trace_id: str


class AnswerReuseDriftRequest(AnswerReuseLibraryRequest):
    min_source_overlap: int = 4


class AnswerReuseDriftTransition(BaseModel):
    sequence: int
    from_state: str | None = None
    to_state: str
    decision: str
    status: str
    checkpoint_key: str
    reason: str


class AnswerReuseDriftFinding(BaseModel):
    snippet_id: str
    title: str
    category: str
    owner: str
    drift_status: str
    drift_score: int
    reuse_decision: str
    expiry_status: str
    citation_status: str
    source_overlap: int
    source_files: list[str] = Field(default_factory=list)
    missing_terms: list[str] = Field(default_factory=list)
    stale_claim_terms: list[str] = Field(default_factory=list)
    reviewer_action: str
    workflow_state: str
    transition_trace: list[AnswerReuseDriftTransition] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class AnswerReuseDriftResponse(BaseModel):
    title: str
    status: str
    findings: list[AnswerReuseDriftFinding]
    summary: dict[str, Any]
    owner_queue: list[dict[str, Any]] = Field(default_factory=list)
    workflow: dict[str, Any] = Field(default_factory=dict)
    endpoint_references: list[dict[str, Any]] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_at: str
    trace_id: str


class AnswerReuseDriftPackRequest(AnswerReuseDriftRequest):
    drift_report: AnswerReuseDriftResponse | None = None
    write_artifact: bool = True


class AnswerReuseDriftPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    drift_report: AnswerReuseDriftResponse
    trace_id: str


class ExportPackageRequest(BaseModel):
    rfp_document_id: str | None = None
    analyzed_payload: AnalyzeResponse | None = None
    draft_response: DraftResponse | None = None
    customer_profile_id: str | None = None
    include_response_memory: bool = False
    write_artifact: bool = True


class ExportPackageResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    package: dict[str, Any]
    trace_id: str


class ReviewAnswerRequest(BaseModel):
    question: str
    answer_text: str
    citations: list[Citation] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)


class ReviewAnswerResponse(ReviewReport):
    pass


class ReviewPackageRequest(BaseModel):
    rfp_document_id: str | None = None
    analyzed_payload: AnalyzeResponse | None = None
    requirement_matrix: list[RequirementMatrixRow] | None = None
    draft_response: DraftResponse | None = None
    answer_payloads: list[Answer] = Field(default_factory=list)
    export_payload: dict[str, Any] | None = None
    write_artifact: bool = False


class ReviewPackageResponse(ReviewReport):
    requirement_matrix: list[RequirementMatrixRow] = Field(default_factory=list)
    export_package: dict[str, Any] | None = None
    artifact_path: str | None = None


class ReviewerAssignment(BaseModel):
    assignment_id: str
    reviewer_role: str
    reviewer_name: str
    scope: str
    priority: str
    status: str
    approval_status: str
    due_hint: str
    requirement_ids: list[str] = Field(default_factory=list)
    source_signals: list[str] = Field(default_factory=list)
    blocking_items: list[str] = Field(default_factory=list)
    citation_refs: list[str] = Field(default_factory=list)


class ReviewerDecisionComment(BaseModel):
    comment_id: str
    reviewer_role: str
    reviewer_name: str
    category: str
    severity: str
    sentiment: str
    comment: str
    required_action: str
    status: str
    related_requirement_id: str | None = None
    related_artifact: str | None = None
    citation_refs: list[str] = Field(default_factory=list)


class ReviewerCollaborationRequest(BaseModel):
    rfp_document_id: str | None = None
    analysis: AnalyzeResponse | None = None
    analyzed_payload: AnalyzeResponse | None = None
    matrix: list[RequirementMatrixRow] | None = None
    requirement_matrix: list[RequirementMatrixRow] | None = None
    draft_response: DraftResponse | None = None
    review_findings: list[ReviewFinding] = Field(default_factory=list)
    review_passed: bool | None = None
    action_plan: list[StakeholderTask] = Field(default_factory=list)
    evidence_gaps: list[EvidenceGap] | None = None
    contract_risk: ContractRiskResponse | None = None
    submission_decision: SubmissionDecisionResponse | None = None


class ReviewerCollaborationResponse(BaseModel):
    title: str
    board_status: str
    assignments: list[ReviewerAssignment]
    decision_comments: list[ReviewerDecisionComment]
    approval_summary: dict[str, Any]
    redline_summary: dict[str, Any]
    reviewer_queue: list[dict[str, Any]] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_at: str
    trace_id: str


class ReviewerCollaborationPackRequest(ReviewerCollaborationRequest):
    collaboration: ReviewerCollaborationResponse | None = None
    write_artifact: bool = True


class ReviewerCollaborationPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    collaboration: ReviewerCollaborationResponse
    trace_id: str


class ReviewerWorkflowCheckpoint(BaseModel):
    checkpoint_id: str
    sequence: int
    state: str
    status: str
    owner_role: str
    decision: str
    rationale: str
    next_states: list[str] = Field(default_factory=list)
    blocking_signals: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class ReviewerWorkflowTransition(BaseModel):
    transition_id: str
    from_state: str
    to_state: str
    condition: str
    decision: str
    trace_note: str
    checkpoint_id: str


class ReviewerCollaborationWorkflowRequest(ReviewerCollaborationRequest):
    collaboration: ReviewerCollaborationResponse | None = None


class ReviewerCollaborationWorkflowResponse(BaseModel):
    title: str
    workflow_status: str
    current_state: str
    checkpoints: list[ReviewerWorkflowCheckpoint]
    transitions: list[ReviewerWorkflowTransition]
    state_summary: dict[str, Any] = Field(default_factory=dict)
    approval_path: list[dict[str, Any]] = Field(default_factory=list)
    replay_notes: list[str] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_at: str
    trace_id: str


class ReviewerCollaborationWorkflowPackRequest(ReviewerCollaborationWorkflowRequest):
    workflow: ReviewerCollaborationWorkflowResponse | None = None
    write_artifact: bool = True


class ReviewerCollaborationWorkflowPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    workflow: ReviewerCollaborationWorkflowResponse
    collaboration: ReviewerCollaborationResponse
    trace_id: str


class ActionPlanRequest(BaseModel):
    rfp_document_id: str | None = None
    analyzed_payload: AnalyzeResponse | None = None
    requirement_matrix: list[RequirementMatrixRow] | None = None
    customer_profile_id: str | None = None
    customer_profile: CustomerProfile | None = None
    customer_fit: CustomerFitResponse | None = None
    review_findings: list[ReviewFinding] = Field(default_factory=list)


class ActionPlanResponse(BaseModel):
    tasks: list[StakeholderTask]
    summary: dict[str, Any]
    trace_id: str


class HandoffBoardRequest(ActionPlanRequest):
    action_plan: list[StakeholderTask] | None = None
    write_artifact: bool = True


class HandoffBoardResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    board: dict[str, Any]
    trace_id: str


class DealReadinessScorecardRequest(BaseModel):
    analysis: AnalyzeResponse | None = None
    analyzed_payload: AnalyzeResponse | None = None
    matrix: list[RequirementMatrixRow] | None = None
    requirement_matrix: list[RequirementMatrixRow] | None = None
    review_findings: list[ReviewFinding] = Field(default_factory=list)
    customer_fit: CustomerFitResponse | None = None
    action_plan: list[StakeholderTask] = Field(default_factory=list)
    eval_metrics: EvaluationMetrics | None = None


class DealReadinessScorecardResponse(BaseModel):
    readiness_score: int
    readiness_level: str
    blockers: list[str] = Field(default_factory=list)
    evidence_coverage: float
    review_risk_count: int
    customer_fit_score: float | None = None
    owner_bottlenecks: list[dict[str, Any]] = Field(default_factory=list)
    score_trace: list[dict[str, Any]] = Field(default_factory=list)
    approval_workflow: list[dict[str, Any]] = Field(default_factory=list)
    human_review_queue: list[dict[str, Any]] = Field(default_factory=list)
    governance_summary: dict[str, Any] = Field(default_factory=dict)
    recommended_next_actions: list[str] = Field(default_factory=list)
    trace_id: str


class WinStrategyRequest(BaseModel):
    rfp_document_id: str | None = None
    analysis: AnalyzeResponse | None = None
    analyzed_payload: AnalyzeResponse | None = None
    matrix: list[RequirementMatrixRow] | None = None
    requirement_matrix: list[RequirementMatrixRow] | None = None
    customer_profile_id: str | None = None
    customer_fit: CustomerFitResponse | None = None
    readiness_scorecard: DealReadinessScorecardResponse | None = None
    response_memory_matches: list[ResponseMemoryMatch] = Field(default_factory=list)
    action_plan: list[StakeholderTask] = Field(default_factory=list)
    review_findings: list[ReviewFinding] = Field(default_factory=list)
    competitor_context: list[str] = Field(default_factory=list)
    pricing_notes: list[str] = Field(default_factory=list)


class WinStrategyResponse(BaseModel):
    win_score: int
    win_level: str
    competitor_risk_profile: dict[str, Any]
    pricing_risk: dict[str, Any]
    compliance_security_differentiators: list[dict[str, Any]] = Field(default_factory=list)
    proof_points: list[dict[str, Any]] = Field(default_factory=list)
    recommended_response_posture: str
    red_flags: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    next_actions_by_owner: list[dict[str, Any]] = Field(default_factory=list)
    trace_id: str


class OutcomeEvidenceSignal(BaseModel):
    evidence_id: str
    category: str
    claim: str
    source: str
    citation: str
    strength: float = 0.5


class PostRfpOutcome(BaseModel):
    outcome_id: str
    result: str
    customer_profile_id: str
    industry: str
    deal_value: int
    competitor: str | None = None
    submitted_at: str
    decision_notes: list[str] = Field(default_factory=list)
    evidence_used: list[OutcomeEvidenceSignal] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    pricing_posture: str = "standard"
    win_loss_reasons: list[str] = Field(default_factory=list)


class WinLossLearningRequest(BaseModel):
    outcomes_fixture_path: str = "sample_data/rfp_outcomes.json"
    outcomes: list[PostRfpOutcome] | None = None
    analysis: AnalyzeResponse | None = None
    analyzed_payload: AnalyzeResponse | None = None
    matrix: list[RequirementMatrixRow] | None = None
    requirement_matrix: list[RequirementMatrixRow] | None = None
    win_strategy: WinStrategyResponse | None = None
    eval_metrics: EvaluationMetrics | None = None
    top_k_patterns: int = 6


class WinLossLearningResponse(BaseModel):
    title: str
    outcome_count: int
    win_rate: float
    pattern_summary: dict[str, Any]
    winning_evidence_patterns: list[dict[str, Any]] = Field(default_factory=list)
    losing_risk_patterns: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_recommendations: list[dict[str, Any]] = Field(default_factory=list)
    eval_recommendations: list[dict[str, Any]] = Field(default_factory=list)
    response_guidance_updates: list[dict[str, Any]] = Field(default_factory=list)
    recommended_next_actions: list[dict[str, Any]] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_at: str
    trace_id: str


class WinLossStrategyPackRequest(WinLossLearningRequest):
    learning_response: WinLossLearningResponse | None = None
    write_artifact: bool = True


class WinLossStrategyPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    learning_response: WinLossLearningResponse
    trace_id: str


class PricingRiskMemoRequest(WinStrategyRequest):
    win_strategy: WinStrategyResponse | None = None
    write_artifact: bool = True


class PricingRiskMemoResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    memo: dict[str, Any]
    trace_id: str


class ObjectionHandlingRequest(WinStrategyRequest):
    objection_notes: list[str] = Field(default_factory=list)
    top_k: int = 4


class ObjectionWorkflowTransition(BaseModel):
    transition_id: str
    objection_id: str
    sequence: int
    from_state: str | None = None
    to_state: str
    decision: str
    status: str
    checkpoint_key: str
    owner_role: str
    evidence: str
    source_refs: list[str] = Field(default_factory=list)
    next_state: str | None = None


class ObjectionEvalAssertion(BaseModel):
    assertion_id: str
    description: str
    passed: bool
    evidence: str
    related_objection_ids: list[str] = Field(default_factory=list)


class ObjectionResponseItem(BaseModel):
    objection_id: str
    concern_type: str
    buyer_objection: str
    competitor_angle: str
    response_posture: str
    cited_response: str
    confidence: float
    risk_level: str
    approval_status: str
    required_reviewer_role: str
    citations: list[Citation] = Field(default_factory=list)
    source_snippets: list[dict[str, Any]] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    reviewer_notes: list[str] = Field(default_factory=list)
    recommended_followups: list[dict[str, Any]] = Field(default_factory=list)
    checkpoint_key: str = ""
    route_decision: str = "review"
    workflow_trace: list[ObjectionWorkflowTransition] = Field(default_factory=list)


class ObjectionHandlingResponse(BaseModel):
    title: str
    objections: list[ObjectionResponseItem]
    coverage_summary: dict[str, Any]
    confidence_summary: dict[str, Any]
    workflow_summary: dict[str, Any] = Field(default_factory=dict)
    eval_assertions: list[ObjectionEvalAssertion] = Field(default_factory=list)
    endpoint_references: list[dict[str, Any]] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_at: str
    trace_id: str


class ObjectionHandlingPackRequest(ObjectionHandlingRequest):
    objection_handling: ObjectionHandlingResponse | None = None
    write_artifact: bool = True


class ObjectionHandlingPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    objection_handling: ObjectionHandlingResponse
    trace_id: str


class ContractRiskClause(BaseModel):
    clause_id: str
    category: str
    title: str
    clause_text: str
    risk_level: str
    risk_score: int
    detected_terms: list[str] = Field(default_factory=list)
    rationale: str
    suggested_redline: str
    fallback_position: str
    proof_points: list[dict[str, Any]] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


class ContractRiskRequest(BaseModel):
    contract_document_id: str | None = None
    fixture_path: str | None = None
    text: str | None = None
    customer_profile_id: str | None = None


class ContractRiskResponse(BaseModel):
    risk_score: int
    status: str
    risky_clauses: list[ContractRiskClause] = Field(default_factory=list)
    category_counts: dict[str, int] = Field(default_factory=dict)
    suggested_redlines: list[dict[str, Any]] = Field(default_factory=list)
    fallback_positions: list[dict[str, Any]] = Field(default_factory=list)
    cited_proof_points: list[dict[str, Any]] = Field(default_factory=list)
    owner_actions: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_evidence_warnings: list[str] = Field(default_factory=list)
    trace_id: str


class NegotiationBriefRequest(ContractRiskRequest):
    contract_risk: ContractRiskResponse | None = None
    win_strategy: WinStrategyResponse | None = None
    pricing_memo: PricingRiskMemoResponse | None = None
    write_artifact: bool = True


class NegotiationBriefResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    brief: dict[str, Any]
    trace_id: str


class EvidenceGapRequest(BaseModel):
    rfp_document_id: str | None = None
    analysis: AnalyzeResponse | None = None
    analyzed_payload: AnalyzeResponse | None = None
    matrix: list[RequirementMatrixRow] | None = None
    requirement_matrix: list[RequirementMatrixRow] | None = None
    review_findings: list[ReviewFinding] = Field(default_factory=list)
    red_team_summary: dict[str, Any] | None = None
    readiness_scorecard: DealReadinessScorecardResponse | None = None
    win_strategy: WinStrategyResponse | None = None
    contract_risk: ContractRiskResponse | None = None
    action_plan: list[StakeholderTask] = Field(default_factory=list)


class EvidenceGapResponse(BaseModel):
    gaps: list[EvidenceGap]
    summary: dict[str, Any]
    trace_id: str


class SourceRequestPackRequest(EvidenceGapRequest):
    evidence_gaps: list[EvidenceGap] | None = None
    write_artifact: bool = True


class SourceRequestPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    trace_id: str


class TimelineMilestone(BaseModel):
    milestone_id: str
    sequence: int
    title: str
    owner_role: str
    due_date: str
    status: str
    category: str
    description: str
    dependencies: list[str] = Field(default_factory=list)
    related_requirement_ids: list[str] = Field(default_factory=list)
    source_signals: list[str] = Field(default_factory=list)


class TimelinePlanRequest(BaseModel):
    rfp_document_id: str | None = None
    analysis: AnalyzeResponse | None = None
    analyzed_payload: AnalyzeResponse | None = None
    matrix: list[RequirementMatrixRow] | None = None
    requirement_matrix: list[RequirementMatrixRow] | None = None
    review_findings: list[ReviewFinding] = Field(default_factory=list)
    action_plan: list[StakeholderTask] = Field(default_factory=list)
    evidence_gaps: list[EvidenceGap] | None = None
    contract_risk: ContractRiskResponse | None = None
    win_strategy: WinStrategyResponse | None = None
    readiness_scorecard: DealReadinessScorecardResponse | None = None
    source_request_pack: dict[str, Any] | None = None
    leadership_brief: dict[str, Any] | None = None
    red_team_summary: dict[str, Any] | None = None


class TimelinePlanResponse(BaseModel):
    milestones: list[TimelineMilestone]
    owner_assignments: list[dict[str, Any]] = Field(default_factory=list)
    dependencies: list[dict[str, Any]] = Field(default_factory=list)
    risk_buffers: list[dict[str, Any]] = Field(default_factory=list)
    blocked_items: list[dict[str, Any]] = Field(default_factory=list)
    readiness_gates: list[dict[str, Any]] = Field(default_factory=list)
    escalation_triggers: list[dict[str, Any]] = Field(default_factory=list)
    calendar_entries: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    trace_id: str


class SubmissionCalendarPackRequest(TimelinePlanRequest):
    timeline_plan: TimelinePlanResponse | None = None
    write_artifact: bool = True


class SubmissionCalendarPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    trace_id: str


class SubmissionDecisionRequest(BaseModel):
    rfp_document_id: str | None = None
    analysis: AnalyzeResponse | None = None
    analyzed_payload: AnalyzeResponse | None = None
    matrix: list[RequirementMatrixRow] | None = None
    requirement_matrix: list[RequirementMatrixRow] | None = None
    draft_response: DraftResponse | None = None
    answers: list[Answer] = Field(default_factory=list)
    review_findings: list[ReviewFinding] = Field(default_factory=list)
    review_passed: bool | None = None
    action_plan: list[StakeholderTask] = Field(default_factory=list)
    readiness_scorecard: DealReadinessScorecardResponse | None = None
    eval_metrics: EvaluationMetrics | None = None
    red_team_summary: dict[str, Any] | None = None
    win_strategy: WinStrategyResponse | None = None
    contract_risk: ContractRiskResponse | None = None
    evidence_gaps: list[EvidenceGap] | None = None
    source_request_pack: dict[str, Any] | None = None
    timeline_plan: TimelinePlanResponse | None = None
    leadership_brief: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    export_artifact_path: str | None = None
    export_json_artifact_path: str | None = None
    source_request_artifact_path: str | None = None
    source_request_json_artifact_path: str | None = None
    submission_calendar_artifact_path: str | None = None
    submission_calendar_json_artifact_path: str | None = None
    leadership_brief_artifact_path: str | None = None
    leadership_brief_json_artifact_path: str | None = None


class SubmissionDecisionResponse(BaseModel):
    decision: str
    score: int
    blocking_issues: list[dict[str, Any]] = Field(default_factory=list)
    exception_list: list[dict[str, Any]] = Field(default_factory=list)
    approvals_required: list[dict[str, Any]] = Field(default_factory=list)
    owner_actions: list[dict[str, Any]] = Field(default_factory=list)
    artifact_links: dict[str, Any] = Field(default_factory=dict)
    rationale: list[str] = Field(default_factory=list)
    local_verification_commands: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    trace_id: str


class ExecutiveSubmissionMemoRequest(SubmissionDecisionRequest):
    submission_decision: SubmissionDecisionResponse | None = None
    write_artifact: bool = True


class ExecutiveSubmissionMemoResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    memo: dict[str, Any]
    trace_id: str


class SubmissionExceptionItem(BaseModel):
    exception_id: str
    source: str
    waiver_type: str
    severity: str
    owner: str
    approver_role: str
    status: str
    expires_at: str
    title: str
    risk_acceptance: str
    required_evidence: list[str] = Field(default_factory=list)
    linked_requirement_ids: list[str] = Field(default_factory=list)
    linked_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    source_signals: list[str] = Field(default_factory=list)
    local_policy: str
    escalation_path: list[str] = Field(default_factory=list)


class SubmissionExceptionRegisterRequest(SubmissionDecisionRequest):
    submission_decision: SubmissionDecisionResponse | None = None
    reviewer_collaboration: ReviewerCollaborationResponse | None = None


class SubmissionExceptionRegisterResponse(BaseModel):
    title: str
    register_status: str
    exceptions: list[SubmissionExceptionItem]
    summary: dict[str, Any]
    approval_queue: list[dict[str, Any]] = Field(default_factory=list)
    endpoint_references: list[dict[str, Any]] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_at: str
    trace_id: str


class SubmissionExceptionPackRequest(SubmissionExceptionRegisterRequest):
    exception_register: SubmissionExceptionRegisterResponse | None = None
    write_artifact: bool = True


class SubmissionExceptionPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    exception_register: SubmissionExceptionRegisterResponse
    trace_id: str


class ExecutiveRiskReportRequest(DealReadinessScorecardRequest):
    red_team_summary: dict[str, Any] | None = None
    write_artifact: bool = True


class ExecutiveRiskReportResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    report: dict[str, Any]
    trace_id: str


class ProposalReadinessScorePackRequest(ExecutiveRiskReportRequest):
    draft_response: DraftResponse | None = None
    readiness_scorecard: DealReadinessScorecardResponse | None = None
    executive_report: ExecutiveRiskReportResponse | None = None


class ProposalReadinessScorePackResponse(BaseModel):
    title: str
    status: str
    readiness_score: int
    readiness_level: str
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    readiness_scorecard: DealReadinessScorecardResponse
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_at: str
    trace_id: str


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


class SubmissionRegressionRequest(BaseModel):
    rfp_fixture_path: str = "sample_data/acme_enterprise_rfp.md"
    eval_dataset_path: str = "sample_data/eval_dataset.json"
    red_team_dataset_path: str = "sample_data/red_team_questions.json"
    customer_profile_id: str = "regulated_healthcare"
    top_k: int = 4
    write_artifacts: bool = True


class SubmissionRegressionCheck(BaseModel):
    name: str
    passed: bool
    evidence_count: int = 0
    details: dict[str, Any] = Field(default_factory=dict)


class SubmissionRegressionResponse(BaseModel):
    passed: bool
    checks: list[SubmissionRegressionCheck]
    evidence_counts: dict[str, int | float | bool | str | None]
    failed_checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    artifact_paths: dict[str, str | None] = Field(default_factory=dict)
    eval_summary: EvaluationMetrics
    red_team_summary: dict[str, Any]
    interview_ready_summary: str
    trace_id: str


class DemoScriptRequest(BaseModel):
    regression: SubmissionRegressionResponse | None = None
    run_regression: bool = True
    regression_request: SubmissionRegressionRequest = Field(default_factory=SubmissionRegressionRequest)
    write_artifact: bool = True


class DemoScriptResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    script: dict[str, Any]
    trace_id: str


class LeadershipBriefRequest(BaseModel):
    rfp_document_id: str | None = None
    analysis: AnalyzeResponse | None = None
    analyzed_payload: AnalyzeResponse | None = None
    matrix: list[RequirementMatrixRow] | None = None
    requirement_matrix: list[RequirementMatrixRow] | None = None
    draft_response: DraftResponse | None = None
    answers: list[Answer] = Field(default_factory=list)
    export_payload: dict[str, Any] | None = None
    export_artifact_path: str | None = None
    export_json_artifact_path: str | None = None
    review_findings: list[ReviewFinding] = Field(default_factory=list)
    review_passed: bool | None = None
    customer_profile_id: str | None = None
    customer_fit: CustomerFitResponse | None = None
    response_memory_matches: list[ResponseMemoryMatch] = Field(default_factory=list)
    action_plan: list[StakeholderTask] = Field(default_factory=list)
    handoff_board: dict[str, Any] | None = None
    handoff_artifact_path: str | None = None
    handoff_json_artifact_path: str | None = None
    readiness_scorecard: DealReadinessScorecardResponse | None = None
    executive_report: ExecutiveRiskReportResponse | None = None
    executive_report_artifact_path: str | None = None
    executive_report_json_artifact_path: str | None = None
    eval_metrics: EvaluationMetrics | None = None
    red_team_summary: dict[str, Any] | None = None
    write_artifact: bool = True


class LeadershipBriefResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    brief: dict[str, Any]
    trace_id: str


class EvaluateRequest(BaseModel):
    dataset_path: str = "sample_data/eval_dataset.json"
    top_k: int = 4


class RagCoverageCheck(BaseModel):
    name: str
    status: str
    passed: int
    total: int
    coverage: float
    missing: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class RagCorpusCoverageResponse(BaseModel):
    title: str
    status: str
    score: int
    corpus_metadata: dict[str, Any]
    doc_category_coverage: RagCoverageCheck
    eval_coverage: RagCoverageCheck
    citation_source_coverage: RagCoverageCheck
    red_team_coverage: RagCoverageCheck
    missing_evidence_coverage: RagCoverageCheck
    gaps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    local_commands: list[str] = Field(default_factory=list)
    generated_at: str
    trace_id: str


class RagEvalCoveragePackRequest(BaseModel):
    write_artifact: bool = True


class RagEvalCoveragePackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    coverage: RagCorpusCoverageResponse
    trace_id: str


class RetrievalExperimentRequest(BaseModel):
    dataset_path: str = "sample_data/eval_dataset.json"
    outcomes_fixture_path: str = "sample_data/rfp_outcomes.json"
    top_k: int = 4
    policy_ids: list[str] = Field(default_factory=list)


class RetrievalExperimentResponse(BaseModel):
    title: str
    status: str
    recommended_policy_id: str
    summary: dict[str, Any]
    policy_results: list[dict[str, Any]] = Field(default_factory=list)
    question_diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    trace_spans: list[dict[str, Any]] = Field(default_factory=list)
    governance_decision: dict[str, Any]
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_at: str
    trace_id: str


class RetrievalExperimentPackRequest(RetrievalExperimentRequest):
    comparison: RetrievalExperimentResponse | None = None
    write_artifact: bool = True


class RetrievalExperimentPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    comparison: RetrievalExperimentResponse
    trace_id: str


class ComplianceRequirementLink(BaseModel):
    requirement_id: str
    requirement_text: str
    category: str
    priority: str
    matrix_status: str | None = None
    risk_level: str | None = None


class ComplianceEvidenceSource(BaseModel):
    document_id: str | None = None
    chunk_id: str | None = None
    filename: str
    document_type: str
    snippet: str
    matched_terms: list[str] = Field(default_factory=list)
    score: float


class ComplianceControlMapping(BaseModel):
    control_id: str
    control_family: str
    title: str
    requirement_links: list[ComplianceRequirementLink] = Field(default_factory=list)
    source_docs: list[ComplianceEvidenceSource] = Field(default_factory=list)
    policy_sources: list[str] = Field(default_factory=list)
    confidence: float
    owner: str
    status: str
    missing_evidence_warnings: list[str] = Field(default_factory=list)
    unsupported_claim_flags: list[str] = Field(default_factory=list)
    reviewer_notes: list[str] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)


class ComplianceEvidenceMatrixResponse(BaseModel):
    title: str
    control_mappings: list[ComplianceControlMapping]
    coverage_summary: dict[str, Any]
    unsupported_claims: list[dict[str, Any]] = Field(default_factory=list)
    owner_followups: list[dict[str, Any]] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_at: str
    trace_id: str


class ControlPackRequest(BaseModel):
    write_artifact: bool = True


class ControlPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    matrix: ComplianceEvidenceMatrixResponse
    trace_id: str


class PrivacyGuardrailSurface(BaseModel):
    surface_id: str
    surface_name: str
    data_categories: list[str] = Field(default_factory=list)
    policy_evidence: list[ComplianceEvidenceSource] = Field(default_factory=list)
    risk_level: str
    risk_score: int
    retention_posture: str
    reviewer_owner: str
    required_controls: list[str] = Field(default_factory=list)
    missing_controls: list[str] = Field(default_factory=list)
    redaction_rules: list[str] = Field(default_factory=list)
    endpoint_references: list[str] = Field(default_factory=list)


class PrivacyRetentionGuardrailResponse(BaseModel):
    title: str
    generated_at: str
    surfaces: list[PrivacyGuardrailSurface]
    summary: dict[str, Any]
    retention_actions: list[dict[str, Any]] = Field(default_factory=list)
    prompt_logging_guidance: list[str] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    trace_id: str


class PrivacyRetentionPackRequest(BaseModel):
    write_artifact: bool = True


class PrivacyRetentionPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    guardrails: PrivacyRetentionGuardrailResponse
    trace_id: str


class ModelRiskRegisterItem(BaseModel):
    risk_id: str
    title: str
    risk_category: str
    severity: str
    likelihood: str
    status: str
    reviewer_owner: str
    description: str
    mitigation_controls: list[str] = Field(default_factory=list)
    evidence_sources: list[ComplianceEvidenceSource] = Field(default_factory=list)
    eval_gate: str
    red_team_gate: str
    endpoint_references: list[str] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)


class ModelRiskRegisterResponse(BaseModel):
    title: str
    generated_at: str
    provider_mode: str
    register_status: str
    risks: list[ModelRiskRegisterItem]
    summary: dict[str, Any]
    release_gates: list[dict[str, Any]] = Field(default_factory=list)
    reviewer_queue: list[dict[str, Any]] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    trace_id: str


class ModelRiskPackRequest(BaseModel):
    write_artifact: bool = True


class ModelRiskPackResponse(BaseModel):
    model_config = {"populate_by_name": True}

    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    risk_register: ModelRiskRegisterResponse = Field(alias="register")
    trace_id: str


class CitationLineageItem(BaseModel):
    citation_id: str
    source_kind: str
    source_label: str
    document_id: str
    chunk_id: str
    filename: str
    document_exists: bool
    chunk_exists: bool
    filename_match: bool
    snippet_match: bool
    integrity_status: str
    risk_level: str
    risk_flags: list[str] = Field(default_factory=list)
    score: float
    document_type: str
    policy_owner: str
    source_path: str | None = None
    citation_snippet: str
    repository_excerpt: str | None = None
    endpoint_references: list[str] = Field(default_factory=list)


class CitationLineageAuditResponse(BaseModel):
    title: str
    status: str
    score: int
    summary: dict[str, Any]
    lineages: list[CitationLineageItem]
    missing_citations: list[dict[str, Any]] = Field(default_factory=list)
    stale_citations: list[dict[str, Any]] = Field(default_factory=list)
    generated_claim_flags: list[dict[str, Any]] = Field(default_factory=list)
    owner_followups: list[dict[str, Any]] = Field(default_factory=list)
    endpoint_references: list[dict[str, Any]] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_at: str
    trace_id: str


class CitationLineagePackRequest(BaseModel):
    write_artifact: bool = True


class CitationLineagePackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    lineage: CitationLineageAuditResponse
    trace_id: str


class EvidenceFreshnessSource(BaseModel):
    document_id: str
    filename: str
    document_type: str
    policy_owner: str
    effective_date: str | None = None
    renewal_date: str | None = None
    age_days: int | None = None
    days_until_renewal: int | None = None
    expiry_status: str
    freshness_score: int
    risk_level: str
    risk_drivers: list[str] = Field(default_factory=list)
    unsupported_claim_flags: list[str] = Field(default_factory=list)
    endpoint_references: list[str] = Field(default_factory=list)
    citation_use_count: int
    chunk_count: int
    source_path: str | None = None


class EvidenceFreshnessResponse(BaseModel):
    title: str
    generated_at: str
    sources: list[EvidenceFreshnessSource]
    summary: dict[str, Any]
    unsupported_claims: list[dict[str, Any]] = Field(default_factory=list)
    renewal_calendar: list[dict[str, Any]] = Field(default_factory=list)
    owner_followups: list[dict[str, Any]] = Field(default_factory=list)
    endpoint_references: list[dict[str, Any]] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    trace_id: str


class EvidenceFreshnessPackRequest(BaseModel):
    write_artifact: bool = True


class EvidenceFreshnessPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    freshness: EvidenceFreshnessResponse
    trace_id: str


class EvidenceConflictClaim(BaseModel):
    claim_id: str
    topic: str
    claim_type: str
    normalized_claim: str
    stance: str
    source_owner: str
    authority_rank: int
    citation: Citation
    snippet: str


class EvidenceConflictItem(BaseModel):
    conflict_id: str
    topic: str
    severity: str
    status: str
    reviewer_owner: str
    resolution_guidance: str
    cited_resolution: str
    primary_claim: EvidenceConflictClaim
    conflicting_claims: list[EvidenceConflictClaim] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    reviewer_actions: list[dict[str, Any]] = Field(default_factory=list)
    endpoint_references: list[dict[str, Any]] = Field(default_factory=list)


class EvidenceConflictResponse(BaseModel):
    title: str
    conflicts: list[EvidenceConflictItem]
    summary: dict[str, Any]
    reviewer_queue: list[dict[str, Any]] = Field(default_factory=list)
    endpoint_references: list[dict[str, Any]] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_at: str
    trace_id: str


class EvidenceConflictPackRequest(BaseModel):
    write_artifact: bool = True


class EvidenceConflictPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    conflicts: EvidenceConflictResponse
    trace_id: str


class SourceTrustItem(BaseModel):
    source_id: str
    filename: str
    document_type: str
    policy_owner: str
    trust_score: int
    trust_decision: str
    approval_required: bool
    freshness_score: int
    freshness_risk_level: str
    expiry_status: str
    citation_use_count: int
    conflict_count: int
    blocking_conflict_count: int
    lineage_issue_count: int
    retrieval_policy: str
    guardrails: list[str] = Field(default_factory=list)
    reviewer_owners: list[str] = Field(default_factory=list)
    endpoint_references: list[str] = Field(default_factory=list)
    source_path: str | None = None


class SourceTrustGateResponse(BaseModel):
    title: str
    status: str
    generated_at: str
    sources: list[SourceTrustItem]
    summary: dict[str, Any]
    reviewer_queue: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_policy_updates: list[dict[str, Any]] = Field(default_factory=list)
    endpoint_references: list[dict[str, Any]] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    trace_id: str


class SourceTrustPackRequest(BaseModel):
    write_artifact: bool = True


class SourceTrustPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    source_trust: SourceTrustGateResponse
    trace_id: str


class GovernedRetrievalRequest(BaseModel):
    question: str = "What disaster recovery, uptime, SSO, encryption, and audit controls are supported?"
    top_k: int = 6
    include_suppressed: bool = False


class GovernedRetrievalResult(BaseModel):
    result_id: str
    filename: str
    chunk_id: str
    original_score: float
    adjusted_score: float
    retrieval_policy: str
    trust_decision: str
    trust_score: int
    governance_action: str
    visible_to_generator: bool
    approval_required: bool
    reviewer_owners: list[str] = Field(default_factory=list)
    reason: str
    guardrails: list[str] = Field(default_factory=list)
    citation: Citation


class GovernedRetrievalResponse(BaseModel):
    title: str
    question: str
    status: str
    generated_at: str
    top_k: int
    include_suppressed: bool
    results: list[GovernedRetrievalResult]
    allowed_citations: list[Citation] = Field(default_factory=list)
    blocked_results: list[GovernedRetrievalResult] = Field(default_factory=list)
    reviewer_queue: list[dict[str, Any]] = Field(default_factory=list)
    policy_trace: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any]
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    trace_id: str


class GovernedRetrievalPackRequest(GovernedRetrievalRequest):
    governed_retrieval: GovernedRetrievalResponse | None = None
    write_artifact: bool = True


class GovernedRetrievalPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    governed_retrieval: GovernedRetrievalResponse
    trace_id: str


class BuyerWorkflowStage(BaseModel):
    stage_id: str
    sequence: int
    name: str
    owner_role: str
    status: str
    durability_key: str
    restart_policy: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    governance_gates: list[str] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)


class BuyerApprovalQueueItem(BaseModel):
    approval_id: str
    reviewer_role: str
    decision_area: str
    priority: str
    status: str
    reason: str
    required_before: str
    related_stage_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class BuyerGovernanceGate(BaseModel):
    gate_id: str
    name: str
    status: str
    owner_role: str
    evidence: str
    required_action: str
    endpoint_refs: list[str] = Field(default_factory=list)


class BuyerProviderRoute(BaseModel):
    provider_mode: str
    readiness: str
    use_when: str
    required_env: list[str] = Field(default_factory=list)
    governance_notes: list[str] = Field(default_factory=list)


class BuyerWorkflowTransition(BaseModel):
    transition_id: str
    replay_order: int
    from_stage_id: str | None = None
    to_stage_id: str
    condition: str
    decision: str
    status: str
    evidence: str
    checkpoint_key: str
    trace_refs: list[str] = Field(default_factory=list)


class BuyerIntelligenceWorkflowResponse(BaseModel):
    title: str
    workflow_id: str
    workflow_status: str
    generated_at: str
    durable_state: dict[str, Any]
    shared_state: dict[str, Any]
    workflow_stages: list[BuyerWorkflowStage]
    human_approval_queue: list[BuyerApprovalQueueItem] = Field(default_factory=list)
    governance_gates: list[BuyerGovernanceGate] = Field(default_factory=list)
    provider_routes: list[BuyerProviderRoute] = Field(default_factory=list)
    trace_analysis: dict[str, Any] = Field(default_factory=dict)
    buyer_readout: dict[str, Any] = Field(default_factory=dict)
    endpoint_references: list[dict[str, Any]] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    trace_id: str


class BuyerIntelligencePackRequest(BaseModel):
    write_artifact: bool = True


class BuyerIntelligencePackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    state_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    workflow: BuyerIntelligenceWorkflowResponse
    trace_id: str


class BuyerWorkflowReplayResponse(BaseModel):
    title: str
    status: str
    generated_at: str
    workflow_id: str
    transition_count: int
    transitions: list[BuyerWorkflowTransition]
    route_decisions: list[dict[str, Any]] = Field(default_factory=list)
    checkpoint_validation: dict[str, Any] = Field(default_factory=dict)
    replay_summary: dict[str, Any] = Field(default_factory=dict)
    eval_scenarios: list[dict[str, Any]] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    trace_id: str


class BuyerWorkflowReplayPackRequest(BaseModel):
    write_artifact: bool = True


class BuyerWorkflowReplayPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    replay: BuyerWorkflowReplayResponse
    trace_id: str


class ProposalCouncilAgent(BaseModel):
    agent_id: str
    role: str
    mandate: str
    allowed_tools: list[str] = Field(default_factory=list)
    blocked_tools: list[str] = Field(default_factory=list)
    approval_scope: list[str] = Field(default_factory=list)
    budget_tokens: int


class ProposalCouncilMessage(BaseModel):
    message_id: str
    turn: int
    agent_id: str
    role: str
    message_type: str
    content: str
    cited_evidence: list[str] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    handoff_to: str | None = None
    governance_flags: list[str] = Field(default_factory=list)
    token_estimate: int


class ProposalCouncilHandoff(BaseModel):
    handoff_id: str
    from_agent_id: str
    to_agent_id: str
    reason: str
    status: str
    required_before: str
    evidence_refs: list[str] = Field(default_factory=list)


class ProposalAgentCouncilResponse(BaseModel):
    title: str
    council_id: str
    status: str
    generated_at: str
    agents: list[ProposalCouncilAgent]
    conversation: list[ProposalCouncilMessage]
    shared_state: dict[str, Any]
    handoffs: list[ProposalCouncilHandoff] = Field(default_factory=list)
    tool_governance: list[dict[str, Any]] = Field(default_factory=list)
    budget_ledger: dict[str, Any] = Field(default_factory=dict)
    decision_summary: dict[str, Any] = Field(default_factory=dict)
    eval_scenarios: list[dict[str, Any]] = Field(default_factory=list)
    endpoint_references: list[dict[str, Any]] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    trace_id: str


class ProposalAgentCouncilPackRequest(BaseModel):
    write_artifact: bool = True


class ProposalAgentCouncilPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    transcript_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    council: ProposalAgentCouncilResponse
    trace_id: str


class ProposalProvenanceNode(BaseModel):
    node_id: str
    node_type: str
    label: str
    owner_role: str | None = None
    status: str
    evidence: str
    source_refs: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    endpoint_refs: list[str] = Field(default_factory=list)


class ProposalProvenanceEdge(BaseModel):
    edge_id: str
    from_node_id: str
    to_node_id: str
    relation: str
    condition: str
    trace_refs: list[str] = Field(default_factory=list)


class ProposalDecisionProvenanceResponse(BaseModel):
    title: str
    provenance_id: str
    status: str
    generated_at: str
    nodes: list[ProposalProvenanceNode]
    edges: list[ProposalProvenanceEdge]
    summary: dict[str, Any] = Field(default_factory=dict)
    decision_controls: list[dict[str, Any]] = Field(default_factory=list)
    eval_assertions: list[dict[str, Any]] = Field(default_factory=list)
    endpoint_references: list[dict[str, Any]] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    trace_id: str


class ProposalDecisionProvenancePackRequest(BaseModel):
    write_artifact: bool = True


class ProposalDecisionProvenancePackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    provenance: ProposalDecisionProvenanceResponse
    trace_id: str


class ProcurementQuestionRiskItem(BaseModel):
    question_id: str
    question_type: str
    category: str
    question: str
    risk_level: str
    required_reviewer_role: str
    approval_status: str
    evidence_support: str
    unsupported_claim_flag: bool
    citations: list[Citation] = Field(default_factory=list)
    snippets: list[dict[str, Any]] = Field(default_factory=list)
    approved_memory_matches: list[ResponseMemoryMatch] = Field(default_factory=list)
    draft_answer: str
    reviewer_checklist: list[str] = Field(default_factory=list)
    escalation_owner: str
    evidence_gaps: list[str] = Field(default_factory=list)
    approval_rationale: str
    review_findings: list[ReviewFinding] = Field(default_factory=list)


class ProcurementQuestionRiskResponse(BaseModel):
    title: str
    questions: list[ProcurementQuestionRiskItem]
    coverage_summary: dict[str, Any]
    approval_summary: dict[str, Any]
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_at: str
    trace_id: str


class ProcurementApprovalPackRequest(BaseModel):
    write_artifact: bool = True


class ProcurementApprovalPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    question_risk: ProcurementQuestionRiskResponse
    trace_id: str


class ProcurementRiskDeskItem(BaseModel):
    risk_id: str
    category: str
    title: str
    severity: str
    risk_score: int
    status: str
    owner_role: str
    reviewer_role: str
    due_hint: str
    source_signals: list[str] = Field(default_factory=list)
    rationale: str
    recommended_actions: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    related_requirement_ids: list[str] = Field(default_factory=list)
    related_contract_clause_ids: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    snippets: list[dict[str, Any]] = Field(default_factory=list)


class ProcurementRiskDeskResponse(BaseModel):
    title: str
    risks: list[ProcurementRiskDeskItem]
    summary: dict[str, Any]
    owner_routing: list[dict[str, Any]] = Field(default_factory=list)
    workflow_stages: list[dict[str, Any]] = Field(default_factory=list)
    human_review_queue: list[dict[str, Any]] = Field(default_factory=list)
    trace_spans: list[dict[str, Any]] = Field(default_factory=list)
    governance_summary: dict[str, Any] = Field(default_factory=dict)
    packet_sources: list[str] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_at: str
    trace_id: str


class ProcurementRiskDeskPackRequest(BaseModel):
    write_artifact: bool = True


class ProcurementRiskDeskPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    risk_desk: ProcurementRiskDeskResponse
    trace_id: str


class BidScenario(BaseModel):
    scenario_id: str
    name: str
    decision_recommendation: str
    deal_value: int
    pursuit_effort_hours: int
    pursuit_cost: int
    win_probability: float
    gross_margin: float
    risk_adjusted_revenue: int
    risk_adjusted_gross_profit: int
    risk_adjusted_roi: float
    roi_formula: str
    blockers: list[dict[str, Any]] = Field(default_factory=list)
    required_reviewers: list[str] = Field(default_factory=list)
    evidence_readiness: dict[str, Any] = Field(default_factory=dict)
    timeline_pressure: dict[str, Any] = Field(default_factory=dict)
    coverage_summary: dict[str, Any] = Field(default_factory=dict)
    customer_profile: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)


class BidScenarioAnalysisResponse(BaseModel):
    title: str
    scenarios: list[BidScenario]
    recommended_scenario_id: str
    coverage_summary: dict[str, Any]
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_at: str
    trace_id: str


class BidRoiPackRequest(BaseModel):
    scenario_analysis: BidScenarioAnalysisResponse | None = None
    write_artifact: bool = True


class BidRoiPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    scenario_analysis: BidScenarioAnalysisResponse
    trace_id: str


class CostGovernanceRequest(BaseModel):
    daily_rfp_count: int = 3
    questions_per_rfp: int = 12
    draft_sections_per_rfp: int = 5
    eval_runs_per_day: int = 1
    red_team_runs_per_day: int = 1
    daily_budget_usd: float = 25.0


class CostGovernanceResponse(BaseModel):
    title: str
    governance_status: str
    provider_readiness: dict[str, Any]
    token_profile: dict[str, Any]
    workflow_estimates: list[dict[str, Any]] = Field(default_factory=list)
    budget_summary: dict[str, Any]
    reviewer_controls: list[dict[str, Any]] = Field(default_factory=list)
    local_proof_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_at: str
    trace_id: str


class CostGovernancePackRequest(CostGovernanceRequest):
    governance: CostGovernanceResponse | None = None
    write_artifact: bool = True


class CostGovernancePackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    governance: CostGovernanceResponse
    trace_id: str


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


class RuntimeDemoPackRequest(BaseModel):
    write_artifact: bool = True


class RuntimeDemoReadinessResponse(BaseModel):
    title: str
    status: str
    provider_mode: str
    vector_store_mode: str
    local_run_commands: list[str] = Field(default_factory=list)
    stop_commands: list[str] = Field(default_factory=list)
    expected_ports: list[dict[str, Any]] = Field(default_factory=list)
    env_requirements: list[dict[str, Any]] = Field(default_factory=list)
    dependency_checks: list[dict[str, Any]] = Field(default_factory=list)
    process_port_checks: list[dict[str, Any]] = Field(default_factory=list)
    expected_health_urls: list[dict[str, Any]] = Field(default_factory=list)
    rag_eval_red_team_commands: list[str] = Field(default_factory=list)
    demo_flow_order: list[str] = Field(default_factory=list)
    screenshot_checklist: list[dict[str, str]] = Field(default_factory=list)
    troubleshooting: list[dict[str, str]] = Field(default_factory=list)
    recruiter_engineer_explanation: dict[str, str] = Field(default_factory=dict)
    known_limitations: list[str] = Field(default_factory=list)
    storage_runtime_pack_dir: str
    generated_at: str
    trace_id: str


class RuntimeDemoPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    readiness: RuntimeDemoReadinessResponse
    trace_id: str


class SmokeMatrixRow(BaseModel):
    endpoint_name: str
    method: str
    path: str
    category: str
    expected_status: int
    expected_result: str
    sample_command: str
    required_artifact_expectations: list[str] = Field(default_factory=list)
    auth_notes: str


class SmokeMatrixSummary(BaseModel):
    total_endpoints: int
    protected_endpoints: int
    artifact_writing_endpoints: int
    local_mock_ready: bool
    readiness_level: str
    recommended_sequence: list[str] = Field(default_factory=list)
    required_local_commands: list[str] = Field(default_factory=list)
    optional_provider_notes: str


class SmokeMatrixResponse(BaseModel):
    rows: list[SmokeMatrixRow]
    readiness_summary: SmokeMatrixSummary
    trace_id: str


class LaunchChecklistRequest(BaseModel):
    write_artifact: bool = True


class LaunchChecklistResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    checklist: dict[str, Any]
    smoke_matrix: SmokeMatrixResponse
    trace_id: str


class DashboardSmokeCheck(BaseModel):
    check_id: str
    category: str
    label: str
    status: str
    expected: str
    evidence: str
    source_path: str
    notes: list[str] = Field(default_factory=list)


class DashboardSmokeView(BaseModel):
    label: str
    status: str
    dashboard_source_present: bool
    endpoint_paths: list[str] = Field(default_factory=list)
    generated_artifact_tab: bool = False
    artifact_root: str | None = None


class DashboardSmokeEndpointReference(BaseModel):
    method: str
    path: str
    status: str
    dashboard_referenced: bool
    route_defined: bool
    purpose: str
    expected_artifacts: list[str] = Field(default_factory=list)


class DashboardSmokeResponse(BaseModel):
    title: str
    status: str
    summary: dict[str, Any]
    expected_views: list[DashboardSmokeView]
    endpoint_references: list[DashboardSmokeEndpointReference]
    generated_artifact_tabs: list[dict[str, Any]] = Field(default_factory=list)
    local_run_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    checks: list[DashboardSmokeCheck] = Field(default_factory=list)
    trace_id: str


class UIVerificationPackRequest(BaseModel):
    write_artifact: bool = True


class UIVerificationPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    dashboard_smoke: DashboardSmokeResponse
    trace_id: str


class ReleaseQualityGateResponse(BaseModel):
    title: str
    status: str
    score: int
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    verification_checklist: list[dict[str, Any]] = Field(default_factory=list)
    coverage: dict[str, Any] = Field(default_factory=dict)
    artifact_coverage: dict[str, Any] = Field(default_factory=dict)
    runtime_notes: list[str] = Field(default_factory=list)
    publish_readiness: dict[str, Any] = Field(default_factory=dict)
    trace_id: str


class CiDoctorCheck(BaseModel):
    check_id: str
    name: str
    category: str
    status: str
    command: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    missing_paths: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    remediation: list[str] = Field(default_factory=list)


class SecretScanFinding(BaseModel):
    path: str
    line: int
    pattern_id: str
    severity: str
    redacted_match: str


class SecretScanSummary(BaseModel):
    files_scanned: int
    skipped_dirs: list[str] = Field(default_factory=list)
    finding_count: int
    findings: list[SecretScanFinding] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DependencyInventory(BaseModel):
    dependency_files: list[dict[str, Any]] = Field(default_factory=list)
    runtime_dependencies: list[str] = Field(default_factory=list)
    dev_dependencies: list[str] = Field(default_factory=list)
    optional_extras: dict[str, list[str]] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class CiDoctorResponse(BaseModel):
    title: str
    status: str
    score: int
    checks: list[CiDoctorCheck]
    summary: dict[str, Any]
    dependency_inventory: DependencyInventory
    secret_scan: SecretScanSummary
    local_verification_commands: list[str] = Field(default_factory=list)
    generated_at: str
    trace_id: str


class AuditPackRequest(BaseModel):
    write_artifact: bool = True


class AuditPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    ci_doctor: CiDoctorResponse
    trace_id: str


class ApiContractEndpoint(BaseModel):
    method: str
    path: str
    domain: str
    operation_id: str | None = None
    summary: str
    expected_status: int
    auth_required: bool
    auth_notes: str
    docs_api_covered: bool
    readme_covered: bool
    dashboard_referenced: bool
    smoke_matrix_covered: bool
    generates_artifact: bool
    artifact_expectations: list[str] = Field(default_factory=list)
    sample_curl: str
    sample_powershell: str


class ApiContractCheck(BaseModel):
    name: str
    status: str
    passed: int
    total: int
    missing_paths: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class ApiContractAuditResponse(BaseModel):
    title: str
    status: str
    score: int
    openapi_route_count: int
    openapi_path_count: int
    auth_protected_endpoint_count: int
    public_endpoint_count: int
    important_endpoint_count: int
    endpoint_inventory: dict[str, list[ApiContractEndpoint]]
    docs_api_coverage: ApiContractCheck
    dashboard_smoke_alignment: ApiContractCheck
    generated_artifact_endpoint_coverage: ApiContractCheck
    demo_flow_endpoint_coverage: ApiContractCheck
    rag_eval_red_team_endpoint_coverage: ApiContractCheck
    missing_docs_warnings: list[str] = Field(default_factory=list)
    deprecated_duplicate_route_warnings: list[str] = Field(default_factory=list)
    local_only_limitations: list[str] = Field(default_factory=list)
    generated_at: str
    trace_id: str


class ReviewerCollectionRequest(BaseModel):
    write_artifact: bool = True


class ReviewerCollectionResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    collection: dict[str, Any]
    contract_audit: ApiContractAuditResponse
    trace_id: str


class PublishPackRequest(BaseModel):
    write_artifact: bool = True


class PublishPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    quality_gate: ReleaseQualityGateResponse
    trace_id: str


class GitPushPlanRequest(BaseModel):
    write_artifact: bool = True


class GitReadinessResponse(BaseModel):
    title: str
    status: str
    git_repo_detected: bool
    repo_root: str | None = None
    current_branch: str | None = None
    working_tree_summary: dict[str, Any]
    generated_artifact_directories: list[dict[str, Any]] = Field(default_factory=list)
    changed_file_groups: dict[str, list[str]] = Field(default_factory=dict)
    suspicious_large_generated_files: list[dict[str, Any]] = Field(default_factory=list)
    github_actions: dict[str, Any]
    readme_final_handoff: dict[str, Any]
    env_example_present: bool
    dirty_worktree_guidance: list[str] = Field(default_factory=list)
    recommended_commit_groups: list[dict[str, Any]] = Field(default_factory=list)
    local_review_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    trace_id: str


class GitPushPlanResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    readiness: GitReadinessResponse
    trace_id: str


class PortfolioEvidenceSkill(BaseModel):
    skill_id: str
    jd_skill: str
    coverage_status: str
    implemented_features: list[str] = Field(default_factory=list)
    endpoints: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    tests_evals: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    demo_commands: list[str] = Field(default_factory=list)
    local_proof_paths: list[str] = Field(default_factory=list)
    interview_notes: list[str] = Field(default_factory=list)


class PortfolioEvidenceIndexResponse(BaseModel):
    title: str
    evidence_score: int
    covered_skill_count: int
    total_skill_count: int
    skills: list[PortfolioEvidenceSkill]
    required_capabilities: list[str] = Field(default_factory=list)
    proof_commands: list[str] = Field(default_factory=list)
    artifact_roots: dict[str, str] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    trace_id: str


class PortfolioInterviewPackRequest(BaseModel):
    run_regression: bool = True
    regression_request: SubmissionRegressionRequest = Field(default_factory=SubmissionRegressionRequest)
    write_artifact: bool = True


class PortfolioInterviewPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    evidence_index: PortfolioEvidenceIndexResponse
    trace_id: str


class ReviewerQuickstartResponse(BaseModel):
    title: str
    status: str
    provider_mode: str
    vector_store_mode: str
    local_mock_default: bool
    exact_local_setup_commands: list[str] = Field(default_factory=list)
    one_command_demo: str
    verification_commands: list[str] = Field(default_factory=list)
    endpoint_walkthrough_order: list[dict[str, Any]] = Field(default_factory=list)
    rag_rfp_workflow_walkthrough: list[dict[str, Any]] = Field(default_factory=list)
    artifact_proof_map: dict[str, Any] = Field(default_factory=dict)
    expected_outputs: dict[str, Any] = Field(default_factory=dict)
    troubleshooting: list[dict[str, str]] = Field(default_factory=list)
    role_specific_reviewer_notes: dict[str, list[str]] = Field(default_factory=dict)
    proof_tour: list[str] = Field(default_factory=list)
    github_readme_blurb: str
    trace_id: str


class ReviewerWalkthroughPackRequest(BaseModel):
    write_artifact: bool = True


class ReviewerWalkthroughPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    quickstart: ReviewerQuickstartResponse
    trace_id: str


class ArtifactFileSummary(BaseModel):
    path: str
    name: str
    extension: str
    size_bytes: int
    last_modified: str


class ArtifactInventoryItem(BaseModel):
    key: str
    directory: str
    exists: bool
    ignored_status: str
    producer_endpoint: str
    producer_command: str
    reviewer_purpose: str
    freshness_notes: list[str] = Field(default_factory=list)
    file_count: int
    latest_files: list[ArtifactFileSummary] = Field(default_factory=list)


class ArtifactInventoryResponse(BaseModel):
    title: str
    storage_root: str
    ignored_status: str
    generated_at: str
    total_directories: int
    total_files: int
    latest_artifact_count: int
    directories: list[ArtifactInventoryItem]
    local_commands: list[str] = Field(default_factory=list)
    reviewer_proof_checklist: list[str] = Field(default_factory=list)
    trace_id: str


class ReadmeChecklistRequest(BaseModel):
    write_artifact: bool = True


class ReadmeChecklistResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    checklist: dict[str, Any]
    inventory: ArtifactInventoryResponse
    trace_id: str


class FinalAuditCheck(BaseModel):
    check_id: str
    name: str
    category: str
    status: str
    evidence_paths: list[str] = Field(default_factory=list)
    missing_paths: list[str] = Field(default_factory=list)
    required_terms: list[str] = Field(default_factory=list)
    missing_terms: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    remediation: list[str] = Field(default_factory=list)


class FinalAuditResponse(BaseModel):
    title: str
    status: str
    score: int
    checks: list[FinalAuditCheck]
    summary: dict[str, Any]
    endpoint_inventory: dict[str, Any]
    artifact_inventory: dict[str, Any]
    local_verification_commands: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_at: str
    trace_id: str


class FinalPackRequest(BaseModel):
    write_artifact: bool = True


class FinalPackResponse(BaseModel):
    artifact_path: str | None = None
    json_artifact_path: str | None = None
    markdown: str
    pack: dict[str, Any]
    final_audit: FinalAuditResponse
    trace_id: str
