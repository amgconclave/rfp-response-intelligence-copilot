from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    ReviewerCollaborationResponse,
    ReviewerCollaborationWorkflowResponse,
    ReviewerEscalationResponse,
    ReviewerSignoffLedgerResponse,
    ReviewerTraceReconciliationPackResponse,
    ReviewerTraceReconciliationResponse,
)


class ReviewerTraceReconciliationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def reconcile(
        self,
        trace_id: str,
        collaboration: ReviewerCollaborationResponse,
        workflow: ReviewerCollaborationWorkflowResponse,
        ledger: ReviewerSignoffLedgerResponse,
        escalation: ReviewerEscalationResponse,
    ) -> ReviewerTraceReconciliationResponse:
        findings = self._findings(collaboration, workflow, ledger, escalation)
        severity_counts = Counter(finding["severity"] for finding in findings)
        score = max(
            0,
            100
            - severity_counts["critical"] * 25
            - severity_counts["high"] * 15
            - severity_counts["medium"] * 7
            - severity_counts["low"] * 3,
        )
        status = self._status(score, severity_counts)
        return ReviewerTraceReconciliationResponse(
            title="Reviewer Trace Reconciliation",
            status=status,
            reconciliation_score=score,
            summary={
                "finding_count": len(findings),
                "critical_count": severity_counts["critical"],
                "high_count": severity_counts["high"],
                "medium_count": severity_counts["medium"],
                "low_count": severity_counts["low"],
                "board_status": collaboration.board_status,
                "workflow_status": workflow.workflow_status,
                "ledger_status": ledger.ledger_status,
                "escalation_status": escalation.status,
                "patterns": ["trace analysis", "shared state", "governance", "human-in-the-loop"],
            },
            findings=findings,
            source_state=self._source_state(collaboration, workflow, ledger, escalation),
            trace_spans=self._trace_spans(collaboration, workflow, ledger, escalation, findings),
            governance_gates=self._governance_gates(status, findings, collaboration, workflow, ledger, escalation),
            reviewer_followups=self._reviewer_followups(findings),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        reconciliation: ReviewerTraceReconciliationResponse,
        collaboration: ReviewerCollaborationResponse,
        workflow: ReviewerCollaborationWorkflowResponse,
        ledger: ReviewerSignoffLedgerResponse,
        escalation: ReviewerEscalationResponse,
        write_artifact: bool = True,
    ) -> ReviewerTraceReconciliationPackResponse:
        pack = self._pack_payload(trace_id, reconciliation, collaboration, workflow, ledger, escalation)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "reviewer_reconciliation"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"reviewer_trace_reconciliation_{safe_trace_id}.md"
            json_path = pack_dir / f"reviewer_trace_reconciliation_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["reconciliation_markdown"] = artifact_path
            pack["artifact_paths"]["reconciliation_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return ReviewerTraceReconciliationPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            reconciliation=reconciliation,
            collaboration=collaboration,
            workflow=workflow,
            ledger=ledger,
            escalation=escalation,
            trace_id=trace_id,
        )

    def _findings(
        self,
        collaboration: ReviewerCollaborationResponse,
        workflow: ReviewerCollaborationWorkflowResponse,
        ledger: ReviewerSignoffLedgerResponse,
        escalation: ReviewerEscalationResponse,
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        assignment_roles = {assignment.reviewer_role for assignment in collaboration.assignments}
        ledger_roles = {record.reviewer_role for record in ledger.records}
        escalation_roles = {item.reviewer_role for item in escalation.escalation_items}
        approval_path_roles = {str(item.get("reviewer_role", "")) for item in workflow.approval_path}

        missing_ledger_roles = sorted(assignment_roles - ledger_roles)
        if missing_ledger_roles:
            findings.append(
                self._finding(
                    findings,
                    "role_coverage",
                    "high",
                    "assignment_missing_signoff_record",
                    f"Reviewer assignments missing signoff records: {', '.join(missing_ledger_roles)}.",
                    "Regenerate the signoff ledger from the same collaboration board before release.",
                    missing_ledger_roles,
                    ["/rfp/reviewer-signoff-ledger"],
                )
            )

        missing_workflow_roles = sorted(assignment_roles - approval_path_roles)
        if missing_workflow_roles:
            findings.append(
                self._finding(
                    findings,
                    "workflow_coverage",
                    "medium",
                    "assignment_missing_workflow_path",
                    f"Reviewer assignments missing from workflow approval path: {', '.join(missing_workflow_roles)}.",
                    "Replay the reviewer workflow after board updates.",
                    missing_workflow_roles,
                    ["/rfp/reviewer-workflow"],
                )
            )

        if workflow.workflow_status == "ready_for_submission" and ledger.ledger_status != "ready_for_submission":
            findings.append(
                self._finding(
                    findings,
                    "status_consistency",
                    "critical",
                    "workflow_ready_but_signoff_not_ready",
                    f"Workflow is ready but signoff ledger is {ledger.ledger_status}.",
                    "Hold submission until named owner signoff is ready or documented exceptions are attached.",
                    sorted(assignment_roles),
                    ["/rfp/reviewer-workflow", "/rfp/reviewer-signoff-ledger"],
                )
            )

        if collaboration.board_status == "approved" and ledger.summary.get("blocked_count", 0):
            findings.append(
                self._finding(
                    findings,
                    "status_consistency",
                    "high",
                    "approved_board_has_blocked_signoffs",
                    "Collaboration board is approved but signoff ledger still has blocked records.",
                    "Reconcile board approval status with outstanding signoff items.",
                    sorted(ledger_roles),
                    ["/rfp/reviewer-collaboration", "/rfp/reviewer-signoff-ledger"],
                )
            )

        if ledger.summary.get("blocked_count", 0) and escalation.status == "clear":
            findings.append(
                self._finding(
                    findings,
                    "escalation_coverage",
                    "high",
                    "blocked_signoffs_without_escalation",
                    "Signoff ledger has blocked records but escalation plan is clear.",
                    "Regenerate escalations from the current ledger and route blocked owners.",
                    sorted(ledger_roles),
                    ["/rfp/reviewer-escalations"],
                )
            )

        if escalation.summary.get("critical_count", 0) and workflow.workflow_status == "ready_for_submission":
            findings.append(
                self._finding(
                    findings,
                    "release_gate",
                    "critical",
                    "critical_escalation_on_ready_workflow",
                    "Critical reviewer escalation exists while workflow reports ready for submission.",
                    "Treat critical escalation as a release hard stop and replay workflow after closure.",
                    sorted(escalation_roles),
                    ["/rfp/reviewer-escalations", "/rfp/reviewer-workflow"],
                )
            )

        if collaboration.redline_summary.get("critical_or_high_count", 0) and "legal" not in assignment_roles:
            findings.append(
                self._finding(
                    findings,
                    "redline_governance",
                    "high",
                    "high_risk_redline_without_legal_owner",
                    "High-risk redlines exist but no legal reviewer assignment is present.",
                    "Add legal review before approving redline or fallback language.",
                    ["legal"],
                    ["/rfp/reviewer-collaboration"],
                )
            )

        open_blockers = {
            comment.comment_id
            for comment in collaboration.decision_comments
            if comment.status == "open" and comment.sentiment == "blocker"
        }
        ledger_comment_ids = {comment_id for record in ledger.records for comment_id in record.decision_comment_ids}
        missing_comments = sorted(open_blockers - ledger_comment_ids)
        if missing_comments:
            findings.append(
                self._finding(
                    findings,
                    "comment_lineage",
                    "medium",
                    "open_blocker_comments_missing_from_ledger",
                    f"Open blocker comments missing from ledger lineage: {', '.join(missing_comments)}.",
                    "Regenerate the signoff ledger after decision-comment updates.",
                    sorted(assignment_roles),
                    ["/rfp/reviewer-signoff-ledger"],
                    missing_comments,
                )
            )

        return findings

    def _finding(
        self,
        existing: list[dict[str, Any]],
        category: str,
        severity: str,
        status: str,
        finding: str,
        required_action: str,
        reviewer_roles: list[str],
        endpoint_refs: list[str],
        trace_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "finding_id": f"recon_{len(existing) + 1:03d}",
            "category": category,
            "severity": severity,
            "status": status,
            "finding": finding,
            "required_action": required_action,
            "reviewer_roles": reviewer_roles,
            "endpoint_refs": endpoint_refs,
            "trace_refs": trace_refs or [],
        }

    def _source_state(
        self,
        collaboration: ReviewerCollaborationResponse,
        workflow: ReviewerCollaborationWorkflowResponse,
        ledger: ReviewerSignoffLedgerResponse,
        escalation: ReviewerEscalationResponse,
    ) -> dict[str, Any]:
        return {
            "collaboration": {
                "trace_id": collaboration.trace_id,
                "status": collaboration.board_status,
                "assignments": len(collaboration.assignments),
                "comments": len(collaboration.decision_comments),
                "redlines": collaboration.redline_summary.get("redline_count", 0),
            },
            "workflow": {
                "trace_id": workflow.trace_id,
                "status": workflow.workflow_status,
                "current_state": workflow.current_state,
                "checkpoints": len(workflow.checkpoints),
                "transitions": len(workflow.transitions),
            },
            "ledger": {
                "trace_id": ledger.trace_id,
                "status": ledger.ledger_status,
                "records": len(ledger.records),
                "blocked": ledger.summary.get("blocked_count", 0),
                "queue": len(ledger.human_review_queue),
            },
            "escalation": {
                "trace_id": escalation.trace_id,
                "status": escalation.status,
                "current_state": escalation.current_state,
                "items": escalation.summary.get("escalation_count", 0),
                "critical": escalation.summary.get("critical_count", 0),
            },
        }

    def _trace_spans(
        self,
        collaboration: ReviewerCollaborationResponse,
        workflow: ReviewerCollaborationWorkflowResponse,
        ledger: ReviewerSignoffLedgerResponse,
        escalation: ReviewerEscalationResponse,
        findings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "span_id": "reviewer_trace_01_board",
                "source": "reviewer_collaboration",
                "trace_id": collaboration.trace_id,
                "status": collaboration.board_status,
                "observations": [
                    f"{len(collaboration.assignments)} assignments",
                    f"{len(collaboration.decision_comments)} decision comments",
                ],
            },
            {
                "span_id": "reviewer_trace_02_workflow",
                "source": "reviewer_workflow",
                "trace_id": workflow.trace_id,
                "status": workflow.workflow_status,
                "observations": [f"current_state={workflow.current_state}", f"transitions={len(workflow.transitions)}"],
            },
            {
                "span_id": "reviewer_trace_03_signoff",
                "source": "reviewer_signoff",
                "trace_id": ledger.trace_id,
                "status": ledger.ledger_status,
                "observations": [
                    f"records={len(ledger.records)}",
                    f"blocked={ledger.summary.get('blocked_count', 0)}",
                ],
            },
            {
                "span_id": "reviewer_trace_04_escalation",
                "source": "reviewer_escalation",
                "trace_id": escalation.trace_id,
                "status": escalation.status,
                "observations": [
                    f"items={escalation.summary.get('escalation_count', 0)}",
                    f"critical={escalation.summary.get('critical_count', 0)}",
                ],
            },
            {
                "span_id": "reviewer_trace_05_reconciliation",
                "source": "reviewer_trace_reconciliation",
                "trace_id": "local_reconciliation",
                "status": "pass" if not findings else "findings_open",
                "observations": [f"{len(findings)} reconciliation finding(s)"],
            },
        ]

    def _governance_gates(
        self,
        status: str,
        findings: list[dict[str, Any]],
        collaboration: ReviewerCollaborationResponse,
        workflow: ReviewerCollaborationWorkflowResponse,
        ledger: ReviewerSignoffLedgerResponse,
        escalation: ReviewerEscalationResponse,
    ) -> list[dict[str, Any]]:
        critical_or_high = [item for item in findings if item["severity"] in {"critical", "high"}]
        return [
            {
                "gate_id": "recon_gate_01_status_alignment",
                "status": "pass" if not critical_or_high else "blocked",
                "owner_role": "review_board",
                "evidence": f"{len(critical_or_high)} critical/high reconciliation finding(s).",
                "required_action": "Resolve high-severity state mismatches before final signoff.",
            },
            {
                "gate_id": "recon_gate_02_source_freshness",
                "status": "pass",
                "owner_role": "proposal_manager",
                "evidence": (
                    f"Board={collaboration.trace_id}; workflow={workflow.trace_id}; "
                    f"ledger={ledger.trace_id}; escalation={escalation.trace_id}."
                ),
                "required_action": "Regenerate all reviewer artifacts after material board updates.",
            },
            {
                "gate_id": "recon_gate_03_release_recommendation",
                "status": "pass" if status == "pass" else "needs_review",
                "owner_role": "executive_sponsor",
                "evidence": f"Reconciliation status is {status}.",
                "required_action": "Attach reconciliation pack to release review when status is not pass.",
            },
        ]

    def _reviewer_followups(self, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        followups = []
        for finding in findings:
            roles = finding["reviewer_roles"] or ["review_board"]
            followups.append(
                {
                    "finding_id": finding["finding_id"],
                    "owner_role": roles[0],
                    "severity": finding["severity"],
                    "next_action": finding["required_action"],
                    "endpoint_refs": finding["endpoint_refs"],
                }
            )
        return followups

    def _pack_payload(
        self,
        trace_id: str,
        reconciliation: ReviewerTraceReconciliationResponse,
        collaboration: ReviewerCollaborationResponse,
        workflow: ReviewerCollaborationWorkflowResponse,
        ledger: ReviewerSignoffLedgerResponse,
        escalation: ReviewerEscalationResponse,
    ) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Reviewer Trace Reconciliation Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "reconciliation": reconciliation.model_dump(mode="json"),
            "source_context": {
                "board_status": collaboration.board_status,
                "workflow_status": workflow.workflow_status,
                "ledger_status": ledger.ledger_status,
                "escalation_status": escalation.status,
            },
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        reconciliation = pack["reconciliation"]
        summary = reconciliation["summary"]
        lines = [
            "# Reviewer Trace Reconciliation Pack",
            "",
            "## Summary",
            "",
            f"- Status: {reconciliation['status']}",
            f"- Score: {reconciliation['reconciliation_score']}",
            f"- Findings: {summary['finding_count']}",
            f"- Critical: {summary['critical_count']}",
            f"- High: {summary['high_count']}",
            f"- Patterns: {', '.join(summary['patterns'])}",
            "",
            "## Findings",
            "",
        ]
        if reconciliation["findings"]:
            lines.append("| ID | Category | Severity | Status | Finding | Required Action |")
            lines.append("| --- | --- | --- | --- | --- | --- |")
            for finding in reconciliation["findings"]:
                lines.append(
                    "| "
                    f"{finding['finding_id']} | {finding['category']} | {finding['severity']} | "
                    f"{finding['status']} | {self._md(finding['finding'])} | "
                    f"{self._md(finding['required_action'])} |"
                )
        else:
            lines.append("- No cross-artifact mismatches detected.")
        lines.extend(["", "## Source State", ""])
        for name, state in reconciliation["source_state"].items():
            lines.append(f"- {name}: {state}")
        lines.extend(["", "## Governance Gates", ""])
        for gate in reconciliation["governance_gates"]:
            lines.append(f"- {gate['gate_id']} ({gate['status']}): {gate['required_action']}")
        lines.extend(["", "## Trace Spans", ""])
        for span in reconciliation["trace_spans"]:
            lines.append(f"- {span['span_id']} {span['source']} status={span['status']}")
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```bash\n{command}\n```" for command in reconciliation["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in reconciliation["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _status(self, score: int, severity_counts: Counter[str]) -> str:
        if severity_counts["critical"] or score < 70:
            return "blocked"
        if severity_counts["high"] or score < 90:
            return "needs_review"
        return "pass"

    def _local_proof_commands(self) -> list[str]:
        return [
            "python -m pytest tests\\test_reviewer_trace_reconciliation.py -q",
            "python -m pytest -q",
            "python -m ruff check .",
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/reviewer-trace-reconciliation" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/reviewer-trace-reconciliation-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Reconciliation compares deterministic local reviewer artifacts, not external ticket or identity systems.",
            (
                "A passing reconciliation does not replace named human approval for legal, security, finance, "
                "or executive gates."
            ),
            (
                "Findings are derived from supplied or regenerated payloads; regenerate all reviewer artifacts "
                "after input changes."
            ),
            "Artifacts under storage/reviewer_reconciliation are ignored by git and should be regenerated per review.",
        ]

    def _md(self, value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ").strip()
