from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    AnswerReuseApprovalLedgerPackResponse,
    AnswerReuseApprovalLedgerResponse,
    AnswerReuseDriftFinding,
)
from app.services.answer_reuse_drift import AnswerReuseDriftService


class AnswerReuseApprovalService:
    def __init__(self, settings: Settings, answer_reuse_drift: AnswerReuseDriftService) -> None:
        self.settings = settings
        self.answer_reuse_drift = answer_reuse_drift

    def ledger(
        self,
        trace_id: str,
        category: str | None = None,
        customer_profile_id: str | None = None,
        include_expired: bool = True,
        min_source_overlap: int = 4,
        requested_by: str = "proposal_manager",
        approver_overrides: dict[str, str] | None = None,
    ) -> AnswerReuseApprovalLedgerResponse:
        drift = self.answer_reuse_drift.drift_report(
            f"{trace_id}-drift",
            category=category,
            customer_profile_id=customer_profile_id,
            include_expired=include_expired,
            min_source_overlap=min_source_overlap,
        )
        overrides = approver_overrides or {}
        records = [self._record(finding, requested_by, overrides.get(finding.snippet_id)) for finding in drift.findings]
        summary = self._summary(records)
        return AnswerReuseApprovalLedgerResponse(
            title="Answer Reuse Approval Ledger",
            status="ready" if summary["pending_count"] == 0 and summary["blocked_count"] == 0 else "needs_human_review",
            records=records,
            summary=summary,
            human_review_queue=self._human_review_queue(records),
            workflow=self._workflow(summary),
            trace_spans=self._trace_spans(records),
            governance_policy=self._governance_policy(min_source_overlap),
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        ledger: AnswerReuseApprovalLedgerResponse | None = None,
        category: str | None = None,
        customer_profile_id: str | None = None,
        include_expired: bool = True,
        min_source_overlap: int = 4,
        requested_by: str = "proposal_manager",
        approver_overrides: dict[str, str] | None = None,
        write_artifact: bool = True,
    ) -> AnswerReuseApprovalLedgerPackResponse:
        ledger = ledger or self.ledger(
            f"{trace_id}-ledger",
            category=category,
            customer_profile_id=customer_profile_id,
            include_expired=include_expired,
            min_source_overlap=min_source_overlap,
            requested_by=requested_by,
            approver_overrides=approver_overrides,
        )
        pack = self._pack_payload(trace_id, ledger)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "answer_reuse_approvals"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"answer_reuse_approval_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"answer_reuse_approval_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["answer_reuse_approval_markdown"] = artifact_path
            pack["artifact_paths"]["answer_reuse_approval_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return AnswerReuseApprovalLedgerPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            ledger=ledger,
            trace_id=trace_id,
        )

    def _record(
        self,
        finding: AnswerReuseDriftFinding,
        requested_by: str,
        override: str | None,
    ) -> dict[str, Any]:
        normalized_override = self._normalize_override(override)
        decision = self._decision(finding, normalized_override)
        approvers = self._required_approvers(finding)
        status = "pass" if decision in {"auto_approved", "approved_with_monitoring"} else "review"
        transitions = self._transitions(finding, decision, status, normalized_override)
        return {
            "snippet_id": finding.snippet_id,
            "title": finding.title,
            "category": finding.category,
            "owner": finding.owner,
            "requested_by": requested_by,
            "approval_decision": decision,
            "approval_status": status,
            "required_approvers": approvers,
            "expires_or_recheck_at": self._recheck_window(decision),
            "checkpoint_key": transitions[-1]["checkpoint_key"],
            "source_drift_status": finding.drift_status,
            "source_drift_score": finding.drift_score,
            "citation_status": finding.citation_status,
            "reuse_decision": finding.reuse_decision,
            "override_applied": normalized_override is not None,
            "override_decision": normalized_override,
            "policy_reason": self._policy_reason(finding, decision),
            "transitions": transitions,
            "evidence_refs": {
                "source_files": finding.source_files,
                "missing_terms": finding.missing_terms,
                "stale_claim_terms": finding.stale_claim_terms,
                "drift_checkpoint_key": finding.transition_trace[-1].checkpoint_key,
            },
        }

    def _decision(self, finding: AnswerReuseDriftFinding, override: str | None) -> str:
        if override == "approve":
            return "approved_by_named_owner"
        if override == "reject":
            return "rejected_by_named_owner"
        if override == "retire":
            return "retired_by_named_owner"
        if finding.drift_status == "stable":
            return "auto_approved"
        if finding.drift_status == "watch":
            return "approved_with_monitoring"
        if finding.drift_status == "owner_review":
            return "pending_owner_approval"
        return "blocked_pending_rewrite"

    def _required_approvers(self, finding: AnswerReuseDriftFinding) -> list[str]:
        approvers = [finding.owner]
        if finding.category == "pricing":
            approvers.append("finance")
        if finding.category in {"security", "compliance"}:
            approvers.append("proposal_security_reviewer")
        if finding.drift_status == "retire_or_rewrite":
            approvers.append("proposal_manager")
        return sorted(dict.fromkeys(approvers))

    def _transitions(
        self,
        finding: AnswerReuseDriftFinding,
        decision: str,
        status: str,
        override: str | None,
    ) -> list[dict[str, Any]]:
        rows = [
            (
                None,
                "drift_report_loaded",
                finding.drift_status,
                "pass",
                "Loaded drift finding and source-overlap evidence.",
            ),
            (
                "drift_report_loaded",
                "policy_evaluation",
                finding.reuse_decision,
                "pass" if finding.reuse_decision != "blocked" else "review",
                "Evaluated library reuse decision, expiry, and citation status.",
            ),
            (
                "policy_evaluation",
                "human_approval_gate",
                override or self._approval_gate_decision(finding),
                status,
                "Applied named-owner override when present, otherwise routed by drift status.",
            ),
            (
                "human_approval_gate",
                "reuse_decision_recorded",
                decision,
                status,
                "Recorded durable local approval decision for snippet reuse.",
            ),
        ]
        return [
            {
                "sequence": index,
                "from_state": from_state,
                "to_state": to_state,
                "decision": transition_decision,
                "status": transition_status,
                "checkpoint_key": f"answer-reuse-approval:{finding.snippet_id}:{to_state}",
                "reason": reason,
            }
            for index, (from_state, to_state, transition_decision, transition_status, reason) in enumerate(
                rows,
                start=1,
            )
        ]

    def _summary(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        decisions = Counter(record["approval_decision"] for record in records)
        owners = Counter(record["owner"] for record in records if record["approval_status"] != "pass")
        return {
            "record_count": len(records),
            "approved_count": sum(
                decisions[key]
                for key in ("auto_approved", "approved_with_monitoring", "approved_by_named_owner")
            ),
            "pending_count": decisions.get("pending_owner_approval", 0),
            "blocked_count": decisions.get("blocked_pending_rewrite", 0)
            + decisions.get("rejected_by_named_owner", 0)
            + decisions.get("retired_by_named_owner", 0),
            "override_count": sum(1 for record in records if record["override_applied"]),
            "decision_counts": dict(sorted(decisions.items())),
            "owner_review_counts": dict(sorted(owners.items())),
        }

    def _human_review_queue(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "snippet_id": record["snippet_id"],
                "title": record["title"],
                "owner": record["owner"],
                "required_approvers": record["required_approvers"],
                "approval_decision": record["approval_decision"],
                "checkpoint_key": record["checkpoint_key"],
                "required_action": self._required_action(record),
            }
            for record in records
            if record["approval_status"] != "pass"
        ]

    def _workflow(self, summary: dict[str, Any]) -> dict[str, Any]:
        return {
            "pattern": "durable_human_in_the_loop_governance",
            "states": [
                "drift_report_loaded",
                "policy_evaluation",
                "human_approval_gate",
                "reuse_decision_recorded",
            ],
            "checkpointing": "Each record has deterministic checkpoint keys for replay and audit.",
            "approval_policy": {
                "stable": "auto_approved",
                "watch": "approved_with_monitoring",
                "owner_review": "pending_owner_approval",
                "retire_or_rewrite": "blocked_pending_rewrite",
            },
            "summary": summary,
        }

    def _trace_spans(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        spans: list[dict[str, Any]] = []
        for record in records:
            parent_id = f"span-{record['snippet_id']}"
            spans.append(
                {
                    "span_id": parent_id,
                    "parent_span_id": None,
                    "name": "answer_reuse_approval.record",
                    "status": record["approval_status"],
                    "attributes": {
                        "snippet_id": record["snippet_id"],
                        "owner": record["owner"],
                        "decision": record["approval_decision"],
                    },
                }
            )
            spans.extend(
                {
                    "span_id": f"{parent_id}-{transition['sequence']}",
                    "parent_span_id": parent_id,
                    "name": f"answer_reuse_approval.{transition['to_state']}",
                    "status": transition["status"],
                    "attributes": {
                        "checkpoint_key": transition["checkpoint_key"],
                        "decision": transition["decision"],
                    },
                }
                for transition in record["transitions"]
            )
        return spans

    def _pack_payload(self, trace_id: str, ledger: AnswerReuseApprovalLedgerResponse) -> dict[str, Any]:
        return {
            "title": "Answer Reuse Approval Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "trace_id": trace_id,
            "ledger": ledger.model_dump(mode="json"),
            "governance_controls": [
                "Stable snippets can be approved locally, but watch and drift findings keep named-owner checkpoints.",
                "Every final reuse decision includes the source drift status, citation status, and checkpoint lineage.",
                "Named-owner overrides are explicit ledger inputs and remain visible in the generated artifact.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        ledger = pack["ledger"]
        summary = ledger["summary"]
        lines = [
            f"# {pack['title']}",
            "",
            f"- Generated at: {pack['generated_at']}",
            f"- Trace ID: {pack['trace_id']}",
            f"- Status: {ledger['status']}",
            f"- Records: {summary['record_count']}",
            f"- Approved: {summary['approved_count']}",
            f"- Pending: {summary['pending_count']}",
            f"- Blocked: {summary['blocked_count']}",
            "",
            "## Approval Records",
            "",
            "| Snippet | Owner | Decision | Status | Approvers | Checkpoint |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for record in ledger["records"]:
            lines.append(
                "| "
                f"{self._md(record['title'])} | "
                f"{self._md(record['owner'])} | "
                f"{self._md(record['approval_decision'])} | "
                f"{self._md(record['approval_status'])} | "
                f"{self._md(', '.join(record['required_approvers']))} | "
                f"{self._md(record['checkpoint_key'])} |"
            )
        lines.extend(["", "## Human Review Queue", ""])
        if ledger["human_review_queue"]:
            lines.extend(
                f"- {item['owner']}: {item['title']} - {item['required_action']}"
                for item in ledger["human_review_queue"]
            )
        else:
            lines.append("- No human review queue items.")
        lines.extend(["", "## Workflow", ""])
        lines.extend(f"- {state}" for state in ledger["workflow"]["states"])
        lines.extend(["", "## Trace Spans", ""])
        lines.append(f"- Span count: {len(ledger['trace_spans'])}")
        lines.extend(["", "## Governance Controls", ""])
        lines.extend(f"- {item}" for item in pack["governance_controls"])
        lines.extend(["", "## Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in ledger["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in ledger["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _governance_policy(self, min_source_overlap: int) -> dict[str, Any]:
        return {
            "min_source_overlap": min_source_overlap,
            "auto_approval_requires": ["stable drift status", "verified citations", "non-blocked reuse decision"],
            "human_review_required_for": ["owner_review", "retire_or_rewrite", "named-owner override"],
            "patterns": ["durable workflows", "human-in-the-loop", "governance", "trace analysis"],
        }

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {
                "method": "POST",
                "path": "/rfp/answer-reuse-approval-ledger",
                "purpose": "Return durable local approval records for reusable accepted answers.",
            },
            {
                "method": "POST",
                "path": "/rfp/answer-reuse-approval-pack",
                "purpose": "Write Markdown/JSON answer reuse approval ledger artifacts.",
                "expected_artifacts": [
                    "storage/answer_reuse_approvals/*.md",
                    "storage/answer_reuse_approvals/*.json",
                ],
            },
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/answer-reuse-approval-ledger" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/answer-reuse-approval-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" '
                '-d "{\\"write_artifact\\":true}"'
            ),
            (
                'rg "answer-reuse-approval|Answer Reuse Approval|answer_reuse_approvals" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\answer_reuse_approvals "
                "-ErrorAction SilentlyContinue | Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Approval records are deterministic local workflow artifacts, not connected to ticketing or e-signature.",
            "Approver overrides are request inputs; external identity and permission checks remain out of scope.",
            "The ledger depends on the local answer reuse drift monitor and sample accepted-answer fixtures.",
        ]

    def _policy_reason(self, finding: AnswerReuseDriftFinding, decision: str) -> str:
        if decision == "auto_approved":
            return "Stable drift status allows reuse under standard proposal review."
        if decision == "approved_with_monitoring":
            return "Watch status allows reuse with monitoring and owner awareness."
        if decision == "pending_owner_approval":
            return f"{finding.owner} must approve source drift before customer-facing reuse."
        if decision == "blocked_pending_rewrite":
            return f"{finding.owner} must rewrite or retire the snippet before reuse."
        return "Named-owner override supplied in request payload."

    def _approval_gate_decision(self, finding: AnswerReuseDriftFinding) -> str:
        return {
            "stable": "auto_gate_pass",
            "watch": "monitoring_gate_pass",
            "owner_review": "route_to_owner",
            "retire_or_rewrite": "block_and_rewrite",
        }[finding.drift_status]

    def _required_action(self, record: dict[str, Any]) -> str:
        decision = record["approval_decision"]
        if decision == "pending_owner_approval":
            return "Named owner must approve, edit, or reject before reuse."
        if decision == "blocked_pending_rewrite":
            return "Rewrite or retire snippet, then regenerate citation lineage and drift checks."
        if decision == "rejected_by_named_owner":
            return "Keep blocked until a revised snippet is accepted."
        if decision == "retired_by_named_owner":
            return "Remove from active response memory and preserve audit history."
        return "Confirm override evidence remains attached."

    def _recheck_window(self, decision: str) -> str:
        windows = {
            "auto_approved": "90_days",
            "approved_with_monitoring": "30_days",
            "approved_by_named_owner": "30_days",
            "pending_owner_approval": "before_customer_reuse",
            "blocked_pending_rewrite": "before_customer_reuse",
            "rejected_by_named_owner": "not_reusable",
            "retired_by_named_owner": "not_reusable",
        }
        return windows[decision]

    def _normalize_override(self, override: str | None) -> str | None:
        if override is None:
            return None
        normalized = override.strip().lower().replace("_", "-")
        aliases = {
            "approved": "approve",
            "approve": "approve",
            "reject": "reject",
            "rejected": "reject",
            "retire": "retire",
            "retired": "retire",
        }
        return aliases.get(normalized)

    def _md(self, value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")
