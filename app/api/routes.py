from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app import __version__
from app.core.config import Settings, get_settings
from app.core.security import require_api_key
from app.core.telemetry import get_trace_id
from app.models.api import (
    AccessPolicyPackRequest,
    AccessPolicyPackResponse,
    AccessPolicyResponse,
    ActionPlanRequest,
    ActionPlanResponse,
    AnalyzeRequest,
    AnalyzeResponse,
    AnswerReuseApprovalLedgerPackRequest,
    AnswerReuseApprovalLedgerPackResponse,
    AnswerReuseApprovalLedgerRequest,
    AnswerReuseApprovalLedgerResponse,
    AnswerReuseCoveragePackRequest,
    AnswerReuseCoveragePackResponse,
    AnswerReuseCoverageRequest,
    AnswerReuseCoverageResponse,
    AnswerReuseDriftPackRequest,
    AnswerReuseDriftPackResponse,
    AnswerReuseDriftRequest,
    AnswerReuseDriftResponse,
    AnswerReuseLibraryPackRequest,
    AnswerReuseLibraryPackResponse,
    AnswerReuseLibraryRequest,
    AnswerReuseLibraryResponse,
    ApiContractAuditResponse,
    ArtifactInventoryResponse,
    AuditPackRequest,
    AuditPackResponse,
    AuditResponse,
    BidRoiPackRequest,
    BidRoiPackResponse,
    BidScenarioAnalysisResponse,
    BuyerIntelligencePackRequest,
    BuyerIntelligencePackResponse,
    BuyerIntelligenceWorkflowResponse,
    BuyerStructuredContractPackRequest,
    BuyerStructuredContractPackResponse,
    BuyerStructuredContractResponse,
    BuyerWorkflowReplayPackRequest,
    BuyerWorkflowReplayPackResponse,
    BuyerWorkflowReplayResponse,
    CiDoctorResponse,
    CitationLineageAuditResponse,
    CitationLineagePackRequest,
    CitationLineagePackResponse,
    ClarificationQuestionPackRequest,
    ClarificationQuestionPackResponse,
    ClarificationQuestionRequest,
    ClarificationQuestionResponse,
    ComplianceEvidenceMatrixResponse,
    ContractRiskRequest,
    ContractRiskResponse,
    ControlPackRequest,
    ControlPackResponse,
    CostGovernancePackRequest,
    CostGovernancePackResponse,
    CostGovernanceRequest,
    CostGovernanceResponse,
    CustomerFitRequest,
    CustomerFitResponse,
    CustomerProfilesResponse,
    DashboardSmokeResponse,
    DealReadinessScorecardRequest,
    DealReadinessScorecardResponse,
    DemoScriptRequest,
    DemoScriptResponse,
    DemoTokenResponse,
    DraftRequest,
    EvaluateRequest,
    EvaluationMetrics,
    EvidenceConflictPackRequest,
    EvidenceConflictPackResponse,
    EvidenceConflictResponse,
    EvidenceFreshnessPackRequest,
    EvidenceFreshnessPackResponse,
    EvidenceFreshnessResponse,
    EvidenceFreshnessSlaPackRequest,
    EvidenceFreshnessSlaPackResponse,
    EvidenceFreshnessSlaResponse,
    EvidenceGapRequest,
    EvidenceGapResponse,
    ExecutiveRiskReportRequest,
    ExecutiveRiskReportResponse,
    ExecutiveSubmissionMemoRequest,
    ExecutiveSubmissionMemoResponse,
    ExportPackageRequest,
    ExportPackageResponse,
    FinalAuditResponse,
    FinalPackRequest,
    FinalPackResponse,
    GitPushPlanRequest,
    GitPushPlanResponse,
    GitReadinessResponse,
    GovernedRetrievalPackRequest,
    GovernedRetrievalPackResponse,
    GovernedRetrievalRequest,
    GovernedRetrievalResponse,
    HandoffBoardRequest,
    HandoffBoardResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    LaunchChecklistRequest,
    LaunchChecklistResponse,
    LeadershipBriefRequest,
    LeadershipBriefResponse,
    ModelRiskPackRequest,
    ModelRiskPackResponse,
    ModelRiskRegisterResponse,
    NegotiationBriefRequest,
    NegotiationBriefResponse,
    ObjectionAuditPackRequest,
    ObjectionAuditPackResponse,
    ObjectionAuditRequest,
    ObjectionAuditResponse,
    ObjectionHandlingPackRequest,
    ObjectionHandlingPackResponse,
    ObjectionHandlingRequest,
    ObjectionHandlingResponse,
    PortfolioEvidenceIndexResponse,
    PortfolioInterviewPackRequest,
    PortfolioInterviewPackResponse,
    PricingRiskMemoRequest,
    PricingRiskMemoResponse,
    PrivacyRetentionGuardrailResponse,
    PrivacyRetentionPackRequest,
    PrivacyRetentionPackResponse,
    ProcurementApprovalPackRequest,
    ProcurementApprovalPackResponse,
    ProcurementQuestionRiskResponse,
    ProcurementRiskDecisionLedgerResponse,
    ProcurementRiskDecisionPackRequest,
    ProcurementRiskDecisionPackResponse,
    ProcurementRiskDeskPackRequest,
    ProcurementRiskDeskPackResponse,
    ProcurementRiskDeskResponse,
    ProposalAgentCouncilPackRequest,
    ProposalAgentCouncilPackResponse,
    ProposalAgentCouncilResponse,
    ProposalApprovalSimulationPackRequest,
    ProposalApprovalSimulationPackResponse,
    ProposalApprovalSimulationRequest,
    ProposalApprovalSimulationResponse,
    ProposalAssuranceBundlePackRequest,
    ProposalAssuranceBundlePackResponse,
    ProposalAssuranceBundleResponse,
    ProposalDecisionProvenancePackRequest,
    ProposalDecisionProvenancePackResponse,
    ProposalDecisionProvenanceResponse,
    ProposalIntakeTriagePackRequest,
    ProposalIntakeTriagePackResponse,
    ProposalIntakeTriageResponse,
    ProposalObservabilityPackRequest,
    ProposalObservabilityPackResponse,
    ProposalObservabilityResponse,
    ProposalQualityBenchmarkPackRequest,
    ProposalQualityBenchmarkPackResponse,
    ProposalQualityBenchmarkResponse,
    ProposalReadinessScorePackRequest,
    ProposalReadinessScorePackResponse,
    ProposalReleaseRoomPackRequest,
    ProposalReleaseRoomPackResponse,
    ProposalReleaseRoomResponse,
    ProposalReviewGatePackRequest,
    ProposalReviewGatePackResponse,
    ProposalReviewGateResponse,
    ProposalSubmissionCertificationPackRequest,
    ProposalSubmissionCertificationPackResponse,
    ProposalSubmissionCertificationResponse,
    ProviderResiliencePackRequest,
    ProviderResiliencePackResponse,
    ProviderResilienceResponse,
    PublishPackRequest,
    PublishPackResponse,
    QueryRequest,
    RagCorpusCoverageResponse,
    RagEvalCoveragePackRequest,
    RagEvalCoveragePackResponse,
    ReadinessScoreEvalRequest,
    ReadinessScoreEvalResponse,
    ReadmeChecklistRequest,
    ReadmeChecklistResponse,
    ReleaseQualityGateResponse,
    RequirementMatrixRequest,
    RequirementMatrixResponse,
    ResponseMemorySearchRequest,
    ResponseMemorySearchResponse,
    RetrievalExperimentPackRequest,
    RetrievalExperimentPackResponse,
    RetrievalExperimentRequest,
    RetrievalExperimentResponse,
    ReviewAnswerRequest,
    ReviewAnswerResponse,
    ReviewerCollaborationPackRequest,
    ReviewerCollaborationPackResponse,
    ReviewerCollaborationRequest,
    ReviewerCollaborationResponse,
    ReviewerCollaborationWorkflowPackRequest,
    ReviewerCollaborationWorkflowPackResponse,
    ReviewerCollaborationWorkflowRequest,
    ReviewerCollaborationWorkflowResponse,
    ReviewerCollectionRequest,
    ReviewerCollectionResponse,
    ReviewerEscalationPackRequest,
    ReviewerEscalationPackResponse,
    ReviewerEscalationRequest,
    ReviewerEscalationResponse,
    ReviewerQuickstartResponse,
    ReviewerSignoffLedgerPackRequest,
    ReviewerSignoffLedgerPackResponse,
    ReviewerSignoffLedgerRequest,
    ReviewerSignoffLedgerResponse,
    ReviewerTraceReconciliationPackRequest,
    ReviewerTraceReconciliationPackResponse,
    ReviewerTraceReconciliationRequest,
    ReviewerTraceReconciliationResponse,
    ReviewerWalkthroughPackRequest,
    ReviewerWalkthroughPackResponse,
    ReviewPackageRequest,
    ReviewPackageResponse,
    RfpAmendmentImpactPackRequest,
    RfpAmendmentImpactPackResponse,
    RfpAmendmentImpactRequest,
    RfpAmendmentImpactResponse,
    RuntimeDemoPackRequest,
    RuntimeDemoPackResponse,
    RuntimeDemoReadinessResponse,
    SmokeMatrixResponse,
    SourceRequestPackRequest,
    SourceRequestPackResponse,
    SourceTrustGateResponse,
    SourceTrustPackRequest,
    SourceTrustPackResponse,
    SubmissionCalendarPackRequest,
    SubmissionCalendarPackResponse,
    SubmissionDecisionRequest,
    SubmissionDecisionResponse,
    SubmissionExceptionPackRequest,
    SubmissionExceptionPackResponse,
    SubmissionExceptionRegisterRequest,
    SubmissionExceptionRegisterResponse,
    SubmissionRegressionRequest,
    SubmissionRegressionResponse,
    TimelinePlanRequest,
    TimelinePlanResponse,
    TraceExportPackRequest,
    TraceExportPackResponse,
    TraceExportRequest,
    TraceExportResponse,
    UIVerificationPackRequest,
    UIVerificationPackResponse,
    UsageResponse,
    VerificationEvidencePackRequest,
    VerificationEvidencePackResponse,
    VerificationEvidenceRequest,
    VerificationEvidenceResponse,
    WinLossEvalCasePackRequest,
    WinLossEvalCasePackResponse,
    WinLossEvalCaseRequest,
    WinLossEvalCaseResponse,
    WinLossLearningRequest,
    WinLossLearningResponse,
    WinLossPolicyActivationRequest,
    WinLossPolicyActivationResponse,
    WinLossPolicyPackRequest,
    WinLossPolicyPackResponse,
    WinLossReplayPackRequest,
    WinLossReplayPackResponse,
    WinLossReplayRequest,
    WinLossReplayResponse,
    WinLossStrategyPackRequest,
    WinLossStrategyPackResponse,
    WinStrategyRequest,
    WinStrategyResponse,
)
from app.models.domain import (
    Answer,
    CustomerProfile,
    Document,
    DraftResponse,
    RequirementMatrixRow,
    ResponseMemoryMatch,
)
from app.services.container import ServiceContainer, get_container

router = APIRouter()


@router.post("/auth/demo-token", response_model=DemoTokenResponse)
async def demo_token(settings: Settings = Depends(get_settings)) -> DemoTokenResponse:
    return DemoTokenResponse(api_key=settings.api_key)


@router.get("/health", response_model=HealthResponse)
async def health(
    settings: Settings = Depends(get_settings),
    container: ServiceContainer = Depends(get_container),
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        provider_mode=settings.provider_mode,
        vector_store_mode=container.vector_store.mode,
        version=__version__,
    )


@router.post("/documents/ingest", response_model=IngestResponse, dependencies=[Depends(require_api_key)])
async def ingest_document(
    request: Request,
    payload: IngestRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> IngestResponse:
    if payload is None or not payload.fixture_path:
        raise HTTPException(status_code=400, detail="Provide fixture_path or use /documents/ingest-upload.")
    trace_id = get_trace_id(request)
    document, chunks = await container.ingestion.ingest_path(
        payload.fixture_path,
        payload.document_type,
        payload.source,
        payload.tags,
    )
    container.audit.record(trace_id, "document.ingested", "document", document.id)
    return IngestResponse(document=document, chunk_count=len(chunks))


@router.post(
    "/documents/ingest-upload",
    response_model=IngestResponse,
    dependencies=[Depends(require_api_key)],
)
async def ingest_upload(
    request: Request,
    file: UploadFile = File(...),
    document_type: str = Form("unknown"),
    source: str = Form("upload"),
    tags: str = Form(""),
    container: ServiceContainer = Depends(get_container),
) -> IngestResponse:
    trace_id = get_trace_id(request)
    tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
    document, chunks = await container.ingestion.ingest_upload(file, document_type, source, tag_list)
    container.audit.record(trace_id, "document.ingested", "document", document.id)
    return IngestResponse(document=document, chunk_count=len(chunks))


@router.get("/documents", response_model=list[Document], dependencies=[Depends(require_api_key)])
async def list_documents(container: ServiceContainer = Depends(get_container)) -> list[Document]:
    return container.ingestion.list_documents()


@router.post("/rfp/analyze", response_model=AnalyzeResponse, dependencies=[Depends(require_api_key)])
async def analyze_rfp(
    payload: AnalyzeRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> AnalyzeResponse:
    trace_id = get_trace_id(request)
    if payload.text:
        text = payload.text
    elif payload.rfp_document_id:
        text = container.ingestion.get_text(payload.rfp_document_id)
    elif payload.fixture_path:
        path = Path(payload.fixture_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            sample_path = container.settings.sample_data_dir / payload.fixture_path
            if sample_path.exists():
                path = sample_path
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"RFP fixture not found: {payload.fixture_path}")
        text = path.read_text(encoding="utf-8")
    else:
        raise HTTPException(status_code=400, detail="Provide text, rfp_document_id, or fixture_path.")
    result = container.analysis.analyze(text, trace_id)
    container.audit.record(trace_id, "rfp.analyzed", "rfp", metadata={"requirements": len(result.requirements)})
    return result


@router.post("/rfp/query", response_model=Answer, dependencies=[Depends(require_api_key)])
async def query_rfp(
    payload: QueryRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> Answer:
    trace_id = get_trace_id(request)
    answer = await container.generation.answer_question(payload.question, trace_id, payload.top_k)
    container.audit.record(
        trace_id,
        "rfp.question_answered",
        "answer",
        metadata={"confidence": answer.confidence, "citations": len(answer.citations)},
    )
    return answer


@router.post(
    "/rfp/draft-response",
    response_model=DraftResponse,
    dependencies=[Depends(require_api_key)],
)
async def draft_response(
    payload: DraftRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> DraftResponse:
    trace_id = get_trace_id(request)
    draft = await container.generation.draft_response(
        trace_id,
        payload.requirement_ids,
        payload.section_names,
        payload.top_k,
    )
    container.audit.record(
        trace_id,
        "rfp.draft_generated",
        "draft",
        metadata={"sections": len(draft.sections), "citations": len(draft.citations)},
    )
    return draft


@router.post(
    "/rfp/requirement-matrix",
    response_model=RequirementMatrixResponse,
    dependencies=[Depends(require_api_key)],
)
async def requirement_matrix(
    payload: RequirementMatrixRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> RequirementMatrixResponse:
    trace_id = get_trace_id(request)
    analysis = _analysis_from_workbench_payload(payload, trace_id, container)
    matrix = container.workbench.create_requirement_matrix(analysis)
    container.audit.record(
        trace_id,
        "rfp.requirement_matrix_created",
        "requirement_matrix",
        metadata={"rows": len(matrix)},
    )
    return RequirementMatrixResponse(matrix=matrix, trace_id=trace_id)


@router.get("/customers/profiles", response_model=CustomerProfilesResponse, dependencies=[Depends(require_api_key)])
async def customer_profiles(container: ServiceContainer = Depends(get_container)) -> CustomerProfilesResponse:
    return CustomerProfilesResponse(profiles=container.customer_intelligence.list_profiles())


@router.post(
    "/rfp/customer-fit",
    response_model=CustomerFitResponse,
    dependencies=[Depends(require_api_key)],
)
async def customer_fit(
    payload: CustomerFitRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> CustomerFitResponse:
    trace_id = get_trace_id(request)
    analysis = None
    if payload.analyzed_payload is not None or payload.rfp_document_id is not None:
        analysis = _analysis_from_workbench_payload(payload, trace_id, container)
    if analysis is None and not payload.requirement_matrix:
        raise HTTPException(status_code=400, detail="Provide analyzed_payload, rfp_document_id, or requirement_matrix.")
    try:
        fit = container.customer_intelligence.customer_fit(
            payload.customer_profile_id,
            trace_id,
            analysis=analysis,
            requirement_matrix=payload.requirement_matrix,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    container.audit.record(
        trace_id,
        "rfp.customer_fit_created",
        "customer_fit",
        resource_id=payload.customer_profile_id,
        metadata={"fit_score": fit.fit_score, "review_count": len(fit.requirements_needing_review)},
    )
    return fit


@router.post(
    "/rfp/response-memory/search",
    response_model=ResponseMemorySearchResponse,
    dependencies=[Depends(require_api_key)],
)
async def response_memory_search(
    payload: ResponseMemorySearchRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ResponseMemorySearchResponse:
    trace_id = get_trace_id(request)
    try:
        matches = container.customer_intelligence.search_response_memory(
            payload.query,
            trace_id,
            category=payload.category,
            customer_profile_id=payload.customer_profile_id,
            top_k=payload.top_k,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    container.audit.record(
        trace_id,
        "rfp.response_memory_searched",
        "response_memory",
        resource_id=payload.customer_profile_id,
        metadata={"matches": len(matches), "category": payload.category},
    )
    return ResponseMemorySearchResponse(matches=matches, trace_id=trace_id)


@router.post(
    "/rfp/answer-reuse-library",
    response_model=AnswerReuseLibraryResponse,
    dependencies=[Depends(require_api_key)],
)
async def answer_reuse_library(
    payload: AnswerReuseLibraryRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> AnswerReuseLibraryResponse:
    trace_id = get_trace_id(request)
    try:
        library = container.answer_reuse_library.library(
            trace_id,
            category=payload.category,
            customer_profile_id=payload.customer_profile_id,
            include_expired=payload.include_expired,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    container.audit.record(
        trace_id,
        "rfp.answer_reuse_library_viewed",
        "answer_reuse_library",
        resource_id=payload.customer_profile_id,
        metadata={
            "snippets": library.summary["snippet_count"],
            "approved": library.summary["approved_count"],
            "review_required": library.summary["review_required_count"],
        },
    )
    return library


@router.post(
    "/rfp/answer-reuse-library-pack",
    response_model=AnswerReuseLibraryPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def answer_reuse_library_pack(
    payload: AnswerReuseLibraryPackRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> AnswerReuseLibraryPackResponse:
    trace_id = get_trace_id(request)
    pack = container.answer_reuse_library.pack(
        trace_id,
        library=payload.library,
        category=payload.category,
        customer_profile_id=payload.customer_profile_id,
        include_expired=payload.include_expired,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.answer_reuse_library_pack_created",
        "answer_reuse_library_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "snippets": pack.library.summary["snippet_count"],
            "approved": pack.library.summary["approved_count"],
        },
    )
    return pack


@router.post(
    "/rfp/answer-reuse-drift",
    response_model=AnswerReuseDriftResponse,
    dependencies=[Depends(require_api_key)],
)
async def answer_reuse_drift(
    payload: AnswerReuseDriftRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> AnswerReuseDriftResponse:
    trace_id = get_trace_id(request)
    drift_report = container.answer_reuse_drift.drift_report(
        trace_id,
        category=payload.category,
        customer_profile_id=payload.customer_profile_id,
        include_expired=payload.include_expired,
        min_source_overlap=payload.min_source_overlap,
    )
    container.audit.record(
        trace_id,
        "rfp.answer_reuse_drift_viewed",
        "answer_reuse_drift",
        resource_id=payload.customer_profile_id,
        metadata={
            "snippets": drift_report.summary["snippet_count"],
            "owner_review": drift_report.summary["owner_review_count"],
            "rewrite": drift_report.summary["rewrite_count"],
        },
    )
    return drift_report


@router.post(
    "/rfp/answer-reuse-drift-pack",
    response_model=AnswerReuseDriftPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def answer_reuse_drift_pack(
    payload: AnswerReuseDriftPackRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> AnswerReuseDriftPackResponse:
    trace_id = get_trace_id(request)
    pack = container.answer_reuse_drift.pack(
        trace_id,
        drift_report=payload.drift_report,
        category=payload.category,
        customer_profile_id=payload.customer_profile_id,
        include_expired=payload.include_expired,
        min_source_overlap=payload.min_source_overlap,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.answer_reuse_drift_pack_created",
        "answer_reuse_drift_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "snippets": pack.drift_report.summary["snippet_count"],
            "owner_review": pack.drift_report.summary["owner_review_count"],
            "rewrite": pack.drift_report.summary["rewrite_count"],
        },
    )
    return pack


@router.post(
    "/rfp/answer-reuse-approval-ledger",
    response_model=AnswerReuseApprovalLedgerResponse,
    dependencies=[Depends(require_api_key)],
)
async def answer_reuse_approval_ledger(
    payload: AnswerReuseApprovalLedgerRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> AnswerReuseApprovalLedgerResponse:
    trace_id = get_trace_id(request)
    ledger = container.answer_reuse_approval.ledger(
        trace_id,
        category=payload.category,
        customer_profile_id=payload.customer_profile_id,
        include_expired=payload.include_expired,
        min_source_overlap=payload.min_source_overlap,
        requested_by=payload.requested_by,
        approver_overrides=payload.approver_overrides,
    )
    container.audit.record(
        trace_id,
        "rfp.answer_reuse_approval_ledger_viewed",
        "answer_reuse_approval_ledger",
        resource_id=payload.customer_profile_id,
        metadata={
            "records": ledger.summary["record_count"],
            "approved": ledger.summary["approved_count"],
            "pending": ledger.summary["pending_count"],
            "blocked": ledger.summary["blocked_count"],
        },
    )
    return ledger


@router.post(
    "/rfp/answer-reuse-approval-pack",
    response_model=AnswerReuseApprovalLedgerPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def answer_reuse_approval_pack(
    payload: AnswerReuseApprovalLedgerPackRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> AnswerReuseApprovalLedgerPackResponse:
    trace_id = get_trace_id(request)
    pack = container.answer_reuse_approval.pack(
        trace_id,
        ledger=payload.ledger,
        category=payload.category,
        customer_profile_id=payload.customer_profile_id,
        include_expired=payload.include_expired,
        min_source_overlap=payload.min_source_overlap,
        requested_by=payload.requested_by,
        approver_overrides=payload.approver_overrides,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.answer_reuse_approval_pack_created",
        "answer_reuse_approval_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "records": pack.ledger.summary["record_count"],
            "pending": pack.ledger.summary["pending_count"],
            "blocked": pack.ledger.summary["blocked_count"],
        },
    )
    return pack


@router.post(
    "/rfp/answer-reuse-coverage",
    response_model=AnswerReuseCoverageResponse,
    dependencies=[Depends(require_api_key)],
)
async def answer_reuse_coverage(
    payload: AnswerReuseCoverageRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> AnswerReuseCoverageResponse:
    trace_id = get_trace_id(request)
    analysis = _analysis_from_workbench_payload(payload, trace_id, container)
    coverage = container.answer_reuse_coverage.coverage(
        trace_id,
        analysis,
        category=payload.category,
        customer_profile_id=payload.customer_profile_id,
        include_expired=payload.include_expired,
        min_match_score=payload.min_match_score,
        top_snippets_per_requirement=payload.top_snippets_per_requirement,
    )
    container.audit.record(
        trace_id,
        "rfp.answer_reuse_coverage_viewed",
        "answer_reuse_coverage",
        resource_id=payload.customer_profile_id,
        metadata={
            "requirements": coverage.summary["requirement_count"],
            "reuse_ready": coverage.summary["reuse_ready_count"],
            "gaps": coverage.summary["gap_count"],
        },
    )
    return coverage


@router.post(
    "/rfp/answer-reuse-coverage-pack",
    response_model=AnswerReuseCoveragePackResponse,
    dependencies=[Depends(require_api_key)],
)
async def answer_reuse_coverage_pack(
    payload: AnswerReuseCoveragePackRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> AnswerReuseCoveragePackResponse:
    trace_id = get_trace_id(request)
    analysis = None
    if payload.coverage is None:
        analysis = _analysis_from_workbench_payload(payload, trace_id, container)
    try:
        pack = container.answer_reuse_coverage.pack(
            trace_id,
            coverage=payload.coverage,
            analysis=analysis,
            category=payload.category,
            customer_profile_id=payload.customer_profile_id,
            include_expired=payload.include_expired,
            min_match_score=payload.min_match_score,
            top_snippets_per_requirement=payload.top_snippets_per_requirement,
            write_artifact=payload.write_artifact,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    container.audit.record(
        trace_id,
        "rfp.answer_reuse_coverage_pack_created",
        "answer_reuse_coverage_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "requirements": pack.coverage.summary["requirement_count"],
            "reuse_ready": pack.coverage.summary["reuse_ready_count"],
        },
    )
    return pack


@router.post(
    "/rfp/export-package",
    response_model=ExportPackageResponse,
    dependencies=[Depends(require_api_key)],
)
async def export_package(
    payload: ExportPackageRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ExportPackageResponse:
    trace_id = get_trace_id(request)
    analysis = _analysis_from_workbench_payload(payload, trace_id, container)
    draft = payload.draft_response
    if draft is None:
        draft = await container.generation.draft_response(
            trace_id=f"{trace_id}-draft",
            requirement_ids=[requirement.id for requirement in analysis.requirements],
            top_k=5,
        )
    customer_fit_result = None
    memory_matches = []
    if payload.customer_profile_id:
        try:
            customer_fit_result = container.customer_intelligence.customer_fit(
                payload.customer_profile_id,
                trace_id,
                analysis=analysis,
            )
            if payload.include_response_memory:
                memory_query = " ".join(requirement.text for requirement in analysis.requirements)
                memory_matches = container.customer_intelligence.search_response_memory(
                    memory_query,
                    trace_id,
                    customer_profile_id=payload.customer_profile_id,
                    top_k=5,
                )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    export = container.workbench.export_package(
        analysis,
        draft,
        trace_id=trace_id,
        write_artifact=payload.write_artifact,
        customer_fit=customer_fit_result,
        response_memory_matches=memory_matches,
    )
    container.audit.record(
        trace_id,
        "rfp.export_package_created",
        "export_package",
        resource_id=export.artifact_path,
        metadata={
            "artifact_path": export.artifact_path,
            "requirements": len(export.package["requirement_matrix"]),
        },
    )
    return export


@router.post(
    "/rfp/review-answer",
    response_model=ReviewAnswerResponse,
    dependencies=[Depends(require_api_key)],
)
async def review_answer(
    payload: ReviewAnswerRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ReviewAnswerResponse:
    trace_id = get_trace_id(request)
    report = container.review_board.review_answer(
        payload.question,
        payload.answer_text,
        payload.citations,
        payload.missing_evidence,
        payload.token_usage,
        trace_id,
    )
    container.audit.record(
        trace_id,
        "rfp.answer_reviewed",
        "review_report",
        metadata={"passed": report.passed, "findings": len(report.findings)},
    )
    return ReviewAnswerResponse(**report.model_dump())


@router.post(
    "/rfp/review-package",
    response_model=ReviewPackageResponse,
    dependencies=[Depends(require_api_key)],
)
async def review_package(
    payload: ReviewPackageRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ReviewPackageResponse:
    trace_id = get_trace_id(request)
    has_review_input = any(
        [
            payload.rfp_document_id,
            payload.analyzed_payload,
            payload.requirement_matrix,
            payload.draft_response,
            payload.answer_payloads,
            payload.export_payload,
        ]
    )
    if not has_review_input:
        raise HTTPException(status_code=400, detail="Provide analysis, matrix, draft, answer, export, or RFP document.")

    analysis = None
    matrix = payload.requirement_matrix
    draft = payload.draft_response
    export_payload = payload.export_payload
    if payload.analyzed_payload is not None or payload.rfp_document_id is not None:
        analysis = _analysis_from_workbench_payload(payload, trace_id, container)
        if matrix is None:
            matrix = container.workbench.create_requirement_matrix(analysis)
        if draft is None:
            draft = await container.generation.draft_response(
                trace_id=f"{trace_id}-draft",
                requirement_ids=[requirement.id for requirement in analysis.requirements],
                top_k=5,
            )
        if export_payload is None:
            export = container.workbench.export_package(
                analysis,
                draft,
                trace_id=trace_id,
                write_artifact=payload.write_artifact,
            )
            export_payload = export.package
            artifact_path = export.artifact_path
        else:
            artifact_path = None
    else:
        artifact_path = None

    if matrix is None and export_payload is not None:
        matrix = container.review_board.matrix_from_export(export_payload)

    report = container.review_board.review_package(
        trace_id=trace_id,
        requirement_matrix=matrix,
        draft_response=draft,
        answer_payloads=payload.answer_payloads,
        export_payload=export_payload,
    )
    container.audit.record(
        trace_id,
        "rfp.package_reviewed",
        "review_report",
        resource_id=artifact_path,
        metadata={"passed": report.passed, "findings": len(report.findings)},
    )
    return ReviewPackageResponse(
        **report.model_dump(),
        requirement_matrix=matrix or [],
        export_package=export_payload,
        artifact_path=artifact_path,
    )


@router.post(
    "/rfp/reviewer-collaboration",
    response_model=ReviewerCollaborationResponse,
    dependencies=[Depends(require_api_key)],
)
async def reviewer_collaboration(
    payload: ReviewerCollaborationRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ReviewerCollaborationResponse:
    trace_id = get_trace_id(request)
    inputs = _reviewer_collaboration_inputs(payload, trace_id, container)
    board = container.reviewer_collaboration.create_board(trace_id=trace_id, **inputs)
    container.audit.record(
        trace_id,
        "rfp.reviewer_collaboration_created",
        "reviewer_collaboration",
        metadata={
            "assignments": len(board.assignments),
            "comments": len(board.decision_comments),
            "board_status": board.board_status,
        },
    )
    return board


@router.post(
    "/rfp/reviewer-collaboration-pack",
    response_model=ReviewerCollaborationPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def reviewer_collaboration_pack(
    payload: ReviewerCollaborationPackRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ReviewerCollaborationPackResponse:
    trace_id = get_trace_id(request)
    collaboration = payload.collaboration
    if collaboration is None:
        inputs = _reviewer_collaboration_inputs(payload, trace_id, container)
        collaboration = container.reviewer_collaboration.create_board(
            trace_id=f"{trace_id}-collaboration",
            **inputs,
        )
    pack = container.reviewer_collaboration.collaboration_pack(
        trace_id=trace_id,
        collaboration=collaboration,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.reviewer_collaboration_pack_created",
        "reviewer_collaboration_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "assignments": len(pack.collaboration.assignments),
            "comments": len(pack.collaboration.decision_comments),
        },
    )
    return pack


@router.post(
    "/rfp/reviewer-workflow",
    response_model=ReviewerCollaborationWorkflowResponse,
    dependencies=[Depends(require_api_key)],
)
async def reviewer_workflow(
    payload: ReviewerCollaborationWorkflowRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ReviewerCollaborationWorkflowResponse:
    trace_id = get_trace_id(request)
    collaboration = payload.collaboration
    if collaboration is None:
        inputs = _reviewer_collaboration_inputs(payload, trace_id, container)
        collaboration = container.reviewer_collaboration.create_board(
            trace_id=f"{trace_id}-collaboration",
            **inputs,
        )
    workflow = container.reviewer_workflow.build_workflow(
        trace_id=trace_id,
        collaboration=collaboration,
    )
    container.audit.record(
        trace_id,
        "rfp.reviewer_workflow_created",
        "reviewer_workflow",
        metadata={
            "workflow_status": workflow.workflow_status,
            "current_state": workflow.current_state,
            "checkpoints": len(workflow.checkpoints),
            "transitions": len(workflow.transitions),
        },
    )
    return workflow


@router.post(
    "/rfp/reviewer-workflow-pack",
    response_model=ReviewerCollaborationWorkflowPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def reviewer_workflow_pack(
    payload: ReviewerCollaborationWorkflowPackRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ReviewerCollaborationWorkflowPackResponse:
    trace_id = get_trace_id(request)
    collaboration = payload.collaboration
    if collaboration is None:
        inputs = _reviewer_collaboration_inputs(payload, trace_id, container)
        collaboration = container.reviewer_collaboration.create_board(
            trace_id=f"{trace_id}-collaboration",
            **inputs,
        )
    workflow = payload.workflow or container.reviewer_workflow.build_workflow(
        trace_id=f"{trace_id}-workflow",
        collaboration=collaboration,
    )
    pack = container.reviewer_workflow.workflow_pack(
        trace_id=trace_id,
        collaboration=collaboration,
        workflow=workflow,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.reviewer_workflow_pack_created",
        "reviewer_workflow_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "workflow_status": pack.workflow.workflow_status,
            "checkpoints": len(pack.workflow.checkpoints),
        },
    )
    return pack


@router.post(
    "/rfp/reviewer-signoff-ledger",
    response_model=ReviewerSignoffLedgerResponse,
    dependencies=[Depends(require_api_key)],
)
async def reviewer_signoff_ledger(
    payload: ReviewerSignoffLedgerRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ReviewerSignoffLedgerResponse:
    trace_id = get_trace_id(request)
    collaboration = payload.collaboration
    if collaboration is None:
        inputs = _reviewer_collaboration_inputs(payload, trace_id, container)
        collaboration = container.reviewer_collaboration.create_board(
            trace_id=f"{trace_id}-collaboration",
            **inputs,
        )
    workflow = payload.workflow or container.reviewer_workflow.build_workflow(
        trace_id=f"{trace_id}-workflow",
        collaboration=collaboration,
    )
    ledger = container.reviewer_signoff.ledger(
        trace_id=trace_id,
        collaboration=collaboration,
        workflow=workflow,
        signoff_overrides=payload.signoff_overrides,
    )
    container.audit.record(
        trace_id,
        "rfp.reviewer_signoff_ledger_created",
        "reviewer_signoff_ledger",
        metadata={
            "ledger_status": ledger.ledger_status,
            "records": len(ledger.records),
            "blocked": ledger.summary["blocked_count"],
            "pending": ledger.summary["pending_count"],
        },
    )
    return ledger


@router.post(
    "/rfp/reviewer-signoff-pack",
    response_model=ReviewerSignoffLedgerPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def reviewer_signoff_pack(
    payload: ReviewerSignoffLedgerPackRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ReviewerSignoffLedgerPackResponse:
    trace_id = get_trace_id(request)
    collaboration = payload.collaboration
    if collaboration is None:
        inputs = _reviewer_collaboration_inputs(payload, trace_id, container)
        collaboration = container.reviewer_collaboration.create_board(
            trace_id=f"{trace_id}-collaboration",
            **inputs,
        )
    workflow = payload.workflow or container.reviewer_workflow.build_workflow(
        trace_id=f"{trace_id}-workflow",
        collaboration=collaboration,
    )
    ledger = payload.ledger or container.reviewer_signoff.ledger(
        trace_id=f"{trace_id}-ledger",
        collaboration=collaboration,
        workflow=workflow,
        signoff_overrides=payload.signoff_overrides,
    )
    pack = container.reviewer_signoff.pack(
        trace_id=trace_id,
        collaboration=collaboration,
        workflow=workflow,
        ledger=ledger,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.reviewer_signoff_pack_created",
        "reviewer_signoff_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "ledger_status": pack.ledger.ledger_status,
            "records": len(pack.ledger.records),
        },
    )
    return pack


@router.post(
    "/rfp/reviewer-escalations",
    response_model=ReviewerEscalationResponse,
    dependencies=[Depends(require_api_key)],
)
async def reviewer_escalations(
    payload: ReviewerEscalationRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ReviewerEscalationResponse:
    trace_id = get_trace_id(request)
    collaboration = payload.collaboration
    if collaboration is None:
        inputs = _reviewer_collaboration_inputs(payload, trace_id, container)
        collaboration = container.reviewer_collaboration.create_board(
            trace_id=f"{trace_id}-collaboration",
            **inputs,
        )
    workflow = payload.workflow or container.reviewer_workflow.build_workflow(
        trace_id=f"{trace_id}-workflow",
        collaboration=collaboration,
    )
    ledger = payload.ledger or container.reviewer_signoff.ledger(
        trace_id=f"{trace_id}-ledger",
        collaboration=collaboration,
        workflow=workflow,
        signoff_overrides=payload.signoff_overrides,
    )
    escalation = container.reviewer_escalation.escalation_plan(
        trace_id=trace_id,
        collaboration=collaboration,
        workflow=workflow,
        ledger=ledger,
        sla_hours=payload.sla_hours,
    )
    container.audit.record(
        trace_id,
        "rfp.reviewer_escalations_created",
        "reviewer_escalations",
        metadata={
            "status": escalation.status,
            "escalations": escalation.summary["escalation_count"],
            "critical": escalation.summary["critical_count"],
            "high": escalation.summary["high_count"],
        },
    )
    return escalation


@router.post(
    "/rfp/reviewer-escalation-pack",
    response_model=ReviewerEscalationPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def reviewer_escalation_pack(
    payload: ReviewerEscalationPackRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ReviewerEscalationPackResponse:
    trace_id = get_trace_id(request)
    collaboration = payload.collaboration
    if collaboration is None:
        inputs = _reviewer_collaboration_inputs(payload, trace_id, container)
        collaboration = container.reviewer_collaboration.create_board(
            trace_id=f"{trace_id}-collaboration",
            **inputs,
        )
    workflow = payload.workflow or container.reviewer_workflow.build_workflow(
        trace_id=f"{trace_id}-workflow",
        collaboration=collaboration,
    )
    ledger = payload.ledger or container.reviewer_signoff.ledger(
        trace_id=f"{trace_id}-ledger",
        collaboration=collaboration,
        workflow=workflow,
        signoff_overrides=payload.signoff_overrides,
    )
    escalation = payload.escalation or container.reviewer_escalation.escalation_plan(
        trace_id=f"{trace_id}-escalation",
        collaboration=collaboration,
        workflow=workflow,
        ledger=ledger,
        sla_hours=payload.sla_hours,
    )
    pack = container.reviewer_escalation.pack(
        trace_id=trace_id,
        escalation=escalation,
        collaboration=collaboration,
        workflow=workflow,
        ledger=ledger,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.reviewer_escalation_pack_created",
        "reviewer_escalation_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": pack.escalation.status,
            "escalations": pack.escalation.summary["escalation_count"],
        },
    )
    return pack


@router.post(
    "/rfp/reviewer-trace-reconciliation",
    response_model=ReviewerTraceReconciliationResponse,
    dependencies=[Depends(require_api_key)],
)
async def reviewer_trace_reconciliation(
    payload: ReviewerTraceReconciliationRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ReviewerTraceReconciliationResponse:
    trace_id = get_trace_id(request)
    collaboration, workflow, ledger, escalation = _reviewer_trace_inputs(payload, trace_id, container)
    reconciliation = container.reviewer_trace_reconciliation.reconcile(
        trace_id=trace_id,
        collaboration=collaboration,
        workflow=workflow,
        ledger=ledger,
        escalation=escalation,
    )
    container.audit.record(
        trace_id,
        "rfp.reviewer_trace_reconciliation_created",
        "reviewer_trace_reconciliation",
        metadata={
            "status": reconciliation.status,
            "score": reconciliation.reconciliation_score,
            "findings": reconciliation.summary["finding_count"],
        },
    )
    return reconciliation


@router.post(
    "/rfp/reviewer-trace-reconciliation-pack",
    response_model=ReviewerTraceReconciliationPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def reviewer_trace_reconciliation_pack(
    payload: ReviewerTraceReconciliationPackRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ReviewerTraceReconciliationPackResponse:
    trace_id = get_trace_id(request)
    collaboration, workflow, ledger, escalation = _reviewer_trace_inputs(payload, trace_id, container)
    reconciliation = payload.reconciliation or container.reviewer_trace_reconciliation.reconcile(
        trace_id=f"{trace_id}-reconciliation",
        collaboration=collaboration,
        workflow=workflow,
        ledger=ledger,
        escalation=escalation,
    )
    pack = container.reviewer_trace_reconciliation.pack(
        trace_id=trace_id,
        reconciliation=reconciliation,
        collaboration=collaboration,
        workflow=workflow,
        ledger=ledger,
        escalation=escalation,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.reviewer_trace_reconciliation_pack_created",
        "reviewer_trace_reconciliation_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": pack.reconciliation.status,
            "findings": pack.reconciliation.summary["finding_count"],
        },
    )
    return pack


@router.post(
    "/rfp/action-plan",
    response_model=ActionPlanResponse,
    dependencies=[Depends(require_api_key)],
)
async def action_plan(
    payload: ActionPlanRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ActionPlanResponse:
    trace_id = get_trace_id(request)
    analysis, matrix, customer_profile, customer_fit = _action_plan_inputs(payload, trace_id, container)
    tasks, summary = container.action_plan.create_action_plan(
        trace_id=trace_id,
        analysis=analysis,
        requirement_matrix=matrix,
        customer_profile=customer_profile,
        customer_fit=customer_fit,
        review_findings=payload.review_findings,
    )
    container.audit.record(
        trace_id,
        "rfp.action_plan_created",
        "action_plan",
        metadata={"tasks": len(tasks), "blocked_tasks": summary["blocked_tasks"]},
    )
    return ActionPlanResponse(tasks=tasks, summary=summary, trace_id=trace_id)


@router.post(
    "/rfp/handoff-board",
    response_model=HandoffBoardResponse,
    dependencies=[Depends(require_api_key)],
)
async def handoff_board(
    payload: HandoffBoardRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> HandoffBoardResponse:
    trace_id = get_trace_id(request)
    analysis, matrix, customer_profile, customer_fit = _action_plan_inputs(payload, trace_id, container)
    tasks = payload.action_plan
    if tasks is None:
        tasks, _ = container.action_plan.create_action_plan(
            trace_id=trace_id,
            analysis=analysis,
            requirement_matrix=matrix,
            customer_profile=customer_profile,
            customer_fit=customer_fit,
            review_findings=payload.review_findings,
        )
    handoff = container.action_plan.export_handoff_board(
        trace_id=trace_id,
        tasks=tasks,
        analysis=analysis,
        requirement_matrix=matrix,
        customer_profile=customer_profile,
        customer_fit=customer_fit,
        review_findings=payload.review_findings,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.handoff_board_exported",
        "handoff_board",
        resource_id=handoff.artifact_path,
        metadata={
            "artifact_path": handoff.artifact_path,
            "tasks": len(tasks),
            "blocked_items": len(handoff.board["blocked_items"]),
        },
    )
    return handoff


@router.post(
    "/rfp/readiness-scorecard",
    response_model=DealReadinessScorecardResponse,
    dependencies=[Depends(require_api_key)],
)
async def readiness_scorecard(
    payload: DealReadinessScorecardRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> DealReadinessScorecardResponse:
    trace_id = get_trace_id(request)
    analysis, matrix = _readiness_inputs(payload, container)
    scorecard = container.deal_readiness.create_scorecard(
        trace_id=trace_id,
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=payload.review_findings,
        customer_fit=payload.customer_fit,
        action_plan=payload.action_plan,
        eval_metrics=payload.eval_metrics,
    )
    container.audit.record(
        trace_id,
        "rfp.readiness_scorecard_created",
        "readiness_scorecard",
        metadata={
            "readiness_score": scorecard.readiness_score,
            "readiness_level": scorecard.readiness_level,
            "blockers": len(scorecard.blockers),
        },
    )
    return scorecard


@router.post(
    "/rfp/executive-risk-report",
    response_model=ExecutiveRiskReportResponse,
    dependencies=[Depends(require_api_key)],
)
async def executive_risk_report(
    payload: ExecutiveRiskReportRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ExecutiveRiskReportResponse:
    trace_id = get_trace_id(request)
    analysis, matrix = _readiness_inputs(payload, container)
    scorecard = container.deal_readiness.create_scorecard(
        trace_id=trace_id,
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=payload.review_findings,
        customer_fit=payload.customer_fit,
        action_plan=payload.action_plan,
        eval_metrics=payload.eval_metrics,
    )
    report = container.deal_readiness.export_executive_report(
        trace_id=trace_id,
        scorecard=scorecard,
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=payload.review_findings,
        customer_fit=payload.customer_fit,
        action_plan=payload.action_plan,
        eval_metrics=payload.eval_metrics,
        red_team_summary=payload.red_team_summary,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.executive_risk_report_exported",
        "executive_risk_report",
        resource_id=report.artifact_path,
        metadata={
            "artifact_path": report.artifact_path,
            "readiness_score": scorecard.readiness_score,
            "readiness_level": scorecard.readiness_level,
        },
    )
    return report


@router.post(
    "/rfp/proposal-readiness-score-pack",
    response_model=ProposalReadinessScorePackResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_readiness_score_pack(
    payload: ProposalReadinessScorePackRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ProposalReadinessScorePackResponse:
    trace_id = get_trace_id(request)
    analysis, matrix = _readiness_inputs(payload, container)
    pack = container.deal_readiness.create_score_pack(
        trace_id=trace_id,
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=payload.review_findings,
        customer_fit=payload.customer_fit,
        action_plan=payload.action_plan,
        eval_metrics=payload.eval_metrics,
        draft_response=payload.draft_response,
        red_team_summary=payload.red_team_summary,
        readiness_scorecard=payload.readiness_scorecard,
        executive_report=payload.executive_report,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.proposal_readiness_score_pack_exported",
        "proposal_readiness_score_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "readiness_score": pack.readiness_score,
            "readiness_level": pack.readiness_level,
            "status": pack.status,
        },
    )
    return pack


@router.post(
    "/rfp/readiness-score-eval",
    response_model=ReadinessScoreEvalResponse,
    dependencies=[Depends(require_api_key)],
)
async def readiness_score_eval(
    payload: ReadinessScoreEvalRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ReadinessScoreEvalResponse:
    trace_id = get_trace_id(request)
    eval_pack = container.deal_readiness.evaluate_score_dataset(
        trace_id=trace_id,
        dataset_path=payload.dataset_path,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.readiness_score_eval_ran",
        "readiness_score_eval",
        resource_id=eval_pack.artifact_path,
        metadata={
            "artifact_path": eval_pack.artifact_path,
            "status": eval_pack.status,
            "score": eval_pack.score,
            "scenario_count": eval_pack.scenario_count,
            "failed_count": eval_pack.failed_count,
        },
    )
    return eval_pack


@router.post(
    "/rfp/amendment-impact",
    response_model=RfpAmendmentImpactResponse,
    dependencies=[Depends(require_api_key)],
)
async def rfp_amendment_impact(
    payload: RfpAmendmentImpactRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> RfpAmendmentImpactResponse:
    trace_id = get_trace_id(request)
    baseline_analysis, revised_analysis, matrix = _amendment_impact_inputs(payload, trace_id, container)
    impact = container.amendment_impact.analyze_impact(
        trace_id=trace_id,
        baseline_analysis=baseline_analysis,
        revised_analysis=revised_analysis,
        requirement_matrix=matrix,
        draft_response=payload.draft_response,
        readiness_scorecard=payload.readiness_scorecard,
        review_findings=payload.review_findings,
        amendment_label=payload.amendment_label,
    )
    container.audit.record(
        trace_id,
        "rfp.amendment_impact_created",
        "rfp_amendment_impact",
        metadata={
            "status": impact.status,
            "change_count": impact.summary["change_count"],
            "blocking_change_count": impact.summary["blocking_change_count"],
        },
    )
    return impact


@router.post(
    "/rfp/amendment-impact-pack",
    response_model=RfpAmendmentImpactPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def rfp_amendment_impact_pack(
    payload: RfpAmendmentImpactPackRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> RfpAmendmentImpactPackResponse:
    trace_id = get_trace_id(request)
    impact = payload.impact
    if impact is None:
        baseline_analysis, revised_analysis, matrix = _amendment_impact_inputs(payload, trace_id, container)
        impact = container.amendment_impact.analyze_impact(
            trace_id=f"{trace_id}-impact",
            baseline_analysis=baseline_analysis,
            revised_analysis=revised_analysis,
            requirement_matrix=matrix,
            draft_response=payload.draft_response,
            readiness_scorecard=payload.readiness_scorecard,
            review_findings=payload.review_findings,
            amendment_label=payload.amendment_label,
        )
    pack = container.amendment_impact.pack(
        trace_id=trace_id,
        impact=impact,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.amendment_impact_pack_exported",
        "rfp_amendment_impact_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "status": impact.status,
            "change_count": impact.summary["change_count"],
        },
    )
    return pack


@router.post(
    "/rfp/win-strategy",
    response_model=WinStrategyResponse,
    dependencies=[Depends(require_api_key)],
)
async def win_strategy(
    payload: WinStrategyRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> WinStrategyResponse:
    trace_id = get_trace_id(request)
    analysis, matrix, customer_fit, readiness, memory_matches, action_plan_items = _win_strategy_inputs(
        payload,
        trace_id,
        container,
    )
    strategy = container.win_strategy.create_win_strategy(
        trace_id=trace_id,
        analysis=analysis,
        requirement_matrix=matrix,
        customer_fit=customer_fit,
        readiness_scorecard=readiness,
        response_memory_matches=memory_matches,
        action_plan=action_plan_items,
        review_findings=payload.review_findings,
        competitor_context=payload.competitor_context,
        pricing_notes=payload.pricing_notes,
    )
    container.audit.record(
        trace_id,
        "rfp.win_strategy_created",
        "win_strategy",
        metadata={
            "win_score": strategy.win_score,
            "win_level": strategy.win_level,
            "pricing_risk_level": strategy.pricing_risk["risk_level"],
        },
    )
    return strategy


@router.post(
    "/rfp/pricing-risk-memo",
    response_model=PricingRiskMemoResponse,
    dependencies=[Depends(require_api_key)],
)
async def pricing_risk_memo(
    payload: PricingRiskMemoRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> PricingRiskMemoResponse:
    trace_id = get_trace_id(request)
    analysis, matrix, customer_fit, readiness, memory_matches, action_plan_items = _win_strategy_inputs(
        payload,
        trace_id,
        container,
    )
    strategy = payload.win_strategy or container.win_strategy.create_win_strategy(
        trace_id=f"{trace_id}-win-strategy",
        analysis=analysis,
        requirement_matrix=matrix,
        customer_fit=customer_fit,
        readiness_scorecard=readiness,
        response_memory_matches=memory_matches,
        action_plan=action_plan_items,
        review_findings=payload.review_findings,
        competitor_context=payload.competitor_context,
        pricing_notes=payload.pricing_notes,
    )
    memo = container.win_strategy.export_pricing_risk_memo(
        trace_id=trace_id,
        win_strategy=strategy,
        analysis=analysis,
        requirement_matrix=matrix,
        customer_fit=customer_fit,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.pricing_risk_memo_exported",
        "pricing_risk_memo",
        resource_id=memo.artifact_path,
        metadata={
            "artifact_path": memo.artifact_path,
            "json_artifact_path": memo.json_artifact_path,
            "win_score": strategy.win_score,
            "pricing_risk_level": strategy.pricing_risk["risk_level"],
        },
    )
    return memo


@router.post(
    "/rfp/objection-handling",
    response_model=ObjectionHandlingResponse,
    dependencies=[Depends(require_api_key)],
)
async def objection_handling(
    request: Request,
    payload: ObjectionHandlingRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ObjectionHandlingResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ObjectionHandlingRequest()
    analysis, matrix, customer_fit, readiness, memory_matches, action_plan_items = _win_strategy_inputs(
        request_payload,
        trace_id,
        container,
    )
    strategy = container.win_strategy.create_win_strategy(
        trace_id=f"{trace_id}-win-strategy",
        analysis=analysis,
        requirement_matrix=matrix,
        customer_fit=customer_fit,
        readiness_scorecard=readiness,
        response_memory_matches=memory_matches,
        action_plan=action_plan_items,
        review_findings=request_payload.review_findings,
        competitor_context=request_payload.competitor_context,
        pricing_notes=request_payload.pricing_notes,
    )
    result = await container.objection_handling.objection_handling(
        trace_id,
        analysis=analysis,
        requirement_matrix=matrix,
        win_strategy=strategy,
        response_memory_matches=memory_matches,
        review_findings=request_payload.review_findings,
        competitor_context=request_payload.competitor_context,
        pricing_notes=request_payload.pricing_notes,
        objection_notes=request_payload.objection_notes,
        top_k=request_payload.top_k,
    )
    container.audit.record(
        trace_id,
        "rfp.objection_handling_created",
        "objection_handling",
        metadata={
            "objections": result.coverage_summary["objection_count"],
            "coverage_ratio": result.coverage_summary["coverage_ratio"],
            "blocked": result.coverage_summary["blocked_count"],
            "average_confidence": result.confidence_summary["average_confidence"],
            "workflow_transitions": result.workflow_summary.get("transition_count", 0),
            "workflow_replay_status": result.workflow_summary.get("replay_status"),
        },
    )
    return result


@router.post(
    "/rfp/objection-handling-pack",
    response_model=ObjectionHandlingPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def objection_handling_pack(
    request: Request,
    payload: ObjectionHandlingPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ObjectionHandlingPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ObjectionHandlingPackRequest()
    handling = request_payload.objection_handling
    if handling is None:
        analysis, matrix, customer_fit, readiness, memory_matches, action_plan_items = _win_strategy_inputs(
            request_payload,
            trace_id,
            container,
        )
        strategy = container.win_strategy.create_win_strategy(
            trace_id=f"{trace_id}-win-strategy",
            analysis=analysis,
            requirement_matrix=matrix,
            customer_fit=customer_fit,
            readiness_scorecard=readiness,
            response_memory_matches=memory_matches,
            action_plan=action_plan_items,
            review_findings=request_payload.review_findings,
            competitor_context=request_payload.competitor_context,
            pricing_notes=request_payload.pricing_notes,
        )
        handling = await container.objection_handling.objection_handling(
            f"{trace_id}-objections",
            analysis=analysis,
            requirement_matrix=matrix,
            win_strategy=strategy,
            response_memory_matches=memory_matches,
            review_findings=request_payload.review_findings,
            competitor_context=request_payload.competitor_context,
            pricing_notes=request_payload.pricing_notes,
            objection_notes=request_payload.objection_notes,
            top_k=request_payload.top_k,
        )
    pack = container.objection_handling.handling_pack(
        trace_id,
        handling,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.objection_handling_pack_exported",
        "objection_handling_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "objections": pack.objection_handling.coverage_summary["objection_count"],
            "coverage_ratio": pack.objection_handling.coverage_summary["coverage_ratio"],
            "workflow_transitions": pack.objection_handling.workflow_summary.get("transition_count", 0),
            "eval_assertions": len(pack.objection_handling.eval_assertions),
        },
    )
    return pack


@router.post(
    "/rfp/objection-audit",
    response_model=ObjectionAuditResponse,
    dependencies=[Depends(require_api_key)],
)
async def objection_audit(
    request: Request,
    payload: ObjectionAuditRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ObjectionAuditResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ObjectionAuditRequest()
    handling = request_payload.objection_handling
    if handling is None:
        analysis, matrix, customer_fit, readiness, memory_matches, action_plan_items = _win_strategy_inputs(
            request_payload,
            trace_id,
            container,
        )
        strategy = container.win_strategy.create_win_strategy(
            trace_id=f"{trace_id}-win-strategy",
            analysis=analysis,
            requirement_matrix=matrix,
            customer_fit=customer_fit,
            readiness_scorecard=readiness,
            response_memory_matches=memory_matches,
            action_plan=action_plan_items,
            review_findings=request_payload.review_findings,
            competitor_context=request_payload.competitor_context,
            pricing_notes=request_payload.pricing_notes,
        )
        handling = await container.objection_handling.objection_handling(
            f"{trace_id}-objections",
            analysis=analysis,
            requirement_matrix=matrix,
            win_strategy=strategy,
            response_memory_matches=memory_matches,
            review_findings=request_payload.review_findings,
            competitor_context=request_payload.competitor_context,
            pricing_notes=request_payload.pricing_notes,
            objection_notes=request_payload.objection_notes,
            top_k=request_payload.top_k,
        )
    audit = container.objection_handling.audit_objections(trace_id, handling)
    container.audit.record(
        trace_id,
        "rfp.objection_audit_created",
        "objection_audit",
        metadata={
            "claim_count": audit.audit_summary["claim_count"],
            "audit_status": audit.audit_summary["audit_status"],
            "unsupported_claim_count": audit.audit_summary["unsupported_claim_count"],
            "blocked_claim_count": audit.audit_summary["blocked_claim_count"],
            "workflow_transitions": audit.workflow_summary.get("transition_count", 0),
        },
    )
    return audit


@router.post(
    "/rfp/objection-audit-pack",
    response_model=ObjectionAuditPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def objection_audit_pack(
    request: Request,
    payload: ObjectionAuditPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ObjectionAuditPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ObjectionAuditPackRequest()
    audit = request_payload.objection_audit
    if audit is None:
        handling = request_payload.objection_handling
        if handling is None:
            analysis, matrix, customer_fit, readiness, memory_matches, action_plan_items = _win_strategy_inputs(
                request_payload,
                trace_id,
                container,
            )
            strategy = container.win_strategy.create_win_strategy(
                trace_id=f"{trace_id}-win-strategy",
                analysis=analysis,
                requirement_matrix=matrix,
                customer_fit=customer_fit,
                readiness_scorecard=readiness,
                response_memory_matches=memory_matches,
                action_plan=action_plan_items,
                review_findings=request_payload.review_findings,
                competitor_context=request_payload.competitor_context,
                pricing_notes=request_payload.pricing_notes,
            )
            handling = await container.objection_handling.objection_handling(
                f"{trace_id}-objections",
                analysis=analysis,
                requirement_matrix=matrix,
                win_strategy=strategy,
                response_memory_matches=memory_matches,
                review_findings=request_payload.review_findings,
                competitor_context=request_payload.competitor_context,
                pricing_notes=request_payload.pricing_notes,
                objection_notes=request_payload.objection_notes,
                top_k=request_payload.top_k,
            )
        audit = container.objection_handling.audit_objections(f"{trace_id}-audit", handling)
    pack = container.objection_handling.audit_pack(
        trace_id,
        audit,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.objection_audit_pack_exported",
        "objection_audit_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "claim_count": pack.objection_audit.audit_summary["claim_count"],
            "audit_status": pack.objection_audit.audit_summary["audit_status"],
            "workflow_transitions": pack.objection_audit.workflow_summary.get("transition_count", 0),
        },
    )
    return pack


@router.post(
    "/rfp/contract-risk",
    response_model=ContractRiskResponse,
    dependencies=[Depends(require_api_key)],
)
async def contract_risk(
    payload: ContractRiskRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ContractRiskResponse:
    trace_id = get_trace_id(request)
    text = _contract_text_from_payload(payload, container)
    risk = container.contract_risk.analyze(text, trace_id, customer_profile_id=payload.customer_profile_id)
    container.audit.record(
        trace_id,
        "rfp.contract_risk_analyzed",
        "contract_risk",
        metadata={
            "risk_score": risk.risk_score,
            "status": risk.status,
            "risky_clauses": len(risk.risky_clauses),
            "missing_evidence_warnings": len(risk.missing_evidence_warnings),
        },
    )
    return risk


@router.post(
    "/rfp/negotiation-brief",
    response_model=NegotiationBriefResponse,
    dependencies=[Depends(require_api_key)],
)
async def negotiation_brief(
    payload: NegotiationBriefRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> NegotiationBriefResponse:
    trace_id = get_trace_id(request)
    risk = payload.contract_risk
    if risk is None:
        text = _contract_text_from_payload(payload, container)
        risk = container.contract_risk.analyze(
            text,
            f"{trace_id}-contract-risk",
            customer_profile_id=payload.customer_profile_id,
        )
    brief = container.contract_risk.export_negotiation_brief(
        trace_id=trace_id,
        contract_risk=risk,
        win_strategy=payload.win_strategy,
        pricing_memo=payload.pricing_memo,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.negotiation_brief_exported",
        "negotiation_brief",
        resource_id=brief.artifact_path,
        metadata={
            "artifact_path": brief.artifact_path,
            "json_artifact_path": brief.json_artifact_path,
            "risk_score": risk.risk_score,
            "status": risk.status,
        },
    )
    return brief


@router.post(
    "/rfp/evidence-gaps",
    response_model=EvidenceGapResponse,
    dependencies=[Depends(require_api_key)],
)
async def evidence_gaps(
    payload: EvidenceGapRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> EvidenceGapResponse:
    trace_id = get_trace_id(request)
    (
        analysis,
        matrix,
        review_findings,
        red_team_summary,
        readiness,
        strategy,
        contract,
        action_plan_items,
    ) = _evidence_gap_inputs(payload, trace_id, container)
    gaps, summary = container.evidence_gap.create_gap_plan(
        trace_id=trace_id,
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review_findings,
        red_team_summary=red_team_summary,
        readiness_scorecard=readiness,
        win_strategy=strategy,
        contract_risk=contract,
        action_plan=action_plan_items,
    )
    container.audit.record(
        trace_id,
        "rfp.evidence_gaps_created",
        "evidence_gap_plan",
        metadata={
            "gap_count": summary["gap_count"],
            "high_severity_count": summary["high_severity_count"],
        },
    )
    return EvidenceGapResponse(gaps=gaps, summary=summary, trace_id=trace_id)


@router.post(
    "/rfp/source-request-pack",
    response_model=SourceRequestPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def source_request_pack(
    payload: SourceRequestPackRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> SourceRequestPackResponse:
    trace_id = get_trace_id(request)
    (
        analysis,
        matrix,
        review_findings,
        red_team_summary,
        readiness,
        strategy,
        contract,
        action_plan_items,
    ) = _evidence_gap_inputs(payload, trace_id, container)
    gaps = payload.evidence_gaps
    if gaps is None:
        gaps, _ = container.evidence_gap.create_gap_plan(
            trace_id=f"{trace_id}-gaps",
            analysis=analysis,
            requirement_matrix=matrix,
            review_findings=review_findings,
            red_team_summary=red_team_summary,
            readiness_scorecard=readiness,
            win_strategy=strategy,
            contract_risk=contract,
            action_plan=action_plan_items,
        )
    pack = container.evidence_gap.export_source_request_pack(
        trace_id=trace_id,
        gaps=gaps,
        analysis=analysis,
        red_team_summary=red_team_summary,
        readiness_scorecard=readiness,
        win_strategy=strategy,
        contract_risk=contract,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.source_request_pack_exported",
        "source_request_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "gap_count": pack.pack["summary"]["gap_count"],
            "high_severity_count": pack.pack["summary"]["high_severity_count"],
        },
    )
    return pack


@router.post(
    "/rfp/clarification-questions",
    response_model=ClarificationQuestionResponse,
    dependencies=[Depends(require_api_key)],
)
async def clarification_questions(
    payload: ClarificationQuestionRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ClarificationQuestionResponse:
    trace_id = get_trace_id(request)
    (
        analysis,
        matrix,
        review_findings,
        red_team_summary,
        readiness,
        strategy,
        contract,
        action_plan_items,
    ) = _evidence_gap_inputs(payload, trace_id, container)
    gaps = payload.evidence_gaps
    if gaps is None:
        gaps, _ = container.evidence_gap.create_gap_plan(
            trace_id=f"{trace_id}-gaps",
            analysis=analysis,
            requirement_matrix=matrix,
            review_findings=review_findings,
            red_team_summary=red_team_summary,
            readiness_scorecard=readiness,
            win_strategy=strategy,
            contract_risk=contract,
            action_plan=action_plan_items,
        )
    questions = await container.clarification_questions.create_questions(
        trace_id=trace_id,
        analysis=analysis,
        requirement_matrix=matrix,
        evidence_gaps=gaps,
        review_findings=review_findings,
        readiness_scorecard=readiness,
        contract_risk=contract,
        top_k=payload.top_k,
        max_questions=payload.max_questions,
    )
    container.audit.record(
        trace_id,
        "rfp.clarification_questions_created",
        "clarification_questions",
        metadata={
            "question_count": questions.summary["question_count"],
            "buyer_question_count": questions.summary["buyer_question_count"],
            "approval_required_count": questions.summary["approval_required_count"],
        },
    )
    return questions


@router.post(
    "/rfp/clarification-question-pack",
    response_model=ClarificationQuestionPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def clarification_question_pack(
    payload: ClarificationQuestionPackRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ClarificationQuestionPackResponse:
    trace_id = get_trace_id(request)
    questions = payload.clarification_questions
    if questions is None:
        (
            analysis,
            matrix,
            review_findings,
            red_team_summary,
            readiness,
            strategy,
            contract,
            action_plan_items,
        ) = _evidence_gap_inputs(payload, trace_id, container)
        gaps = payload.evidence_gaps
        if gaps is None:
            gaps, _ = container.evidence_gap.create_gap_plan(
                trace_id=f"{trace_id}-gaps",
                analysis=analysis,
                requirement_matrix=matrix,
                review_findings=review_findings,
                red_team_summary=red_team_summary,
                readiness_scorecard=readiness,
                win_strategy=strategy,
                contract_risk=contract,
                action_plan=action_plan_items,
            )
        questions = await container.clarification_questions.create_questions(
            trace_id=f"{trace_id}-questions",
            analysis=analysis,
            requirement_matrix=matrix,
            evidence_gaps=gaps,
            review_findings=review_findings,
            readiness_scorecard=readiness,
            contract_risk=contract,
            top_k=payload.top_k,
            max_questions=payload.max_questions,
        )
    pack = container.clarification_questions.question_pack(
        trace_id=trace_id,
        clarification_questions=questions,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.clarification_question_pack_exported",
        "clarification_question_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "question_count": pack.pack["summary"]["question_count"],
            "approval_required_count": pack.pack["summary"]["approval_required_count"],
        },
    )
    return pack


@router.post(
    "/rfp/timeline-plan",
    response_model=TimelinePlanResponse,
    dependencies=[Depends(require_api_key)],
)
async def timeline_plan(
    payload: TimelinePlanRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> TimelinePlanResponse:
    trace_id = get_trace_id(request)
    (
        analysis,
        matrix,
        review_findings,
        red_team_summary,
        readiness,
        strategy,
        contract,
        action_plan_items,
        gaps,
        source_pack,
        leadership,
    ) = _timeline_inputs(payload, trace_id, container)
    plan = container.timeline_orchestration.create_plan(
        trace_id=trace_id,
        analysis=analysis,
        requirement_matrix=matrix,
        action_plan=action_plan_items,
        evidence_gaps=gaps,
        contract_risk=contract,
        win_strategy=strategy,
        readiness_scorecard=readiness,
        source_request_pack=source_pack,
        leadership_brief=leadership,
        review_findings=review_findings,
        red_team_summary=red_team_summary,
    )
    container.audit.record(
        trace_id,
        "rfp.timeline_plan_created",
        "timeline_plan",
        metadata={
            "milestone_count": plan.summary["milestone_count"],
            "blocked_count": plan.summary["blocked_count"],
            "calendar_entry_count": plan.summary["calendar_entry_count"],
        },
    )
    return plan


@router.post(
    "/rfp/submission-calendar-pack",
    response_model=SubmissionCalendarPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def submission_calendar_pack(
    payload: SubmissionCalendarPackRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> SubmissionCalendarPackResponse:
    trace_id = get_trace_id(request)
    (
        analysis,
        matrix,
        review_findings,
        red_team_summary,
        readiness,
        strategy,
        contract,
        action_plan_items,
        gaps,
        source_pack,
        leadership,
    ) = _timeline_inputs(payload, trace_id, container)
    plan = payload.timeline_plan
    if plan is None:
        plan = container.timeline_orchestration.create_plan(
            trace_id=f"{trace_id}-timeline",
            analysis=analysis,
            requirement_matrix=matrix,
            action_plan=action_plan_items,
            evidence_gaps=gaps,
            contract_risk=contract,
            win_strategy=strategy,
            readiness_scorecard=readiness,
            source_request_pack=source_pack,
            leadership_brief=leadership,
            review_findings=review_findings,
            red_team_summary=red_team_summary,
        )
    pack = container.timeline_orchestration.export_submission_calendar_pack(
        trace_id=trace_id,
        plan=plan,
        analysis=analysis,
        source_request_pack=source_pack,
        leadership_brief=leadership,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.submission_calendar_pack_exported",
        "submission_calendar_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "milestone_count": pack.pack["summary"]["milestone_count"],
            "blocked_count": pack.pack["summary"]["blocked_count"],
        },
    )
    return pack


@router.post(
    "/rfp/submission-decision",
    response_model=SubmissionDecisionResponse,
    dependencies=[Depends(require_api_key)],
)
async def submission_decision(
    payload: SubmissionDecisionRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> SubmissionDecisionResponse:
    trace_id = get_trace_id(request)
    inputs = _submission_decision_inputs(payload, trace_id, container)
    decision = container.submission_decision.create_decision(trace_id=trace_id, **inputs)
    container.audit.record(
        trace_id,
        "rfp.submission_decision_created",
        "submission_decision",
        metadata={
            "decision": decision.decision,
            "score": decision.score,
            "blocking_issues": len(decision.blocking_issues),
            "exceptions": len(decision.exception_list),
        },
    )
    return decision


@router.post(
    "/rfp/executive-submission-memo",
    response_model=ExecutiveSubmissionMemoResponse,
    dependencies=[Depends(require_api_key)],
)
async def executive_submission_memo(
    payload: ExecutiveSubmissionMemoRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ExecutiveSubmissionMemoResponse:
    trace_id = get_trace_id(request)
    decision = payload.submission_decision
    if decision is None:
        inputs = _submission_decision_inputs(payload, trace_id, container)
        decision = container.submission_decision.create_decision(trace_id=f"{trace_id}-decision", **inputs)
    memo = container.submission_decision.export_memo(
        trace_id=trace_id,
        decision=decision,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.executive_submission_memo_exported",
        "executive_submission_memo",
        resource_id=memo.artifact_path,
        metadata={
            "artifact_path": memo.artifact_path,
            "json_artifact_path": memo.json_artifact_path,
            "decision": decision.decision,
            "score": decision.score,
        },
    )
    return memo


@router.post(
    "/rfp/exception-register",
    response_model=SubmissionExceptionRegisterResponse,
    dependencies=[Depends(require_api_key)],
)
async def submission_exception_register(
    payload: SubmissionExceptionRegisterRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> SubmissionExceptionRegisterResponse:
    trace_id = get_trace_id(request)
    decision = payload.submission_decision
    if decision is None:
        inputs = _submission_decision_inputs(payload, trace_id, container)
        decision = container.submission_decision.create_decision(trace_id=f"{trace_id}-decision", **inputs)
    collaboration = payload.reviewer_collaboration
    if collaboration is None:
        collaboration_inputs = _reviewer_collaboration_inputs(payload, trace_id, container)
        collaboration_inputs["submission_decision"] = decision
        collaboration = container.reviewer_collaboration.create_board(
            trace_id=f"{trace_id}-reviewer-collaboration",
            **collaboration_inputs,
        )
    register = container.submission_exceptions.create_register(
        trace_id=trace_id,
        submission_decision=decision,
        reviewer_collaboration=collaboration,
    )
    container.audit.record(
        trace_id,
        "rfp.exception_register_created",
        "submission_exception_register",
        metadata={
            "exceptions": len(register.exceptions),
            "status": register.register_status,
            "requires_approval": register.summary["requires_approval_count"],
        },
    )
    return register


@router.post(
    "/rfp/exception-pack",
    response_model=SubmissionExceptionPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def submission_exception_pack(
    payload: SubmissionExceptionPackRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> SubmissionExceptionPackResponse:
    trace_id = get_trace_id(request)
    register = payload.exception_register
    if register is None:
        decision = payload.submission_decision
        if decision is None:
            inputs = _submission_decision_inputs(payload, trace_id, container)
            decision = container.submission_decision.create_decision(trace_id=f"{trace_id}-decision", **inputs)
        collaboration = payload.reviewer_collaboration
        if collaboration is None:
            collaboration_inputs = _reviewer_collaboration_inputs(payload, trace_id, container)
            collaboration_inputs["submission_decision"] = decision
            collaboration = container.reviewer_collaboration.create_board(
                trace_id=f"{trace_id}-reviewer-collaboration",
                **collaboration_inputs,
            )
        register = container.submission_exceptions.create_register(
            trace_id=f"{trace_id}-register",
            submission_decision=decision,
            reviewer_collaboration=collaboration,
        )
    pack = container.submission_exceptions.exception_pack(
        trace_id=trace_id,
        exception_register=register,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.exception_pack_created",
        "submission_exception_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "exceptions": len(pack.exception_register.exceptions),
        },
    )
    return pack


@router.post(
    "/rfp/leadership-brief",
    response_model=LeadershipBriefResponse,
    dependencies=[Depends(require_api_key)],
)
async def leadership_brief(
    payload: LeadershipBriefRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> LeadershipBriefResponse:
    trace_id = get_trace_id(request)
    analysis = payload.analysis or payload.analyzed_payload
    if analysis is None and payload.rfp_document_id is not None:
        analysis = _analysis_from_workbench_payload(payload, trace_id, container)

    matrix = payload.matrix or payload.requirement_matrix
    if matrix is None and analysis is not None:
        matrix = container.workbench.create_requirement_matrix(analysis)

    if not any(
        [
            analysis,
            matrix,
            payload.draft_response,
            payload.answers,
            payload.export_payload,
            payload.review_findings,
            payload.customer_fit,
            payload.action_plan,
            payload.handoff_board,
            payload.readiness_scorecard,
            payload.executive_report,
            payload.eval_metrics,
            payload.red_team_summary,
        ]
    ):
        raise HTTPException(
            status_code=400,
            detail="Provide an RFP, analysis, matrix, or workflow artifact to summarize.",
        )

    draft = payload.draft_response
    if draft is None and analysis is not None:
        draft = await container.generation.draft_response(
            trace_id=f"{trace_id}-draft",
            requirement_ids=[requirement.id for requirement in analysis.requirements],
            top_k=5,
        )

    customer_fit_result = payload.customer_fit
    memory_matches = list(payload.response_memory_matches)
    if payload.customer_profile_id and customer_fit_result is None and (analysis is not None or matrix):
        try:
            customer_fit_result = container.customer_intelligence.customer_fit(
                payload.customer_profile_id,
                trace_id=f"{trace_id}-customer-fit",
                analysis=analysis,
                requirement_matrix=matrix,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    if payload.customer_profile_id and not memory_matches and analysis is not None:
        memory_query = " ".join(requirement.text for requirement in analysis.requirements)
        memory_matches = container.customer_intelligence.search_response_memory(
            memory_query,
            trace_id=f"{trace_id}-response-memory",
            customer_profile_id=payload.customer_profile_id,
            top_k=5,
        )

    export_payload = payload.export_payload
    export_artifact_path = payload.export_artifact_path
    export_json_artifact_path = payload.export_json_artifact_path
    if export_payload is None and analysis is not None and draft is not None:
        export = container.workbench.export_package(
            analysis,
            draft,
            trace_id=f"{trace_id}-export",
            write_artifact=payload.write_artifact,
            customer_fit=customer_fit_result,
            response_memory_matches=memory_matches,
        )
        export_payload = export.package
        export_artifact_path = export.artifact_path
        export_json_artifact_path = export.json_artifact_path

    review_findings = list(payload.review_findings)
    review_passed = payload.review_passed
    if review_passed is None and not review_findings and (matrix or draft is not None or export_payload is not None):
        review = container.review_board.review_package(
            trace_id=f"{trace_id}-review",
            requirement_matrix=matrix,
            draft_response=draft,
            answer_payloads=payload.answers,
            export_payload=export_payload,
        )
        review_findings = review.findings
        review_passed = review.passed

    action_plan_items = list(payload.action_plan)
    if not action_plan_items and (matrix or analysis is not None):
        action_plan_items, _ = container.action_plan.create_action_plan(
            trace_id=f"{trace_id}-action-plan",
            analysis=analysis,
            requirement_matrix=matrix,
            customer_fit=customer_fit_result,
            review_findings=review_findings,
        )

    handoff_board_payload = payload.handoff_board
    handoff_artifact_path = payload.handoff_artifact_path
    handoff_json_artifact_path = payload.handoff_json_artifact_path
    if handoff_board_payload is None and action_plan_items:
        handoff = container.action_plan.export_handoff_board(
            trace_id=f"{trace_id}-handoff",
            tasks=action_plan_items,
            analysis=analysis,
            requirement_matrix=matrix,
            customer_fit=customer_fit_result,
            review_findings=review_findings,
            write_artifact=payload.write_artifact,
        )
        handoff_board_payload = handoff.board
        handoff_artifact_path = handoff.artifact_path
        handoff_json_artifact_path = handoff.json_artifact_path

    readiness = payload.readiness_scorecard
    has_readiness_input = any(
        [
            analysis,
            matrix,
            review_findings,
            customer_fit_result,
            action_plan_items,
            payload.eval_metrics,
        ]
    )
    if readiness is None and has_readiness_input:
        readiness = container.deal_readiness.create_scorecard(
            trace_id=f"{trace_id}-readiness",
            analysis=analysis,
            requirement_matrix=matrix,
            review_findings=review_findings,
            customer_fit=customer_fit_result,
            action_plan=action_plan_items,
            eval_metrics=payload.eval_metrics,
        )

    executive_report_payload = payload.executive_report
    executive_report_artifact_path = payload.executive_report_artifact_path
    executive_report_json_artifact_path = payload.executive_report_json_artifact_path
    if executive_report_payload is None and readiness is not None:
        executive_report_payload = container.deal_readiness.export_executive_report(
            trace_id=f"{trace_id}-executive-report",
            scorecard=readiness,
            analysis=analysis,
            requirement_matrix=matrix,
            review_findings=review_findings,
            customer_fit=customer_fit_result,
            action_plan=action_plan_items,
            eval_metrics=payload.eval_metrics,
            red_team_summary=payload.red_team_summary,
            write_artifact=payload.write_artifact,
        )
        executive_report_artifact_path = executive_report_payload.artifact_path
        executive_report_json_artifact_path = executive_report_payload.json_artifact_path

    brief = container.leadership_brief.export_brief(
        trace_id=trace_id,
        documents_ingested=len(container.repo.documents),
        analysis=analysis,
        requirement_matrix=matrix,
        draft_response=draft,
        answers=payload.answers,
        export_payload=export_payload,
        export_artifact_path=export_artifact_path,
        export_json_artifact_path=export_json_artifact_path,
        review_findings=review_findings,
        review_passed=review_passed,
        customer_fit=customer_fit_result,
        response_memory_matches=memory_matches,
        action_plan=action_plan_items,
        handoff_board=handoff_board_payload,
        handoff_artifact_path=handoff_artifact_path,
        handoff_json_artifact_path=handoff_json_artifact_path,
        readiness_scorecard=readiness,
        executive_report=executive_report_payload,
        executive_report_artifact_path=executive_report_artifact_path,
        executive_report_json_artifact_path=executive_report_json_artifact_path,
        eval_metrics=payload.eval_metrics,
        red_team_summary=payload.red_team_summary,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rfp.leadership_brief_exported",
        "leadership_brief",
        resource_id=brief.artifact_path,
        metadata={
            "artifact_path": brief.artifact_path,
            "requirements": brief.brief["metrics"]["requirements"],
            "readiness_score": brief.brief["metrics"]["readiness_score"],
        },
    )
    return brief


@router.post(
    "/rfp/submission-regression",
    response_model=SubmissionRegressionResponse,
    dependencies=[Depends(require_api_key)],
)
async def submission_regression(
    payload: SubmissionRegressionRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> SubmissionRegressionResponse:
    trace_id = get_trace_id(request)
    result = await container.submission_regression.run(container, payload, trace_id)
    container.audit.record(
        trace_id,
        "rfp.submission_regression_completed",
        "submission_regression",
        metadata={
            "passed": result.passed,
            "failed_checks": result.failed_checks,
            "artifact_paths": result.artifact_paths,
        },
    )
    return result


@router.post(
    "/rfp/demo-script",
    response_model=DemoScriptResponse,
    dependencies=[Depends(require_api_key)],
)
async def demo_script(
    payload: DemoScriptRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> DemoScriptResponse:
    trace_id = get_trace_id(request)
    regression = payload.regression
    if regression is None:
        if not payload.run_regression:
            raise HTTPException(status_code=400, detail="Provide regression or set run_regression=true.")
        regression = await container.submission_regression.run(
            container,
            payload.regression_request,
            f"{trace_id}-regression",
        )
    script = container.demo_script.generate(trace_id, regression, write_artifact=payload.write_artifact)
    container.audit.record(
        trace_id,
        "rfp.demo_script_generated",
        "demo_script",
        resource_id=script.artifact_path,
        metadata={
            "artifact_path": script.artifact_path,
            "json_artifact_path": script.json_artifact_path,
            "regression_passed": regression.passed,
        },
    )
    return script


@router.get("/ops/smoke-matrix", response_model=SmokeMatrixResponse, dependencies=[Depends(require_api_key)])
async def smoke_matrix(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> SmokeMatrixResponse:
    trace_id = get_trace_id(request)
    matrix = container.launch_checklist.smoke_matrix(trace_id)
    container.audit.record(
        trace_id,
        "ops.smoke_matrix_viewed",
        "smoke_matrix",
        metadata={
            "endpoints": matrix.readiness_summary.total_endpoints,
            "artifact_endpoints": matrix.readiness_summary.artifact_writing_endpoints,
            "readiness_level": matrix.readiness_summary.readiness_level,
        },
    )
    return matrix


@router.post("/ops/launch-checklist", response_model=LaunchChecklistResponse, dependencies=[Depends(require_api_key)])
async def launch_checklist(
    payload: LaunchChecklistRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> LaunchChecklistResponse:
    trace_id = get_trace_id(request)
    checklist = container.launch_checklist.launch_checklist(trace_id, write_artifact=payload.write_artifact)
    container.audit.record(
        trace_id,
        "ops.launch_checklist_generated",
        "launch_checklist",
        resource_id=checklist.artifact_path,
        metadata={
            "artifact_path": checklist.artifact_path,
            "json_artifact_path": checklist.json_artifact_path,
            "endpoints": checklist.smoke_matrix.readiness_summary.total_endpoints,
        },
    )
    return checklist


@router.get("/ops/cost-governance", response_model=CostGovernanceResponse, dependencies=[Depends(require_api_key)])
async def cost_governance(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> CostGovernanceResponse:
    trace_id = get_trace_id(request)
    report = container.cost_governance.report(trace_id)
    container.audit.record(
        trace_id,
        "ops.cost_governance_viewed",
        "cost_governance",
        metadata={
            "status": report.governance_status,
            "provider_mode": report.provider_readiness["provider_mode"],
            "daily_estimated_cost": report.budget_summary["daily_estimated_cost"],
        },
    )
    return report


@router.post(
    "/ops/cost-governance",
    response_model=CostGovernanceResponse,
    dependencies=[Depends(require_api_key)],
)
async def cost_governance_with_assumptions(
    payload: CostGovernanceRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> CostGovernanceResponse:
    trace_id = get_trace_id(request)
    report = container.cost_governance.report(
        trace_id,
        daily_rfp_count=payload.daily_rfp_count,
        questions_per_rfp=payload.questions_per_rfp,
        draft_sections_per_rfp=payload.draft_sections_per_rfp,
        eval_runs_per_day=payload.eval_runs_per_day,
        red_team_runs_per_day=payload.red_team_runs_per_day,
        daily_budget_usd=payload.daily_budget_usd,
    )
    container.audit.record(
        trace_id,
        "ops.cost_governance_viewed",
        "cost_governance",
        metadata={
            "status": report.governance_status,
            "provider_mode": report.provider_readiness["provider_mode"],
            "daily_estimated_cost": report.budget_summary["daily_estimated_cost"],
            "daily_budget_usd": report.budget_summary["daily_budget_usd"],
        },
    )
    return report


@router.post(
    "/ops/cost-governance-pack",
    response_model=CostGovernancePackResponse,
    dependencies=[Depends(require_api_key)],
)
async def cost_governance_pack(
    request: Request,
    payload: CostGovernancePackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> CostGovernancePackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or CostGovernancePackRequest()
    governance = request_payload.governance
    if governance is None:
        governance = container.cost_governance.report(
            f"{trace_id}-report",
            daily_rfp_count=request_payload.daily_rfp_count,
            questions_per_rfp=request_payload.questions_per_rfp,
            draft_sections_per_rfp=request_payload.draft_sections_per_rfp,
            eval_runs_per_day=request_payload.eval_runs_per_day,
            red_team_runs_per_day=request_payload.red_team_runs_per_day,
            daily_budget_usd=request_payload.daily_budget_usd,
        )
    pack = container.cost_governance.pack(
        trace_id,
        report=governance,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "ops.cost_governance_pack_generated",
        "cost_governance_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": pack.governance.governance_status,
            "daily_estimated_cost": pack.governance.budget_summary["daily_estimated_cost"],
        },
    )
    return pack


@router.get(
    "/ops/provider-resilience",
    response_model=ProviderResilienceResponse,
    dependencies=[Depends(require_api_key)],
)
async def provider_resilience(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ProviderResilienceResponse:
    trace_id = get_trace_id(request)
    resilience = container.provider_resilience.resilience(trace_id)
    container.audit.record(
        trace_id,
        "ops.provider_resilience_viewed",
        "provider_resilience",
        metadata={
            "status": resilience.status,
            "active_provider_mode": resilience.active_provider_mode,
            "recommended_route_id": resilience.recommended_route_id,
            "fallback_required": resilience.summary["fallback_required"],
        },
    )
    return resilience


@router.post(
    "/ops/provider-resilience-pack",
    response_model=ProviderResiliencePackResponse,
    dependencies=[Depends(require_api_key)],
)
async def provider_resilience_pack(
    request: Request,
    payload: ProviderResiliencePackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ProviderResiliencePackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ProviderResiliencePackRequest()
    resilience = request_payload.resilience or container.provider_resilience.resilience(f"{trace_id}-resilience")
    pack = container.provider_resilience.pack(
        trace_id,
        resilience=resilience,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "ops.provider_resilience_pack_generated",
        "provider_resilience_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": pack.resilience.status,
            "recommended_route_id": pack.resilience.recommended_route_id,
        },
    )
    return pack


@router.get(
    "/runtime/demo-readiness",
    response_model=RuntimeDemoReadinessResponse,
    dependencies=[Depends(require_api_key)],
)
async def runtime_demo_readiness(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> RuntimeDemoReadinessResponse:
    trace_id = get_trace_id(request)
    readiness = container.runtime_demo.readiness(trace_id)
    container.audit.record(
        trace_id,
        "runtime.demo_readiness_viewed",
        "runtime_demo_readiness",
        metadata={
            "status": readiness.status,
            "ports_listening": sum(check["listening"] for check in readiness.process_port_checks),
            "dependency_count": len(readiness.dependency_checks),
        },
    )
    return readiness


@router.post(
    "/runtime/demo-pack",
    response_model=RuntimeDemoPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def runtime_demo_pack(
    request: Request,
    payload: RuntimeDemoPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> RuntimeDemoPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or RuntimeDemoPackRequest()
    pack = container.runtime_demo.demo_pack(trace_id, write_artifact=request_payload.write_artifact)
    container.audit.record(
        trace_id,
        "runtime.demo_pack_generated",
        "runtime_demo_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "readiness_status": pack.readiness.status,
        },
    )
    return pack


@router.get("/ops/ci-doctor", response_model=CiDoctorResponse, dependencies=[Depends(require_api_key)])
async def ci_doctor(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> CiDoctorResponse:
    trace_id = get_trace_id(request)
    doctor = container.ci_doctor.ci_doctor(trace_id)
    container.audit.record(
        trace_id,
        "ops.ci_doctor_viewed",
        "ci_doctor",
        metadata={
            "status": doctor.status,
            "score": doctor.score,
            "checks": len(doctor.checks),
            "secret_findings": doctor.secret_scan.finding_count,
        },
    )
    return doctor


@router.post("/ops/audit-pack", response_model=AuditPackResponse, dependencies=[Depends(require_api_key)])
async def audit_pack(
    request: Request,
    payload: AuditPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> AuditPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or AuditPackRequest()
    doctor = container.ci_doctor.ci_doctor(f"{trace_id}-doctor")
    pack = container.ci_doctor.audit_pack(
        trace_id,
        write_artifact=request_payload.write_artifact,
        doctor=doctor,
    )
    container.audit.record(
        trace_id,
        "ops.audit_pack_generated",
        "audit_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "ci_doctor_status": doctor.status,
            "ci_doctor_score": doctor.score,
            "secret_findings": doctor.secret_scan.finding_count,
        },
    )
    return pack


@router.get("/api/contract-audit", response_model=ApiContractAuditResponse, dependencies=[Depends(require_api_key)])
async def api_contract_audit(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ApiContractAuditResponse:
    trace_id = get_trace_id(request)
    smoke = container.launch_checklist.smoke_matrix(f"{trace_id}-smoke")
    dashboard = container.ui_verification.dashboard_smoke(f"{trace_id}-dashboard-smoke")
    inventory = container.artifact_inventory.inventory(f"{trace_id}-inventory")
    audit = container.api_contracts.audit(
        trace_id,
        request.app.openapi(),
        smoke,
        dashboard,
        inventory,
    )
    container.audit.record(
        trace_id,
        "api.contract_audit_viewed",
        "api_contract",
        metadata={
            "openapi_route_count": audit.openapi_route_count,
            "auth_protected": audit.auth_protected_endpoint_count,
            "status": audit.status,
        },
    )
    return audit


@router.post(
    "/api/reviewer-collection",
    response_model=ReviewerCollectionResponse,
    dependencies=[Depends(require_api_key)],
)
async def reviewer_collection(
    request: Request,
    payload: ReviewerCollectionRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ReviewerCollectionResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ReviewerCollectionRequest()
    smoke = container.launch_checklist.smoke_matrix(f"{trace_id}-smoke")
    dashboard = container.ui_verification.dashboard_smoke(f"{trace_id}-dashboard-smoke")
    inventory = container.artifact_inventory.inventory(f"{trace_id}-inventory")
    audit = container.api_contracts.audit(
        f"{trace_id}-contract-audit",
        request.app.openapi(),
        smoke,
        dashboard,
        inventory,
    )
    collection = container.api_contracts.reviewer_collection(
        trace_id,
        audit,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "api.reviewer_collection_generated",
        "api_contract",
        resource_id=collection.artifact_path,
        metadata={
            "artifact_path": collection.artifact_path,
            "json_artifact_path": collection.json_artifact_path,
            "openapi_route_count": audit.openapi_route_count,
        },
    )
    return collection


@router.get("/ui/dashboard-smoke", response_model=DashboardSmokeResponse, dependencies=[Depends(require_api_key)])
async def dashboard_smoke(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> DashboardSmokeResponse:
    trace_id = get_trace_id(request)
    smoke = container.ui_verification.dashboard_smoke(trace_id)
    container.audit.record(
        trace_id,
        "ui.dashboard_smoke_viewed",
        "dashboard_smoke",
        metadata={
            "status": smoke.status,
            "view_count": smoke.summary["view_count"],
            "endpoint_count": smoke.summary["endpoint_count"],
            "failed_checks": smoke.summary["failed_checks"],
        },
    )
    return smoke


@router.post(
    "/ui/verification-pack",
    response_model=UIVerificationPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def ui_verification_pack(
    request: Request,
    payload: UIVerificationPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> UIVerificationPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or UIVerificationPackRequest()
    pack = container.ui_verification.verification_pack(
        trace_id,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "ui.verification_pack_generated",
        "ui_verification_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "dashboard_smoke_status": pack.dashboard_smoke.status,
            "failed_checks": pack.dashboard_smoke.summary["failed_checks"],
        },
    )
    return pack


@router.get(
    "/artifacts/inventory",
    response_model=ArtifactInventoryResponse,
    dependencies=[Depends(require_api_key)],
)
async def artifact_inventory(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ArtifactInventoryResponse:
    trace_id = get_trace_id(request)
    inventory = container.artifact_inventory.inventory(trace_id)
    container.audit.record(
        trace_id,
        "artifacts.inventory_viewed",
        "artifact_inventory",
        metadata={
            "total_directories": inventory.total_directories,
            "total_files": inventory.total_files,
            "ignored_status": inventory.ignored_status,
        },
    )
    return inventory


@router.post(
    "/artifacts/readme-checklist",
    response_model=ReadmeChecklistResponse,
    dependencies=[Depends(require_api_key)],
)
async def readme_checklist(
    request: Request,
    payload: ReadmeChecklistRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ReadmeChecklistResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ReadmeChecklistRequest()
    checklist = container.artifact_inventory.readme_checklist(
        trace_id,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "artifacts.readme_checklist_generated",
        "readme_checklist",
        resource_id=checklist.artifact_path,
        metadata={
            "artifact_path": checklist.artifact_path,
            "json_artifact_path": checklist.json_artifact_path,
            "inventory_directories": checklist.inventory.total_directories,
            "inventory_files": checklist.inventory.total_files,
        },
    )
    return checklist


@router.get(
    "/release/quality-gate",
    response_model=ReleaseQualityGateResponse,
    dependencies=[Depends(require_api_key)],
)
async def release_quality_gate(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ReleaseQualityGateResponse:
    trace_id = get_trace_id(request)
    smoke = container.launch_checklist.smoke_matrix(f"{trace_id}-smoke")
    gate = container.release.quality_gate(smoke, trace_id)
    container.audit.record(
        trace_id,
        "release.quality_gate_viewed",
        "release_quality_gate",
        metadata={
            "status": gate.status,
            "score": gate.score,
            "blockers": len(gate.blockers),
            "warnings": len(gate.warnings),
        },
    )
    return gate


@router.post(
    "/release/publish-pack",
    response_model=PublishPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def release_publish_pack(
    request: Request,
    payload: PublishPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> PublishPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or PublishPackRequest()
    smoke = container.launch_checklist.smoke_matrix(f"{trace_id}-smoke")
    gate = container.release.quality_gate(smoke, f"{trace_id}-gate")
    artifact_path, json_artifact_path, markdown, pack = container.release.publish_pack(
        gate,
        smoke,
        trace_id,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "release.publish_pack_generated",
        "release_publish_pack",
        resource_id=artifact_path,
        metadata={
            "artifact_path": artifact_path,
            "json_artifact_path": json_artifact_path,
            "gate_status": gate.status,
            "gate_score": gate.score,
        },
    )
    return PublishPackResponse(
        artifact_path=artifact_path,
        json_artifact_path=json_artifact_path,
        markdown=markdown,
        pack=pack,
        quality_gate=gate,
        trace_id=trace_id,
    )


@router.get(
    "/ops/verification-evidence",
    response_model=VerificationEvidenceResponse,
    dependencies=[Depends(require_api_key)],
)
async def verification_evidence_current(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> VerificationEvidenceResponse:
    trace_id = get_trace_id(request)
    smoke = container.launch_checklist.smoke_matrix(f"{trace_id}-smoke")
    dashboard_smoke = container.ui_verification.dashboard_smoke(f"{trace_id}-dashboard-smoke")
    artifact_inventory = container.artifact_inventory.inventory(f"{trace_id}-artifact-inventory")
    release_gate = container.release.quality_gate(smoke, f"{trace_id}-release-gate")
    final_audit = container.final_handoff.final_audit(
        f"{trace_id}-final-audit",
        smoke,
        artifact_inventory,
        dashboard_smoke,
    )
    evidence = container.verification_evidence.evidence(
        trace_id,
        release_gate,
        final_audit,
        dashboard_smoke,
        artifact_inventory,
    )
    container.audit.record(
        trace_id,
        "ops.verification_evidence_viewed",
        "verification_evidence",
        metadata={
            "status": evidence.status,
            "score": evidence.score,
            "recorded_commands": evidence.summary["recorded_command_count"],
            "failed_commands": evidence.summary["failed_command_count"],
        },
    )
    return evidence


@router.post(
    "/ops/verification-evidence",
    response_model=VerificationEvidenceResponse,
    dependencies=[Depends(require_api_key)],
)
async def verification_evidence(
    request: Request,
    payload: VerificationEvidenceRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> VerificationEvidenceResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or VerificationEvidenceRequest()
    smoke = container.launch_checklist.smoke_matrix(f"{trace_id}-smoke")
    dashboard_smoke = container.ui_verification.dashboard_smoke(f"{trace_id}-dashboard-smoke")
    artifact_inventory = container.artifact_inventory.inventory(f"{trace_id}-artifact-inventory")
    release_gate = container.release.quality_gate(smoke, f"{trace_id}-release-gate")
    final_audit = container.final_handoff.final_audit(
        f"{trace_id}-final-audit",
        smoke,
        artifact_inventory,
        dashboard_smoke,
    )
    evidence = container.verification_evidence.evidence(
        trace_id,
        release_gate,
        final_audit,
        dashboard_smoke,
        artifact_inventory,
        command_results=request_payload.command_results,
    )
    container.audit.record(
        trace_id,
        "ops.verification_evidence_viewed",
        "verification_evidence",
        metadata={
            "status": evidence.status,
            "score": evidence.score,
            "recorded_commands": evidence.summary["recorded_command_count"],
            "failed_commands": evidence.summary["failed_command_count"],
        },
    )
    return evidence


@router.post(
    "/ops/verification-evidence-pack",
    response_model=VerificationEvidencePackResponse,
    dependencies=[Depends(require_api_key)],
)
async def verification_evidence_pack(
    request: Request,
    payload: VerificationEvidencePackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> VerificationEvidencePackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or VerificationEvidencePackRequest()
    evidence = request_payload.evidence
    if evidence is None:
        smoke = container.launch_checklist.smoke_matrix(f"{trace_id}-smoke")
        dashboard_smoke = container.ui_verification.dashboard_smoke(f"{trace_id}-dashboard-smoke")
        artifact_inventory = container.artifact_inventory.inventory(f"{trace_id}-artifact-inventory")
        release_gate = container.release.quality_gate(smoke, f"{trace_id}-release-gate")
        final_audit = container.final_handoff.final_audit(
            f"{trace_id}-final-audit",
            smoke,
            artifact_inventory,
            dashboard_smoke,
        )
        evidence = container.verification_evidence.evidence(
            f"{trace_id}-evidence",
            release_gate,
            final_audit,
            dashboard_smoke,
            artifact_inventory,
            command_results=request_payload.command_results,
        )
    pack = container.verification_evidence.pack(
        trace_id,
        evidence,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "ops.verification_evidence_pack_generated",
        "verification_evidence_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "evidence_status": pack.evidence.status,
            "evidence_score": pack.evidence.score,
        },
    )
    return pack


@router.get(
    "/git/readiness",
    response_model=GitReadinessResponse,
    dependencies=[Depends(require_api_key)],
)
async def git_readiness(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> GitReadinessResponse:
    trace_id = get_trace_id(request)
    readiness = container.git_readiness.readiness(trace_id)
    container.audit.record(
        trace_id,
        "git.readiness_viewed",
        "git_readiness",
        metadata={
            "status": readiness.status,
            "branch": readiness.current_branch,
            "dirty": readiness.working_tree_summary["dirty"],
            "changed": readiness.working_tree_summary["changed"],
        },
    )
    return readiness


@router.post(
    "/git/push-plan",
    response_model=GitPushPlanResponse,
    dependencies=[Depends(require_api_key)],
)
async def git_push_plan(
    request: Request,
    payload: GitPushPlanRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> GitPushPlanResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or GitPushPlanRequest()
    pack = container.git_readiness.push_plan(trace_id, write_artifact=request_payload.write_artifact)
    container.audit.record(
        trace_id,
        "git.push_plan_generated",
        "git_push_plan",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "readiness_status": pack.readiness.status,
            "commit_groups": len(pack.pack["suggested_commit_grouping"]),
        },
    )
    return pack


@router.get(
    "/portfolio/evidence-index",
    response_model=PortfolioEvidenceIndexResponse,
    dependencies=[Depends(require_api_key)],
)
async def portfolio_evidence_index(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> PortfolioEvidenceIndexResponse:
    trace_id = get_trace_id(request)
    evidence = container.portfolio.evidence_index(trace_id)
    container.audit.record(
        trace_id,
        "portfolio.evidence_index_viewed",
        "portfolio_evidence_index",
        metadata={
            "evidence_score": evidence.evidence_score,
            "covered_skill_count": evidence.covered_skill_count,
            "total_skill_count": evidence.total_skill_count,
        },
    )
    return evidence


@router.post(
    "/portfolio/interview-pack",
    response_model=PortfolioInterviewPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def portfolio_interview_pack(
    request: Request,
    payload: PortfolioInterviewPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> PortfolioInterviewPackResponse:
    trace_id = get_trace_id(request)
    pack = await container.portfolio.generate_interview_pack(container, trace_id, payload)
    container.audit.record(
        trace_id,
        "portfolio.interview_pack_generated",
        "portfolio_interview_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "evidence_score": pack.evidence_index.evidence_score,
            "covered_skill_count": pack.evidence_index.covered_skill_count,
        },
    )
    return pack


@router.get(
    "/reviewer/quickstart",
    response_model=ReviewerQuickstartResponse,
    dependencies=[Depends(require_api_key)],
)
async def reviewer_quickstart(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ReviewerQuickstartResponse:
    trace_id = get_trace_id(request)
    quickstart = container.reviewer.quickstart(trace_id)
    container.audit.record(
        trace_id,
        "reviewer.quickstart_viewed",
        "reviewer_quickstart",
        metadata={
            "status": quickstart.status,
            "endpoint_count": len(quickstart.endpoint_walkthrough_order),
            "artifact_roots": len(quickstart.artifact_proof_map),
        },
    )
    return quickstart


@router.post(
    "/reviewer/walkthrough-pack",
    response_model=ReviewerWalkthroughPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def reviewer_walkthrough_pack(
    request: Request,
    payload: ReviewerWalkthroughPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ReviewerWalkthroughPackResponse:
    trace_id = get_trace_id(request)
    pack = container.reviewer.walkthrough_pack(trace_id, payload)
    container.audit.record(
        trace_id,
        "reviewer.walkthrough_pack_generated",
        "reviewer_walkthrough_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "quickstart_status": pack.quickstart.status,
            "endpoint_count": len(pack.quickstart.endpoint_walkthrough_order),
        },
    )
    return pack


@router.get(
    "/handoff/final-audit",
    response_model=FinalAuditResponse,
    dependencies=[Depends(require_api_key)],
)
async def final_handoff_audit(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> FinalAuditResponse:
    trace_id = get_trace_id(request)
    smoke = container.launch_checklist.smoke_matrix(f"{trace_id}-smoke")
    inventory = container.artifact_inventory.inventory(f"{trace_id}-inventory")
    dashboard_smoke = container.ui_verification.dashboard_smoke(f"{trace_id}-dashboard-smoke")
    audit = container.final_handoff.final_audit(trace_id, smoke, inventory, dashboard_smoke)
    container.audit.record(
        trace_id,
        "handoff.final_audit_viewed",
        "final_audit",
        metadata={
            "status": audit.status,
            "score": audit.score,
            "failed_checks": audit.summary["failed_checks"],
        },
    )
    return audit


@router.post(
    "/handoff/final-pack",
    response_model=FinalPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def final_handoff_pack(
    request: Request,
    payload: FinalPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> FinalPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or FinalPackRequest()
    smoke = container.launch_checklist.smoke_matrix(f"{trace_id}-smoke")
    inventory = container.artifact_inventory.inventory(f"{trace_id}-inventory")
    dashboard_smoke = container.ui_verification.dashboard_smoke(f"{trace_id}-dashboard-smoke")
    audit = container.final_handoff.final_audit(f"{trace_id}-audit", smoke, inventory, dashboard_smoke)
    artifact_path, json_artifact_path, markdown, pack = container.final_handoff.final_pack(
        trace_id,
        audit,
        smoke,
        inventory,
        dashboard_smoke,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "handoff.final_pack_generated",
        "final_handoff_pack",
        resource_id=artifact_path,
        metadata={
            "artifact_path": artifact_path,
            "json_artifact_path": json_artifact_path,
            "final_audit_status": audit.status,
            "final_audit_score": audit.score,
        },
    )
    return FinalPackResponse(
        artifact_path=artifact_path,
        json_artifact_path=json_artifact_path,
        markdown=markdown,
        pack=pack,
        final_audit=audit,
        trace_id=trace_id,
    )


@router.post("/rfp/evaluate", response_model=EvaluationMetrics, dependencies=[Depends(require_api_key)])
async def evaluate(
    payload: EvaluateRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> EvaluationMetrics:
    trace_id = get_trace_id(request)
    result = await container.evaluation.run(payload.dataset_path, trace_id, payload.top_k)
    container.audit.record(trace_id, "eval.completed", "evaluation", metadata=result.model_dump())
    return result


@router.get("/rag/corpus-coverage", response_model=RagCorpusCoverageResponse, dependencies=[Depends(require_api_key)])
async def rag_corpus_coverage(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> RagCorpusCoverageResponse:
    trace_id = get_trace_id(request)
    coverage = container.corpus_coverage.corpus_coverage(trace_id)
    container.audit.record(
        trace_id,
        "rag.corpus_coverage_viewed",
        "rag_corpus_coverage",
        metadata={
            "status": coverage.status,
            "score": coverage.score,
            "sample_document_count": coverage.corpus_metadata["sample_document_count"],
            "gaps": len(coverage.gaps),
        },
    )
    return coverage


@router.post(
    "/rag/eval-coverage-pack",
    response_model=RagEvalCoveragePackResponse,
    dependencies=[Depends(require_api_key)],
)
async def rag_eval_coverage_pack(
    request: Request,
    payload: RagEvalCoveragePackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> RagEvalCoveragePackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or RagEvalCoveragePackRequest()
    pack = container.corpus_coverage.eval_coverage_pack(
        trace_id,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "rag.eval_coverage_pack_generated",
        "rag_eval_coverage_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "coverage_status": pack.coverage.status,
            "coverage_score": pack.coverage.score,
        },
    )
    return pack


@router.post(
    "/rag/retrieval-experiments",
    response_model=RetrievalExperimentResponse,
    dependencies=[Depends(require_api_key)],
)
async def retrieval_experiments(
    request: Request,
    payload: RetrievalExperimentRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> RetrievalExperimentResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or RetrievalExperimentRequest()
    await _freshness_inputs(container)
    try:
        result = await container.retrieval_experiments.compare(
            trace_id=trace_id,
            dataset_path=request_payload.dataset_path,
            outcomes_fixture_path=request_payload.outcomes_fixture_path,
            top_k=request_payload.top_k,
            policy_ids=request_payload.policy_ids,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    container.audit.record(
        trace_id,
        "rag.retrieval_experiments_compared",
        "retrieval_experiments",
        metadata={
            "status": result.status,
            "recommended_policy_id": result.recommended_policy_id,
            "policy_count": result.summary["policy_count"],
            "question_count": result.summary["question_count"],
        },
    )
    return result


@router.post(
    "/rag/retrieval-experiment-pack",
    response_model=RetrievalExperimentPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def retrieval_experiment_pack(
    request: Request,
    payload: RetrievalExperimentPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> RetrievalExperimentPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or RetrievalExperimentPackRequest()
    await _freshness_inputs(container)
    try:
        pack = await container.retrieval_experiments.experiment_pack(
            trace_id=trace_id,
            comparison=request_payload.comparison,
            dataset_path=request_payload.dataset_path,
            outcomes_fixture_path=request_payload.outcomes_fixture_path,
            top_k=request_payload.top_k,
            policy_ids=request_payload.policy_ids,
            write_artifact=request_payload.write_artifact,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    container.audit.record(
        trace_id,
        "rag.retrieval_experiment_pack_generated",
        "retrieval_experiment_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": pack.comparison.status,
            "recommended_policy_id": pack.comparison.recommended_policy_id,
        },
    )
    return pack


@router.get(
    "/evidence/freshness",
    response_model=EvidenceFreshnessResponse,
    dependencies=[Depends(require_api_key)],
)
async def evidence_freshness(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> EvidenceFreshnessResponse:
    trace_id = get_trace_id(request)
    await _freshness_inputs(container)
    result = container.evidence_freshness.freshness_report(trace_id)
    container.audit.record(
        trace_id,
        "evidence.freshness_viewed",
        "evidence_freshness",
        metadata={
            "sources": result.summary["source_count"],
            "expired": result.summary["expired_count"],
            "unsupported_claims": result.summary["unsupported_claim_count"],
            "high_or_critical": result.summary["high_or_critical_risk_count"],
        },
    )
    return result


@router.post(
    "/evidence/freshness-pack",
    response_model=EvidenceFreshnessPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def evidence_freshness_pack(
    request: Request,
    payload: EvidenceFreshnessPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> EvidenceFreshnessPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or EvidenceFreshnessPackRequest()
    await _freshness_inputs(container)
    freshness = container.evidence_freshness.freshness_report(f"{trace_id}-freshness")
    pack = container.evidence_freshness.freshness_pack(
        trace_id,
        freshness,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "evidence.freshness_pack_generated",
        "evidence_freshness_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "sources": pack.freshness.summary["source_count"],
            "expired": pack.freshness.summary["expired_count"],
        },
    )
    return pack


@router.get(
    "/evidence/freshness-sla",
    response_model=EvidenceFreshnessSlaResponse,
    dependencies=[Depends(require_api_key)],
)
async def evidence_freshness_sla(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> EvidenceFreshnessSlaResponse:
    trace_id = get_trace_id(request)
    await _freshness_inputs(container)
    freshness = container.evidence_freshness.freshness_report(f"{trace_id}-freshness")
    sla = container.evidence_sla.ledger(trace_id, freshness)
    container.audit.record(
        trace_id,
        "evidence.freshness_sla_viewed",
        "evidence_freshness_sla",
        metadata={
            "status": sla.status,
            "items": sla.summary["sla_item_count"],
            "breached": sla.summary["breached_count"],
            "blocked_endpoints": sla.summary["blocked_endpoint_count"],
        },
    )
    return sla


@router.post(
    "/evidence/freshness-sla-pack",
    response_model=EvidenceFreshnessSlaPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def evidence_freshness_sla_pack(
    request: Request,
    payload: EvidenceFreshnessSlaPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> EvidenceFreshnessSlaPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or EvidenceFreshnessSlaPackRequest()
    await _freshness_inputs(container)
    freshness = container.evidence_freshness.freshness_report(f"{trace_id}-freshness")
    sla = container.evidence_sla.ledger(f"{trace_id}-sla", freshness)
    pack = container.evidence_sla.pack(
        trace_id,
        sla,
        freshness,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "evidence.freshness_sla_pack_generated",
        "evidence_freshness_sla_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": pack.sla.status,
            "items": pack.sla.summary["sla_item_count"],
        },
    )
    return pack


@router.get(
    "/evidence/conflicts",
    response_model=EvidenceConflictResponse,
    dependencies=[Depends(require_api_key)],
)
async def evidence_conflicts(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> EvidenceConflictResponse:
    trace_id = get_trace_id(request)
    await _freshness_inputs(container)
    result = container.evidence_conflicts.conflict_report(trace_id)
    container.audit.record(
        trace_id,
        "evidence.conflicts_viewed",
        "evidence_conflicts",
        metadata={
            "claims": result.summary["claim_count"],
            "conflicts": result.summary["conflict_count"],
            "blocked": result.summary["blocking_conflict_count"],
            "needs_review": result.summary["needs_review_count"],
        },
    )
    return result


@router.post(
    "/evidence/conflict-pack",
    response_model=EvidenceConflictPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def evidence_conflict_pack(
    request: Request,
    payload: EvidenceConflictPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> EvidenceConflictPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or EvidenceConflictPackRequest()
    await _freshness_inputs(container)
    conflicts = container.evidence_conflicts.conflict_report(f"{trace_id}-conflicts")
    pack = container.evidence_conflicts.conflict_pack(
        trace_id,
        conflicts,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "evidence.conflict_pack_generated",
        "evidence_conflict_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "conflicts": pack.conflicts.summary["conflict_count"],
            "blocked": pack.conflicts.summary["blocking_conflict_count"],
        },
    )
    return pack


@router.get(
    "/evidence/citation-lineage",
    response_model=CitationLineageAuditResponse,
    dependencies=[Depends(require_api_key)],
)
async def evidence_citation_lineage(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> CitationLineageAuditResponse:
    trace_id = get_trace_id(request)
    answer, draft = await _citation_lineage_inputs(trace_id, container)
    result = container.citation_lineage.audit(trace_id, answers=[answer], drafts=[draft])
    container.audit.record(
        trace_id,
        "evidence.citation_lineage_viewed",
        "citation_lineage",
        metadata={
            "citations": result.summary["citation_count"],
            "verified": result.summary["verified_count"],
            "blocking_issues": result.summary["blocking_issue_count"],
            "score": result.score,
        },
    )
    return result


@router.post(
    "/evidence/citation-lineage-pack",
    response_model=CitationLineagePackResponse,
    dependencies=[Depends(require_api_key)],
)
async def evidence_citation_lineage_pack(
    request: Request,
    payload: CitationLineagePackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> CitationLineagePackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or CitationLineagePackRequest()
    answer, draft = await _citation_lineage_inputs(trace_id, container)
    lineage = container.citation_lineage.audit(f"{trace_id}-lineage", answers=[answer], drafts=[draft])
    pack = container.citation_lineage.lineage_pack(
        trace_id,
        lineage,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "evidence.citation_lineage_pack_generated",
        "citation_lineage_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "citations": pack.lineage.summary["citation_count"],
            "blocking_issues": pack.lineage.summary["blocking_issue_count"],
        },
    )
    return pack


@router.get(
    "/evidence/source-trust",
    response_model=SourceTrustGateResponse,
    dependencies=[Depends(require_api_key)],
)
async def evidence_source_trust(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> SourceTrustGateResponse:
    trace_id = get_trace_id(request)
    freshness, conflicts, lineage = await _source_trust_inputs(trace_id, container)
    result = container.source_trust.trust_gate(trace_id, freshness, conflicts, lineage)
    container.audit.record(
        trace_id,
        "evidence.source_trust_viewed",
        "source_trust",
        metadata={
            "status": result.status,
            "sources": result.summary["source_count"],
            "approved": result.summary["approved_count"],
            "blocked": result.summary["blocked_count"],
            "approval_required": result.summary["approval_required_count"],
        },
    )
    return result


@router.post(
    "/evidence/source-trust-pack",
    response_model=SourceTrustPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def evidence_source_trust_pack(
    request: Request,
    payload: SourceTrustPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> SourceTrustPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or SourceTrustPackRequest()
    freshness, conflicts, lineage = await _source_trust_inputs(trace_id, container)
    source_trust = container.source_trust.trust_gate(f"{trace_id}-source-trust", freshness, conflicts, lineage)
    pack = container.source_trust.trust_pack(
        trace_id,
        source_trust,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "evidence.source_trust_pack_generated",
        "source_trust_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": pack.source_trust.status,
            "sources": pack.source_trust.summary["source_count"],
            "blocked": pack.source_trust.summary["blocked_count"],
        },
    )
    return pack


@router.post(
    "/evidence/governed-retrieval",
    response_model=GovernedRetrievalResponse,
    dependencies=[Depends(require_api_key)],
)
async def evidence_governed_retrieval(
    payload: GovernedRetrievalRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> GovernedRetrievalResponse:
    trace_id = get_trace_id(request)
    freshness, conflicts, lineage = await _source_trust_inputs(trace_id, container)
    source_trust = container.source_trust.trust_gate(f"{trace_id}-source-trust", freshness, conflicts, lineage)
    result = await container.governed_retrieval.preview(
        trace_id,
        payload.question,
        source_trust,
        top_k=payload.top_k,
        include_suppressed=payload.include_suppressed,
    )
    container.audit.record(
        trace_id,
        "evidence.governed_retrieval_viewed",
        "governed_retrieval",
        metadata={
            "status": result.status,
            "question": result.question,
            "candidates": result.summary["candidate_count"],
            "allowed": result.summary["allowed_count"],
            "approval_required": result.summary["approval_required_count"],
        },
    )
    return result


@router.post(
    "/evidence/governed-retrieval-pack",
    response_model=GovernedRetrievalPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def evidence_governed_retrieval_pack(
    request: Request,
    payload: GovernedRetrievalPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> GovernedRetrievalPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or GovernedRetrievalPackRequest()
    governed = request_payload.governed_retrieval
    if governed is None:
        freshness, conflicts, lineage = await _source_trust_inputs(trace_id, container)
        source_trust = container.source_trust.trust_gate(f"{trace_id}-source-trust", freshness, conflicts, lineage)
        governed = await container.governed_retrieval.preview(
            f"{trace_id}-governed-retrieval",
            request_payload.question,
            source_trust,
            top_k=request_payload.top_k,
            include_suppressed=request_payload.include_suppressed,
        )
    pack = container.governed_retrieval.pack(
        trace_id,
        governed,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "evidence.governed_retrieval_pack_generated",
        "governed_retrieval_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": pack.governed_retrieval.status,
            "allowed": pack.governed_retrieval.summary["allowed_count"],
            "approval_required": pack.governed_retrieval.summary["approval_required_count"],
        },
    )
    return pack


@router.get(
    "/proposal/intake-triage",
    response_model=ProposalIntakeTriageResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_intake_triage(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ProposalIntakeTriageResponse:
    trace_id = get_trace_id(request)
    triage = _proposal_intake_triage(trace_id, container)
    container.audit.record(
        trace_id,
        "proposal.intake_triage_viewed",
        "proposal_intake_triage",
        metadata={
            "status": triage.status,
            "readiness_score": triage.readiness_score,
            "route": triage.recommended_route,
            "signals": len(triage.signals),
            "tasks": len(triage.owner_tasks),
        },
    )
    return triage


@router.post(
    "/proposal/intake-triage-pack",
    response_model=ProposalIntakeTriagePackResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_intake_triage_pack(
    request: Request,
    payload: ProposalIntakeTriagePackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ProposalIntakeTriagePackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ProposalIntakeTriagePackRequest()
    triage = request_payload.triage or _proposal_intake_triage(f"{trace_id}-triage", container)
    pack = container.proposal_intake.pack(
        trace_id,
        triage,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "proposal.intake_triage_pack_generated",
        "proposal_intake_triage_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": pack.triage.status,
            "readiness_score": pack.triage.readiness_score,
            "route": pack.triage.recommended_route,
        },
    )
    return pack


@router.get(
    "/proposal/buyer-intelligence",
    response_model=BuyerIntelligenceWorkflowResponse,
    dependencies=[Depends(require_api_key)],
)
async def buyer_intelligence_workflow(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> BuyerIntelligenceWorkflowResponse:
    trace_id = get_trace_id(request)
    inputs = await _buyer_intelligence_inputs(trace_id, container)
    result = container.buyer_intelligence.workflow(trace_id=trace_id, **inputs)
    container.audit.record(
        trace_id,
        "proposal.buyer_intelligence_viewed",
        "buyer_intelligence_workflow",
        metadata={
            "status": result.workflow_status,
            "stages": len(result.workflow_stages),
            "approvals": len(result.human_approval_queue),
            "gates": len(result.governance_gates),
        },
    )
    return result


@router.post(
    "/proposal/buyer-intelligence-pack",
    response_model=BuyerIntelligencePackResponse,
    dependencies=[Depends(require_api_key)],
)
async def buyer_intelligence_pack(
    request: Request,
    payload: BuyerIntelligencePackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> BuyerIntelligencePackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or BuyerIntelligencePackRequest()
    inputs = await _buyer_intelligence_inputs(trace_id, container)
    workflow = container.buyer_intelligence.workflow(trace_id=f"{trace_id}-workflow", **inputs)
    pack = container.buyer_intelligence.pack(
        trace_id,
        workflow,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "proposal.buyer_intelligence_pack_generated",
        "buyer_intelligence_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "state_artifact_path": pack.state_artifact_path,
            "status": pack.workflow.workflow_status,
            "approvals": len(pack.workflow.human_approval_queue),
        },
    )
    return pack


@router.get(
    "/proposal/buyer-intelligence-replay",
    response_model=BuyerWorkflowReplayResponse,
    dependencies=[Depends(require_api_key)],
)
async def buyer_intelligence_replay(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> BuyerWorkflowReplayResponse:
    trace_id = get_trace_id(request)
    inputs = await _buyer_intelligence_inputs(trace_id, container)
    workflow = container.buyer_intelligence.workflow(trace_id=f"{trace_id}-workflow", **inputs)
    replay = container.buyer_intelligence.replay(trace_id, workflow)
    container.audit.record(
        trace_id,
        "proposal.buyer_intelligence_replay_viewed",
        "buyer_workflow_replay",
        metadata={
            "status": replay.status,
            "workflow_id": replay.workflow_id,
            "transitions": replay.transition_count,
            "checkpoint_validation": replay.checkpoint_validation["status"],
        },
    )
    return replay


@router.post(
    "/proposal/buyer-intelligence-replay-pack",
    response_model=BuyerWorkflowReplayPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def buyer_intelligence_replay_pack(
    request: Request,
    payload: BuyerWorkflowReplayPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> BuyerWorkflowReplayPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or BuyerWorkflowReplayPackRequest()
    inputs = await _buyer_intelligence_inputs(trace_id, container)
    workflow = container.buyer_intelligence.workflow(trace_id=f"{trace_id}-workflow", **inputs)
    replay = container.buyer_intelligence.replay(f"{trace_id}-replay", workflow)
    pack = container.buyer_intelligence.replay_pack(
        trace_id,
        replay,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "proposal.buyer_intelligence_replay_pack_generated",
        "buyer_workflow_replay_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": pack.replay.status,
            "transitions": pack.replay.transition_count,
        },
    )
    return pack


@router.get(
    "/proposal/agent-council",
    response_model=ProposalAgentCouncilResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_agent_council(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ProposalAgentCouncilResponse:
    trace_id = get_trace_id(request)
    inputs = await _buyer_intelligence_inputs(trace_id, container)
    workflow = container.buyer_intelligence.workflow(trace_id=f"{trace_id}-workflow", **inputs)
    council = container.proposal_agent_council.council(
        trace_id=trace_id,
        workflow=workflow,
        cost_governance=inputs["cost_governance"],
        source_trust=inputs["source_trust"],
        model_risk=inputs["model_risk"],
        procurement_risk=inputs["procurement_risk"],
    )
    container.audit.record(
        trace_id,
        "proposal.agent_council_viewed",
        "proposal_agent_council",
        metadata={
            "status": council.status,
            "agents": len(council.agents),
            "turns": len(council.conversation),
            "handoffs": len(council.handoffs),
        },
    )
    return council


@router.post(
    "/proposal/approval-simulation",
    response_model=ProposalApprovalSimulationResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_approval_simulation(
    request: Request,
    payload: ProposalApprovalSimulationRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ProposalApprovalSimulationResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ProposalApprovalSimulationRequest()
    workflow = request_payload.workflow
    if workflow is None:
        inputs = await _buyer_intelligence_inputs(trace_id, container)
        workflow = container.buyer_intelligence.workflow(trace_id=f"{trace_id}-workflow", **inputs)
    simulation = container.approval_simulation.simulate(
        trace_id=trace_id,
        workflow=workflow,
        requested_by=request_payload.requested_by,
        decisions=request_payload.decisions,
    )
    container.audit.record(
        trace_id,
        "proposal.approval_simulation_created",
        "proposal_approval_simulation",
        metadata={
            "status": simulation.status,
            "decisions": len(simulation.decision_records),
            "unresolved": simulation.unresolved_approval_count,
            "simulated_workflow_status": simulation.simulated_workflow_status,
        },
    )
    return simulation


@router.post(
    "/proposal/approval-simulation-pack",
    response_model=ProposalApprovalSimulationPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_approval_simulation_pack(
    request: Request,
    payload: ProposalApprovalSimulationPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ProposalApprovalSimulationPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ProposalApprovalSimulationPackRequest()
    simulation = request_payload.simulation
    if simulation is None:
        workflow = request_payload.workflow
        if workflow is None:
            inputs = await _buyer_intelligence_inputs(trace_id, container)
            workflow = container.buyer_intelligence.workflow(trace_id=f"{trace_id}-workflow", **inputs)
        simulation = container.approval_simulation.simulate(
            trace_id=f"{trace_id}-simulation",
            workflow=workflow,
            requested_by=request_payload.requested_by,
            decisions=request_payload.decisions,
        )
    pack = container.approval_simulation.pack(
        trace_id,
        simulation,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "proposal.approval_simulation_pack_generated",
        "proposal_approval_simulation_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "state_artifact_path": pack.state_artifact_path,
            "status": pack.simulation.status,
            "decisions": len(pack.simulation.decision_records),
        },
    )
    return pack


@router.post(
    "/proposal/agent-council-pack",
    response_model=ProposalAgentCouncilPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_agent_council_pack(
    request: Request,
    payload: ProposalAgentCouncilPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ProposalAgentCouncilPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ProposalAgentCouncilPackRequest()
    inputs = await _buyer_intelligence_inputs(trace_id, container)
    workflow = container.buyer_intelligence.workflow(trace_id=f"{trace_id}-workflow", **inputs)
    council = container.proposal_agent_council.council(
        trace_id=f"{trace_id}-council",
        workflow=workflow,
        cost_governance=inputs["cost_governance"],
        source_trust=inputs["source_trust"],
        model_risk=inputs["model_risk"],
        procurement_risk=inputs["procurement_risk"],
    )
    pack = container.proposal_agent_council.pack(
        trace_id,
        council,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "proposal.agent_council_pack_generated",
        "proposal_agent_council_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "transcript_artifact_path": pack.transcript_artifact_path,
            "status": pack.council.status,
            "agents": len(pack.council.agents),
            "turns": len(pack.council.conversation),
        },
    )
    return pack


@router.get(
    "/proposal/decision-provenance",
    response_model=ProposalDecisionProvenanceResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_decision_provenance(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ProposalDecisionProvenanceResponse:
    trace_id = get_trace_id(request)
    inputs = await _buyer_intelligence_inputs(trace_id, container)
    workflow = container.buyer_intelligence.workflow(trace_id=f"{trace_id}-workflow", **inputs)
    replay = container.buyer_intelligence.replay(f"{trace_id}-replay", workflow)
    council = container.proposal_agent_council.council(
        trace_id=f"{trace_id}-council",
        workflow=workflow,
        cost_governance=inputs["cost_governance"],
        source_trust=inputs["source_trust"],
        model_risk=inputs["model_risk"],
        procurement_risk=inputs["procurement_risk"],
    )
    provenance = container.decision_provenance.provenance(
        trace_id=trace_id,
        workflow=workflow,
        replay=replay,
        council=council,
        cost_governance=inputs["cost_governance"],
        source_trust=inputs["source_trust"],
        model_risk=inputs["model_risk"],
        procurement_risk=inputs["procurement_risk"],
    )
    container.audit.record(
        trace_id,
        "proposal.decision_provenance_viewed",
        "proposal_decision_provenance",
        metadata={
            "status": provenance.status,
            "nodes": len(provenance.nodes),
            "edges": len(provenance.edges),
            "controls": len(provenance.decision_controls),
        },
    )
    return provenance


@router.post(
    "/proposal/decision-provenance-pack",
    response_model=ProposalDecisionProvenancePackResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_decision_provenance_pack(
    request: Request,
    payload: ProposalDecisionProvenancePackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ProposalDecisionProvenancePackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ProposalDecisionProvenancePackRequest()
    inputs = await _buyer_intelligence_inputs(trace_id, container)
    workflow = container.buyer_intelligence.workflow(trace_id=f"{trace_id}-workflow", **inputs)
    replay = container.buyer_intelligence.replay(f"{trace_id}-replay", workflow)
    council = container.proposal_agent_council.council(
        trace_id=f"{trace_id}-council",
        workflow=workflow,
        cost_governance=inputs["cost_governance"],
        source_trust=inputs["source_trust"],
        model_risk=inputs["model_risk"],
        procurement_risk=inputs["procurement_risk"],
    )
    provenance = container.decision_provenance.provenance(
        trace_id=f"{trace_id}-provenance",
        workflow=workflow,
        replay=replay,
        council=council,
        cost_governance=inputs["cost_governance"],
        source_trust=inputs["source_trust"],
        model_risk=inputs["model_risk"],
        procurement_risk=inputs["procurement_risk"],
    )
    pack = container.decision_provenance.pack(
        trace_id,
        provenance,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "proposal.decision_provenance_pack_generated",
        "proposal_decision_provenance_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": pack.provenance.status,
            "nodes": len(pack.provenance.nodes),
            "edges": len(pack.provenance.edges),
        },
    )
    return pack


@router.get(
    "/proposal/buyer-contracts",
    response_model=BuyerStructuredContractResponse,
    dependencies=[Depends(require_api_key)],
)
async def buyer_structured_contracts(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> BuyerStructuredContractResponse:
    trace_id = get_trace_id(request)
    outputs = await _buyer_structured_contract_outputs(trace_id, container)
    contract_audit = container.buyer_contracts.audit(trace_id=trace_id, **outputs)
    container.audit.record(
        trace_id,
        "proposal.buyer_contracts_viewed",
        "buyer_structured_contracts",
        metadata={
            "status": contract_audit.status,
            "score": contract_audit.score,
            "checks": len(contract_audit.checks),
            "roles": len(contract_audit.role_contracts),
        },
    )
    return contract_audit


@router.post(
    "/proposal/buyer-contracts-pack",
    response_model=BuyerStructuredContractPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def buyer_structured_contracts_pack(
    request: Request,
    payload: BuyerStructuredContractPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> BuyerStructuredContractPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or BuyerStructuredContractPackRequest()
    outputs = await _buyer_structured_contract_outputs(trace_id, container)
    contract_audit = container.buyer_contracts.audit(trace_id=f"{trace_id}-contracts", **outputs)
    pack = container.buyer_contracts.pack(
        trace_id,
        contract_audit,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "proposal.buyer_contracts_pack_generated",
        "buyer_structured_contracts_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": pack.contract_audit.status,
            "score": pack.contract_audit.score,
        },
    )
    return pack


@router.get(
    "/proposal/submission-certification",
    response_model=ProposalSubmissionCertificationResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_submission_certification(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ProposalSubmissionCertificationResponse:
    trace_id = get_trace_id(request)
    outputs = await _proposal_submission_certification_outputs(trace_id, container)
    certification = container.submission_certification.certify(trace_id=trace_id, **outputs)
    container.audit.record(
        trace_id,
        "proposal.submission_certification_viewed",
        "proposal_submission_certification",
        metadata={
            "status": certification.status,
            "score": certification.readiness_score,
            "gates": len(certification.gates),
            "reviewer_queue": len(certification.reviewer_queue),
        },
    )
    return certification


@router.post(
    "/proposal/submission-certification-pack",
    response_model=ProposalSubmissionCertificationPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_submission_certification_pack(
    request: Request,
    payload: ProposalSubmissionCertificationPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ProposalSubmissionCertificationPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ProposalSubmissionCertificationPackRequest()
    outputs = await _proposal_submission_certification_outputs(trace_id, container)
    certification = container.submission_certification.certify(trace_id=f"{trace_id}-certification", **outputs)
    pack = container.submission_certification.pack(
        trace_id,
        certification,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "proposal.submission_certification_pack_generated",
        "proposal_submission_certification_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": pack.certification.status,
            "score": pack.certification.readiness_score,
        },
    )
    return pack


@router.get(
    "/proposal/quality-benchmark",
    response_model=ProposalQualityBenchmarkResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_quality_benchmark(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ProposalQualityBenchmarkResponse:
    trace_id = get_trace_id(request)
    benchmark = await _proposal_quality_benchmark_report(trace_id, container)
    container.audit.record(
        trace_id,
        "proposal.quality_benchmark_viewed",
        "proposal_quality_benchmark",
        metadata={
            "status": benchmark.status,
            "score": benchmark.score,
            "scenarios": benchmark.scenario_count,
            "warnings": benchmark.warning_count,
            "failures": benchmark.failed_count,
        },
    )
    return benchmark


@router.post(
    "/proposal/quality-benchmark-pack",
    response_model=ProposalQualityBenchmarkPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_quality_benchmark_pack(
    request: Request,
    payload: ProposalQualityBenchmarkPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ProposalQualityBenchmarkPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ProposalQualityBenchmarkPackRequest()
    benchmark = await _proposal_quality_benchmark_report(
        trace_id,
        container,
        dataset_path=request_payload.dataset_path,
        outcomes_fixture_path=request_payload.outcomes_fixture_path,
        top_k=request_payload.top_k,
    )
    pack = container.proposal_benchmark.pack(
        trace_id,
        benchmark,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "proposal.quality_benchmark_pack_generated",
        "proposal_quality_benchmark_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": benchmark.status,
            "score": benchmark.score,
        },
    )
    return pack


@router.get(
    "/proposal/assurance-bundle",
    response_model=ProposalAssuranceBundleResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_assurance_bundle(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ProposalAssuranceBundleResponse:
    trace_id = get_trace_id(request)
    assurance = await _proposal_assurance_bundle_report(trace_id, container)
    container.audit.record(
        trace_id,
        "proposal.assurance_bundle_viewed",
        "proposal_assurance_bundle",
        metadata={
            "status": assurance.status,
            "score": assurance.score,
            "artifacts": assurance.control_summary["artifact_count"],
            "blocking": assurance.control_summary["blocking_count"],
        },
    )
    return assurance


@router.post(
    "/proposal/assurance-bundle-pack",
    response_model=ProposalAssuranceBundlePackResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_assurance_bundle_pack(
    request: Request,
    payload: ProposalAssuranceBundlePackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ProposalAssuranceBundlePackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ProposalAssuranceBundlePackRequest()
    assurance = await _proposal_assurance_bundle_report(
        trace_id,
        container,
        dataset_path=request_payload.dataset_path,
        outcomes_fixture_path=request_payload.outcomes_fixture_path,
        top_k=request_payload.top_k,
    )
    pack = container.proposal_assurance.pack(
        trace_id,
        assurance,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "proposal.assurance_bundle_pack_generated",
        "proposal_assurance_bundle_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": assurance.status,
            "score": assurance.score,
        },
    )
    return pack


@router.get(
    "/proposal/review-gate",
    response_model=ProposalReviewGateResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_review_gate(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ProposalReviewGateResponse:
    trace_id = get_trace_id(request)
    review_gate = await _proposal_review_gate_report(trace_id, container)
    container.audit.record(
        trace_id,
        "proposal.review_gate_viewed",
        "proposal_review_gate",
        metadata={
            "status": review_gate.status,
            "score": review_gate.score,
            "criteria": review_gate.summary["criterion_count"],
            "delegations": review_gate.summary["delegation_count"],
        },
    )
    return review_gate


@router.post(
    "/proposal/review-gate-pack",
    response_model=ProposalReviewGatePackResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_review_gate_pack(
    request: Request,
    payload: ProposalReviewGatePackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ProposalReviewGatePackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ProposalReviewGatePackRequest()
    review_gate = await _proposal_review_gate_report(
        trace_id,
        container,
        dataset_path=request_payload.dataset_path,
        outcomes_fixture_path=request_payload.outcomes_fixture_path,
        top_k=request_payload.top_k,
    )
    pack = container.proposal_review_gate.pack(
        trace_id,
        review_gate,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "proposal.review_gate_pack_generated",
        "proposal_review_gate_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": review_gate.status,
            "score": review_gate.score,
        },
    )
    return pack


@router.get(
    "/proposal/release-room",
    response_model=ProposalReleaseRoomResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_release_room(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ProposalReleaseRoomResponse:
    trace_id = get_trace_id(request)
    release_room = await _proposal_release_room_report(trace_id, container)
    container.audit.record(
        trace_id,
        "proposal.release_room_viewed",
        "proposal_release_room",
        metadata={
            "status": release_room.status,
            "score": release_room.readiness_score,
            "decisions": release_room.summary["decision_count"],
            "hitl_queue": release_room.summary["hitl_queue_count"],
        },
    )
    return release_room


@router.post(
    "/proposal/release-room-pack",
    response_model=ProposalReleaseRoomPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_release_room_pack(
    request: Request,
    payload: ProposalReleaseRoomPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ProposalReleaseRoomPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ProposalReleaseRoomPackRequest()
    release_room = await _proposal_release_room_report(
        trace_id,
        container,
        dataset_path=request_payload.dataset_path,
        outcomes_fixture_path=request_payload.outcomes_fixture_path,
        top_k=request_payload.top_k,
    )
    pack = container.proposal_release_room.pack(
        trace_id,
        release_room,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "proposal.release_room_pack_generated",
        "proposal_release_room_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": pack.release_room.status,
            "score": pack.release_room.readiness_score,
        },
    )
    return pack


@router.get(
    "/compliance/evidence-matrix",
    response_model=ComplianceEvidenceMatrixResponse,
    dependencies=[Depends(require_api_key)],
)
async def compliance_evidence_matrix(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ComplianceEvidenceMatrixResponse:
    trace_id = get_trace_id(request)
    analysis, matrix, review_findings = await _compliance_inputs(trace_id, container)
    result = container.compliance.evidence_matrix(
        trace_id,
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review_findings,
    )
    container.audit.record(
        trace_id,
        "compliance.evidence_matrix_viewed",
        "compliance_evidence_matrix",
        metadata={
            "control_families": result.coverage_summary["control_family_count"],
            "coverage_ratio": result.coverage_summary["coverage_ratio"],
            "unsupported_claims": result.coverage_summary["unsupported_claim_count"],
        },
    )
    return result


@router.post(
    "/compliance/control-pack",
    response_model=ControlPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def compliance_control_pack(
    request: Request,
    payload: ControlPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ControlPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ControlPackRequest()
    analysis, matrix, review_findings = await _compliance_inputs(trace_id, container)
    evidence_matrix = container.compliance.evidence_matrix(
        f"{trace_id}-matrix",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review_findings,
    )
    pack = container.compliance.control_pack(
        trace_id,
        evidence_matrix,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "compliance.control_pack_generated",
        "compliance_control_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "coverage_ratio": pack.matrix.coverage_summary["coverage_ratio"],
            "unsupported_claims": pack.matrix.coverage_summary["unsupported_claim_count"],
        },
    )
    return pack


@router.get(
    "/privacy/retention-guardrails",
    response_model=PrivacyRetentionGuardrailResponse,
    dependencies=[Depends(require_api_key)],
)
async def privacy_retention_guardrails(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> PrivacyRetentionGuardrailResponse:
    trace_id = get_trace_id(request)
    await _freshness_inputs(container)
    result = container.privacy_retention.guardrails(trace_id)
    container.audit.record(
        trace_id,
        "privacy.retention_guardrails_viewed",
        "privacy_retention_guardrails",
        metadata={
            "surfaces": result.summary["surface_count"],
            "high_risk": result.summary["high_risk_surface_count"],
            "missing_controls": result.summary["missing_control_count"],
        },
    )
    return result


@router.post(
    "/privacy/retention-pack",
    response_model=PrivacyRetentionPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def privacy_retention_pack(
    request: Request,
    payload: PrivacyRetentionPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> PrivacyRetentionPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or PrivacyRetentionPackRequest()
    await _freshness_inputs(container)
    guardrails = container.privacy_retention.guardrails(f"{trace_id}-guardrails")
    pack = container.privacy_retention.retention_pack(
        trace_id,
        guardrails,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "privacy.retention_pack_generated",
        "privacy_retention_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "surfaces": pack.guardrails.summary["surface_count"],
            "retention_actions": pack.guardrails.summary["retention_action_count"],
        },
    )
    return pack


@router.get(
    "/governance/model-risk-register",
    response_model=ModelRiskRegisterResponse,
    dependencies=[Depends(require_api_key)],
)
async def model_risk_register(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ModelRiskRegisterResponse:
    trace_id = get_trace_id(request)
    await _freshness_inputs(container)
    result = container.model_risk.register(trace_id)
    container.audit.record(
        trace_id,
        "governance.model_risk_register_viewed",
        "model_risk_register",
        metadata={
            "status": result.register_status,
            "risks": result.summary["risk_count"],
            "high_or_critical": result.summary["high_or_critical_count"],
            "needs_review": result.summary["needs_review_count"],
        },
    )
    return result


@router.post(
    "/governance/model-risk-pack",
    response_model=ModelRiskPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def model_risk_pack(
    request: Request,
    payload: ModelRiskPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ModelRiskPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ModelRiskPackRequest()
    await _freshness_inputs(container)
    register = container.model_risk.register(f"{trace_id}-model-risk")
    pack = container.model_risk.risk_pack(
        trace_id,
        register,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "governance.model_risk_pack_generated",
        "model_risk_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": pack.risk_register.register_status,
            "risks": pack.risk_register.summary["risk_count"],
        },
    )
    return pack


@router.get(
    "/governance/access-policy",
    response_model=AccessPolicyResponse,
    dependencies=[Depends(require_api_key)],
)
async def access_policy(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> AccessPolicyResponse:
    trace_id = get_trace_id(request)
    policy = await _access_policy_report(trace_id, container)
    container.audit.record(
        trace_id,
        "governance.access_policy_viewed",
        "access_policy",
        metadata={
            "status": policy.status,
            "roles": policy.summary["role_count"],
            "endpoint_policies": policy.summary["endpoint_policy_count"],
            "reviewer_queue": policy.summary["reviewer_queue_count"],
        },
    )
    return policy


@router.post(
    "/governance/access-policy-pack",
    response_model=AccessPolicyPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def access_policy_pack(
    request: Request,
    payload: AccessPolicyPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> AccessPolicyPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or AccessPolicyPackRequest()
    policy = request_payload.policy or await _access_policy_report(trace_id, container)
    pack = container.access_policy.pack(
        trace_id,
        policy,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "governance.access_policy_pack_generated",
        "access_policy_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": pack.policy.status,
            "roles": pack.policy.summary["role_count"],
        },
    )
    return pack


@router.get(
    "/procurement/question-risk",
    response_model=ProcurementQuestionRiskResponse,
    dependencies=[Depends(require_api_key)],
)
async def procurement_question_risk(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ProcurementQuestionRiskResponse:
    trace_id = get_trace_id(request)
    analysis, matrix, review_findings = await _procurement_inputs(trace_id, container)
    result = await container.procurement.question_risk(
        trace_id,
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review_findings,
    )
    container.audit.record(
        trace_id,
        "procurement.question_risk_viewed",
        "procurement_question_risk",
        metadata={
            "questions": result.coverage_summary["question_count"],
            "coverage_ratio": result.coverage_summary["coverage_ratio"],
            "blocked": result.approval_summary["blocked_count"],
            "approvals_required": result.approval_summary["approvals_required_count"],
        },
    )
    return result


@router.post(
    "/procurement/approval-pack",
    response_model=ProcurementApprovalPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def procurement_approval_pack(
    request: Request,
    payload: ProcurementApprovalPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ProcurementApprovalPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ProcurementApprovalPackRequest()
    analysis, matrix, review_findings = await _procurement_inputs(trace_id, container)
    question_risk = await container.procurement.question_risk(
        f"{trace_id}-question-risk",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review_findings,
    )
    pack = container.procurement.approval_pack(
        trace_id,
        question_risk,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "procurement.approval_pack_generated",
        "procurement_approval_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "blocked": pack.question_risk.approval_summary["blocked_count"],
            "approvals_required": pack.question_risk.approval_summary["approvals_required_count"],
        },
    )
    return pack


@router.get(
    "/procurement/risk-desk",
    response_model=ProcurementRiskDeskResponse,
    dependencies=[Depends(require_api_key)],
)
async def procurement_risk_desk(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ProcurementRiskDeskResponse:
    trace_id = get_trace_id(request)
    inputs = await _procurement_risk_desk_inputs(trace_id, container)
    result = await container.procurement_risk_desk.risk_desk(trace_id=trace_id, **inputs)
    container.audit.record(
        trace_id,
        "procurement.risk_desk_viewed",
        "procurement_risk_desk",
        metadata={
            "risks": result.summary["risk_count"],
            "critical": result.summary["critical_count"],
            "high": result.summary["high_count"],
            "blocked": result.summary["blocked_count"],
        },
    )
    return result


@router.post(
    "/procurement/risk-desk-pack",
    response_model=ProcurementRiskDeskPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def procurement_risk_desk_pack(
    request: Request,
    payload: ProcurementRiskDeskPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ProcurementRiskDeskPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ProcurementRiskDeskPackRequest()
    inputs = await _procurement_risk_desk_inputs(trace_id, container)
    risk_desk = await container.procurement_risk_desk.risk_desk(
        trace_id=f"{trace_id}-risk-desk",
        **inputs,
    )
    pack = container.procurement_risk_desk.risk_desk_pack(
        trace_id,
        risk_desk,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "procurement.risk_desk_pack_generated",
        "procurement_risk_desk_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "risks": pack.risk_desk.summary["risk_count"],
            "blocked": pack.risk_desk.summary["blocked_count"],
        },
    )
    return pack


@router.get(
    "/procurement/risk-decision-ledger",
    response_model=ProcurementRiskDecisionLedgerResponse,
    dependencies=[Depends(require_api_key)],
)
async def procurement_risk_decision_ledger(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ProcurementRiskDecisionLedgerResponse:
    trace_id = get_trace_id(request)
    inputs = await _procurement_risk_desk_inputs(trace_id, container)
    risk_desk = await container.procurement_risk_desk.risk_desk(
        trace_id=f"{trace_id}-risk-desk",
        **inputs,
    )
    ledger = container.procurement_risk_decisions.decision_ledger(trace_id, risk_desk)
    container.audit.record(
        trace_id,
        "procurement.risk_decision_ledger_viewed",
        "procurement_risk_decision_ledger",
        metadata={
            "decisions": ledger.summary["decision_count"],
            "pending": ledger.summary["pending_count"],
            "holds": ledger.summary["hold_submission_count"],
            "status": ledger.ledger_status,
        },
    )
    return ledger


@router.post(
    "/procurement/risk-decision-pack",
    response_model=ProcurementRiskDecisionPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def procurement_risk_decision_pack(
    request: Request,
    payload: ProcurementRiskDecisionPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ProcurementRiskDecisionPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ProcurementRiskDecisionPackRequest()
    risk_desk = request_payload.risk_desk
    if risk_desk is None:
        inputs = await _procurement_risk_desk_inputs(trace_id, container)
        risk_desk = await container.procurement_risk_desk.risk_desk(
            trace_id=f"{trace_id}-risk-desk",
            **inputs,
        )
    ledger = request_payload.ledger or container.procurement_risk_decisions.decision_ledger(
        trace_id,
        risk_desk,
        request_payload.decision_overrides,
    )
    pack = container.procurement_risk_decisions.decision_pack(
        trace_id,
        ledger,
        risk_desk,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "procurement.risk_decision_pack_generated",
        "procurement_risk_decision_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "decisions": pack.ledger.summary["decision_count"],
            "status": pack.ledger.ledger_status,
        },
    )
    return pack


@router.get(
    "/bid/scenario-analysis",
    response_model=BidScenarioAnalysisResponse,
    dependencies=[Depends(require_api_key)],
)
async def bid_scenario_analysis(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> BidScenarioAnalysisResponse:
    trace_id = get_trace_id(request)
    inputs = await _bid_inputs(trace_id, container)
    result = container.bid_simulator.scenario_analysis(trace_id=trace_id, **inputs)
    container.audit.record(
        trace_id,
        "bid.scenario_analysis_viewed",
        "bid_scenario_analysis",
        metadata={
            "scenarios": len(result.scenarios),
            "recommended_scenario_id": result.recommended_scenario_id,
            "best_roi": result.coverage_summary["best_risk_adjusted_roi"],
        },
    )
    return result


@router.post("/bid/roi-pack", response_model=BidRoiPackResponse, dependencies=[Depends(require_api_key)])
async def bid_roi_pack(
    payload: BidRoiPackRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> BidRoiPackResponse:
    trace_id = get_trace_id(request)
    analysis = payload.scenario_analysis
    if analysis is None:
        inputs = await _bid_inputs(f"{trace_id}-analysis", container)
        analysis = container.bid_simulator.scenario_analysis(trace_id=f"{trace_id}-analysis", **inputs)
    pack = container.bid_simulator.export_roi_pack(
        trace_id=trace_id,
        scenario_analysis=analysis,
        write_artifact=payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "bid.roi_pack_generated",
        "bid_roi_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "scenarios": len(analysis.scenarios),
            "recommended_scenario_id": analysis.recommended_scenario_id,
        },
    )
    return pack


@router.post(
    "/learning/win-loss",
    response_model=WinLossLearningResponse,
    dependencies=[Depends(require_api_key)],
)
async def win_loss_learning(
    request: Request,
    payload: WinLossLearningRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> WinLossLearningResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or WinLossLearningRequest()
    inputs = await _win_loss_inputs(request_payload, trace_id, container)
    try:
        result = container.win_loss_learning.learn(
            trace_id=trace_id,
            outcomes=request_payload.outcomes,
            outcomes_fixture_path=request_payload.outcomes_fixture_path,
            top_k_patterns=request_payload.top_k_patterns,
            **inputs,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    container.audit.record(
        trace_id,
        "learning.win_loss_analyzed",
        "win_loss_learning",
        metadata={
            "outcome_count": result.outcome_count,
            "win_rate": result.win_rate,
            "winning_patterns": len(result.winning_evidence_patterns),
            "losing_patterns": len(result.losing_risk_patterns),
        },
    )
    return result


@router.post(
    "/learning/win-loss-pack",
    response_model=WinLossStrategyPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def win_loss_strategy_pack(
    request: Request,
    payload: WinLossStrategyPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> WinLossStrategyPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or WinLossStrategyPackRequest()
    learning = request_payload.learning_response
    if learning is None:
        inputs = await _win_loss_inputs(request_payload, f"{trace_id}-learning", container)
        try:
            learning = container.win_loss_learning.learn(
                trace_id=f"{trace_id}-learning",
                outcomes=request_payload.outcomes,
                outcomes_fixture_path=request_payload.outcomes_fixture_path,
                top_k_patterns=request_payload.top_k_patterns,
                **inputs,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    pack = container.win_loss_learning.strategy_pack(
        trace_id=trace_id,
        learning=learning,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "learning.win_loss_pack_generated",
        "win_loss_strategy_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "outcome_count": learning.outcome_count,
            "win_rate": learning.win_rate,
        },
    )
    return pack


@router.post(
    "/learning/win-loss-eval-cases",
    response_model=WinLossEvalCaseResponse,
    dependencies=[Depends(require_api_key)],
)
async def win_loss_eval_cases(
    request: Request,
    payload: WinLossEvalCaseRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> WinLossEvalCaseResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or WinLossEvalCaseRequest()
    learning = request_payload.learning_response
    if learning is None:
        inputs = await _win_loss_inputs(request_payload, f"{trace_id}-learning", container)
        try:
            learning = container.win_loss_learning.learn(
                trace_id=f"{trace_id}-learning",
                outcomes=request_payload.outcomes,
                outcomes_fixture_path=request_payload.outcomes_fixture_path,
                top_k_patterns=request_payload.top_k_patterns,
                **inputs,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        plan = container.win_loss_eval_cases.compile_cases(
            trace_id=trace_id,
            learning=learning,
            eval_dataset_path=request_payload.eval_dataset_path,
            red_team_dataset_path=request_payload.red_team_dataset_path,
            max_cases_per_type=request_payload.max_cases_per_type,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    container.audit.record(
        trace_id,
        "learning.win_loss_eval_cases_compiled",
        "win_loss_eval_cases",
        metadata={
            "status": plan.status,
            "candidate_cases": plan.summary["candidate_case_count"],
            "eval_candidates": plan.dataset_patch["candidate_eval_cases"],
            "red_team_candidates": plan.dataset_patch["candidate_red_team_cases"],
        },
    )
    return plan


@router.post(
    "/learning/win-loss-eval-case-pack",
    response_model=WinLossEvalCasePackResponse,
    dependencies=[Depends(require_api_key)],
)
async def win_loss_eval_case_pack(
    request: Request,
    payload: WinLossEvalCasePackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> WinLossEvalCasePackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or WinLossEvalCasePackRequest()
    plan = request_payload.eval_case_plan
    if plan is None:
        learning = request_payload.learning_response
        if learning is None:
            inputs = await _win_loss_inputs(request_payload, f"{trace_id}-learning", container)
            try:
                learning = container.win_loss_learning.learn(
                    trace_id=f"{trace_id}-learning",
                    outcomes=request_payload.outcomes,
                    outcomes_fixture_path=request_payload.outcomes_fixture_path,
                    top_k_patterns=request_payload.top_k_patterns,
                    **inputs,
                )
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            plan = container.win_loss_eval_cases.compile_cases(
                trace_id=f"{trace_id}-eval-cases",
                learning=learning,
                eval_dataset_path=request_payload.eval_dataset_path,
                red_team_dataset_path=request_payload.red_team_dataset_path,
                max_cases_per_type=request_payload.max_cases_per_type,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    pack = container.win_loss_eval_cases.eval_case_pack(
        trace_id=trace_id,
        eval_case_plan=plan,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "learning.win_loss_eval_case_pack_generated",
        "win_loss_eval_case_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "candidate_eval_dataset_path": pack.candidate_eval_dataset_path,
            "candidate_red_team_dataset_path": pack.candidate_red_team_dataset_path,
        },
    )
    return pack


@router.post(
    "/learning/win-loss-policy",
    response_model=WinLossPolicyActivationResponse,
    dependencies=[Depends(require_api_key)],
)
async def win_loss_policy_activation(
    request: Request,
    payload: WinLossPolicyActivationRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> WinLossPolicyActivationResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or WinLossPolicyActivationRequest()
    await _freshness_inputs(container)
    try:
        learning, comparison = await _win_loss_policy_inputs(request_payload, trace_id, container)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    plan = container.win_loss_policy.activation_plan(
        trace_id=trace_id,
        learning=learning,
        retrieval_experiment=comparison,
        activation_mode=request_payload.activation_mode,
    )
    container.audit.record(
        trace_id,
        "learning.win_loss_policy_planned",
        "win_loss_policy_activation",
        metadata={
            "status": plan.status,
            "recommended_policy_id": plan.recommended_policy_id,
            "policy_rules": len(plan.policy_rules),
            "checkpoints": len(plan.checkpoints),
        },
    )
    return plan


@router.post(
    "/learning/win-loss-policy-pack",
    response_model=WinLossPolicyPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def win_loss_policy_pack(
    request: Request,
    payload: WinLossPolicyPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> WinLossPolicyPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or WinLossPolicyPackRequest()
    await _freshness_inputs(container)
    activation_plan = request_payload.activation_plan
    if activation_plan is None:
        try:
            learning, comparison = await _win_loss_policy_inputs(request_payload, f"{trace_id}-policy", container)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        activation_plan = container.win_loss_policy.activation_plan(
            trace_id=f"{trace_id}-policy",
            learning=learning,
            retrieval_experiment=comparison,
            activation_mode=request_payload.activation_mode,
        )
    pack = container.win_loss_policy.policy_pack(
        trace_id=trace_id,
        activation_plan=activation_plan,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "learning.win_loss_policy_pack_generated",
        "win_loss_policy_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": activation_plan.status,
            "policy_rules": len(activation_plan.policy_rules),
        },
    )
    return pack


@router.post(
    "/learning/win-loss-replay",
    response_model=WinLossReplayResponse,
    dependencies=[Depends(require_api_key)],
)
async def win_loss_replay(
    request: Request,
    payload: WinLossReplayRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> WinLossReplayResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or WinLossReplayRequest()
    try:
        learning, comparison = await _win_loss_policy_inputs(request_payload, trace_id, container)
        activation_plan = request_payload.activation_plan or container.win_loss_policy.activation_plan(
            trace_id=f"{trace_id}-policy",
            learning=learning,
            retrieval_experiment=comparison,
            activation_mode=request_payload.activation_mode,
        )
        replay = container.win_loss_replay.replay(
            trace_id=trace_id,
            learning=learning,
            activation_plan=activation_plan,
            retrieval_experiment=comparison,
            eval_dataset_path=request_payload.eval_dataset_path,
            red_team_dataset_path=request_payload.red_team_dataset_path,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    container.audit.record(
        trace_id,
        "learning.win_loss_replay_backtested",
        "win_loss_replay",
        metadata={
            "status": replay.status,
            "eval_cases": replay.replay_summary["eval_case_count"],
            "red_team_cases": replay.replay_summary["red_team_case_count"],
            "approval_required": replay.governance_decision["approval_required"],
        },
    )
    return replay


@router.post(
    "/learning/win-loss-replay-pack",
    response_model=WinLossReplayPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def win_loss_replay_pack(
    request: Request,
    payload: WinLossReplayPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> WinLossReplayPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or WinLossReplayPackRequest()
    try:
        replay = request_payload.replay
        if replay is None:
            learning, comparison = await _win_loss_policy_inputs(request_payload, f"{trace_id}-replay", container)
            activation_plan = request_payload.activation_plan or container.win_loss_policy.activation_plan(
                trace_id=f"{trace_id}-policy",
                learning=learning,
                retrieval_experiment=comparison,
                activation_mode=request_payload.activation_mode,
            )
            replay = container.win_loss_replay.replay(
                trace_id=f"{trace_id}-replay",
                learning=learning,
                activation_plan=activation_plan,
                retrieval_experiment=comparison,
                eval_dataset_path=request_payload.eval_dataset_path,
                red_team_dataset_path=request_payload.red_team_dataset_path,
            )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    pack = container.win_loss_replay.replay_pack(
        trace_id=trace_id,
        replay=replay,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "learning.win_loss_replay_pack_generated",
        "win_loss_replay_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": replay.status,
            "human_review_items": len(replay.human_review_queue),
        },
    )
    return pack


@router.get("/metrics/usage", response_model=UsageResponse, dependencies=[Depends(require_api_key)])
async def usage(container: ServiceContainer = Depends(get_container)) -> UsageResponse:
    return UsageResponse(metrics=container.metrics.list_metrics(), totals=container.metrics.totals())


@router.get(
    "/ops/proposal-observability",
    response_model=ProposalObservabilityResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_observability(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> ProposalObservabilityResponse:
    trace_id = get_trace_id(request)
    observability = await _proposal_observability_report(trace_id, container)
    container.audit.record(
        trace_id,
        "ops.proposal_observability_viewed",
        "proposal_observability",
        metadata={
            "status": observability.status,
            "trace_spans": observability.summary["trace_span_count"],
            "retrieval_diagnostics": observability.summary["retrieval_diagnostic_count"],
        },
    )
    return observability


@router.post(
    "/ops/proposal-observability-pack",
    response_model=ProposalObservabilityPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def proposal_observability_pack(
    request: Request,
    payload: ProposalObservabilityPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> ProposalObservabilityPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or ProposalObservabilityPackRequest()
    observability = await _proposal_observability_report(
        trace_id,
        container,
        dataset_path=request_payload.dataset_path,
        outcomes_fixture_path=request_payload.outcomes_fixture_path,
        top_k=request_payload.top_k,
    )
    pack = container.proposal_observability.pack(
        trace_id,
        observability,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "ops.proposal_observability_pack_generated",
        "proposal_observability_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "status": observability.status,
        },
    )
    return pack


@router.get(
    "/ops/trace-export",
    response_model=TraceExportResponse,
    dependencies=[Depends(require_api_key)],
)
async def trace_export(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> TraceExportResponse:
    trace_id = get_trace_id(request)
    request_payload = TraceExportRequest()
    observability = await _proposal_observability_report(
        trace_id=f"{trace_id}-observability",
        container=container,
        dataset_path=request_payload.dataset_path,
        outcomes_fixture_path=request_payload.outcomes_fixture_path,
        top_k=request_payload.top_k,
    )
    export = container.trace_export.export(
        trace_id=trace_id,
        observability=observability,
        dataset_path=request_payload.dataset_path,
        outcomes_fixture_path=request_payload.outcomes_fixture_path,
        top_k=request_payload.top_k,
    )
    container.audit.record(
        trace_id,
        "ops.trace_export_viewed",
        "trace_export",
        metadata={
            "status": export.status,
            "span_count": export.span_count,
            "diagnostics": export.retrieval_diagnostics["diagnostic_count"],
        },
    )
    return export


@router.post(
    "/ops/trace-export-pack",
    response_model=TraceExportPackResponse,
    dependencies=[Depends(require_api_key)],
)
async def trace_export_pack(
    request: Request,
    payload: TraceExportPackRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> TraceExportPackResponse:
    trace_id = get_trace_id(request)
    request_payload = payload or TraceExportPackRequest()
    export = request_payload.trace_export
    if export is None:
        observability = await _proposal_observability_report(
            trace_id=f"{trace_id}-observability",
            container=container,
            dataset_path=request_payload.dataset_path,
            outcomes_fixture_path=request_payload.outcomes_fixture_path,
            top_k=request_payload.top_k,
        )
        export = container.trace_export.export(
            trace_id=trace_id,
            observability=observability,
            dataset_path=request_payload.dataset_path,
            outcomes_fixture_path=request_payload.outcomes_fixture_path,
            top_k=request_payload.top_k,
        )
    pack = container.trace_export.pack(
        trace_id=trace_id,
        trace_export=export,
        write_artifact=request_payload.write_artifact,
    )
    container.audit.record(
        trace_id,
        "ops.trace_export_pack_generated",
        "trace_export_pack",
        resource_id=pack.artifact_path,
        metadata={
            "artifact_path": pack.artifact_path,
            "json_artifact_path": pack.json_artifact_path,
            "jsonl_artifact_path": pack.jsonl_artifact_path,
            "status": export.status,
            "span_count": export.span_count,
        },
    )
    return pack


@router.get("/audit/events", response_model=AuditResponse, dependencies=[Depends(require_api_key)])
async def audit_events(container: ServiceContainer = Depends(get_container)) -> AuditResponse:
    return AuditResponse(events=container.audit.list_events())


async def _proposal_observability_report(
    trace_id: str,
    container: ServiceContainer,
    dataset_path: str = "sample_data/eval_dataset.json",
    outcomes_fixture_path: str = "sample_data/rfp_outcomes.json",
    top_k: int = 4,
) -> ProposalObservabilityResponse:
    inputs = await _buyer_intelligence_inputs(f"{trace_id}-buyer", container)
    workflow = container.buyer_intelligence.workflow(trace_id=f"{trace_id}-workflow", **inputs)
    replay = container.buyer_intelligence.replay(f"{trace_id}-replay", workflow)
    council = container.proposal_agent_council.council(
        trace_id=f"{trace_id}-council",
        workflow=workflow,
        cost_governance=inputs["cost_governance"],
        source_trust=inputs["source_trust"],
        model_risk=inputs["model_risk"],
        procurement_risk=inputs["procurement_risk"],
    )
    provenance = container.decision_provenance.provenance(
        trace_id=f"{trace_id}-provenance",
        workflow=workflow,
        replay=replay,
        council=council,
        cost_governance=inputs["cost_governance"],
        source_trust=inputs["source_trust"],
        model_risk=inputs["model_risk"],
        procurement_risk=inputs["procurement_risk"],
    )
    retrieval_experiment = await container.retrieval_experiments.compare(
        trace_id=f"{trace_id}-retrieval-experiment",
        dataset_path=dataset_path,
        outcomes_fixture_path=outcomes_fixture_path,
        top_k=top_k,
    )
    return container.proposal_observability.report(
        trace_id=trace_id,
        workflow=workflow,
        replay=replay,
        council=council,
        provenance=provenance,
        retrieval_experiment=retrieval_experiment,
        cost_governance=inputs["cost_governance"],
        usage_metrics=container.metrics.list_metrics(),
        audit_events=container.audit.list_events(),
    )


async def _proposal_quality_benchmark_report(
    trace_id: str,
    container: ServiceContainer,
    dataset_path: str = "sample_data/eval_dataset.json",
    outcomes_fixture_path: str = "sample_data/rfp_outcomes.json",
    top_k: int = 4,
) -> ProposalQualityBenchmarkResponse:
    outputs = await _proposal_submission_certification_outputs(f"{trace_id}-certification", container)
    certification = container.submission_certification.certify(
        trace_id=f"{trace_id}-certification",
        **outputs,
    )
    observability = await _proposal_observability_report(
        f"{trace_id}-observability",
        container,
        dataset_path=dataset_path,
        outcomes_fixture_path=outcomes_fixture_path,
        top_k=top_k,
    )
    provider_resilience = container.provider_resilience.resilience(f"{trace_id}-provider-resilience")
    return container.proposal_benchmark.benchmark(
        trace_id=trace_id,
        certification=certification,
        observability=observability,
        provider_resilience=provider_resilience,
    )


async def _proposal_assurance_bundle_report(
    trace_id: str,
    container: ServiceContainer,
    dataset_path: str = "sample_data/eval_dataset.json",
    outcomes_fixture_path: str = "sample_data/rfp_outcomes.json",
    top_k: int = 4,
) -> ProposalAssuranceBundleResponse:
    inputs = await _buyer_intelligence_inputs(f"{trace_id}-assurance-buyer", container)
    workflow = container.buyer_intelligence.workflow(trace_id=f"{trace_id}-workflow", **inputs)
    replay = container.buyer_intelligence.replay(f"{trace_id}-replay", workflow)
    council = container.proposal_agent_council.council(
        trace_id=f"{trace_id}-council",
        workflow=workflow,
        cost_governance=inputs["cost_governance"],
        source_trust=inputs["source_trust"],
        model_risk=inputs["model_risk"],
        procurement_risk=inputs["procurement_risk"],
    )
    provenance = container.decision_provenance.provenance(
        trace_id=f"{trace_id}-provenance",
        workflow=workflow,
        replay=replay,
        council=council,
        cost_governance=inputs["cost_governance"],
        source_trust=inputs["source_trust"],
        model_risk=inputs["model_risk"],
        procurement_risk=inputs["procurement_risk"],
    )
    contract_audit = container.buyer_contracts.audit(
        trace_id=f"{trace_id}-contracts",
        workflow=workflow,
        replay=replay,
        council=council,
        provenance=provenance,
    )
    certification_outputs = await _proposal_submission_certification_outputs(
        f"{trace_id}-certification",
        container,
    )
    certification = container.submission_certification.certify(
        trace_id=f"{trace_id}-certification",
        **certification_outputs,
    )
    observability = await _proposal_observability_report(
        f"{trace_id}-observability",
        container,
        dataset_path=dataset_path,
        outcomes_fixture_path=outcomes_fixture_path,
        top_k=top_k,
    )
    provider_resilience = container.provider_resilience.resilience(f"{trace_id}-provider-resilience")
    benchmark = container.proposal_benchmark.benchmark(
        trace_id=f"{trace_id}-benchmark",
        certification=certification,
        observability=observability,
        provider_resilience=provider_resilience,
    )
    return container.proposal_assurance.bundle(
        trace_id=trace_id,
        workflow=workflow,
        replay=replay,
        contract_audit=contract_audit,
        council=council,
        provenance=provenance,
        certification=certification,
        observability=observability,
        benchmark=benchmark,
        provider_resilience=provider_resilience,
    )


async def _proposal_review_gate_report(
    trace_id: str,
    container: ServiceContainer,
    dataset_path: str = "sample_data/eval_dataset.json",
    outcomes_fixture_path: str = "sample_data/rfp_outcomes.json",
    top_k: int = 4,
) -> ProposalReviewGateResponse:
    assurance = await _proposal_assurance_bundle_report(
        f"{trace_id}-assurance",
        container,
        dataset_path=dataset_path,
        outcomes_fixture_path=outcomes_fixture_path,
        top_k=top_k,
    )
    observability = await _proposal_observability_report(
        f"{trace_id}-observability",
        container,
        dataset_path=dataset_path,
        outcomes_fixture_path=outcomes_fixture_path,
        top_k=top_k,
    )
    return container.proposal_review_gate.gate(
        trace_id=trace_id,
        assurance=assurance,
        observability=observability,
    )


async def _proposal_release_room_report(
    trace_id: str,
    container: ServiceContainer,
    dataset_path: str = "sample_data/eval_dataset.json",
    outcomes_fixture_path: str = "sample_data/rfp_outcomes.json",
    top_k: int = 4,
) -> ProposalReleaseRoomResponse:
    inputs = await _buyer_intelligence_inputs(f"{trace_id}-release-room-buyer", container)
    workflow = container.buyer_intelligence.workflow(trace_id=f"{trace_id}-workflow", **inputs)
    replay = container.buyer_intelligence.replay(f"{trace_id}-replay", workflow)
    council = container.proposal_agent_council.council(
        trace_id=f"{trace_id}-council",
        workflow=workflow,
        cost_governance=inputs["cost_governance"],
        source_trust=inputs["source_trust"],
        model_risk=inputs["model_risk"],
        procurement_risk=inputs["procurement_risk"],
    )
    provenance = container.decision_provenance.provenance(
        trace_id=f"{trace_id}-provenance",
        workflow=workflow,
        replay=replay,
        council=council,
        cost_governance=inputs["cost_governance"],
        source_trust=inputs["source_trust"],
        model_risk=inputs["model_risk"],
        procurement_risk=inputs["procurement_risk"],
    )
    contract_audit = container.buyer_contracts.audit(
        trace_id=f"{trace_id}-contracts",
        workflow=workflow,
        replay=replay,
        council=council,
        provenance=provenance,
    )
    certification = container.submission_certification.certify(
        trace_id=f"{trace_id}-certification",
        workflow=workflow,
        replay=replay,
        council=council,
        provenance=provenance,
        contract_audit=contract_audit,
    )
    observability = await _proposal_observability_report(
        f"{trace_id}-observability",
        container,
        dataset_path=dataset_path,
        outcomes_fixture_path=outcomes_fixture_path,
        top_k=top_k,
    )
    assurance = await _proposal_assurance_bundle_report(
        f"{trace_id}-assurance",
        container,
        dataset_path=dataset_path,
        outcomes_fixture_path=outcomes_fixture_path,
        top_k=top_k,
    )
    review_gate = container.proposal_review_gate.gate(
        trace_id=f"{trace_id}-review-gate",
        assurance=assurance,
        observability=observability,
    )
    provider_resilience = container.provider_resilience.resilience(f"{trace_id}-provider-resilience")
    return container.proposal_release_room.room(
        trace_id=trace_id,
        workflow=workflow,
        replay=replay,
        council=council,
        provenance=provenance,
        certification=certification,
        review_gate=review_gate,
        observability=observability,
        provider_resilience=provider_resilience,
    )


async def _access_policy_report(
    trace_id: str,
    container: ServiceContainer,
) -> AccessPolicyResponse:
    inputs = await _buyer_intelligence_inputs(f"{trace_id}-access-policy", container)
    workflow = container.buyer_intelligence.workflow(
        trace_id=f"{trace_id}-workflow",
        **inputs,
    )
    council = container.proposal_agent_council.council(
        trace_id=f"{trace_id}-council",
        workflow=workflow,
        cost_governance=inputs["cost_governance"],
        source_trust=inputs["source_trust"],
        model_risk=inputs["model_risk"],
        procurement_risk=inputs["procurement_risk"],
    )
    replay = container.buyer_intelligence.replay(f"{trace_id}-replay", workflow)
    provenance = container.decision_provenance.provenance(
        trace_id=f"{trace_id}-provenance",
        workflow=workflow,
        replay=replay,
        council=council,
        cost_governance=inputs["cost_governance"],
        source_trust=inputs["source_trust"],
        model_risk=inputs["model_risk"],
        procurement_risk=inputs["procurement_risk"],
    )
    contract_audit = container.buyer_contracts.audit(
        trace_id=f"{trace_id}-contracts",
        workflow=workflow,
        replay=replay,
        council=council,
        provenance=provenance,
    )
    certification = container.submission_certification.certify(
        trace_id=f"{trace_id}-certification",
        workflow=workflow,
        replay=replay,
        council=council,
        provenance=provenance,
        contract_audit=contract_audit,
    )
    return container.access_policy.policy(
        trace_id=trace_id,
        workflow=workflow,
        council=council,
        certification=certification,
        cost_governance=inputs["cost_governance"],
        model_risk=inputs["model_risk"],
    )


def _proposal_intake_triage(trace_id: str, container: ServiceContainer) -> ProposalIntakeTriageResponse:
    sample_path = container.settings.sample_data_dir / "acme_enterprise_rfp.md"
    if not sample_path.exists():
        raise HTTPException(status_code=404, detail="Sample RFP fixture not found: acme_enterprise_rfp.md")
    analysis = container.analysis.analyze(sample_path.read_text(encoding="utf-8"), f"{trace_id}-analysis")
    matrix = container.workbench.create_requirement_matrix(analysis)
    return container.proposal_intake.triage(
        trace_id=trace_id,
        analysis=analysis,
        requirement_matrix=matrix,
    )


async def _win_loss_inputs(
    payload: WinLossLearningRequest,
    trace_id: str,
    container: ServiceContainer,
) -> dict[str, object]:
    analysis = payload.analysis or payload.analyzed_payload
    matrix = payload.matrix or payload.requirement_matrix
    if analysis is None or matrix is None:
        sample_analysis, sample_matrix, _ = await _procurement_inputs(trace_id, container)
        analysis = analysis or sample_analysis
        matrix = matrix or sample_matrix
    if matrix is None and analysis is not None:
        matrix = container.workbench.create_requirement_matrix(analysis)
    win_strategy = payload.win_strategy
    if win_strategy is None and (analysis is not None or matrix):
        strategy_payload = WinStrategyRequest(
            analysis=analysis,
            matrix=matrix or [],
            customer_profile_id="regulated_healthcare",
            competitor_context=[
                "Incumbent competitor may bundle workflow tooling and use price pressure after procurement.",
            ],
        )
        strategy_inputs = _win_strategy_inputs(strategy_payload, f"{trace_id}-win-strategy", container)
        strategy_analysis, strategy_matrix, customer_fit, readiness, memory_matches, action_plan_items = strategy_inputs
        win_strategy = container.win_strategy.create_win_strategy(
            trace_id=f"{trace_id}-win-strategy",
            analysis=strategy_analysis,
            requirement_matrix=strategy_matrix,
            customer_fit=customer_fit,
            readiness_scorecard=readiness,
            response_memory_matches=memory_matches,
            action_plan=action_plan_items,
            competitor_context=strategy_payload.competitor_context,
        )
    return {
        "analysis": analysis,
        "requirement_matrix": matrix or [],
        "win_strategy": win_strategy,
        "eval_metrics": payload.eval_metrics,
    }


async def _win_loss_policy_inputs(
    payload: WinLossPolicyActivationRequest,
    trace_id: str,
    container: ServiceContainer,
) -> tuple[WinLossLearningResponse, RetrievalExperimentResponse]:
    learning = payload.learning_response
    if learning is None:
        inputs = await _win_loss_inputs(payload, f"{trace_id}-learning", container)
        learning = container.win_loss_learning.learn(
            trace_id=f"{trace_id}-learning",
            outcomes=payload.outcomes,
            outcomes_fixture_path=payload.outcomes_fixture_path,
            top_k_patterns=payload.top_k_patterns,
            **inputs,
        )
    comparison = payload.retrieval_experiment
    if comparison is None:
        comparison = await container.retrieval_experiments.compare(
            trace_id=f"{trace_id}-retrieval-experiment",
            dataset_path=payload.dataset_path,
            outcomes_fixture_path=payload.outcomes_fixture_path,
            top_k=payload.top_k,
            policy_ids=payload.policy_ids,
        )
    return learning, comparison


async def _buyer_intelligence_inputs(trace_id: str, container: ServiceContainer) -> dict[str, object]:
    analysis, matrix, review_findings = await _procurement_inputs(f"{trace_id}-proposal", container)
    freshness, conflicts, lineage = await _source_trust_inputs(f"{trace_id}-source-trust", container)
    source_trust = container.source_trust.trust_gate(
        f"{trace_id}-source-trust",
        freshness,
        conflicts,
        lineage,
    )
    model_risk = container.model_risk.register(f"{trace_id}-model-risk")
    procurement_risk = await container.procurement.question_risk(
        f"{trace_id}-procurement",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review_findings,
    )
    cost_governance = container.cost_governance.report(f"{trace_id}-cost-governance")
    return {
        "analysis": analysis,
        "requirement_matrix": matrix,
        "review_findings": review_findings,
        "cost_governance": cost_governance,
        "source_trust": source_trust,
        "model_risk": model_risk,
        "procurement_risk": procurement_risk,
    }


async def _buyer_structured_contract_outputs(trace_id: str, container: ServiceContainer) -> dict[str, object]:
    inputs = await _buyer_intelligence_inputs(trace_id, container)
    workflow = container.buyer_intelligence.workflow(trace_id=f"{trace_id}-workflow", **inputs)
    replay = container.buyer_intelligence.replay(f"{trace_id}-replay", workflow)
    council = container.proposal_agent_council.council(
        trace_id=f"{trace_id}-council",
        workflow=workflow,
        cost_governance=inputs["cost_governance"],
        source_trust=inputs["source_trust"],
        model_risk=inputs["model_risk"],
        procurement_risk=inputs["procurement_risk"],
    )
    provenance = container.decision_provenance.provenance(
        trace_id=f"{trace_id}-provenance",
        workflow=workflow,
        replay=replay,
        council=council,
        cost_governance=inputs["cost_governance"],
        source_trust=inputs["source_trust"],
        model_risk=inputs["model_risk"],
        procurement_risk=inputs["procurement_risk"],
    )
    return {
        "workflow": workflow,
        "replay": replay,
        "council": council,
        "provenance": provenance,
    }


async def _proposal_submission_certification_outputs(
    trace_id: str,
    container: ServiceContainer,
) -> dict[str, object]:
    outputs = await _buyer_structured_contract_outputs(trace_id, container)
    contract_audit = container.buyer_contracts.audit(trace_id=f"{trace_id}-contracts", **outputs)
    return {
        **outputs,
        "contract_audit": contract_audit,
    }


async def _compliance_inputs(
    trace_id: str,
    container: ServiceContainer,
) -> tuple[AnalyzeResponse, list[RequirementMatrixRow], list]:
    sample_docs = [
        ("sample_data/acme_enterprise_rfp.md", "rfp"),
        ("sample_data/security_policy.md", "security"),
        ("sample_data/compliance_policy.md", "compliance"),
        ("sample_data/dpa_privacy_policy.md", "privacy"),
        ("sample_data/sla_support_policy.md", "support"),
        ("sample_data/ai_governance_security.md", "security"),
        ("sample_data/disaster_recovery_plan.md", "disaster_recovery"),
        ("sample_data/customer_contract_terms.md", "contract"),
    ]
    loaded = {document.filename for document in container.repo.documents.values()}
    for fixture_path, document_type in sample_docs:
        filename = Path(fixture_path).name
        if filename not in loaded:
            await container.ingestion.ingest_path(fixture_path, document_type=document_type, source="sample_data")
            loaded.add(filename)
    rfp_doc = next(
        (
            document
            for document in container.repo.documents.values()
            if document.filename == "acme_enterprise_rfp.md"
        ),
        None,
    )
    if rfp_doc is not None:
        rfp_text = container.ingestion.get_text(rfp_doc.id)
    else:
        rfp_text = (container.settings.sample_data_dir / "acme_enterprise_rfp.md").read_text(encoding="utf-8")
    analysis = container.analysis.analyze(rfp_text, f"{trace_id}-analysis")
    matrix = container.workbench.create_requirement_matrix(analysis)
    review = container.review_board.review_package(
        trace_id=f"{trace_id}-review",
        requirement_matrix=matrix,
    )
    return analysis, matrix, review.findings


async def _freshness_inputs(container: ServiceContainer) -> None:
    sample_docs = [
        ("sample_data/acme_enterprise_rfp.md", "rfp"),
        ("sample_data/prior_proposal.md", "proposal"),
        ("sample_data/product_overview.md", "product"),
        ("sample_data/security_policy.md", "security"),
        ("sample_data/compliance_policy.md", "compliance"),
        ("sample_data/pricing_notes.md", "pricing"),
        ("sample_data/implementation_guide.md", "implementation"),
        ("sample_data/dpa_privacy_policy.md", "privacy"),
        ("sample_data/sla_support_policy.md", "support"),
        ("sample_data/ai_governance_security.md", "security"),
        ("sample_data/disaster_recovery_plan.md", "disaster_recovery"),
        ("sample_data/customer_success_onboarding.md", "customer_success"),
        ("sample_data/customer_contract_terms.md", "contract"),
    ]
    loaded = {document.filename for document in container.repo.documents.values()}
    for fixture_path, document_type in sample_docs:
        filename = Path(fixture_path).name
        if filename not in loaded:
            await container.ingestion.ingest_path(fixture_path, document_type=document_type, source="sample_data")
            loaded.add(filename)


async def _citation_lineage_inputs(trace_id: str, container: ServiceContainer) -> tuple[Answer, DraftResponse]:
    await _freshness_inputs(container)
    rfp_doc = next(
        (
            document
            for document in container.repo.documents.values()
            if document.filename == "acme_enterprise_rfp.md"
        ),
        None,
    )
    requirement_ids: list[str] = []
    if rfp_doc is not None:
        rfp_text = container.ingestion.get_text(rfp_doc.id)
        analysis = container.analysis.analyze(rfp_text, f"{trace_id}-analysis")
        requirement_ids = [requirement.id for requirement in analysis.requirements[:4]]
    answer = await container.generation.answer_question(
        "What SSO, encryption, audit logging, and reviewer controls are supported?",
        f"{trace_id}-answer",
        top_k=4,
    )
    draft = await container.generation.draft_response(
        f"{trace_id}-draft",
        requirement_ids=requirement_ids,
        section_names=["Security and Compliance", "Implementation Controls"],
        top_k=5,
    )
    return answer, draft


async def _source_trust_inputs(
    trace_id: str,
    container: ServiceContainer,
) -> tuple[EvidenceFreshnessResponse, EvidenceConflictResponse, CitationLineageAuditResponse]:
    await _freshness_inputs(container)
    freshness = container.evidence_freshness.freshness_report(f"{trace_id}-freshness")
    conflicts = container.evidence_conflicts.conflict_report(f"{trace_id}-conflicts")
    answer, draft = await _citation_lineage_inputs(f"{trace_id}-lineage-inputs", container)
    lineage = container.citation_lineage.audit(f"{trace_id}-lineage", answers=[answer], drafts=[draft])
    return freshness, conflicts, lineage


async def _procurement_inputs(
    trace_id: str,
    container: ServiceContainer,
) -> tuple[AnalyzeResponse, list[RequirementMatrixRow], list]:
    sample_docs = [
        ("sample_data/acme_enterprise_rfp.md", "rfp"),
        ("sample_data/security_policy.md", "security"),
        ("sample_data/compliance_policy.md", "compliance"),
        ("sample_data/pricing_notes.md", "pricing"),
        ("sample_data/implementation_guide.md", "implementation"),
        ("sample_data/dpa_privacy_policy.md", "privacy"),
        ("sample_data/sla_support_policy.md", "support"),
        ("sample_data/ai_governance_security.md", "security"),
        ("sample_data/disaster_recovery_plan.md", "disaster_recovery"),
        ("sample_data/customer_success_onboarding.md", "customer_success"),
        ("sample_data/customer_contract_terms.md", "contract"),
    ]
    loaded = {document.filename for document in container.repo.documents.values()}
    for fixture_path, document_type in sample_docs:
        filename = Path(fixture_path).name
        if filename not in loaded:
            await container.ingestion.ingest_path(fixture_path, document_type=document_type, source="sample_data")
            loaded.add(filename)
    rfp_doc = next(
        (
            document
            for document in container.repo.documents.values()
            if document.filename == "acme_enterprise_rfp.md"
        ),
        None,
    )
    if rfp_doc is not None:
        rfp_text = container.ingestion.get_text(rfp_doc.id)
    else:
        rfp_text = (container.settings.sample_data_dir / "acme_enterprise_rfp.md").read_text(encoding="utf-8")
    analysis = container.analysis.analyze(rfp_text, f"{trace_id}-analysis")
    matrix = container.workbench.create_requirement_matrix(analysis)
    review = container.review_board.review_package(
        trace_id=f"{trace_id}-review",
        requirement_matrix=matrix,
    )
    return analysis, matrix, review.findings


async def _procurement_risk_desk_inputs(trace_id: str, container: ServiceContainer) -> dict[str, object]:
    analysis, matrix, review_findings = await _procurement_inputs(trace_id, container)
    customer_fit = container.customer_intelligence.customer_fit(
        "regulated_healthcare",
        f"{trace_id}-customer-fit",
        analysis=analysis,
        requirement_matrix=matrix,
    )
    memory_matches = container.customer_intelligence.search_response_memory(
        "pricing data residency legal implementation procurement contract",
        f"{trace_id}-memory",
        customer_profile_id="regulated_healthcare",
        top_k=5,
    )
    action_plan, _ = container.action_plan.create_action_plan(
        trace_id=f"{trace_id}-action-plan",
        analysis=analysis,
        requirement_matrix=matrix,
        customer_fit=customer_fit,
        review_findings=review_findings,
    )
    readiness = container.deal_readiness.create_scorecard(
        trace_id=f"{trace_id}-readiness",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review_findings,
        customer_fit=customer_fit,
        action_plan=action_plan,
    )
    win_strategy = container.win_strategy.create_win_strategy(
        trace_id=f"{trace_id}-win-strategy",
        analysis=analysis,
        requirement_matrix=matrix,
        customer_fit=customer_fit,
        readiness_scorecard=readiness,
        response_memory_matches=memory_matches,
        action_plan=action_plan,
        review_findings=review_findings,
        competitor_context=[
            "Incumbent competitor may use discount pressure during procurement.",
        ],
    )
    contract_path = container.settings.sample_data_dir / "customer_contract_terms.md"
    contract_risk = container.contract_risk.analyze(
        contract_path.read_text(encoding="utf-8"),
        f"{trace_id}-contract-risk",
        customer_profile_id="regulated_healthcare",
    )
    procurement_risk = await container.procurement.question_risk(
        f"{trace_id}-question-risk",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review_findings,
    )
    return {
        "analysis": analysis,
        "requirement_matrix": matrix,
        "review_findings": review_findings,
        "contract_risk": contract_risk,
        "win_strategy": win_strategy,
        "procurement_risk": procurement_risk,
    }


async def _bid_inputs(trace_id: str, container: ServiceContainer) -> dict[str, object]:
    analysis, matrix, review_findings = await _procurement_inputs(trace_id, container)
    customer_fit = container.customer_intelligence.customer_fit(
        "regulated_healthcare",
        f"{trace_id}-customer-fit",
        analysis=analysis,
        requirement_matrix=matrix,
    )
    memory_matches = container.customer_intelligence.search_response_memory(
        "SSO encryption SOC 2 procurement pricing implementation",
        f"{trace_id}-memory",
        customer_profile_id="regulated_healthcare",
        top_k=5,
    )
    action_plan_items, _ = container.action_plan.create_action_plan(
        trace_id=f"{trace_id}-action-plan",
        analysis=analysis,
        requirement_matrix=matrix,
        customer_fit=customer_fit,
        review_findings=review_findings,
    )
    readiness = container.deal_readiness.create_scorecard(
        trace_id=f"{trace_id}-readiness",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review_findings,
        customer_fit=customer_fit,
        action_plan=action_plan_items,
    )
    win_strategy = container.win_strategy.create_win_strategy(
        trace_id=f"{trace_id}-win-strategy",
        analysis=analysis,
        requirement_matrix=matrix,
        customer_fit=customer_fit,
        readiness_scorecard=readiness,
        response_memory_matches=memory_matches,
        action_plan=action_plan_items,
        review_findings=review_findings,
        competitor_context=[
            "Incumbent competitor may bundle workflow tooling and push price-match pressure.",
        ],
    )
    contract_path = container.settings.sample_data_dir / "customer_contract_terms.md"
    contract_risk = container.contract_risk.analyze(
        contract_path.read_text(encoding="utf-8"),
        f"{trace_id}-contract-risk",
        customer_profile_id="regulated_healthcare",
    )
    evidence_gaps, _ = container.evidence_gap.create_gap_plan(
        trace_id=f"{trace_id}-evidence-gaps",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review_findings,
        readiness_scorecard=readiness,
        win_strategy=win_strategy,
        contract_risk=contract_risk,
        action_plan=action_plan_items,
    )
    source_pack = container.evidence_gap.export_source_request_pack(
        trace_id=f"{trace_id}-source-pack",
        gaps=evidence_gaps,
        analysis=analysis,
        readiness_scorecard=readiness,
        win_strategy=win_strategy,
        contract_risk=contract_risk,
        write_artifact=False,
    )
    timeline_plan = container.timeline_orchestration.create_plan(
        trace_id=f"{trace_id}-timeline",
        analysis=analysis,
        requirement_matrix=matrix,
        action_plan=action_plan_items,
        evidence_gaps=evidence_gaps,
        contract_risk=contract_risk,
        win_strategy=win_strategy,
        readiness_scorecard=readiness,
        source_request_pack=source_pack.pack,
        review_findings=review_findings,
    )
    draft = await container.generation.draft_response(
        trace_id=f"{trace_id}-draft",
        requirement_ids=[requirement.id for requirement in analysis.requirements],
        top_k=5,
    )
    submission_decision = container.submission_decision.create_decision(
        trace_id=f"{trace_id}-submission-decision",
        requirement_matrix=matrix,
        draft_response=draft,
        review_findings=review_findings,
        review_passed=not review_findings,
        action_plan=action_plan_items,
        readiness_scorecard=readiness,
        win_strategy=win_strategy,
        contract_risk=contract_risk,
        evidence_gaps=evidence_gaps,
        source_request_pack=source_pack.pack,
        timeline_plan=timeline_plan,
    )
    procurement_risk = await container.procurement.question_risk(
        f"{trace_id}-procurement-risk",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review_findings,
    )
    return {
        "requirement_matrix": matrix,
        "customer_profiles": container.customer_intelligence.list_profiles(),
        "readiness_scorecard": readiness,
        "win_strategy": win_strategy,
        "submission_decision": submission_decision,
        "evidence_gaps": evidence_gaps,
        "contract_risk": contract_risk,
        "timeline_plan": timeline_plan,
        "procurement_risk": procurement_risk,
    }


def _submission_decision_inputs(
    payload: SubmissionDecisionRequest | ExecutiveSubmissionMemoRequest,
    trace_id: str,
    container: ServiceContainer,
) -> dict:
    has_supplied_input = any(
        [
            payload.rfp_document_id,
            payload.analysis,
            payload.analyzed_payload,
            payload.matrix,
            payload.requirement_matrix,
            payload.draft_response,
            payload.answers,
            payload.review_findings,
            payload.action_plan,
            payload.readiness_scorecard,
            payload.eval_metrics,
            payload.red_team_summary,
            payload.win_strategy,
            payload.contract_risk,
            payload.evidence_gaps,
            payload.source_request_pack,
            payload.timeline_plan,
        ]
    )
    analysis = payload.analysis or payload.analyzed_payload
    if analysis is None and payload.rfp_document_id is not None:
        analysis = _analysis_from_document_id(payload.rfp_document_id, trace_id, container)
    if analysis is None and not has_supplied_input:
        sample_path = container.settings.sample_data_dir / "acme_enterprise_rfp.md"
        if sample_path.exists():
            analysis = container.analysis.analyze(sample_path.read_text(encoding="utf-8"), f"{trace_id}-sample")

    matrix = payload.matrix or payload.requirement_matrix
    if matrix is None and analysis is not None:
        matrix = container.workbench.create_requirement_matrix(analysis)
    matrix = matrix or []

    draft = payload.draft_response
    if draft is None and analysis is not None:
        draft = _draft_from_repo_or_sample(container, analysis, trace_id)

    review_findings = list(payload.review_findings)
    review_passed = payload.review_passed
    if not review_findings and matrix:
        review = container.review_board.review_package(
            trace_id=f"{trace_id}-review",
            requirement_matrix=matrix,
            draft_response=draft,
            answer_payloads=payload.answers,
        )
        review_findings = review.findings
        review_passed = review.passed

    action_plan_items = list(payload.action_plan)
    if not action_plan_items and matrix:
        action_plan_items, _ = container.action_plan.create_action_plan(
            trace_id=f"{trace_id}-action-plan",
            analysis=analysis,
            requirement_matrix=matrix,
            review_findings=review_findings,
        )

    readiness = payload.readiness_scorecard
    if readiness is None and (analysis is not None or matrix or review_findings or action_plan_items):
        readiness = container.deal_readiness.create_scorecard(
            trace_id=f"{trace_id}-readiness",
            analysis=analysis,
            requirement_matrix=matrix,
            review_findings=review_findings,
            action_plan=action_plan_items,
            eval_metrics=payload.eval_metrics,
        )

    strategy = payload.win_strategy
    if strategy is None and (analysis is not None or matrix):
        strategy = container.win_strategy.create_win_strategy(
            trace_id=f"{trace_id}-win-strategy",
            analysis=analysis,
            requirement_matrix=matrix,
            readiness_scorecard=readiness,
            action_plan=action_plan_items,
            review_findings=review_findings,
        )

    contract = payload.contract_risk
    if contract is None and not has_supplied_input:
        contract_path = container.settings.sample_data_dir / "customer_contract_terms.md"
        if contract_path.exists():
            contract = container.contract_risk.analyze(
                contract_path.read_text(encoding="utf-8"),
                f"{trace_id}-contract-risk",
            )

    gaps = payload.evidence_gaps
    if gaps is None:
        gaps, _ = container.evidence_gap.create_gap_plan(
            trace_id=f"{trace_id}-gaps",
            analysis=analysis,
            requirement_matrix=matrix,
            review_findings=review_findings,
            red_team_summary=payload.red_team_summary,
            readiness_scorecard=readiness,
            win_strategy=strategy,
            contract_risk=contract,
            action_plan=action_plan_items,
        )

    source_pack = payload.source_request_pack
    if source_pack is None:
        source_pack = container.evidence_gap.export_source_request_pack(
            trace_id=f"{trace_id}-source-pack",
            gaps=gaps,
            analysis=analysis,
            red_team_summary=payload.red_team_summary,
            readiness_scorecard=readiness,
            win_strategy=strategy,
            contract_risk=contract,
            write_artifact=False,
        ).pack

    timeline = payload.timeline_plan
    if timeline is None:
        timeline = container.timeline_orchestration.create_plan(
            trace_id=f"{trace_id}-timeline",
            analysis=analysis,
            requirement_matrix=matrix,
            action_plan=action_plan_items,
            evidence_gaps=gaps,
            contract_risk=contract,
            win_strategy=strategy,
            readiness_scorecard=readiness,
            source_request_pack=source_pack,
            leadership_brief=payload.leadership_brief,
            review_findings=review_findings,
            red_team_summary=payload.red_team_summary,
        )

    artifact_links = {
        "export_package": {
            "artifact_path": payload.export_artifact_path,
            "json_artifact_path": payload.export_json_artifact_path,
        },
        "source_request_pack": {
            "artifact_path": payload.source_request_artifact_path,
            "json_artifact_path": payload.source_request_json_artifact_path,
        },
        "submission_calendar": {
            "artifact_path": payload.submission_calendar_artifact_path,
            "json_artifact_path": payload.submission_calendar_json_artifact_path,
        },
        "leadership_brief": {
            "artifact_path": payload.leadership_brief_artifact_path,
            "json_artifact_path": payload.leadership_brief_json_artifact_path,
        },
    }
    artifact_links = {
        key: value
        for key, value in artifact_links.items()
        if any(path for path in value.values())
    }
    return {
        "requirement_matrix": matrix,
        "draft_response": draft,
        "answers": payload.answers,
        "review_findings": review_findings,
        "review_passed": review_passed,
        "action_plan": action_plan_items,
        "readiness_scorecard": readiness,
        "eval_metrics": payload.eval_metrics,
        "red_team_summary": payload.red_team_summary,
        "win_strategy": strategy,
        "contract_risk": contract,
        "evidence_gaps": gaps,
        "source_request_pack": source_pack,
        "timeline_plan": timeline,
        "leadership_brief": payload.leadership_brief,
        "metrics": payload.metrics or container.metrics.totals(),
        "artifact_links": artifact_links,
    }


def _draft_from_repo_or_sample(
    container: ServiceContainer,
    analysis: AnalyzeResponse,
    trace_id: str,
) -> DraftResponse:
    citations = []
    for row in container.workbench.create_requirement_matrix(analysis):
        for ref in row.evidence_refs:
            for chunk in container.repo.chunks.values():
                document = container.repo.documents.get(chunk.document_id)
                if document and document.filename == ref:
                    citations.append(
                        {
                            "document_id": document.id,
                            "chunk_id": chunk.id,
                            "filename": document.filename,
                            "page": None,
                            "snippet": chunk.text[:220],
                            "score": 0.75,
                        }
                    )
                    break
    return DraftResponse(
        sections=[
            {
                "title": "Executive Summary",
                "body": "Local deterministic draft assembled for final submission decision review.",
                "requirement_ids": [requirement.id for requirement in analysis.requirements[:4]],
            },
            {
                "title": "Security, Compliance, and Commercial Posture",
                "body": "Response posture is based on approved local evidence and explicit exception tracking.",
                "requirement_ids": [requirement.id for requirement in analysis.requirements[4:]],
            },
        ],
        citations=citations,
        risks=analysis.risks,
        assumptions=analysis.missing_information,
        revision_notes=["Generated locally for submission decision fallback."],
        trace_id=f"{trace_id}-draft-fallback",
    )


def _reviewer_collaboration_inputs(
    payload: (
        ReviewerCollaborationRequest
        | ReviewerCollaborationPackRequest
        | ReviewerCollaborationWorkflowRequest
        | ReviewerCollaborationWorkflowPackRequest
        | ReviewerSignoffLedgerRequest
        | ReviewerSignoffLedgerPackRequest
        | ReviewerEscalationRequest
        | ReviewerEscalationPackRequest
        | ReviewerTraceReconciliationRequest
        | ReviewerTraceReconciliationPackRequest
    ),
    trace_id: str,
    container: ServiceContainer,
) -> dict:
    has_supplied_input = any(
        [
            payload.rfp_document_id,
            payload.analysis,
            payload.analyzed_payload,
            payload.matrix,
            payload.requirement_matrix,
            payload.draft_response,
            payload.review_findings,
            payload.action_plan,
            payload.evidence_gaps,
            payload.contract_risk,
            payload.submission_decision,
        ]
    )
    analysis = payload.analysis or payload.analyzed_payload
    if analysis is None and payload.rfp_document_id is not None:
        analysis = _analysis_from_document_id(payload.rfp_document_id, trace_id, container)
    if analysis is None and not has_supplied_input:
        sample_path = container.settings.sample_data_dir / "acme_enterprise_rfp.md"
        if sample_path.exists():
            analysis = container.analysis.analyze(sample_path.read_text(encoding="utf-8"), f"{trace_id}-sample")

    matrix = payload.matrix or payload.requirement_matrix
    if matrix is None and analysis is not None:
        matrix = container.workbench.create_requirement_matrix(analysis)
    matrix = matrix or []

    draft = payload.draft_response
    if draft is None and analysis is not None:
        draft = _draft_from_repo_or_sample(container, analysis, trace_id)

    review_findings = list(payload.review_findings)
    review_passed = payload.review_passed
    if not review_findings and (matrix or draft is not None):
        review = container.review_board.review_package(
            trace_id=f"{trace_id}-review",
            requirement_matrix=matrix,
            draft_response=draft,
        )
        review_findings = review.findings
        review_passed = review.passed

    action_plan_items = list(payload.action_plan)
    if not action_plan_items and matrix:
        action_plan_items, _ = container.action_plan.create_action_plan(
            trace_id=f"{trace_id}-action-plan",
            analysis=analysis,
            requirement_matrix=matrix,
            review_findings=review_findings,
        )

    contract = payload.contract_risk
    if contract is None and not has_supplied_input:
        contract_path = container.settings.sample_data_dir / "customer_contract_terms.md"
        if contract_path.exists():
            contract = container.contract_risk.analyze(
                contract_path.read_text(encoding="utf-8"),
                f"{trace_id}-contract-risk",
                customer_profile_id="regulated_healthcare",
            )

    gaps = payload.evidence_gaps
    if gaps is None and (analysis is not None or matrix or review_findings or action_plan_items):
        readiness = container.deal_readiness.create_scorecard(
            trace_id=f"{trace_id}-readiness",
            analysis=analysis,
            requirement_matrix=matrix,
            review_findings=review_findings,
            action_plan=action_plan_items,
        )
        strategy = container.win_strategy.create_win_strategy(
            trace_id=f"{trace_id}-win-strategy",
            analysis=analysis,
            requirement_matrix=matrix,
            readiness_scorecard=readiness,
            action_plan=action_plan_items,
            review_findings=review_findings,
        )
        gaps, _ = container.evidence_gap.create_gap_plan(
            trace_id=f"{trace_id}-gaps",
            analysis=analysis,
            requirement_matrix=matrix,
            review_findings=review_findings,
            readiness_scorecard=readiness,
            win_strategy=strategy,
            contract_risk=contract,
            action_plan=action_plan_items,
        )

    return {
        "requirement_matrix": matrix,
        "draft_response": draft,
        "review_findings": review_findings,
        "review_passed": review_passed,
        "action_plan": action_plan_items,
        "evidence_gaps": gaps or [],
        "contract_risk": contract,
        "submission_decision": payload.submission_decision,
    }


def _reviewer_trace_inputs(
    payload: ReviewerTraceReconciliationRequest | ReviewerTraceReconciliationPackRequest,
    trace_id: str,
    container: ServiceContainer,
):
    collaboration = payload.collaboration
    if collaboration is None:
        inputs = _reviewer_collaboration_inputs(payload, trace_id, container)
        collaboration = container.reviewer_collaboration.create_board(
            trace_id=f"{trace_id}-collaboration",
            **inputs,
        )
    workflow = payload.workflow or container.reviewer_workflow.build_workflow(
        trace_id=f"{trace_id}-workflow",
        collaboration=collaboration,
    )
    ledger = payload.ledger or container.reviewer_signoff.ledger(
        trace_id=f"{trace_id}-ledger",
        collaboration=collaboration,
        workflow=workflow,
        signoff_overrides=payload.signoff_overrides,
    )
    escalation = payload.escalation or container.reviewer_escalation.escalation_plan(
        trace_id=f"{trace_id}-escalation",
        collaboration=collaboration,
        workflow=workflow,
        ledger=ledger,
        sla_hours=payload.sla_hours,
    )
    return collaboration, workflow, ledger, escalation


def _timeline_inputs(
    payload: TimelinePlanRequest | SubmissionCalendarPackRequest,
    trace_id: str,
    container: ServiceContainer,
):
    (
        analysis,
        matrix,
        review_findings,
        red_team_summary,
        readiness,
        strategy,
        contract,
        action_plan_items,
    ) = _evidence_gap_inputs(payload, trace_id, container)
    gaps = payload.evidence_gaps
    if gaps is None:
        gaps, _ = container.evidence_gap.create_gap_plan(
            trace_id=f"{trace_id}-gaps",
            analysis=analysis,
            requirement_matrix=matrix,
            review_findings=review_findings,
            red_team_summary=red_team_summary,
            readiness_scorecard=readiness,
            win_strategy=strategy,
            contract_risk=contract,
            action_plan=action_plan_items,
        )
    source_pack = payload.source_request_pack
    if source_pack is None:
        source_pack = container.evidence_gap.export_source_request_pack(
            trace_id=f"{trace_id}-source-pack",
            gaps=gaps,
            analysis=analysis,
            red_team_summary=red_team_summary,
            readiness_scorecard=readiness,
            win_strategy=strategy,
            contract_risk=contract,
            write_artifact=False,
        ).pack
    leadership = payload.leadership_brief
    if leadership is None:
        leadership = container.leadership_brief.export_brief(
            trace_id=f"{trace_id}-leadership",
            documents_ingested=len(container.repo.documents),
            analysis=analysis,
            requirement_matrix=matrix,
            review_findings=review_findings,
            action_plan=action_plan_items,
            readiness_scorecard=readiness,
            red_team_summary=red_team_summary,
            write_artifact=False,
        ).brief
    return (
        analysis,
        matrix,
        review_findings,
        red_team_summary,
        readiness,
        strategy,
        contract,
        action_plan_items,
        gaps,
        source_pack,
        leadership,
    )


def _evidence_gap_inputs(
    payload: EvidenceGapRequest | SourceRequestPackRequest,
    trace_id: str,
    container: ServiceContainer,
) -> tuple[
    AnalyzeResponse | None,
    list[RequirementMatrixRow],
    list,
    dict | None,
    DealReadinessScorecardResponse | None,
    WinStrategyResponse | None,
    ContractRiskResponse | None,
    list,
]:
    has_supplied_input = any(
        [
            payload.rfp_document_id,
            payload.analysis,
            payload.analyzed_payload,
            payload.matrix,
            payload.requirement_matrix,
            payload.review_findings,
            payload.red_team_summary,
            payload.readiness_scorecard,
            payload.win_strategy,
            payload.contract_risk,
            payload.action_plan,
        ]
    )
    analysis = payload.analysis or payload.analyzed_payload
    if analysis is None and payload.rfp_document_id is not None:
        analysis = _analysis_from_document_id(payload.rfp_document_id, trace_id, container)
    if analysis is None and not has_supplied_input:
        sample_path = container.settings.sample_data_dir / "acme_enterprise_rfp.md"
        if sample_path.exists():
            analysis = container.analysis.analyze(sample_path.read_text(encoding="utf-8"), f"{trace_id}-sample")

    matrix = payload.matrix or payload.requirement_matrix
    if matrix is None and analysis is not None:
        matrix = container.workbench.create_requirement_matrix(analysis)
    matrix = matrix or []

    review_findings = list(payload.review_findings)
    if not review_findings and matrix:
        review = container.review_board.review_package(
            trace_id=f"{trace_id}-review",
            requirement_matrix=matrix,
        )
        review_findings = review.findings

    action_plan_items = list(payload.action_plan)
    if not action_plan_items and matrix:
        action_plan_items, _ = container.action_plan.create_action_plan(
            trace_id=f"{trace_id}-action-plan",
            analysis=analysis,
            requirement_matrix=matrix,
            review_findings=review_findings,
        )

    readiness = payload.readiness_scorecard
    if readiness is None and (analysis is not None or matrix or review_findings or action_plan_items):
        readiness = container.deal_readiness.create_scorecard(
            trace_id=f"{trace_id}-readiness",
            analysis=analysis,
            requirement_matrix=matrix,
            review_findings=review_findings,
            action_plan=action_plan_items,
        )

    strategy = payload.win_strategy
    if strategy is None and (analysis is not None or matrix):
        strategy = container.win_strategy.create_win_strategy(
            trace_id=f"{trace_id}-win-strategy",
            analysis=analysis,
            requirement_matrix=matrix,
            readiness_scorecard=readiness,
            action_plan=action_plan_items,
            review_findings=review_findings,
        )

    contract = payload.contract_risk
    if contract is None and not has_supplied_input:
        contract_path = container.settings.sample_data_dir / "customer_contract_terms.md"
        if contract_path.exists():
            contract = container.contract_risk.analyze(
                contract_path.read_text(encoding="utf-8"),
                f"{trace_id}-contract-risk",
            )

    return (
        analysis,
        matrix,
        review_findings,
        payload.red_team_summary,
        readiness,
        strategy,
        contract,
        action_plan_items,
    )


def _analysis_from_workbench_payload(
    payload: (
        RequirementMatrixRequest
        | ExportPackageRequest
        | ReviewPackageRequest
        | CustomerFitRequest
        | ActionPlanRequest
        | LeadershipBriefRequest
        | AnswerReuseCoverageRequest
        | AnswerReuseCoveragePackRequest
    ),
    trace_id: str,
    container: ServiceContainer,
) -> AnalyzeResponse:
    if payload.analyzed_payload is not None:
        return payload.analyzed_payload
    if payload.rfp_document_id is None:
        raise HTTPException(status_code=400, detail="Provide analyzed_payload or rfp_document_id.")
    if payload.rfp_document_id not in container.repo.documents:
        raise HTTPException(status_code=404, detail=f"RFP document not found: {payload.rfp_document_id}")
    text = container.ingestion.get_text(payload.rfp_document_id)
    return container.analysis.analyze(text, trace_id)


def _contract_text_from_payload(payload: ContractRiskRequest, container: ServiceContainer) -> str:
    if payload.text:
        return payload.text
    if payload.contract_document_id:
        if payload.contract_document_id not in container.repo.documents:
            raise HTTPException(status_code=404, detail=f"Contract document not found: {payload.contract_document_id}")
        return container.ingestion.get_text(payload.contract_document_id)
    if payload.fixture_path:
        path = Path(payload.fixture_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            sample_path = container.settings.sample_data_dir / payload.fixture_path
            if sample_path.exists():
                path = sample_path
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Contract fixture not found: {payload.fixture_path}")
        return path.read_text(encoding="utf-8")
    raise HTTPException(status_code=400, detail="Provide text, contract_document_id, or fixture_path.")


def _action_plan_inputs(
    payload: ActionPlanRequest,
    trace_id: str,
    container: ServiceContainer,
) -> tuple[AnalyzeResponse | None, list[RequirementMatrixRow], CustomerProfile | None, CustomerFitResponse | None]:
    analysis = None
    if payload.analyzed_payload is not None or payload.rfp_document_id is not None:
        analysis = _analysis_from_workbench_payload(payload, trace_id, container)
    matrix = payload.requirement_matrix
    if matrix is None and analysis is not None:
        matrix = container.workbench.create_requirement_matrix(analysis)
    if matrix is None:
        raise HTTPException(status_code=400, detail="Provide analyzed_payload, rfp_document_id, or requirement_matrix.")

    customer_profile = payload.customer_profile
    customer_fit = payload.customer_fit
    if payload.customer_profile_id:
        try:
            customer_profile = container.customer_intelligence.get_profile(payload.customer_profile_id)
            if customer_fit is None:
                customer_fit = container.customer_intelligence.customer_fit(
                    payload.customer_profile_id,
                    trace_id,
                    analysis=analysis,
                    requirement_matrix=matrix,
                )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return analysis, matrix, customer_profile, customer_fit


def _readiness_inputs(
    payload: DealReadinessScorecardRequest,
    container: ServiceContainer,
) -> tuple[AnalyzeResponse | None, list[RequirementMatrixRow]]:
    analysis = payload.analysis or payload.analyzed_payload
    matrix = payload.matrix or payload.requirement_matrix
    if matrix is None and analysis is not None:
        matrix = container.workbench.create_requirement_matrix(analysis)
    if not any(
        [
            analysis,
            matrix,
            payload.review_findings,
            payload.customer_fit,
            payload.action_plan,
            payload.eval_metrics,
        ]
    ):
        raise HTTPException(
            status_code=400,
            detail="Provide analysis, matrix, review findings, customer fit, action plan, or eval metrics.",
        )
    return analysis, matrix or []


def _amendment_impact_inputs(
    payload: RfpAmendmentImpactRequest,
    trace_id: str,
    container: ServiceContainer,
) -> tuple[AnalyzeResponse, AnalyzeResponse, list[RequirementMatrixRow]]:
    baseline_analysis = payload.baseline_analysis or payload.analysis or payload.analyzed_payload
    if baseline_analysis is None:
        baseline_analysis = _analysis_from_text_or_fixture(
            trace_id=f"{trace_id}-baseline",
            text=payload.baseline_text,
            fixture_path=payload.baseline_fixture_path,
            container=container,
            label="baseline RFP",
        )
    revised_analysis = payload.revised_analysis
    if revised_analysis is None:
        revised_analysis = _analysis_from_text_or_fixture(
            trace_id=f"{trace_id}-revised",
            text=payload.revised_text,
            fixture_path=payload.revised_fixture_path,
            container=container,
            label="revised RFP",
        )
    matrix = payload.baseline_matrix or payload.matrix or payload.requirement_matrix
    if matrix is None:
        matrix = container.workbench.create_requirement_matrix(baseline_analysis)
    return baseline_analysis, revised_analysis, matrix


def _analysis_from_text_or_fixture(
    trace_id: str,
    text: str | None,
    fixture_path: str | None,
    container: ServiceContainer,
    label: str,
) -> AnalyzeResponse:
    if text:
        return container.analysis.analyze(text, trace_id)
    if not fixture_path:
        raise HTTPException(status_code=400, detail=f"Provide {label} text, fixture path, or analysis.")
    path = Path(fixture_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        sample_path = container.settings.sample_data_dir / fixture_path
        if sample_path.exists():
            path = sample_path
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{label.title()} fixture not found: {fixture_path}")
    return container.analysis.analyze(path.read_text(encoding="utf-8"), trace_id)


def _win_strategy_inputs(
    payload: WinStrategyRequest,
    trace_id: str,
    container: ServiceContainer,
) -> tuple[
    AnalyzeResponse | None,
    list[RequirementMatrixRow],
    CustomerFitResponse | None,
    DealReadinessScorecardResponse | None,
    list[ResponseMemoryMatch],
    list,
]:
    analysis = payload.analysis or payload.analyzed_payload
    if analysis is None and payload.rfp_document_id is not None:
        analysis = _analysis_from_document_id(payload.rfp_document_id, trace_id, container)
    if analysis is None and not (payload.matrix or payload.requirement_matrix):
        sample_path = container.settings.sample_data_dir / "acme_enterprise_rfp.md"
        if sample_path.exists():
            analysis = container.analysis.analyze(sample_path.read_text(encoding="utf-8"), trace_id)

    matrix = payload.matrix or payload.requirement_matrix
    if matrix is None and analysis is not None:
        matrix = container.workbench.create_requirement_matrix(analysis)
    matrix = matrix or []

    customer_fit = payload.customer_fit
    profile_id = payload.customer_profile_id
    if profile_id is None and (analysis is not None or matrix):
        profile_id = "regulated_healthcare"
    if customer_fit is None and profile_id and (analysis is not None or matrix):
        try:
            customer_fit = container.customer_intelligence.customer_fit(
                profile_id,
                f"{trace_id}-customer-fit",
                analysis=analysis,
                requirement_matrix=matrix,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    memory_matches = list(payload.response_memory_matches)
    if not memory_matches and (analysis is not None or matrix):
        memory_query = _win_strategy_memory_query(analysis, matrix)
        memory_matches = container.customer_intelligence.search_response_memory(
            memory_query,
            f"{trace_id}-response-memory",
            customer_profile_id=profile_id,
            top_k=5,
        )

    action_plan_items = list(payload.action_plan)
    if not action_plan_items and matrix:
        action_plan_items, _ = container.action_plan.create_action_plan(
            trace_id=f"{trace_id}-action-plan",
            analysis=analysis,
            requirement_matrix=matrix,
            customer_fit=customer_fit,
            review_findings=payload.review_findings,
        )

    readiness = payload.readiness_scorecard
    if readiness is None and (analysis is not None or matrix or customer_fit is not None or action_plan_items):
        readiness = container.deal_readiness.create_scorecard(
            trace_id=f"{trace_id}-readiness",
            analysis=analysis,
            requirement_matrix=matrix,
            review_findings=payload.review_findings,
            customer_fit=customer_fit,
            action_plan=action_plan_items,
        )
    return analysis, matrix, customer_fit, readiness, memory_matches, action_plan_items


def _analysis_from_document_id(
    document_id: str,
    trace_id: str,
    container: ServiceContainer,
) -> AnalyzeResponse:
    if document_id not in container.repo.documents:
        raise HTTPException(status_code=404, detail=f"RFP document not found: {document_id}")
    text = container.ingestion.get_text(document_id)
    return container.analysis.analyze(text, trace_id)


def _win_strategy_memory_query(
    analysis: AnalyzeResponse | None,
    matrix: list[RequirementMatrixRow],
) -> str:
    parts = [row.requirement_text for row in matrix]
    if analysis:
        parts.extend(analysis.security_questions)
        parts.extend(analysis.compliance_asks)
        parts.extend(analysis.pricing_mentions)
    return " ".join(parts) or "SSO encryption SOC 2 implementation pricing"
