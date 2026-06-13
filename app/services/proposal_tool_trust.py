from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    CostGovernanceResponse,
    ProposalAgentCouncilResponse,
    ProposalToolTrustPackResponse,
    ProposalToolTrustResponse,
)


class ProposalToolTrustService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def registry(
        self,
        trace_id: str,
        council: ProposalAgentCouncilResponse,
        cost_governance: CostGovernanceResponse,
    ) -> ProposalToolTrustResponse:
        trust_registry = self._trust_registry(council)
        tool_risk_matrix = self._tool_risk_matrix(trust_registry, council)
        agent_policy_rollups = self._agent_policy_rollups(council, trust_registry)
        human_queue = self._human_approval_queue(tool_risk_matrix, council)
        provider_constraints = self._provider_constraints(cost_governance, trust_registry)
        budget_guardrails = self._budget_guardrails(council, cost_governance)
        shared_state_policy = self._shared_state_policy(council)
        eval_assertions = self._eval_assertions(
            trust_registry,
            tool_risk_matrix,
            agent_policy_rollups,
            provider_constraints,
            budget_guardrails,
        )
        return ProposalToolTrustResponse(
            title="Proposal Tool Trust Registry",
            status=self._status(tool_risk_matrix, human_queue, provider_constraints),
            generated_at=datetime.now(UTC).isoformat(),
            registry_id=f"tool-trust-{self._slug(trace_id)}",
            trust_registry=trust_registry,
            tool_risk_matrix=tool_risk_matrix,
            agent_policy_rollups=agent_policy_rollups,
            provider_constraints=provider_constraints,
            budget_guardrails=budget_guardrails,
            shared_state_policy=shared_state_policy,
            human_approval_queue=human_queue,
            eval_assertions=eval_assertions,
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        registry: ProposalToolTrustResponse,
        write_artifact: bool = True,
    ) -> ProposalToolTrustPackResponse:
        pack = self._pack_payload(trace_id, registry)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "tool_trust"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = self._slug(trace_id)
            markdown_path = pack_dir / f"proposal_tool_trust_{safe_trace_id}.md"
            json_path = pack_dir / f"proposal_tool_trust_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["tool_trust_markdown"] = artifact_path
            pack["artifact_paths"]["tool_trust_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return ProposalToolTrustPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            registry=registry,
            trace_id=trace_id,
        )

    def _trust_registry(self, council: ProposalAgentCouncilResponse) -> list[dict[str, Any]]:
        tool_agents: dict[str, set[str]] = defaultdict(set)
        tool_sources: dict[str, set[str]] = defaultdict(set)
        for agent in council.agents:
            for tool in agent.allowed_tools:
                tool_agents[tool].add(agent.agent_id)
                tool_sources[tool].add("agent_allowed_tools")
            for tool in agent.blocked_tools:
                tool_agents[tool].add(agent.agent_id)
                tool_sources[tool].add("agent_blocked_tools")
        for row in council.tool_governance:
            for tool in row.get("allowed_tools", []):
                tool_agents[tool].add(str(row.get("agent_id", "global")))
                tool_sources[tool].add("tool_governance_allowed")
            for tool in row.get("blocked_tools", []):
                tool_agents[tool].add(str(row.get("agent_id", "global")))
                tool_sources[tool].add("tool_governance_blocked")

        rows = []
        for tool_id in sorted(tool_agents):
            tier = self._trust_tier(tool_id, tool_sources[tool_id])
            rows.append(
                {
                    "tool_id": tool_id,
                    "trust_tier": tier,
                    "default_decision": self._default_decision(tier),
                    "allowed_agent_ids": sorted(tool_agents[tool_id]),
                    "source_policies": sorted(tool_sources[tool_id]),
                    "provider_boundary": self._provider_boundary(tool_id),
                    "requires_human_approval": tier in {"restricted", "blocked"},
                    "audit_event": f"tool_trust.{tool_id}.{tier}",
                }
            )
        return rows

    def _tool_risk_matrix(
        self,
        registry: list[dict[str, Any]],
        council: ProposalAgentCouncilResponse,
    ) -> list[dict[str, Any]]:
        blocked_by_agent = {
            agent.agent_id: set(agent.blocked_tools)
            for agent in council.agents
        }
        rows = []
        for item in registry:
            blocked_count = sum(item["tool_id"] in blocked for blocked in blocked_by_agent.values())
            risk_score = self._risk_score(item["trust_tier"], blocked_count, item["provider_boundary"])
            rows.append(
                {
                    "tool_id": item["tool_id"],
                    "trust_tier": item["trust_tier"],
                    "risk_score": risk_score,
                    "risk_level": self._risk_level(risk_score),
                    "blocked_by_agent_count": blocked_count,
                    "requires_human_approval": item["requires_human_approval"],
                    "control": self._control_for_tier(item["trust_tier"]),
                    "reviewer_role": self._reviewer_for_tool(item["tool_id"]),
                }
            )
        return rows

    def _agent_policy_rollups(
        self,
        council: ProposalAgentCouncilResponse,
        registry: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        registry_by_tool = {item["tool_id"]: item for item in registry}
        rows = []
        for agent in council.agents:
            allowed = [registry_by_tool[tool] for tool in agent.allowed_tools if tool in registry_by_tool]
            restricted_allowed = [tool for tool in allowed if tool["trust_tier"] in {"restricted", "blocked"}]
            rows.append(
                {
                    "agent_id": agent.agent_id,
                    "role": agent.role,
                    "allowed_tool_count": len(agent.allowed_tools),
                    "blocked_tool_count": len(agent.blocked_tools),
                    "restricted_allowed_count": len(restricted_allowed),
                    "policy_status": "needs_review" if restricted_allowed else "pass",
                    "max_budget_tokens": agent.budget_tokens,
                    "approval_scope": agent.approval_scope,
                }
            )
        return rows

    def _human_approval_queue(
        self,
        risk_matrix: list[dict[str, Any]],
        council: ProposalAgentCouncilResponse,
    ) -> list[dict[str, Any]]:
        queue = []
        handoff_refs = [handoff.handoff_id for handoff in council.handoffs if handoff.status == "open"]
        for row in risk_matrix:
            if not row["requires_human_approval"]:
                continue
            queue.append(
                {
                    "approval_id": f"tool-approval-{self._slug(row['tool_id'])}",
                    "tool_id": row["tool_id"],
                    "reviewer_role": row["reviewer_role"],
                    "priority": "critical" if row["risk_level"] == "critical" else "high",
                    "status": "requires_approval" if row["trust_tier"] != "blocked" else "blocked",
                    "required_before": "external provider use or final proposal submission",
                    "handoff_refs": handoff_refs[:4],
                    "control": row["control"],
                }
            )
        return queue

    def _provider_constraints(
        self,
        cost_governance: CostGovernanceResponse,
        registry: list[dict[str, Any]],
    ) -> dict[str, Any]:
        readiness = cost_governance.provider_readiness
        external_tools = [
            item["tool_id"]
            for item in registry
            if item["provider_boundary"] == "external_provider_or_submission"
        ]
        return {
            "active_provider_mode": readiness["provider_mode"],
            "local_mock_default": readiness["local_mock_ready"],
            "external_provider_requested": readiness["external_provider_requested"],
            "external_provider_tools": external_tools,
            "blocked_until_governance": bool(external_tools),
            "allowed_provider_modes": ["mock", "openai", "azure_openai"],
            "required_gate": "model_risk_and_cost_governance_review",
        }

    def _budget_guardrails(
        self,
        council: ProposalAgentCouncilResponse,
        cost_governance: CostGovernanceResponse,
    ) -> dict[str, Any]:
        budget = council.budget_ledger
        daily_budget = cost_governance.budget_summary["daily_budget_usd"]
        estimated_cost = float(budget["estimated_cost"])
        return {
            "council_token_estimate": budget["total_token_estimate"],
            "tokens_by_agent": budget["tokens_by_agent"],
            "estimated_cost": estimated_cost,
            "daily_budget_usd": daily_budget,
            "budget_utilization": round(estimated_cost / daily_budget, 6) if daily_budget else 0.0,
            "max_single_agent_share": self._max_agent_share(budget["tokens_by_agent"]),
            "decision": "pass" if estimated_cost <= daily_budget else "needs_review",
        }

    def _shared_state_policy(self, council: ProposalAgentCouncilResponse) -> dict[str, Any]:
        state = council.shared_state
        return {
            "workflow_id": state.get("workflow_id"),
            "state_policy": state.get("state_policy"),
            "append_only": str(state.get("state_policy", "")).startswith("append-only"),
            "governance_gate_count": state.get("governance_gate_count", 0),
            "source_trust_status": state.get("source_trust_status"),
            "procurement_status": state.get("procurement_status"),
            "mutation_policy": "read_only_tool_registry_until_human_approval",
        }

    def _eval_assertions(
        self,
        registry: list[dict[str, Any]],
        risk_matrix: list[dict[str, Any]],
        agent_rollups: list[dict[str, Any]],
        provider_constraints: dict[str, Any],
        budget_guardrails: dict[str, Any],
    ) -> list[dict[str, Any]]:
        tool_ids = {item["tool_id"] for item in registry}
        matrix_ids = {item["tool_id"] for item in risk_matrix}
        return [
            {
                "assertion_id": "tool-trust-all-tools-scored",
                "assertion": "every governed tool has a risk matrix row",
                "expected": sorted(tool_ids),
                "observed": sorted(matrix_ids),
                "passed": tool_ids == matrix_ids,
            },
            {
                "assertion_id": "tool-trust-blocks-external-provider",
                "assertion": "external provider tools are blocked until governance review",
                "expected": "blocked_until_governance",
                "observed": provider_constraints["blocked_until_governance"],
                "passed": provider_constraints["blocked_until_governance"],
            },
            {
                "assertion_id": "tool-trust-agent-rollups-covered",
                "assertion": "agent policy rollups cover the full proposal council",
                "expected": 5,
                "observed": len(agent_rollups),
                "passed": len(agent_rollups) >= 5,
            },
            {
                "assertion_id": "tool-trust-budget-guardrail",
                "assertion": "local council estimate stays within configured budget",
                "expected": "pass",
                "observed": budget_guardrails["decision"],
                "passed": budget_guardrails["decision"] == "pass",
            },
        ]

    def _pack_payload(self, trace_id: str, registry: ProposalToolTrustResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Proposal Tool Trust Registry Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "registry": registry.model_dump(mode="json"),
            "reviewer_controls": [
                "Treat blocked tools as unavailable until a named owner approves the policy change.",
                "Keep provider mode on mock unless model-risk, privacy, and cost gates explicitly pass.",
                "Use the registry to review council tool intent; it does not execute external actions.",
                "Regenerate after changing agent roles, provider mode, model-risk policy, or approval gates.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        registry = pack["registry"]
        lines = [
            "# Proposal Tool Trust Registry Pack",
            "",
            "## Summary",
            "",
            f"- Status: {registry['status']}",
            f"- Registry ID: {registry['registry_id']}",
            f"- Tools: {len(registry['trust_registry'])}",
            f"- Approval items: {len(registry['human_approval_queue'])}",
            f"- Provider mode: {registry['provider_constraints']['active_provider_mode']}",
            "",
            "## Tool Registry",
            "",
            "| Tool | Trust tier | Decision | Provider boundary | Human approval |",
            "| --- | --- | --- | --- | --- |",
        ]
        for item in registry["trust_registry"]:
            lines.append(
                f"| {item['tool_id']} | {item['trust_tier']} | {item['default_decision']} | "
                f"{item['provider_boundary']} | {item['requires_human_approval']} |"
            )
        lines.extend(["", "## Risk Matrix", ""])
        lines.append("| Tool | Risk | Score | Reviewer | Control |")
        lines.append("| --- | --- | ---: | --- | --- |")
        for row in registry["tool_risk_matrix"]:
            lines.append(
                f"| {row['tool_id']} | {row['risk_level']} | {row['risk_score']} | "
                f"{row['reviewer_role']} | {self._md(row['control'])} |"
            )
        lines.extend(["", "## Agent Rollups", ""])
        for row in registry["agent_policy_rollups"]:
            lines.append(
                f"- {row['agent_id']} ({row['policy_status']}): allowed={row['allowed_tool_count']}, "
                f"blocked={row['blocked_tool_count']}, restricted_allowed={row['restricted_allowed_count']}"
            )
        lines.extend(["", "## Provider Constraints", ""])
        for key, value in registry["provider_constraints"].items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Budget Guardrails", ""])
        for key, value in registry["budget_guardrails"].items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Human Approval Queue", ""])
        if registry["human_approval_queue"]:
            for item in registry["human_approval_queue"]:
                lines.append(f"- {item['approval_id']} ({item['status']}): {self._md(item['control'])}")
        else:
            lines.append("- No tool approvals are currently required.")
        lines.extend(["", "## Eval Assertions", ""])
        for assertion in registry["eval_assertions"]:
            result = "pass" if assertion["passed"] else "fail"
            lines.append(f"- {assertion['assertion_id']} ({result}): {assertion['assertion']}")
        lines.extend(["", "## Reviewer Controls", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_controls"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in registry["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {self._md(item)}" for item in registry["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Generated Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _trust_tier(self, tool_id: str, sources: set[str]) -> str:
        if "blocked" in tool_id or "without" in tool_id or "submit_" in tool_id or "bypass" in tool_id:
            return "blocked"
        if "external_provider" in tool_id or "final" in tool_id or "custom_terms" in tool_id:
            return "restricted"
        if "pricing" in tool_id or "exception" in tool_id or "model_risk" in tool_id:
            return "controlled"
        if any(source.endswith("blocked") for source in sources):
            return "restricted"
        return "trusted"

    def _default_decision(self, tier: str) -> str:
        return {
            "trusted": "allow_read_only",
            "controlled": "allow_with_audit",
            "restricted": "human_approval_required",
            "blocked": "deny",
        }[tier]

    def _provider_boundary(self, tool_id: str) -> str:
        if "external_provider" in tool_id or "submit" in tool_id:
            return "external_provider_or_submission"
        return "local_control_plane"

    def _risk_score(self, tier: str, blocked_count: int, provider_boundary: str) -> int:
        base = {"trusted": 20, "controlled": 45, "restricted": 70, "blocked": 90}[tier]
        provider_weight = 10 if provider_boundary == "external_provider_or_submission" else 0
        return min(100, base + blocked_count * 4 + provider_weight)

    def _risk_level(self, score: int) -> str:
        if score >= 90:
            return "critical"
        if score >= 70:
            return "high"
        if score >= 45:
            return "medium"
        return "low"

    def _control_for_tier(self, tier: str) -> str:
        return {
            "trusted": "Allow read-only local execution with audit event capture.",
            "controlled": "Allow only with trace ID, source references, and role-scoped owner review.",
            "restricted": "Require named human approval before use in a customer-facing workflow.",
            "blocked": "Deny by default; unblock only through governance exception review.",
        }[tier]

    def _reviewer_for_tool(self, tool_id: str) -> str:
        if "pricing" in tool_id or "commercial" in tool_id:
            return "Sales Lead"
        if "source" in tool_id or "citation" in tool_id or "uncited" in tool_id:
            return "Compliance Reviewer"
        if "custom_terms" in tool_id or "legal" in tool_id or "procurement" in tool_id:
            return "Procurement Lead"
        if "external_provider" in tool_id or "model" in tool_id:
            return "AI Governance Reviewer"
        return "Proposal Manager"

    def _status(
        self,
        risk_matrix: list[dict[str, Any]],
        human_queue: list[dict[str, Any]],
        provider_constraints: dict[str, Any],
    ) -> str:
        if any(row["risk_level"] == "critical" for row in risk_matrix):
            return "blocked_tools_present"
        if human_queue or provider_constraints["blocked_until_governance"]:
            return "needs_tool_owner_review"
        return "pass"

    def _max_agent_share(self, tokens_by_agent: dict[str, int]) -> float:
        total = sum(tokens_by_agent.values())
        if not total:
            return 0.0
        return round(max(tokens_by_agent.values()) / total, 4)

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {"method": "GET", "path": "/proposal/tool-trust-registry", "purpose": "View tool trust controls."},
            {"method": "POST", "path": "/proposal/tool-trust-pack", "purpose": "Write tool trust artifacts."},
            {"method": "GET", "path": "/proposal/agent-council", "purpose": "Source council tool policy."},
            {"method": "GET", "path": "/ops/cost-governance", "purpose": "Source provider and budget controls."},
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/proposal/tool-trust-registry" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/proposal/tool-trust-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'rg "tool-trust|Tool Trust|tool_trust" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\tool_trust -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Registry entries are deterministic local governance records derived from council policy.",
            "Tools are not executed; this pack audits intended access, trust tier, owner route, and budget impact.",
            "Provider constraints keep OpenAI and Azure OpenAI optional and blocked until local governance clears.",
            "Human approval queue is a local artifact and needs a ticketing or GRC system for production routing.",
        ]

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower() or "local"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
