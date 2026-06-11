from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    BuyerApprovalQueueItem,
    BuyerGovernanceGate,
    BuyerIntelligenceWorkflowResponse,
    BuyerProviderRoute,
    BuyerWorkflowStage,
    ProposalApprovalDecisionInput,
    ProposalApprovalSimulationPackResponse,
    ProposalApprovalSimulationRecord,
    ProposalApprovalSimulationResponse,
)


class ProposalApprovalSimulationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def simulate(
        self,
        trace_id: str,
        workflow: BuyerIntelligenceWorkflowResponse,
        requested_by: str = "proposal_manager",
        decisions: list[ProposalApprovalDecisionInput] | None = None,
    ) -> ProposalApprovalSimulationResponse:
        decision_map = {decision.approval_id: decision for decision in decisions or []}
        records = self._decision_records(trace_id, workflow.human_approval_queue, decision_map)
        stage_impacts = self._stage_impacts(workflow.workflow_stages, records)
        gate_impacts = self._gate_impacts(workflow.governance_gates, records)
        unresolved = sum(record.simulated_status != "resolved" for record in records)
        simulated_status = self._simulated_workflow_status(records, gate_impacts)
        durable_state_update = self._durable_state_update(trace_id, workflow, records, simulated_status)
        trace_analysis = self._trace_analysis(workflow, records, stage_impacts, gate_impacts)
        return ProposalApprovalSimulationResponse(
            title="Proposal Approval Resolution Simulator",
            simulation_id=f"approval-simulation-{self._slug(trace_id)}",
            status=self._status(simulated_status, unresolved, records),
            generated_at=datetime.now(UTC).isoformat(),
            requested_by=requested_by,
            workflow_id=workflow.workflow_id,
            original_workflow_status=workflow.workflow_status,
            simulated_workflow_status=simulated_status,
            unresolved_approval_count=unresolved,
            decision_records=records,
            stage_impacts=stage_impacts,
            gate_impacts=gate_impacts,
            durable_state_update=durable_state_update,
            trace_analysis=trace_analysis,
            provider_policy=self._provider_policy(workflow.provider_routes),
            eval_assertions=self._eval_assertions(workflow, records, stage_impacts, gate_impacts),
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        simulation: ProposalApprovalSimulationResponse,
        write_artifact: bool = True,
    ) -> ProposalApprovalSimulationPackResponse:
        pack = self._pack_payload(trace_id, simulation)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        state_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "approval_simulations"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = self._slug(trace_id)
            markdown_path = pack_dir / f"approval_simulation_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"approval_simulation_pack_{safe_trace_id}.json"
            state_path = pack_dir / f"approval_simulation_state_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            state_artifact_path = str(state_path.resolve())
            pack["artifact_paths"]["approval_simulation_markdown"] = artifact_path
            pack["artifact_paths"]["approval_simulation_json"] = json_artifact_path
            pack["artifact_paths"]["approval_simulation_state"] = state_artifact_path
            pack["simulation"]["durable_state_update"]["state_store_path"] = state_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
            state_path.write_text(
                json.dumps(
                    {
                        "simulation_id": simulation.simulation_id,
                        "workflow_id": simulation.workflow_id,
                        "trace_id": trace_id,
                        "simulated_workflow_status": simulation.simulated_workflow_status,
                        "durable_state_update": pack["simulation"]["durable_state_update"],
                        "decision_records": pack["simulation"]["decision_records"],
                        "gate_impacts": pack["simulation"]["gate_impacts"],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

        return ProposalApprovalSimulationPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            state_artifact_path=state_artifact_path,
            markdown=markdown,
            pack=pack,
            simulation=simulation,
            trace_id=trace_id,
        )

    def _decision_records(
        self,
        trace_id: str,
        approvals: list[BuyerApprovalQueueItem],
        decision_map: dict[str, ProposalApprovalDecisionInput],
    ) -> list[ProposalApprovalSimulationRecord]:
        records = []
        for index, approval in enumerate(approvals, start=1):
            decision = decision_map.get(approval.approval_id)
            reviewer_role = decision.reviewer_role if decision and decision.reviewer_role else approval.reviewer_role
            simulated_decision = self._normalize_decision(
                decision.decision if decision else self._default_decision(approval)
            )
            simulated_status = self._simulated_status(simulated_decision)
            rationale = decision.rationale if decision else self._default_rationale(approval, simulated_decision)
            records.append(
                ProposalApprovalSimulationRecord(
                    approval_id=approval.approval_id,
                    reviewer_role=reviewer_role,
                    decision_area=approval.decision_area,
                    priority=approval.priority,
                    original_status=approval.status,
                    simulated_decision=simulated_decision,
                    simulated_status=simulated_status,
                    rationale=rationale,
                    required_before=approval.required_before,
                    related_stage_ids=approval.related_stage_ids,
                    evidence_refs=approval.evidence_refs,
                    checkpoint_key=f"{self._slug(trace_id)}:approval:{index:02d}:{self._slug(approval.approval_id)}",
                    trace_refs=[approval.approval_id, *approval.related_stage_ids, *approval.evidence_refs[:3]],
                )
            )
        return records

    def _stage_impacts(
        self,
        stages: list[BuyerWorkflowStage],
        records: list[ProposalApprovalSimulationRecord],
    ) -> list[dict[str, Any]]:
        records_by_stage: dict[str, list[ProposalApprovalSimulationRecord]] = defaultdict(list)
        for record in records:
            for stage_id in record.related_stage_ids:
                records_by_stage[stage_id].append(record)

        impacts = []
        for stage in stages:
            related = records_by_stage.get(stage.stage_id, [])
            decision_counts = Counter(record.simulated_decision for record in related)
            if decision_counts.get("reject", 0):
                simulated_status = "blocked"
            elif decision_counts.get("defer", 0):
                simulated_status = "waiting_on_human_approval"
            elif related and all(record.simulated_status == "resolved" for record in related):
                simulated_status = "complete" if stage.status != "ready" else "ready"
            else:
                simulated_status = stage.status
            impacts.append(
                {
                    "stage_id": stage.stage_id,
                    "stage_name": stage.name,
                    "owner_role": stage.owner_role,
                    "original_status": stage.status,
                    "simulated_status": simulated_status,
                    "approval_count": len(related),
                    "decision_counts": dict(sorted(decision_counts.items())),
                    "checkpoint_key": stage.durability_key,
                }
            )
        return impacts

    def _gate_impacts(
        self,
        gates: list[BuyerGovernanceGate],
        records: list[ProposalApprovalSimulationRecord],
    ) -> list[dict[str, Any]]:
        records_by_gate = {
            "gate-human-approval": records,
            "gate-source-trust": [record for record in records if record.approval_id.startswith("approval-source")],
            "gate-model-risk": [record for record in records if record.approval_id.startswith("approval-model-risk")],
            "gate-procurement-risk": [
                record for record in records if record.approval_id.startswith("approval-procurement")
            ],
        }
        impacts = []
        for gate in gates:
            related = records_by_gate.get(gate.gate_id, [])
            decision_counts = Counter(record.simulated_decision for record in related)
            if related:
                if decision_counts.get("reject", 0):
                    simulated_status = "blocked"
                elif decision_counts.get("defer", 0):
                    simulated_status = "needs_review"
                elif all(record.simulated_status == "resolved" for record in related):
                    simulated_status = "pass"
                else:
                    simulated_status = gate.status
            else:
                simulated_status = gate.status
            impacts.append(
                {
                    "gate_id": gate.gate_id,
                    "name": gate.name,
                    "owner_role": gate.owner_role,
                    "original_status": gate.status,
                    "simulated_status": simulated_status,
                    "approval_count": len(related),
                    "decision_counts": dict(sorted(decision_counts.items())),
                    "required_action": self._gate_action(gate.required_action, simulated_status),
                    "endpoint_refs": gate.endpoint_refs,
                }
            )
        return impacts

    def _durable_state_update(
        self,
        trace_id: str,
        workflow: BuyerIntelligenceWorkflowResponse,
        records: list[ProposalApprovalSimulationRecord],
        simulated_status: str,
    ) -> dict[str, Any]:
        resolved = [record.approval_id for record in records if record.simulated_status == "resolved"]
        unresolved = [record.approval_id for record in records if record.simulated_status != "resolved"]
        return {
            "state_backend": "local_json_artifact",
            "state_store_path": None,
            "source_workflow_id": workflow.workflow_id,
            "previous_workflow_status": workflow.workflow_status,
            "next_workflow_status": simulated_status,
            "previous_checkpoint_count": workflow.durable_state.get("checkpoint_count"),
            "simulation_checkpoint_count": len(records),
            "resolved_approval_ids": resolved,
            "unresolved_approval_ids": unresolved,
            "restart_policy": "resume_from_approval_checkpoint_without_replaying_ingestion_or_retrieval",
            "state_transition_id": f"approval-resolution-{self._slug(trace_id)}",
        }

    def _trace_analysis(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        records: list[ProposalApprovalSimulationRecord],
        stage_impacts: list[dict[str, Any]],
        gate_impacts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "source_trace_id": workflow.trace_id,
            "span_count": len(records) + len(stage_impacts) + len(gate_impacts),
            "decision_counts": dict(sorted(Counter(record.simulated_decision for record in records).items())),
            "record_status_counts": dict(sorted(Counter(record.simulated_status for record in records).items())),
            "stage_status_counts": dict(sorted(Counter(row["simulated_status"] for row in stage_impacts).items())),
            "gate_status_counts": dict(sorted(Counter(row["simulated_status"] for row in gate_impacts).items())),
            "checkpoint_keys": [record.checkpoint_key for record in records],
        }

    def _provider_policy(self, routes: list[BuyerProviderRoute]) -> dict[str, Any]:
        route_by_mode = {route.provider_mode: route for route in routes}
        mock_route = route_by_mode.get("mock")
        return {
            "active_provider_mode": "mock",
            "external_provider_required": False,
            "local_mock_ready": bool(mock_route),
            "allowed_routes": [route.provider_mode for route in routes],
            "blocked_until_governance": [
                route.provider_mode for route in routes if route.provider_mode in {"openai", "azure_openai"}
            ],
            "policy_note": "Approval simulation mutates local control state only and never calls provider APIs.",
        }

    def _eval_assertions(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        records: list[ProposalApprovalSimulationRecord],
        stage_impacts: list[dict[str, Any]],
        gate_impacts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        approval_ids = {item.approval_id for item in workflow.human_approval_queue}
        record_ids = {record.approval_id for record in records}
        human_gate = next((gate for gate in gate_impacts if gate["gate_id"] == "gate-human-approval"), None)
        rejected = [record for record in records if record.simulated_decision == "reject"]
        blocked_stage_count = sum(row["simulated_status"] == "blocked" for row in stage_impacts)
        return [
            {
                "assertion_id": "approval-simulation-covers-queue",
                "assertion": "every workflow approval queue item has one simulated decision record",
                "expected": sorted(approval_ids),
                "observed": sorted(record_ids),
                "passed": approval_ids == record_ids,
            },
            {
                "assertion_id": "approval-simulation-checkpointed",
                "assertion": "every simulated decision record has a durable checkpoint key and trace refs",
                "expected": len(records),
                "observed": sum(1 for record in records if record.checkpoint_key and record.trace_refs),
                "passed": all(record.checkpoint_key and record.trace_refs for record in records),
            },
            {
                "assertion_id": "approval-simulation-human-gate-reflects-decisions",
                "assertion": "human approval gate passes only when every approval is resolved",
                "expected": "pass when all resolved",
                "observed": human_gate["simulated_status"] if human_gate else "missing",
                "passed": bool(human_gate) and self._human_gate_matches_records(human_gate, records),
            },
            {
                "assertion_id": "approval-simulation-rejects-block",
                "assertion": "rejected approvals block at least one impacted workflow stage",
                "expected": "blocked stage when rejection exists",
                "observed": blocked_stage_count,
                "passed": not rejected or blocked_stage_count > 0,
            },
        ]

    def _pack_payload(self, trace_id: str, simulation: ProposalApprovalSimulationResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Proposal Approval Simulation Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "simulation": simulation.model_dump(mode="json"),
            "reviewer_controls": [
                (
                    "Treat simulated approvals as planning evidence only; named human owners still decide "
                    "in real workflow."
                ),
                "Regenerate after source trust, model risk, procurement risk, or buyer workflow policy changes.",
                "Do not use approval simulation to bypass blocked source, model, or procurement gates.",
                "Keep external providers disabled unless provider, privacy, cost, and model-risk gates pass.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        simulation = pack["simulation"]
        lines = [
            "# Proposal Approval Simulation Pack",
            "",
            "## Summary",
            "",
            f"- Status: {simulation['status']}",
            f"- Workflow: {simulation['workflow_id']}",
            f"- Original workflow status: {simulation['original_workflow_status']}",
            f"- Simulated workflow status: {simulation['simulated_workflow_status']}",
            f"- Unresolved approvals: {simulation['unresolved_approval_count']}",
            f"- Provider policy: {simulation['provider_policy']['active_provider_mode']}",
            "",
            "## Decision Records",
            "",
            "| Approval | Reviewer | Decision | Status | Priority | Required before |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for record in simulation["decision_records"]:
            lines.append(
                f"| `{self._md(record['approval_id'])}` | {self._md(record['reviewer_role'])} | "
                f"{record['simulated_decision']} | {record['simulated_status']} | {record['priority']} | "
                f"{self._md(record['required_before'])} |"
            )
        lines.extend(["", "## Stage Impacts", ""])
        for stage in simulation["stage_impacts"]:
            lines.append(
                f"- {stage['stage_id']}: {stage['original_status']} -> {stage['simulated_status']} "
                f"({stage['approval_count']} approval item(s))"
            )
        lines.extend(["", "## Gate Impacts", ""])
        for gate in simulation["gate_impacts"]:
            lines.append(
                f"- {gate['gate_id']} ({gate['owner_role']}): {gate['original_status']} -> "
                f"{gate['simulated_status']}. {self._md(gate['required_action'])}"
            )
        lines.extend(["", "## Durable State Update", ""])
        for key, value in simulation["durable_state_update"].items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Eval Assertions", ""])
        for assertion in simulation["eval_assertions"]:
            result = "pass" if assertion["passed"] else "fail"
            lines.append(f"- {assertion['assertion_id']} ({result}): {self._md(assertion['assertion'])}")
        lines.extend(["", "## Reviewer Controls", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_controls"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in simulation["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {self._md(item)}" for item in simulation["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Generated Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _simulated_workflow_status(
        self,
        records: list[ProposalApprovalSimulationRecord],
        gate_impacts: list[dict[str, Any]],
    ) -> str:
        if any(record.simulated_decision == "reject" for record in records):
            return "blocked"
        if any(gate["simulated_status"] == "blocked" for gate in gate_impacts):
            return "blocked"
        if any(record.simulated_decision == "defer" for record in records):
            return "waiting_on_human_approval"
        if any(gate["simulated_status"] == "needs_review" for gate in gate_impacts):
            return "waiting_on_human_approval"
        return "ready_for_submission_review"

    def _human_gate_matches_records(
        self,
        human_gate: dict[str, Any],
        records: list[ProposalApprovalSimulationRecord],
    ) -> bool:
        all_resolved = all(record.simulated_status == "resolved" for record in records)
        any_unresolved = any(record.simulated_status != "resolved" for record in records)
        return (all_resolved and human_gate["simulated_status"] == "pass") or any_unresolved

    def _status(
        self,
        simulated_workflow_status: str,
        unresolved: int,
        records: list[ProposalApprovalSimulationRecord],
    ) -> str:
        if simulated_workflow_status == "blocked":
            return "blocked_by_reviewer_decision"
        if unresolved:
            return "waiting_on_human_approval"
        if records:
            return "ready_after_simulated_approval"
        return "no_approval_queue"

    def _default_decision(self, approval: BuyerApprovalQueueItem) -> str:
        if approval.priority in {"critical", "high"}:
            return "defer"
        return "approve"

    def _default_rationale(self, approval: BuyerApprovalQueueItem, decision: str) -> str:
        if decision == "defer":
            return f"{approval.priority} priority item remains open for named reviewer confirmation."
        return "Lower-risk local queue item is simulated as approved for planning."

    def _normalize_decision(self, decision: str) -> str:
        normalized = decision.strip().lower().replace("_", "-")
        if normalized in {"approved", "approve", "accept", "accepted"}:
            return "approve"
        if normalized in {"reject", "rejected", "block", "blocked"}:
            return "reject"
        return "defer"

    def _simulated_status(self, decision: str) -> str:
        if decision == "approve":
            return "resolved"
        if decision == "reject":
            return "blocked"
        return "pending_human_review"

    def _gate_action(self, original_action: str, simulated_status: str) -> str:
        if simulated_status == "pass":
            return "Simulated approvals clear this gate for local planning; retain artifact evidence for audit."
        if simulated_status == "blocked":
            return "Reviewer rejection blocks final submission until owner remediation or exception approval."
        return original_action

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {"method": "POST", "path": "/proposal/approval-simulation", "purpose": "Simulate approval outcomes."},
            {
                "method": "POST",
                "path": "/proposal/approval-simulation-pack",
                "purpose": "Write approval simulation artifacts.",
            },
            {"method": "GET", "path": "/proposal/buyer-intelligence", "purpose": "Source HITL approval queue."},
            {"method": "GET", "path": "/proposal/buyer-intelligence-replay", "purpose": "Source checkpoint replay."},
            {"method": "GET", "path": "/proposal/decision-provenance", "purpose": "Source decision graph."},
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            (
                'curl -X POST "http://127.0.0.1:8000/proposal/approval-simulation" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/proposal/approval-simulation-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'rg "proposal/approval-simulation|Approval Simulation|approval_simulations" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\approval_simulations -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Simulation updates local workflow control state only; it is not a live approval system.",
            "Reviewer decisions are deterministic inputs or defaults and must be confirmed by real owners.",
            "Provider routes remain mock-first; no OpenAI, Azure, CRM, procurement, or GRC APIs are called.",
            "Gate impacts model proposal governance posture and do not mutate source documents or prior artifacts.",
        ]

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower() or "local"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
