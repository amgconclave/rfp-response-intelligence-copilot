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
    ReviewerSignoffLedgerPackResponse,
    ReviewerSignoffLedgerResponse,
    ReviewerSignoffOverride,
    ReviewerSignoffRecord,
)


class ReviewerSignoffLedgerService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def ledger(
        self,
        trace_id: str,
        collaboration: ReviewerCollaborationResponse,
        workflow: ReviewerCollaborationWorkflowResponse,
        signoff_overrides: list[ReviewerSignoffOverride] | None = None,
    ) -> ReviewerSignoffLedgerResponse:
        overrides = {self._role_key(item.reviewer_role): item for item in signoff_overrides or []}
        comments_by_role = self._comments_by_role(collaboration)
        records = [
            self._record(index + 1, assignment, comments_by_role.get(assignment.reviewer_role, []), overrides)
            for index, assignment in enumerate(collaboration.assignments)
        ]
        summary = self._summary(collaboration, workflow, records)
        return ReviewerSignoffLedgerResponse(
            title="Reviewer Signoff Ledger",
            ledger_status=summary["ledger_status"],
            records=records,
            summary=summary,
            workflow_snapshot=self._workflow_snapshot(workflow),
            governance_gates=self._governance_gates(collaboration, workflow, records),
            human_review_queue=self._human_review_queue(records),
            transition_log=self._transition_log(workflow, records),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        collaboration: ReviewerCollaborationResponse,
        workflow: ReviewerCollaborationWorkflowResponse,
        ledger: ReviewerSignoffLedgerResponse,
        write_artifact: bool = True,
    ) -> ReviewerSignoffLedgerPackResponse:
        pack = self._pack_payload(trace_id, ledger, collaboration, workflow)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "reviewer_signoffs"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"reviewer_signoff_ledger_{safe_trace_id}.md"
            json_path = pack_dir / f"reviewer_signoff_ledger_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["signoff_ledger_markdown"] = artifact_path
            pack["artifact_paths"]["signoff_ledger_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return ReviewerSignoffLedgerPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            ledger=ledger,
            collaboration=collaboration,
            workflow=workflow,
            trace_id=trace_id,
        )

    def _record(
        self,
        sequence: int,
        assignment: Any,
        comments: list[Any],
        overrides: dict[str, ReviewerSignoffOverride],
    ) -> ReviewerSignoffRecord:
        role = self._role_key(assignment.reviewer_role)
        override = overrides.get(role)
        blocker_comments = [
            comment
            for comment in comments
            if comment.status == "open" and comment.sentiment == "blocker"
        ]
        outstanding = list(assignment.blocking_items)
        outstanding.extend(f"{comment.comment_id}: {comment.required_action}" for comment in blocker_comments)
        approval_status = override.approval_status if override else assignment.approval_status
        signoff_state = self._signoff_state(assignment.approval_status, approval_status, outstanding, override)
        return ReviewerSignoffRecord(
            signoff_id=f"signoff_{role}_{sequence:02d}",
            reviewer_role=role,
            reviewer_name=assignment.reviewer_name,
            approval_status=approval_status,
            signoff_state=signoff_state,
            policy_gate=self._policy_gate(signoff_state, outstanding),
            signed_by=override.signed_by if override else None,
            signed_at=override.signed_at if override else None,
            evidence_note=override.evidence_note if override else "",
            requirement_ids=assignment.requirement_ids,
            outstanding_items=outstanding[:10],
            decision_comment_ids=[comment.comment_id for comment in comments],
            citation_refs=assignment.citation_refs,
            trace_notes=self._trace_notes(assignment, comments, override, signoff_state),
        )

    def _signoff_state(
        self,
        assignment_status: str,
        requested_status: str,
        outstanding_items: list[str],
        override: ReviewerSignoffOverride | None,
    ) -> str:
        requested = requested_status.lower()
        if requested in {"rejected", "blocked"}:
            return "blocked"
        if outstanding_items and requested not in {"waived", "exception_approved"}:
            return "blocked"
        if override and requested in {"approved", "signed", "approved_to_submit"}:
            return "signed_off"
        if override and requested in {
            "approved_with_conditions",
            "conditional_approval",
            "exception_approved",
            "waived",
        }:
            return "conditional_signoff"
        if assignment_status == "approved":
            return "ready_for_signoff"
        if assignment_status == "conditional_approval":
            return "conditional_review"
        return "pending_human_review"

    def _policy_gate(self, signoff_state: str, outstanding_items: list[str]) -> str:
        if signoff_state == "blocked":
            return "hard_stop_until_blockers_close"
        if signoff_state == "conditional_signoff" or outstanding_items:
            return "submit_only_with_named_exception"
        if signoff_state == "signed_off":
            return "human_approved"
        if signoff_state == "ready_for_signoff":
            return "ready_for_named_owner_signature"
        return "human_review_required"

    def _summary(
        self,
        collaboration: ReviewerCollaborationResponse,
        workflow: ReviewerCollaborationWorkflowResponse,
        records: list[ReviewerSignoffRecord],
    ) -> dict[str, Any]:
        state_counts = Counter(record.signoff_state for record in records)
        gate_counts = Counter(record.policy_gate for record in records)
        ledger_status = "blocked"
        if state_counts.get("blocked", 0) == 0:
            if records and all(record.signoff_state in {"signed_off", "ready_for_signoff"} for record in records):
                ledger_status = "ready_for_submission"
            elif state_counts.get("conditional_signoff", 0) or state_counts.get("conditional_review", 0):
                ledger_status = "conditional"
            else:
                ledger_status = "pending_review"
        return {
            "ledger_status": ledger_status,
            "record_count": len(records),
            "signed_count": state_counts.get("signed_off", 0),
            "ready_for_signoff_count": state_counts.get("ready_for_signoff", 0),
            "conditional_count": state_counts.get("conditional_signoff", 0) + state_counts.get("conditional_review", 0),
            "pending_count": state_counts.get("pending_human_review", 0),
            "blocked_count": state_counts.get("blocked", 0),
            "open_outstanding_item_count": sum(len(record.outstanding_items) for record in records),
            "policy_gate_counts": dict(gate_counts),
            "source_board_status": collaboration.board_status,
            "source_workflow_status": workflow.workflow_status,
            "current_workflow_state": workflow.current_state,
            "patterns": [
                "durable workflow ledger",
                "human-in-the-loop signoff",
                "governance gates",
                "shared reviewer state",
            ],
        }

    def _governance_gates(
        self,
        collaboration: ReviewerCollaborationResponse,
        workflow: ReviewerCollaborationWorkflowResponse,
        records: list[ReviewerSignoffRecord],
    ) -> list[dict[str, Any]]:
        hard_stops = [record for record in records if record.policy_gate == "hard_stop_until_blockers_close"]
        exception_gates = [record for record in records if record.policy_gate == "submit_only_with_named_exception"]
        return [
            {
                "gate_id": "signoff_gate_01_board_status",
                "status": "pass" if collaboration.board_status == "approved" else "needs_review",
                "owner_role": "review_board",
                "evidence": f"Reviewer board status is {collaboration.board_status}.",
                "required_action": (
                    "Resolve board blockers before final submission."
                    if collaboration.board_status != "approved"
                    else "Attach board artifact."
                ),
            },
            {
                "gate_id": "signoff_gate_02_workflow_replay",
                "status": "pass" if workflow.workflow_status == "ready_for_submission" else "needs_review",
                "owner_role": "executive_sponsor",
                "evidence": f"Workflow state is {workflow.current_state}.",
                "required_action": (
                    "Replay workflow after closures."
                    if workflow.workflow_status != "ready_for_submission"
                    else "Attach workflow replay."
                ),
            },
            {
                "gate_id": "signoff_gate_03_named_owners",
                "status": "blocked" if hard_stops else "needs_review" if exception_gates else "pass",
                "owner_role": "review_board",
                "evidence": f"{len(hard_stops)} hard stop(s), {len(exception_gates)} exception gate(s).",
                "required_action": "Collect named owner signoff or documented exceptions.",
            },
        ]

    def _human_review_queue(self, records: list[ReviewerSignoffRecord]) -> list[dict[str, Any]]:
        queue = []
        for record in records:
            if record.signoff_state in {"signed_off", "ready_for_signoff"} and not record.outstanding_items:
                continue
            queue.append(
                {
                    "signoff_id": record.signoff_id,
                    "reviewer_role": record.reviewer_role,
                    "reviewer_name": record.reviewer_name,
                    "policy_gate": record.policy_gate,
                    "signoff_state": record.signoff_state,
                    "outstanding_items": record.outstanding_items,
                    "next_action": record.outstanding_items[0]
                    if record.outstanding_items
                    else "Capture named owner approval before submission.",
                }
            )
        return queue

    def _transition_log(
        self,
        workflow: ReviewerCollaborationWorkflowResponse,
        records: list[ReviewerSignoffRecord],
    ) -> list[dict[str, Any]]:
        transitions = [
            {
                "sequence": index + 1,
                "source": "reviewer_workflow",
                "from_state": transition.from_state,
                "to_state": transition.to_state,
                "condition": transition.condition,
                "status": "observed",
                "evidence": transition.trace_note,
            }
            for index, transition in enumerate(workflow.transitions)
        ]
        offset = len(transitions)
        for index, record in enumerate(records):
            transitions.append(
                {
                    "sequence": offset + index + 1,
                    "source": "signoff_ledger",
                    "from_state": "reviewer_assignment",
                    "to_state": record.signoff_state,
                    "condition": record.policy_gate,
                    "status": "blocked" if record.signoff_state == "blocked" else "recorded",
                    "evidence": f"{record.reviewer_role} has {len(record.outstanding_items)} outstanding item(s).",
                }
            )
        return transitions

    def _workflow_snapshot(self, workflow: ReviewerCollaborationWorkflowResponse) -> dict[str, Any]:
        return {
            "workflow_status": workflow.workflow_status,
            "current_state": workflow.current_state,
            "checkpoint_count": len(workflow.checkpoints),
            "transition_count": len(workflow.transitions),
            "blocked_checkpoints": [
                checkpoint.checkpoint_id for checkpoint in workflow.checkpoints if checkpoint.status == "blocked"
            ],
        }

    def _pack_payload(
        self,
        trace_id: str,
        ledger: ReviewerSignoffLedgerResponse,
        collaboration: ReviewerCollaborationResponse,
        workflow: ReviewerCollaborationWorkflowResponse,
    ) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Reviewer Signoff Ledger Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "ledger": ledger.model_dump(mode="json"),
            "source_context": {
                "board_status": collaboration.board_status,
                "workflow_status": workflow.workflow_status,
                "current_workflow_state": workflow.current_state,
                "assignment_count": len(collaboration.assignments),
                "decision_comment_count": len(collaboration.decision_comments),
            },
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        ledger = pack["ledger"]
        summary = ledger["summary"]
        lines = [
            "# Reviewer Signoff Ledger Pack",
            "",
            "## Ledger Summary",
            "",
            f"- Status: {ledger['ledger_status']}",
            f"- Records: {summary['record_count']}",
            f"- Signed: {summary['signed_count']}",
            f"- Ready for signoff: {summary['ready_for_signoff_count']}",
            f"- Conditional: {summary['conditional_count']}",
            f"- Blocked: {summary['blocked_count']}",
            f"- Outstanding items: {summary['open_outstanding_item_count']}",
            f"- Patterns: {', '.join(summary['patterns'])}",
            "",
            "## Signoff Records",
            "",
            "| Reviewer | Role | State | Policy Gate | Requirements | Outstanding Items |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for record in ledger["records"]:
            lines.append(
                "| "
                f"{self._md(record['reviewer_name'])} | "
                f"{self._md(record['reviewer_role'])} | "
                f"{self._md(record['signoff_state'])} | "
                f"{self._md(record['policy_gate'])} | "
                f"{self._md(', '.join(record['requirement_ids']) or 'None')} | "
                f"{self._md('; '.join(record['outstanding_items']) or 'None')} |"
            )
        lines.extend(["", "## Governance Gates", ""])
        for gate in ledger["governance_gates"]:
            lines.append(
                f"- {gate['gate_id']} ({gate['status']}): {gate['evidence']} Action: {gate['required_action']}"
            )
        lines.extend(["", "## Human Review Queue", ""])
        if ledger["human_review_queue"]:
            for item in ledger["human_review_queue"]:
                lines.append(
                    f"- {item['reviewer_name']} ({item['policy_gate']}): {item['next_action']}"
                )
        else:
            lines.append("- No open human review queue items.")
        lines.extend(["", "## Transition Log", ""])
        for transition in ledger["transition_log"]:
            lines.append(
                f"- {transition['sequence']}. {transition['from_state']} -> {transition['to_state']} "
                f"when {transition['condition']} ({transition['status']})."
            )
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```bash\n{command}\n```" for command in ledger["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in ledger["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _comments_by_role(self, collaboration: ReviewerCollaborationResponse) -> dict[str, list[Any]]:
        comments: dict[str, list[Any]] = {}
        for comment in collaboration.decision_comments:
            comments.setdefault(comment.reviewer_role, []).append(comment)
        return comments

    def _trace_notes(
        self,
        assignment: Any,
        comments: list[Any],
        override: ReviewerSignoffOverride | None,
        signoff_state: str,
    ) -> list[str]:
        notes = [
            f"Assignment status {assignment.status}; approval status {assignment.approval_status}.",
            f"{len(comments)} related decision comment(s).",
            f"Ledger state resolved to {signoff_state}.",
        ]
        if override:
            notes.append(f"Explicit local override recorded as {override.approval_status}.")
        return notes

    def _local_proof_commands(self) -> list[str]:
        return [
            "python -m pytest tests\\test_reviewer_signoff.py -q",
            "python -m pytest -q",
            "python -m ruff check .",
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/reviewer-signoff-ledger" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/reviewer-signoff-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "This ledger records local signoff readiness and explicit request payload overrides, not real identities.",
            "Human approvals still need reconciliation with the buyer's legal, security, and sales systems.",
            "Signed states are deterministic local workflow records unless a caller supplies signoff_overrides.",
            "Artifacts under storage/reviewer_signoffs are ignored by git and regenerated per local review.",
        ]

    def _role_key(self, value: str) -> str:
        return value.lower().replace(" ", "_").replace("-", "_")

    def _md(self, value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ").strip()
