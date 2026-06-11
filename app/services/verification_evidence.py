from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    ArtifactInventoryResponse,
    DashboardSmokeResponse,
    FinalAuditResponse,
    ReleaseQualityGateResponse,
    VerificationCommandResult,
    VerificationEvidencePackResponse,
    VerificationEvidenceResponse,
)


class VerificationEvidenceService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def evidence(
        self,
        trace_id: str,
        release_gate: ReleaseQualityGateResponse,
        final_audit: FinalAuditResponse,
        dashboard_smoke: DashboardSmokeResponse,
        artifact_inventory: ArtifactInventoryResponse,
        command_results: list[VerificationCommandResult] | None = None,
    ) -> VerificationEvidenceResponse:
        supplied = {item.command_id: item for item in command_results or []}
        command_evidence = [self._command_evidence(row, supplied.get(row["command_id"])) for row in self._commands()]
        summary = self._summary(command_evidence, release_gate, final_audit, dashboard_smoke, artifact_inventory)
        status = self._status(summary, release_gate, final_audit, dashboard_smoke)
        score = self._score(summary, release_gate, final_audit, dashboard_smoke)
        return VerificationEvidenceResponse(
            title="Verification Evidence Ledger",
            status=status,
            score=score,
            summary=summary,
            command_evidence=command_evidence,
            release_gate_snapshot={
                "status": release_gate.status,
                "score": release_gate.score,
                "blockers": release_gate.blockers,
                "warnings": release_gate.warnings,
                "verification_check_count": len(release_gate.verification_checklist),
            },
            final_audit_snapshot={
                "status": final_audit.status,
                "score": final_audit.score,
                "failed_checks": final_audit.summary.get("failed_checks", 0),
                "failed_check_ids": final_audit.summary.get("failed_check_ids", []),
            },
            dashboard_smoke_snapshot={
                "status": dashboard_smoke.status,
                "views_present": dashboard_smoke.summary.get("views_present", 0),
                "view_count": dashboard_smoke.summary.get("view_count", 0),
                "routes_defined": dashboard_smoke.summary.get("routes_defined", 0),
                "endpoint_count": dashboard_smoke.summary.get("endpoint_count", 0),
            },
            artifact_inventory_snapshot={
                "storage_root": artifact_inventory.storage_root,
                "ignored_status": artifact_inventory.ignored_status,
                "total_directories": artifact_inventory.total_directories,
                "total_files": artifact_inventory.total_files,
                "verification_evidence_indexed": any(
                    item.key == "verification_evidence" for item in artifact_inventory.directories
                ),
            },
            reviewer_signoff=self._reviewer_signoff(summary, release_gate, final_audit, dashboard_smoke),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        evidence: VerificationEvidenceResponse,
        write_artifact: bool = True,
    ) -> VerificationEvidencePackResponse:
        pack = self._pack_payload(trace_id, evidence)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "verification_evidence"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"verification_evidence_ledger_{safe_trace_id}.md"
            json_path = pack_dir / f"verification_evidence_ledger_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["verification_evidence_markdown"] = artifact_path
            pack["artifact_paths"]["verification_evidence_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return VerificationEvidencePackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            evidence=evidence,
            trace_id=trace_id,
        )

    def _commands(self) -> list[dict[str, Any]]:
        return [
            {
                "command_id": "pytest",
                "area": "Tests",
                "command": "python -m pytest -q",
                "expected_output": "All tests pass.",
                "required": True,
            },
            {
                "command_id": "ruff",
                "area": "Lint",
                "command": "python -m ruff check .",
                "expected_output": "All checks passed.",
                "required": True,
            },
            {
                "command_id": "standard_eval",
                "area": "Evaluation",
                "command": "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
                "expected_output": "Pass/fail summary: PASS.",
                "required": True,
            },
            {
                "command_id": "red_team",
                "area": "Red team",
                "command": "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
                "expected_output": "Pass/fail summary: PASS.",
                "required": True,
            },
            {
                "command_id": "dashboard_smoke",
                "area": "Dashboard",
                "command": "python scripts\\dashboard_smoke.py",
                "expected_output": "Dashboard smoke status is pass.",
                "required": True,
            },
            {
                "command_id": "demo",
                "area": "Demo",
                "command": "python -m app.demo",
                "expected_output": "Final demo summary prints artifact paths and red_team=True.",
                "required": True,
            },
        ]

    def _command_evidence(
        self,
        row: dict[str, Any],
        result: VerificationCommandResult | None,
    ) -> dict[str, Any]:
        status = result.status if result else "not_recorded"
        observed_output = result.observed_output if result else ""
        notes = list(result.notes) if result else ["Observed output can be supplied after the local command is run."]
        normalized = status.lower()
        passed = normalized in {"pass", "passed", "success", "ok"}
        failed = normalized in {"fail", "failed", "error"}
        if not result:
            evidence_status = "not_recorded"
        elif passed:
            evidence_status = "pass"
        elif failed:
            evidence_status = "fail"
        else:
            evidence_status = "review"
        return {
            **row,
            "status": evidence_status,
            "observed_output": observed_output[:800],
            "duration_seconds": result.duration_seconds if result else None,
            "notes": notes,
        }

    def _summary(
        self,
        command_evidence: list[dict[str, Any]],
        release_gate: ReleaseQualityGateResponse,
        final_audit: FinalAuditResponse,
        dashboard_smoke: DashboardSmokeResponse,
        artifact_inventory: ArtifactInventoryResponse,
    ) -> dict[str, Any]:
        recorded = [row for row in command_evidence if row["status"] != "not_recorded"]
        failed = [row for row in command_evidence if row["status"] == "fail"]
        passed = [row for row in command_evidence if row["status"] == "pass"]
        return {
            "required_command_count": len(command_evidence),
            "recorded_command_count": len(recorded),
            "passed_command_count": len(passed),
            "failed_command_count": len(failed),
            "unrecorded_command_ids": [
                row["command_id"] for row in command_evidence if row["status"] == "not_recorded"
            ],
            "failed_command_ids": [row["command_id"] for row in failed],
            "release_gate_status": release_gate.status,
            "release_gate_score": release_gate.score,
            "final_audit_status": final_audit.status,
            "final_audit_score": final_audit.score,
            "dashboard_smoke_status": dashboard_smoke.status,
            "artifact_directories": artifact_inventory.total_directories,
            "artifact_files": artifact_inventory.total_files,
            "local_mock_default": self.settings.provider_mode == "mock",
            "external_services_required": False,
        }

    def _status(
        self,
        summary: dict[str, Any],
        release_gate: ReleaseQualityGateResponse,
        final_audit: FinalAuditResponse,
        dashboard_smoke: DashboardSmokeResponse,
    ) -> str:
        if summary["failed_command_count"] or release_gate.status == "blocked" or final_audit.status == "needs_work":
            return "blocked"
        if dashboard_smoke.status != "pass":
            return "needs_dashboard_review"
        if summary["recorded_command_count"] < summary["required_command_count"]:
            return "pending_command_evidence"
        return "accepted"

    def _score(
        self,
        summary: dict[str, Any],
        release_gate: ReleaseQualityGateResponse,
        final_audit: FinalAuditResponse,
        dashboard_smoke: DashboardSmokeResponse,
    ) -> int:
        score = min(release_gate.score, final_audit.score)
        score -= summary["failed_command_count"] * 15
        score -= len(summary["unrecorded_command_ids"]) * 3
        if dashboard_smoke.status != "pass":
            score -= 10
        if not summary["local_mock_default"]:
            score -= 5
        return max(0, min(100, score))

    def _reviewer_signoff(
        self,
        summary: dict[str, Any],
        release_gate: ReleaseQualityGateResponse,
        final_audit: FinalAuditResponse,
        dashboard_smoke: DashboardSmokeResponse,
    ) -> list[dict[str, Any]]:
        return [
            {
                "role": "Engineering reviewer",
                "status": "ready" if not summary["failed_command_count"] else "blocked",
                "required_action": "Review command evidence rows and inspect failed command output.",
            },
            {
                "role": "Portfolio reviewer",
                "status": "ready" if release_gate.status in {"ready", "ready_with_warnings"} else "review",
                "required_action": "Inspect Release Pack, Final Handoff Pack, and generated storage artifacts.",
            },
            {
                "role": "Dashboard reviewer",
                "status": "ready" if dashboard_smoke.status == "pass" else "review",
                "required_action": "Run dashboard smoke and inspect Streamlit screenshots manually if needed.",
            },
            {
                "role": "Documentation reviewer",
                "status": "ready" if final_audit.status == "pass" else "review",
                "required_action": "Resolve README/docs consistency checks before external handoff.",
            },
        ]

    def _pack_payload(self, trace_id: str, evidence: VerificationEvidenceResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Verification Evidence Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "evidence": evidence.model_dump(mode="json"),
            "reviewer_controls": [
                "The API does not execute shell commands; paste observed results after running commands locally.",
                "Treat unrecorded required commands as pending evidence before external review.",
                "Regenerate this pack after changing tests, eval datasets, dashboard tabs, docs, or demo flow.",
                "Keep storage/ artifacts ignored and regenerate them locally for each reviewer handoff.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        evidence = pack["evidence"]
        summary = evidence["summary"]
        lines = [
            "# Verification Evidence Pack",
            "",
            "## Summary",
            "",
            f"- Status: {evidence['status']}",
            f"- Score: {evidence['score']}",
            f"- Recorded commands: {summary['recorded_command_count']}/{summary['required_command_count']}",
            f"- Failed commands: {summary['failed_command_count']}",
            f"- Release gate: {summary['release_gate_status']}/{summary['release_gate_score']}",
            f"- Final audit: {summary['final_audit_status']}/{summary['final_audit_score']}",
            f"- Dashboard smoke: {summary['dashboard_smoke_status']}",
            "",
            "## Command Evidence",
            "",
            "| Command | Area | Status | Expected output | Observed output |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in evidence["command_evidence"]:
            lines.append(
                f"| `{self._md(row['command'])}` | {self._md(row['area'])} | {row['status']} | "
                f"{self._md(row['expected_output'])} | {self._md(row['observed_output'] or 'not recorded')} |"
            )
        lines.extend(["", "## Reviewer Signoff", ""])
        for row in evidence["reviewer_signoff"]:
            lines.append(f"- {row['role']} ({row['status']}): {self._md(row['required_action'])}")
        lines.extend(["", "## Reviewer Controls", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_controls"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in evidence["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {self._md(item)}" for item in evidence["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Generated Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/ops/verification-evidence" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/ops/verification-evidence-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m pytest -q",
            "python -m ruff check .",
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            "python scripts\\dashboard_smoke.py",
            "python -m app.demo",
        ]

    def _limitations(self) -> list[str]:
        return [
            "The ledger records expected and observed command evidence; it does not execute shell commands.",
            "Observed outputs are reviewer-supplied summaries and should be checked against terminal logs when needed.",
            "Generated storage/verification_evidence artifacts are ignored by git and should be regenerated locally.",
            "External OpenAI, Azure, live Qdrant, CRM, legal, and ticketing systems remain optional.",
        ]

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
