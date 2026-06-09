from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.models.api import ReleaseQualityGateResponse, SmokeMatrixResponse


class ReleaseService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def quality_gate(self, smoke_matrix: SmokeMatrixResponse, trace_id: str) -> ReleaseQualityGateResponse:
        checks = self._verification_checklist()
        coverage = self._coverage(smoke_matrix)
        artifact_coverage = self._artifact_coverage(smoke_matrix)
        blockers = self._blockers(checks, coverage)
        warnings = self._warnings(checks, artifact_coverage)
        score = self._score(checks, coverage, artifact_coverage, blockers, warnings)
        status = self._status(score, blockers)
        publish_readiness = self._publish_readiness(status, score, blockers, warnings, coverage, artifact_coverage)
        return ReleaseQualityGateResponse(
            title="Release Candidate Quality Gate",
            status=status,
            score=score,
            blockers=blockers,
            warnings=warnings,
            verification_checklist=checks,
            coverage=coverage,
            artifact_coverage=artifact_coverage,
            runtime_notes=self._runtime_notes(),
            publish_readiness=publish_readiness,
            trace_id=trace_id,
        )

    def publish_pack(
        self,
        gate: ReleaseQualityGateResponse,
        smoke_matrix: SmokeMatrixResponse,
        trace_id: str,
        write_artifact: bool = True,
    ) -> tuple[str | None, str | None, str, dict[str, Any]]:
        pack = self._pack_payload(gate, smoke_matrix, trace_id)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "release_packs"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"github_publish_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"github_publish_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["publish_pack_markdown"] = artifact_path
            pack["artifact_paths"]["publish_pack_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return artifact_path, json_artifact_path, markdown, pack

    def _verification_checklist(self) -> list[dict[str, Any]]:
        items = [
            self._check(
                "pytest",
                "Tests",
                "python -m pytest -q",
                ["tests/test_api_flows.py", "tests/test_ops_launch.py"],
            ),
            self._check("ruff", "Lint", "python -m ruff check .", ["pyproject.toml"]),
            self._check(
                "standard_eval",
                "Evaluation",
                "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
                ["app/evals/run_eval.py", "sample_data/eval_dataset.json"],
            ),
            self._check(
                "red_team",
                "Red team",
                "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
                ["app/evals/run_red_team.py", "sample_data/red_team_questions.json"],
            ),
            self._check(
                "rag_coverage",
                "RAG corpus coverage",
                "make rag-coverage-pack",
                ["app/services/corpus_coverage.py", "sample_data/implementation_guide.md"],
            ),
            self._check(
                "compliance_control_pack",
                "Compliance evidence",
                "make compliance-pack",
                ["app/services/compliance.py", "sample_data/ai_governance_security.md"],
            ),
            self._check(
                "procurement_approval_pack",
                "Procurement approval workflow",
                "make procurement-pack",
                ["app/services/procurement.py", "sample_data/approved_responses.json"],
            ),
            self._check(
                "bid_roi_pack",
                "Bid/No-Bid ROI Impact",
                "make bid-roi-pack",
                ["app/services/bid_simulator.py", "sample_data/customer_profiles.json"],
            ),
            self._check("demo", "Demo", "python -m app.demo", ["app/demo.py"]),
            self._check("readme", "README", "rg \"Release Candidate|Publish Pack\" README.md", ["README.md"]),
            self._check(
                "api_docs",
                "API docs",
                'rg "release/quality-gate|release/publish-pack" docs/api.md',
                ["docs/api.md"],
            ),
            self._check(
                "architecture_docs",
                "Architecture docs",
                'rg "ReleaseService|release_packs" docs/architecture.md',
                ["docs/architecture.md"],
            ),
            self._check(
                "evaluation_docs",
                "Evaluation docs",
                'rg "Release Candidate|Publish Pack" docs/evaluation.md',
                ["docs/evaluation.md"],
            ),
            self._check("make_targets", "Makefile", "make release-pack", ["Makefile"]),
            self._check("ci", "CI", "GitHub Actions workflow", [".github/workflows/ci.yml"]),
        ]
        return items

    def _check(self, check_id: str, area: str, command: str, paths: list[str]) -> dict[str, Any]:
        missing = [path for path in paths if not Path(path).exists()]
        return {
            "check_id": check_id,
            "area": area,
            "status": "pass" if not missing else "blocker",
            "command": command,
            "evidence_paths": paths,
            "missing_paths": missing,
            "expected_output": self._expected_output(check_id),
        }

    def _expected_output(self, check_id: str) -> str:
        outputs = {
            "pytest": "All tests pass.",
            "ruff": "All checks passed.",
            "standard_eval": "Pass/fail summary: PASS.",
            "red_team": "Pass/fail summary: PASS.",
            "rag_coverage": "RAG Eval Coverage Pack writes Markdown and JSON under storage/rag_coverage.",
            "compliance_control_pack": (
                "Compliance control pack writes Markdown and JSON under storage/compliance_packs."
            ),
            "procurement_approval_pack": (
                "Procurement Approval Workflow Pack writes Markdown and JSON under storage/procurement_packs."
            ),
            "bid_roi_pack": "ROI Impact Pack writes Markdown and JSON under storage/bid_packs.",
            "demo": "Final demo summary plus release gate status and publish pack path.",
            "readme": "README documents Release Candidate and Publish Pack workflow.",
            "api_docs": "API docs list /release/quality-gate and /release/publish-pack.",
            "architecture_docs": "Architecture docs include ReleaseService and release_packs artifacts.",
            "evaluation_docs": "Evaluation docs include the release gate pass criteria.",
            "make_targets": "Makefile has release-gate and release-pack targets.",
            "ci": "CI workflow is present for GitHub publishing.",
        }
        return outputs.get(check_id, "Check completes successfully.")

    def _coverage(self, smoke_matrix: SmokeMatrixResponse) -> dict[str, Any]:
        rows = [row.model_dump(mode="json") for row in smoke_matrix.rows]
        paths = {row["path"] for row in rows}
        categories = sorted({row["category"] for row in rows})
        docs = {
            "README.md": Path("README.md").exists(),
            "docs/api.md": Path("docs/api.md").exists(),
            "docs/architecture.md": Path("docs/architecture.md").exists(),
            "docs/evaluation.md": Path("docs/evaluation.md").exists(),
        }
        tests = sorted(str(path) for path in Path("tests").glob("test_*.py"))
        return {
            "ci": {
                "workflow_present": Path(".github/workflows/ci.yml").exists(),
                "workflow_path": ".github/workflows/ci.yml",
            },
            "docs": {
                "required_docs": docs,
                "complete": all(docs.values()),
            },
            "tests": {
                "test_file_count": len(tests),
                "test_files": tests,
                "has_release_tests": Path("tests/test_release.py").exists(),
            },
            "eval": {
                "standard_dataset": Path("sample_data/eval_dataset.json").exists(),
                "red_team_dataset": Path("sample_data/red_team_questions.json").exists(),
                "eval_runner": Path("app/evals/run_eval.py").exists(),
                "red_team_runner": Path("app/evals/run_red_team.py").exists(),
            },
            "red_team": {
                "dataset_path": "sample_data/red_team_questions.json",
                "runner_path": "app/evals/run_red_team.py",
                "local_only": True,
            },
            "demo": {
                "demo_command": "python -m app.demo",
                "demo_file_present": Path("app/demo.py").exists(),
            },
            "rag_coverage": {
                "service_path": "app/services/corpus_coverage.py",
                "artifact_root": str((self.settings.storage_dir / "rag_coverage").resolve()),
                "endpoints": ["/rag/corpus-coverage", "/rag/eval-coverage-pack"],
            },
            "compliance": {
                "service_path": "app/services/compliance.py",
                "artifact_root": str((self.settings.storage_dir / "compliance_packs").resolve()),
                "endpoints": ["/compliance/evidence-matrix", "/compliance/control-pack"],
            },
            "procurement": {
                "service_path": "app/services/procurement.py",
                "artifact_root": str((self.settings.storage_dir / "procurement_packs").resolve()),
                "endpoints": ["/procurement/question-risk", "/procurement/approval-pack"],
            },
            "bid": {
                "service_path": "app/services/bid_simulator.py",
                "artifact_root": str((self.settings.storage_dir / "bid_packs").resolve()),
                "endpoints": ["/bid/scenario-analysis", "/bid/roi-pack"],
            },
            "api": {
                "endpoint_count": len(paths),
                "artifact_endpoint_count": smoke_matrix.readiness_summary.artifact_writing_endpoints,
                "categories": categories,
                "release_endpoints": {
                    "/release/quality-gate": "/release/quality-gate" in paths,
                    "/release/publish-pack": "/release/publish-pack" in paths,
                },
            },
        }

    def _artifact_coverage(self, smoke_matrix: SmokeMatrixResponse) -> dict[str, Any]:
        expected_dirs = {
            "exports": "Response export packs",
            "handoffs": "Stakeholder handoff boards",
            "reports": "Executive risk reports",
            "pricing_memos": "Pricing risk memos",
            "negotiation_briefs": "Contract negotiation briefs",
            "source_requests": "Evidence source request packs",
            "submission_calendars": "Submission calendar packs",
            "submission_memos": "Executive submission memos",
            "leadership_briefs": "Leadership briefs",
            "demo_scripts": "Demo scripts",
            "launch_checklists": "Launch checklists",
            "rag_coverage": "RAG corpus expansion and eval coverage artifacts",
            "compliance_packs": "Compliance evidence matrix and control mapping packs",
            "procurement_packs": "Procurement Q&A risk and approval workflow packs",
            "bid_packs": "Bid/No-Bid scenario simulator and ROI Impact packs",
            "portfolio_packs": "Portfolio interview packs",
            "release_packs": "GitHub publish packs",
            "ui_verification": "Dashboard Smoke and UI verification packs",
            "artifact_indexes": "Artifact Inventory and README Checklist packs",
            "final_handoff": "README Consistency final audit and Final Handoff Pack",
        }
        dirs: dict[str, Any] = {}
        for name, description in expected_dirs.items():
            path = self.settings.storage_dir / name
            files = sorted(
                (item for item in path.glob("*") if item.is_file()),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            ) if path.exists() else []
            dirs[name] = {
                "description": description,
                "path": str(path.resolve()),
                "exists": path.exists(),
                "file_count": len(files),
                "latest_files": [str(item.resolve()) for item in files[:3]],
            }
        expectations = sorted(
            {
                expectation
                for row in smoke_matrix.rows
                for expectation in row.required_artifact_expectations
            }
        )
        return {
            "expected_artifact_dirs": dirs,
            "smoke_matrix_artifact_expectations": expectations,
            "release_pack_path": str((self.settings.storage_dir / "release_packs").resolve()),
            "ignored_by_git": "storage/",
        }

    def _blockers(self, checks: list[dict[str, Any]], coverage: dict[str, Any]) -> list[str]:
        blockers = [
            f"{check['area']} missing required paths: {', '.join(check['missing_paths'])}"
            for check in checks
            if check["missing_paths"]
        ]
        release_endpoints = coverage["api"]["release_endpoints"]
        if not all(release_endpoints.values()):
            blockers.append("Release endpoints are not present in the API smoke matrix.")
        if not coverage["docs"]["complete"]:
            blockers.append("Required README/API/architecture/evaluation docs are incomplete.")
        if not coverage["tests"]["has_release_tests"]:
            blockers.append("Release endpoint tests are missing.")
        return blockers

    def _warnings(self, checks: list[dict[str, Any]], artifact_coverage: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        if self.settings.provider_mode != "mock":
            warnings.append("Provider mode is not mock; local GitHub portfolio verification should default to mock.")
        if self.settings.vector_store_mode not in {"qdrant", "faiss"}:
            warnings.append(
                "Vector store mode is unusual for local verification; expected qdrant or faiss adapter mode."
            )
        empty_dirs = [
            name
            for name, details in artifact_coverage["expected_artifact_dirs"].items()
            if name != "release_packs" and details["file_count"] == 0
        ]
        if empty_dirs:
            warnings.append(
                "Some artifact directories are empty before running the demo: " + ", ".join(empty_dirs[:6])
            )
        if any(check["status"] == "blocker" for check in checks):
            warnings.append("Run the verification commands after resolving blocker checks.")
        return warnings

    def _score(
        self,
        checks: list[dict[str, Any]],
        coverage: dict[str, Any],
        artifact_coverage: dict[str, Any],
        blockers: list[str],
        warnings: list[str],
    ) -> int:
        score = 100
        score -= 12 * len(blockers)
        score -= 3 * len(warnings)
        score -= max(0, 5 - coverage["tests"]["test_file_count"]) * 2
        if coverage["api"]["endpoint_count"] < 35:
            score -= 5
        if coverage["api"]["artifact_endpoint_count"] < 12:
            score -= 5
        if artifact_coverage["expected_artifact_dirs"]["release_packs"]["file_count"] == 0:
            score -= 2
        missing_checks = sum(1 for check in checks if check["status"] != "pass")
        score -= missing_checks * 4
        return max(0, min(100, score))

    def _status(self, score: int, blockers: list[str]) -> str:
        if blockers:
            return "blocked"
        if score >= 90:
            return "ready"
        if score >= 75:
            return "ready_with_warnings"
        return "needs_work"

    def _publish_readiness(
        self,
        status: str,
        score: int,
        blockers: list[str],
        warnings: list[str],
        coverage: dict[str, Any],
        artifact_coverage: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "ready_to_publish": status in {"ready", "ready_with_warnings"} and not blockers,
            "recommended_branch": "dev/release-candidate-quality-gate",
            "minimum_score": 90,
            "current_score": score,
            "required_before_push": [
                "Run pytest, ruff, standard eval, red-team eval, demo, release gate, and publish pack commands.",
                "Review generated storage/release_packs Markdown and JSON artifacts.",
                "Confirm no secrets or generated storage artifacts are staged for GitHub.",
                "Capture dashboard screenshots or leave the provided manual verification placeholders for reviewers.",
            ],
            "github_repo_checklist": self._github_repo_checklist(blockers, warnings),
            "commit_push_notes": [
                "Commit code, docs, tests, and Makefile updates only; keep storage/ ignored.",
                "Use the release pack artifact as a local reviewer aid, not as a committed file.",
                "Push after the acceptance commands pass locally or in CI.",
            ],
            "coverage_snapshot": {
                "endpoint_count": coverage["api"]["endpoint_count"],
                "artifact_endpoint_count": coverage["api"]["artifact_endpoint_count"],
                "release_pack_path": artifact_coverage["release_pack_path"],
            },
        }

    def _github_repo_checklist(self, blockers: list[str], warnings: list[str]) -> list[dict[str, Any]]:
        return [
            {
                "item": "README explains value proposition, local commands, endpoints, screenshots, and limitations.",
                "status": "ready",
            },
            {
                "item": "Docs cover API, architecture, evaluation, and release publish workflow.",
                "status": "ready",
            },
            {
                "item": "Tests and CI are available for local and GitHub verification.",
                "status": "ready" if not blockers else "review",
            },
            {"item": "Generated artifacts live under ignored storage/ directories.", "status": "ready"},
            {
                "item": "No paid OpenAI, Azure, or Qdrant service is required for default verification.",
                "status": "ready",
            },
            {"item": "Warnings have been reviewed.", "status": "ready" if not warnings else "review"},
        ]

    def _runtime_notes(self) -> list[str]:
        return [
            (
                f"Provider mode: {self.settings.provider_mode}. "
                "Mock mode is the portfolio default and needs no paid API key."
            ),
            (
                f"Vector store mode: {self.settings.vector_store_mode}. "
                "Local adapter fallback keeps tests and demos deterministic."
            ),
            f"Storage root: {self.settings.storage_dir.resolve()}. The storage/ directory is ignored by git.",
            "OpenAI, Azure OpenAI, Azure AI Search, and live Qdrant are optional adapters, not release prerequisites.",
        ]

    def _pack_payload(
        self,
        gate: ReleaseQualityGateResponse,
        smoke_matrix: SmokeMatrixResponse,
        trace_id: str,
    ) -> dict[str, Any]:
        endpoint_inventory = [
            {
                "method": row.method,
                "path": row.path,
                "category": row.category,
                "expected_result": row.expected_result,
                "artifact_expectations": row.required_artifact_expectations,
            }
            for row in smoke_matrix.rows
        ]
        return {
            "trace_id": trace_id,
            "title": "Release Candidate GitHub Publish Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "release_summary": {
                "project": "RFP Response Intelligence Copilot",
                "status": gate.status,
                "score": gate.score,
                "one_liner": (
                    "Local-first enterprise RFP response copilot with RAG, citations, red-team checks, "
                    "workflow artifacts, release gate, and GitHub publish guidance."
                ),
                "blockers": gate.blockers,
                "warnings": gate.warnings,
            },
            "setup_demo_commands": [
                "python -m pip install -e \".[dev]\"",
                "python -m uvicorn app.main:app --reload",
                "python -m streamlit run dashboard/app.py",
                "python -m app.demo",
            ],
            "verification_commands": [
                "python -m pytest -q",
                "python -m ruff check .",
                "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
                "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
                "make rag-coverage-pack",
                "make compliance-pack",
                "make procurement-pack",
                "make bid-roi-pack",
                "python -m app.demo",
                (
                    'rg "release/quality-gate|release/publish-pack|Release Candidate|Publish Pack|'
                    'release_packs|release gate" app dashboard docs README.md tests sample_data Makefile'
                ),
            ],
            "expected_outputs": {
                "pytest": "All tests pass.",
                "ruff": "All checks passed.",
                "standard_eval": "Pass/fail summary: PASS.",
                "red_team": "Pass/fail summary: PASS.",
                "rag_coverage": "storage/rag_coverage contains Markdown and JSON coverage pack files.",
                "compliance_pack": "storage/compliance_packs contains Markdown and JSON control mapping files.",
                "procurement_pack": "storage/procurement_packs contains Markdown and JSON approval workflow files.",
                "bid_roi_pack": "storage/bid_packs contains Markdown and JSON ROI Impact Pack files.",
                "demo": "Prints release gate status/score and publish pack path.",
                "artifact_listing": "storage/release_packs contains Markdown and JSON publish pack files.",
            },
            "endpoint_inventory": endpoint_inventory,
            "artifact_inventory": gate.artifact_coverage,
            "screenshots_manual_verification_placeholders": [
                "Dashboard Release Pack tab showing gate status, score, warnings, commands, and artifact path.",
                "FastAPI docs showing /release/quality-gate and /release/publish-pack.",
                "Terminal output for pytest, ruff, eval, red-team, and demo commands.",
                "Generated Markdown publish pack opened locally from storage/release_packs/.",
            ],
            "github_repo_checklist": gate.publish_readiness["github_repo_checklist"],
            "commit_push_readiness_notes": gate.publish_readiness["commit_push_notes"],
            "recruiter_review_notes": [
                "Start with README 30-second demo, then show Release Pack tab and generated publish pack.",
                "Emphasize deterministic local/mock behavior and optional cloud adapters.",
                "Point reviewers to tests, evals, red-team datasets, docs, and storage artifact examples.",
                "Use the endpoint inventory to explain breadth without needing a live paid service.",
            ],
            "known_limitations": [
                "Generated storage artifacts are intentionally ignored and should be regenerated locally.",
                "Sample data is fake and compact; production deployment would connect real source systems.",
                (
                    "Mock provider is deterministic for portfolio review; OpenAI/Azure behavior requires "
                    "separate credentials."
                ),
                (
                    "The release gate validates local readiness signals and expected commands; "
                    "it does not run shell commands itself."
                ),
            ],
            "quality_gate": gate.model_dump(mode="json"),
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        summary = pack["release_summary"]
        lines = [
            "# Release Candidate GitHub Publish Pack",
            "",
            "## Release Summary",
            "",
            f"- Project: {summary['project']}",
            f"- Status: {summary['status']}",
            f"- Score: {summary['score']}",
            f"- Summary: {summary['one_liner']}",
            "",
            "## Blockers and Warnings",
            "",
        ]
        lines.extend(f"- Blocker: {item}" for item in summary["blockers"] or ["None"])
        lines.extend(f"- Warning: {item}" for item in summary["warnings"] or ["None"])
        lines.extend(["", "## Setup and Demo Commands", ""])
        lines.extend(f"```bash\n{command}\n```" for command in pack["setup_demo_commands"])
        lines.extend(["", "## Verification Commands", ""])
        lines.extend(f"```bash\n{command}\n```" for command in pack["verification_commands"])
        lines.extend(["", "## Expected Outputs", ""])
        lines.extend(f"- {label}: {value}" for label, value in pack["expected_outputs"].items())
        lines.extend(["", "## Endpoint Inventory", ""])
        lines.append("| Method | Path | Category | Expected Result | Artifacts |")
        lines.append("| --- | --- | --- | --- | --- |")
        for endpoint in pack["endpoint_inventory"]:
            artifacts = ", ".join(endpoint["artifact_expectations"]) or "None"
            lines.append(
                f"| {endpoint['method']} | {endpoint['path']} | {endpoint['category']} | "
                f"{endpoint['expected_result']} | {artifacts} |"
            )
        lines.extend(["", "## Artifact Inventory", ""])
        for name, details in pack["artifact_inventory"]["expected_artifact_dirs"].items():
            lines.append(f"- {name}: {details['path']} ({details['file_count']} files)")
        lines.extend(["", "## Screenshots and Manual Verification Placeholders", ""])
        lines.extend(f"- [ ] {item}" for item in pack["screenshots_manual_verification_placeholders"])
        lines.extend(["", "## GitHub Repo Checklist", ""])
        lines.extend(f"- [{item['status']}] {item['item']}" for item in pack["github_repo_checklist"])
        lines.extend(["", "## Commit and Push Readiness Notes", ""])
        lines.extend(f"- {item}" for item in pack["commit_push_readiness_notes"])
        lines.extend(["", "## Recruiter Review Notes", ""])
        lines.extend(f"- {item}" for item in pack["recruiter_review_notes"])
        lines.extend(["", "## Known Limitations", ""])
        lines.extend(f"- {item}" for item in pack["known_limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Publish Pack Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"
