from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    BuyerIntelligenceWorkflowResponse,
    CostGovernanceResponse,
    ModelRiskRegisterResponse,
    ProcurementQuestionRiskResponse,
    ProposalAgentCouncilPackResponse,
    ProposalAgentCouncilResponse,
    ProposalCouncilAgent,
    ProposalCouncilHandoff,
    ProposalCouncilMessage,
    SourceTrustGateResponse,
)


class ProposalAgentCouncilService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def council(
        self,
        trace_id: str,
        workflow: BuyerIntelligenceWorkflowResponse,
        cost_governance: CostGovernanceResponse,
        source_trust: SourceTrustGateResponse,
        model_risk: ModelRiskRegisterResponse,
        procurement_risk: ProcurementQuestionRiskResponse,
    ) -> ProposalAgentCouncilResponse:
        agents = self._agents()
        shared_state = self._shared_state(workflow, source_trust, model_risk, procurement_risk)
        conversation = self._conversation(agents, workflow, shared_state, source_trust, model_risk, procurement_risk)
        handoffs = self._handoffs(conversation, workflow, source_trust, model_risk, procurement_risk)
        tool_governance = self._tool_governance(agents, cost_governance, model_risk)
        budget_ledger = self._budget_ledger(conversation, cost_governance)
        status = self._status(workflow, handoffs, tool_governance)
        return ProposalAgentCouncilResponse(
            title="Proposal Agent Council",
            council_id=f"proposal-council-{self._slug(trace_id)}",
            status=status,
            generated_at=datetime.now(UTC).isoformat(),
            agents=agents,
            conversation=conversation,
            shared_state=shared_state,
            handoffs=handoffs,
            tool_governance=tool_governance,
            budget_ledger=budget_ledger,
            decision_summary=self._decision_summary(status, workflow, handoffs, shared_state),
            eval_scenarios=self._eval_scenarios(agents, conversation, handoffs, tool_governance),
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        council: ProposalAgentCouncilResponse,
        write_artifact: bool = True,
    ) -> ProposalAgentCouncilPackResponse:
        pack = self._pack_payload(trace_id, council)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        transcript_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "agent_council"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = self._slug(trace_id)
            markdown_path = pack_dir / f"proposal_agent_council_{safe_trace_id}.md"
            json_path = pack_dir / f"proposal_agent_council_{safe_trace_id}.json"
            transcript_path = pack_dir / f"proposal_agent_council_transcript_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            transcript_artifact_path = str(transcript_path.resolve())
            pack["artifact_paths"]["agent_council_markdown"] = artifact_path
            pack["artifact_paths"]["agent_council_json"] = json_artifact_path
            pack["artifact_paths"]["agent_council_transcript"] = transcript_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
            transcript_path.write_text(
                json.dumps(
                    {
                        "trace_id": trace_id,
                        "council_id": council.council_id,
                        "agents": [agent.model_dump(mode="json") for agent in council.agents],
                        "conversation": [message.model_dump(mode="json") for message in council.conversation],
                        "handoffs": [handoff.model_dump(mode="json") for handoff in council.handoffs],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

        return ProposalAgentCouncilPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            transcript_artifact_path=transcript_artifact_path,
            markdown=markdown,
            pack=pack,
            council=council,
            trace_id=trace_id,
        )

    def _agents(self) -> list[ProposalCouncilAgent]:
        return [
            ProposalCouncilAgent(
                agent_id="agent-sales",
                role="Sales Lead",
                mandate="Protect win strategy, buyer value, and commercial posture.",
                allowed_tools=["customer_fit", "win_strategy", "answer_reuse_library"],
                blocked_tools=["external_provider_without_governance", "submit_final_response"],
                approval_scope=["pricing posture", "executive summary", "commercial exceptions"],
                budget_tokens=1800,
            ),
            ProposalCouncilAgent(
                agent_id="agent-presales",
                role="Presales Architect",
                mandate="Ground technical answers in retrieved evidence and flag implementation gaps.",
                allowed_tools=["retrieval", "requirement_matrix", "draft_response", "source_trust"],
                blocked_tools=["uncited_claim_generation", "unapproved_source_reuse"],
                approval_scope=["technical architecture", "implementation plan", "source coverage"],
                budget_tokens=2200,
            ),
            ProposalCouncilAgent(
                agent_id="agent-compliance",
                role="Compliance Reviewer",
                mandate="Check regulatory, security, privacy, and model-governance claims before release.",
                allowed_tools=["compliance_matrix", "privacy_retention", "model_risk", "citation_lineage"],
                blocked_tools=["approve_unsupported_claims", "export_customer_sensitive_data"],
                approval_scope=["compliance claims", "privacy language", "AI governance language"],
                budget_tokens=2000,
            ),
            ProposalCouncilAgent(
                agent_id="agent-procurement",
                role="Procurement Lead",
                mandate="Route buyer Q&A, contract exceptions, pricing risk, and required approvals.",
                allowed_tools=["procurement_question_risk", "procurement_risk_desk", "submission_exceptions"],
                blocked_tools=["bypass_legal_or_finance_approval", "promise_custom_terms"],
                approval_scope=["buyer Q&A", "commercial exceptions", "legal redlines"],
                budget_tokens=1800,
            ),
            ProposalCouncilAgent(
                agent_id="agent-proposal-manager",
                role="Proposal Manager",
                mandate="Coordinate handoffs, preserve shared state, and decide whether the packet can advance.",
                allowed_tools=["buyer_workflow", "reviewer_collaboration", "submission_decision"],
                blocked_tools=["submit_without_human_approval", "clear_governance_gate_without_owner"],
                approval_scope=["final packet readiness", "reviewer queue", "handoff completeness"],
                budget_tokens=1600,
            ),
        ]

    def _conversation(
        self,
        agents: list[ProposalCouncilAgent],
        workflow: BuyerIntelligenceWorkflowResponse,
        shared_state: dict[str, Any],
        source_trust: SourceTrustGateResponse,
        model_risk: ModelRiskRegisterResponse,
        procurement_risk: ProcurementQuestionRiskResponse,
    ) -> list[ProposalCouncilMessage]:
        agent_by_id = {agent.agent_id: agent for agent in agents}
        blocked_sources = source_trust.summary.get("blocked_count", 0)
        approvals = len(workflow.human_approval_queue)
        questions = procurement_risk.coverage_summary.get("question_count", len(procurement_risk.questions))
        model_reviews = model_risk.summary.get("needs_review_count", 0)
        procurement_status = self._procurement_status(procurement_risk)
        messages = [
            self._message(
                1,
                agent_by_id["agent-proposal-manager"],
                "shared_state_update",
                (
                    f"Loaded {shared_state['requirements']} requirements, "
                    f"{shared_state['approval_items']} approval items, and workflow status "
                    f"{workflow.workflow_status} into council state."
                ),
                [workflow.workflow_id],
                [{"tool": "buyer_workflow", "status": "read_only"}],
                None,
                [],
            ),
            self._message(
                2,
                agent_by_id["agent-presales"],
                "evidence_review",
                (
                    f"Requirement matrix has {shared_state['matrix_rows']} rows; "
                    f"{blocked_sources} blocked sources must stay out of final citations."
                ),
                shared_state["source_refs"][:4],
                [{"tool": "source_trust", "status": source_trust.status}],
                "agent-compliance" if blocked_sources else None,
                ["source_review_required"] if blocked_sources else [],
            ),
            self._message(
                3,
                agent_by_id["agent-compliance"],
                "governance_review",
                (
                    f"Model-risk register has {model_risk.summary['risk_count']} risks and "
                    f"{model_reviews} item(s) needing review before provider or final-language changes."
                ),
                [str(item) for row in model_risk.reviewer_queue for item in row["risk_ids"]][:4],
                [{"tool": "model_risk", "status": model_risk.register_status}],
                "agent-proposal-manager" if model_reviews else None,
                ["model_risk_review"] if model_reviews else [],
            ),
            self._message(
                4,
                agent_by_id["agent-procurement"],
                "buyer_qa_review",
                (
                    f"Procurement Q&A covers {questions} buyer questions with "
                    f"{procurement_risk.approval_summary['approvals_required_count']} approval(s) required."
                ),
                shared_state["procurement_refs"][:4],
                [{"tool": "procurement_question_risk", "status": procurement_status}],
                "agent-sales" if procurement_risk.approval_summary["approvals_required_count"] else None,
                ["buyer_approval_required"]
                if procurement_risk.approval_summary["approvals_required_count"]
                else [],
            ),
            self._message(
                5,
                agent_by_id["agent-sales"],
                "commercial_review",
                (
                    "Commercial response can advance only with cited value proof, approved pricing posture, "
                    "and unresolved exceptions visible in the submission decision."
                ),
                shared_state["source_refs"][:3],
                [{"tool": "win_strategy", "status": "governed"}],
                "agent-procurement" if approvals else None,
                ["commercial_exception_review"] if approvals else [],
            ),
            self._message(
                6,
                agent_by_id["agent-proposal-manager"],
                "handoff_decision",
                (
                    f"Council recommendation is {self._recommended_posture(workflow, approvals)}; "
                    "do not clear the packet until open handoffs and governance gates are resolved."
                ),
                [gate.gate_id for gate in workflow.governance_gates],
                [{"tool": "submission_decision", "status": "requires_human_confirmation"}],
                None,
                ["human_in_the_loop"] if approvals else [],
            ),
        ]
        return messages

    def _message(
        self,
        turn: int,
        agent: ProposalCouncilAgent,
        message_type: str,
        content: str,
        cited_evidence: list[str],
        tool_calls: list[dict[str, Any]],
        handoff_to: str | None,
        governance_flags: list[str],
    ) -> ProposalCouncilMessage:
        token_estimate = max(80, len(content.split()) * 6 + len(cited_evidence) * 18 + len(tool_calls) * 35)
        return ProposalCouncilMessage(
            message_id=f"msg-{turn:02d}-{agent.agent_id}",
            turn=turn,
            agent_id=agent.agent_id,
            role=agent.role,
            message_type=message_type,
            content=content,
            cited_evidence=cited_evidence,
            tool_calls=tool_calls,
            handoff_to=handoff_to,
            governance_flags=governance_flags,
            token_estimate=token_estimate,
        )

    def _shared_state(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        source_trust: SourceTrustGateResponse,
        model_risk: ModelRiskRegisterResponse,
        procurement_risk: ProcurementQuestionRiskResponse,
    ) -> dict[str, Any]:
        source_refs = [source.filename for source in source_trust.sources]
        procurement_refs = [
            citation.filename for question in procurement_risk.questions for citation in question.citations
        ]
        stage_statuses = Counter(stage.status for stage in workflow.workflow_stages)
        return {
            "workflow_id": workflow.workflow_id,
            "workflow_status": workflow.workflow_status,
            "requirements": workflow.shared_state.get("requirements", 0),
            "matrix_rows": workflow.shared_state.get("matrix_rows", 0),
            "approval_items": len(workflow.human_approval_queue),
            "governance_gate_count": len(workflow.governance_gates),
            "stage_status_counts": dict(sorted(stage_statuses.items())),
            "source_refs": source_refs,
            "procurement_refs": sorted(set(procurement_refs)),
            "source_trust_status": source_trust.status,
            "model_risk_status": model_risk.register_status,
            "procurement_status": self._procurement_status(procurement_risk),
            "state_policy": "append-only local council transcript with deterministic shared-state deltas",
        }

    def _handoffs(
        self,
        conversation: list[ProposalCouncilMessage],
        workflow: BuyerIntelligenceWorkflowResponse,
        source_trust: SourceTrustGateResponse,
        model_risk: ModelRiskRegisterResponse,
        procurement_risk: ProcurementQuestionRiskResponse,
    ) -> list[ProposalCouncilHandoff]:
        handoffs = []
        for message in conversation:
            if message.handoff_to:
                handoffs.append(
                    ProposalCouncilHandoff(
                        handoff_id=f"handoff-{message.turn:02d}-{message.agent_id}-to-{message.handoff_to}",
                        from_agent_id=message.agent_id,
                        to_agent_id=message.handoff_to,
                        reason=message.content,
                        status="open" if message.governance_flags else "ready",
                        required_before=self._required_before(message.message_type),
                        evidence_refs=message.cited_evidence[:6],
                    )
                )
        if workflow.human_approval_queue:
            handoffs.append(
                ProposalCouncilHandoff(
                    handoff_id="handoff-human-approval-queue",
                    from_agent_id="agent-proposal-manager",
                    to_agent_id="human-reviewers",
                    reason=f"{len(workflow.human_approval_queue)} buyer workflow approval item(s) remain open.",
                    status="open",
                    required_before="final response submission",
                    evidence_refs=[item.approval_id for item in workflow.human_approval_queue[:6]],
                )
            )
        if source_trust.reviewer_queue or model_risk.reviewer_queue or procurement_risk.approval_summary.get(
            "approvals_required_count",
            0,
        ):
            handoffs.append(
                ProposalCouncilHandoff(
                    handoff_id="handoff-governance-controls",
                    from_agent_id="agent-compliance",
                    to_agent_id="agent-proposal-manager",
                    reason="Governance, source trust, or procurement approvals require owner confirmation.",
                    status="open",
                    required_before="executive submission memo",
                    evidence_refs=[
                        f"source_trust={source_trust.status}",
                        f"model_risk={model_risk.register_status}",
                        f"procurement={self._procurement_status(procurement_risk)}",
                    ],
                )
            )
        return handoffs

    def _procurement_status(self, procurement_risk: ProcurementQuestionRiskResponse) -> str:
        if procurement_risk.approval_summary.get("blocked_count", 0):
            return "blocked"
        if procurement_risk.approval_summary.get("approvals_required_count", 0):
            return "needs_review"
        return "pass"

    def _tool_governance(
        self,
        agents: list[ProposalCouncilAgent],
        cost_governance: CostGovernanceResponse,
        model_risk: ModelRiskRegisterResponse,
    ) -> list[dict[str, Any]]:
        provider_ready = cost_governance.provider_readiness
        rows: list[dict[str, Any]] = []
        for agent in agents:
            rows.append(
                {
                    "agent_id": agent.agent_id,
                    "role": agent.role,
                    "allowed_tools": agent.allowed_tools,
                    "blocked_tools": agent.blocked_tools,
                    "policy": "read_only_until_human_approval" if agent.role != "Proposal Manager" else "orchestrate",
                    "max_budget_tokens": agent.budget_tokens,
                    "requires_provider_review": not provider_ready["local_mock_ready"],
                }
            )
        rows.append(
            {
                "agent_id": "global",
                "role": "All agents",
                "allowed_tools": ["local_retrieval", "local_artifact_generation", "mock_provider"],
                "blocked_tools": ["external_provider_call_without_env", "submit_without_approval"],
                "policy": "blocked" if model_risk.summary["needs_review_count"] else "pass",
                "max_budget_tokens": sum(agent.budget_tokens for agent in agents),
                "requires_provider_review": provider_ready["external_provider_requested"],
            }
        )
        return rows

    def _budget_ledger(
        self,
        conversation: list[ProposalCouncilMessage],
        cost_governance: CostGovernanceResponse,
    ) -> dict[str, Any]:
        tokens_by_agent = Counter()
        for message in conversation:
            tokens_by_agent[message.agent_id] += message.token_estimate
        total_tokens = sum(tokens_by_agent.values())
        token_profile = cost_governance.token_profile
        input_rate = token_profile.get("input_cost_per_1k", 0.0)
        output_rate = token_profile.get("output_cost_per_1k", 0.0)
        estimated_cost = round((total_tokens * 0.7 / 1000 * input_rate) + (total_tokens * 0.3 / 1000 * output_rate), 6)
        return {
            "provider_mode": cost_governance.provider_readiness["provider_mode"],
            "local_mock_default": cost_governance.provider_readiness["local_mock_ready"],
            "total_token_estimate": total_tokens,
            "tokens_by_agent": dict(sorted(tokens_by_agent.items())),
            "estimated_cost": estimated_cost,
            "budget_utilization": cost_governance.budget_summary["budget_utilization"],
            "budget_status": cost_governance.governance_status,
            "note": "Council transcript is deterministic local analysis; token and cost values are planning estimates.",
        }

    def _status(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        handoffs: list[ProposalCouncilHandoff],
        tool_governance: list[dict[str, Any]],
    ) -> str:
        if workflow.workflow_status == "blocked" or any(row["policy"] == "blocked" for row in tool_governance):
            return "blocked_by_governance"
        if any(handoff.status == "open" for handoff in handoffs):
            return "needs_human_handoff"
        return "ready_for_executive_review"

    def _decision_summary(
        self,
        status: str,
        workflow: BuyerIntelligenceWorkflowResponse,
        handoffs: list[ProposalCouncilHandoff],
        shared_state: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "recommended_posture": self._recommended_posture(workflow, len(workflow.human_approval_queue)),
            "status": status,
            "open_handoffs": sum(handoff.status == "open" for handoff in handoffs),
            "approval_items": len(workflow.human_approval_queue),
            "governance_gates": shared_state["governance_gate_count"],
            "advance_criteria": [
                "All open handoffs are accepted or closed by the named human owner.",
                "Blocked or approval-required source trust rows are resolved before citation reuse.",
                "Provider and model-risk gates are re-run before leaving mock mode.",
                "Procurement Q&A and commercial exceptions have explicit reviewer approval.",
            ],
        }

    def _eval_scenarios(
        self,
        agents: list[ProposalCouncilAgent],
        conversation: list[ProposalCouncilMessage],
        handoffs: list[ProposalCouncilHandoff],
        tool_governance: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        agent_ids = {agent.agent_id for agent in agents}
        turns = [message.turn for message in conversation]
        handoff_targets = {handoff.to_agent_id for handoff in handoffs if handoff.to_agent_id != "human-reviewers"}
        return [
            {
                "scenario_id": "agent-council-required-roles",
                "assertion": "sales, presales, compliance, procurement, and proposal manager roles are present",
                "expected": 5,
                "observed": len(agent_ids),
                "passed": {
                    "agent-sales",
                    "agent-presales",
                    "agent-compliance",
                    "agent-procurement",
                    "agent-proposal-manager",
                }
                <= agent_ids,
            },
            {
                "scenario_id": "agent-council-turn-order",
                "assertion": "conversation turns are deterministic and contiguous",
                "expected": list(range(1, len(conversation) + 1)),
                "observed": turns,
                "passed": turns == list(range(1, len(conversation) + 1)),
            },
            {
                "scenario_id": "agent-council-governed-tools",
                "assertion": "every agent has allowed and blocked tool policy",
                "expected": len(agents) + 1,
                "observed": len(tool_governance),
                "passed": all(row["allowed_tools"] and row["blocked_tools"] for row in tool_governance),
            },
            {
                "scenario_id": "agent-council-handoff-routing",
                "assertion": "handoffs route only to known agents or human reviewers",
                "expected": "known agent ids",
                "observed": sorted(handoff_targets),
                "passed": handoff_targets <= agent_ids,
            },
        ]

    def _pack_payload(self, trace_id: str, council: ProposalAgentCouncilResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Proposal Agent Council Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "council": council.model_dump(mode="json"),
            "reviewer_controls": [
                "Use the council transcript to inspect cross-functional reasoning, not to auto-approve a bid.",
                "Treat every open handoff as requiring named human owner confirmation.",
                "Keep external provider calls disabled until model-risk, privacy, and cost gates are cleared.",
                "Regenerate after changing source trust, procurement risk, cost governance, or buyer workflow policy.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        council = pack["council"]
        summary = council["decision_summary"]
        lines = [
            "# Proposal Agent Council Pack",
            "",
            "## Decision Summary",
            "",
            f"- Status: {council['status']}",
            f"- Recommended posture: {summary['recommended_posture']}",
            f"- Open handoffs: {summary['open_handoffs']}",
            f"- Approval items: {summary['approval_items']}",
            f"- Governance gates: {summary['governance_gates']}",
            "",
            "## Agents",
            "",
            "| Agent | Role | Budget tokens | Allowed tools | Blocked tools |",
            "| --- | --- | ---: | --- | --- |",
        ]
        for agent in council["agents"]:
            lines.append(
                f"| {agent['agent_id']} | {self._md(agent['role'])} | {agent['budget_tokens']} | "
                f"{self._md(', '.join(agent['allowed_tools']))} | {self._md(', '.join(agent['blocked_tools']))} |"
            )
        lines.extend(["", "## Transcript", ""])
        for message in council["conversation"]:
            lines.append(
                f"{message['turn']}. **{self._md(message['role'])}** ({message['message_type']}): "
                f"{self._md(message['content'])}"
            )
            if message["governance_flags"]:
                lines.append(f"   - Flags: {self._md(', '.join(message['governance_flags']))}")
            if message["handoff_to"]:
                lines.append(f"   - Handoff: {self._md(message['handoff_to'])}")
        lines.extend(["", "## Handoffs", ""])
        if council["handoffs"]:
            lines.append("| From | To | Status | Required before | Reason |")
            lines.append("| --- | --- | --- | --- | --- |")
            for handoff in council["handoffs"]:
                lines.append(
                    f"| {handoff['from_agent_id']} | {handoff['to_agent_id']} | {handoff['status']} | "
                    f"{self._md(handoff['required_before'])} | {self._md(handoff['reason'])} |"
                )
        else:
            lines.append("- No open council handoffs.")
        lines.extend(["", "## Tool Governance", ""])
        for row in council["tool_governance"]:
            lines.append(f"- {row['agent_id']} ({row['policy']}): blocked={self._md(', '.join(row['blocked_tools']))}")
        lines.extend(["", "## Budget Ledger", ""])
        for key, value in council["budget_ledger"].items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Eval Scenarios", ""])
        for scenario in council["eval_scenarios"]:
            result = "pass" if scenario["passed"] else "fail"
            lines.append(f"- {scenario['scenario_id']} ({result}): {scenario['assertion']}")
        lines.extend(["", "## Reviewer Controls", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_controls"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in council["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {self._md(item)}" for item in council["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Generated Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _recommended_posture(self, workflow: BuyerIntelligenceWorkflowResponse, approvals: int) -> str:
        if workflow.workflow_status == "blocked":
            return "do_not_submit_until_governance_clears"
        if approvals:
            return "conditional_response_with_named_human_handoffs"
        return "advance_to_executive_review"

    def _required_before(self, message_type: str) -> str:
        return {
            "evidence_review": "final citation reuse",
            "governance_review": "provider change or executive memo",
            "buyer_qa_review": "buyer Q&A submission",
            "commercial_review": "pricing and terms response",
        }.get(message_type, "final response submission")

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {"method": "GET", "path": "/proposal/agent-council", "purpose": "View governed agent council."},
            {"method": "POST", "path": "/proposal/agent-council-pack", "purpose": "Write council artifacts."},
            {
                "method": "GET",
                "path": "/proposal/buyer-intelligence",
                "purpose": "Source durable workflow state.",
            },
            {"method": "GET", "path": "/ops/cost-governance", "purpose": "Source provider and budget controls."},
            {
                "method": "GET",
                "path": "/procurement/question-risk",
                "purpose": "Source buyer Q&A approval signals.",
            },
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/proposal/agent-council" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/proposal/agent-council-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'rg "proposal/agent-council|Proposal Agent Council|agent_council" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\agent_council -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Council turns are deterministic local workflow analysis, not autonomous LLM conversations.",
            "Tool calls are governed intent records; they do not execute external systems or submit proposals.",
            "Open handoffs require human confirmation outside this local artifact.",
            "Token and cost estimates are planning controls and do not represent live provider billing.",
            "OpenAI and Azure OpenAI remain optional and are blocked by governance until configured and approved.",
        ]

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower() or "local"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
