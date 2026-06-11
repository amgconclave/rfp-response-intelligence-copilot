from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    BuyerIntelligenceWorkflowResponse,
    BuyerWorkflowReplayResponse,
    CostGovernanceResponse,
    ModelRiskRegisterResponse,
    ProcurementQuestionRiskResponse,
    ProposalAgentCouncilResponse,
    ProposalDecisionProvenancePackResponse,
    ProposalDecisionProvenanceResponse,
    ProposalProvenanceEdge,
    ProposalProvenanceNode,
    SourceTrustGateResponse,
)


class ProposalDecisionProvenanceService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def provenance(
        self,
        trace_id: str,
        workflow: BuyerIntelligenceWorkflowResponse,
        replay: BuyerWorkflowReplayResponse,
        council: ProposalAgentCouncilResponse,
        cost_governance: CostGovernanceResponse,
        source_trust: SourceTrustGateResponse,
        model_risk: ModelRiskRegisterResponse,
        procurement_risk: ProcurementQuestionRiskResponse,
    ) -> ProposalDecisionProvenanceResponse:
        nodes = self._nodes(workflow, replay, council, cost_governance, source_trust, model_risk, procurement_risk)
        edges = self._edges(workflow, replay, council)
        status = self._status(nodes, workflow, council, source_trust, model_risk, procurement_risk)
        return ProposalDecisionProvenanceResponse(
            title="Proposal Decision Provenance Graph",
            provenance_id=f"proposal-provenance-{self._slug(trace_id)}",
            status=status,
            generated_at=datetime.now(UTC).isoformat(),
            nodes=nodes,
            edges=edges,
            summary=self._summary(nodes, edges, workflow, council, cost_governance),
            decision_controls=self._decision_controls(workflow, council, source_trust, model_risk, procurement_risk),
            eval_assertions=self._eval_assertions(nodes, edges, replay, council),
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        provenance: ProposalDecisionProvenanceResponse,
        write_artifact: bool = True,
    ) -> ProposalDecisionProvenancePackResponse:
        pack = self._pack_payload(trace_id, provenance)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "decision_provenance"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = self._slug(trace_id)
            markdown_path = pack_dir / f"proposal_decision_provenance_{safe_trace_id}.md"
            json_path = pack_dir / f"proposal_decision_provenance_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["decision_provenance_markdown"] = artifact_path
            pack["artifact_paths"]["decision_provenance_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return ProposalDecisionProvenancePackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            provenance=provenance,
            trace_id=trace_id,
        )

    def _nodes(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        replay: BuyerWorkflowReplayResponse,
        council: ProposalAgentCouncilResponse,
        cost_governance: CostGovernanceResponse,
        source_trust: SourceTrustGateResponse,
        model_risk: ModelRiskRegisterResponse,
        procurement_risk: ProcurementQuestionRiskResponse,
    ) -> list[ProposalProvenanceNode]:
        nodes: list[ProposalProvenanceNode] = []
        for stage in workflow.workflow_stages:
            prior_stage = (
                []
                if stage.sequence == 1
                else [f"stage:{workflow.workflow_stages[stage.sequence - 2].stage_id}"]
            )
            nodes.append(
                ProposalProvenanceNode(
                    node_id=f"stage:{stage.stage_id}",
                    node_type="workflow_stage",
                    label=stage.name,
                    owner_role=stage.owner_role,
                    status=stage.status,
                    evidence=f"Durability key {stage.durability_key}; restart policy {stage.restart_policy}.",
                    source_refs=stage.trace_refs,
                    depends_on=prior_stage,
                    endpoint_refs=["/proposal/buyer-intelligence", "/proposal/buyer-intelligence-replay"],
                )
            )
        for message in council.conversation:
            nodes.append(
                ProposalProvenanceNode(
                    node_id=f"turn:{message.message_id}",
                    node_type="agent_turn",
                    label=f"{message.role}: {message.message_type}",
                    owner_role=message.role,
                    status="needs_review" if message.governance_flags else "complete",
                    evidence=message.content,
                    source_refs=message.cited_evidence,
                    depends_on=[f"stage:{workflow.workflow_stages[0].stage_id}"],
                    endpoint_refs=["/proposal/agent-council"],
                )
            )
        for handoff in council.handoffs:
            source_turns = [
                f"turn:{message.message_id}"
                for message in council.conversation
                if message.agent_id == handoff.from_agent_id
            ][:1]
            nodes.append(
                ProposalProvenanceNode(
                    node_id=f"handoff:{handoff.handoff_id}",
                    node_type="handoff",
                    label=f"{handoff.from_agent_id} to {handoff.to_agent_id}",
                    owner_role=handoff.to_agent_id,
                    status=handoff.status,
                    evidence=handoff.reason,
                    source_refs=handoff.evidence_refs,
                    depends_on=source_turns,
                    endpoint_refs=["/proposal/agent-council"],
                )
            )
        for gate in workflow.governance_gates:
            nodes.append(
                ProposalProvenanceNode(
                    node_id=f"gate:{gate.gate_id}",
                    node_type="governance_gate",
                    label=gate.name,
                    owner_role=gate.owner_role,
                    status=gate.status,
                    evidence=f"{gate.evidence} Required action: {gate.required_action}",
                    source_refs=[gate.gate_id],
                    depends_on=[
                        f"stage:{stage.stage_id}"
                        for stage in workflow.workflow_stages
                        if self._gate_stage_matches(gate.gate_id, stage.governance_gates)
                    ],
                    endpoint_refs=gate.endpoint_refs,
                )
            )
        nodes.extend(
            [
                ProposalProvenanceNode(
                    node_id="policy:provider-cost",
                    node_type="provider_policy",
                    label="Provider and cost governance",
                    owner_role="Platform Owner",
                    status=cost_governance.governance_status,
                    evidence=(
                        f"Provider={cost_governance.provider_readiness['provider_mode']}; "
                        f"budget={cost_governance.budget_summary['daily_estimated_cost']}."
                    ),
                    source_refs=[cost_governance.trace_id],
                    endpoint_refs=["/ops/cost-governance"],
                ),
                ProposalProvenanceNode(
                    node_id="policy:source-trust",
                    node_type="source_policy",
                    label="Source trust policy",
                    owner_role="Knowledge Owner",
                    status=source_trust.status,
                    evidence=(
                        f"{source_trust.summary['blocked_count']} blocked source(s), "
                        f"{source_trust.summary['approval_required_count']} approval-required source(s)."
                    ),
                    source_refs=[source.filename for source in source_trust.sources[:6]],
                    endpoint_refs=["/evidence/source-trust"],
                ),
                ProposalProvenanceNode(
                    node_id="policy:model-risk",
                    node_type="model_policy",
                    label="Model risk policy",
                    owner_role="AI Governance Reviewer",
                    status=model_risk.register_status,
                    evidence=(
                        f"{model_risk.summary['risk_count']} risk(s), "
                        f"{model_risk.summary['needs_review_count']} needing review."
                    ),
                    source_refs=[model_risk.trace_id],
                    endpoint_refs=["/governance/model-risk-register"],
                ),
                ProposalProvenanceNode(
                    node_id="policy:procurement",
                    node_type="procurement_policy",
                    label="Procurement Q&A approval policy",
                    owner_role="Procurement Lead",
                    status=self._procurement_status(procurement_risk),
                    evidence=(
                        f"{procurement_risk.coverage_summary['question_count']} question(s), "
                        f"{procurement_risk.approval_summary['approvals_required_count']} approval(s)."
                    ),
                    source_refs=[question.question_id for question in procurement_risk.questions[:6]],
                    endpoint_refs=["/procurement/question-risk"],
                ),
                ProposalProvenanceNode(
                    node_id="replay:checkpoint-validation",
                    node_type="eval_checkpoint",
                    label="Replay checkpoint validation",
                    owner_role="Platform Owner",
                    status=replay.checkpoint_validation["status"],
                    evidence=f"{replay.transition_count} transition(s) checked for checkpoint and trace refs.",
                    source_refs=[replay.workflow_id],
                    endpoint_refs=["/proposal/buyer-intelligence-replay"],
                ),
            ]
        )
        return nodes

    def _edges(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        replay: BuyerWorkflowReplayResponse,
        council: ProposalAgentCouncilResponse,
    ) -> list[ProposalProvenanceEdge]:
        edges: list[ProposalProvenanceEdge] = []
        for transition in replay.transitions:
            if transition.from_stage_id:
                edges.append(
                    ProposalProvenanceEdge(
                        edge_id=f"edge:{transition.transition_id}",
                        from_node_id=f"stage:{transition.from_stage_id}",
                        to_node_id=f"stage:{transition.to_stage_id}",
                        relation="workflow_transition",
                        condition=transition.condition,
                        trace_refs=transition.trace_refs,
                    )
                )
        first_stage = f"stage:{workflow.workflow_stages[0].stage_id}"
        for message in council.conversation:
            edges.append(
                ProposalProvenanceEdge(
                    edge_id=f"edge:stage-to-{message.message_id}",
                    from_node_id=first_stage,
                    to_node_id=f"turn:{message.message_id}",
                    relation="shared_state_consumed_by_agent",
                    condition="agent turn derives from buyer workflow shared state",
                    trace_refs=message.cited_evidence,
                )
            )
            if message.handoff_to:
                handoff = next(
                    (
                        item
                        for item in council.handoffs
                        if item.from_agent_id == message.agent_id and item.to_agent_id == message.handoff_to
                    ),
                    None,
                )
                if handoff:
                    edges.append(
                        ProposalProvenanceEdge(
                            edge_id=f"edge:{message.message_id}-to-{handoff.handoff_id}",
                            from_node_id=f"turn:{message.message_id}",
                            to_node_id=f"handoff:{handoff.handoff_id}",
                            relation="handoff_created",
                            condition=", ".join(message.governance_flags) or "handoff requested",
                            trace_refs=message.cited_evidence,
                        )
                    )
        for gate in workflow.governance_gates:
            edges.append(
                ProposalProvenanceEdge(
                    edge_id=f"edge:{gate.gate_id}-to-submission",
                    from_node_id=f"gate:{gate.gate_id}",
                    to_node_id=f"stage:{workflow.workflow_stages[-1].stage_id}",
                    relation="submission_gate",
                    condition=gate.required_action,
                    trace_refs=[gate.gate_id],
                )
            )
        for policy_node in ["policy:provider-cost", "policy:source-trust", "policy:model-risk", "policy:procurement"]:
            edges.append(
                ProposalProvenanceEdge(
                    edge_id=f"edge:{policy_node}-to-checkpoint",
                    from_node_id=policy_node,
                    to_node_id="replay:checkpoint-validation",
                    relation="control_evidence",
                    condition="policy evidence must be visible in replayable decision state",
                    trace_refs=[],
                )
            )
        return edges

    def _status(
        self,
        nodes: list[ProposalProvenanceNode],
        workflow: BuyerIntelligenceWorkflowResponse,
        council: ProposalAgentCouncilResponse,
        source_trust: SourceTrustGateResponse,
        model_risk: ModelRiskRegisterResponse,
        procurement_risk: ProcurementQuestionRiskResponse,
    ) -> str:
        if workflow.workflow_status == "blocked" or council.status == "blocked_by_governance":
            return "blocked_by_governance"
        if source_trust.status == "blocked" or model_risk.register_status == "blocked":
            return "blocked_by_policy"
        if procurement_risk.approval_summary.get("approvals_required_count", 0) or any(
            node.status in {"open", "needs_review", "waiting_on_approvals"} for node in nodes
        ):
            return "needs_human_review"
        return "ready_for_audit_review"

    def _summary(
        self,
        nodes: list[ProposalProvenanceNode],
        edges: list[ProposalProvenanceEdge],
        workflow: BuyerIntelligenceWorkflowResponse,
        council: ProposalAgentCouncilResponse,
        cost_governance: CostGovernanceResponse,
    ) -> dict[str, Any]:
        node_types = Counter(node.node_type for node in nodes)
        statuses = Counter(node.status for node in nodes)
        return {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "node_type_counts": dict(sorted(node_types.items())),
            "status_counts": dict(sorted(statuses.items())),
            "workflow_status": workflow.workflow_status,
            "council_status": council.status,
            "approval_items": len(workflow.human_approval_queue),
            "open_handoffs": council.decision_summary.get("open_handoffs", 0),
            "provider_mode": cost_governance.provider_readiness["provider_mode"],
            "external_provider_requested": cost_governance.provider_readiness["external_provider_requested"],
        }

    def _decision_controls(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        council: ProposalAgentCouncilResponse,
        source_trust: SourceTrustGateResponse,
        model_risk: ModelRiskRegisterResponse,
        procurement_risk: ProcurementQuestionRiskResponse,
    ) -> list[dict[str, Any]]:
        return [
            {
                "control_id": "control-clear-human-approvals",
                "status": "needs_review" if workflow.human_approval_queue else "pass",
                "owner_role": "Proposal Manager",
                "evidence": f"{len(workflow.human_approval_queue)} approval queue item(s).",
            },
            {
                "control_id": "control-close-agent-handoffs",
                "status": "needs_review" if council.decision_summary.get("open_handoffs", 0) else "pass",
                "owner_role": "Proposal Manager",
                "evidence": f"{council.decision_summary.get('open_handoffs', 0)} council handoff(s) open.",
            },
            {
                "control_id": "control-source-trust",
                "status": source_trust.status,
                "owner_role": "Knowledge Owner",
                "evidence": f"{source_trust.summary['blocked_count']} blocked source(s).",
            },
            {
                "control_id": "control-model-risk",
                "status": model_risk.register_status,
                "owner_role": "AI Governance Reviewer",
                "evidence": f"{model_risk.summary['needs_review_count']} model risk item(s) need review.",
            },
            {
                "control_id": "control-procurement-approval",
                "status": self._procurement_status(procurement_risk),
                "owner_role": "Procurement Lead",
                "evidence": f"{procurement_risk.approval_summary['approvals_required_count']} procurement approval(s).",
            },
        ]

    def _eval_assertions(
        self,
        nodes: list[ProposalProvenanceNode],
        edges: list[ProposalProvenanceEdge],
        replay: BuyerWorkflowReplayResponse,
        council: ProposalAgentCouncilResponse,
    ) -> list[dict[str, Any]]:
        node_ids = {node.node_id for node in nodes}
        edge_refs_valid = all(edge.from_node_id in node_ids and edge.to_node_id in node_ids for edge in edges)
        required_types = {
            "workflow_stage",
            "agent_turn",
            "handoff",
            "governance_gate",
            "provider_policy",
            "eval_checkpoint",
        }
        observed_types = {node.node_type for node in nodes}
        return [
            {
                "assertion_id": "provenance-graph-edges-resolve",
                "assertion": "every provenance edge resolves to known typed nodes",
                "expected": True,
                "observed": edge_refs_valid,
                "passed": edge_refs_valid,
            },
            {
                "assertion_id": "provenance-required-node-types",
                "assertion": "workflow, agent, handoff, governance, provider, and eval nodes are present",
                "expected": sorted(required_types),
                "observed": sorted(observed_types),
                "passed": required_types <= observed_types,
            },
            {
                "assertion_id": "provenance-checkpoints-pass-through",
                "assertion": "buyer replay checkpoint validation remains visible in provenance",
                "expected": "pass",
                "observed": replay.checkpoint_validation["status"],
                "passed": replay.checkpoint_validation["status"] == "pass",
            },
            {
                "assertion_id": "provenance-council-evals-pass-through",
                "assertion": "agent council eval scenarios remain attached and passing",
                "expected": len(council.eval_scenarios),
                "observed": sum(1 for scenario in council.eval_scenarios if scenario["passed"]),
                "passed": all(scenario["passed"] for scenario in council.eval_scenarios),
            },
        ]

    def _pack_payload(self, trace_id: str, provenance: ProposalDecisionProvenanceResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Proposal Decision Provenance Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "provenance": provenance.model_dump(mode="json"),
            "reviewer_controls": [
                "Verify every edge resolves before using this as a review artifact.",
                "Treat needs_review or open nodes as blocking final submission until owner approval is recorded.",
                "Keep external providers disabled unless provider, cost, privacy, and model-risk controls pass.",
                (
                    "Regenerate after changing buyer workflow, agent council, procurement, source trust, "
                    "or model-risk policy."
                ),
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        provenance = pack["provenance"]
        summary = provenance["summary"]
        lines = [
            "# Proposal Decision Provenance Pack",
            "",
            "## Summary",
            "",
            f"- Status: {provenance['status']}",
            f"- Nodes: {summary['node_count']}",
            f"- Edges: {summary['edge_count']}",
            f"- Workflow status: {summary['workflow_status']}",
            f"- Council status: {summary['council_status']}",
            f"- Provider mode: {summary['provider_mode']}",
            "",
            "## Provenance Nodes",
            "",
            "| Node | Type | Owner | Status | Evidence |",
            "| --- | --- | --- | --- | --- |",
        ]
        for node in provenance["nodes"]:
            lines.append(
                f"| `{self._md(node['node_id'])}` | {node['node_type']} | "
                f"{self._md(node['owner_role'] or 'n/a')} | {node['status']} | {self._md(node['evidence'])} |"
            )
        lines.extend(["", "## Provenance Edges", ""])
        lines.append("| From | To | Relation | Condition |")
        lines.append("| --- | --- | --- | --- |")
        for edge in provenance["edges"]:
            lines.append(
                f"| `{self._md(edge['from_node_id'])}` | `{self._md(edge['to_node_id'])}` | "
                f"{edge['relation']} | {self._md(edge['condition'])} |"
            )
        lines.extend(["", "## Decision Controls", ""])
        for control in provenance["decision_controls"]:
            lines.append(
                f"- {control['control_id']} ({control['status']}): "
                f"{self._md(control['owner_role'])} - {self._md(control['evidence'])}"
            )
        lines.extend(["", "## Eval Assertions", ""])
        for assertion in provenance["eval_assertions"]:
            result = "pass" if assertion["passed"] else "fail"
            lines.append(f"- {assertion['assertion_id']} ({result}): {self._md(assertion['assertion'])}")
        lines.extend(["", "## Reviewer Controls", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_controls"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in provenance["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {self._md(item)}" for item in provenance["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Generated Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _gate_stage_matches(self, gate_id: str, stage_gates: list[str]) -> set[str]:
        aliases = {
            "gate-human-approval": {"human_in_the_loop", "unsupported_claim_block", "executive_signoff"},
            "gate-source-trust": {"source_trust", "citation_coverage"},
            "gate-model-risk": {"model_risk", "provider_flexibility"},
            "gate-provider-cost": {"provider_flexibility"},
            "gate-procurement-risk": {"procurement_approval", "commercial_exception_review"},
            "gate-durable-state": {"state_checkpoint", "input_traceability"},
        }
        return aliases.get(gate_id, {gate_id}) & set(stage_gates)

    def _procurement_status(self, procurement_risk: ProcurementQuestionRiskResponse) -> str:
        if procurement_risk.approval_summary.get("blocked_count", 0):
            return "blocked"
        if procurement_risk.approval_summary.get("approvals_required_count", 0):
            return "needs_review"
        return "pass"

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {"method": "GET", "path": "/proposal/decision-provenance", "purpose": "View provenance graph."},
            {"method": "POST", "path": "/proposal/decision-provenance-pack", "purpose": "Write provenance artifacts."},
            {"method": "GET", "path": "/proposal/buyer-intelligence-replay", "purpose": "Source checkpoint replay."},
            {"method": "GET", "path": "/proposal/agent-council", "purpose": "Source role transcript."},
            {"method": "GET", "path": "/evidence/source-trust", "purpose": "Source evidence policy."},
            {"method": "GET", "path": "/governance/model-risk-register", "purpose": "Source model-risk policy."},
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/proposal/decision-provenance" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/proposal/decision-provenance-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'rg "proposal/decision-provenance|Decision Provenance|decision_provenance" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\decision_provenance -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "The graph is deterministic local provenance, not a distributed tracing backend.",
            "Edges connect generated control artifacts and reviewer handoffs; they do not execute workflow jobs.",
            "Human approval status is modeled from local queues and must be reconciled with real reviewer systems.",
            "External OpenAI, Azure, CRM, procurement, and GRC systems remain optional and are not called.",
        ]

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower() or "local"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
