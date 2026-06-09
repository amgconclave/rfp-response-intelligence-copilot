from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.models.api import (
    ArtifactInventoryResponse,
    DashboardSmokeResponse,
    FinalAuditCheck,
    FinalAuditResponse,
    SmokeMatrixResponse,
)


class FinalHandoffService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def final_audit(
        self,
        trace_id: str,
        smoke_matrix: SmokeMatrixResponse,
        artifact_inventory: ArtifactInventoryResponse,
        dashboard_smoke: DashboardSmokeResponse,
    ) -> FinalAuditResponse:
        checks = self._checks(smoke_matrix, artifact_inventory, dashboard_smoke)
        failed = [check for check in checks if check.status != "pass"]
        score = max(0, 100 - (len(failed) * 10) - sum(len(check.missing_terms) for check in checks))
        status = "pass" if not failed else "needs_work"
        endpoint_inventory = self._endpoint_inventory(smoke_matrix)
        artifact_summary = self._artifact_inventory(artifact_inventory)
        return FinalAuditResponse(
            title="README Consistency Final Audit",
            status=status,
            score=score,
            checks=checks,
            summary={
                "passed_checks": sum(check.status == "pass" for check in checks),
                "failed_checks": len(failed),
                "failed_check_ids": [check.check_id for check in failed],
                "final_endpoint_count": len(endpoint_inventory["final_handoff_endpoints"]),
                "final_handoff_artifact_root": str((self.settings.storage_dir / "final_handoff").resolve()),
                "dashboard_smoke_status": dashboard_smoke.status,
                "artifact_inventory_directories": artifact_inventory.total_directories,
                "local_mock_default": self.settings.provider_mode == "mock",
            },
            endpoint_inventory=endpoint_inventory,
            artifact_inventory=artifact_summary,
            local_verification_commands=self._verification_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def final_pack(
        self,
        trace_id: str,
        final_audit: FinalAuditResponse,
        smoke_matrix: SmokeMatrixResponse,
        artifact_inventory: ArtifactInventoryResponse,
        dashboard_smoke: DashboardSmokeResponse,
        write_artifact: bool = True,
    ) -> tuple[str | None, str | None, str, dict[str, Any]]:
        pack = self._pack_payload(trace_id, final_audit, smoke_matrix, artifact_inventory, dashboard_smoke)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "final_handoff"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"final_handoff_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"final_handoff_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["final_handoff_markdown"] = artifact_path
            pack["artifact_paths"]["final_handoff_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return artifact_path, json_artifact_path, markdown, pack

    def _checks(
        self,
        smoke_matrix: SmokeMatrixResponse,
        artifact_inventory: ArtifactInventoryResponse,
        dashboard_smoke: DashboardSmokeResponse,
    ) -> list[FinalAuditCheck]:
        return [
            self._terms_check(
                "readme_endpoint_mentions",
                "README endpoint mentions",
                "docs",
                ["README.md", "app/api/routes.py"],
                ["handoff/final-audit", "handoff/final-pack", "Final Handoff", "final_handoff"],
            ),
            self._terms_check(
                "docs_api_coverage",
                "Docs/API coverage",
                "docs",
                ["docs/api.md", "app/models/api.py", "app/api/routes.py"],
                ["GET /handoff/final-audit", "POST /handoff/final-pack", "FinalAuditResponse", "FinalPackResponse"],
            ),
            self._terms_check(
                "architecture_evaluation_coverage",
                "Architecture/evaluation coverage",
                "docs",
                ["docs/architecture.md", "docs/evaluation.md"],
                ["FinalHandoffService", "README Consistency", "Final Handoff", "storage/final_handoff"],
            ),
            self._terms_check(
                "demo_output_claims",
                "Demo output claims",
                "demo",
                ["app/demo.py", "README.md"],
                ["Final audit status", "Final Handoff Pack", "final_audit", "final_handoff"],
            ),
            self._terms_check(
                "scripts_present",
                "Verification scripts present",
                "scripts",
                [
                    "app/evals/run_eval.py",
                    "app/evals/run_red_team.py",
                    "app/demo.py",
                    "scripts/dashboard_smoke.py",
                    "Makefile",
                ],
                ["run_eval", "run_red_team", "dashboard_smoke", "final-pack"],
            ),
            self._dashboard_script_check(dashboard_smoke),
            self._terms_check(
                "generated_artifact_directory_docs",
                "Generated artifact directory docs",
                "artifacts",
                ["README.md", "docs/api.md", "docs/architecture.md", ".gitignore"],
                ["storage/final_handoff", "final_handoff", "storage/"],
            ),
            self._terms_check(
                "rag_eval_red_team_local_mock_clarity",
                "RAG/eval/red-team/local mock limitation clarity",
                "limitations",
                ["README.md", "docs/evaluation.md", "docs/architecture.md"],
                ["RAG", "eval", "red-team", "local/mock", "MockLLMProvider", "missing-evidence"],
            ),
            self._terms_check(
                "azure_optional_notes",
                "Azure optional notes",
                "limitations",
                ["README.md", "docs/azure-deployment-notes.md", "docs/architecture.md"],
                ["Azure remains optional", "No Azure dependency", "Azure OpenAI", "Azure AI Search"],
            ),
            self._final_smoke_check(smoke_matrix),
            self._final_artifact_inventory_check(artifact_inventory),
        ]

    def _terms_check(
        self,
        check_id: str,
        name: str,
        category: str,
        paths: list[str],
        terms: list[str],
    ) -> FinalAuditCheck:
        missing_paths = [path for path in paths if not Path(path).exists()]
        combined = "\n".join(self._read(path) for path in paths)
        lower = combined.lower()
        missing_terms = [term for term in terms if term.lower() not in lower]
        return FinalAuditCheck(
            check_id=check_id,
            name=name,
            category=category,
            status="pass" if not missing_paths and not missing_terms else "fail",
            evidence_paths=paths,
            missing_paths=missing_paths,
            required_terms=terms,
            missing_terms=missing_terms,
            details={"terms_found": [term for term in terms if term not in missing_terms]},
            remediation=[f"Add or align claim for `{term}`." for term in missing_terms],
        )

    def _dashboard_script_check(self, dashboard_smoke: DashboardSmokeResponse) -> FinalAuditCheck:
        script_path = Path("scripts/dashboard_smoke.py")
        missing_terms = []
        if dashboard_smoke.status != "pass":
            missing_terms.append("Dashboard Smoke PASS status")
        if "python scripts\\dashboard_smoke.py" not in "\n".join(dashboard_smoke.local_run_commands):
            missing_terms.append("dashboard smoke script command")
        return FinalAuditCheck(
            check_id="dashboard_smoke_script_present",
            name="Dashboard smoke script present",
            category="scripts",
            status="pass" if script_path.exists() and not missing_terms else "fail",
            evidence_paths=["scripts/dashboard_smoke.py", "app/services/ui_verification.py"],
            missing_paths=[] if script_path.exists() else ["scripts/dashboard_smoke.py"],
            required_terms=["python scripts\\dashboard_smoke.py", "Dashboard Smoke status pass"],
            missing_terms=missing_terms,
            details={
                "dashboard_smoke_status": dashboard_smoke.status,
                "view_count": dashboard_smoke.summary["view_count"],
                "endpoint_count": dashboard_smoke.summary["endpoint_count"],
            },
            remediation=["Restore scripts/dashboard_smoke.py or update UI smoke specs."] if missing_terms else [],
        )

    def _final_smoke_check(self, smoke_matrix: SmokeMatrixResponse) -> FinalAuditCheck:
        paths = {row.path for row in smoke_matrix.rows}
        required = {"/handoff/final-audit", "/handoff/final-pack"}
        missing = sorted(required - paths)
        return FinalAuditCheck(
            check_id="final_endpoints_in_smoke_matrix",
            name="Final endpoints in smoke matrix",
            category="api",
            status="pass" if not missing else "fail",
            evidence_paths=["app/services/launch_checklist.py"],
            required_terms=sorted(required),
            missing_terms=missing,
            details={
                "endpoint_count": smoke_matrix.readiness_summary.total_endpoints,
                "final_endpoints_present": sorted(required & paths),
            },
            remediation=["Add final handoff endpoints to LaunchChecklistService._smoke_rows()."] if missing else [],
        )

    def _final_artifact_inventory_check(self, artifact_inventory: ArtifactInventoryResponse) -> FinalAuditCheck:
        keys = {item.key for item in artifact_inventory.directories}
        missing = [] if "final_handoff" in keys else ["final_handoff"]
        return FinalAuditCheck(
            check_id="final_handoff_artifact_inventory",
            name="Final handoff artifact inventory",
            category="artifacts",
            status="pass" if not missing else "fail",
            evidence_paths=["app/services/artifact_inventory.py"],
            required_terms=["final_handoff", "storage/final_handoff"],
            missing_terms=missing,
            details={
                "directory_count": artifact_inventory.total_directories,
                "ignored_status": artifact_inventory.ignored_status,
            },
            remediation=["Add final_handoff to ArtifactInventoryService._artifact_specs()."] if missing else [],
        )

    def _endpoint_inventory(self, smoke_matrix: SmokeMatrixResponse) -> dict[str, Any]:
        rows = [row.model_dump(mode="json") for row in smoke_matrix.rows]
        final_rows = [row for row in rows if row["path"].startswith("/handoff/final")]
        categories: dict[str, int] = {}
        for row in rows:
            categories[row["category"]] = categories.get(row["category"], 0) + 1
        return {
            "total_endpoints": len(rows),
            "artifact_writing_endpoints": smoke_matrix.readiness_summary.artifact_writing_endpoints,
            "categories": categories,
            "final_handoff_endpoints": final_rows,
            "recommended_sequence": smoke_matrix.readiness_summary.recommended_sequence,
        }

    def _artifact_inventory(self, inventory: ArtifactInventoryResponse) -> dict[str, Any]:
        final_item = next((item for item in inventory.directories if item.key == "final_handoff"), None)
        return {
            "storage_root": inventory.storage_root,
            "ignored_status": inventory.ignored_status,
            "total_directories": inventory.total_directories,
            "total_files": inventory.total_files,
            "final_handoff": final_item.model_dump(mode="json") if final_item else None,
            "directory_keys": [item.key for item in inventory.directories],
        }

    def _pack_payload(
        self,
        trace_id: str,
        final_audit: FinalAuditResponse,
        smoke_matrix: SmokeMatrixResponse,
        artifact_inventory: ArtifactInventoryResponse,
        dashboard_smoke: DashboardSmokeResponse,
    ) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Final Handoff Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "final_audit": final_audit.model_dump(mode="json"),
            "clone_run_commands": self._clone_run_commands(),
            "end_to_end_verification_order": self._verification_order(),
            "endpoint_inventory_summary": self._endpoint_inventory(smoke_matrix),
            "artifact_inventory_summary": self._artifact_inventory(artifact_inventory),
            "dashboard_smoke_summary": {
                "status": dashboard_smoke.status,
                "summary": dashboard_smoke.summary,
                "script_command": "python scripts\\dashboard_smoke.py",
                "limitations": dashboard_smoke.limitations,
            },
            "rag_eval_proof_summary": self._rag_eval_proof_summary(),
            "recruiter_final_readme_blurb": self._recruiter_blurb(),
            "limitations": self._limitations(),
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        audit = pack["final_audit"]
        endpoint_summary = pack["endpoint_inventory_summary"]
        artifact_summary = pack["artifact_inventory_summary"]
        dashboard = pack["dashboard_smoke_summary"]
        lines = [
            "# Final Handoff Pack",
            "",
            "## Final Audit",
            "",
            f"- Status: {audit['status']}",
            f"- Score: {audit['score']}",
            f"- Passed checks: {audit['summary']['passed_checks']}",
            f"- Failed checks: {audit['summary']['failed_checks']}",
            "",
            "## Clone and Run Commands",
            "",
        ]
        lines.extend(f"```bash\n{command}\n```" for command in pack["clone_run_commands"])
        lines.extend(["", "## End-to-End Verification Order", ""])
        lines.extend(f"{index}. {item}" for index, item in enumerate(pack["end_to_end_verification_order"], start=1))
        lines.extend(["", "## Endpoint Inventory Summary", ""])
        lines.append(f"- Total endpoints: {endpoint_summary['total_endpoints']}")
        lines.append(f"- Artifact-writing endpoints: {endpoint_summary['artifact_writing_endpoints']}")
        for endpoint in endpoint_summary["final_handoff_endpoints"]:
            lines.append(f"- {endpoint['method']} {endpoint['path']}: {endpoint['expected_result']}")
        lines.extend(["", "## Artifact Inventory Summary", ""])
        lines.append(f"- Storage root: {artifact_summary['storage_root']}")
        lines.append(f"- Ignored status: {artifact_summary['ignored_status']}")
        lines.append(f"- Directories: {artifact_summary['total_directories']}")
        lines.append(f"- Files: {artifact_summary['total_files']}")
        if artifact_summary["final_handoff"]:
            item = artifact_summary["final_handoff"]
            lines.append(f"- final_handoff: {item['directory']} ({item['file_count']} files)")
        lines.extend(["", "## Dashboard Smoke Summary", ""])
        lines.append(f"- Status: {dashboard['status']}")
        lines.append(f"- Command: `{dashboard['script_command']}`")
        lines.append(
            "- Coverage: "
            f"views={dashboard['summary']['views_present']}/{dashboard['summary']['view_count']} "
            f"endpoints={dashboard['summary']['endpoints_referenced']}/{dashboard['summary']['endpoint_count']}"
        )
        lines.extend(["", "## RAG/Eval Proof Summary", ""])
        proof = pack["rag_eval_proof_summary"]
        lines.extend(f"- {item}" for item in proof["proof_points"])
        lines.extend(f"```bash\n{command}\n```" for command in proof["commands"])
        lines.extend(["", "## Recruiter-Facing README Blurb", "", pack["recruiter_final_readme_blurb"]])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Final Handoff Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _clone_run_commands(self) -> list[str]:
        return [
            "git clone <repo-url>",
            "cd rfp-response-intelligence-copilot",
            'python -m pip install -e ".[dev]"',
            "python -m pytest -q",
            "python -m ruff check .",
            "python -m app.demo",
            "python -m uvicorn app.main:app --reload",
            "python -m streamlit run dashboard/app.py",
        ]

    def _verification_order(self) -> list[str]:
        return [
            "Install dev dependencies.",
            "Run pytest and ruff.",
            "Run standard eval and red-team eval.",
            "Run dashboard smoke script.",
            "Run python -m app.demo to generate ignored storage artifacts.",
            "Call GET /handoff/final-audit.",
            "Call POST /handoff/final-pack and inspect storage/final_handoff/.",
            "Run the rg proof command and PowerShell artifact listing.",
        ]

    def _verification_commands(self) -> list[str]:
        return [
            "python -m pytest -q",
            "python -m ruff check .",
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            "python scripts\\dashboard_smoke.py",
            "python -m app.demo",
            (
                'rg "handoff/final-audit|handoff/final-pack|Final Handoff|final_handoff|README Consistency|'
                'final audit" app dashboard docs README.md tests scripts sample_data Makefile'
            ),
            (
                "Get-ChildItem -Recurse -File storage\\final_handoff -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _rag_eval_proof_summary(self) -> dict[str, Any]:
        return {
            "proof_points": [
                (
                    "RAG proof is implemented through ingestion, retrieval, cited answers, "
                    "and requirement matrix coverage."
                ),
                (
                    "Standard eval verifies retrieval precision, citation coverage, latency, "
                    "token usage, and cost estimates."
                ),
                "Red-team eval verifies missing-evidence and review-board behavior for unsupported prompts.",
                "Local/mock mode is the default; paid OpenAI, Azure, live Qdrant, and Azure AI Search are optional.",
            ],
            "files": [
                "app/services/retrieval.py",
                "app/services/evaluation.py",
                "app/evals/run_eval.py",
                "app/evals/run_red_team.py",
                "sample_data/eval_dataset.json",
                "sample_data/red_team_questions.json",
            ],
            "commands": [
                "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
                "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            ],
        }

    def _recruiter_blurb(self) -> str:
        return (
            "Final Handoff: a local-first RFP Response Intelligence Copilot with typed FastAPI endpoints, "
            "RAG citations, eval/red-team checks, source-level dashboard smoke, generated Markdown/JSON "
            "artifacts, and a README Consistency final audit that keeps portfolio claims aligned with code."
        )

    def _limitations(self) -> list[str]:
        return [
            (
                "Final audit checks repository text, route metadata, and generated summaries; "
                "it does not execute shell commands."
            ),
            "Generated storage/final_handoff artifacts are ignored by git and should be regenerated locally.",
            "Sample data is fake and compact for deterministic portfolio review.",
            "OpenAI, Azure OpenAI, Azure AI Search, and live Qdrant validation remain optional deployment paths.",
        ]

    def _read(self, path: str) -> str:
        item = Path(path)
        return item.read_text(encoding="utf-8") if item.exists() else ""
