from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    ReviewerCollaborationResponse,
    ReviewerCollaborationWorkflowPackResponse,
    ReviewerCollaborationWorkflowResponse,
    ReviewerWorkflowCheckpoint,
    ReviewerWorkflowTransition,
)


class ReviewerWorkflowService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build_workflow(
        self,
        trace_id: str,
        collaboration: ReviewerCollaborationResponse,
    ) -> ReviewerCollaborationWorkflowResponse:
        checkpoints = self._checkpoints(collaboration)
        transitions = self._transitions(checkpoints)
        workflow_status = self._workflow_status(collaboration, checkpoints)
        current_state = self._current_state(checkpoints, workflow_status)
        return ReviewerCollaborationWorkflowResponse(
            title="Reviewer Collaboration Workflow",
            workflow_status=workflow_status,
            current_state=current_state,
            checkpoints=checkpoints,
            transitions=transitions,
            state_summary=self._state_summary(collaboration, checkpoints),
            approval_path=self._approval_path(collaboration),
            replay_notes=self._replay_notes(workflow_status, current_state),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def workflow_pack(
        self,
        trace_id: str,
        collaboration: ReviewerCollaborationResponse,
        workflow: ReviewerCollaborationWorkflowResponse,
        write_artifact: bool = True,
    ) -> ReviewerCollaborationWorkflowPackResponse:
        pack = self._pack_payload(trace_id, collaboration, workflow)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "review_boards"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"reviewer_workflow_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"reviewer_workflow_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["workflow_markdown"] = artifact_path
            pack["artifact_paths"]["workflow_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return ReviewerCollaborationWorkflowPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            workflow=workflow,
            collaboration=collaboration,
            trace_id=trace_id,
        )

    def _checkpoints(self, collaboration: ReviewerCollaborationResponse) -> list[ReviewerWorkflowCheckpoint]:
        summary = collaboration.approval_summary
        redlines = collaboration.redline_summary
        role_blockers = [
            f"{assignment.reviewer_role}: {'; '.join(assignment.blocking_items)}"
            for assignment in collaboration.assignments
            if assignment.blocking_items
        ]
        open_comments = [
            f"{comment.reviewer_role}: {comment.comment}"
            for comment in collaboration.decision_comments
            if comment.status == "open"
        ]
        redline_blockers = [
            f"{item['id']}: {item['suggested_redline']}"
            for item in redlines.get("items", [])
            if item.get("risk_level") in {"critical", "high"}
        ]
        checkpoints = [
            ReviewerWorkflowCheckpoint(
                checkpoint_id="review_cp_01_intake",
                sequence=1,
                state="intake",
                status="complete",
                owner_role="sales",
                decision="collaboration_board_loaded",
                rationale=(
                    f"Board status is {collaboration.board_status} with "
                    f"{summary.get('assignment_count', 0)} reviewer assignment(s)."
                ),
                next_states=["role_routing"],
                blocking_signals=[],
                evidence_refs=[],
            ),
            ReviewerWorkflowCheckpoint(
                checkpoint_id="review_cp_02_role_routing",
                sequence=2,
                state="role_routing",
                status="blocked" if role_blockers else "complete",
                owner_role="solutions",
                decision="route_by_reviewer_scope",
                rationale="Assignments are grouped by owner role, priority, requirement IDs, and source signals.",
                next_states=["decision_comment_triage"],
                blocking_signals=role_blockers[:8],
                evidence_refs=self._assignment_refs(collaboration),
            ),
            ReviewerWorkflowCheckpoint(
                checkpoint_id="review_cp_03_comment_triage",
                sequence=3,
                state="decision_comment_triage",
                status="blocked" if open_comments else "complete",
                owner_role="review_board",
                decision="resolve_or_accept_comments",
                rationale=(
                    f"{summary.get('open_decision_comment_count', 0)} open comment(s) and "
                    f"{summary.get('blocker_comment_count', 0)} blocker comment(s) are in the board."
                ),
                next_states=["redline_gate"],
                blocking_signals=open_comments[:8],
                evidence_refs=self._comment_refs(collaboration),
            ),
            ReviewerWorkflowCheckpoint(
                checkpoint_id="review_cp_04_redline_gate",
                sequence=4,
                state="redline_gate",
                status="blocked" if redline_blockers else "complete",
                owner_role="legal",
                decision="approve_redlines_or_require_rewrite",
                rationale=(
                    f"{redlines.get('redline_count', 0)} redline(s); "
                    f"{redlines.get('critical_or_high_count', 0)} critical/high item(s)."
                ),
                next_states=["approval_gate"],
                blocking_signals=redline_blockers[:8],
                evidence_refs=[],
            ),
            ReviewerWorkflowCheckpoint(
                checkpoint_id="review_cp_05_approval_gate",
                sequence=5,
                state="approval_gate",
                status="complete" if summary.get("ready_for_submission") else "blocked",
                owner_role="executive_sponsor",
                decision=(
                    "ready_for_submission"
                    if summary.get("ready_for_submission")
                    else "hold_for_reviewer_closure"
                ),
                rationale=(
                    "Submission readiness requires no blocked assignments, no open blocker comments, "
                    "and review_passed is not false."
                ),
                next_states=["submission_release" if summary.get("ready_for_submission") else "blocker_resolution"],
                blocking_signals=self._approval_blockers(collaboration)[:8],
                evidence_refs=[],
            ),
        ]
        final_state = "submission_release" if summary.get("ready_for_submission") else "blocker_resolution"
        checkpoints.append(
            ReviewerWorkflowCheckpoint(
                checkpoint_id="review_cp_06_final",
                sequence=6,
                state=final_state,
                status="complete" if final_state == "submission_release" else "pending",
                owner_role="executive_sponsor" if final_state == "submission_release" else "review_board",
                decision="release_package" if final_state == "submission_release" else "close_blockers_and_replay",
                rationale=(
                    "All review gates are clear."
                    if final_state == "submission_release"
                    else "Replay this workflow after owners close blockers, comments, and redlines."
                ),
                next_states=[],
                blocking_signals=[],
                evidence_refs=[],
            )
        )
        return checkpoints

    def _transitions(
        self,
        checkpoints: list[ReviewerWorkflowCheckpoint],
    ) -> list[ReviewerWorkflowTransition]:
        transitions: list[ReviewerWorkflowTransition] = []
        for current, next_checkpoint in zip(checkpoints, checkpoints[1:], strict=False):
            condition = "blocked_gate" if current.status == "blocked" else "gate_passed"
            transitions.append(
                ReviewerWorkflowTransition(
                    transition_id=f"review_tx_{len(transitions) + 1:02d}",
                    from_state=current.state,
                    to_state=next_checkpoint.state,
                    condition=condition,
                    decision=current.decision,
                    trace_note=(
                        f"{current.checkpoint_id} produced {current.status}; "
                        f"next state is {next_checkpoint.state}."
                    ),
                    checkpoint_id=current.checkpoint_id,
                )
            )
        return transitions

    def _workflow_status(
        self,
        collaboration: ReviewerCollaborationResponse,
        checkpoints: list[ReviewerWorkflowCheckpoint],
    ) -> str:
        if any(checkpoint.status == "blocked" for checkpoint in checkpoints):
            return "blocked"
        if collaboration.board_status in {"needs_review", "pending_review"}:
            return collaboration.board_status
        return "ready_for_submission"

    def _current_state(self, checkpoints: list[ReviewerWorkflowCheckpoint], workflow_status: str) -> str:
        if workflow_status == "blocked":
            for checkpoint in checkpoints:
                if checkpoint.status == "blocked":
                    return checkpoint.state
        return checkpoints[-1].state

    def _state_summary(
        self,
        collaboration: ReviewerCollaborationResponse,
        checkpoints: list[ReviewerWorkflowCheckpoint],
    ) -> dict[str, Any]:
        status_counts = Counter(checkpoint.status for checkpoint in checkpoints)
        return {
            "checkpoint_count": len(checkpoints),
            "transition_count": max(0, len(checkpoints) - 1),
            "blocked_checkpoint_count": status_counts.get("blocked", 0),
            "complete_checkpoint_count": status_counts.get("complete", 0),
            "pending_checkpoint_count": status_counts.get("pending", 0),
            "board_status": collaboration.board_status,
            "ready_for_submission": collaboration.approval_summary.get("ready_for_submission", False),
            "patterns": [
                "typed contracts",
                "state machine workflow",
                "checkpointing",
                "traceable node transitions",
            ],
        }

    def _approval_path(self, collaboration: ReviewerCollaborationResponse) -> list[dict[str, Any]]:
        return [
            {
                "sequence": index + 1,
                "reviewer_role": assignment.reviewer_role,
                "reviewer_name": assignment.reviewer_name,
                "approval_status": assignment.approval_status,
                "priority": assignment.priority,
                "next_action": assignment.blocking_items[0] if assignment.blocking_items else assignment.scope,
                "requirement_ids": assignment.requirement_ids,
            }
            for index, assignment in enumerate(collaboration.assignments)
        ]

    def _pack_payload(
        self,
        trace_id: str,
        collaboration: ReviewerCollaborationResponse,
        workflow: ReviewerCollaborationWorkflowResponse,
    ) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Reviewer Collaboration Workflow Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "workflow": workflow.model_dump(mode="json"),
            "collaboration_summary": {
                "board_status": collaboration.board_status,
                "approval_summary": collaboration.approval_summary,
                "redline_summary": collaboration.redline_summary,
                "assignment_count": len(collaboration.assignments),
                "decision_comment_count": len(collaboration.decision_comments),
            },
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        workflow = pack["workflow"]
        summary = workflow["state_summary"]
        lines = [
            "# Reviewer Collaboration Workflow Pack",
            "",
            "## Workflow Summary",
            "",
            f"- Status: {workflow['workflow_status']}",
            f"- Current state: {workflow['current_state']}",
            f"- Checkpoints: {summary['checkpoint_count']}",
            f"- Transitions: {summary['transition_count']}",
            f"- Blocked checkpoints: {summary['blocked_checkpoint_count']}",
            f"- Patterns: {', '.join(summary['patterns'])}",
            "",
            "## Checkpoints",
            "",
            "| Seq | State | Status | Owner | Decision | Blocking Signals |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for checkpoint in workflow["checkpoints"]:
            lines.append(
                f"| {checkpoint['sequence']} | {checkpoint['state']} | {checkpoint['status']} | "
                f"{checkpoint['owner_role']} | {checkpoint['decision']} | "
                f"{'; '.join(checkpoint['blocking_signals']) or 'None'} |"
            )
        lines.extend(["", "## Transitions", ""])
        for transition in workflow["transitions"]:
            lines.append(
                f"- {transition['transition_id']}: {transition['from_state']} -> "
                f"{transition['to_state']} when {transition['condition']}. {transition['trace_note']}"
            )
        lines.extend(["", "## Approval Path", ""])
        for item in workflow["approval_path"]:
            lines.append(
                f"- {item['sequence']}. {item['reviewer_name']} ({item['reviewer_role']}): "
                f"{item['approval_status']} / {item['priority']}. Next: {item['next_action']}"
            )
        lines.extend(["", "## Replay Notes", ""])
        lines.extend(f"- {item}" for item in workflow["replay_notes"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```bash\n{command}\n```" for command in workflow["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in workflow["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Workflow Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _assignment_refs(self, collaboration: ReviewerCollaborationResponse) -> list[str]:
        refs = {ref for assignment in collaboration.assignments for ref in assignment.citation_refs}
        return sorted(refs)[:12]

    def _comment_refs(self, collaboration: ReviewerCollaborationResponse) -> list[str]:
        refs = {ref for comment in collaboration.decision_comments for ref in comment.citation_refs}
        return sorted(refs)[:12]

    def _approval_blockers(self, collaboration: ReviewerCollaborationResponse) -> list[str]:
        summary = collaboration.approval_summary
        blockers = []
        if summary.get("blocked_count"):
            blockers.append(f"{summary['blocked_count']} blocked reviewer assignment(s).")
        if summary.get("blocker_comment_count"):
            blockers.append(f"{summary['blocker_comment_count']} blocker decision comment(s).")
        if summary.get("review_passed") is False:
            blockers.append("Review board did not pass.")
        if collaboration.redline_summary.get("critical_or_high_count"):
            blockers.append(
                f"{collaboration.redline_summary['critical_or_high_count']} critical/high redline(s)."
            )
        return blockers

    def _replay_notes(self, workflow_status: str, current_state: str) -> list[str]:
        if workflow_status == "ready_for_submission":
            return [
                "Workflow replay can be attached to the submission memo as local governance evidence.",
                "No external approval system is required for this deterministic proof artifact.",
            ]
        return [
            f"Replay should restart at {current_state} after owners update the collaboration board inputs.",
            "Checkpoint statuses are deterministic and can be compared across repeated local runs.",
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            "python -m pytest tests\\test_reviewer_workflow.py -q",
            "python -m pytest -q",
            "python -m ruff check .",
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/reviewer-workflow" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/reviewer-workflow-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Workflow checkpoints are deterministic local governance records, not persisted task state.",
            "Approval routing is derived from the collaboration board and still requires human owner confirmation.",
            (
                "The replay model is designed for local portfolio review and does not integrate an external "
                "ticketing tool."
            ),
        ]
