from pathlib import Path

import pytest

from app.core.config import get_settings
from app.evals.run_red_team import _run as run_red_team
from app.models.api import AnalyzeResponse, EvaluationMetrics, SubmissionRegressionRequest
from app.models.domain import (
    CustomerProfile,
    DraftResponse,
    DraftSection,
    EvidenceGap,
    RequirementMatrixRow,
    ReviewFinding,
    RfpRequirement,
    StakeholderTask,
    TokenUsage,
)
from app.providers.mock import MockLLMProvider
from app.repositories.memory import repository
from app.services.action_plan import StakeholderActionPlanService
from app.services.container import get_container
from app.services.contract_risk import ContractRiskService
from app.services.deal_readiness import DealReadinessService
from app.services.evidence_gap import EvidenceGapService
from app.services.leadership_brief import LeadershipBriefService
from app.services.metrics import MetricsService
from app.services.review_board import RfpReviewBoardService
from app.services.submission_decision import SubmissionDecisionService
from app.services.timeline_orchestration import TimelineOrchestrationService


@pytest.mark.asyncio
async def test_service_boundaries_ingest_retrieve_generate_and_measure(tmp_path, monkeypatch):
    monkeypatch.setenv("API_KEY", "service-test-key")
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setenv("VECTOR_STORE_MODE", "qdrant")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    get_container.cache_clear()
    repository.reset()

    container = get_container()
    document, chunks = await container.ingestion.ingest_path(
        "sample_data/security_policy.md",
        document_type="knowledge_base",
        source="test",
        tags=["security"],
    )
    assert document.id in container.repo.documents
    assert chunks

    citations = await container.retrieval.search("SSO SAML OIDC encryption TLS AES-256", top_k=3)
    assert citations
    assert citations[0].filename == "security_policy.md"

    answer = await container.generation.answer_question(
        "What SSO and encryption controls are supported?",
        trace_id="service-trace",
        top_k=3,
    )
    assert answer.citations
    assert answer.token_usage.input_tokens > 0

    analysis = container.analysis.analyze(
        "The vendor must provide SOC 2 evidence. The response deadline is July 18, 2026.",
        trace_id="analysis-trace",
    )
    assert analysis.requirements
    assert analysis.deadlines == ["July 18, 2026"]

    matrix = container.workbench.create_requirement_matrix(analysis)
    assert matrix
    assert matrix[0].owner_role == "Compliance Lead"
    assert matrix[0].status in {"evidence_found", "needs_review"}
    assert matrix[0].evidence_refs

    draft = await container.generation.draft_response("service-draft", top_k=3)
    export = container.workbench.export_package(analysis, draft, "service-export")
    assert export.artifact_path
    assert export.package["executive_summary"]["requirement_count"] == len(matrix)
    assert "Requirement Matrix" in export.markdown

    event = container.audit.record("service-trace", "test.event", "test")
    assert event.trace_id == "service-trace"

    get_container.cache_clear()
    get_settings.cache_clear()
    repository.reset()


def test_mock_provider_and_cost_estimation(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    settings = get_settings()
    settings.estimated_input_cost_per_1k = 0.01
    settings.estimated_output_cost_per_1k = 0.02
    metrics = MetricsService(repository, settings)
    usage = TokenUsage(input_tokens=1000, output_tokens=500)
    assert metrics.estimate_cost(usage) == 0.02
    assert MockLLMProvider().name == "mock"
    get_settings.cache_clear()


def test_review_board_flags_unsupported_answer():
    reviewer = RfpReviewBoardService()
    report = reviewer.review_answer(
        question="Do we guarantee FedRAMP High?",
        answer_text="Yes, the platform is certified and guarantees FedRAMP High support.",
        citations=[],
        missing_evidence=[],
        token_usage=TokenUsage(input_tokens=25, output_tokens=12),
        trace_id="review-test",
    )
    categories = {finding.category for finding in report.findings}
    assert not report.passed
    assert "unsupported_claim" in categories
    assert "missing_evidence" in categories
    assert "weak_citation" in categories


def test_review_board_flags_package_risks():
    reviewer = RfpReviewBoardService()
    matrix = [
        RequirementMatrixRow(
            requirement_id="req_test",
            category="security",
            requirement_text="Vendor must provide proof of FedRAMP High authorization.",
            priority="high",
            owner_role="Security Architect",
            status="blocked",
            risk_level="high",
            suggested_response="Do not claim support yet.",
            missing_evidence=["No FedRAMP authorization evidence found."],
        )
    ]
    draft = DraftResponse(
        sections=[
            DraftSection(
                title="Security",
                body="The platform supports FedRAMP High deployments.",
                requirement_ids=["req_test"],
            )
        ],
        trace_id="draft-review-test",
    )
    report = reviewer.review_package(
        trace_id="package-review-test",
        requirement_matrix=matrix,
        draft_response=draft,
    )
    categories = {finding.category for finding in report.findings}
    assert not report.passed
    assert "high_risk_requirement" in categories
    assert "missing_evidence" in categories
    assert "unsupported_claim" in categories


def test_action_plan_assigns_enterprise_owner_roles(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    service = StakeholderActionPlanService(get_settings())
    profile = CustomerProfile(
        id="low_risk_buyer",
        name="Low Risk Buyer",
        industry="healthcare",
        region="United States",
        risk_tolerance="low",
    )
    matrix = [
        RequirementMatrixRow(
            requirement_id="req_security",
            category="security",
            requirement_text="Vendor must provide SSO and encryption controls.",
            priority="high",
            owner_role="Security Architect",
            status="needs_review",
            risk_level="medium",
            suggested_response="Confirm controls.",
            evidence_refs=["security_policy.md"],
        ),
        RequirementMatrixRow(
            requirement_id="req_legal",
            category="compliance",
            requirement_text="Vendor must provide GDPR DPA and subprocessor terms.",
            priority="high",
            owner_role="Compliance Lead",
            status="blocked",
            risk_level="high",
            suggested_response="Confirm terms.",
            missing_evidence=["No DPA evidence found."],
        ),
        RequirementMatrixRow(
            requirement_id="req_engineering",
            category="implementation",
            requirement_text="Vendor must support API repository integration.",
            priority="medium",
            owner_role="Implementation Lead",
            status="not_started",
            risk_level="medium",
            suggested_response="Confirm integration.",
        ),
        RequirementMatrixRow(
            requirement_id="req_product",
            category="functional",
            requirement_text="Vendor must provide dashboard workflow reports.",
            priority="medium",
            owner_role="Solutions Engineer",
            status="not_started",
            risk_level="medium",
            suggested_response="Confirm product behavior.",
            missing_evidence=["No workflow evidence found."],
        ),
        RequirementMatrixRow(
            requirement_id="req_sales",
            category="pricing",
            requirement_text="Vendor must provide pricing and packaging.",
            priority="medium",
            owner_role="Commercial Owner",
            status="needs_review",
            risk_level="medium",
            suggested_response="Confirm price.",
        ),
    ]
    tasks, summary = service.create_action_plan(
        trace_id="assignment-test",
        requirement_matrix=matrix,
        customer_profile=profile,
    )
    owners = {task.source_requirement_id: task.owner_role for task in tasks}
    assert owners["req_security"] == "security"
    assert owners["req_legal"] == "legal"
    assert owners["req_engineering"] == "engineering"
    assert owners["req_product"] == "product"
    assert owners["req_sales"] == "sales"
    assert summary["task_counts_by_owner"]["legal"] == 1
    assert any(task.status == "blocked" for task in tasks)
    get_settings.cache_clear()


def test_handoff_export_contains_board_sections(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    service = StakeholderActionPlanService(get_settings())
    matrix = [
        RequirementMatrixRow(
            requirement_id="req_blocked",
            category="security",
            requirement_text="Vendor must provide proof of FedRAMP High authorization.",
            priority="high",
            owner_role="Security Architect",
            status="blocked",
            risk_level="high",
            suggested_response="Do not claim support yet.",
            missing_evidence=["No FedRAMP authorization evidence found."],
        )
    ]
    findings = [
        ReviewFinding(
            severity="high",
            category="missing_evidence",
            message="Requirement req_blocked is missing FedRAMP evidence.",
            related_requirement_id="req_blocked",
            recommendation="Attach approved evidence or document an exception.",
        )
    ]
    tasks, _ = service.create_action_plan("handoff-test", requirement_matrix=matrix, review_findings=findings)
    handoff = service.export_handoff_board(
        "handoff-test",
        tasks,
        requirement_matrix=matrix,
        review_findings=findings,
    )
    assert handoff.artifact_path
    assert handoff.json_artifact_path
    assert "## Blocked Items" in handoff.markdown
    assert "FedRAMP" in handoff.markdown
    assert handoff.board["blocked_items"]
    assert handoff.board["high_risk_requirements"]
    get_settings.cache_clear()


def test_deal_readiness_scorecard_scoring(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    service = DealReadinessService(get_settings())
    matrix = [
        RequirementMatrixRow(
            requirement_id="req_ready",
            category="security",
            requirement_text="Vendor must provide SSO controls.",
            priority="medium",
            owner_role="Security Architect",
            status="evidence_found",
            risk_level="medium",
            suggested_response="Use approved security evidence.",
            evidence_refs=["security_policy.md"],
        ),
        RequirementMatrixRow(
            requirement_id="req_blocked",
            category="compliance",
            requirement_text="Vendor must provide FedRAMP High authorization.",
            priority="high",
            owner_role="Compliance Lead",
            status="blocked",
            risk_level="high",
            suggested_response="Do not claim support yet.",
            missing_evidence=["No FedRAMP authorization evidence found."],
        ),
    ]
    findings = [
        ReviewFinding(
            severity="high",
            category="missing_evidence",
            message="Requirement req_blocked is missing FedRAMP evidence.",
            related_requirement_id="req_blocked",
            recommendation="Attach approved evidence or document an exception.",
        )
    ]
    scorecard = service.create_scorecard(
        trace_id="readiness-score-test",
        requirement_matrix=matrix,
        review_findings=findings,
        eval_metrics=EvaluationMetrics(
            question_count=1,
            retrieval_precision_at_k=0.4,
            citation_coverage=0.5,
            missing_evidence_detection_count=1,
            average_latency_ms=10,
            input_tokens=20,
            output_tokens=10,
            estimated_cost=0,
            passed=False,
        ),
    )

    assert scorecard.readiness_score == 47
    assert scorecard.readiness_level == "not_ready"
    assert scorecard.evidence_coverage == 0.5
    assert scorecard.review_risk_count == 1
    assert scorecard.blockers
    assert scorecard.owner_bottlenecks[0]["blocked_items"] == 1
    assert scorecard.score_trace[-1]["component"] == "final_readiness_score"
    assert any(item["component"] == "eval_quality_gate" for item in scorecard.score_trace)
    assert any(item["state"] == "executive_submission_gate" for item in scorecard.approval_workflow)
    assert scorecard.human_review_queue
    assert "durable_checkpoint_ids" in scorecard.governance_summary["controls"]
    assert "Attach approved evidence" in scorecard.recommended_next_actions[0]
    get_settings.cache_clear()


def test_executive_risk_report_export_contains_leadership_sections(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    service = DealReadinessService(get_settings())
    matrix = [
        RequirementMatrixRow(
            requirement_id="req_blocked",
            category="security",
            requirement_text="Vendor must provide incident response evidence.",
            priority="high",
            owner_role="Security Architect",
            status="blocked",
            risk_level="high",
            suggested_response="Attach evidence before submission.",
            missing_evidence=["No incident response evidence found."],
        )
    ]
    findings = [
        ReviewFinding(
            severity="high",
            category="high_risk_requirement",
            message="Requirement req_blocked is high risk.",
            related_requirement_id="req_blocked",
            recommendation="Escalate to security leadership.",
        )
    ]
    tasks = [
        StakeholderTask(
            task_id="task_req_blocked_security",
            owner_role="security",
            title="Security: unblock incident response evidence",
            description="Attach the approved policy.",
            priority="high",
            due_hint="before submission",
            source_requirement_id="req_blocked",
            risk_level="high",
            status="blocked",
        )
    ]
    scorecard = service.create_scorecard(
        trace_id="executive-report-test",
        requirement_matrix=matrix,
        review_findings=findings,
        action_plan=tasks,
    )
    report = service.export_executive_report(
        trace_id="executive-report-test",
        scorecard=scorecard,
        requirement_matrix=matrix,
        review_findings=findings,
        action_plan=tasks,
        red_team_summary={"passed": False, "missing_evidence_detection_count": 3},
    )

    assert report.artifact_path
    assert report.json_artifact_path
    assert "storage" in report.artifact_path
    assert "reports" in report.artifact_path
    assert "## Submission Recommendation" in report.markdown
    assert "## Deal Readiness Scorecard" in report.markdown
    assert "## Red-Team Summary" in report.markdown
    assert "Hold submission" in report.report["submission_recommendation"]
    assert report.report["missing_evidence_count"] == 1
    assert report.report["red_team_summary"]["passed"] is False
    get_settings.cache_clear()


def test_proposal_readiness_score_pack_exports_section_and_reviewer_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    service = DealReadinessService(get_settings())
    matrix = [
        RequirementMatrixRow(
            requirement_id="req_security",
            category="security",
            requirement_text="Vendor must support SSO and encryption.",
            priority="high",
            owner_role="security",
            status="evidence_found",
            risk_level="medium",
            suggested_response="Use approved security posture.",
            evidence_refs=["security_policy.md"],
        ),
        RequirementMatrixRow(
            requirement_id="req_compliance",
            category="compliance",
            requirement_text="Vendor must provide FedRAMP evidence.",
            priority="high",
            owner_role="legal",
            status="blocked",
            risk_level="high",
            suggested_response="Do not claim unsupported authorization.",
            missing_evidence=["No FedRAMP authorization evidence found."],
        ),
    ]
    findings = [
        ReviewFinding(
            severity="high",
            category="missing_evidence",
            message="FedRAMP evidence is missing for compliance response.",
            related_requirement_id="req_compliance",
            recommendation="Route exception to legal and security.",
        )
    ]
    tasks = [
        StakeholderTask(
            task_id="task_req_compliance",
            owner_role="legal",
            title="Legal: approve FedRAMP exception",
            description="Decide whether this is a no-bid blocker.",
            priority="high",
            due_hint="before executive review",
            source_requirement_id="req_compliance",
            risk_level="high",
            status="blocked",
        )
    ]
    draft = DraftResponse(
        sections=[
            DraftSection(
                title="Security Response",
                body="SSO and encryption response using approved controls.",
                requirement_ids=["req_security"],
            )
        ],
        trace_id="draft-test",
    )

    pack = service.create_score_pack(
        trace_id="score-pack-test",
        requirement_matrix=matrix,
        review_findings=findings,
        action_plan=tasks,
        draft_response=draft,
    )

    assert pack.artifact_path
    assert pack.json_artifact_path
    assert Path(pack.artifact_path).exists()
    assert Path(pack.json_artifact_path).exists()
    assert "readiness_packs" in pack.artifact_path
    assert pack.status in {"blocked_by_compliance_risk", "blocked_by_reviewer_bottleneck", "needs_owner_followup"}
    assert pack.pack["section_completeness"]["sections"]
    assert pack.pack["section_completeness"]["blocked_sections"] == ["compliance"]
    assert pack.pack["evidence_coverage"]["overall_coverage"] == 0.5
    assert pack.pack["compliance_risk"]["risk_level"] in {"high", "critical"}
    assert pack.pack["reviewer_bottlenecks"][0]["escalation_required"] is True
    assert pack.pack["score_trace_analysis"]["deduction_count"] >= 1
    assert pack.pack["durable_approval_workflow"]
    assert pack.pack["human_review_queue"]
    assert pack.pack["governance_summary"]["approval_required"] is True
    assert "## Section Completeness" in pack.markdown
    assert "## Score Trace Analysis" in pack.markdown
    assert "## Durable Approval Workflow" in pack.markdown
    assert "## Human Review Queue" in pack.markdown
    assert "POST /rfp/proposal-readiness-score-pack" in pack.markdown
    get_settings.cache_clear()


def test_evidence_gap_prioritization_and_closure_criteria(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    service = EvidenceGapService(get_settings())
    matrix = [
        RequirementMatrixRow(
            requirement_id="req_ready",
            category="security",
            requirement_text="Vendor must provide SSO controls.",
            priority="medium",
            owner_role="Security Architect",
            status="evidence_found",
            risk_level="medium",
            suggested_response="Use approved security evidence.",
            evidence_refs=["security_policy.md"],
        ),
        RequirementMatrixRow(
            requirement_id="req_blocked",
            category="compliance",
            requirement_text="Vendor must provide FedRAMP High authorization.",
            priority="high",
            owner_role="Compliance Lead",
            status="blocked",
            risk_level="high",
            suggested_response="Do not claim support yet.",
            missing_evidence=["No FedRAMP authorization evidence found."],
        ),
        RequirementMatrixRow(
            requirement_id="req_price",
            category="pricing",
            requirement_text="Vendor must provide approved discount assumptions.",
            priority="medium",
            owner_role="Commercial Owner",
            status="needs_review",
            risk_level="medium",
            suggested_response="Confirm commercial approval.",
            missing_evidence=["No discount approval attached."],
        ),
    ]
    findings = [
        ReviewFinding(
            severity="high",
            category="missing_evidence",
            message="Requirement req_blocked is missing FedRAMP evidence.",
            related_requirement_id="req_blocked",
            recommendation="Attach approved evidence or document an exception.",
        )
    ]

    gaps, summary = service.create_gap_plan(
        trace_id="gap-service-test",
        requirement_matrix=matrix,
        review_findings=findings,
        red_team_summary={
            "passed": False,
            "missing_evidence_detection_count": 1,
            "expected_missing_evidence": 1,
            "details": [
                {
                    "question": "Can we claim FedRAMP High authorization?",
                    "risk_type": "unsupported_claim",
                    "missing_evidence_detected": True,
                    "passed": False,
                }
            ],
        },
    )

    assert summary["gap_count"] >= 3
    assert summary["high_severity_count"] >= 2
    assert gaps[0].severity == "high"
    assert gaps[0].priority_rank == 1
    blocked_gap = next(gap for gap in gaps if "req_blocked" in gap.requirement_ids)
    assert blocked_gap.owner_team == "legal"
    assert blocked_gap.missing_source_type in {
        "legal_approval_or_contract_source",
        "compliance_attestation_or_exception",
    }
    assert any("approved for external customer use" in item for item in blocked_gap.closure_acceptance_criteria)
    assert any("Review-board finding" in item for item in blocked_gap.closure_acceptance_criteria)
    assert any(gap.red_team_risks for gap in gaps)
    get_settings.cache_clear()


def test_source_request_pack_export_contains_required_sections(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    service = EvidenceGapService(get_settings())
    matrix = [
        RequirementMatrixRow(
            requirement_id="req_blocked",
            category="security",
            requirement_text="Vendor must provide incident response evidence.",
            priority="high",
            owner_role="Security Architect",
            status="blocked",
            risk_level="high",
            suggested_response="Attach evidence before submission.",
            missing_evidence=["No incident response evidence found."],
        )
    ]
    gaps, _ = service.create_gap_plan("source-pack-test", requirement_matrix=matrix)
    pack = service.export_source_request_pack("source-pack-test", gaps)

    assert pack.artifact_path
    assert pack.json_artifact_path
    assert Path(pack.artifact_path).exists()
    assert Path(pack.json_artifact_path).exists()
    assert "source_requests" in pack.artifact_path
    assert "## Source Request Emails and Tasks" in pack.markdown
    assert "## Owner Matrix" in pack.markdown
    assert "## JD Skills Demonstrated" in pack.markdown
    assert len(pack.pack["interviewer_talking_points"]) == 5
    assert pack.pack["source_request_emails_tasks"]
    assert pack.pack["acceptance_criteria"][0]["criteria"]
    get_settings.cache_clear()


def test_timeline_orchestration_orders_milestones_and_generates_gates(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    settings = get_settings()
    service = TimelineOrchestrationService(settings)
    analyzed = AnalyzeResponse(
        requirements=[
            RfpRequirement(
                id="req_security",
                category="security",
                text="Vendor must provide SSO and encryption evidence.",
                priority="high",
            ),
            RfpRequirement(
                id="req_pricing",
                category="pricing",
                text="Vendor must provide approved pricing assumptions.",
                priority="medium",
            ),
        ],
        deadlines=["July 18, 2026"],
        risks=["Security evidence and pricing approvals are required."],
        trace_id="timeline-analysis-test",
    )
    matrix = [
        RequirementMatrixRow(
            requirement_id="req_security",
            category="security",
            requirement_text="Vendor must provide SSO and encryption evidence.",
            priority="high",
            owner_role="Security Architect",
            status="blocked",
            risk_level="high",
            suggested_response="Attach approved evidence.",
            missing_evidence=["No current encryption evidence attached."],
        )
    ]
    tasks = [
        StakeholderTask(
            task_id="task_req_security_security",
            owner_role="security",
            title="Security: unblock security requirement",
            description="Attach the approved policy.",
            priority="high",
            due_hint="before the next customer review call",
            source_requirement_id="req_security",
            risk_level="high",
            status="blocked",
        )
    ]
    gaps = [
        EvidenceGap(
            gap_id="gap_01_security",
            title="Close security evidence",
            priority_rank=1,
            severity="high",
            owner_team="security",
            missing_source_type="security_policy_or_control_evidence",
            impacted_sections=["Security Response"],
            requirement_ids=["req_security"],
            due_date_recommendation="July 11, 2026",
            suggested_sme_or_source_request="Ask security for approved controls.",
            closure_acceptance_criteria=["Security evidence is approved for customer use."],
        )
    ]
    readiness = DealReadinessService(settings).create_scorecard(
        trace_id="timeline-readiness-test",
        analysis=analyzed,
        requirement_matrix=matrix,
        action_plan=tasks,
    )

    plan = service.create_plan(
        trace_id="timeline-service-test",
        analysis=analyzed,
        requirement_matrix=matrix,
        action_plan=tasks,
        evidence_gaps=gaps,
        readiness_scorecard=readiness,
    )

    dates = [milestone.due_date for milestone in plan.milestones]
    assert dates == sorted(dates)
    assert plan.milestones[-1].title == "Submit response package"
    assert plan.dependencies
    assert any(gate["gate"] == "Evidence closure" and gate["status"] == "blocked" for gate in plan.readiness_gates)
    assert plan.blocked_items
    assert plan.escalation_triggers
    assert plan.calendar_entries[0]["uid"].endswith("@local-rfp-copilot")
    assert plan.summary["milestone_count"] == len(plan.milestones)
    assert plan.summary["blocked_count"] >= 1
    get_settings.cache_clear()


def test_submission_calendar_pack_export_contains_required_sections(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    service = TimelineOrchestrationService(get_settings())
    plan = service.create_plan(trace_id="calendar-pack-plan-test")

    pack = service.export_submission_calendar_pack("calendar-pack-test", plan)

    assert pack.artifact_path
    assert pack.json_artifact_path
    assert Path(pack.artifact_path).exists()
    assert Path(pack.json_artifact_path).exists()
    assert "submission_calendars" in pack.artifact_path
    assert "## Milestone Calendar" in pack.markdown
    assert "## Owner Matrix" in pack.markdown
    assert "## Readiness Gates" in pack.markdown
    assert "## Escalation Triggers" in pack.markdown
    assert len(pack.pack["interviewer_talking_points"]) == 5
    assert pack.pack["calendar_entries"]
    get_settings.cache_clear()


def test_leadership_brief_links_portfolio_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    settings = get_settings()
    readiness_service = DealReadinessService(settings)
    brief_service = LeadershipBriefService(settings)
    matrix = [
        RequirementMatrixRow(
            requirement_id="req_security",
            category="security",
            requirement_text="Vendor must provide SSO controls.",
            priority="high",
            owner_role="Security Architect",
            status="evidence_found",
            risk_level="medium",
            suggested_response="Use approved security evidence.",
            evidence_refs=["security_policy.md"],
        ),
        RequirementMatrixRow(
            requirement_id="req_blocked",
            category="compliance",
            requirement_text="Vendor must provide FedRAMP evidence.",
            priority="high",
            owner_role="Compliance Lead",
            status="blocked",
            risk_level="high",
            suggested_response="Document an exception.",
            missing_evidence=["No FedRAMP authorization evidence found."],
        ),
    ]
    findings = [
        ReviewFinding(
            severity="high",
            category="missing_evidence",
            message="FedRAMP evidence is missing.",
            related_requirement_id="req_blocked",
            recommendation="Attach approved evidence or document an exception.",
        )
    ]
    tasks = [
        StakeholderTask(
            task_id="task_req_blocked_legal",
            owner_role="legal",
            title="Legal: unblock compliance requirement",
            description="Document exception language.",
            priority="high",
            due_hint="before the next customer review call",
            source_requirement_id="req_blocked",
            risk_level="high",
            status="blocked",
        )
    ]
    scorecard = readiness_service.create_scorecard(
        trace_id="leadership-readiness-test",
        requirement_matrix=matrix,
        review_findings=findings,
        action_plan=tasks,
    )
    brief = brief_service.export_brief(
        trace_id="leadership-brief-test",
        documents_ingested=6,
        requirement_matrix=matrix,
        export_payload={"executive_summary": {"requirement_count": 2}, "citations": []},
        export_artifact_path="storage/exports/rfp_export_test.md",
        review_findings=findings,
        review_passed=False,
        action_plan=tasks,
        handoff_board={
            "next_meeting_agenda": ["Close FedRAMP exception with legal and security."],
            "summary": {"task_count": 1, "blocked_tasks": 1},
        },
        handoff_artifact_path="storage/handoffs/rfp_handoff_test.md",
        readiness_scorecard=scorecard,
        executive_report_artifact_path="storage/reports/executive_risk_report_test.md",
        red_team_summary={"passed": True},
    )

    assert brief.artifact_path
    assert brief.json_artifact_path
    assert "leadership_briefs" in brief.artifact_path
    assert "## Local Artifact Links" in brief.markdown
    assert "Export package: storage/exports/rfp_export_test.md" in brief.markdown
    assert brief.brief["metrics"]["docs_ingested"] == 6
    assert brief.brief["metrics"]["requirements"] == 2
    assert brief.brief["metrics"]["red_team_pass"] is True
    assert brief.brief["metrics"]["task_counts"]["blocked"] == 1
    assert brief.brief["artifact_links"]["handoff_board"]["artifact_path"] == "storage/handoffs/rfp_handoff_test.md"
    assert brief.brief["recommended_next_meeting_agenda"] == ["Close FedRAMP exception with legal and security."]
    get_settings.cache_clear()


def test_submission_decision_and_executive_memo_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    settings = get_settings()
    readiness_service = DealReadinessService(settings)
    decision_service = SubmissionDecisionService(settings)
    matrix = [
        RequirementMatrixRow(
            requirement_id="req_sso",
            category="security",
            requirement_text="Vendor must support SSO.",
            priority="high",
            owner_role="Security Architect",
            status="evidence_found",
            risk_level="medium",
            suggested_response="Use SSO evidence.",
            evidence_refs=["security_policy.md"],
        ),
        RequirementMatrixRow(
            requirement_id="req_fedramp",
            category="compliance",
            requirement_text="Vendor must provide FedRAMP authorization.",
            priority="high",
            owner_role="Compliance Lead",
            status="blocked",
            risk_level="high",
            suggested_response="Document exception language.",
            missing_evidence=["No FedRAMP authorization evidence found."],
        ),
    ]
    finding = ReviewFinding(
        severity="high",
        category="missing_evidence",
        message="FedRAMP evidence is missing.",
        related_requirement_id="req_fedramp",
        recommendation="Attach evidence or approve an exception.",
    )
    task = StakeholderTask(
        task_id="task_req_fedramp",
        owner_role="legal",
        title="Approve FedRAMP exception",
        description="Document legal-approved exception language.",
        priority="high",
        due_hint="before final QA",
        source_requirement_id="req_fedramp",
        risk_level="high",
        status="blocked",
    )
    readiness = readiness_service.create_scorecard(
        trace_id="submission-decision-readiness-test",
        requirement_matrix=matrix,
        review_findings=[finding],
        action_plan=[task],
    )
    decision = decision_service.create_decision(
        trace_id="submission-decision-service-test",
        requirement_matrix=matrix,
        review_findings=[finding],
        action_plan=[task],
        readiness_scorecard=readiness,
        red_team_summary={"passed": True, "missing_evidence_detection_count": 1},
        artifact_links={"source_request_pack": {"artifact_path": "storage/source_requests/source_request_pack.md"}},
    )

    assert decision.decision in {"submit_with_exceptions", "do_not_submit"}
    assert decision.score < 85
    assert decision.blocking_issues
    assert decision.exception_list
    assert any(approval["owner"] in {"executive_sponsor", "legal"} for approval in decision.approvals_required)
    assert "go/no-go" in " ".join(decision.local_verification_commands).lower()

    memo = decision_service.export_memo("executive-submission-memo-service-test", decision)
    assert memo.artifact_path
    assert memo.json_artifact_path
    assert Path(memo.artifact_path).exists()
    assert Path(memo.json_artifact_path).exists()
    assert "submission_memos" in memo.artifact_path
    assert "## Go/No-Go Summary" in memo.markdown
    assert "## Evidence Posture" in memo.markdown
    assert len(memo.memo["interviewer_talking_points"]) == 5
    get_settings.cache_clear()


def test_contract_risk_detects_risky_clauses_with_proof_points(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    repository.reset()
    service = ContractRiskService(repository, get_settings())
    text = Path("sample_data/customer_contract_terms.md").read_text(encoding="utf-8")

    risk = service.analyze(text, "contract-risk-service-test", customer_profile_id="regulated_healthcare")

    categories = {clause.category for clause in risk.risky_clauses}
    assert risk.risk_score >= 60
    assert risk.status in {"high_risk", "critical"}
    assert {
        "liability",
        "data_processing",
        "security_obligations",
        "sla_service_credits",
        "audit_rights",
        "termination",
        "indemnity",
        "data_residency",
        "ai_data_use",
        "pricing_payment",
    } <= categories
    assert risk.category_counts["liability"] == 1
    assert risk.suggested_redlines
    assert risk.fallback_positions
    assert risk.cited_proof_points
    assert any(point["source"] == "security_policy.md" for point in risk.cited_proof_points)
    repository.reset()
    get_settings.cache_clear()


def test_contract_risk_missing_evidence_warning_when_no_local_proof(tmp_path, monkeypatch):
    sample_dir = tmp_path / "empty_sample_data"
    sample_dir.mkdir()
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("SAMPLE_DATA_DIR", str(sample_dir))
    get_settings.cache_clear()
    repository.reset()
    service = ContractRiskService(repository, get_settings())

    risk = service.analyze(
        "Supplier shall accept unlimited liability for consequential damages and all indirect damages.",
        "contract-risk-missing-proof-test",
    )

    assert risk.risky_clauses
    assert risk.missing_evidence_warnings
    assert "No internal proof point found" in risk.missing_evidence_warnings[0]
    repository.reset()
    get_settings.cache_clear()


def test_negotiation_brief_export_contains_required_sections(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    repository.reset()
    service = ContractRiskService(repository, get_settings())
    text = Path("sample_data/customer_contract_terms.md").read_text(encoding="utf-8")
    risk = service.analyze(text, "contract-risk-brief-input")

    brief = service.export_negotiation_brief("negotiation-brief-service-test", risk)

    assert brief.artifact_path
    assert brief.json_artifact_path
    assert Path(brief.artifact_path).exists()
    assert Path(brief.json_artifact_path).exists()
    assert "negotiation_briefs" in brief.artifact_path
    assert "## Clause-by-Clause Redlines" in brief.markdown
    assert "## JD Skills Demonstrated" in brief.markdown
    assert len(brief.brief["interviewer_talking_points"]) == 5
    assert brief.brief["contract_risk_summary"]["risk_score"] == risk.risk_score
    repository.reset()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_red_team_eval_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("API_KEY", "red-team-test-key")
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    get_container.cache_clear()
    repository.reset()

    result = await run_red_team("sample_data/red_team_questions.json", top_k=4)

    assert result["passed"]
    assert result["missing_evidence_detection_count"] >= result["expected_missing_evidence"]
    assert result["review_finding_count"] >= result["expected_missing_evidence"]
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_submission_regression_and_demo_script_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("API_KEY", "regression-test-key")
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    get_container.cache_clear()
    repository.reset()

    container = get_container()
    regression = await container.submission_regression.run(
        container,
        SubmissionRegressionRequest(write_artifacts=True),
        trace_id="regression-service-test",
    )

    assert regression.passed
    assert not regression.failed_checks
    assert regression.red_team_summary["missing_evidence_detection_count"] >= regression.red_team_summary[
        "expected_missing_evidence"
    ]
    missing_check = next(
        check for check in regression.checks if check.name == "cited_query_and_missing_evidence_behavior"
    )
    assert missing_check.passed
    assert missing_check.details["missing_evidence_items"] >= 1
    assert regression.artifact_paths["executive_report_markdown"]
    assert Path(regression.artifact_paths["executive_report_markdown"]).exists()
    assert regression.artifact_paths["submission_memo_markdown"]
    assert Path(regression.artifact_paths["submission_memo_markdown"]).exists()

    script = container.demo_script.generate("demo-script-service-test", regression)
    assert script.artifact_path
    assert script.json_artifact_path
    assert Path(script.artifact_path).exists()
    assert "demo_scripts" in script.artifact_path
    assert "## Business Pain" in script.markdown
    assert len(script.script["interviewer_talking_points"]) == 5

    get_settings.cache_clear()
    get_container.cache_clear()
    repository.reset()
