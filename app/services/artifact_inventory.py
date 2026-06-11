from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.models.api import (
    ArtifactFileSummary,
    ArtifactInventoryItem,
    ArtifactInventoryResponse,
    ReadmeChecklistResponse,
)


class ArtifactInventoryService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def inventory(self, trace_id: str) -> ArtifactInventoryResponse:
        directories = [self._inventory_item(spec) for spec in self._artifact_specs()]
        return ArtifactInventoryResponse(
            title="Artifact Inventory",
            storage_root=str(self.settings.storage_dir.resolve()),
            ignored_status=self._ignored_status(),
            generated_at=datetime.now(UTC).isoformat(),
            total_directories=len(directories),
            total_files=sum(item.file_count for item in directories),
            latest_artifact_count=sum(len(item.latest_files) for item in directories),
            directories=directories,
            local_commands=self._local_commands(),
            reviewer_proof_checklist=self._reviewer_proof_checklist(),
            trace_id=trace_id,
        )

    def readme_checklist(self, trace_id: str, write_artifact: bool = True) -> ReadmeChecklistResponse:
        inventory = self.inventory(f"{trace_id}-inventory")
        checklist = self._checklist_payload(trace_id, inventory)
        markdown = self._render_markdown(checklist)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            index_dir = self.settings.storage_dir / "artifact_indexes"
            index_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = index_dir / f"readme_checklist_{safe_trace_id}.md"
            json_path = index_dir / f"readme_checklist_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            checklist["artifact_paths"]["readme_checklist_markdown"] = artifact_path
            checklist["artifact_paths"]["readme_checklist_json"] = json_artifact_path
            markdown = self._render_markdown(checklist)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(checklist, indent=2), encoding="utf-8")

        return ReadmeChecklistResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            checklist=checklist,
            inventory=inventory,
            trace_id=trace_id,
        )

    def _inventory_item(self, spec: dict[str, str]) -> ArtifactInventoryItem:
        directory = self.settings.storage_dir / spec["directory_name"]
        files = self._latest_files(directory)
        notes = self._freshness_notes(files, spec["producer_command"])
        return ArtifactInventoryItem(
            key=spec["key"],
            directory=str(directory.resolve()),
            exists=directory.exists(),
            ignored_status=self._ignored_status(),
            producer_endpoint=spec["producer_endpoint"],
            producer_command=spec["producer_command"],
            reviewer_purpose=spec["reviewer_purpose"],
            freshness_notes=notes,
            file_count=len([item for item in directory.glob("*") if item.is_file()]) if directory.exists() else 0,
            latest_files=files,
        )

    def _latest_files(self, directory: Path) -> list[ArtifactFileSummary]:
        if not directory.exists():
            return []
        files = sorted(
            (item for item in directory.glob("*") if item.is_file()),
            key=lambda item: (item.stat().st_mtime, item.name),
            reverse=True,
        )
        return [
            ArtifactFileSummary(
                path=str(item.resolve()),
                name=item.name,
                extension=item.suffix.lstrip(".") or "none",
                size_bytes=item.stat().st_size,
                last_modified=datetime.fromtimestamp(item.stat().st_mtime, UTC).isoformat(),
            )
            for item in files[:3]
        ]

    def _freshness_notes(self, files: list[ArtifactFileSummary], command: str) -> list[str]:
        if not files:
            return [
                "No generated files found yet.",
                f"Regenerate with: {command}",
            ]
        newest = files[0]
        return [
            f"Latest file: {newest.name} modified {newest.last_modified}.",
            "Freshness is local-run based; rerun the producer command after code or sample-data changes.",
        ]

    def _ignored_status(self) -> str:
        gitignore = Path(".gitignore")
        if not gitignore.exists():
            return "not_confirmed_no_gitignore"
        lines = {
            line.strip()
            for line in gitignore.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        return "ignored_by_gitignore_storage_rule" if "storage/" in lines else "not_confirmed_missing_storage_rule"

    def _checklist_payload(
        self,
        trace_id: str,
        inventory: ArtifactInventoryResponse,
    ) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "README Checklist Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "readme_badge_suggestions": self._badge_suggestions(),
            "readme_checklist_suggestions": self._readme_checklist_suggestions(),
            "artifact_inventory": inventory.model_dump(mode="json"),
            "local_commands": self._local_commands(),
            "reviewer_proof_checklist": self._reviewer_proof_checklist(),
            "cleanup_regeneration_notes": [
                "Generated files live under ignored storage/ directories and should not be committed.",
                (
                    "Delete storage/ to reset local artifacts, then run python -m app.demo to regenerate "
                    "the full demo set."
                ),
            (
                "Regenerate only this pack with POST /artifacts/readme-checklist or make readme-checklist "
                "while the API is running."
            ),
            "Regenerate runtime demo server proof with POST /runtime/demo-pack or make runtime-pack.",
            "Run the rg proof command after docs or endpoint names change.",
            ],
            "artifact_paths": {},
        }

    def _badge_suggestions(self) -> list[dict[str, str]]:
        return [
            {
                "label": "Local Mock Ready",
                "markdown": "![local mock](https://img.shields.io/badge/local--mock-ready-brightgreen)",
                "purpose": "Signals that the reviewer path works without paid provider keys.",
            },
            {
                "label": "Pytest + Ruff",
                "markdown": "![tests](https://img.shields.io/badge/pytest%20%2B%20ruff-passing-blue)",
                "purpose": "Points reviewers to the deterministic local quality gate.",
            },
            {
                "label": "Artifact Inventory",
                "markdown": "![artifacts](https://img.shields.io/badge/artifact--inventory-storage%2F-orange)",
                "purpose": "Highlights that generated proof artifacts are discoverable but ignored by git.",
            },
        ]

    def _readme_checklist_suggestions(self) -> list[str]:
        return [
            "Add a GitHub-visible badge row for local/mock readiness, pytest/ruff, and artifact inventory.",
            "Keep the one-command demo near the top: python -m app.demo.",
            "Link reviewers to GET /artifacts/inventory and POST /artifacts/readme-checklist.",
            "List ignored artifact roots and explain that reviewers regenerate them locally.",
            "Include the reviewer proof checklist with pytest, ruff, eval, red-team, demo, rg, and artifact listing.",
        ]

    def _local_commands(self) -> list[str]:
        return [
            "python -m pytest -q",
            "python -m ruff check .",
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            "python -m app.demo",
            (
                'rg "artifacts/inventory|artifacts/readme-checklist|Artifact Inventory|README Checklist|'
                'artifact_indexes|reviewer proof checklist" app dashboard docs README.md tests sample_data Makefile'
            ),
            (
                "Get-ChildItem -Recurse -File storage\\artifact_indexes -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
            "python scripts\\runtime_check.py",
            (
                'rg "runtime/demo-readiness|runtime/demo-pack|Runtime Demo|runtime_packs|'
                'runtime_check|start_demo" app dashboard docs README.md tests scripts sample_data Makefile'
            ),
            (
                "Get-ChildItem -Recurse -File storage\\runtime_packs -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
            (
                'rg "ops/cost-governance|ops/cost-governance-pack|Cost Governance|'
                'cost_governance|provider readiness" app dashboard docs README.md tests Makefile'
            ),
            (
                "Get-ChildItem -Recurse -File storage\\cost_governance -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
            (
                'rg "handoff/final-audit|handoff/final-pack|Final Handoff|final_handoff|'
                'README Consistency|final audit" app dashboard docs README.md tests scripts sample_data Makefile'
            ),
            (
                "Get-ChildItem -Recurse -File storage\\final_handoff -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
            (
                'rg "git/readiness|git/push-plan|GitHub Push Readiness|git_packs|'
                'Branch Hygiene|Git Readiness" app dashboard docs README.md tests scripts sample_data Makefile'
            ),
            (
                "Get-ChildItem -Recurse -File storage\\git_packs -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
            (
                'rg "api/contract-audit|api/reviewer-collection|API Contract|api_contracts|'
                'Reviewer Collection|OpenAPI" app dashboard docs README.md tests scripts sample_data Makefile'
            ),
            (
                "Get-ChildItem -Recurse -File storage\\api_contracts -ErrorAction SilentlyContinue | "
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
                'privacy_packs|prompt logging" app dashboard docs README.md tests sample_data Makefile'
            ),
            (
                "Get-ChildItem -Recurse -File storage\\privacy_packs -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
            (
                'rg "governance/model-risk|Model Risk Register|model_risk|model-risk-pack" '
                "app dashboard docs README.md tests sample_data Makefile"
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
                'rg "evidence/freshness|Evidence Freshness|freshness_packs|expiry risk|renewal" '
                "app dashboard docs README.md tests sample_data Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\freshness_packs -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
            (
                'rg "evidence/conflicts|evidence/conflict-pack|Evidence Conflict|'
                'conflict_packs|Conflict Resolver" app dashboard docs README.md tests sample_data Makefile'
            ),
            (
                "Get-ChildItem -Recurse -File storage\\conflict_packs -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
            (
                'rg "evidence/citation-lineage|Citation Lineage|citation_lineage|'
                'integrity audit" app dashboard docs README.md tests sample_data Makefile'
            ),
            (
                "Get-ChildItem -Recurse -File storage\\citation_lineage -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
            (
                'rg "proposal/buyer-intelligence|buyer-intelligence-replay|'
                'Buyer-Grade Proposal Intelligence|Buyer Workflow Replay|'
                'buyer_intelligence|storage/buyer_intelligence" app dashboard docs README.md tests Makefile'
            ),
            (
                "Get-ChildItem -Recurse -File storage\\buyer_intelligence -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _reviewer_proof_checklist(self) -> list[str]:
        return [
            "Use this reviewer proof checklist before judging the GitHub repository.",
            "Run pytest and ruff before reviewing generated artifacts.",
            "Run standard eval and red-team eval to verify grounded retrieval and missing-evidence behavior.",
            "Run python -m app.demo to generate the complete ignored storage artifact set.",
            "Call GET /artifacts/inventory to inspect directories, producers, latest files, and ignored status.",
            "Call POST /artifacts/readme-checklist to write the README Checklist Pack under storage/artifact_indexes/.",
            "Call POST /runtime/demo-pack to write the Runtime Demo Server Pack under storage/runtime_packs/.",
            (
                "Call POST /ops/cost-governance-pack to write the Cost Governance Pack "
                "under storage/cost_governance/."
            ),
            (
                "Call POST /api/reviewer-collection to write the API Reviewer Collection Pack "
                "under storage/api_contracts/."
            ),
            (
                "Call POST /compliance/control-pack to write the Compliance Evidence control pack "
                "under storage/compliance_packs/."
            ),
            (
                "Call POST /procurement/approval-pack to write the Procurement Q&A Approval Workflow Pack "
                "under storage/procurement_packs/."
            ),
            (
                "Call POST /rfp/reviewer-collaboration-pack to write the Reviewer Collaboration Pack "
                "under storage/review_boards/."
            ),
            (
                "Call POST /rfp/exception-pack to write the Submission Exception Register Pack "
                "under storage/exception_registers/."
            ),
            (
                "Call POST /bid/roi-pack to write the Bid/No-Bid ROI Impact Pack "
                "under storage/bid_packs/."
            ),
            (
                "Call POST /rfp/objection-handling-pack to write the Competitive Objection Handling Pack "
                "under storage/objection_packs/."
            ),
            (
                "Call POST /learning/win-loss-pack to write the Win/Loss Learning Strategy Pack "
                "under storage/win_loss_packs/."
            ),
            (
                "Call POST /evidence/freshness-pack to write the Evidence Freshness Pack "
                "under storage/freshness_packs/."
            ),
            (
                "Call POST /evidence/conflict-pack to write the Evidence Conflict Resolver Pack "
                "under storage/conflict_packs/."
            ),
            (
                "Call POST /evidence/citation-lineage-pack to write the Citation Lineage Integrity Pack "
                "under storage/citation_lineage/."
            ),
            (
                "Call POST /proposal/buyer-intelligence-pack to write the Buyer-Grade Proposal Intelligence Pack "
                "under storage/buyer_intelligence/."
            ),
            (
                "Call POST /proposal/buyer-intelligence-replay-pack to write the Buyer Workflow Replay Pack "
                "under storage/buyer_intelligence/."
            ),
            (
                "Inspect storage/artifact_indexes plus at least one Markdown/JSON artifact from each "
                "major artifact family."
            ),
        ]

    def _render_markdown(self, checklist: dict[str, Any]) -> str:
        inventory = checklist["artifact_inventory"]
        lines = [
            "# README Checklist Pack",
            "",
            "## Artifact Inventory",
            "",
            f"- Storage root: {inventory['storage_root']}",
            f"- Ignored status: {inventory['ignored_status']}",
            f"- Directories: {inventory['total_directories']}",
            f"- Files: {inventory['total_files']}",
            "",
            "| Key | Files | Producer | Reviewer purpose | Freshness |",
            "| --- | ---: | --- | --- | --- |",
        ]
        for item in inventory["directories"]:
            freshness = " ".join(item["freshness_notes"])
            lines.append(
                f"| {item['key']} | {item['file_count']} | `{item['producer_endpoint']}` | "
                f"{item['reviewer_purpose']} | {freshness} |"
            )
        lines.extend(["", "## README Badge Suggestions", ""])
        for badge in checklist["readme_badge_suggestions"]:
            lines.append(f"- {badge['label']}: {badge['markdown']} - {badge['purpose']}")
        lines.extend(["", "## README Checklist Suggestions", ""])
        lines.extend(f"- [ ] {item}" for item in checklist["readme_checklist_suggestions"])
        lines.extend(["", "## Local Commands", ""])
        lines.extend(f"```bash\n{command}\n```" for command in checklist["local_commands"])
        lines.extend(["", "## Reviewer Proof Checklist", ""])
        lines.append("This is the deterministic reviewer proof checklist for GitHub judging.")
        lines.extend(f"- [ ] {item}" for item in checklist["reviewer_proof_checklist"])
        lines.extend(["", "## Cleanup and Regeneration Notes", ""])
        lines.extend(f"- {item}" for item in checklist["cleanup_regeneration_notes"])
        if checklist["artifact_paths"]:
            lines.extend(["", "## README Checklist Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in checklist["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _artifact_specs(self) -> list[dict[str, str]]:
        return [
            self._spec(
                "exports",
                "exports",
                "POST /rfp/export-package",
                "Response package, requirement matrix, draft, citations, customer fit, and response memory.",
            ),
            self._spec(
                "handoffs",
                "handoffs",
                "POST /rfp/handoff-board",
                "Owner-routed stakeholder handoff board with blocked items and agenda.",
            ),
            self._spec(
                "reports",
                "reports",
                "POST /rfp/executive-risk-report",
                "Leadership readiness and risk report.",
            ),
            self._spec(
                "readiness_packs",
                "readiness_packs",
                "POST /rfp/proposal-readiness-score-pack",
                (
                    "Proposal readiness score pack with section completeness, evidence coverage, "
                    "compliance risk, and bottlenecks."
                ),
            ),
            self._spec(
                "pricing_memos",
                "pricing_memos",
                "POST /rfp/pricing-risk-memo",
                "Competitive pricing and discount-risk memo.",
            ),
            self._spec(
                "negotiation_briefs",
                "negotiation_briefs",
                "POST /rfp/negotiation-brief",
                "Contract redline and negotiation proof artifact.",
            ),
            self._spec(
                "source_requests",
                "source_requests",
                "POST /rfp/source-request-pack",
                "Evidence gap closure requests and owner tasks.",
            ),
            self._spec(
                "submission_calendars",
                "submission_calendars",
                "POST /rfp/submission-calendar-pack",
                "Timeline, dependencies, readiness gates, and local calendar entries.",
            ),
            self._spec(
                "submission_memos",
                "submission_memos",
                "POST /rfp/executive-submission-memo",
                "Final go/no-go memo with blockers, exceptions, approvals, and commands.",
            ),
            self._spec(
                "leadership_briefs",
                "leadership_briefs",
                "POST /rfp/leadership-brief",
                "Consolidated portfolio leadership artifact and artifact links.",
            ),
            self._spec(
                "demo_scripts",
                "demo_scripts",
                "POST /rfp/demo-script",
                "Interview demo script with commands and sample outputs.",
            ),
            self._spec(
                "launch_checklists",
                "launch_checklists",
                "POST /ops/launch-checklist",
                "Local launch checklist and smoke matrix.",
            ),
            self._spec(
                "runtime_packs",
                "runtime_packs",
                "POST /runtime/demo-pack",
                "Runtime Demo Server Pack with FastAPI/Streamlit commands, readiness checks, and screenshot checklist.",
            ),
            self._spec(
                "cost_governance",
                "cost_governance",
                "POST /ops/cost-governance-pack",
                "Provider readiness, token budget forecast, and local cost governance artifacts.",
            ),
            self._spec(
                "rag_coverage",
                "rag_coverage",
                "POST /rag/eval-coverage-pack",
                (
                    "RAG corpus expansion and eval coverage pack with category, citation, red-team, "
                    "and missing-evidence checks."
                ),
            ),
            self._spec(
                "compliance_packs",
                "compliance_packs",
                "POST /compliance/control-pack",
                "Compliance evidence matrix and control mapping Markdown and JSON.",
            ),
            self._spec(
                "privacy_packs",
                "privacy_packs",
                "POST /privacy/retention-pack",
                "Privacy retention guardrail matrix, prompt logging guidance, and owner actions.",
            ),
            self._spec(
                "model_risk",
                "model_risk",
                "POST /governance/model-risk-pack",
                "Model risk register, release gates, reviewer queue, and local AI governance artifacts.",
            ),
            self._spec(
                "procurement_packs",
                "procurement_packs",
                "POST /procurement/approval-pack",
                "Procurement Q&A risk simulator and approval workflow Markdown and JSON.",
            ),
            self._spec(
                "procurement_risk_desk",
                "procurement_risk_desk",
                "POST /procurement/risk-desk-pack",
                "Owner-routed legal, pricing, data residency, insurance, and implementation risk desk artifacts.",
            ),
            self._spec(
                "review_boards",
                "review_boards",
                "POST /rfp/reviewer-collaboration-pack",
                "Reviewer assignments, decision comments, approval statuses, and redline summary artifacts.",
            ),
            self._spec(
                "exception_registers",
                "exception_registers",
                "POST /rfp/exception-pack",
                "Submission exception register with waiver type, approver, expiry, and required evidence.",
            ),
            self._spec(
                "answer_reuse_library",
                "answer_reuse_library",
                "POST /rfp/answer-reuse-library-pack",
                "Governed accepted-answer snippets with owners, expiry, citation lineage, and reuse decisions.",
            ),
            self._spec(
                "bid_packs",
                "bid_packs",
                "POST /bid/roi-pack",
                "Bid/No-Bid scenario simulator and ROI Impact Pack Markdown and JSON.",
            ),
            self._spec(
                "objection_packs",
                "objection_packs",
                "POST /rfp/objection-handling-pack",
                "Competitive objection handling responses, reviewer workflow, confidence, and citations.",
            ),
            self._spec(
                "win_loss_packs",
                "win_loss_packs",
                "POST /learning/win-loss-pack",
                "Win/loss learning strategy pack with retrieval, eval, and response guidance updates.",
            ),
            self._spec(
                "freshness_packs",
                "freshness_packs",
                "POST /evidence/freshness-pack",
                "Evidence freshness, renewal, owner, endpoint, and unsupported-claim risk artifacts.",
            ),
            self._spec(
                "conflict_packs",
                "conflict_packs",
                "POST /evidence/conflict-pack",
                "Evidence conflict resolver artifacts with source precedence, ambiguity, and reviewer routing.",
            ),
            self._spec(
                "citation_lineage",
                "citation_lineage",
                "POST /evidence/citation-lineage-pack",
                "Citation lineage and integrity artifacts with missing, stale, weak, and claim-risk checks.",
            ),
            self._spec(
                "source_trust",
                "source_trust",
                "POST /evidence/source-trust-pack",
                "Source trust gate artifacts with retrieval policy, owner review, and source approval decisions.",
            ),
            self._spec(
                "buyer_intelligence",
                "buyer_intelligence",
                "POST /proposal/buyer-intelligence-pack",
                (
                    "Buyer-grade proposal workflow pack with durable checkpoints, HITL approval queue, "
                    "governance gates, provider routes, local state JSON, and replay transition packs."
                ),
            ),
            self._spec(
                "audit_packs",
                "audit_packs",
                "POST /ops/audit-pack",
                "CI Doctor audit pack, dependency inventory, and secret scan summary.",
            ),
            self._spec(
                "api_contracts",
                "api_contracts",
                "POST /api/reviewer-collection",
                "OpenAPI-derived API contract snapshot and runnable reviewer collection.",
            ),
            self._spec(
                "portfolio_packs",
                "portfolio_packs",
                "POST /portfolio/interview-pack",
                "Portfolio evidence and interview pack.",
            ),
            self._spec(
                "reviewer_packs",
                "reviewer_packs",
                "POST /reviewer/walkthrough-pack",
                "Reviewer walkthrough, proof tour, and README blurb.",
            ),
            self._spec(
                "release_packs",
                "release_packs",
                "POST /release/publish-pack",
                "GitHub publish readiness pack.",
            ),
            self._spec(
                "ui_verification",
                "ui_verification",
                "POST /ui/verification-pack",
                "Dashboard Smoke and reviewer UI verification artifacts.",
            ),
            self._spec(
                "artifact_indexes",
                "artifact_indexes",
                "POST /artifacts/readme-checklist",
                "Artifact Inventory plus README badge/checklist pack.",
            ),
            self._spec(
                "final_handoff",
                "final_handoff",
                "POST /handoff/final-pack",
                "Final Handoff Pack with README consistency audit, commands, inventories, and recruiter blurb.",
            ),
            self._spec(
                "git_packs",
                "git_packs",
                "POST /git/push-plan",
                "GitHub Push Readiness and Branch Hygiene Pack with local non-destructive review commands.",
            ),
        ]

    def _spec(
        self,
        key: str,
        directory_name: str,
        producer_endpoint: str,
        reviewer_purpose: str,
    ) -> dict[str, str]:
        return {
            "key": key,
            "directory_name": directory_name,
            "producer_endpoint": producer_endpoint,
            "producer_command": self._producer_command(producer_endpoint),
            "reviewer_purpose": reviewer_purpose,
        }

    def _producer_command(self, endpoint: str) -> str:
        path = endpoint.split(" ", 1)[1]
        return (
            f'curl -X POST "http://127.0.0.1:8000{path}" '
            '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
        )
