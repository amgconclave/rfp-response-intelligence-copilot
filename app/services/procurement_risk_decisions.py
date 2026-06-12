# ruff: noqa: E501

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    ProcurementRiskDecisionLedgerResponse,
    ProcurementRiskDecisionOverride,
    ProcurementRiskDecisionPackResponse,
    ProcurementRiskDecisionRecord,
    ProcurementRiskDeskItem,
    ProcurementRiskDeskResponse,
)


class ProcurementRiskDecisionService:
    """Human-in-the-loop decision ledger for Procurement Risk Desk rows."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def decision_ledger(
        self,
        trace_id: str,
        risk_desk: ProcurementRiskDeskResponse,
        decision_overrides: list[ProcurementRiskDecisionOverride] | None = None,
    ) -> ProcurementRiskDecisionLedgerResponse:
        overrides = {override.risk_id: override for override in decision_overrides or []}
        decisions = [
            self._decision_record(risk, overrides.get(risk.risk_id), risk_desk.trace_id)
            for risk in risk_desk.risks
        ]
        release_gate = self._release_gate(decisions)
        summary = self._summary(decisions, overrides)
        return ProcurementRiskDecisionLedgerResponse(
            title="Procurement Risk Decision Ledger",
            ledger_status=release_gate["status"],
            decisions=decisions,
            summary=summary,
            release_gate=release_gate,
            durable_state=self._durable_state(trace_id, decisions, overrides),
            governance_gates=self._governance_gates(decisions),
            trace_spans=self._trace_spans(trace_id, decisions),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def decision_pack(
        self,
        trace_id: str,
        ledger: ProcurementRiskDecisionLedgerResponse,
        risk_desk: ProcurementRiskDeskResponse,
        write_artifact: bool = True,
    ) -> ProcurementRiskDecisionPackResponse:
        pack = self._pack_payload(trace_id, ledger, risk_desk)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "procurement_risk_decisions"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"procurement_risk_decision_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"procurement_risk_decision_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["decision_markdown"] = artifact_path
            pack["artifact_paths"]["decision_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return ProcurementRiskDecisionPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            ledger=ledger,
            risk_desk=risk_desk,
            trace_id=trace_id,
        )

    def _decision_record(
        self,
        risk: ProcurementRiskDeskItem,
        override: ProcurementRiskDecisionOverride | None,
        source_trace_id: str,
    ) -> ProcurementRiskDecisionRecord:
        decision_status = override.decision_status if override else self._default_status(risk)
        decision_state = self._decision_state(decision_status)
        return ProcurementRiskDecisionRecord(
            decision_id=f"prd_decision_{risk.risk_id.removeprefix('prd_')}",
            risk_id=risk.risk_id,
            category=risk.category,
            risk_severity=risk.severity,
            risk_score=risk.risk_score,
            owner_role=override.owner_role if override and override.owner_role else risk.owner_role,
            reviewer_role=override.reviewer_role if override and override.reviewer_role else risk.reviewer_role,
            decision_status=decision_status,
            decision_state=decision_state,
            release_effect=self._release_effect(decision_status, risk),
            approval_gate=self._approval_gate(decision_status, risk),
            required_action=self._required_action(decision_status, risk),
            decided_by=override.decided_by if override else None,
            evidence_reference=override.evidence_reference if override else None,
            decision_note=override.decision_note if override else self._default_note(risk),
            expires_at=override.expires_at if override else None,
            source_trace_id=source_trace_id,
        )

    def _default_status(self, risk: ProcurementRiskDeskItem) -> str:
        if risk.status == "blocked" or risk.severity == "critical":
            return "pending_exception"
        if risk.status == "needs_owner_review" or risk.severity in {"high", "medium"}:
            return "pending_owner_approval"
        return "accepted"

    def _decision_state(self, status: str) -> str:
        if status in {"approved", "approved_with_conditions", "exception_granted", "accepted"}:
            return "approved"
        if status in {"rejected", "exception_rejected"}:
            return "rejected"
        if status in {"needs_more_evidence", "pending_exception", "pending_owner_approval"}:
            return "pending"
        return "pending"

    def _release_effect(self, status: str, risk: ProcurementRiskDeskItem) -> str:
        if status in {"rejected", "exception_rejected", "pending_exception"}:
            return "hold_submission"
        if status in {"needs_more_evidence", "pending_owner_approval"}:
            return "owner_review_required"
        if status == "approved_with_conditions" or (status == "accepted" and risk.severity == "high"):
            return "conditional_release"
        return "can_submit"

    def _approval_gate(self, status: str, risk: ProcurementRiskDeskItem) -> str:
        if status in {"pending_exception", "exception_granted", "exception_rejected"}:
            return "exception_control"
        if risk.severity in {"critical", "high"}:
            return "executive_or_owner_approval"
        if risk.severity == "medium":
            return "owner_attestation"
        return "monitor"

    def _required_action(self, status: str, risk: ProcurementRiskDeskItem) -> str:
        if status == "pending_exception":
            return "Record exception decision or attach approved source evidence before customer submission."
        if status == "pending_owner_approval":
            return f"{risk.owner_role} must approve wording and evidence support before release."
        if status == "needs_more_evidence":
            return "Retrieve or attach stronger packet evidence before approving this risk."
        if status in {"rejected", "exception_rejected"}:
            return "Remove or rewrite the customer-facing commitment before submission."
        if status == "exception_granted":
            return "Attach exception rationale, expiry, and reviewer approval to the final submission packet."
        if status == "approved_with_conditions":
            return "Release only with the recorded caveat and cited evidence reference."
        return "No action beyond monitoring for packet changes."

    def _default_note(self, risk: ProcurementRiskDeskItem) -> str:
        if risk.status == "blocked" or risk.severity == "critical":
            return "Awaiting explicit owner exception because the desk marked this risk as blocked or critical."
        if risk.status == "needs_owner_review" or risk.severity in {"high", "medium"}:
            return "Awaiting named owner approval before customer-facing reuse."
        return "Accepted for monitoring based on current local packet evidence."

    def _summary(
        self,
        decisions: list[ProcurementRiskDecisionRecord],
        overrides: dict[str, ProcurementRiskDecisionOverride],
    ) -> dict[str, Any]:
        states = Counter(decision.decision_state for decision in decisions)
        effects = Counter(decision.release_effect for decision in decisions)
        statuses = Counter(decision.decision_status for decision in decisions)
        return {
            "decision_count": len(decisions),
            "approved_count": states.get("approved", 0),
            "pending_count": states.get("pending", 0),
            "rejected_count": states.get("rejected", 0),
            "hold_submission_count": effects.get("hold_submission", 0),
            "owner_review_required_count": effects.get("owner_review_required", 0),
            "conditional_release_count": effects.get("conditional_release", 0),
            "override_count": len(overrides),
            "status_counts": dict(sorted(statuses.items())),
            "release_effect_counts": dict(sorted(effects.items())),
        }

    def _release_gate(self, decisions: list[ProcurementRiskDecisionRecord]) -> dict[str, Any]:
        hold = [decision.risk_id for decision in decisions if decision.release_effect == "hold_submission"]
        review = [decision.risk_id for decision in decisions if decision.release_effect == "owner_review_required"]
        conditional = [decision.risk_id for decision in decisions if decision.release_effect == "conditional_release"]
        status = "hold_submission" if hold else "owner_review_required" if review else "conditional_release" if conditional else "can_submit"
        return {
            "status": status,
            "hold_risk_ids": hold,
            "owner_review_risk_ids": review,
            "conditional_release_risk_ids": conditional,
            "submission_allowed": status in {"conditional_release", "can_submit"},
            "exit_criteria": "All desk risks must be approved, conditionally approved, or explicitly excepted with evidence.",
        }

    def _durable_state(
        self,
        trace_id: str,
        decisions: list[ProcurementRiskDecisionRecord],
        overrides: dict[str, ProcurementRiskDecisionOverride],
    ) -> dict[str, Any]:
        return {
            "checkpoint_id": "procurement-risk-decisions.owner-ledger.v1",
            "resumable": True,
            "state_storage": "storage/procurement_risk_decisions/*.json",
            "trace_id": trace_id,
            "applied_override_risk_ids": sorted(overrides),
            "pending_risk_ids": [decision.risk_id for decision in decisions if decision.decision_state == "pending"],
            "implemented_patterns": ["human_in_the_loop", "durable_workflows", "governance", "trace_analysis"],
        }

    def _governance_gates(self, decisions: list[ProcurementRiskDecisionRecord]) -> list[dict[str, Any]]:
        return [
            {
                "gate_id": "risk-owner-decision",
                "status": "blocked" if any(decision.decision_state == "pending" for decision in decisions) else "complete",
                "pattern": "human_in_the_loop",
                "required_records": [decision.risk_id for decision in decisions if decision.decision_state == "pending"],
                "exit_criteria": "Every routed risk has a named owner decision.",
            },
            {
                "gate_id": "exception-control",
                "status": "blocked" if any(decision.decision_status == "pending_exception" for decision in decisions) else "complete",
                "pattern": "governance",
                "required_records": [decision.risk_id for decision in decisions if "exception" in decision.decision_status],
                "exit_criteria": "Every exception is granted or rejected with evidence and expiry.",
            },
            {
                "gate_id": "submission-release",
                "status": self._release_gate(decisions)["status"],
                "pattern": "durable_workflows",
                "required_records": [decision.risk_id for decision in decisions if decision.release_effect != "can_submit"],
                "exit_criteria": "No hold or owner-review decision remains.",
            },
        ]

    def _trace_spans(self, trace_id: str, decisions: list[ProcurementRiskDecisionRecord]) -> list[dict[str, Any]]:
        return [
            {
                "span_id": f"{trace_id}.procurement-risk-decisions.ledger",
                "operation": "owner_decision_ledger",
                "status": "ok",
                "decision_count": len(decisions),
                "pending_count": sum(decision.decision_state == "pending" for decision in decisions),
                "pattern": "trace_analysis",
            },
            {
                "span_id": f"{trace_id}.procurement-risk-decisions.release-gate",
                "operation": "decision_release_gate",
                "status": self._release_gate(decisions)["status"],
                "hold_count": sum(decision.release_effect == "hold_submission" for decision in decisions),
                "conditional_count": sum(decision.release_effect == "conditional_release" for decision in decisions),
                "pattern": "governance",
            },
        ]

    def _pack_payload(
        self,
        trace_id: str,
        ledger: ProcurementRiskDecisionLedgerResponse,
        risk_desk: ProcurementRiskDeskResponse,
    ) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Procurement Risk Decision Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "ledger_status": ledger.ledger_status,
            "summary": ledger.summary,
            "release_gate": ledger.release_gate,
            "decisions": [decision.model_dump(mode="json") for decision in ledger.decisions],
            "durable_state": ledger.durable_state,
            "governance_gates": ledger.governance_gates,
            "trace_spans": ledger.trace_spans,
            "risk_desk_summary": risk_desk.summary,
            "risk_desk_trace_id": risk_desk.trace_id,
            "local_proof_commands": ledger.local_proof_commands,
            "limitations": ledger.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        lines = [
            "# Procurement Risk Decision Pack",
            "",
            "## Summary",
            "",
            f"- Ledger status: {pack['ledger_status']}",
            f"- Decisions: {pack['summary']['decision_count']}",
            f"- Approved: {pack['summary']['approved_count']}",
            f"- Pending: {pack['summary']['pending_count']}",
            f"- Rejected: {pack['summary']['rejected_count']}",
            f"- Holds: {pack['summary']['hold_submission_count']}",
            f"- Owner review required: {pack['summary']['owner_review_required_count']}",
            f"- Conditional release: {pack['summary']['conditional_release_count']}",
            "",
            "## Release Gate",
            "",
        ]
        for key, value in pack["release_gate"].items():
            lines.append(f"- {self._md(key)}: {self._md(value)}")
        lines.extend(["", "## Decisions", ""])
        self._append_dict_table(
            lines,
            pack["decisions"],
            ["risk_id", "category", "decision_status", "release_effect", "owner_role", "reviewer_role"],
        )
        lines.extend(["", "## Governance Gates", ""])
        self._append_dict_table(lines, pack["governance_gates"], ["gate_id", "status", "pattern", "exit_criteria"])
        lines.extend(["", "## Trace Analysis", ""])
        self._append_dict_table(lines, pack["trace_spans"], ["span_id", "operation", "status", "pattern"])
        lines.extend(["", "## Required Actions", ""])
        for decision in pack["decisions"]:
            lines.append(f"- {decision['risk_id']}: {decision['required_action']}")
        lines.extend(["", "## Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Decision Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/procurement/risk-decision-ledger" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/procurement/risk-decision-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m pytest -q",
            "python -m ruff check .",
            "python scripts\\dashboard_smoke.py",
            (
                'rg "procurement/risk-decision|Procurement Risk Decision|procurement_risk_decisions" '
                "app dashboard docs README.md tests scripts sample_data Makefile"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "The ledger is deterministic and local; it models owner decisions but does not create legally binding approvals.",
            "Decision overrides are request-scoped unless callers persist the generated JSON artifact or integrate a workflow store.",
            "Final release still requires real legal, finance, privacy, risk, and implementation approval in production.",
            "External services remain optional; all default decisions run with local sample data and mock provider behavior.",
        ]

    def _append_dict_table(self, lines: list[str], rows: list[dict[str, Any]], fields: list[str]) -> None:
        if not rows:
            lines.append("No rows.")
            return
        lines.append("| " + " | ".join(fields) + " |")
        lines.append("| " + " | ".join("---" for _ in fields) + " |")
        for row in rows:
            lines.append("| " + " | ".join(self._md(row.get(field, "")) for field in fields) + " |")

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
