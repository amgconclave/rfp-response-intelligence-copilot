from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    BuyerIntelligenceWorkflowResponse,
    BuyerStructuredContractResponse,
    BuyerWorkflowReplayResponse,
    ProposalAgentCouncilResponse,
    ProposalCertificationGate,
    ProposalCertificationTransition,
    ProposalDecisionProvenanceResponse,
    ProposalSubmissionCertificationPackResponse,
    ProposalSubmissionCertificationResponse,
)


class ProposalSubmissionCertificationService:
    def __init__(self, settings: Settings, readiness_floor: int = 90) -> None:
        self.settings = settings
        self.readiness_floor = readiness_floor

    def certify(
        self,
        trace_id: str,
        workflow: BuyerIntelligenceWorkflowResponse,
        replay: BuyerWorkflowReplayResponse,
        council: ProposalAgentCouncilResponse,
        provenance: ProposalDecisionProvenanceResponse,
        contract_audit: BuyerStructuredContractResponse,
    ) -> ProposalSubmissionCertificationResponse:
        gates = self._gates(workflow, replay, council, provenance, contract_audit)
        transitions = self._transitions(trace_id, gates)
        reviewer_queue = self._reviewer_queue(gates, workflow, council)
        status = self._status(gates)
        readiness_score = self._readiness_score(gates, contract_audit)
        return ProposalSubmissionCertificationResponse(
            title="Proposal Submission Certification Gate",
            certification_id=f"proposal-certification-{self._slug(trace_id)}",
            status=status,
            generated_at=datetime.now(UTC).isoformat(),
            recommendation=self._recommendation(status, reviewer_queue),
            readiness_score=readiness_score,
            injected_dependencies=self._injected_dependencies(contract_audit),
            source_artifacts=self._source_artifacts(workflow, replay, council, provenance, contract_audit),
            gates=gates,
            transitions=transitions,
            reviewer_queue=reviewer_queue,
            eval_assertions=self._eval_assertions(
                workflow,
                replay,
                council,
                provenance,
                contract_audit,
                gates,
                transitions,
            ),
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        certification: ProposalSubmissionCertificationResponse,
        write_artifact: bool = True,
    ) -> ProposalSubmissionCertificationPackResponse:
        pack = self._pack_payload(trace_id, certification)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "submission_certifications"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = self._slug(trace_id)
            markdown_path = pack_dir / f"proposal_submission_certification_{safe_trace_id}.md"
            json_path = pack_dir / f"proposal_submission_certification_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["submission_certification_markdown"] = artifact_path
            pack["artifact_paths"]["submission_certification_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return ProposalSubmissionCertificationPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            certification=certification,
            trace_id=trace_id,
        )

    def _gates(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        replay: BuyerWorkflowReplayResponse,
        council: ProposalAgentCouncilResponse,
        provenance: ProposalDecisionProvenanceResponse,
        contract_audit: BuyerStructuredContractResponse,
    ) -> list[ProposalCertificationGate]:
        open_handoffs = council.decision_summary.get("open_handoffs", 0)
        source_gate = self._workflow_gate_status(workflow, "gate-source-trust")
        model_gate = self._workflow_gate_status(workflow, "gate-model-risk")
        procurement_gate = self._workflow_gate_status(workflow, "gate-procurement-risk")
        external_required = bool(contract_audit.injected_dependencies.get("external_provider_required"))
        return [
            self._gate(
                "gate-structured-output-contracts",
                "Structured output contract stability",
                "pass" if contract_audit.status == "pass" and contract_audit.score >= self.readiness_floor else "fail",
                "Platform Owner",
                "critical",
                f"{contract_audit.status} with score {contract_audit.score}.",
                "Fix failing schema, role, or eval contract checks.",
                ["/proposal/buyer-contracts"],
            ),
            self._gate(
                "gate-checkpoint-replay",
                "Checkpoint replay validation",
                "pass" if replay.status == "pass" and replay.checkpoint_validation.get("status") == "pass" else "fail",
                "Platform Owner",
                "critical",
                f"{replay.transition_count} transition(s), checkpoint={replay.checkpoint_validation.get('status')}.",
                "Repair transition order, checkpoint keys, or trace refs before certification.",
                ["/proposal/buyer-intelligence-replay"],
            ),
            self._gate(
                "gate-human-approval-queue",
                "Human approval queue clearance",
                "needs_review" if workflow.human_approval_queue else "pass",
                "Proposal Manager",
                "high",
                f"{len(workflow.human_approval_queue)} approval item(s).",
                "Clear named reviewer approvals or certify with explicit exceptions.",
                ["/proposal/buyer-intelligence", "/rfp/reviewer-collaboration-pack"],
            ),
            self._gate(
                "gate-agent-handoffs",
                "Role council handoff closure",
                "needs_review" if open_handoffs or council.status != "ready_for_executive_review" else "pass",
                "Proposal Manager",
                "high",
                f"Council status={council.status}; open handoffs={open_handoffs}.",
                "Close cross-functional handoffs before final response submission.",
                ["/proposal/agent-council"],
            ),
            self._gate(
                "gate-provenance-integrity",
                "Decision provenance integrity",
                "pass" if all(item.get("passed") for item in provenance.eval_assertions) else "fail",
                "AI Governance Reviewer",
                "critical",
                f"{provenance.summary.get('node_count')} node(s), {provenance.summary.get('edge_count')} edge(s).",
                "Resolve provenance eval failures and missing decision edges.",
                ["/proposal/decision-provenance"],
            ),
            self._gate(
                "gate-source-trust-policy",
                "Source trust policy",
                source_gate,
                "Knowledge Owner",
                "high",
                self._workflow_gate_evidence(workflow, "gate-source-trust"),
                "Resolve blocked or restricted evidence before citation reuse.",
                ["/evidence/source-trust"],
            ),
            self._gate(
                "gate-model-risk-policy",
                "Model risk policy",
                model_gate,
                "AI Governance Reviewer",
                "high",
                self._workflow_gate_evidence(workflow, "gate-model-risk"),
                "Review model/provider risks before provider or final-language changes.",
                ["/governance/model-risk-register"],
            ),
            self._gate(
                "gate-procurement-policy",
                "Procurement and commercial approval policy",
                procurement_gate,
                "Procurement Lead",
                "high",
                self._workflow_gate_evidence(workflow, "gate-procurement-risk"),
                "Resolve buyer Q&A, pricing, legal, or commercial approvals.",
                ["/procurement/question-risk", "/procurement/risk-desk"],
            ),
            self._gate(
                "gate-provider-optionality",
                "Local provider optionality",
                "pass" if self.settings.provider_mode == "mock" and not external_required else "needs_review",
                "Platform Owner",
                "medium",
                f"provider_mode={self.settings.provider_mode}; external_provider_required={external_required}.",
                "Keep mock mode for local certification unless cloud provider review is explicit.",
                ["/ops/cost-governance"],
            ),
        ]

    def _gate(
        self,
        gate_id: str,
        name: str,
        status: str,
        owner_role: str,
        severity: str,
        evidence: str,
        required_action: str,
        endpoint_refs: list[str],
    ) -> ProposalCertificationGate:
        return ProposalCertificationGate(
            gate_id=gate_id,
            name=name,
            status=status,
            owner_role=owner_role,
            severity=severity,
            evidence=evidence,
            required_action=required_action,
            endpoint_refs=endpoint_refs,
        )

    def _transitions(
        self,
        trace_id: str,
        gates: list[ProposalCertificationGate],
    ) -> list[ProposalCertificationTransition]:
        states = [
            ("snapshot_loaded", "validate_contracts", ["gate-structured-output-contracts"]),
            ("validate_contracts", "validate_replay", ["gate-checkpoint-replay"]),
            (
                "validate_replay",
                "route_human_reviews",
                ["gate-human-approval-queue", "gate-agent-handoffs"],
            ),
            (
                "route_human_reviews",
                "validate_governance",
                ["gate-provenance-integrity", "gate-source-trust-policy", "gate-model-risk-policy"],
            ),
            (
                "validate_governance",
                "certification_decision",
                ["gate-procurement-policy", "gate-provider-optionality"],
            ),
        ]
        gate_by_id = {gate.gate_id: gate for gate in gates}
        transitions: list[ProposalCertificationTransition] = []
        prior: str | None = None
        for sequence, (from_state, to_state, gate_refs) in enumerate(states, start=1):
            blocking = [
                gate_by_id[gate_id]
                for gate_id in gate_refs
                if gate_by_id[gate_id].status in {"fail", "blocked"}
            ]
            review = [
                gate_by_id[gate_id]
                for gate_id in gate_refs
                if gate_by_id[gate_id].status in {"needs_review", "warn"}
            ]
            if blocking:
                decision = "block"
                condition = "blocking gate detected: " + ", ".join(gate.gate_id for gate in blocking)
            elif review:
                decision = "route_to_reviewer_queue"
                condition = "review gate detected: " + ", ".join(gate.gate_id for gate in review)
            else:
                decision = "continue"
                condition = "all scoped gates pass"
            transitions.append(
                ProposalCertificationTransition(
                    transition_id=f"cert-transition-{sequence:02d}-{self._slug(to_state)}",
                    sequence=sequence,
                    from_state=prior or from_state,
                    to_state=to_state,
                    condition=condition,
                    decision=decision,
                    checkpoint_key=f"{self._slug(trace_id)}:{sequence:02d}:{self._slug(to_state)}",
                    gate_refs=gate_refs,
                )
            )
            prior = to_state
        return transitions

    def _reviewer_queue(
        self,
        gates: list[ProposalCertificationGate],
        workflow: BuyerIntelligenceWorkflowResponse,
        council: ProposalAgentCouncilResponse,
    ) -> list[dict[str, Any]]:
        rows = [
            {
                "queue_id": f"cert-review-{self._slug(gate.gate_id)}",
                "owner_role": gate.owner_role,
                "priority": gate.severity,
                "status": gate.status,
                "decision_area": gate.name,
                "required_action": gate.required_action,
                "evidence": gate.evidence,
                "endpoint_refs": gate.endpoint_refs,
            }
            for gate in gates
            if gate.status in {"needs_review", "warn", "fail", "blocked"}
        ]
        rows.extend(
            {
                "queue_id": f"workflow-{item.approval_id}",
                "owner_role": item.reviewer_role,
                "priority": item.priority,
                "status": item.status,
                "decision_area": item.decision_area,
                "required_action": item.required_before,
                "evidence": item.reason,
                "endpoint_refs": ["/proposal/buyer-intelligence"],
            }
            for item in workflow.human_approval_queue[:6]
        )
        rows.extend(
            {
                "queue_id": f"council-{item.handoff_id}",
                "owner_role": item.to_agent_id,
                "priority": "high",
                "status": item.status,
                "decision_area": "Agent council handoff",
                "required_action": item.required_before,
                "evidence": item.reason,
                "endpoint_refs": ["/proposal/agent-council"],
            }
            for item in council.handoffs[:6]
            if item.status == "open"
        )
        return rows

    def _status(self, gates: list[ProposalCertificationGate]) -> str:
        if any(gate.status in {"fail", "blocked"} for gate in gates):
            return "blocked"
        if any(gate.status in {"needs_review", "warn"} for gate in gates):
            return "certified_with_exceptions"
        return "certified"

    def _readiness_score(
        self,
        gates: list[ProposalCertificationGate],
        contract_audit: BuyerStructuredContractResponse,
    ) -> int:
        penalties = {"fail": 25, "blocked": 25, "needs_review": 7, "warn": 5, "pass": 0}
        score = min(100, contract_audit.score)
        for gate in gates:
            score -= penalties.get(gate.status, 4)
        return max(0, score)

    def _recommendation(self, status: str, reviewer_queue: list[dict[str, Any]]) -> str:
        if status == "blocked":
            return "do_not_submit_until_blocking_certification_gates_pass"
        if reviewer_queue:
            return "submit_only_with_named_exception_approvals_and_attached_certification_pack"
        return "ready_for_submission_with_certification_attached"

    def _injected_dependencies(self, contract_audit: BuyerStructuredContractResponse) -> dict[str, Any]:
        return {
            "service": "ProposalSubmissionCertificationService",
            "settings_provider_mode": self.settings.provider_mode,
            "settings_vector_store_mode": self.settings.vector_store_mode,
            "readiness_floor": self.readiness_floor,
            "contract_service": contract_audit.injected_dependencies.get("service"),
            "external_provider_required": False,
        }

    def _source_artifacts(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        replay: BuyerWorkflowReplayResponse,
        council: ProposalAgentCouncilResponse,
        provenance: ProposalDecisionProvenanceResponse,
        contract_audit: BuyerStructuredContractResponse,
    ) -> dict[str, Any]:
        return {
            "workflow_id": workflow.workflow_id,
            "workflow_status": workflow.workflow_status,
            "replay_status": replay.status,
            "replay_transition_count": replay.transition_count,
            "council_id": council.council_id,
            "council_status": council.status,
            "provenance_id": provenance.provenance_id,
            "provenance_status": provenance.status,
            "contract_version": contract_audit.contract_version,
            "contract_status": contract_audit.status,
            "contract_score": contract_audit.score,
        }

    def _eval_assertions(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        replay: BuyerWorkflowReplayResponse,
        council: ProposalAgentCouncilResponse,
        provenance: ProposalDecisionProvenanceResponse,
        contract_audit: BuyerStructuredContractResponse,
        gates: list[ProposalCertificationGate],
        transitions: list[ProposalCertificationTransition],
    ) -> list[dict[str, Any]]:
        gate_statuses = Counter(gate.status for gate in gates)
        return [
            {
                "assertion_id": "certification-source-artifacts-linked",
                "assertion": "workflow, replay, council, provenance, and contract audit source IDs are present",
                "expected": 5,
                "observed": sum(
                    bool(value)
                    for value in [
                        workflow.workflow_id,
                        replay.workflow_id,
                        council.council_id,
                        provenance.provenance_id,
                        contract_audit.contract_version,
                    ]
                ),
                "passed": all(
                    [
                        workflow.workflow_id,
                        replay.workflow_id,
                        council.council_id,
                        provenance.provenance_id,
                        contract_audit.contract_version,
                    ]
                ),
            },
            {
                "assertion_id": "certification-transitions-checkpointed",
                "assertion": "every certification transition has a local checkpoint key",
                "expected": len(transitions),
                "observed": sum(1 for transition in transitions if transition.checkpoint_key),
                "passed": all(transition.checkpoint_key for transition in transitions),
            },
            {
                "assertion_id": "certification-review-routing",
                "assertion": "non-pass certification gates route to block or reviewer decisions",
                "expected": dict(sorted(gate_statuses.items())),
                "observed": [transition.decision for transition in transitions],
                "passed": all(
                    gate.status == "pass"
                    or any(
                        gate.gate_id in transition.gate_refs and transition.decision != "continue"
                        for transition in transitions
                    )
                    for gate in gates
                ),
            },
            {
                "assertion_id": "certification-contracts-pass-through",
                "assertion": "buyer structured contract audit passes before certification can be used",
                "expected": "pass",
                "observed": contract_audit.status,
                "passed": contract_audit.status == "pass",
            },
            {
                "assertion_id": "certification-external-provider-optional",
                "assertion": "local certification does not require OpenAI, Azure OpenAI, CRM, GRC, or procurement APIs",
                "expected": False,
                "observed": self.settings.provider_mode != "mock",
                "passed": self.settings.provider_mode == "mock",
            },
        ]

    def _workflow_gate_status(self, workflow: BuyerIntelligenceWorkflowResponse, gate_id: str) -> str:
        gate = next((item for item in workflow.governance_gates if item.gate_id == gate_id), None)
        if gate is None:
            return "fail"
        if gate.status == "blocked":
            return "blocked"
        if gate.status in {"needs_review", "warn"}:
            return "needs_review"
        return "pass"

    def _workflow_gate_evidence(self, workflow: BuyerIntelligenceWorkflowResponse, gate_id: str) -> str:
        gate = next((item for item in workflow.governance_gates if item.gate_id == gate_id), None)
        if gate is None:
            return f"{gate_id} missing from workflow governance gates."
        return gate.evidence

    def _pack_payload(
        self,
        trace_id: str,
        certification: ProposalSubmissionCertificationResponse,
    ) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Proposal Submission Certification Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "certification": certification.model_dump(mode="json"),
            "reviewer_controls": [
                "Attach this pack to final proposal review before customer submission.",
                "Treat blocked gates as hard stops and needs_review gates as named exception approvals.",
                "Verify all transition checkpoint keys are present after workflow, council, or policy changes.",
                "Keep PROVIDER_MODE=mock for local certification unless cloud provider approval is explicit.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        certification = pack["certification"]
        lines = [
            "# Proposal Submission Certification Pack",
            "",
            "## Summary",
            "",
            f"- Status: {certification['status']}",
            f"- Recommendation: {certification['recommendation']}",
            f"- Readiness score: {certification['readiness_score']}",
            f"- Provider mode: {certification['injected_dependencies']['settings_provider_mode']}",
            "",
            "## Certification Gates",
            "",
            "| Gate | Owner | Status | Severity | Required action |",
            "| --- | --- | --- | --- | --- |",
        ]
        for gate in certification["gates"]:
            lines.append(
                f"| {self._md(gate['name'])} | {self._md(gate['owner_role'])} | {gate['status']} | "
                f"{gate['severity']} | {self._md(gate['required_action'])} |"
            )
        lines.extend(["", "## State Transitions", ""])
        lines.append("| Seq | From | To | Decision | Checkpoint |")
        lines.append("| ---: | --- | --- | --- | --- |")
        for transition in certification["transitions"]:
            lines.append(
                f"| {transition['sequence']} | {self._md(transition['from_state'] or 'START')} | "
                f"{self._md(transition['to_state'])} | {self._md(transition['decision'])} | "
                f"`{self._md(transition['checkpoint_key'])}` |"
            )
        lines.extend(["", "## Reviewer Queue", ""])
        if certification["reviewer_queue"]:
            for item in certification["reviewer_queue"]:
                lines.append(
                    f"- {self._md(item['owner_role'])} ({item['priority']}/{item['status']}): "
                    f"{self._md(item['required_action'])}"
                )
        else:
            lines.append("- No reviewer queue items are open.")
        lines.extend(["", "## Eval Assertions", ""])
        for assertion in certification["eval_assertions"]:
            result = "pass" if assertion["passed"] else "fail"
            lines.append(f"- {assertion['assertion_id']} ({result}): {self._md(assertion['assertion'])}")
        lines.extend(["", "## Reviewer Controls", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_controls"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in certification["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {self._md(item)}" for item in certification["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Generated Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {"method": "GET", "path": "/proposal/submission-certification", "purpose": "View certification gate."},
            {
                "method": "POST",
                "path": "/proposal/submission-certification-pack",
                "purpose": "Write certification artifacts.",
            },
            {"method": "GET", "path": "/proposal/buyer-contracts", "purpose": "Source contract audit."},
            {"method": "GET", "path": "/proposal/decision-provenance", "purpose": "Source decision graph."},
            {"method": "GET", "path": "/proposal/agent-council", "purpose": "Source role council."},
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/proposal/submission-certification" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/proposal/submission-certification-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'rg "proposal/submission-certification|Proposal Submission Certification|'
                'submission_certifications" app dashboard docs README.md tests Makefile'
            ),
            (
                "Get-ChildItem -Recurse -File storage\\submission_certifications "
                "-ErrorAction SilentlyContinue | Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Certification is deterministic local governance logic, not a legally binding signature workflow.",
            "Human approvals are modeled from local queues and must be reconciled with real review systems.",
            "The service validates generated control artifacts and does not submit proposals or call external APIs.",
            "OpenAI, Azure OpenAI, CRM, GRC, procurement, and e-signature systems remain optional.",
        ]

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower() or "local"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
