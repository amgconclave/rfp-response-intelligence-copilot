# ruff: noqa: E501

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.core.config import Settings
from app.models.api import (
    PortfolioEvidenceIndexResponse,
    PortfolioEvidenceSkill,
    PortfolioInterviewPackRequest,
    PortfolioInterviewPackResponse,
    SubmissionRegressionResponse,
)

if TYPE_CHECKING:
    from app.services.container import ServiceContainer


class PortfolioService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def evidence_index(self, trace_id: str) -> PortfolioEvidenceIndexResponse:
        skills = self._skills()
        covered = sum(1 for skill in skills if skill.coverage_status == "implemented")
        score = round((covered / len(skills)) * 100) if skills else 0
        return PortfolioEvidenceIndexResponse(
            title="Portfolio Evidence Index",
            evidence_score=score,
            covered_skill_count=covered,
            total_skill_count=len(skills),
            skills=skills,
            required_capabilities=[skill.jd_skill for skill in skills],
            proof_commands=self._proof_commands(),
            artifact_roots={
                "portfolio_packs": str((self.settings.storage_dir / "portfolio_packs").resolve()),
                "exports": str((self.settings.storage_dir / "exports").resolve()),
                "handoffs": str((self.settings.storage_dir / "handoffs").resolve()),
                "reports": str((self.settings.storage_dir / "reports").resolve()),
                "source_requests": str((self.settings.storage_dir / "source_requests").resolve()),
                "submission_calendars": str((self.settings.storage_dir / "submission_calendars").resolve()),
                "submission_memos": str((self.settings.storage_dir / "submission_memos").resolve()),
                "launch_checklists": str((self.settings.storage_dir / "launch_checklists").resolve()),
                "rag_coverage": str((self.settings.storage_dir / "rag_coverage").resolve()),
                "compliance_packs": str((self.settings.storage_dir / "compliance_packs").resolve()),
                "procurement_packs": str((self.settings.storage_dir / "procurement_packs").resolve()),
                "review_boards": str((self.settings.storage_dir / "review_boards").resolve()),
                "bid_packs": str((self.settings.storage_dir / "bid_packs").resolve()),
                "objection_packs": str((self.settings.storage_dir / "objection_packs").resolve()),
                "win_loss_packs": str((self.settings.storage_dir / "win_loss_packs").resolve()),
            },
            limitations=[
                "Local portfolio mode uses deterministic mock LLM behavior by default; paid OpenAI/Azure APIs are optional adapters.",
                "Qdrant and FAISS are represented by local vector-store adapters; live Qdrant service validation is optional for interviews.",
                "Sample data is intentionally small so tests, evals, red-team checks, and demos run quickly on a local laptop.",
            ],
            trace_id=trace_id,
        )

    async def generate_interview_pack(
        self,
        container: ServiceContainer,
        trace_id: str,
        request: PortfolioInterviewPackRequest | None = None,
    ) -> PortfolioInterviewPackResponse:
        payload = request or PortfolioInterviewPackRequest()
        evidence = self.evidence_index(f"{trace_id}-evidence")
        regression: SubmissionRegressionResponse | None = None
        if payload.run_regression:
            regression = await container.submission_regression.run(
                container,
                payload.regression_request,
                f"{trace_id}-regression",
            )
        pack = self._pack_payload(trace_id, evidence, regression)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if payload.write_artifact:
            pack_dir = self.settings.storage_dir / "portfolio_packs"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"portfolio_interview_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"portfolio_interview_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["portfolio_pack_markdown"] = artifact_path
            pack["artifact_paths"]["portfolio_pack_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return PortfolioInterviewPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            evidence_index=evidence,
            trace_id=trace_id,
        )

    def _skills(self) -> list[PortfolioEvidenceSkill]:
        return [
            self._skill(
                "rag-vector-retrieval",
                "RAG retrieval with Qdrant/FAISS-ready vector adapters",
                ["Local embedding, chunk retrieval, Qdrant/FAISS factory adapters, deterministic mock vector search"],
                ["/documents/ingest", "/rfp/query"],
                ["app/vectorstores/qdrant_store.py", "app/vectorstores/faiss_store.py", "app/services/retrieval.py"],
                ["tests/test_api_flows.py::test_query_returns_cited_answer_and_metrics", "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4"],
                ["storage/usage_metrics.jsonl"],
                ["python -m app.demo", "make eval"],
                ["app/vectorstores/factory.py", "sample_data/security_policy.md"],
            ),
            self._skill(
                "document-ingestion",
                "Document ingestion, chunking, and local source management",
                ["Fixture ingest, upload ingest, document listing, repository-backed chunks"],
                ["/documents/ingest", "/documents/ingest-upload", "/documents"],
                ["app/services/ingestion.py", "app/repositories/memory.py"],
                ["tests/test_api_flows.py::test_ingestion_and_document_listing"],
                ["storage/audit_events.jsonl"],
                ["curl -X POST http://127.0.0.1:8000/documents/ingest -H \"X-API-Key: local-demo-key\" -H \"Content-Type: application/json\" -d \"{\\\"fixture_path\\\":\\\"sample_data/security_policy.md\\\"}\""],
                ["sample_data/acme_enterprise_rfp.md", "sample_data/product_overview.md"],
            ),
            self._skill(
                "citations-missing-evidence",
                "Citations, confidence scoring, and missing-evidence handling",
                ["Cited answers, unsupported-claim detection, missing evidence warnings, review findings"],
                ["/rfp/query", "/rfp/review-answer", "/rfp/evidence-gaps"],
                ["app/services/draft_generation.py", "app/services/review_board.py", "app/services/evidence_gap.py"],
                ["tests/test_api_flows.py::test_missing_evidence_is_flagged", "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4"],
                ["storage/source_requests/*.md"],
                ["make red-team"],
                ["sample_data/red_team_questions.json"],
            ),
            self._skill(
                "draft-generation",
                "Grounded response draft generation",
                ["Sectioned draft responses, assumptions, revision notes, citation reuse"],
                ["/rfp/draft-response", "/rfp/export-package"],
                ["app/services/draft_generation.py", "app/services/workbench.py"],
                ["tests/test_api_flows.py::test_draft_response_has_required_sections"],
                ["storage/exports/*.md", "storage/exports/*.json"],
                ["python -m app.demo"],
                ["app/providers/mock.py", "sample_data/prior_proposal.md"],
            ),
            self._skill(
                "eval-red-team",
                "Evaluation and red-team readiness gates",
                ["Standard eval metrics, adversarial missing-evidence eval, regression checks"],
                ["/rfp/evaluate", "/rfp/submission-regression"],
                ["app/services/evaluation.py", "app/evals/run_eval.py", "app/evals/run_red_team.py"],
                ["tests/test_api_flows.py::test_evaluation_and_audit_events", "tests/test_api_flows.py::test_submission_regression_and_demo_script_endpoints"],
                ["storage/reports/*.md", "storage/submission_memos/*.md"],
                ["make eval", "make red-team", "make demo"],
                ["sample_data/eval_dataset.json", "sample_data/red_team_questions.json"],
            ),
            self._skill(
                "rag-corpus-eval-coverage",
                "RAG corpus expansion and eval coverage analysis",
                [
                    "Expanded fake enterprise corpus",
                    "Category coverage checks",
                    "Citation/source coverage checks",
                    "Missing-evidence and red-team coverage pack",
                ],
                ["/rag/corpus-coverage", "/rag/eval-coverage-pack"],
                ["app/services/corpus_coverage.py"],
                [
                    "tests/test_api_flows.py::test_rag_corpus_coverage_and_eval_pack",
                    "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
                    "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
                ],
                ["storage/rag_coverage/*.md", "storage/rag_coverage/*.json"],
                ["make rag-coverage-pack", "python -m app.demo"],
                [
                    "sample_data/implementation_guide.md",
                    "sample_data/dpa_privacy_policy.md",
                    "sample_data/sla_support_policy.md",
                    "sample_data/ai_governance_security.md",
                    "sample_data/disaster_recovery_plan.md",
                    "sample_data/customer_success_onboarding.md",
                ],
            ),
            self._skill(
                "compliance-control-mapping",
                "Compliance evidence matrix and control mapping pack",
                [
                    "Control-family mapping",
                    "Requirement links",
                    "Policy snippets",
                    "Unsupported-claim flags",
                    "Owner follow-ups",
                ],
                ["/compliance/evidence-matrix", "/compliance/control-pack"],
                ["app/services/compliance.py"],
                ["tests/test_compliance.py", "python scripts\\dashboard_smoke.py"],
                ["storage/compliance_packs/*.md", "storage/compliance_packs/*.json"],
                ["make compliance-pack", "python -m app.demo"],
                [
                    "sample_data/security_policy.md",
                    "sample_data/dpa_privacy_policy.md",
                    "sample_data/ai_governance_security.md",
                    "sample_data/disaster_recovery_plan.md",
                ],
            ),
            self._skill(
                "procurement-approval-workflow",
                "Procurement Q&A risk simulation and reviewer approval workflow",
                [
                    "Buyer question simulator",
                    "Risk classification",
                    "Reviewer routing",
                    "Unsupported-claim blocking",
                    "Markdown/JSON approval pack",
                ],
                ["/procurement/question-risk", "/procurement/approval-pack"],
                ["app/services/procurement.py"],
                ["tests/test_procurement.py", "python scripts\\dashboard_smoke.py"],
                ["storage/procurement_packs/*.md", "storage/procurement_packs/*.json"],
                ["make procurement-pack", "python -m app.demo"],
                [
                    "sample_data/approved_responses.json",
                    "sample_data/dpa_privacy_policy.md",
                    "sample_data/disaster_recovery_plan.md",
                ],
            ),
            self._skill(
                "reviewer-collaboration-pack",
                "Reviewer collaboration board with assignments, comments, approvals, and redlines",
                [
                    "Named local reviewer assignments",
                    "Decision comments by owner",
                    "Approval status rollups",
                    "Contract and draft redline summary",
                    "Markdown/JSON review-board artifacts",
                ],
                ["/rfp/reviewer-collaboration", "/rfp/reviewer-collaboration-pack"],
                ["app/services/reviewer_collaboration.py"],
                ["tests/test_reviewer_collaboration.py", "python scripts\\dashboard_smoke.py"],
                ["storage/review_boards/*.md", "storage/review_boards/*.json"],
                ["make reviewer-collaboration-pack", "python -m app.demo"],
                ["docs/api.md", "README.md"],
            ),
            self._skill(
                "bid-no-bid-roi",
                "Bid/no-bid scenario simulation and ROI decision intelligence",
                [
                    "Four deterministic pursuit scenarios",
                    "Risk-adjusted ROI math",
                    "Evidence, compliance, procurement, timeline, and commercial blocker routing",
                    "Executive ROI Impact Pack",
                ],
                ["/bid/scenario-analysis", "/bid/roi-pack"],
                ["app/services/bid_simulator.py"],
                ["tests/test_bid_simulator.py", "python scripts\\dashboard_smoke.py"],
                ["storage/bid_packs/*.md", "storage/bid_packs/*.json"],
                ["make bid-roi-pack", "python -m app.demo"],
                ["sample_data/customer_profiles.json", "docs/api.md"],
            ),
            self._skill(
                "competitive-objection-handling",
                "Competitive objection handling with cited, reviewer-gated responses",
                [
                    "Competitor, pricing, security, compliance, and implementation objection catalog",
                    "Citation-backed response posture",
                    "Confidence and reviewer approval status",
                    "Markdown/JSON reviewer pack",
                ],
                ["/rfp/objection-handling", "/rfp/objection-handling-pack"],
                ["app/services/objection_handling.py"],
                ["tests/test_objection_handling.py", "python scripts\\dashboard_smoke.py"],
                ["storage/objection_packs/*.md", "storage/objection_packs/*.json"],
                ["make objection-pack", "python -m app.demo"],
                ["sample_data/pricing_notes.md", "sample_data/security_policy.md", "docs/api.md"],
            ),
            self._skill(
                "win-loss-learning-loop",
                "Post-RFP win/loss learning loop for retrieval, eval, and response guidance",
                [
                    "Fake post-RFP outcome ingestion",
                    "Winning evidence pattern mining",
                    "Loss guardrails for unsupported claims",
                    "Retrieval and eval recommendation updates",
                    "Markdown/JSON strategy pack",
                ],
                ["/learning/win-loss", "/learning/win-loss-pack"],
                ["app/services/win_loss_learning.py"],
                ["tests/test_win_loss_learning.py", "python scripts\\dashboard_smoke.py"],
                ["storage/win_loss_packs/*.md", "storage/win_loss_packs/*.json"],
                ["make win-loss-pack", "python -m app.demo"],
                ["sample_data/rfp_outcomes.json", "docs/api.md"],
            ),
            self._skill(
                "requirement-matrix-review",
                "Requirement matrix and review-board workflow",
                ["Requirement ownership, risk status, package review, groundedness review"],
                ["/rfp/requirement-matrix", "/rfp/review-package"],
                ["app/services/rfp_analysis.py", "app/services/workbench.py", "app/services/review_board.py"],
                ["tests/test_api_flows.py::test_requirement_matrix_and_export_package"],
                ["storage/exports/*.md"],
                ["python -m app.demo"],
                ["docs/api.md", "docs/evaluation.md"],
            ),
            self._skill(
                "action-plan-handoff",
                "Stakeholder action plan and handoff board",
                ["Owner-routed tasks, blocked evidence work, meeting agenda, handoff artifact"],
                ["/rfp/action-plan", "/rfp/handoff-board"],
                ["app/services/action_plan.py"],
                ["tests/test_api_flows.py::test_requirement_matrix_and_export_package"],
                ["storage/handoffs/*.md", "storage/handoffs/*.json"],
                ["python -m app.demo"],
                ["docs/architecture.md"],
            ),
            self._skill(
                "readiness-risk",
                "Readiness scoring, risk reporting, and leadership brief",
                ["Deal readiness scorecard, executive risk report, portfolio leadership brief"],
                ["/rfp/readiness-scorecard", "/rfp/executive-risk-report", "/rfp/leadership-brief"],
                ["app/services/deal_readiness.py", "app/services/leadership_brief.py"],
                ["tests/test_api_flows.py::test_requirement_matrix_and_export_package"],
                ["storage/reports/*.md", "storage/leadership_briefs/*.md"],
                ["python -m app.demo"],
                ["docs/architecture.md"],
            ),
            self._skill(
                "win-pricing-contract-risk",
                "Win strategy, pricing risk, and contract-risk negotiation support",
                ["Win score, competitor risk, pricing memo, clause redlines, negotiation brief"],
                ["/rfp/win-strategy", "/rfp/pricing-risk-memo", "/rfp/contract-risk", "/rfp/negotiation-brief"],
                ["app/services/win_strategy.py", "app/services/contract_risk.py"],
                ["tests/test_api_flows.py::test_win_strategy_endpoint_returns_cited_proof_points", "tests/test_api_flows.py::test_contract_risk_and_negotiation_brief_endpoints"],
                ["storage/pricing_memos/*.md", "storage/negotiation_briefs/*.md"],
                ["python -m app.demo"],
                ["sample_data/customer_contract_terms.md", "sample_data/pricing_notes.md"],
            ),
            self._skill(
                "source-requests",
                "Source requests and evidence-gap closure",
                ["Prioritized source requests, acceptance criteria, SME owner routing"],
                ["/rfp/evidence-gaps", "/rfp/source-request-pack"],
                ["app/services/evidence_gap.py"],
                ["tests/test_api_flows.py::test_requirement_matrix_and_export_package"],
                ["storage/source_requests/*.md", "storage/source_requests/*.json"],
                ["python -m app.demo"],
                ["docs/evaluation.md"],
            ),
            self._skill(
                "timeline-submission-calendar",
                "Timeline orchestration and submission calendar",
                ["Milestones, dependencies, readiness gates, calendar-friendly pack"],
                ["/rfp/timeline-plan", "/rfp/submission-calendar-pack"],
                ["app/services/timeline_orchestration.py"],
                ["tests/test_api_flows.py::test_requirement_matrix_and_export_package"],
                ["storage/submission_calendars/*.md", "storage/submission_calendars/*.json"],
                ["python -m app.demo"],
                ["docs/api.md"],
            ),
            self._skill(
                "go-no-go-decision",
                "Go/no-go submission decision and executive memo",
                ["Decision scoring, blockers, exceptions, approvals, local verification commands"],
                ["/rfp/submission-decision", "/rfp/executive-submission-memo"],
                ["app/services/submission_decision.py"],
                ["tests/test_api_flows.py::test_requirement_matrix_and_export_package"],
                ["storage/submission_memos/*.md", "storage/submission_memos/*.json"],
                ["python -m app.demo"],
                ["README.md"],
            ),
            self._skill(
                "launch-checklist",
                "Launch checklist and API smoke matrix",
                ["Smoke matrix, local launch checklist, artifact inventory"],
                ["/ops/smoke-matrix", "/ops/launch-checklist"],
                ["app/services/launch_checklist.py"],
                ["tests/test_ops_launch.py"],
                ["storage/launch_checklists/*.md", "storage/launch_checklists/*.json"],
                ["make smoke", "make checklist"],
                ["Makefile", "docs/api.md"],
            ),
            self._skill(
                "observability-auth",
                "Observability, metrics, audit, and API auth",
                ["API-key auth, trace IDs, audit events, latency/token/cost metrics"],
                ["/auth/demo-token", "/metrics/usage", "/audit/events", "/health"],
                ["app/core/security.py", "app/core/telemetry.py", "app/services/audit.py", "app/services/metrics.py"],
                ["tests/test_auth_and_health.py", "tests/test_api_flows.py::test_evaluation_and_audit_events"],
                ["storage/audit_events.jsonl", "storage/usage_metrics.jsonl"],
                ["python -m pytest -q"],
                ["app/main.py", ".env.example"],
            ),
            self._skill(
                "portfolio-evidence-pack",
                "Portfolio evidence index and interview script pack",
                ["JD skill coverage, proof paths, interview script, README/resume bullets"],
                ["/portfolio/evidence-index", "/portfolio/interview-pack"],
                ["app/services/portfolio.py", "dashboard/app.py"],
                ["tests/test_api_flows.py::test_portfolio_evidence_index_and_interview_pack"],
                ["storage/portfolio_packs/*.md", "storage/portfolio_packs/*.json"],
                ["make portfolio", "python -m app.demo"],
                ["docs/api.md", "docs/architecture.md"],
            ),
            self._skill(
                "reviewer-quickstart",
                "Reviewer quickstart and recruiter walkthrough pack",
                ["Exact local setup, one-command demo, endpoint walkthrough, RAG/RFP proof tour, artifact proof map, role notes"],
                ["/reviewer/quickstart", "/reviewer/walkthrough-pack"],
                ["app/services/reviewer.py", "dashboard/app.py", "app/demo.py"],
                ["tests/test_api_flows.py::test_reviewer_quickstart_and_walkthrough_pack"],
                ["storage/reviewer_packs/*.md", "storage/reviewer_packs/*.json"],
                ["make reviewer", "python -m app.demo"],
                ["docs/api.md", "docs/evaluation.md", "README.md"],
            ),
        ]

    def _skill(
        self,
        skill_id: str,
        jd_skill: str,
        implemented_features: list[str],
        endpoints: list[str],
        services: list[str],
        tests_evals: list[str],
        artifacts: list[str],
        demo_commands: list[str],
        local_proof_paths: list[str],
    ) -> PortfolioEvidenceSkill:
        return PortfolioEvidenceSkill(
            skill_id=skill_id,
            jd_skill=jd_skill,
            coverage_status="implemented",
            implemented_features=implemented_features,
            endpoints=endpoints,
            services=services,
            tests_evals=tests_evals,
            artifacts=artifacts,
            demo_commands=demo_commands,
            local_proof_paths=local_proof_paths,
            interview_notes=[
                "Explain how this is deterministic in local/mock mode.",
                "Point to the endpoint, service, test, artifact path, and demo command as independent proof.",
            ],
        )

    def _proof_commands(self) -> list[str]:
        return [
            "python -m pytest -q",
            "python -m ruff check .",
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            "python -m app.demo",
            "rg \"portfolio/evidence-index|portfolio/interview-pack|Portfolio Evidence|Interview Pack|portfolio_packs|evidence score\" app dashboard docs README.md tests sample_data Makefile",
            "rg \"reviewer/quickstart|reviewer/walkthrough-pack|Reviewer Quickstart|Walkthrough Pack|reviewer_packs|proof tour\" app dashboard docs README.md tests sample_data Makefile",
            "rg \"rag/corpus-coverage|rag/eval-coverage-pack|RAG Corpus|rag_coverage|corpus coverage|eval coverage\" app dashboard docs README.md tests scripts sample_data Makefile",
            "rg \"compliance/evidence-matrix|compliance/control-pack|Compliance Evidence|Control Mapping|compliance_packs|control coverage\" app dashboard docs README.md tests scripts sample_data Makefile",
            "rg \"procurement/question-risk|procurement/approval-pack|Procurement Q&A|Approval Workflow|procurement_packs|question risk\" app dashboard docs README.md tests scripts sample_data Makefile",
            "rg \"reviewer-collaboration|Reviewer Collaboration|review_boards|decision comments\" app dashboard docs README.md tests sample_data Makefile",
            "rg \"bid/scenario-analysis|bid/roi-pack|Bid/No-Bid|ROI Impact|bid_packs|risk-adjusted ROI\" app dashboard docs README.md tests scripts sample_data Makefile",
            "rg \"objection-handling|Competitive Objection|Objection Handling|objection_packs\" app dashboard docs README.md tests Makefile",
            "rg \"learning/win-loss|Win/Loss Learning|win_loss_packs|rfp_outcomes\" app dashboard docs README.md tests sample_data Makefile",
        ]

    def _pack_payload(
        self,
        trace_id: str,
        evidence: PortfolioEvidenceIndexResponse,
        regression: SubmissionRegressionResponse | None,
    ) -> dict[str, Any]:
        eval_summary = None
        red_team_summary = None
        regression_summary = None
        artifact_paths: dict[str, str | None] = {}
        if regression is not None:
            eval_summary = regression.eval_summary.model_dump(mode="json", exclude={"details"})
            red_team_summary = regression.red_team_summary
            regression_summary = {
                "passed": regression.passed,
                "failed_checks": regression.failed_checks,
                "warnings": regression.warnings,
                "evidence_counts": regression.evidence_counts,
                "interview_ready_summary": regression.interview_ready_summary,
            }
            artifact_paths.update(regression.artifact_paths)
        return {
            "trace_id": trace_id,
            "title": "GitHub Portfolio Evidence Index + Interview Script Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "evidence_score": evidence.evidence_score,
            "covered_skill_count": evidence.covered_skill_count,
            "total_skill_count": evidence.total_skill_count,
            "three_minute_demo_script": [
                {
                    "timebox": "0:00-0:30",
                    "talk_track": "Frame the product: a local-first RFP copilot that turns enterprise source docs into cited answers, drafts, risks, and submission artifacts without paid cloud APIs.",
                    "proof": "Run python -m app.demo and show document count, requirements, citations, readiness, and portfolio evidence score.",
                },
                {
                    "timebox": "0:30-1:15",
                    "talk_track": "Walk through ingestion and RAG: sample RFP, security, compliance, pricing, and proposal docs are chunked into a vector adapter, then queried with citations.",
                    "proof": "Show /documents/ingest, /rfp/query, Qdrant/FAISS adapter files, and sample_data fixtures.",
                },
                {
                    "timebox": "1:15-2:00",
                    "talk_track": "Show the enterprise guardrails: requirement matrix, review board, missing-evidence detection, red-team checks, and source request pack.",
                    "proof": "Run eval and red-team commands; point to review findings and storage/source_requests artifacts.",
                },
                {
                    "timebox": "2:00-2:40",
                    "talk_track": "Show workflow orchestration: action plan, handoff board, readiness score, win/pricing/contract risk, timeline, and go/no-go memo.",
                    "proof": "Open generated Markdown/JSON artifacts under storage and the dashboard workflow tabs.",
                },
                {
                    "timebox": "2:40-3:00",
                    "talk_track": "Close with engineering proof: typed FastAPI contracts, tests, ruff, metrics, audit, API auth, and this portfolio pack mapping JD skills to code and commands.",
                    "proof": "Show /portfolio/evidence-index and /portfolio/interview-pack outputs.",
                },
            ],
            "technical_talking_points": [
                "Local/mock provider mode makes demos reproducible and avoids paid API dependencies while preserving provider-adapter boundaries.",
                "RAG is implemented as ingestion, chunking, embeddings, vector-store abstraction, retrieval, answer generation, and citation packaging.",
                "Unsupported claims are routed into missing evidence, review findings, action plans, source requests, and submission blockers.",
                "Eval and red-team commands exercise both normal retrieval quality and adversarial missing-evidence behavior.",
                "RAG corpus coverage checks prove breadth across implementation, privacy, SLA/support, governance, disaster recovery, and onboarding documents.",
                "Typed Pydantic models keep API contracts stable across FastAPI routes, services, tests, dashboard views, and artifacts.",
                "Audit events, trace IDs, token/cost/latency metrics, and API-key auth make the local app feel enterprise-operated.",
                "Workflow services compose sales, solutions, security, legal, product, and leadership handoffs without hidden cloud state.",
                "Artifacts are written as Markdown plus JSON so interviewers can inspect both human-readable and machine-readable proof.",
                "The portfolio index is deterministic: every JD skill maps to endpoints, tests/evals, commands, and local proof paths.",
            ],
            "architecture_walkthrough": [
                "FastAPI routes define protected workflow endpoints and public health/demo-token endpoints.",
                "ServiceContainer wires settings, repository, vector store, provider, audit, metrics, ingestion, retrieval, generation, and workflow services.",
                "The in-memory repository and storage artifacts keep local runs deterministic; Qdrant/FAISS/OpenAI/Azure adapters are optional extension points.",
                "Streamlit calls the same API routes as tests and demo scripts, preventing a separate dashboard-only path.",
                "Evaluation, red-team, launch checklist, and portfolio pack commands form the local release gate.",
            ],
            "failure_missing_evidence_story": [
                "Ask a deliberately unsupported question such as quantum-resistant satellite telemetry controls.",
                "The retriever returns no credible citation, generation lowers confidence, and missing_evidence is populated.",
                "The review board flags unsupported_claim and missing_evidence instead of letting a confident false answer pass.",
                "The issue becomes a source request, stakeholder task, readiness blocker, and go/no-go exception.",
            ],
            "local_verification_commands": self._proof_commands(),
            "metrics_eval_summary": {
                "regression": regression_summary,
                "standard_eval": eval_summary,
                "red_team": red_team_summary,
            },
            "artifact_inventory": {
                "portfolio_roots": evidence.artifact_roots,
                "regression_artifacts": artifact_paths,
                "storage_snapshot": self._storage_snapshot(),
            },
            "resume_github_readme_bullets": [
                "Built a local-first enterprise RFP GenAI copilot with RAG, citations, missing-evidence controls, evals, red-team checks, and FastAPI/Streamlit UX.",
                "Expanded the fake enterprise RAG corpus and added deterministic corpus/eval coverage endpoints plus Markdown/JSON reviewer artifacts.",
                "Implemented workflow artifacts for requirement matrices, response drafts, review boards, action plans, handoffs, readiness scoring, win/pricing/contract risk, timelines, and go/no-go decisions.",
                "Added deterministic portfolio evidence endpoints that map JD skills to code paths, endpoints, tests, artifacts, and demo commands without requiring paid OpenAI/Azure APIs.",
                "Instrumented API-key auth, trace IDs, audit logs, latency/token/cost metrics, launch checklist, and local regression gates for recruiter/interviewer verification.",
            ],
            "skill_coverage": [skill.model_dump(mode="json") for skill in evidence.skills],
            "limitations": evidence.limitations,
            "artifact_paths": artifact_paths,
        }

    def _storage_snapshot(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = {}
        for path in sorted(self.settings.storage_dir.glob("*")):
            if not path.is_dir():
                continue
            files = sorted(
                (item for item in path.glob("*") if item.is_file()),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
            snapshot[path.name] = {
                "path": str(path.resolve()),
                "file_count": len(files),
                "latest_files": [str(item.resolve()) for item in files[:5]],
            }
        return snapshot

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        lines = [
            "# GitHub Portfolio Evidence Index + Interview Script Pack",
            "",
            "## Portfolio Evidence",
            "",
            f"- Evidence score: {pack['evidence_score']}",
            f"- Covered skills: {pack['covered_skill_count']}/{pack['total_skill_count']}",
            f"- Generated at: {pack['generated_at']}",
            "",
            "## 3-Minute Demo Script",
            "",
        ]
        for item in pack["three_minute_demo_script"]:
            lines.append(f"- {item['timebox']}: {item['talk_track']} Proof: {item['proof']}")
        lines.extend(["", "## Technical Talking Points", ""])
        lines.extend(f"- {item}" for item in pack["technical_talking_points"])
        lines.extend(["", "## Architecture Walk-Through", ""])
        lines.extend(f"- {item}" for item in pack["architecture_walkthrough"])
        lines.extend(["", "## Failure and Missing-Evidence Story", ""])
        lines.extend(f"- {item}" for item in pack["failure_missing_evidence_story"])
        lines.extend(["", "## Local Verification Commands", ""])
        lines.extend(f"```bash\n{command}\n```" for command in pack["local_verification_commands"])
        lines.extend(["", "## Metrics and Eval Summary", ""])
        metrics = pack["metrics_eval_summary"]
        if metrics["regression"]:
            regression = metrics["regression"]
            lines.extend(
                [
                    f"- Regression passed: {regression['passed']}",
                    f"- Failed checks: {regression['failed_checks']}",
                    f"- Evidence counts: {regression['evidence_counts']}",
                    f"- Summary: {regression['interview_ready_summary']}",
                ]
            )
        if metrics["standard_eval"]:
            lines.append(f"- Standard eval: {metrics['standard_eval']}")
        if metrics["red_team"]:
            lines.append(f"- Red-team: {metrics['red_team']}")
        lines.extend(["", "## Artifact Inventory", ""])
        for label, path in pack["artifact_paths"].items():
            lines.append(f"- {label}: {path}")
        for label, details in pack["artifact_inventory"]["storage_snapshot"].items():
            lines.append(f"- {label}: {details['path']} ({details['file_count']} files)")
        lines.extend(["", "## Skill Coverage", ""])
        lines.append("| JD Skill | Endpoints | Tests/Evals | Proof Paths |")
        lines.append("| --- | --- | --- | --- |")
        for skill in pack["skill_coverage"]:
            lines.append(
                f"| {skill['jd_skill']} | {', '.join(skill['endpoints'])} | "
                f"{', '.join(skill['tests_evals'])} | {', '.join(skill['local_proof_paths'])} |"
            )
        lines.extend(["", "## Resume and GitHub README Bullets", ""])
        lines.extend(f"- {item}" for item in pack["resume_github_readme_bullets"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        return "\n".join(lines).strip() + "\n"
