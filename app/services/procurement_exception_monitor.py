# ruff: noqa: E501

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, date, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    ProcurementExceptionMonitorItem,
    ProcurementExceptionMonitorPackResponse,
    ProcurementExceptionMonitorResponse,
    ProcurementRiskDecisionLedgerResponse,
    ProcurementRiskDecisionRecord,
)


class ProcurementExceptionMonitorService:
    """Replay procurement owner decisions into expiry, evidence, and release controls."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def monitor(
        self,
        trace_id: str,
        ledger: ProcurementRiskDecisionLedgerResponse,
        reference_date: str | None = None,
    ) -> ProcurementExceptionMonitorResponse:
        as_of = self._reference_date(reference_date)
        exceptions = [self._monitor_item(decision, as_of) for decision in ledger.decisions]
        summary = self._summary(exceptions, as_of)
        status = self._status(summary)
        return ProcurementExceptionMonitorResponse(
            title="Procurement Exception Monitor",
            monitor_status=status,
            exceptions=exceptions,
            summary=summary,
            owner_queues=self._owner_queues(exceptions),
            state_machine=self._state_machine(trace_id, status, exceptions),
            governance_gates=self._governance_gates(exceptions),
            trace_spans=self._trace_spans(trace_id, exceptions),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def monitor_pack(
        self,
        trace_id: str,
        monitor: ProcurementExceptionMonitorResponse,
        ledger: ProcurementRiskDecisionLedgerResponse,
        write_artifact: bool = True,
    ) -> ProcurementExceptionMonitorPackResponse:
        pack = self._pack_payload(trace_id, monitor, ledger)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "procurement_exception_monitor"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"procurement_exception_monitor_{safe_trace_id}.md"
            json_path = pack_dir / f"procurement_exception_monitor_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["exception_monitor_markdown"] = artifact_path
            pack["artifact_paths"]["exception_monitor_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return ProcurementExceptionMonitorPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            monitor=monitor,
            ledger=ledger,
            trace_id=trace_id,
        )

    def _monitor_item(self, decision: ProcurementRiskDecisionRecord, as_of: date) -> ProcurementExceptionMonitorItem:
        expiry_date = self._parse_date(decision.expires_at)
        days_to_expiry = (expiry_date - as_of).days if expiry_date else None
        expiry_status = self._expiry_status(decision, days_to_expiry)
        monitor_state = self._monitor_state(decision, expiry_status)
        severity = self._severity(decision, monitor_state, expiry_status)
        return ProcurementExceptionMonitorItem(
            exception_id=f"prx_{decision.risk_id.removeprefix('prd_')}",
            risk_id=decision.risk_id,
            category=decision.category,
            owner_role=decision.owner_role,
            reviewer_role=decision.reviewer_role,
            decision_status=decision.decision_status,
            monitor_state=monitor_state,
            expiry_status=expiry_status,
            release_effect=decision.release_effect,
            severity=severity,
            days_to_expiry=days_to_expiry,
            evidence_reference=decision.evidence_reference,
            required_action=self._required_action(decision, monitor_state, expiry_status),
            escalation_path=self._escalation_path(decision, monitor_state),
            checkpoint_id=f"procurement-exception-monitor.{decision.risk_id}.v1",
            transition_log=self._transition_log(decision, monitor_state, expiry_status),
        )

    def _expiry_status(
        self,
        decision: ProcurementRiskDecisionRecord,
        days_to_expiry: int | None,
    ) -> str:
        if decision.decision_status not in {"exception_granted", "approved_with_conditions"}:
            return "not_applicable"
        if days_to_expiry is None:
            return "missing_expiry"
        if days_to_expiry < 0:
            return "expired"
        if days_to_expiry <= 30:
            return "expires_soon"
        return "active"

    def _monitor_state(self, decision: ProcurementRiskDecisionRecord, expiry_status: str) -> str:
        if expiry_status == "expired":
            return "expired_hold"
        if expiry_status == "missing_expiry":
            return "expiry_missing_hold"
        if decision.decision_state == "pending":
            return "pending_owner_decision"
        if decision.decision_state == "rejected":
            return "rejected_commitment"
        if not decision.evidence_reference and decision.decision_status in {"exception_granted", "approved_with_conditions"}:
            return "evidence_hold"
        if expiry_status == "expires_soon":
            return "expiry_watch"
        if decision.release_effect == "conditional_release":
            return "conditional_release_watch"
        return "accepted_monitoring"

    def _severity(
        self,
        decision: ProcurementRiskDecisionRecord,
        monitor_state: str,
        expiry_status: str,
    ) -> str:
        if monitor_state in {"expired_hold", "expiry_missing_hold", "rejected_commitment"}:
            return "critical"
        if monitor_state in {"pending_owner_decision", "evidence_hold"} or decision.release_effect == "hold_submission":
            return "high"
        if expiry_status == "expires_soon" or decision.release_effect == "conditional_release":
            return "medium"
        return "low"

    def _required_action(
        self,
        decision: ProcurementRiskDecisionRecord,
        monitor_state: str,
        expiry_status: str,
    ) -> str:
        if monitor_state == "expired_hold":
            return "Block reuse and renew or revoke the exception before proposal submission."
        if monitor_state == "expiry_missing_hold":
            return "Add an exception expiry date and reviewer approval before release."
        if monitor_state == "pending_owner_decision":
            return decision.required_action
        if monitor_state == "rejected_commitment":
            return "Remove rejected commitment language from the response package."
        if monitor_state == "evidence_hold":
            return "Attach a specific evidence reference to support the approved exception."
        if expiry_status == "expires_soon":
            return "Schedule owner renewal or retire this exception before the next submission checkpoint."
        if monitor_state == "conditional_release_watch":
            return "Confirm the recorded condition appears in the final customer-facing response."
        return "Monitor for packet amendments, source freshness changes, or owner revocation."

    def _escalation_path(self, decision: ProcurementRiskDecisionRecord, monitor_state: str) -> list[str]:
        path = [decision.owner_role, decision.reviewer_role]
        if monitor_state in {"expired_hold", "expiry_missing_hold", "rejected_commitment"}:
            path.append("Proposal Manager")
        if decision.category in {"legal", "insurance", "data_residency"}:
            path.append("Compliance Lead")
        if decision.category == "pricing":
            path.append("Sales Leadership")
        return list(dict.fromkeys(path))

    def _transition_log(
        self,
        decision: ProcurementRiskDecisionRecord,
        monitor_state: str,
        expiry_status: str,
    ) -> list[dict[str, Any]]:
        return [
            {
                "from_state": "ledger_recorded",
                "to_state": "expiry_checked",
                "condition": f"decision_status={decision.decision_status}",
                "checkpoint": "procurement-exception-monitor.expiry-check.v1",
            },
            {
                "from_state": "expiry_checked",
                "to_state": monitor_state,
                "condition": f"expiry_status={expiry_status}; release_effect={decision.release_effect}",
                "checkpoint": f"procurement-exception-monitor.{decision.risk_id}.v1",
            },
        ]

    def _summary(self, exceptions: list[ProcurementExceptionMonitorItem], as_of: date) -> dict[str, Any]:
        states = Counter(item.monitor_state for item in exceptions)
        severities = Counter(item.severity for item in exceptions)
        expiry = Counter(item.expiry_status for item in exceptions)
        hold_states = {"expired_hold", "expiry_missing_hold", "evidence_hold", "pending_owner_decision", "rejected_commitment"}
        return {
            "exception_count": len(exceptions),
            "critical_count": severities.get("critical", 0),
            "high_count": severities.get("high", 0),
            "hold_count": sum(states[state] for state in hold_states),
            "expiring_or_expired_count": expiry.get("expires_soon", 0) + expiry.get("expired", 0),
            "missing_expiry_count": expiry.get("missing_expiry", 0),
            "missing_evidence_count": sum(1 for item in exceptions if not item.evidence_reference and item.decision_status in {"exception_granted", "approved_with_conditions"}),
            "state_counts": dict(sorted(states.items())),
            "severity_counts": dict(sorted(severities.items())),
            "expiry_counts": dict(sorted(expiry.items())),
            "reference_date": as_of.isoformat(),
        }

    def _status(self, summary: dict[str, Any]) -> str:
        if summary["critical_count"] or summary["hold_count"]:
            return "hold_submission"
        if summary["expiring_or_expired_count"] or summary["high_count"]:
            return "owner_review_required"
        return "can_submit"

    def _owner_queues(self, exceptions: list[ProcurementExceptionMonitorItem]) -> list[dict[str, Any]]:
        grouped: dict[str, list[ProcurementExceptionMonitorItem]] = {}
        for item in exceptions:
            if item.severity == "low":
                continue
            grouped.setdefault(item.owner_role, []).append(item)
        return [
            {
                "owner_role": owner,
                "item_count": len(rows),
                "critical_count": sum(row.severity == "critical" for row in rows),
                "risk_ids": [row.risk_id for row in rows],
                "next_action": rows[0].required_action,
                "escalation_path": rows[0].escalation_path,
            }
            for owner, rows in sorted(grouped.items())
        ]

    def _state_machine(
        self,
        trace_id: str,
        status: str,
        exceptions: list[ProcurementExceptionMonitorItem],
    ) -> dict[str, Any]:
        return {
            "workflow_id": "procurement-exception-monitor.v1",
            "trace_id": trace_id,
            "current_state": status,
            "checkpoint_id": "procurement-exception-monitor.release-control.v1",
            "resumable": True,
            "implemented_patterns": [
                "typed_contracts",
                "structured_outputs",
                "state_machine_workflow",
                "checkpointing",
                "conditional_routing",
                "traceable_node_transitions",
            ],
            "blocked_risk_ids": [item.risk_id for item in exceptions if item.severity in {"critical", "high"}],
            "state_storage": "storage/procurement_exception_monitor/*.json",
        }

    def _governance_gates(self, exceptions: list[ProcurementExceptionMonitorItem]) -> list[dict[str, Any]]:
        return [
            {
                "gate_id": "exception-expiry-control",
                "status": "blocked" if any(item.expiry_status in {"expired", "missing_expiry"} for item in exceptions) else "complete",
                "required_records": [item.risk_id for item in exceptions if item.expiry_status in {"expired", "missing_expiry"}],
                "exit_criteria": "Every granted exception has a future expiry or has been retired.",
            },
            {
                "gate_id": "exception-evidence-control",
                "status": "blocked" if any(item.monitor_state == "evidence_hold" for item in exceptions) else "complete",
                "required_records": [item.risk_id for item in exceptions if item.monitor_state == "evidence_hold"],
                "exit_criteria": "Every approved exception references specific packet evidence.",
            },
            {
                "gate_id": "submission-release-control",
                "status": "blocked" if any(item.severity in {"critical", "high"} for item in exceptions) else "ready",
                "required_records": [item.risk_id for item in exceptions if item.severity in {"critical", "high"}],
                "exit_criteria": "No expired, pending, rejected, or evidence-missing exception remains.",
            },
        ]

    def _trace_spans(self, trace_id: str, exceptions: list[ProcurementExceptionMonitorItem]) -> list[dict[str, Any]]:
        return [
            {
                "span_id": f"{trace_id}.procurement-exception-monitor.replay",
                "operation": "decision_ledger_replay",
                "status": "ok",
                "item_count": len(exceptions),
                "pattern": "traceable_node_transitions",
            },
            {
                "span_id": f"{trace_id}.procurement-exception-monitor.release-control",
                "operation": "exception_release_control",
                "status": "blocked" if any(item.severity in {"critical", "high"} for item in exceptions) else "ready",
                "critical_count": sum(item.severity == "critical" for item in exceptions),
                "high_count": sum(item.severity == "high" for item in exceptions),
                "pattern": "conditional_routing",
            },
        ]

    def _pack_payload(
        self,
        trace_id: str,
        monitor: ProcurementExceptionMonitorResponse,
        ledger: ProcurementRiskDecisionLedgerResponse,
    ) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Procurement Exception Monitor Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "monitor_status": monitor.monitor_status,
            "summary": monitor.summary,
            "exceptions": [item.model_dump(mode="json") for item in monitor.exceptions],
            "owner_queues": monitor.owner_queues,
            "state_machine": monitor.state_machine,
            "governance_gates": monitor.governance_gates,
            "trace_spans": monitor.trace_spans,
            "ledger_status": ledger.ledger_status,
            "ledger_trace_id": ledger.trace_id,
            "local_proof_commands": monitor.local_proof_commands,
            "limitations": monitor.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        lines = [
            "# Procurement Exception Monitor Pack",
            "",
            "## Summary",
            "",
            f"- Monitor status: {pack['monitor_status']}",
            f"- Exceptions monitored: {pack['summary']['exception_count']}",
            f"- Critical: {pack['summary']['critical_count']}",
            f"- High: {pack['summary']['high_count']}",
            f"- Holds: {pack['summary']['hold_count']}",
            f"- Expiring or expired: {pack['summary']['expiring_or_expired_count']}",
            f"- Missing expiry: {pack['summary']['missing_expiry_count']}",
            "",
            "## Exception Monitor",
            "",
        ]
        self._append_dict_table(
            lines,
            pack["exceptions"],
            ["risk_id", "category", "decision_status", "monitor_state", "expiry_status", "severity", "owner_role"],
        )
        lines.extend(["", "## Owner Queues", ""])
        self._append_dict_table(lines, pack["owner_queues"], ["owner_role", "item_count", "critical_count", "risk_ids", "next_action"])
        lines.extend(["", "## State Machine", ""])
        for key, value in pack["state_machine"].items():
            lines.append(f"- {self._md(key)}: {self._md(value)}")
        lines.extend(["", "## Governance Gates", ""])
        self._append_dict_table(lines, pack["governance_gates"], ["gate_id", "status", "required_records", "exit_criteria"])
        lines.extend(["", "## Trace Spans", ""])
        self._append_dict_table(lines, pack["trace_spans"], ["span_id", "operation", "status", "pattern"])
        lines.extend(["", "## Required Actions", ""])
        for item in pack["exceptions"]:
            lines.append(f"- {item['risk_id']}: {item['required_action']}")
        lines.extend(["", "## Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Monitor Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _reference_date(self, reference_date: str | None) -> date:
        if not reference_date:
            return datetime.now(UTC).date()
        return self._parse_date(reference_date) or datetime.now(UTC).date()

    def _parse_date(self, value: str | None) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/procurement/exception-monitor" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/procurement/exception-monitor-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m pytest -q",
            "python -m ruff check .",
            "python scripts\\dashboard_smoke.py",
            (
                'rg "procurement/exception-monitor|Procurement Exception Monitor|procurement_exception_monitor" '
                "app dashboard docs README.md tests scripts sample_data Makefile"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "The monitor replays local ledger state and does not persist owner decisions outside generated JSON artifacts.",
            "Expiry checks use the request reference date or current local date; production should use workflow-system timestamps.",
            "The monitor does not replace legal, finance, privacy, insurance, or delivery approval systems.",
            "External services remain optional; all default outputs run with local sample data and mock provider behavior.",
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
