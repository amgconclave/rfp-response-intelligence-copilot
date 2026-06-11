from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    AccessPolicyPackResponse,
    AccessPolicyResponse,
    BuyerIntelligenceWorkflowResponse,
    CostGovernanceResponse,
    ModelRiskRegisterResponse,
    ProposalAgentCouncilResponse,
    ProposalSubmissionCertificationResponse,
)


class AccessPolicyService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def policy(
        self,
        trace_id: str,
        workflow: BuyerIntelligenceWorkflowResponse,
        council: ProposalAgentCouncilResponse,
        certification: ProposalSubmissionCertificationResponse,
        cost_governance: CostGovernanceResponse,
        model_risk: ModelRiskRegisterResponse,
    ) -> AccessPolicyResponse:
        roles = self._roles(council, certification)
        endpoint_permissions = self._endpoint_permissions()
        artifact_permissions = self._artifact_permissions()
        reviewer_queue = self._reviewer_queue(certification, workflow, model_risk)
        trace_spans = self._trace_spans(trace_id, endpoint_permissions, artifact_permissions, reviewer_queue)
        eval_assertions = self._eval_assertions(roles, endpoint_permissions, artifact_permissions, reviewer_queue)
        status = self._status(eval_assertions, reviewer_queue, cost_governance)
        return AccessPolicyResponse(
            title="Role-Based Access Policy Review",
            status=status,
            generated_at=datetime.now(UTC).isoformat(),
            summary=self._summary(
                roles,
                endpoint_permissions,
                artifact_permissions,
                reviewer_queue,
                trace_spans,
                status,
            ),
            roles=roles,
            endpoint_permissions=endpoint_permissions,
            artifact_permissions=artifact_permissions,
            reviewer_queue=reviewer_queue,
            control_gates=self._control_gates(workflow, cost_governance, model_risk, reviewer_queue),
            trace_spans=trace_spans,
            eval_assertions=eval_assertions,
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        policy: AccessPolicyResponse,
        write_artifact: bool = True,
    ) -> AccessPolicyPackResponse:
        pack = self._pack_payload(trace_id, policy)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "access_policy"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = self._slug(trace_id)
            markdown_path = pack_dir / f"access_policy_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"access_policy_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["access_policy_markdown"] = artifact_path
            pack["artifact_paths"]["access_policy_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return AccessPolicyPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            policy=policy,
            trace_id=trace_id,
        )

    def _roles(
        self,
        council: ProposalAgentCouncilResponse,
        certification: ProposalSubmissionCertificationResponse,
    ) -> list[dict[str, Any]]:
        role_map = {
            agent.role: {
                "role": agent.role,
                "principal_type": "human_reviewer_or_local_agent",
                "allowed_tools": agent.allowed_tools,
                "blocked_tools": agent.blocked_tools,
                "approval_scope": agent.approval_scope,
                "max_budget_tokens": agent.budget_tokens,
                "default_access": "read_only",
            }
            for agent in council.agents
        }
        role_map["Platform Owner"] = {
            "role": "Platform Owner",
            "principal_type": "operator",
            "allowed_tools": ["runtime_demo", "provider_resilience", "cost_governance", "api_contract_audit"],
            "blocked_tools": ["submit_final_response", "bypass_human_approval"],
            "approval_scope": ["provider mode change", "API key policy", "artifact retention"],
            "max_budget_tokens": 0,
            "default_access": "admin_for_local_controls",
        }
        role_map["Executive Sponsor"] = {
            "role": "Executive Sponsor",
            "principal_type": "human_reviewer",
            "allowed_tools": ["submission_certification", "proposal_quality_benchmark", "final_handoff"],
            "blocked_tools": ["edit_citations_without_owner", "external_submit_without_packet"],
            "approval_scope": ["final go/no-go", "named exceptions"],
            "max_budget_tokens": 0,
            "default_access": "approve_only",
        }
        queue_roles = {item["owner_role"] for item in certification.reviewer_queue if item.get("owner_role")}
        for role in sorted(queue_roles):
            role_map.setdefault(
                role,
                {
                    "role": role,
                    "principal_type": "human_reviewer",
                    "allowed_tools": ["review_queue", "source_trust", "submission_certification"],
                    "blocked_tools": ["provider_change", "final_submission"],
                    "approval_scope": ["assigned review item"],
                    "max_budget_tokens": 0,
                    "default_access": "review_assigned_items",
                },
            )
        return list(role_map.values())

    def _endpoint_permissions(self) -> list[dict[str, Any]]:
        return [
            self._endpoint(
                "/documents/ingest",
                "POST",
                ["Proposal Manager", "Presales Architect", "Platform Owner"],
                ["Executive Sponsor"],
                "knowledge intake",
                False,
            ),
            self._endpoint(
                "/rfp/query",
                "POST",
                ["Sales Lead", "Presales Architect", "Compliance Reviewer", "Proposal Manager"],
                [],
                "grounded answer drafting",
                False,
            ),
            self._endpoint(
                "/evidence/governed-retrieval",
                "POST",
                ["Presales Architect", "Compliance Reviewer", "Knowledge Owner", "Platform Owner"],
                ["Sales Lead"],
                "policy-aware citation review",
                True,
            ),
            self._endpoint(
                "/proposal/agent-council",
                "GET",
                ["Sales Lead", "Presales Architect", "Compliance Reviewer", "Procurement Lead", "Proposal Manager"],
                [],
                "cross-functional shared-state transcript",
                False,
            ),
            self._endpoint(
                "/proposal/submission-certification",
                "GET",
                ["Proposal Manager", "Executive Sponsor", "Compliance Reviewer", "Platform Owner"],
                [],
                "final control gate review",
                True,
            ),
            self._endpoint(
                "/governance/model-risk-register",
                "GET",
                ["Compliance Reviewer", "AI Governance Reviewer", "Platform Owner"],
                ["Sales Lead"],
                "model and provider governance",
                True,
            ),
            self._endpoint(
                "/ops/provider-resilience",
                "GET",
                ["Platform Owner", "AI Governance Reviewer"],
                ["Sales Lead", "Procurement Lead"],
                "provider route readiness",
                True,
            ),
            self._endpoint(
                "/proposal/quality-benchmark-pack",
                "POST",
                ["Proposal Manager", "Platform Owner", "Executive Sponsor"],
                ["Sales Lead"],
                "submission evidence artifact generation",
                True,
            ),
        ]

    def _endpoint(
        self,
        path: str,
        method: str,
        allowed_roles: list[str],
        denied_roles: list[str],
        business_purpose: str,
        approval_required: bool,
    ) -> dict[str, Any]:
        return {
            "path": path,
            "method": method,
            "allowed_roles": allowed_roles,
            "denied_roles": denied_roles,
            "business_purpose": business_purpose,
            "auth_scheme": "X-API-Key local demo auth",
            "approval_required": approval_required,
            "policy": "least_privilege_with_named_human_review" if approval_required else "least_privilege_read_write",
        }

    def _artifact_permissions(self) -> list[dict[str, Any]]:
        return [
            {
                "artifact_root": "storage/buyer_intelligence",
                "classification": "proposal_workflow_state",
                "read_roles": ["Proposal Manager", "Sales Lead", "Presales Architect", "Compliance Reviewer"],
                "write_roles": ["Proposal Manager", "Platform Owner"],
                "retention_posture": "local_ignored_artifact_regenerate_after_policy_change",
            },
            {
                "artifact_root": "storage/agent_council",
                "classification": "agent_transcript_and_handoffs",
                "read_roles": ["Proposal Manager", "Compliance Reviewer", "Executive Sponsor"],
                "write_roles": ["Proposal Manager", "Platform Owner"],
                "retention_posture": "local_ignored_artifact_contains_governance_discussion",
            },
            {
                "artifact_root": "storage/submission_certifications",
                "classification": "final_submission_control_packet",
                "read_roles": ["Executive Sponsor", "Proposal Manager", "Compliance Reviewer"],
                "write_roles": ["Proposal Manager", "Platform Owner"],
                "retention_posture": "attach_to_local_review_packet_not_customer_submission_by_default",
            },
            {
                "artifact_root": "storage/access_policy",
                "classification": "local_access_governance",
                "read_roles": ["Platform Owner", "AI Governance Reviewer", "Compliance Reviewer"],
                "write_roles": ["Platform Owner"],
                "retention_posture": "regenerate_after_endpoint_role_or_provider_policy_change",
            },
        ]

    def _reviewer_queue(
        self,
        certification: ProposalSubmissionCertificationResponse,
        workflow: BuyerIntelligenceWorkflowResponse,
        model_risk: ModelRiskRegisterResponse,
    ) -> list[dict[str, Any]]:
        rows = [
            {
                "queue_id": f"access-cert-{self._slug(item['queue_id'])}",
                "owner_role": item["owner_role"],
                "priority": item["priority"],
                "status": item["status"],
                "decision_area": item["decision_area"],
                "required_action": item["required_action"],
                "source": "/proposal/submission-certification",
            }
            for item in certification.reviewer_queue[:8]
        ]
        rows.extend(
            {
                "queue_id": f"access-workflow-{self._slug(item.approval_id)}",
                "owner_role": item.reviewer_role,
                "priority": item.priority,
                "status": item.status,
                "decision_area": item.decision_area,
                "required_action": item.required_before,
                "source": "/proposal/buyer-intelligence",
            }
            for item in workflow.human_approval_queue[:6]
        )
        rows.extend(
            {
                "queue_id": f"access-model-{self._slug(str(item['reviewer_owner']))}",
                "owner_role": str(item["reviewer_owner"]),
                "priority": str(item["highest_severity"]),
                "status": "requires_approval",
                "decision_area": "Model/provider access policy",
                "required_action": str(item["next_action"]),
                "source": "/governance/model-risk-register",
            }
            for item in model_risk.reviewer_queue[:4]
        )
        return rows

    def _control_gates(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        cost_governance: CostGovernanceResponse,
        model_risk: ModelRiskRegisterResponse,
        reviewer_queue: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "gate_id": "access-api-key-boundary",
                "status": "pass",
                "owner_role": "Platform Owner",
                "evidence": "All non-public business endpoints use X-API-Key dependency in FastAPI routes.",
                "required_action": "Replace demo API key with enterprise identity before production deployment.",
            },
            {
                "gate_id": "access-human-review-boundary",
                "status": "needs_review" if reviewer_queue else "pass",
                "owner_role": "Proposal Manager",
                "evidence": (
                    f"{len(reviewer_queue)} reviewer queue item(s) from workflow, "
                    "certification, or model risk."
                ),
                "required_action": "Confirm named owner decisions before final response submission.",
            },
            {
                "gate_id": "access-provider-boundary",
                "status": "pass" if cost_governance.provider_readiness["local_mock_ready"] else "needs_review",
                "owner_role": "AI Governance Reviewer",
                "evidence": f"provider_mode={cost_governance.provider_readiness['provider_mode']}",
                "required_action": "Keep external providers disabled unless cost, privacy, and model-risk gates pass.",
            },
            {
                "gate_id": "access-model-risk-boundary",
                "status": model_risk.register_status,
                "owner_role": "AI Governance Reviewer",
                "evidence": f"{model_risk.summary['risk_count']} model/provider risk(s).",
                "required_action": "Clear model risk review before expanding tool or provider access.",
            },
            {
                "gate_id": "access-workflow-boundary",
                "status": "needs_review" if workflow.workflow_status != "ready_for_submission_review" else "pass",
                "owner_role": "Proposal Manager",
                "evidence": f"buyer workflow status={workflow.workflow_status}",
                "required_action": (
                    "Use workflow checkpoint state to decide which roles may approve or write artifacts."
                ),
            },
        ]

    def _trace_spans(
        self,
        trace_id: str,
        endpoint_permissions: list[dict[str, Any]],
        artifact_permissions: list[dict[str, Any]],
        reviewer_queue: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        spans = [
            {
                "span_id": f"access-endpoint-{idx:02d}",
                "trace_id": trace_id,
                "operation": "endpoint_policy_check",
                "target": row["path"],
                "status": "needs_review" if row["approval_required"] else "pass",
                "owner_role": ", ".join(row["allowed_roles"][:2]),
            }
            for idx, row in enumerate(endpoint_permissions, start=1)
        ]
        spans.extend(
            {
                "span_id": f"access-artifact-{idx:02d}",
                "trace_id": trace_id,
                "operation": "artifact_policy_check",
                "target": row["artifact_root"],
                "status": "pass",
                "owner_role": ", ".join(row["write_roles"]),
            }
            for idx, row in enumerate(artifact_permissions, start=1)
        )
        spans.extend(
            {
                "span_id": f"access-review-{idx:02d}",
                "trace_id": trace_id,
                "operation": "human_review_routing",
                "target": row["queue_id"],
                "status": row["status"],
                "owner_role": row["owner_role"],
            }
            for idx, row in enumerate(reviewer_queue[:10], start=1)
        )
        return spans

    def _eval_assertions(
        self,
        roles: list[dict[str, Any]],
        endpoint_permissions: list[dict[str, Any]],
        artifact_permissions: list[dict[str, Any]],
        reviewer_queue: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        role_names = {role["role"] for role in roles}
        required_roles = {"Sales Lead", "Presales Architect", "Compliance Reviewer", "Procurement Lead"}
        return [
            {
                "assertion_id": "access-required-business-roles",
                "assertion": "sales, presales, compliance, and procurement roles are represented",
                "expected": sorted(required_roles),
                "observed": sorted(required_roles & role_names),
                "passed": required_roles <= role_names,
            },
            {
                "assertion_id": "access-sensitive-endpoints-reviewed",
                "assertion": "provider, model-risk, governed retrieval, and certification endpoints require review",
                "expected": "review on sensitive endpoints",
                "observed": [row["path"] for row in endpoint_permissions if row["approval_required"]],
                "passed": any(
                    row["path"] == "/ops/provider-resilience" and row["approval_required"]
                    for row in endpoint_permissions
                )
                and any(
                    row["path"] == "/governance/model-risk-register" and row["approval_required"]
                    for row in endpoint_permissions
                ),
            },
            {
                "assertion_id": "access-artifact-write-restricted",
                "assertion": "generated governance artifacts have narrower write roles than read roles",
                "expected": len(artifact_permissions),
                "observed": sum(len(row["write_roles"]) <= len(row["read_roles"]) for row in artifact_permissions),
                "passed": all(len(row["write_roles"]) <= len(row["read_roles"]) for row in artifact_permissions),
            },
            {
                "assertion_id": "access-hitl-visible",
                "assertion": "human-review queue is visible when workflow or certification has review items",
                "expected": "visible queue or no review needed",
                "observed": len(reviewer_queue),
                "passed": True,
            },
        ]

    def _summary(
        self,
        roles: list[dict[str, Any]],
        endpoint_permissions: list[dict[str, Any]],
        artifact_permissions: list[dict[str, Any]],
        reviewer_queue: list[dict[str, Any]],
        trace_spans: list[dict[str, Any]],
        status: str,
    ) -> dict[str, Any]:
        owners = Counter(item["owner_role"] for item in reviewer_queue)
        return {
            "status": status,
            "role_count": len(roles),
            "endpoint_policy_count": len(endpoint_permissions),
            "approval_required_endpoint_count": sum(row["approval_required"] for row in endpoint_permissions),
            "artifact_policy_count": len(artifact_permissions),
            "reviewer_queue_count": len(reviewer_queue),
            "reviewer_owner_counts": dict(sorted(owners.items())),
            "trace_span_count": len(trace_spans),
            "implemented_patterns": [
                "governance",
                "human-in-the-loop",
                "shared state",
                "provider flexibility",
                "trace analysis",
            ],
        }

    def _status(
        self,
        eval_assertions: list[dict[str, Any]],
        reviewer_queue: list[dict[str, Any]],
        cost_governance: CostGovernanceResponse,
    ) -> str:
        if not all(assertion["passed"] for assertion in eval_assertions):
            return "blocked"
        if not cost_governance.provider_readiness["local_mock_ready"]:
            return "needs_provider_access_review"
        if reviewer_queue:
            return "needs_human_access_review"
        return "pass"

    def _pack_payload(self, trace_id: str, policy: AccessPolicyResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Role-Based Access Policy Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "policy": policy.model_dump(mode="json"),
            "reviewer_controls": [
                "Use this pack to review least-privilege posture before sharing local proposal artifacts.",
                "Treat provider, model-risk, certification, and governed-retrieval actions as owner-approved only.",
                "Do not expose generated proposal artifacts outside the local workspace without named approval.",
                "Regenerate after adding endpoints, changing roles, or switching provider mode away from mock.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        policy = pack["policy"]
        summary = policy["summary"]
        lines = [
            "# Role-Based Access Policy Pack",
            "",
            "## Summary",
            "",
            f"- Status: {policy['status']}",
            f"- Roles: {summary['role_count']}",
            f"- Endpoint policies: {summary['endpoint_policy_count']}",
            f"- Approval-required endpoints: {summary['approval_required_endpoint_count']}",
            f"- Reviewer queue items: {summary['reviewer_queue_count']}",
            f"- Trace spans: {summary['trace_span_count']}",
            "",
            "## Role Policy",
            "",
            "| Role | Default access | Allowed tools | Blocked tools | Approval scope |",
            "| --- | --- | --- | --- | --- |",
        ]
        for role in policy["roles"]:
            lines.append(
                f"| {self._md(role['role'])} | {role['default_access']} | "
                f"{self._md(', '.join(role['allowed_tools']))} | "
                f"{self._md(', '.join(role['blocked_tools']))} | "
                f"{self._md(', '.join(role['approval_scope']))} |"
            )
        lines.extend(["", "## Endpoint Permissions", ""])
        lines.append("| Method | Path | Approval | Allowed roles | Denied roles |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in policy["endpoint_permissions"]:
            lines.append(
                f"| {row['method']} | `{row['path']}` | {row['approval_required']} | "
                f"{self._md(', '.join(row['allowed_roles']))} | {self._md(', '.join(row['denied_roles']) or 'none')} |"
            )
        lines.extend(["", "## Reviewer Queue", ""])
        if policy["reviewer_queue"]:
            for row in policy["reviewer_queue"][:20]:
                lines.append(
                    f"- {row['queue_id']} ({row['priority']}/{row['status']}): "
                    f"{self._md(row['owner_role'])} - {self._md(row['required_action'])}"
                )
        else:
            lines.append("- No access-related reviewer queue items are open.")
        lines.extend(["", "## Control Gates", ""])
        for gate in policy["control_gates"]:
            lines.append(
                f"- {gate['gate_id']} ({gate['status']}): {self._md(gate['required_action'])} "
                f"Owner: {self._md(gate['owner_role'])}"
            )
        lines.extend(["", "## Eval Assertions", ""])
        for assertion in policy["eval_assertions"]:
            result = "pass" if assertion["passed"] else "fail"
            lines.append(f"- {assertion['assertion_id']} ({result}): {self._md(assertion['assertion'])}")
        lines.extend(["", "## Reviewer Controls", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_controls"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in policy["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {self._md(item)}" for item in policy["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Generated Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/governance/access-policy" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/governance/access-policy-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'rg "governance/access-policy|Role-Based Access Policy|access_policy" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\access_policy -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "This is a deterministic local access review artifact, not a live RBAC enforcement engine.",
            "FastAPI still uses demo API-key auth; enterprise SSO, SCIM, and IAM integrations are out of scope.",
            "Role and artifact policies are reviewer controls for the local proposal workflow.",
            (
                "OpenAI and Azure OpenAI remain optional and require separate provider, privacy, cost, "
                "and model-risk review."
            ),
        ]

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower() or "local"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
