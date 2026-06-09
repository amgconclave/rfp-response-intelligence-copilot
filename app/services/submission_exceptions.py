from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import Settings
from app.models.api import (
    ReviewerCollaborationResponse,
    SubmissionDecisionResponse,
    SubmissionExceptionItem,
    SubmissionExceptionPackResponse,
    SubmissionExceptionRegisterResponse,
)


class SubmissionExceptionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_register(
        self,
        trace_id: str,
        submission_decision: SubmissionDecisionResponse,
        reviewer_collaboration: ReviewerCollaborationResponse | None = None,
    ) -> SubmissionExceptionRegisterResponse:
        exceptions = self._exception_items(submission_decision, reviewer_collaboration)
        summary = self._summary(exceptions, submission_decision, reviewer_collaboration)
        return SubmissionExceptionRegisterResponse(
            title="Submission Exception Register",
            register_status=self._register_status(summary),
            exceptions=exceptions,
            summary=summary,
            approval_queue=self._approval_queue(exceptions, submission_decision),
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def exception_pack(
        self,
        trace_id: str,
        exception_register: SubmissionExceptionRegisterResponse,
        write_artifact: bool = True,
    ) -> SubmissionExceptionPackResponse:
        pack = self._pack_payload(trace_id, exception_register)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "exception_registers"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"submission_exception_register_{safe_trace_id}.md"
            json_path = pack_dir / f"submission_exception_register_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["exception_register_markdown"] = artifact_path
            pack["artifact_paths"]["exception_register_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return SubmissionExceptionPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            exception_register=exception_register,
            trace_id=trace_id,
        )

    def _exception_items(
        self,
        decision: SubmissionDecisionResponse,
        collaboration: ReviewerCollaborationResponse | None,
    ) -> list[SubmissionExceptionItem]:
        items: list[SubmissionExceptionItem] = []
        for issue in decision.blocking_issues:
            items.append(
                self._item(
                    items,
                    source=str(issue.get("source", "blocking_issue")),
                    waiver_type="blocking_risk_waiver",
                    severity=str(issue.get("severity", "high")),
                    owner=str(issue.get("owner", "proposal_manager")),
                    title=str(issue.get("title", "Submission blocker requires exception review.")),
                    related_id=issue.get("related_id"),
                    source_signals=["submission_decision.blocking_issues"],
                    linked_artifacts=self._artifact_links(decision),
                )
            )
        for exception in decision.exception_list:
            items.append(
                self._item(
                    items,
                    source=str(exception.get("source", "submission_exception")),
                    waiver_type="conditional_submission_exception",
                    severity="medium",
                    owner=str(exception.get("owner", "proposal_manager")),
                    title=str(exception.get("title", "Conditional submission exception requires approval.")),
                    resolution=str(exception.get("resolution", "")),
                    source_signals=["submission_decision.exception_list"],
                    linked_artifacts=self._artifact_links(decision),
                )
            )
        if collaboration:
            for comment in collaboration.decision_comments:
                if comment.status == "open" or comment.sentiment == "blocker":
                    items.append(
                        self._item(
                            items,
                            source=comment.related_artifact or "reviewer_collaboration",
                            waiver_type="review_comment_exception",
                            severity=comment.severity,
                            owner=comment.reviewer_role,
                            title=comment.comment,
                            related_id=comment.related_requirement_id,
                            resolution=comment.required_action,
                            source_signals=[f"reviewer_comment:{comment.comment_id}"],
                            linked_artifacts=[
                                {
                                    "artifact": "reviewer_collaboration",
                                    "trace_id": collaboration.trace_id,
                                    "status": collaboration.board_status,
                                }
                            ],
                        )
                    )
            for item in collaboration.redline_summary.get("items", [])[:8]:
                items.append(
                    self._item(
                        items,
                        source=str(item.get("source", "redline")),
                        waiver_type="redline_exception",
                        severity=str(item.get("risk_level", "high")),
                        owner="legal",
                        title=str(item.get("title", "Redline item requires legal exception.")),
                        related_id=str(item.get("id", "")),
                        resolution=str(item.get("suggested_redline", "")),
                        source_signals=["reviewer_collaboration.redline_summary"],
                        linked_artifacts=[
                            {
                                "artifact": "reviewer_collaboration",
                                "trace_id": collaboration.trace_id,
                                "redline_count": collaboration.redline_summary.get("redline_count", 0),
                            }
                        ],
                    )
                )
        return self._dedupe(items)[:24]

    def _item(
        self,
        items: list[SubmissionExceptionItem],
        source: str,
        waiver_type: str,
        severity: str,
        owner: str,
        title: str,
        related_id: object = None,
        resolution: str = "",
        source_signals: list[str] | None = None,
        linked_artifacts: list[dict[str, Any]] | None = None,
    ) -> SubmissionExceptionItem:
        normalized_owner = self._owner_slug(owner)
        normalized_severity = self._severity(severity)
        return SubmissionExceptionItem(
            exception_id=f"exc_{len(items) + 1:03d}_{self._slug(source)}",
            source=source,
            waiver_type=waiver_type,
            severity=normalized_severity,
            owner=normalized_owner,
            approver_role=self._approver(normalized_owner, source),
            status="requires_approval" if normalized_severity in {"critical", "high"} else "conditional",
            expires_at=self._expiry(normalized_severity),
            title=title,
            risk_acceptance=self._risk_acceptance(normalized_severity, resolution),
            required_evidence=self._required_evidence(source, normalized_severity),
            linked_requirement_ids=[str(related_id)] if related_id else [],
            linked_artifacts=linked_artifacts or [],
            source_signals=source_signals or [],
            local_policy=self._local_policy(waiver_type, normalized_severity),
            escalation_path=self._escalation_path(normalized_owner, normalized_severity),
        )

    def _summary(
        self,
        exceptions: list[SubmissionExceptionItem],
        decision: SubmissionDecisionResponse,
        collaboration: ReviewerCollaborationResponse | None,
    ) -> dict[str, Any]:
        severity_counts = Counter(item.severity for item in exceptions)
        owner_counts = Counter(item.approver_role for item in exceptions)
        expiry_threshold = (datetime.now(UTC) + timedelta(days=10)).date().isoformat()
        expiring_soon = sum(item.expires_at <= expiry_threshold for item in exceptions)
        return {
            "exception_count": len(exceptions),
            "critical_count": severity_counts.get("critical", 0),
            "high_count": severity_counts.get("high", 0),
            "conditional_count": sum(item.status == "conditional" for item in exceptions),
            "requires_approval_count": sum(item.status == "requires_approval" for item in exceptions),
            "expiring_soon_count": expiring_soon,
            "submission_decision": decision.decision,
            "submission_score": decision.score,
            "reviewer_board_status": collaboration.board_status if collaboration else None,
            "approver_counts": dict(sorted(owner_counts.items())),
            "ready_for_exception_submit": (
                decision.decision == "submit_with_exceptions"
                and severity_counts.get("critical", 0) == 0
                and bool(exceptions)
            ),
        }

    def _approval_queue(
        self,
        exceptions: list[SubmissionExceptionItem],
        decision: SubmissionDecisionResponse,
    ) -> list[dict[str, Any]]:
        queue = []
        grouped: dict[str, list[SubmissionExceptionItem]] = {}
        for item in exceptions:
            grouped.setdefault(item.approver_role, []).append(item)
        approval_reasons = {item["owner"]: item["reason"] for item in decision.approvals_required}
        for approver, items in sorted(grouped.items()):
            highest = self._highest_severity(items)
            queue.append(
                {
                    "approver_role": approver,
                    "exception_count": len(items),
                    "highest_severity": highest,
                    "required_by": min(item.expires_at for item in items),
                    "approval_reason": approval_reasons.get(approver, "Approve local submission exception posture."),
                    "next_action": items[0].risk_acceptance,
                }
            )
        return queue

    def _pack_payload(
        self,
        trace_id: str,
        register: SubmissionExceptionRegisterResponse,
    ) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Submission Exception Register Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "register_status": register.register_status,
            "summary": register.summary,
            "exceptions": [item.model_dump(mode="json") for item in register.exceptions],
            "approval_queue": register.approval_queue,
            "endpoint_references": register.endpoint_references,
            "local_proof_commands": register.local_proof_commands,
            "limitations": register.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        summary = pack["summary"]
        lines = [
            "# Submission Exception Register Pack",
            "",
            "## Summary",
            "",
            f"- Register status: {pack['register_status']}",
            f"- Submission decision: {summary['submission_decision']} score={summary['submission_score']}",
            f"- Exceptions: {summary['exception_count']}",
            f"- Critical: {summary['critical_count']}",
            f"- High: {summary['high_count']}",
            f"- Requires approval: {summary['requires_approval_count']}",
            f"- Ready for exception submit: {summary['ready_for_exception_submit']}",
            "",
            "## Exception Register",
            "",
            "| ID | Source | Type | Severity | Owner | Approver | Status | Expires | Title |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for item in pack["exceptions"]:
            lines.append(
                f"| {item['exception_id']} | {item['source']} | {item['waiver_type']} | "
                f"{item['severity']} | {item['owner']} | {item['approver_role']} | "
                f"{item['status']} | {item['expires_at']} | {self._md(item['title'])} |"
            )
        lines.extend(["", "## Approval Queue", ""])
        lines.append("| Approver | Exceptions | Highest Severity | Required By | Next Action |")
        lines.append("| --- | ---: | --- | --- | --- |")
        for item in pack["approval_queue"]:
            lines.append(
                f"| {item['approver_role']} | {item['exception_count']} | {item['highest_severity']} | "
                f"{item['required_by']} | {self._md(item['next_action'])} |"
            )
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```bash\n{command}\n```" for command in pack["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Exception Register Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _artifact_links(self, decision: SubmissionDecisionResponse) -> list[dict[str, Any]]:
        return [
            {"artifact": key, **value}
            for key, value in decision.artifact_links.items()
            if isinstance(value, dict)
        ][:6]

    def _register_status(self, summary: dict[str, Any]) -> str:
        if summary["critical_count"]:
            return "blocked"
        if summary["high_count"] or summary["requires_approval_count"]:
            return "requires_approval"
        if summary["exception_count"]:
            return "conditional"
        return "clear"

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {"method": "POST", "path": "/rfp/submission-decision", "purpose": "Creates go/no-go signals."},
            {"method": "POST", "path": "/rfp/reviewer-collaboration", "purpose": "Adds review comments and redlines."},
            {"method": "POST", "path": "/rfp/exception-register", "purpose": "Builds local exception register."},
            {"method": "POST", "path": "/rfp/exception-pack", "purpose": "Writes Markdown/JSON exception artifacts."},
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            "python -m pytest -q",
            "python -m ruff check .",
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/exception-register" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/exception-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'rg "exception-register|exception-pack|Submission Exception|exception_registers" '
                "app dashboard docs README.md tests Makefile"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Exception records are deterministic local workflow artifacts, not persisted approval transactions.",
            "Approval status is derived from local signals and must be confirmed by accountable humans.",
            "Expiry dates are local policy defaults, not synced with a ticketing, CLM, or GRC system.",
            "Generated files under storage/exception_registers are ignored by git and should be regenerated locally.",
        ]

    def _required_evidence(self, source: str, severity: str) -> list[str]:
        evidence = ["Named approver", "Business rationale", "Customer-facing caveat or revised response text"]
        if source in {"contract", "redline", "contract_risk"}:
            evidence.append("Legal redline or fallback language")
        if source in {"red_team", "citations", "review_board", "evidence_gap"} or severity in {"critical", "high"}:
            evidence.append("Cited source evidence or explicit missing-evidence refusal")
        if source == "pricing":
            evidence.append("Finance approval for discount, packaging, payment, or margin exception")
        return evidence

    def _risk_acceptance(self, severity: str, resolution: str) -> str:
        if resolution:
            return resolution
        if severity == "critical":
            return "Do not submit unless the executive sponsor approves a written exception."
        if severity == "high":
            return "Approve only with owner sign-off, cited evidence, and customer-facing caveat."
        return "Track as conditional exception and close before final QA when possible."

    def _local_policy(self, waiver_type: str, severity: str) -> str:
        if waiver_type == "redline_exception":
            return "Legal exceptions require fallback language and final legal approval before submission."
        if severity in {"critical", "high"}:
            return "High-risk exceptions require executive, owner, and proposal-manager approval."
        return "Medium-risk exceptions require owner acknowledgement and closure criteria."

    def _escalation_path(self, owner: str, severity: str) -> list[str]:
        path = [owner, self._approver(owner, "")]
        if severity in {"critical", "high"}:
            path.append("executive_sponsor")
        return list(dict.fromkeys(path))

    def _approver(self, owner: str, source: str) -> str:
        if owner in {"legal", "security", "finance", "executive_sponsor"}:
            return owner
        if source in {"contract", "redline", "contract_risk"}:
            return "legal"
        if source == "pricing":
            return "finance"
        if source in {"red_team", "citations"}:
            return "security"
        return "proposal_manager"

    def _expiry(self, severity: str) -> str:
        days = {"critical": 3, "high": 7, "medium": 14, "low": 30}.get(severity, 14)
        return (datetime.now(UTC) + timedelta(days=days)).date().isoformat()

    def _highest_severity(self, items: list[SubmissionExceptionItem]) -> str:
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return min((item.severity for item in items), key=lambda value: order.get(value, 9))

    def _severity(self, severity: str) -> str:
        lowered = severity.lower()
        if lowered in {"critical", "high", "medium", "low"}:
            return lowered
        if lowered in {"blocked", "not_ready"}:
            return "high"
        return "medium"

    def _owner_slug(self, owner: str) -> str:
        normalized = owner.lower().replace(" ", "_").replace("-", "_")
        aliases = {
            "commercial_owner": "sales",
            "compliance_lead": "legal",
            "security_architect": "security",
            "proposal": "proposal_manager",
            "sales_leadership": "sales",
        }
        return aliases.get(normalized, normalized or "proposal_manager")

    def _dedupe(self, items: list[SubmissionExceptionItem]) -> list[SubmissionExceptionItem]:
        seen = set()
        deduped = []
        for item in items:
            key = (item.source, item.owner, item.title)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "local"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
