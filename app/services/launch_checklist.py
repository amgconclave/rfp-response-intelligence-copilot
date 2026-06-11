from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.models.api import (
    LaunchChecklistResponse,
    SmokeMatrixResponse,
    SmokeMatrixRow,
    SmokeMatrixSummary,
)


class LaunchChecklistService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def smoke_matrix(self, trace_id: str) -> SmokeMatrixResponse:
        rows = self._smoke_rows()
        summary = SmokeMatrixSummary(
            total_endpoints=len(rows),
            protected_endpoints=sum(1 for row in rows if "X-API-Key" in row.auth_notes),
            artifact_writing_endpoints=sum(1 for row in rows if row.required_artifact_expectations),
            local_mock_ready=self.settings.provider_mode == "mock",
            readiness_level="ready" if self.settings.provider_mode == "mock" else "cloud_provider_configured",
            recommended_sequence=[
                "GET /health",
                "POST /auth/demo-token",
                "POST /documents/ingest",
                "POST /rfp/submission-regression",
                "GET /ops/smoke-matrix",
                "POST /ops/launch-checklist",
                "GET /ops/cost-governance",
                "POST /ops/cost-governance-pack",
                "GET /runtime/demo-readiness",
                "POST /runtime/demo-pack",
                "GET /rag/corpus-coverage",
                "POST /rag/eval-coverage-pack",
                "GET /compliance/evidence-matrix",
                "POST /compliance/control-pack",
                "GET /privacy/retention-guardrails",
                "POST /privacy/retention-pack",
                "GET /governance/model-risk-register",
                "POST /governance/model-risk-pack",
                "GET /procurement/question-risk",
                "POST /procurement/approval-pack",
                "GET /procurement/risk-desk",
                "POST /procurement/risk-desk-pack",
                "POST /rfp/reviewer-collaboration",
                "POST /rfp/reviewer-collaboration-pack",
                "POST /rfp/exception-register",
                "POST /rfp/exception-pack",
                "POST /rfp/proposal-readiness-score-pack",
                "GET /bid/scenario-analysis",
                "POST /bid/roi-pack",
                "POST /rfp/objection-handling",
                "POST /rfp/objection-handling-pack",
                "POST /rfp/answer-reuse-library",
                "POST /rfp/answer-reuse-library-pack",
                "POST /rfp/answer-reuse-drift",
                "POST /rfp/answer-reuse-drift-pack",
                "POST /learning/win-loss",
                "POST /learning/win-loss-pack",
                "POST /rag/retrieval-experiments",
                "POST /rag/retrieval-experiment-pack",
                "GET /evidence/freshness",
                "POST /evidence/freshness-pack",
                "GET /evidence/conflicts",
                "POST /evidence/conflict-pack",
                "GET /evidence/source-trust",
                "POST /evidence/source-trust-pack",
                "POST /evidence/governed-retrieval",
                "POST /evidence/governed-retrieval-pack",
                "GET /proposal/buyer-intelligence",
                "POST /proposal/buyer-intelligence-pack",
                "GET /proposal/buyer-intelligence-replay",
                "POST /proposal/buyer-intelligence-replay-pack",
                "GET /proposal/buyer-contracts",
                "POST /proposal/buyer-contracts-pack",
                "GET /proposal/agent-council",
                "POST /proposal/agent-council-pack",
                "GET /proposal/decision-provenance",
                "POST /proposal/decision-provenance-pack",
                "GET /proposal/submission-certification",
                "POST /proposal/submission-certification-pack",
                "GET /ops/ci-doctor",
                "POST /ops/audit-pack",
                "GET /api/contract-audit",
                "POST /api/reviewer-collection",
                "GET /ui/dashboard-smoke",
                "POST /ui/verification-pack",
                "GET /artifacts/inventory",
                "POST /artifacts/readme-checklist",
                "GET /release/quality-gate",
                "POST /release/publish-pack",
                "GET /ops/verification-evidence",
                "POST /ops/verification-evidence",
                "POST /ops/verification-evidence-pack",
                "GET /reviewer/quickstart",
                "POST /reviewer/walkthrough-pack",
                "GET /handoff/final-audit",
                "POST /handoff/final-pack",
                "GET /git/readiness",
                "POST /git/push-plan",
            ],
            required_local_commands=[
                "python -m uvicorn app.main:app --reload",
                "python -m streamlit run dashboard/app.py",
                "python -m pytest -q",
                "python -m ruff check .",
                "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
                "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
                "python scripts\\runtime_check.py",
                "python -m app.demo",
                (
                    'rg "runtime/demo-readiness|runtime/demo-pack|Runtime Demo|runtime_packs|'
                    'runtime_check|start_demo" app dashboard docs README.md tests scripts sample_data Makefile'
                ),
                (
                    'rg "ops/cost-governance|ops/cost-governance-pack|Cost Governance|'
                    'cost_governance|provider readiness" app dashboard docs README.md tests Makefile'
                ),
                (
                    'rg "ops/verification-evidence|Verification Evidence|verification_evidence|'
                    'command evidence ledger" app dashboard docs README.md tests Makefile'
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\verification_evidence "
                    "-ErrorAction SilentlyContinue | Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\cost_governance -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "rag/corpus-coverage|rag/eval-coverage-pack|RAG Corpus|rag_coverage|'
                    'corpus coverage|eval coverage" app dashboard docs README.md tests scripts sample_data Makefile'
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\rag_coverage -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "compliance/evidence-matrix|compliance/control-pack|Compliance Evidence|'
                    'Control Mapping|compliance_packs|control coverage" '
                    "app dashboard docs README.md tests scripts sample_data Makefile"
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\compliance_packs -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "privacy/retention-guardrails|privacy/retention-pack|Privacy Retention|'
                    'privacy_packs|prompt logging" app dashboard docs README.md tests scripts sample_data Makefile'
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\privacy_packs -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "governance/model-risk|Model Risk Register|model_risk|model-risk-pack" '
                    "app dashboard docs README.md tests scripts sample_data Makefile"
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\model_risk -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "procurement/question-risk|procurement/approval-pack|Procurement Q&A|'
                    'Approval Workflow|procurement_packs|question risk" '
                    "app dashboard docs README.md tests scripts sample_data Makefile"
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\procurement_packs -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "procurement/risk-desk|Procurement Risk Desk|procurement_risk_desk|owner-routed risk" '
                    "app dashboard docs README.md tests scripts sample_data Makefile"
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\procurement_risk_desk -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "reviewer-collaboration|Reviewer Collaboration|review_boards|decision comments" '
                    "app dashboard docs README.md tests sample_data Makefile"
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\review_boards -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "exception-register|exception-pack|Submission Exception|exception_registers" '
                    "app dashboard docs README.md tests Makefile"
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\exception_registers -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "answer-reuse-library|Answer Reuse Library|answer_reuse_library|governed snippets" '
                    "app dashboard docs README.md tests sample_data Makefile"
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\answer_reuse_library -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "answer-reuse-drift|Answer Reuse Drift|answer_reuse_drift|drift monitor" '
                    "app dashboard docs README.md tests sample_data Makefile"
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\answer_reuse_drift -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "bid/scenario-analysis|bid/roi-pack|Bid/No-Bid|ROI Impact|bid_packs|'
                    'risk-adjusted ROI" app dashboard docs README.md tests scripts sample_data Makefile'
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\bid_packs -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "objection-handling|Competitive Objection|Objection Handling|'
                    'objection_packs" app dashboard docs README.md tests Makefile'
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\objection_packs -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "learning/win-loss|Win/Loss Learning|win_loss_packs|rfp_outcomes" '
                    "app dashboard docs README.md tests sample_data Makefile"
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\win_loss_packs -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "retrieval-experiments|retrieval-experiment-pack|Retrieval Experiments|'
                    'retrieval_experiments|experiment comparison" '
                    "app dashboard docs README.md tests sample_data Makefile"
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\retrieval_experiments -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "evidence/freshness|Evidence Freshness|freshness_packs|expiry risk|renewal" '
                    "app dashboard docs README.md tests sample_data Makefile"
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\freshness_packs -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "evidence/conflicts|evidence/conflict-pack|Evidence Conflict|'
                    'conflict_packs|Conflict Resolver" app dashboard docs README.md tests Makefile'
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\conflict_packs -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "evidence/source-trust|Source Trust|source_trust|storage/source_trust" '
                    "app dashboard docs README.md tests Makefile"
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\source_trust -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "evidence/governed-retrieval|Governed Retrieval|governed_retrieval|'
                    'storage/governed_retrieval" app dashboard docs README.md tests Makefile'
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\governed_retrieval -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "proposal/buyer-intelligence|buyer-intelligence-replay|'
                    'proposal/buyer-contracts|Buyer-Grade Proposal Intelligence|'
                    'Buyer Workflow Replay|Buyer Structured Output Contract|'
                    'buyer_intelligence|storage/buyer_intelligence" '
                    "app dashboard docs README.md tests Makefile"
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\buyer_intelligence -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\buyer_contracts -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "proposal/agent-council|Proposal Agent Council|'
                    'agent_council|storage/agent_council" app dashboard docs README.md tests Makefile'
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\agent_council -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\runtime_packs -ErrorAction SilentlyContinue | "
                    "Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "proposal/submission-certification|Proposal Submission Certification|'
                    'submission_certifications" app dashboard docs README.md tests Makefile'
                ),
                (
                    "Get-ChildItem -Recurse -File storage\\submission_certifications "
                    "-ErrorAction SilentlyContinue | Select-Object FullName,Length,LastWriteTime"
                ),
                (
                    'rg "ops/ci-doctor|ops/audit-pack|CI Doctor|Audit Pack|'
                    'audit_packs|secret scan" app dashboard docs README.md tests sample_data Makefile'
                ),
                (
                    'rg "reviewer/quickstart|reviewer/walkthrough-pack|Reviewer Quickstart|'
                    'Walkthrough Pack|reviewer_packs|proof tour" app dashboard docs README.md '
                    "tests sample_data Makefile"
                ),
                (
                    'rg "artifacts/inventory|artifacts/readme-checklist|Artifact Inventory|'
                    'README Checklist|artifact_indexes|reviewer proof checklist" '
                    "app dashboard docs README.md tests sample_data Makefile"
                ),
                (
                    'rg "ui/dashboard-smoke|ui/verification-pack|Dashboard Smoke|UI Verification|'
                    'ui_verification|dashboard smoke" app dashboard docs README.md tests sample_data scripts Makefile'
                ),
                (
                    'rg "api/contract-audit|api/reviewer-collection|API Contract|api_contracts|'
                    'Reviewer Collection|OpenAPI" app dashboard docs README.md tests scripts sample_data Makefile'
                ),
                (
                    'rg "handoff/final-audit|handoff/final-pack|Final Handoff|final_handoff|'
                    'README Consistency|final audit" app dashboard docs README.md tests scripts sample_data Makefile'
                ),
                (
                    'rg "git/readiness|git/push-plan|GitHub Push Readiness|git_packs|'
                    'Branch Hygiene|Git Readiness" app dashboard docs README.md tests scripts sample_data Makefile'
                ),
            ],
            optional_provider_notes=(
                "OpenAI and Azure OpenAI adapters are optional. Local interview verification should keep "
                "PROVIDER_MODE=mock unless the interviewer explicitly asks for a cloud-provider path."
            ),
        )
        return SmokeMatrixResponse(rows=rows, readiness_summary=summary, trace_id=trace_id)

    def launch_checklist(self, trace_id: str, write_artifact: bool = True) -> LaunchChecklistResponse:
        smoke = self.smoke_matrix(f"{trace_id}-smoke")
        checklist = self._checklist_payload(trace_id, smoke)
        markdown = self._render_markdown(checklist)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            checklist_dir = self.settings.storage_dir / "launch_checklists"
            checklist_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = checklist_dir / f"local_launch_checklist_{safe_trace_id}.md"
            json_path = checklist_dir / f"local_launch_checklist_{safe_trace_id}.json"
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(checklist, indent=2), encoding="utf-8")
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            checklist["artifact_paths"]["launch_checklist_markdown"] = artifact_path
            checklist["artifact_paths"]["launch_checklist_json"] = json_artifact_path
            markdown = self._render_markdown(checklist)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(checklist, indent=2), encoding="utf-8")

        return LaunchChecklistResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            checklist=checklist,
            smoke_matrix=smoke,
            trace_id=trace_id,
        )

    def _checklist_payload(self, trace_id: str, smoke: SmokeMatrixResponse) -> dict[str, Any]:
        storage_snapshot = self._storage_snapshot()
        return {
            "trace_id": trace_id,
            "title": "Local Launch Checklist + API Smoke Matrix",
            "generated_at": datetime.now(UTC).isoformat(),
            "readiness": {
                "status": smoke.readiness_summary.readiness_level,
                "provider_mode": self.settings.provider_mode,
                "vector_store_mode": self.settings.vector_store_mode,
                "storage_dir": str(self.settings.storage_dir.resolve()),
                "local_mock_default": self.settings.provider_mode == "mock",
                "summary": (
                    "Ready for a local Agentic/GenAI Engineer interview walkthrough when pytest, ruff, "
                    "standard eval, red-team eval, demo, smoke matrix, and checklist commands pass."
                ),
            },
            "install_run_commands": [
                "python -m pip install -e .",
                "python -m pip install -e \".[dev]\"",
                "python -m uvicorn app.main:app --reload",
                "python -m streamlit run dashboard/app.py",
                (
                    'curl -X GET "http://127.0.0.1:8000/ops/smoke-matrix" '
                    '-H "X-API-Key: local-demo-key"'
                ),
                (
                    'curl -X POST "http://127.0.0.1:8000/ops/launch-checklist" '
                    '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
                ),
            ],
            "api_smoke_matrix": [row.model_dump(mode="json") for row in smoke.rows],
            "readiness_summary": smoke.readiness_summary.model_dump(mode="json"),
            "demo_command": "python -m app.demo",
            "eval_red_team_commands": [
                "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
                "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
                "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4 && "
                "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            ],
            "generated_artifact_paths": storage_snapshot,
            "artifact_paths": {},
            "troubleshooting": [
                {
                    "symptom": "401 from protected endpoints",
                    "fix": "Load /auth/demo-token or send X-API-Key=local-demo-key in local mode.",
                },
                {
                    "symptom": "Dashboard cannot reach API",
                    "fix": "Start python -m uvicorn app.main:app --reload and confirm GET /health returns ok.",
                },
                {
                    "symptom": "No citations returned",
                    "fix": "Ingest the six sample documents or run python -m app.demo before querying.",
                },
                {
                    "symptom": "Cloud provider key errors",
                    "fix": "Unset PROVIDER_MODE or set PROVIDER_MODE=mock for local portfolio verification.",
                },
                {
                    "symptom": "No launch checklist files visible",
                    "fix": "Run POST /ops/launch-checklist and inspect storage/launch_checklists/.",
                },
            ],
            "jd_skills_demonstrated": [
                "Agentic workflow orchestration with deterministic local readiness gates.",
                "Typed FastAPI/Pydantic API contracts, auth boundaries, and traceable ops endpoints.",
                "RAG quality evaluation, red-team missing-evidence checks, and audit/metrics visibility.",
                "Enterprise artifact generation for sales, legal, security, leadership, and interview review.",
                "Local-first GenAI architecture with optional OpenAI/Azure provider adapters.",
            ],
            "interviewer_talking_points": [
                "The smoke matrix turns a large API surface into an interview-safe verification map.",
                "The launch checklist writes durable Markdown and JSON artifacts without cloud dependencies.",
                "Unsupported GenAI claims are routed into review findings, source requests, and submission gates.",
                "The same local services power tests, API routes, dashboard views, evals, and the demo command.",
                "OpenAI/Azure can be enabled later without changing the local workflow or portfolio story.",
            ],
        }

    def _storage_snapshot(self) -> dict[str, Any]:
        storage_map = {
            "exports": "storage/exports",
            "handoffs": "storage/handoffs",
            "reports": "storage/reports",
            "readiness_packs": "storage/readiness_packs",
            "pricing_memos": "storage/pricing_memos",
            "negotiation_briefs": "storage/negotiation_briefs",
            "source_requests": "storage/source_requests",
            "submission_calendars": "storage/submission_calendars",
            "submission_memos": "storage/submission_memos",
            "leadership_briefs": "storage/leadership_briefs",
            "demo_scripts": "storage/demo_scripts",
            "launch_checklists": "storage/launch_checklists",
            "cost_governance": "storage/cost_governance",
            "runtime_packs": "storage/runtime_packs",
            "rag_coverage": "storage/rag_coverage",
            "compliance_packs": "storage/compliance_packs",
            "procurement_packs": "storage/procurement_packs",
            "procurement_risk_desk": "storage/procurement_risk_desk",
            "review_boards": "storage/review_boards",
            "exception_registers": "storage/exception_registers",
            "answer_reuse_library": "storage/answer_reuse_library",
            "answer_reuse_drift": "storage/answer_reuse_drift",
            "bid_packs": "storage/bid_packs",
            "objection_packs": "storage/objection_packs",
            "win_loss_packs": "storage/win_loss_packs",
            "retrieval_experiments": "storage/retrieval_experiments",
            "freshness_packs": "storage/freshness_packs",
            "conflict_packs": "storage/conflict_packs",
            "citation_lineage": "storage/citation_lineage",
            "source_trust": "storage/source_trust",
            "governed_retrieval": "storage/governed_retrieval",
            "buyer_intelligence": "storage/buyer_intelligence",
            "buyer_contracts": "storage/buyer_contracts",
            "agent_council": "storage/agent_council",
            "api_contracts": "storage/api_contracts",
            "portfolio_packs": "storage/portfolio_packs",
            "release_packs": "storage/release_packs",
            "reviewer_packs": "storage/reviewer_packs",
            "artifact_indexes": "storage/artifact_indexes",
            "final_handoff": "storage/final_handoff",
            "git_packs": "storage/git_packs",
        }
        snapshot: dict[str, Any] = {}
        for label, relative in storage_map.items():
            path = self.settings.storage_dir / Path(relative).name
            files = sorted(
                (item for item in path.glob("*") if item.is_file()),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
            snapshot[label] = {
                "expected_path": str(path.resolve()),
                "file_count": len(files),
                "latest_files": [str(item.resolve()) for item in files[:3]],
            }
        return snapshot

    def _smoke_rows(self) -> list[SmokeMatrixRow]:
        return [
            self._row("Demo token", "POST", "/auth/demo-token", "core", 200, "Returns local API key."),
            self._row("Health", "GET", "/health", "core", 200, "Returns ok, provider mode, vector mode, version."),
            self._row(
                "Ingest fixture",
                "POST",
                "/documents/ingest",
                "core",
                200,
                "Stores a sample document and chunks it for retrieval.",
                body='{"fixture_path":"sample_data/security_policy.md","document_type":"security","source":"sample"}',
            ),
            self._row(
                "Ingest upload",
                "POST",
                "/documents/ingest-upload",
                "core",
                200,
                "Accepts uploaded PDF, Markdown, or TXT files.",
                command=(
                    'curl -X POST "http://127.0.0.1:8000/documents/ingest-upload" '
                    '-H "X-API-Key: local-demo-key" '
                    '-F "file=@sample_data/security_policy.md" -F "document_type=security"'
                ),
            ),
            self._row("List documents", "GET", "/documents", "core", 200, "Returns ingested document metadata."),
            self._row(
                "Analyze RFP",
                "POST",
                "/rfp/analyze",
                "core",
                200,
                "Extracts requirements, deadlines, compliance asks, risks, and missing info.",
                body='{"fixture_path":"sample_data/acme_enterprise_rfp.md"}',
            ),
            self._row(
                "Cited question answer",
                "POST",
                "/rfp/query",
                "core",
                200,
                "Returns answer, citations, confidence, missing-evidence warnings, and token usage.",
                body='{"question":"What SSO and encryption controls are supported?","top_k":4}',
            ),
            self._row(
                "Draft response",
                "POST",
                "/rfp/draft-response",
                "core",
                200,
                "Returns cited response sections, assumptions, and revision notes.",
                body='{"section_names":["Executive Summary","Security Response"],"top_k":5}',
            ),
            self._row(
                "Requirement matrix",
                "POST",
                "/rfp/requirement-matrix",
                "core",
                200,
                "Returns owner, status, risk, evidence refs, suggested response, and missing evidence rows.",
                body='{"analyzed_payload":{}}',
            ),
            self._row(
                "Customer profiles",
                "GET",
                "/customers/profiles",
                "enterprise",
                200,
                "Lists local fake profiles.",
            ),
            self._row(
                "Customer fit",
                "POST",
                "/rfp/customer-fit",
                "enterprise",
                200,
                "Returns profile fit score, risks, positioning, and requirement emphasis.",
                body='{"customer_profile_id":"regulated_healthcare","analyzed_payload":{}}',
            ),
            self._row(
                "Response memory search",
                "POST",
                "/rfp/response-memory/search",
                "enterprise",
                200,
                "Returns approved reusable local snippets with confidence and citations.",
                body='{"query":"SSO encryption SOC 2 controls","top_k":3}',
            ),
            self._row(
                "Answer reuse library",
                "POST",
                "/rfp/answer-reuse-library",
                "enterprise",
                200,
                "Returns governed accepted snippets with owner, expiry, reuse decision, and citation lineage.",
                body='{"customer_profile_id":"regulated_healthcare"}',
            ),
            self._row(
                "Answer reuse library pack",
                "POST",
                "/rfp/answer-reuse-library-pack",
                "artifact",
                200,
                "Writes governed Answer Reuse Library Markdown and JSON artifacts.",
                ["storage/answer_reuse_library/*.md", "storage/answer_reuse_library/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Answer reuse drift",
                "POST",
                "/rfp/answer-reuse-drift",
                "enterprise",
                200,
                "Returns checkpointed reusable-answer drift findings with owner routing.",
                body='{"customer_profile_id":"regulated_healthcare","min_source_overlap":4}',
            ),
            self._row(
                "Answer reuse drift pack",
                "POST",
                "/rfp/answer-reuse-drift-pack",
                "artifact",
                200,
                "Writes Answer Reuse Drift Markdown and JSON artifacts.",
                ["storage/answer_reuse_drift/*.md", "storage/answer_reuse_drift/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Export package",
                "POST",
                "/rfp/export-package",
                "artifact",
                200,
                "Writes response package Markdown and JSON.",
                ["storage/exports/*.md", "storage/exports/*.json"],
                '{"fixture_path":"sample_data/acme_enterprise_rfp.md","write_artifact":true}',
            ),
            self._row(
                "Review answer",
                "POST",
                "/rfp/review-answer",
                "enterprise",
                200,
                "Returns groundedness and risk findings for one answer.",
                body='{"question":"Can we guarantee FedRAMP High?","answer_text":"Yes.","citations":[]}',
            ),
            self._row(
                "Review package",
                "POST",
                "/rfp/review-package",
                "enterprise",
                200,
                "Returns package-level findings and optional reviewed export payload.",
                body='{"analyzed_payload":{},"write_artifact":false}',
            ),
            self._row(
                "Reviewer collaboration board",
                "POST",
                "/rfp/reviewer-collaboration",
                "enterprise",
                200,
                "Returns reviewer assignments, decision comments, approval status, and redline summary.",
                body="{}",
            ),
            self._row(
                "Reviewer Collaboration Pack",
                "POST",
                "/rfp/reviewer-collaboration-pack",
                "artifact",
                200,
                "Writes reviewer collaboration Markdown and JSON artifacts.",
                ["storage/review_boards/*.md", "storage/review_boards/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Reviewer Workflow",
                "POST",
                "/rfp/reviewer-workflow",
                "enterprise",
                200,
                "Returns checkpointed reviewer workflow states and traceable transitions.",
                body="{}",
            ),
            self._row(
                "Reviewer Workflow Pack",
                "POST",
                "/rfp/reviewer-workflow-pack",
                "artifact",
                200,
                "Writes reviewer workflow checkpoint and transition Markdown and JSON artifacts.",
                ["storage/review_boards/*.md", "storage/review_boards/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Submission Exception Register",
                "POST",
                "/rfp/exception-register",
                "enterprise",
                200,
                "Returns waiver records with approvers, expiry, evidence requirements, and approval queue.",
                body="{}",
            ),
            self._row(
                "Submission Exception Pack",
                "POST",
                "/rfp/exception-pack",
                "artifact",
                200,
                "Writes submission exception register Markdown and JSON artifacts.",
                ["storage/exception_registers/*.md", "storage/exception_registers/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Action plan",
                "POST",
                "/rfp/action-plan",
                "enterprise",
                200,
                "Returns owner-routed stakeholder tasks and task summary.",
                body='{"analyzed_payload":{},"customer_profile_id":"regulated_healthcare"}',
            ),
            self._row(
                "Handoff board",
                "POST",
                "/rfp/handoff-board",
                "artifact",
                200,
                "Writes cross-functional handoff board Markdown and JSON.",
                ["storage/handoffs/*.md", "storage/handoffs/*.json"],
                '{"analyzed_payload":{},"write_artifact":true}',
            ),
            self._row(
                "Readiness scorecard",
                "POST",
                "/rfp/readiness-scorecard",
                "enterprise",
                200,
                "Returns 0-100 readiness, blockers, coverage, bottlenecks, and next actions.",
                body='{"analysis":{},"matrix":[]}',
            ),
            self._row(
                "Executive risk report",
                "POST",
                "/rfp/executive-risk-report",
                "artifact",
                200,
                "Writes leadership risk report Markdown and JSON.",
                ["storage/reports/*.md", "storage/reports/*.json"],
                '{"analysis":{},"matrix":[],"write_artifact":true}',
            ),
            self._row(
                "Proposal readiness score pack",
                "POST",
                "/rfp/proposal-readiness-score-pack",
                "artifact",
                200,
                "Writes section completeness, evidence coverage, compliance risk, and reviewer bottleneck artifacts.",
                ["storage/readiness_packs/*.md", "storage/readiness_packs/*.json"],
                '{"analysis":{},"matrix":[],"write_artifact":true}',
            ),
            self._row(
                "Win strategy",
                "POST",
                "/rfp/win-strategy",
                "enterprise",
                200,
                "Returns win score, competitor risk, pricing risk, proof points, and owner actions.",
                body='{"analysis":{},"matrix":[],"competitor_context":["Incumbent discount pressure."]}',
            ),
            self._row(
                "Pricing risk memo",
                "POST",
                "/rfp/pricing-risk-memo",
                "artifact",
                200,
                "Writes pricing risk memo Markdown and JSON.",
                ["storage/pricing_memos/*.md", "storage/pricing_memos/*.json"],
                '{"analysis":{},"matrix":[],"write_artifact":true}',
            ),
            self._row(
                "Contract risk",
                "POST",
                "/rfp/contract-risk",
                "enterprise",
                200,
                "Returns risky clauses, redlines, fallback positions, proof points, and owner actions.",
                body='{"fixture_path":"sample_data/customer_contract_terms.md"}',
            ),
            self._row(
                "Negotiation brief",
                "POST",
                "/rfp/negotiation-brief",
                "artifact",
                200,
                "Writes negotiation brief Markdown and JSON.",
                ["storage/negotiation_briefs/*.md", "storage/negotiation_briefs/*.json"],
                '{"fixture_path":"sample_data/customer_contract_terms.md","write_artifact":true}',
            ),
            self._row(
                "Evidence gaps",
                "POST",
                "/rfp/evidence-gaps",
                "enterprise",
                200,
                "Returns prioritized missing evidence and acceptance criteria.",
                body='{"analysis":{},"matrix":[]}',
            ),
            self._row(
                "Source request pack",
                "POST",
                "/rfp/source-request-pack",
                "artifact",
                200,
                "Writes source request pack Markdown and JSON.",
                ["storage/source_requests/*.md", "storage/source_requests/*.json"],
                '{"analysis":{},"matrix":[],"write_artifact":true}',
            ),
            self._row(
                "Timeline plan",
                "POST",
                "/rfp/timeline-plan",
                "enterprise",
                200,
                "Returns milestones, dependencies, readiness gates, and calendar-friendly entries.",
                body='{"analysis":{},"matrix":[]}',
            ),
            self._row(
                "Submission calendar pack",
                "POST",
                "/rfp/submission-calendar-pack",
                "artifact",
                200,
                "Writes submission calendar pack Markdown and JSON.",
                ["storage/submission_calendars/*.md", "storage/submission_calendars/*.json"],
                '{"analysis":{},"matrix":[],"write_artifact":true}',
            ),
            self._row(
                "Submission decision",
                "POST",
                "/rfp/submission-decision",
                "enterprise",
                200,
                "Returns go/no-go decision, blockers, approvals, owner actions, and verification commands.",
                body='{"analysis":{},"matrix":[]}',
            ),
            self._row(
                "Executive submission memo",
                "POST",
                "/rfp/executive-submission-memo",
                "artifact",
                200,
                "Writes executive submission memo Markdown and JSON.",
                ["storage/submission_memos/*.md", "storage/submission_memos/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Leadership brief",
                "POST",
                "/rfp/leadership-brief",
                "artifact",
                200,
                "Writes consolidated leadership brief Markdown and JSON.",
                ["storage/leadership_briefs/*.md", "storage/leadership_briefs/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Submission regression",
                "POST",
                "/rfp/submission-regression",
                "ops",
                200,
                "Runs local readiness regression and writes downstream artifacts when requested.",
                ["storage/reports/*.md", "storage/submission_memos/*.md", "storage/demo_scripts/*.md"],
                '{"top_k":4,"write_artifacts":true}',
            ),
            self._row(
                "Demo script",
                "POST",
                "/rfp/demo-script",
                "artifact",
                200,
                "Writes interview demo script Markdown and JSON.",
                ["storage/demo_scripts/*.md", "storage/demo_scripts/*.json"],
                '{"run_regression":true,"write_artifact":true}',
            ),
            self._row(
                "Standard eval",
                "POST",
                "/rfp/evaluate",
                "ops",
                200,
                "Returns precision, citation coverage, missing-evidence detection, latency, tokens, and cost.",
                body='{"dataset_path":"sample_data/eval_dataset.json","top_k":4}',
            ),
            self._row("Usage metrics", "GET", "/metrics/usage", "ops", 200, "Returns usage metrics and totals."),
            self._row("Audit events", "GET", "/audit/events", "ops", 200, "Returns traceable audit events."),
            self._row(
                "Smoke matrix",
                "GET",
                "/ops/smoke-matrix",
                "ops",
                200,
                "Returns this structured API smoke matrix and readiness summary.",
            ),
            self._row(
                "Launch checklist",
                "POST",
                "/ops/launch-checklist",
                "artifact",
                200,
                "Writes local launch checklist Markdown and JSON.",
                ["storage/launch_checklists/*.md", "storage/launch_checklists/*.json"],
                "{}",
            ),
            self._row(
                "Cost governance",
                "GET",
                "/ops/cost-governance",
                "ops",
                200,
                (
                    "Returns provider readiness, current usage totals, workflow cost forecasts, "
                    "budget status, reviewer controls, and proof commands."
                ),
            ),
            self._row(
                "Cost Governance Pack",
                "POST",
                "/ops/cost-governance-pack",
                "artifact",
                200,
                "Writes provider and budget governance Markdown and JSON.",
                ["storage/cost_governance/*.md", "storage/cost_governance/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Proposal observability",
                "GET",
                "/ops/proposal-observability",
                "ops",
                200,
                (
                    "Returns trace map, retrieval diagnostics, experiment comparison, provider cost signals, "
                    "governance findings, and human-review signals."
                ),
            ),
            self._row(
                "Proposal Observability Pack",
                "POST",
                "/ops/proposal-observability-pack",
                "artifact",
                200,
                "Writes local observability control-plane Markdown and JSON.",
                ["storage/proposal_observability/*.md", "storage/proposal_observability/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Runtime demo readiness",
                "GET",
                "/runtime/demo-readiness",
                "runtime",
                200,
                (
                    "Returns local FastAPI/Streamlit run commands, env/dependency checks, "
                    "read-only port checks, health URLs, and limitations."
                ),
            ),
            self._row(
                "Runtime Demo Server Pack",
                "POST",
                "/runtime/demo-pack",
                "runtime",
                200,
                (
                    "Writes exact runtime start/stop, health, demo-flow, RAG/eval/red-team, screenshot, "
                    "troubleshooting, and explanation artifacts."
                ),
                ["storage/runtime_packs/*.md", "storage/runtime_packs/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "RAG corpus coverage",
                "GET",
                "/rag/corpus-coverage",
                "rag",
                200,
                (
                    "Returns corpus metadata, document category coverage, eval coverage, citation/source "
                    "coverage, red-team coverage, missing-evidence coverage, gaps, and warnings."
                ),
            ),
            self._row(
                "RAG eval coverage pack",
                "POST",
                "/rag/eval-coverage-pack",
                "artifact",
                200,
                "Writes deterministic RAG corpus and eval coverage Markdown and JSON.",
                ["storage/rag_coverage/*.md", "storage/rag_coverage/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Compliance evidence matrix",
                "GET",
                "/compliance/evidence-matrix",
                "compliance",
                200,
                (
                    "Returns control family mappings, linked requirements, evidence snippets, owners, "
                    "missing-evidence warnings, unsupported-claim flags, and control coverage."
                ),
            ),
            self._row(
                "Control Mapping Pack",
                "POST",
                "/compliance/control-pack",
                "artifact",
                200,
                "Writes compliance control coverage, gaps, owner actions, reviewer notes, and local proof commands.",
                ["storage/compliance_packs/*.md", "storage/compliance_packs/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Privacy retention guardrails",
                "GET",
                "/privacy/retention-guardrails",
                "privacy",
                200,
                (
                    "Returns prompt/log/vector/artifact/upload/eval privacy surfaces, retention posture, "
                    "policy evidence, missing controls, redaction rules, and owner actions."
                ),
            ),
            self._row(
                "Privacy Retention Pack",
                "POST",
                "/privacy/retention-pack",
                "artifact",
                200,
                "Writes privacy retention guardrails, prompt logging guidance, owner actions, and proof commands.",
                ["storage/privacy_packs/*.md", "storage/privacy_packs/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Model risk register",
                "GET",
                "/governance/model-risk-register",
                "governance",
                200,
                (
                    "Returns model/provider risk register items, release gates, local evidence, "
                    "reviewer queue, and proof commands."
                ),
            ),
            self._row(
                "Model Risk Register Pack",
                "POST",
                "/governance/model-risk-pack",
                "artifact",
                200,
                "Writes model risk register, release gates, reviewer queue, and governance proof artifacts.",
                ["storage/model_risk/*.md", "storage/model_risk/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Procurement question risk",
                "GET",
                "/procurement/question-risk",
                "procurement",
                200,
                (
                    "Returns simulated buyer questions with category, risk, reviewer role, approval status, "
                    "evidence support, unsupported-claim flags, citations, snippets, and coverage summary."
                ),
            ),
            self._row(
                "Procurement Approval Workflow Pack",
                "POST",
                "/procurement/approval-pack",
                "artifact",
                200,
                (
                    "Writes high-risk question triage, approved/blocked draft answers, reviewer checklist, "
                    "escalation owners, evidence gaps, proof commands, and limitations."
                ),
                ["storage/procurement_packs/*.md", "storage/procurement_packs/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Procurement risk desk",
                "GET",
                "/procurement/risk-desk",
                "procurement",
                200,
                (
                    "Returns legal, pricing, data residency, insurance, and implementation risk rows "
                    "with owner routing, evidence gaps, citations, and packet signals."
                ),
            ),
            self._row(
                "Procurement Risk Desk Pack",
                "POST",
                "/procurement/risk-desk-pack",
                "artifact",
                200,
                (
                    "Writes owner-routed procurement risk desk Markdown and JSON artifacts for legal, "
                    "commercial, privacy, insurance, and implementation review."
                ),
                ["storage/procurement_risk_desk/*.md", "storage/procurement_risk_desk/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Bid/No-Bid scenario analysis",
                "GET",
                "/bid/scenario-analysis",
                "bid",
                200,
                (
                    "Returns deterministic bid/no-bid scenarios with deal value, effort, win probability, "
                    "risk-adjusted ROI, blockers, reviewers, evidence readiness, and timeline pressure."
                ),
            ),
            self._row(
                "ROI Impact Pack",
                "POST",
                "/bid/roi-pack",
                "artifact",
                200,
                (
                    "Writes executive decision memo, scenario comparison, ROI math, blockers, owners, "
                    "proof commands, and limitations."
                ),
                ["storage/bid_packs/*.md", "storage/bid_packs/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Competitive objection handling",
                "POST",
                "/rfp/objection-handling",
                "enterprise",
                200,
                (
                    "Returns cited objection responses for competitor, pricing, security, compliance, "
                    "and implementation concerns with confidence and reviewer status."
                ),
                body='{"competitor_context":["Incumbent competitor is cheaper."],"top_k":4}',
            ),
            self._row(
                "Objection Handling Pack",
                "POST",
                "/rfp/objection-handling-pack",
                "artifact",
                200,
                "Writes competitive objection responses, reviewer workflow, endpoint references, and proof commands.",
                ["storage/objection_packs/*.md", "storage/objection_packs/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Win/Loss Learning",
                "POST",
                "/learning/win-loss",
                "enterprise",
                200,
                (
                    "Ingests fake post-RFP outcomes and returns winning evidence patterns, loss guardrails, "
                    "retrieval recommendations, eval recommendations, and response guidance updates."
                ),
                body='{"outcomes_fixture_path":"sample_data/rfp_outcomes.json","top_k_patterns":6}',
            ),
            self._row(
                "Win/Loss Strategy Pack",
                "POST",
                "/learning/win-loss-pack",
                "artifact",
                200,
                "Writes Win/Loss Learning Strategy Pack Markdown and JSON.",
                ["storage/win_loss_packs/*.md", "storage/win_loss_packs/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Retrieval Experiments",
                "POST",
                "/rag/retrieval-experiments",
                "rag",
                200,
                (
                    "Compares baseline, win/loss boosted, loss-gap guarded, and balanced governed retrieval "
                    "policies with diagnostics, trace spans, and governance decision."
                ),
                body='{"dataset_path":"sample_data/eval_dataset.json","top_k":4}',
            ),
            self._row(
                "Retrieval Experiment Pack",
                "POST",
                "/rag/retrieval-experiment-pack",
                "artifact",
                200,
                "Writes Retrieval Experiment Comparison Pack Markdown and JSON.",
                ["storage/retrieval_experiments/*.md", "storage/retrieval_experiments/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Evidence freshness",
                "GET",
                "/evidence/freshness",
                "evidence",
                200,
                (
                    "Returns source document age, renewal dates, owner follow-ups, unsupported-claim flags, "
                    "endpoint references, and expiry risk scoring."
                ),
            ),
            self._row(
                "Evidence Freshness Pack",
                "POST",
                "/evidence/freshness-pack",
                "artifact",
                200,
                "Writes Evidence Freshness and Expiry Risk Markdown and JSON.",
                ["storage/freshness_packs/*.md", "storage/freshness_packs/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Evidence conflicts",
                "GET",
                "/evidence/conflicts",
                "evidence",
                200,
                (
                    "Returns source-precedence, scope, and ambiguity conflicts with citations, reviewer owners, "
                    "endpoint impact, and resolution guidance."
                ),
            ),
            self._row(
                "Evidence Conflict Pack",
                "POST",
                "/evidence/conflict-pack",
                "artifact",
                200,
                "Writes Evidence Conflict Resolver Markdown and JSON.",
                ["storage/conflict_packs/*.md", "storage/conflict_packs/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Citation lineage audit",
                "GET",
                "/evidence/citation-lineage",
                "evidence",
                200,
                (
                    "Returns answer and draft citation lineage, missing/stale reference checks, "
                    "generated-claim flags, owners, endpoint impact, and proof commands."
                ),
            ),
            self._row(
                "Citation Lineage Pack",
                "POST",
                "/evidence/citation-lineage-pack",
                "artifact",
                200,
                "Writes citation lineage integrity Markdown and JSON.",
                ["storage/citation_lineage/*.md", "storage/citation_lineage/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Source trust gate",
                "GET",
                "/evidence/source-trust",
                "evidence",
                200,
                (
                    "Returns source-level trust decisions by combining freshness, conflict, and "
                    "citation-lineage signals into retrieval policy guidance."
                ),
            ),
            self._row(
                "Source Trust Pack",
                "POST",
                "/evidence/source-trust-pack",
                "artifact",
                200,
                "Writes Source Trust Gate Markdown and JSON.",
                ["storage/source_trust/*.md", "storage/source_trust/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Governed retrieval",
                "POST",
                "/evidence/governed-retrieval",
                "evidence",
                200,
                (
                    "Applies source-trust retrieval policies to retrieved citations and returns allowed, "
                    "review-required, suppressed, blocked, and trace-analysis rows."
                ),
                body=(
                    '{"question":"What disaster recovery, uptime, SSO, encryption, and audit controls are '
                    'supported?","top_k":6}'
                ),
            ),
            self._row(
                "Governed Retrieval Pack",
                "POST",
                "/evidence/governed-retrieval-pack",
                "artifact",
                200,
                "Writes Governed Retrieval Markdown and JSON.",
                ["storage/governed_retrieval/*.md", "storage/governed_retrieval/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Buyer Proposal Intelligence Workflow",
                "GET",
                "/proposal/buyer-intelligence",
                "proposal",
                200,
                (
                    "Returns durable proposal workflow stages, human approval queue, governance gates, "
                    "provider routes, shared state, and trace analysis."
                ),
            ),
            self._row(
                "Buyer Intelligence Pack",
                "POST",
                "/proposal/buyer-intelligence-pack",
                "artifact",
                200,
                "Writes buyer-grade proposal workflow Markdown, JSON, and durable state JSON artifacts.",
                ["storage/buyer_intelligence/*.md", "storage/buyer_intelligence/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Buyer Workflow Replay",
                "GET",
                "/proposal/buyer-intelligence-replay",
                "proposal",
                200,
                (
                    "Returns ordered buyer workflow transitions, conditional route decisions, checkpoint "
                    "validation, and eval-friendly replay scenarios."
                ),
            ),
            self._row(
                "Buyer Workflow Replay Pack",
                "POST",
                "/proposal/buyer-intelligence-replay-pack",
                "artifact",
                200,
                "Writes buyer workflow replay Markdown and JSON artifacts.",
                ["storage/buyer_intelligence/*replay*.md", "storage/buyer_intelligence/*replay*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Buyer Structured Contracts",
                "GET",
                "/proposal/buyer-contracts",
                "proposal",
                200,
                (
                    "Returns typed structured-output contract checks over buyer workflow, replay, council, "
                    "and decision provenance with role coverage and eval assertions."
                ),
            ),
            self._row(
                "Buyer Structured Contract Pack",
                "POST",
                "/proposal/buyer-contracts-pack",
                "artifact",
                200,
                "Writes buyer structured-output contract Markdown and JSON artifacts.",
                ["storage/buyer_contracts/*.md", "storage/buyer_contracts/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Proposal Agent Council",
                "GET",
                "/proposal/agent-council",
                "proposal",
                200,
                (
                    "Returns a deterministic multi-agent proposal council with shared state, governed tool "
                    "access, handoffs, token budget estimates, and eval scenarios."
                ),
            ),
            self._row(
                "Proposal Agent Council Pack",
                "POST",
                "/proposal/agent-council-pack",
                "artifact",
                200,
                "Writes proposal agent council Markdown, JSON, and transcript JSON artifacts.",
                ["storage/agent_council/*.md", "storage/agent_council/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Proposal Decision Provenance",
                "GET",
                "/proposal/decision-provenance",
                "proposal",
                200,
                (
                    "Returns a typed decision provenance graph linking workflow checkpoints, agent turns, "
                    "handoffs, governance gates, provider/source/model/procurement policies, and eval assertions."
                ),
            ),
            self._row(
                "Proposal Decision Provenance Pack",
                "POST",
                "/proposal/decision-provenance-pack",
                "artifact",
                200,
                "Writes proposal decision provenance Markdown and JSON artifacts.",
                ["storage/decision_provenance/*.md", "storage/decision_provenance/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Proposal Submission Certification",
                "GET",
                "/proposal/submission-certification",
                "proposal",
                200,
                (
                    "Returns typed final certification gates, checkpointed state transitions, reviewer queue, "
                    "source artifacts, injected dependencies, and eval assertions."
                ),
            ),
            self._row(
                "Proposal Submission Certification Pack",
                "POST",
                "/proposal/submission-certification-pack",
                "artifact",
                200,
                "Writes proposal submission certification Markdown and JSON artifacts.",
                ["storage/submission_certifications/*.md", "storage/submission_certifications/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "CI Doctor",
                "GET",
                "/ops/ci-doctor",
                "ops",
                200,
                "Returns local CI/docs/tests/env/Docker/dependency and secret scan readiness.",
            ),
            self._row(
                "Audit Pack",
                "POST",
                "/ops/audit-pack",
                "artifact",
                200,
                "Writes local CI Doctor audit pack Markdown and JSON.",
                ["storage/audit_packs/*.md", "storage/audit_packs/*.json"],
                "{}",
            ),
            self._row(
                "API Contract audit",
                "GET",
                "/api/contract-audit",
                "ops",
                200,
                (
                    "Returns OpenAPI route/auth counts, docs/API coverage, dashboard alignment, "
                    "artifact coverage, demo flow coverage, RAG/eval/red-team coverage, warnings, and limitations."
                ),
            ),
            self._row(
                "Reviewer Collection",
                "POST",
                "/api/reviewer-collection",
                "artifact",
                200,
                "Writes OpenAPI-derived reviewer collection Markdown and JSON.",
                ["storage/api_contracts/*.md", "storage/api_contracts/*.json"],
                "{}",
            ),
            self._row(
                "Dashboard Smoke",
                "GET",
                "/ui/dashboard-smoke",
                "ui",
                200,
                "Returns source-level dashboard view, endpoint, artifact-tab, command, and limitation checks.",
            ),
            self._row(
                "UI Verification Pack",
                "POST",
                "/ui/verification-pack",
                "ui",
                200,
                "Writes Dashboard Smoke reviewer verification Markdown and JSON.",
                ["storage/ui_verification/*.md", "storage/ui_verification/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Artifact Inventory",
                "GET",
                "/artifacts/inventory",
                "artifact",
                200,
                "Returns generated artifact directories, producer commands, ignored status, purpose, and freshness.",
            ),
            self._row(
                "README Checklist",
                "POST",
                "/artifacts/readme-checklist",
                "artifact",
                200,
                "Writes Artifact Inventory and README Badge/Checklist Pack Markdown and JSON.",
                ["storage/artifact_indexes/*.md", "storage/artifact_indexes/*.json"],
                "{}",
            ),
            self._row(
                "Release quality gate",
                "GET",
                "/release/quality-gate",
                "release",
                200,
                (
                    "Returns release candidate status, score, blockers, warnings, coverage, "
                    "artifacts, and publish readiness."
                ),
            ),
            self._row(
                "GitHub publish pack",
                "POST",
                "/release/publish-pack",
                "release",
                200,
                "Writes Release Candidate GitHub Publish Pack Markdown and JSON.",
                ["storage/release_packs/*.md", "storage/release_packs/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Verification Evidence Ledger",
                "GET",
                "/ops/verification-evidence",
                "ops",
                200,
                (
                    "Returns a local acceptance evidence ledger across pytest, ruff, eval, red-team, "
                    "dashboard smoke, demo, release gate, final audit, and artifact inventory."
                ),
            ),
            self._row(
                "Verification Evidence Ledger With Results",
                "POST",
                "/ops/verification-evidence",
                "ops",
                200,
                "Returns the verification evidence ledger with optional reviewer-supplied observed command results.",
                body='{"command_results":[]}',
            ),
            self._row(
                "Verification Evidence Pack",
                "POST",
                "/ops/verification-evidence-pack",
                "artifact",
                200,
                "Writes Verification Evidence Markdown and JSON artifacts.",
                ["storage/verification_evidence/*.md", "storage/verification_evidence/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Portfolio evidence index",
                "GET",
                "/portfolio/evidence-index",
                "portfolio",
                200,
                "Returns JD skill coverage mapped to endpoints, tests, artifacts, commands, and proof paths.",
            ),
            self._row(
                "Portfolio interview pack",
                "POST",
                "/portfolio/interview-pack",
                "portfolio",
                200,
                "Writes interview script pack Markdown and JSON.",
                ["storage/portfolio_packs/*.md", "storage/portfolio_packs/*.json"],
                '{"run_regression":true,"write_artifact":true}',
            ),
            self._row(
                "Reviewer Quickstart",
                "GET",
                "/reviewer/quickstart",
                "reviewer",
                200,
                (
                    "Returns exact local setup, one-command demo, verification commands, walkthrough order, "
                    "proof tour, expected outputs, troubleshooting, and role notes."
                ),
            ),
            self._row(
                "Walkthrough Pack",
                "POST",
                "/reviewer/walkthrough-pack",
                "reviewer",
                200,
                "Writes recruiter-friendly and engineer deep-dive Walkthrough Pack Markdown and JSON.",
                ["storage/reviewer_packs/*.md", "storage/reviewer_packs/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "README Consistency final audit",
                "GET",
                "/handoff/final-audit",
                "handoff",
                200,
                (
                    "Returns structured final checks for README endpoints, docs/API coverage, demo claims, "
                    "artifact docs, dashboard smoke, RAG/eval clarity, and Azure optional notes."
                ),
            ),
            self._row(
                "Final Handoff Pack",
                "POST",
                "/handoff/final-pack",
                "handoff",
                200,
                (
                    "Writes final handoff Markdown and JSON with audit, commands, inventories, "
                    "proof summaries, and README blurb."
                ),
                ["storage/final_handoff/*.md", "storage/final_handoff/*.json"],
                '{"write_artifact":true}',
            ),
            self._row(
                "Git Readiness",
                "GET",
                "/git/readiness",
                "git",
                200,
                (
                    "Returns local git repo, branch, status, ignored artifacts, GitHub Actions, "
                    "README handoff, .env.example, and commit grouping checks."
                ),
            ),
            self._row(
                "Branch Hygiene Pack",
                "POST",
                "/git/push-plan",
                "git",
                200,
                "Writes local GitHub Push Readiness and Branch Hygiene Markdown and JSON.",
                ["storage/git_packs/*.md", "storage/git_packs/*.json"],
                '{"write_artifact":true}',
            ),
        ]

    def _row(
        self,
        endpoint_name: str,
        method: str,
        path: str,
        category: str,
        expected_status: int,
        expected_result: str,
        artifact_expectations: list[str] | None = None,
        body: str | None = None,
        command: str | None = None,
    ) -> SmokeMatrixRow:
        auth_notes = "No API key required." if path in {"/auth/demo-token", "/health"} else "Requires X-API-Key."
        sample_command = command or self._curl(method, path, body, auth_notes)
        return SmokeMatrixRow(
            endpoint_name=endpoint_name,
            method=method,
            path=path,
            category=category,
            expected_status=expected_status,
            expected_result=expected_result,
            sample_command=sample_command,
            required_artifact_expectations=artifact_expectations or [],
            auth_notes=auth_notes,
        )

    def _curl(self, method: str, path: str, body: str | None, auth_notes: str) -> str:
        parts = [f'curl -X {method} "http://127.0.0.1:8000{path}"']
        if "X-API-Key" in auth_notes:
            parts.append('-H "X-API-Key: local-demo-key"')
        if body is not None and method != "GET":
            parts.append('-H "Content-Type: application/json"')
            parts.append(f"-d '{body}'")
        return " ".join(parts)

    def _render_markdown(self, checklist: dict[str, Any]) -> str:
        readiness = checklist["readiness"]
        lines = [
            "# Local Launch Checklist + API Smoke Matrix",
            "",
            "## Launch Readiness",
            "",
            f"- Status: {readiness['status']}",
            f"- Provider mode: {readiness['provider_mode']}",
            f"- Vector store mode: {readiness['vector_store_mode']}",
            f"- Storage dir: {readiness['storage_dir']}",
            f"- Summary: {readiness['summary']}",
            "",
            "## Install and Run Commands",
            "",
        ]
        lines.extend(f"```bash\n{command}\n```" for command in checklist["install_run_commands"])
        lines.extend(["", "## API Smoke Matrix", ""])
        lines.append("| Endpoint | Method | Expected | Artifact expectations | Auth |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in checklist["api_smoke_matrix"]:
            artifacts = ", ".join(row["required_artifact_expectations"]) or "None"
            lines.append(
                f"| {row['path']} | {row['method']} | {row['expected_status']} - "
                f"{row['expected_result']} | {artifacts} | {row['auth_notes']} |"
            )
        lines.extend(["", "## Demo Command", "", f"```bash\n{checklist['demo_command']}\n```", ""])
        lines.extend(["## Eval and Red-Team Commands", ""])
        lines.extend(f"```bash\n{command}\n```" for command in checklist["eval_red_team_commands"])
        lines.extend(["", "## Generated Artifact Paths", ""])
        for label, details in checklist["generated_artifact_paths"].items():
            lines.append(f"- {label}: {details['expected_path']} ({details['file_count']} files)")
            for latest in details["latest_files"]:
                lines.append(f"  - latest: {latest}")
        if checklist["artifact_paths"]:
            lines.extend(["", "## Checklist Artifacts", ""])
            for label, path in checklist["artifact_paths"].items():
                lines.append(f"- {label}: {path}")
        lines.extend(["", "## Troubleshooting", ""])
        lines.extend(
            f"- {item['symptom']}: {item['fix']}"
            for item in checklist["troubleshooting"]
        )
        lines.extend(["", "## JD Skills Demonstrated", ""])
        lines.extend(f"- {item}" for item in checklist["jd_skills_demonstrated"])
        lines.extend(["", "## Five Interviewer Talking Points", ""])
        lines.extend(f"- {item}" for item in checklist["interviewer_talking_points"])
        return "\n".join(lines).strip() + "\n"
