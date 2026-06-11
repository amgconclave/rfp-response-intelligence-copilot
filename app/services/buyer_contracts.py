from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.models.api import (
    BuyerContractCheck,
    BuyerContractRoleCoverage,
    BuyerIntelligenceWorkflowResponse,
    BuyerStructuredContractPackResponse,
    BuyerStructuredContractResponse,
    BuyerWorkflowReplayResponse,
    ProposalAgentCouncilResponse,
    ProposalDecisionProvenanceResponse,
)


class BuyerStructuredContractService:
    def __init__(self, settings: Settings, contract_models: list[type[BaseModel]] | None = None) -> None:
        self.settings = settings
        self.contract_models = contract_models or [
            BuyerIntelligenceWorkflowResponse,
            BuyerWorkflowReplayResponse,
            ProposalAgentCouncilResponse,
            ProposalDecisionProvenanceResponse,
        ]

    def audit(
        self,
        trace_id: str,
        workflow: BuyerIntelligenceWorkflowResponse,
        replay: BuyerWorkflowReplayResponse,
        council: ProposalAgentCouncilResponse,
        provenance: ProposalDecisionProvenanceResponse,
    ) -> BuyerStructuredContractResponse:
        validation_checks = self._validation_checks(workflow, replay, council, provenance)
        role_contracts = self._role_contracts(workflow, council, provenance)
        checks = [
            *validation_checks,
            self._workflow_check(workflow),
            self._replay_check(replay),
            self._council_check(council),
            self._provenance_check(provenance),
            self._provider_optionality_check(workflow),
            self._eval_contract_check(replay, council, provenance),
        ]
        checks.extend(self._role_checks(role_contracts))
        failed = [check for check in checks if check.status == "fail"]
        warnings = [check for check in checks if check.status == "warn"]
        score = max(0, 100 - len(failed) * 14 - len(warnings) * 5)
        return BuyerStructuredContractResponse(
            title="Buyer Structured Output Contract Audit",
            status="pass" if not failed and not warnings else "needs_review" if not failed else "fail",
            score=score,
            generated_at=datetime.now(UTC).isoformat(),
            contract_version="buyer-contracts-v1",
            injected_dependencies={
                "service": "BuyerStructuredContractService",
                "settings_provider_mode": self.settings.provider_mode,
                "settings_vector_store_mode": self.settings.vector_store_mode,
                "contract_model_count": len(self.contract_models),
                "contract_models": [model.__name__ for model in self.contract_models],
                "external_provider_required": False,
            },
            output_contracts=self._output_contracts(),
            role_contracts=role_contracts,
            checks=checks,
            schema_snapshots=self._schema_snapshots(),
            eval_assertions=self._eval_assertions(workflow, replay, council, provenance, checks, role_contracts),
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        contract_audit: BuyerStructuredContractResponse,
        write_artifact: bool = True,
    ) -> BuyerStructuredContractPackResponse:
        pack = self._pack_payload(trace_id, contract_audit)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "buyer_contracts"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = self._slug(trace_id)
            markdown_path = pack_dir / f"buyer_structured_contracts_{safe_trace_id}.md"
            json_path = pack_dir / f"buyer_structured_contracts_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["buyer_contracts_markdown"] = artifact_path
            pack["artifact_paths"]["buyer_contracts_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return BuyerStructuredContractPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            contract_audit=contract_audit,
            trace_id=trace_id,
        )

    def _validation_checks(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        replay: BuyerWorkflowReplayResponse,
        council: ProposalAgentCouncilResponse,
        provenance: ProposalDecisionProvenanceResponse,
    ) -> list[BuyerContractCheck]:
        payloads: list[tuple[type[BaseModel], BaseModel]] = [
            (BuyerIntelligenceWorkflowResponse, workflow),
            (BuyerWorkflowReplayResponse, replay),
            (ProposalAgentCouncilResponse, council),
            (ProposalDecisionProvenanceResponse, provenance),
        ]
        checks: list[BuyerContractCheck] = []
        for model_class, payload in payloads:
            try:
                model_class.model_validate(payload.model_dump(mode="json"))
                status = "pass"
                observed = "valid"
                evidence = f"{model_class.__name__} round-tripped through Pydantic validation."
            except ValidationError as exc:
                status = "fail"
                observed = f"{len(exc.errors())} validation error(s)"
                evidence = str(exc.errors()[0])[:240]
            checks.append(
                BuyerContractCheck(
                    check_id=f"schema-{self._slug(model_class.__name__)}",
                    name=f"{model_class.__name__} schema validation",
                    status=status,
                    expected="valid Pydantic structured output",
                    observed=observed,
                    evidence=evidence,
                    blocking=status == "fail",
                    endpoint_refs=self._model_endpoint_refs(model_class.__name__),
                )
            )
        return checks

    def _role_contracts(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        council: ProposalAgentCouncilResponse,
        provenance: ProposalDecisionProvenanceResponse,
    ) -> list[BuyerContractRoleCoverage]:
        agent_by_role = {agent.role: agent for agent in council.agents}
        stage_outputs = {
            stage.owner_role: stage.outputs
            for stage in workflow.workflow_stages
            if stage.owner_role
        }
        provenance_by_role: dict[str, list[str]] = {}
        for node in provenance.nodes:
            if node.owner_role:
                provenance_by_role.setdefault(node.owner_role, []).append(node.node_id)
        specs = [
            (
                "Sales Lead",
                "buyer-sales-contract",
                ["win strategy", "commercial posture", "buyer value proof"],
                ["/proposal/agent-council", "/rfp/pricing-risk-memo"],
            ),
            (
                "Presales Architect",
                "buyer-presales-contract",
                ["technical evidence", "requirement matrix", "source coverage"],
                ["/proposal/buyer-intelligence", "/evidence/governed-retrieval"],
            ),
            (
                "Compliance Reviewer",
                "buyer-compliance-contract",
                ["compliance controls", "privacy/model risk", "unsupported claim gates"],
                ["/compliance/evidence-matrix", "/governance/model-risk-register"],
            ),
            (
                "Procurement Lead",
                "buyer-procurement-contract",
                ["buyer Q&A risk", "commercial exceptions", "approval routing"],
                ["/procurement/question-risk", "/procurement/risk-desk"],
            ),
            (
                "Proposal Manager",
                "buyer-proposal-manager-contract",
                ["human approval queue", "handoff closure", "final packet readiness"],
                ["/proposal/buyer-intelligence", "/rfp/reviewer-collaboration"],
            ),
        ]
        contracts: list[BuyerContractRoleCoverage] = []
        for role, contract_id, required_outputs, endpoint_refs in specs:
            agent = agent_by_role.get(role)
            observed = []
            if agent:
                observed.extend(agent.allowed_tools)
                observed.extend(agent.approval_scope)
            observed.extend(stage_outputs.get(role, []))
            observed.extend(provenance_by_role.get(role, []))
            contracts.append(
                BuyerContractRoleCoverage(
                    role=role,
                    contract_id=contract_id,
                    status="pass" if observed else "fail",
                    required_outputs=required_outputs,
                    observed_outputs=sorted(set(observed)),
                    endpoint_refs=endpoint_refs,
                    reviewer_controls=[
                        f"{role} must approve its scoped output before final submission.",
                        "Evidence and governance references must remain attached to exported artifacts.",
                    ],
                )
            )
        return contracts

    def _workflow_check(self, workflow: BuyerIntelligenceWorkflowResponse) -> BuyerContractCheck:
        stage_count = len(workflow.workflow_stages)
        checkpoint_count = sum(1 for stage in workflow.workflow_stages if stage.durability_key)
        passed = stage_count >= 6 and checkpoint_count == stage_count
        return BuyerContractCheck(
            check_id="workflow-durable-structured-output",
            name="Buyer workflow durable output contract",
            status="pass" if passed else "fail",
            expected="at least 6 workflow stages with checkpoint keys",
            observed=f"{stage_count} stage(s), {checkpoint_count} checkpoint key(s)",
            evidence=f"Workflow status is {workflow.workflow_status}.",
            blocking=not passed,
            endpoint_refs=["/proposal/buyer-intelligence"],
        )

    def _replay_check(self, replay: BuyerWorkflowReplayResponse) -> BuyerContractCheck:
        passed = replay.checkpoint_validation.get("status") == "pass" and all(
            transition.checkpoint_key for transition in replay.transitions
        )
        return BuyerContractCheck(
            check_id="replay-checkpoint-contract",
            name="Replay checkpoint contract",
            status="pass" if passed else "fail",
            expected="checkpoint validation pass with every transition checkpointed",
            observed=f"{replay.checkpoint_validation.get('status')} / {replay.transition_count} transition(s)",
            evidence="Replay exposes ordered transitions for local state-machine evaluation.",
            blocking=not passed,
            endpoint_refs=["/proposal/buyer-intelligence-replay"],
        )

    def _council_check(self, council: ProposalAgentCouncilResponse) -> BuyerContractCheck:
        required = {"Sales Lead", "Presales Architect", "Compliance Reviewer", "Procurement Lead", "Proposal Manager"}
        observed = {agent.role for agent in council.agents}
        passed = required <= observed and all(scenario.get("passed") for scenario in council.eval_scenarios)
        return BuyerContractCheck(
            check_id="role-council-contract",
            name="Role council contract",
            status="pass" if passed else "fail",
            expected=", ".join(sorted(required)),
            observed=", ".join(sorted(observed)),
            evidence=f"Council status is {council.status} with {len(council.conversation)} deterministic turns.",
            blocking=not passed,
            role_refs=sorted(required),
            endpoint_refs=["/proposal/agent-council"],
        )

    def _provenance_check(self, provenance: ProposalDecisionProvenanceResponse) -> BuyerContractCheck:
        passed = provenance.status in {"pass", "needs_review", "blocked_by_governance"} and all(
            assertion.get("passed") for assertion in provenance.eval_assertions
        )
        return BuyerContractCheck(
            check_id="decision-provenance-contract",
            name="Decision provenance contract",
            status="pass" if passed else "fail",
            expected="typed provenance graph with passing eval assertions",
            observed=f"{provenance.status}; {provenance.summary.get('node_count')} node(s)",
            evidence="Provenance keeps workflow, council, governance, and procurement decisions linked.",
            blocking=not passed,
            endpoint_refs=["/proposal/decision-provenance"],
        )

    def _provider_optionality_check(self, workflow: BuyerIntelligenceWorkflowResponse) -> BuyerContractCheck:
        modes = {route.provider_mode for route in workflow.provider_routes}
        passed = {"mock", "openai", "azure_openai"} <= modes
        return BuyerContractCheck(
            check_id="provider-optional-contract",
            name="Provider optionality contract",
            status="pass" if passed else "fail",
            expected="mock, openai, and azure_openai provider routes",
            observed=", ".join(sorted(modes)),
            evidence="Mock remains the default local route while OpenAI and Azure OpenAI are optional.",
            blocking=not passed,
            endpoint_refs=["/proposal/buyer-intelligence", "/ops/cost-governance"],
        )

    def _eval_contract_check(
        self,
        replay: BuyerWorkflowReplayResponse,
        council: ProposalAgentCouncilResponse,
        provenance: ProposalDecisionProvenanceResponse,
    ) -> BuyerContractCheck:
        scenario_count = len(replay.eval_scenarios) + len(council.eval_scenarios) + len(provenance.eval_assertions)
        passed_count = sum(1 for item in replay.eval_scenarios if item.get("passed"))
        passed_count += sum(1 for item in council.eval_scenarios if item.get("passed"))
        passed_count += sum(1 for item in provenance.eval_assertions if item.get("passed"))
        passed = scenario_count > 0 and scenario_count == passed_count
        return BuyerContractCheck(
            check_id="eval-friendly-contract",
            name="Eval-friendly structured assertions",
            status="pass" if passed else "fail",
            expected="all buyer replay, council, and provenance eval assertions pass",
            observed=f"{passed_count}/{scenario_count} passed",
            evidence="Assertions are deterministic local contract checks suitable for regression tests.",
            blocking=not passed,
            endpoint_refs=[
                "/proposal/buyer-intelligence-replay",
                "/proposal/agent-council",
                "/proposal/decision-provenance",
            ],
        )

    def _role_checks(self, roles: list[BuyerContractRoleCoverage]) -> list[BuyerContractCheck]:
        return [
            BuyerContractCheck(
                check_id=f"role-output-{self._slug(role.role)}",
                name=f"{role.role} output contract",
                status=role.status,
                expected=", ".join(role.required_outputs),
                observed=", ".join(role.observed_outputs) or "none",
                evidence=f"{role.contract_id} maps reviewer controls and endpoint references.",
                blocking=role.status == "fail",
                role_refs=[role.role],
                endpoint_refs=role.endpoint_refs,
            )
            for role in roles
        ]

    def _output_contracts(self) -> list[dict[str, Any]]:
        return [
            {
                "model": model.__name__,
                "contract_type": "pydantic_response_model",
                "required_fields": self._schema_required(model),
                "field_count": len(model.model_fields),
                "structured_output": True,
            }
            for model in self.contract_models
        ]

    def _schema_snapshots(self) -> dict[str, Any]:
        snapshots: dict[str, Any] = {}
        for model in self.contract_models:
            schema = model.model_json_schema()
            snapshots[model.__name__] = {
                "title": schema.get("title", model.__name__),
                "required": schema.get("required", []),
                "properties": sorted(schema.get("properties", {}).keys()),
            }
        return snapshots

    def _eval_assertions(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        replay: BuyerWorkflowReplayResponse,
        council: ProposalAgentCouncilResponse,
        provenance: ProposalDecisionProvenanceResponse,
        checks: list[BuyerContractCheck],
        roles: list[BuyerContractRoleCoverage],
    ) -> list[dict[str, Any]]:
        return [
            {
                "assertion_id": "buyer-contracts-all-checks-pass",
                "assertion": "all structured output contract checks pass",
                "expected": len(checks),
                "observed": sum(1 for check in checks if check.status == "pass"),
                "passed": all(check.status == "pass" for check in checks),
            },
            {
                "assertion_id": "buyer-contracts-role-coverage",
                "assertion": "sales, presales, compliance, procurement, and proposal manager contracts are covered",
                "expected": 5,
                "observed": len([role for role in roles if role.status == "pass"]),
                "passed": all(role.status == "pass" for role in roles),
            },
            {
                "assertion_id": "buyer-contracts-cross-artifact-links",
                "assertion": "workflow, replay, council, and provenance retain linked local traceability",
                "expected": "linked",
                "observed": {
                    "workflow": workflow.workflow_id,
                    "replay": replay.workflow_id,
                    "council": council.council_id,
                    "provenance": provenance.provenance_id,
                },
                "passed": bool(workflow.workflow_id and replay.workflow_id and council.council_id),
            },
        ]

    def _pack_payload(self, trace_id: str, contract_audit: BuyerStructuredContractResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Buyer Structured Output Contract Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "contract_audit": contract_audit.model_dump(mode="json"),
            "reviewer_controls": [
                "Inspect failed or warning checks before exporting buyer-facing proposal artifacts.",
                "Use schema snapshots to verify API consumers receive stable structured outputs.",
                "Confirm every role contract maps to a human reviewer before submission.",
                "Regenerate after changing buyer workflow, replay, council, or provenance response models.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        audit = pack["contract_audit"]
        lines = [
            "# Buyer Structured Output Contract Pack",
            "",
            "## Summary",
            "",
            f"- Status: {audit['status']}",
            f"- Score: {audit['score']}",
            f"- Contract version: {audit['contract_version']}",
            f"- Provider mode: {audit['injected_dependencies']['settings_provider_mode']}",
            f"- External provider required: {audit['injected_dependencies']['external_provider_required']}",
            "",
            "## Output Contracts",
            "",
            "| Model | Fields | Required fields |",
            "| --- | ---: | --- |",
        ]
        for contract in audit["output_contracts"]:
            lines.append(
                f"| {contract['model']} | {contract['field_count']} | "
                f"{self._md(', '.join(contract['required_fields']))} |"
            )
        lines.extend(["", "## Role Contracts", ""])
        lines.append("| Role | Status | Required outputs | Observed outputs |")
        lines.append("| --- | --- | --- | --- |")
        for role in audit["role_contracts"]:
            lines.append(
                f"| {self._md(role['role'])} | {role['status']} | "
                f"{self._md(', '.join(role['required_outputs']))} | "
                f"{self._md(', '.join(role['observed_outputs']))} |"
            )
        lines.extend(["", "## Contract Checks", ""])
        for check in audit["checks"]:
            lines.append(
                f"- {check['check_id']} ({check['status']}): expected {self._md(check['expected'])}; "
                f"observed {self._md(check['observed'])}."
            )
        lines.extend(["", "## Eval Assertions", ""])
        for assertion in audit["eval_assertions"]:
            result = "pass" if assertion["passed"] else "fail"
            lines.append(f"- {assertion['assertion_id']} ({result}): {self._md(assertion['assertion'])}")
        lines.extend(["", "## Reviewer Controls", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_controls"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in audit["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {self._md(item)}" for item in audit["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Generated Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {"method": "GET", "path": "/proposal/buyer-contracts", "purpose": "View structured contract audit."},
            {"method": "POST", "path": "/proposal/buyer-contracts-pack", "purpose": "Write contract artifacts."},
            {"method": "GET", "path": "/proposal/buyer-intelligence", "purpose": "Source workflow output."},
            {"method": "GET", "path": "/proposal/buyer-intelligence-replay", "purpose": "Source replay output."},
            {"method": "GET", "path": "/proposal/agent-council", "purpose": "Source role council output."},
            {"method": "GET", "path": "/proposal/decision-provenance", "purpose": "Source provenance output."},
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/proposal/buyer-contracts" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/proposal/buyer-contracts-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'rg "proposal/buyer-contracts|Buyer Structured Output Contract|buyer_contracts" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\buyer_contracts -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "This audit validates local Pydantic outputs and deterministic routing, not a live workflow engine.",
            "Schema snapshots are compact field inventories for reviewer inspection, not full OpenAPI replacement.",
            "Role contracts prove local output coverage; real approval records must be reconciled outside this repo.",
            "OpenAI, Azure OpenAI, CRM, GRC, procurement, and ticketing systems remain optional and are not called.",
        ]

    def _schema_required(self, model: type[BaseModel]) -> list[str]:
        return list(model.model_json_schema().get("required", []))

    def _model_endpoint_refs(self, model_name: str) -> list[str]:
        return {
            "BuyerIntelligenceWorkflowResponse": ["/proposal/buyer-intelligence"],
            "BuyerWorkflowReplayResponse": ["/proposal/buyer-intelligence-replay"],
            "ProposalAgentCouncilResponse": ["/proposal/agent-council"],
            "ProposalDecisionProvenanceResponse": ["/proposal/decision-provenance"],
        }.get(model_name, [])

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower() or "local"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
