from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    EvidenceFreshnessResponse,
    EvidenceFreshnessSlaItem,
    EvidenceFreshnessSlaPackResponse,
    EvidenceFreshnessSlaResponse,
)

ESCALATION_OWNERS = {
    "security": "security_director",
    "legal": "general_counsel",
    "customer_success": "vp_customer_success",
    "engineering": "engineering_manager",
    "finance": "finance_director",
    "solutions": "solutions_lead",
    "product": "product_lead",
    "proposal_owner": "proposal_manager",
}


class EvidenceFreshnessSlaService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def ledger(
        self,
        trace_id: str,
        freshness: EvidenceFreshnessResponse,
    ) -> EvidenceFreshnessSlaResponse:
        items = [self._item(source) for source in freshness.sources if self._requires_sla(source)]
        summary = self._summary(items, freshness)
        checkpoints = self._checkpoints(items, summary)
        return EvidenceFreshnessSlaResponse(
            title="Evidence Freshness SLA Ledger",
            status=summary["status"],
            current_state=self._current_state(checkpoints),
            generated_at=datetime.now(UTC).isoformat(),
            summary=summary,
            ledger_items=sorted(
                items,
                key=lambda item: (self._severity_rank(item.severity), item.policy_owner, item.filename),
            ),
            owner_rollups=self._owner_rollups(items),
            endpoint_impact=self._endpoint_impact(items),
            role_crew_queue=self._role_crew_queue(items),
            checkpoints=checkpoints,
            transitions=self._transitions(checkpoints, summary),
            governance_policy=self._governance_policy(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        sla: EvidenceFreshnessSlaResponse,
        freshness: EvidenceFreshnessResponse,
        write_artifact: bool = True,
    ) -> EvidenceFreshnessSlaPackResponse:
        pack = self._pack_payload(trace_id, sla, freshness)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "freshness_sla"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"evidence_freshness_sla_{safe_trace_id}.md"
            json_path = pack_dir / f"evidence_freshness_sla_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["freshness_sla_markdown"] = artifact_path
            pack["artifact_paths"]["freshness_sla_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return EvidenceFreshnessSlaPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            sla=sla,
            freshness=freshness,
            trace_id=trace_id,
        )

    def _requires_sla(self, source: Any) -> bool:
        return (
            source.expiry_status in {"expired", "renewal_due", "renewal_watch", "missing_renewal"}
            or source.risk_level in {"high", "critical"}
            or bool(source.unsupported_claim_flags)
        )

    def _item(self, source: Any) -> EvidenceFreshnessSlaItem:
        severity = self._severity(source)
        status = self._sla_status(source, severity)
        return EvidenceFreshnessSlaItem(
            ledger_id=f"freshness-sla-{self._slug(source.filename)}",
            filename=source.filename,
            document_type=source.document_type,
            policy_owner=source.policy_owner,
            escalation_owner=ESCALATION_OWNERS.get(source.policy_owner, "proposal_manager"),
            severity=severity,
            sla_status=status,
            workflow_state=self._workflow_state(source, status),
            days_until_renewal=source.days_until_renewal,
            days_past_due=max(0, -(source.days_until_renewal or 0)) if source.expiry_status == "expired" else 0,
            response_sla_hours=self._response_sla_hours(severity, status),
            required_action=self._required_action(source, status),
            blocked_endpoints=self._blocked_endpoints(source),
            risk_drivers=source.risk_drivers,
            evidence_flags=source.unsupported_claim_flags,
        )

    def _severity(self, source: Any) -> str:
        if source.expiry_status == "expired" or source.risk_level == "critical":
            return "critical"
        if source.expiry_status == "renewal_due" or source.risk_level == "high" or source.unsupported_claim_flags:
            return "high"
        return "medium"

    def _sla_status(self, source: Any, severity: str) -> str:
        if source.expiry_status == "expired":
            return "breached"
        if source.expiry_status == "missing_renewal":
            return "policy_gap"
        if severity == "critical":
            return "breach_risk"
        if source.expiry_status == "renewal_due":
            return "due_now"
        if source.unsupported_claim_flags:
            return "claim_review_required"
        return "watch"

    def _workflow_state(self, source: Any, status: str) -> str:
        if status == "breached":
            return "quarantine_source"
        if status == "policy_gap":
            return "metadata_remediation"
        if source.unsupported_claim_flags:
            return "claim_owner_approval"
        if status in {"due_now", "breach_risk"}:
            return "owner_sla_review"
        return "renewal_watch"

    def _response_sla_hours(self, severity: str, status: str) -> int:
        if status == "breached":
            return 4
        if severity == "critical":
            return 8
        if severity == "high":
            return 24
        return 72

    def _required_action(self, source: Any, status: str) -> str:
        if status == "breached":
            return "Block customer-facing citation until owner renews or replaces the source."
        if status == "policy_gap":
            return "Add renewal metadata, policy owner signoff, and next review cadence."
        if source.unsupported_claim_flags:
            return "Approve qualified wording or remove unsupported absolute language before draft reuse."
        if status in {"due_now", "breach_risk"}:
            return "Confirm renewal date, owner approval, and retrieval reuse policy before submission."
        return "Track renewal watch item and refresh before the next customer review cycle."

    def _blocked_endpoints(self, source: Any) -> list[str]:
        if source.expiry_status == "expired" or source.risk_level == "critical":
            return source.endpoint_references
        if source.unsupported_claim_flags:
            generation_endpoints = {"/rfp/query", "/rfp/draft-response"}
            return [endpoint for endpoint in source.endpoint_references if endpoint in generation_endpoints]
        return []

    def _summary(self, items: list[EvidenceFreshnessSlaItem], freshness: EvidenceFreshnessResponse) -> dict[str, Any]:
        severity_counts = Counter(item.severity for item in items)
        status_counts = Counter(item.sla_status for item in items)
        owner_counts = Counter(item.policy_owner for item in items)
        blocked_endpoints = {endpoint for item in items for endpoint in item.blocked_endpoints}
        status = "blocked" if status_counts.get("breached", 0) else ("needs_review" if items else "pass")
        return {
            "status": status,
            "source_count": freshness.summary["source_count"],
            "sla_item_count": len(items),
            "breached_count": status_counts.get("breached", 0),
            "due_now_count": status_counts.get("due_now", 0),
            "policy_gap_count": status_counts.get("policy_gap", 0),
            "claim_review_required_count": status_counts.get("claim_review_required", 0),
            "critical_count": severity_counts.get("critical", 0),
            "high_count": severity_counts.get("high", 0),
            "medium_count": severity_counts.get("medium", 0),
            "blocked_endpoint_count": len(blocked_endpoints),
            "severity_counts": dict(sorted(severity_counts.items())),
            "sla_status_counts": dict(sorted(status_counts.items())),
            "owner_counts": dict(sorted(owner_counts.items())),
            "patterns_applied": [
                "typed contracts",
                "structured outputs",
                "dependency injection",
                "state machine workflow",
                "traceable node transitions",
                "role crews",
            ],
        }

    def _owner_rollups(self, items: list[EvidenceFreshnessSlaItem]) -> list[dict[str, Any]]:
        grouped: dict[str, list[EvidenceFreshnessSlaItem]] = defaultdict(list)
        for item in items:
            grouped[item.policy_owner].append(item)
        rows = []
        for owner, owner_items in grouped.items():
            rows.append(
                {
                    "owner": owner,
                    "escalation_owner": ESCALATION_OWNERS.get(owner, "proposal_manager"),
                    "item_count": len(owner_items),
                    "critical_count": sum(item.severity == "critical" for item in owner_items),
                    "breached_count": sum(item.sla_status == "breached" for item in owner_items),
                    "blocked_endpoint_count": len(
                        {endpoint for item in owner_items for endpoint in item.blocked_endpoints}
                    ),
                    "next_action": self._owner_next_action(owner_items),
                }
            )
        return sorted(rows, key=lambda item: (-item["critical_count"], -item["breached_count"], item["owner"]))

    def _endpoint_impact(self, items: list[EvidenceFreshnessSlaItem]) -> list[dict[str, Any]]:
        grouped: dict[str, list[EvidenceFreshnessSlaItem]] = defaultdict(list)
        for item in items:
            for endpoint in item.blocked_endpoints:
                grouped[endpoint].append(item)
        return [
            {
                "endpoint": endpoint,
                "blocked_source_count": len(endpoint_items),
                "owners": sorted({item.policy_owner for item in endpoint_items}),
                "sources": [item.filename for item in sorted(endpoint_items, key=lambda row: row.filename)],
                "mitigation": "Suppress or qualify affected citations until owner SLA items close.",
            }
            for endpoint, endpoint_items in sorted(grouped.items())
        ]

    def _role_crew_queue(self, items: list[EvidenceFreshnessSlaItem]) -> list[dict[str, Any]]:
        rows = []
        for owner in sorted({item.policy_owner for item in items}):
            owner_items = [item for item in items if item.policy_owner == owner]
            rows.append(
                {
                    "role": owner,
                    "crew_lead": ESCALATION_OWNERS.get(owner, "proposal_manager"),
                    "process_mode": "sequential_blocking_review"
                    if any(item.sla_status == "breached" for item in owner_items)
                    else "parallel_owner_review",
                    "assigned_items": [item.ledger_id for item in owner_items],
                    "exit_condition": "All critical and high freshness SLA items are renewed, qualified, or blocked.",
                }
            )
        return rows

    def _checkpoints(self, items: list[EvidenceFreshnessSlaItem], summary: dict[str, Any]) -> list[dict[str, Any]]:
        breached = [item for item in items if item.sla_status == "breached"]
        policy_gaps = [item for item in items if item.sla_status == "policy_gap"]
        claim_reviews = [item for item in items if item.sla_status == "claim_review_required"]
        blocked_endpoints = {endpoint for item in items for endpoint in item.blocked_endpoints}
        return [
            {
                "checkpoint_id": "freshness-sla-cp-001",
                "sequence": 1,
                "state": "ledger_build",
                "status": "complete",
                "owner_role": "ai_engineering",
                "item_count": len(items),
                "exit_condition": "Every freshness risk is converted into a typed SLA ledger row.",
            },
            {
                "checkpoint_id": "freshness-sla-cp-002",
                "sequence": 2,
                "state": "breach_triage",
                "status": "blocked" if breached else "complete",
                "owner_role": "policy_owner",
                "item_count": len(breached),
                "exit_condition": "Expired evidence is renewed, replaced, or blocked from customer citation.",
            },
            {
                "checkpoint_id": "freshness-sla-cp-003",
                "sequence": 3,
                "state": "metadata_and_claim_review",
                "status": "review" if policy_gaps or claim_reviews else "complete",
                "owner_role": "security_legal_review",
                "item_count": len(policy_gaps) + len(claim_reviews),
                "exit_condition": "Missing renewal metadata and unsupported claim wording have owner decisions.",
            },
            {
                "checkpoint_id": "freshness-sla-cp-004",
                "sequence": 4,
                "state": "endpoint_release_gate",
                "status": "blocked" if summary["blocked_endpoint_count"] else ("review" if items else "complete"),
                "owner_role": "proposal_operations",
                "item_count": len(blocked_endpoints),
                "exit_condition": "Impacted endpoints have suppression, qualification, or owner-approved reuse rules.",
            },
        ]

    def _current_state(self, checkpoints: list[dict[str, Any]]) -> str:
        for checkpoint in checkpoints:
            if checkpoint["status"] in {"blocked", "review"}:
                return str(checkpoint["state"])
        return "ready_for_reuse"

    def _transitions(self, checkpoints: list[dict[str, Any]], summary: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "from_state": checkpoints[index]["state"],
                "to_state": checkpoints[index + 1]["state"],
                "condition": checkpoints[index]["exit_condition"],
                "decision": "hold" if checkpoints[index + 1]["status"] == "blocked" else "continue",
            }
            for index in range(len(checkpoints) - 1)
        ] + [
            {
                "from_state": checkpoints[-1]["state"],
                "to_state": self._current_state(checkpoints),
                "condition": "Endpoint impact and owner queues are synchronized.",
                "decision": summary["status"],
            }
        ]

    def _governance_policy(self) -> dict[str, Any]:
        return {
            "policy_id": "local-freshness-sla-ledger-v1",
            "enforcement_mode": "owner_sla_and_endpoint_gate",
            "breach_rules": [
                "Expired sources create a breached SLA item and block impacted generation endpoints.",
                "Unsupported absolute claims require source owner or security/legal approval before reuse.",
                "Missing renewal metadata stays in policy_gap until owner cadence is recorded.",
            ],
            "response_sla_hours": {"critical": 8, "high": 24, "medium": 72, "breached": 4},
            "artifact_retention": "Generated Markdown and JSON live under ignored storage/freshness_sla/.",
        }

    def _pack_payload(
        self,
        trace_id: str,
        sla: EvidenceFreshnessSlaResponse,
        freshness: EvidenceFreshnessResponse,
    ) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Evidence Freshness SLA Ledger Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "summary": sla.summary,
            "ledger_items": [item.model_dump(mode="json") for item in sla.ledger_items],
            "owner_rollups": sla.owner_rollups,
            "endpoint_impact": sla.endpoint_impact,
            "role_crew_queue": sla.role_crew_queue,
            "checkpoints": sla.checkpoints,
            "transitions": sla.transitions,
            "governance_policy": sla.governance_policy,
            "source_freshness_summary": freshness.summary,
            "local_proof_commands": sla.local_proof_commands,
            "limitations": sla.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        summary = pack["summary"]
        lines = [
            "# Evidence Freshness SLA Ledger Pack",
            "",
            "## Summary",
            "",
            f"- Status: {summary['status']}",
            f"- SLA items: {summary['sla_item_count']}",
            f"- Breached: {summary['breached_count']}",
            f"- Critical: {summary['critical_count']}",
            f"- Blocked endpoints: {summary['blocked_endpoint_count']}",
            "",
            "## SLA Ledger",
            "",
            "| Source | Owner | Escalation | Severity | SLA | State | SLA Hours | Action |",
            "| --- | --- | --- | --- | --- | --- | ---: | --- |",
        ]
        for item in pack["ledger_items"]:
            lines.append(
                f"| {self._md(item['filename'])} | {self._md(item['policy_owner'])} | "
                f"{self._md(item['escalation_owner'])} | {self._md(item['severity'])} | "
                f"{self._md(item['sla_status'])} | {self._md(item['workflow_state'])} | "
                f"{self._md(item['response_sla_hours'])} | {self._md(item['required_action'])} |"
            )
        lines.extend(["", "## Owner Rollups", ""])
        for item in pack["owner_rollups"]:
            lines.append(
                f"- {item['owner']} -> {item['escalation_owner']}: {item['item_count']} items, "
                f"{item['blocked_endpoint_count']} blocked endpoints. {item['next_action']}"
            )
        lines.extend(["", "## Endpoint Impact", ""])
        if pack["endpoint_impact"]:
            for item in pack["endpoint_impact"]:
                lines.append(
                    f"- {item['endpoint']}: {item['blocked_source_count']} blocked sources "
                    f"owned by {', '.join(item['owners'])}."
                )
        else:
            lines.append("- No endpoints are blocked by breached freshness SLA items.")
        lines.extend(["", "## State Machine", ""])
        lines.append("| Seq | State | Status | Owner | Items | Exit condition |")
        lines.append("| ---: | --- | --- | --- | ---: | --- |")
        for checkpoint in pack["checkpoints"]:
            lines.append(
                f"| {self._md(checkpoint['sequence'])} | {self._md(checkpoint['state'])} | "
                f"{self._md(checkpoint['status'])} | {self._md(checkpoint['owner_role'])} | "
                f"{self._md(checkpoint['item_count'])} | {self._md(checkpoint['exit_condition'])} |"
            )
        lines.extend(["", "## Role Crew Queue", ""])
        for item in pack["role_crew_queue"]:
            lines.append(
                f"- {item['role']} led by {item['crew_lead']} runs {item['process_mode']} "
                f"for {len(item['assigned_items'])} assigned items."
            )
        lines.extend(["", "## Governance Policy", ""])
        policy = pack["governance_policy"]
        lines.append(f"- Policy ID: {policy['policy_id']}")
        lines.append(f"- Enforcement mode: {policy['enforcement_mode']}")
        self._append_list(lines, "Breach rules", policy["breach_rules"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Artifact Paths", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines) + "\n"

    def _owner_next_action(self, items: list[EvidenceFreshnessSlaItem]) -> str:
        if any(item.sla_status == "breached" for item in items):
            return "Renew or replace breached evidence before customer-facing reuse."
        if any(item.sla_status == "claim_review_required" for item in items):
            return "Approve qualified language and attach owner rationale."
        if any(item.sla_status == "policy_gap" for item in items):
            return "Backfill renewal metadata and next review cadence."
        return "Confirm renewal watch date and reviewer accountability."

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/evidence/freshness-sla" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/evidence/freshness-sla-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m pytest -q",
            "python -m ruff check .",
            (
                'rg "freshness-sla|Evidence Freshness SLA|freshness_sla|owner SLA" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\freshness_sla -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "SLA timers are deterministic local severity windows, not connected to Jira, ServiceNow, Slack, or email.",
            (
                "Owner and escalation routing is role-based fixture logic and should be mapped to real directories "
                "in production."
            ),
            (
                "Endpoint blocking guidance is a governance preview; the local app does not mutate retrieval "
                "indexes automatically."
            ),
            "The ledger should be regenerated per RFP submission cycle because renewal status depends on runtime date.",
        ]

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "source"

    def _severity_rank(self, severity: str) -> int:
        return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(severity, 4)

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()

    def _append_list(self, lines: list[str], title: str, items: list[str]) -> None:
        lines.append(f"- {title}:")
        lines.extend(f"  - {item}" for item in items)
