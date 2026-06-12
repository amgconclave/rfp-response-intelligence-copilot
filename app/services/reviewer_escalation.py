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
    ReviewerEscalationCheckpoint,
    ReviewerEscalationItem,
    ReviewerEscalationPackResponse,
    ReviewerEscalationResponse,
    ReviewerSignoffLedgerResponse,
)

ESCALATION_MANAGERS = {
    "sales": "proposal_manager",
    "solutions": "proposal_manager",
    "security": "security_director",
    "legal": "general_counsel",
    "product": "product_lead",
    "engineering": "engineering_manager",
    "finance": "finance_director",
    "executive_sponsor": "cro",
    "review_board": "proposal_manager",
}


class ReviewerEscalationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def escalation_plan(
        self,
        trace_id: str,
        collaboration: ReviewerCollaborationResponse,
        workflow: ReviewerCollaborationWorkflowResponse,
        ledger: ReviewerSignoffLedgerResponse,
        sla_hours: dict[str, int] | None = None,
    ) -> ReviewerEscalationResponse:
        sla = sla_hours or {}
        items = self._items(collaboration, workflow, ledger, sla)
        summary = self._summary(items, collaboration, workflow, ledger)
        checkpoints = self._checkpoints(items, summary)
        return ReviewerEscalationResponse(
            title="Reviewer SLA Escalation Plan",
            status=summary["status"],
            current_state=self._current_state(checkpoints),
            escalation_items=items,
            summary=summary,
            checkpoints=checkpoints,
            transitions=self._transitions(checkpoints),
            role_crew_queue=self._role_crew_queue(items),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        escalation: ReviewerEscalationResponse,
        collaboration: ReviewerCollaborationResponse,
        workflow: ReviewerCollaborationWorkflowResponse,
        ledger: ReviewerSignoffLedgerResponse,
        write_artifact: bool = True,
    ) -> ReviewerEscalationPackResponse:
        pack = self._pack_payload(trace_id, escalation, collaboration, workflow, ledger)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "reviewer_escalations"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"reviewer_escalation_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"reviewer_escalation_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["reviewer_escalation_markdown"] = artifact_path
            pack["artifact_paths"]["reviewer_escalation_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return ReviewerEscalationPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            escalation=escalation,
            collaboration=collaboration,
            workflow=workflow,
            ledger=ledger,
            trace_id=trace_id,
        )

    def _items(
        self,
        collaboration: ReviewerCollaborationResponse,
        workflow: ReviewerCollaborationWorkflowResponse,
        ledger: ReviewerSignoffLedgerResponse,
        sla_hours: dict[str, int],
    ) -> list[ReviewerEscalationItem]:
        items: list[ReviewerEscalationItem] = []
        for assignment in collaboration.assignments:
            if assignment.approval_status == "approved" and not assignment.blocking_items:
                continue
            severity = "high" if assignment.blocking_items else "medium"
            items.append(
                self._item(
                    items,
                    assignment.reviewer_role,
                    assignment.reviewer_name,
                    severity,
                    "assignment",
                    assignment.approval_status,
                    assignment.due_hint,
                    f"{assignment.reviewer_role} assignment is {assignment.approval_status}.",
                    assignment.blocking_items[0] if assignment.blocking_items else assignment.scope,
                    assignment.requirement_ids,
                    [],
                    assignment.blocking_items,
                    assignment.citation_refs,
                    sla_hours,
                )
            )

        for comment in collaboration.decision_comments:
            if comment.status not in {"open", "needs_review"}:
                continue
            severity = "critical" if comment.sentiment == "blocker" else comment.severity
            items.append(
                self._item(
                    items,
                    comment.reviewer_role,
                    comment.reviewer_name,
                    severity,
                    "decision_comment",
                    comment.status,
                    "before executive submission review",
                    comment.comment,
                    comment.required_action,
                    [comment.related_requirement_id] if comment.related_requirement_id else [],
                    [comment.comment_id],
                    [comment.required_action],
                    comment.citation_refs,
                    sla_hours,
                )
            )

        for redline in collaboration.redline_summary.get("items", []):
            if redline.get("risk_level") not in {"critical", "high"}:
                continue
            role = "legal" if redline.get("source") == "contract" else "solutions"
            items.append(
                self._item(
                    items,
                    role,
                    self._reviewer_name(collaboration, role),
                    str(redline.get("risk_level", "high")),
                    "redline",
                    "open",
                    "before final approval gate",
                    str(redline.get("title", "High-risk redline requires approval.")),
                    str(redline.get("suggested_redline", "Approve redline or rewrite as an exception.")),
                    [str(redline.get("id", ""))],
                    [],
                    [str(redline.get("fallback_position", ""))],
                    [str(redline.get("id", ""))],
                    sla_hours,
                )
            )

        for record in ledger.records:
            if record.signoff_state in {"signed_off", "ready_for_signoff"} and not record.outstanding_items:
                continue
            severity = "critical" if record.policy_gate == "hard_stop_until_blockers_close" else "high"
            if record.signoff_state in {"pending_human_review", "conditional_review"}:
                severity = "medium"
            items.append(
                self._item(
                    items,
                    record.reviewer_role,
                    record.reviewer_name,
                    severity,
                    "signoff_ledger",
                    record.signoff_state,
                    "before final approval gate",
                    f"{record.reviewer_role} signoff is {record.signoff_state}.",
                    record.outstanding_items[0]
                    if record.outstanding_items
                    else "Capture named owner signoff.",
                    record.requirement_ids,
                    record.decision_comment_ids,
                    record.outstanding_items,
                    record.citation_refs,
                    sla_hours,
                    policy_gate=record.policy_gate,
                )
            )

        if not items and workflow.workflow_status != "ready_for_submission":
            items.append(
                self._item(
                    items,
                    "review_board",
                    "Review Board",
                    "medium",
                    "workflow",
                    workflow.workflow_status,
                    "before final approval gate",
                    f"Reviewer workflow remains in {workflow.current_state}.",
                    "Replay reviewer workflow after owners update board inputs.",
                    [],
                    [],
                    [workflow.current_state],
                    [checkpoint.checkpoint_id for checkpoint in workflow.checkpoints],
                    sla_hours,
                )
            )
        return items

    def _item(
        self,
        existing: list[ReviewerEscalationItem],
        role: str,
        reviewer_name: str,
        severity: str,
        source: str,
        status: str,
        due_hint: str,
        trigger: str,
        action: str,
        requirement_ids: list[str],
        comment_ids: list[str],
        outstanding_items: list[str],
        trace_refs: list[str],
        sla_hours: dict[str, int],
        policy_gate: str | None = None,
    ) -> ReviewerEscalationItem:
        normalized_role = role or "review_board"
        severity_label = severity if severity in {"low", "medium", "high", "critical"} else "medium"
        gate = policy_gate or self._policy_gate(severity_label, status)
        return ReviewerEscalationItem(
            escalation_id=f"esc_{len(existing) + 1:03d}_{normalized_role}",
            reviewer_role=normalized_role,
            reviewer_name=reviewer_name,
            severity=severity_label,
            source=source,
            status=status,
            escalation_state=self._escalation_state(severity_label, gate),
            policy_gate=gate,
            due_hint=self._sla_hint(normalized_role, severity_label, due_hint, sla_hours),
            escalation_owner=ESCALATION_MANAGERS.get(normalized_role, "proposal_manager"),
            escalation_path=self._escalation_path(normalized_role, severity_label),
            trigger=trigger,
            recommended_action=action,
            related_requirement_ids=[item for item in requirement_ids if item],
            related_comment_ids=comment_ids,
            outstanding_items=[item for item in outstanding_items if item],
            trace_refs=[item for item in trace_refs if item],
        )

    def _summary(
        self,
        items: list[ReviewerEscalationItem],
        collaboration: ReviewerCollaborationResponse,
        workflow: ReviewerCollaborationWorkflowResponse,
        ledger: ReviewerSignoffLedgerResponse,
    ) -> dict[str, Any]:
        severities = Counter(item.severity for item in items)
        states = Counter(item.escalation_state for item in items)
        roles = Counter(item.reviewer_role for item in items)
        status = "clear"
        if severities.get("critical", 0):
            status = "blocked_escalation"
        elif severities.get("high", 0):
            status = "escalated"
        elif items:
            status = "watch"
        return {
            "status": status,
            "escalation_count": len(items),
            "critical_count": severities.get("critical", 0),
            "high_count": severities.get("high", 0),
            "watch_count": states.get("watch", 0),
            "owner_count": len(roles),
            "roles": dict(sorted(roles.items())),
            "source_board_status": collaboration.board_status,
            "source_workflow_status": workflow.workflow_status,
            "source_ledger_status": ledger.ledger_status,
            "patterns": [
                "typed contracts",
                "role crews",
                "task delegation",
                "checkpointing",
                "conditional routing",
                "traceable node transitions",
            ],
        }

    def _checkpoints(
        self,
        items: list[ReviewerEscalationItem],
        summary: dict[str, Any],
    ) -> list[ReviewerEscalationCheckpoint]:
        critical_or_high = summary["critical_count"] + summary["high_count"]
        return [
            ReviewerEscalationCheckpoint(
                checkpoint_id="escalation_cp_01_intake",
                sequence=1,
                state="intake",
                status="complete",
                owner_role="proposal_manager",
                decision="load_reviewer_governance_inputs",
                rationale=f"{summary['escalation_count']} escalation candidate(s) loaded.",
                next_state="sla_triage",
            ),
            ReviewerEscalationCheckpoint(
                checkpoint_id="escalation_cp_02_sla_triage",
                sequence=2,
                state="sla_triage",
                status="blocked" if critical_or_high else "complete" if not items else "watch",
                owner_role="proposal_manager",
                decision="classify_sla_risk",
                rationale=f"{critical_or_high} critical/high item(s) require escalation routing.",
                next_state="role_crew_route",
                blocking_count=critical_or_high,
            ),
            ReviewerEscalationCheckpoint(
                checkpoint_id="escalation_cp_03_role_crew_route",
                sequence=3,
                state="role_crew_route",
                status="blocked" if critical_or_high else "complete",
                owner_role="review_board",
                decision="delegate_to_owner_crews",
                rationale="Items are grouped by reviewer role with escalation owners and next actions.",
                next_state="executive_gate",
                blocking_count=critical_or_high,
            ),
            ReviewerEscalationCheckpoint(
                checkpoint_id="escalation_cp_04_executive_gate",
                sequence=4,
                state="executive_gate",
                status="blocked" if summary["critical_count"] else "watch" if summary["high_count"] else "complete",
                owner_role="executive_sponsor",
                decision="hold_or_release_submission",
                rationale="Critical escalations create a hard stop; high escalations require owner closure.",
                next_state="replay_or_release",
                blocking_count=summary["critical_count"],
            ),
            ReviewerEscalationCheckpoint(
                checkpoint_id="escalation_cp_05_final",
                sequence=5,
                state="replay_or_release",
                status="complete" if not items else "pending",
                owner_role="proposal_manager",
                decision="release_if_clear_else_replay",
                rationale="Replay collaboration, workflow, signoff, and escalation after owner closures.",
                next_state=None,
                blocking_count=len(items),
            ),
        ]

    def _transitions(self, checkpoints: list[ReviewerEscalationCheckpoint]) -> list[dict[str, Any]]:
        transitions = []
        for current, next_checkpoint in zip(checkpoints, checkpoints[1:], strict=False):
            transitions.append(
                {
                    "transition_id": f"escalation_tx_{len(transitions) + 1:02d}",
                    "from_state": current.state,
                    "to_state": next_checkpoint.state,
                    "condition": "blocked_gate" if current.status == "blocked" else current.status,
                    "decision": current.decision,
                    "trace_note": (
                        f"{current.checkpoint_id} resolved {current.status}; "
                        f"routing to {next_checkpoint.state}."
                    ),
                }
            )
        return transitions

    def _role_crew_queue(self, items: list[ReviewerEscalationItem]) -> list[dict[str, Any]]:
        grouped: dict[str, list[ReviewerEscalationItem]] = {}
        for item in items:
            grouped.setdefault(item.reviewer_role, []).append(item)
        queue = []
        severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        for role, role_items in sorted(grouped.items()):
            ordered = sorted(role_items, key=lambda item: severity_rank[item.severity])
            queue.append(
                {
                    "reviewer_role": role,
                    "escalation_owner": ordered[0].escalation_owner,
                    "item_count": len(ordered),
                    "highest_severity": ordered[0].severity,
                    "next_action": ordered[0].recommended_action,
                    "escalation_path": ordered[0].escalation_path,
                }
            )
        return queue

    def _pack_payload(
        self,
        trace_id: str,
        escalation: ReviewerEscalationResponse,
        collaboration: ReviewerCollaborationResponse,
        workflow: ReviewerCollaborationWorkflowResponse,
        ledger: ReviewerSignoffLedgerResponse,
    ) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Reviewer SLA Escalation Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "escalation": escalation.model_dump(mode="json"),
            "source_context": {
                "board_status": collaboration.board_status,
                "workflow_status": workflow.workflow_status,
                "workflow_state": workflow.current_state,
                "ledger_status": ledger.ledger_status,
                "assignment_count": len(collaboration.assignments),
                "signoff_record_count": len(ledger.records),
            },
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        escalation = pack["escalation"]
        summary = escalation["summary"]
        lines = [
            "# Reviewer SLA Escalation Pack",
            "",
            "## Summary",
            "",
            f"- Status: {escalation['status']}",
            f"- Current state: {escalation['current_state']}",
            f"- Escalations: {summary['escalation_count']}",
            f"- Critical: {summary['critical_count']}",
            f"- High: {summary['high_count']}",
            f"- Source board: {summary['source_board_status']}",
            f"- Source workflow: {summary['source_workflow_status']}",
            f"- Source ledger: {summary['source_ledger_status']}",
            f"- Patterns: {', '.join(summary['patterns'])}",
            "",
            "## Escalation Items",
            "",
            "| ID | Reviewer | Severity | Source | Gate | Owner | Due | Action |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for item in escalation["escalation_items"]:
            lines.append(
                f"| {item['escalation_id']} | {self._md(item['reviewer_name'])} | "
                f"{item['severity']} | {item['source']} | {item['policy_gate']} | "
                f"{item['escalation_owner']} | {self._md(item['due_hint'])} | "
                f"{self._md(item['recommended_action'])} |"
            )
        lines.extend(["", "## Role Crew Queue", ""])
        for item in escalation["role_crew_queue"]:
            lines.append(
                f"- {item['reviewer_role']} -> {item['escalation_owner']}: "
                f"{item['item_count']} item(s), highest={item['highest_severity']}. "
                f"Next: {item['next_action']}"
            )
        lines.extend(["", "## Checkpoints", ""])
        for checkpoint in escalation["checkpoints"]:
            lines.append(
                f"- {checkpoint['checkpoint_id']} {checkpoint['state']} ({checkpoint['status']}): "
                f"{checkpoint['rationale']}"
            )
        lines.extend(["", "## Transitions", ""])
        for transition in escalation["transitions"]:
            lines.append(
                f"- {transition['transition_id']}: {transition['from_state']} to "
                f"{transition['to_state']} when {transition['condition']}. {transition['trace_note']}"
            )
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```bash\n{command}\n```" for command in escalation["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in escalation["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _summary_status_rank(self, severity: str) -> int:
        return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(severity, 2)

    def _current_state(self, checkpoints: list[ReviewerEscalationCheckpoint]) -> str:
        for checkpoint in checkpoints:
            if checkpoint.status == "blocked":
                return checkpoint.state
        for checkpoint in checkpoints:
            if checkpoint.status == "watch":
                return checkpoint.state
        return checkpoints[-1].state

    def _reviewer_name(self, collaboration: ReviewerCollaborationResponse, role: str) -> str:
        for assignment in collaboration.assignments:
            if assignment.reviewer_role == role:
                return assignment.reviewer_name
        return role.replace("_", " ").title()

    def _policy_gate(self, severity: str, status: str) -> str:
        if severity == "critical" or status in {"blocked", "hard_stop_until_blockers_close"}:
            return "hard_stop_until_owner_closure"
        if severity == "high":
            return "same_day_escalation"
        return "monitor_next_review_cycle"

    def _escalation_state(self, severity: str, gate: str) -> str:
        if gate.startswith("hard_stop") or severity == "critical":
            return "executive_escalation"
        if severity == "high":
            return "owner_escalation"
        return "watch"

    def _sla_hint(
        self,
        role: str,
        severity: str,
        due_hint: str,
        sla_hours: dict[str, int],
    ) -> str:
        configured = sla_hours.get(role) or sla_hours.get(severity)
        if configured:
            return f"{configured} business hour SLA; {due_hint}"
        defaults = {"critical": 4, "high": 8, "medium": 24, "low": 48}
        return f"{defaults[severity]} business hour SLA; {due_hint}"

    def _escalation_path(self, role: str, severity: str) -> list[str]:
        manager = ESCALATION_MANAGERS.get(role, "proposal_manager")
        path = [role, manager]
        if severity in {"critical", "high"}:
            path.append("executive_sponsor")
        if role == "legal" and "general_counsel" not in path:
            path.append("general_counsel")
        return list(dict.fromkeys(path))

    def _local_proof_commands(self) -> list[str]:
        return [
            "python -m pytest tests\\test_reviewer_escalation.py -q",
            "python -m pytest -q",
            "python -m ruff check .",
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/reviewer-escalations" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/reviewer-escalation-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Escalation items are deterministic local workflow records, not live Slack, email, or ticketing tasks.",
            "SLA hints are business-hour targets for local review and do not inspect real calendars.",
            "Named escalation owners are role placeholders unless a caller maps them to enterprise identities.",
            "Artifacts under storage/reviewer_escalations are ignored by git and regenerated locally.",
        ]

    def _md(self, value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ").strip()
