from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    ProviderResiliencePackResponse,
    ProviderResilienceResponse,
    ProviderResilienceRoute,
    ProviderResilienceTransition,
)


class ProviderResilienceService:
    """Local provider fallback runbook for mock/OpenAI/Azure modes."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def resilience(self, trace_id: str) -> ProviderResilienceResponse:
        routes = self._routes()
        active = self._active_route(routes)
        recommended = self._recommended_route(routes, active)
        transitions = self._transitions(active, recommended)
        state_machine = self._state_machine(active, recommended, transitions)
        status = self._status(active, recommended)
        summary = {
            "route_count": len(routes),
            "ready_route_count": sum(route.readiness_status == "ready" for route in routes),
            "blocked_route_count": sum(route.readiness_status == "blocked" for route in routes),
            "active_route_id": active.route_id,
            "recommended_route_id": recommended.route_id,
            "fallback_required": active.route_id != recommended.route_id,
            "missing_env": sorted({name for route in routes for name in route.missing_env}),
            "implemented_patterns": [
                "typed_contracts",
                "dependency_injection",
                "state_machine_workflow",
                "conditional_routing",
                "traceable_node_transitions",
                "eval_friendly_design",
            ],
        }
        return ProviderResilienceResponse(
            title="Provider Resilience Runbook",
            status=status,
            active_provider_mode=self.settings.provider_mode,
            recommended_route_id=recommended.route_id,
            provider_routes=routes,
            state_machine=state_machine,
            transitions=transitions,
            dependency_injection_contract=self._dependency_contract(recommended),
            evaluator_scenarios=self._evaluator_scenarios(routes),
            operator_runbook=self._operator_runbook(status, active, recommended),
            trace_spans=self._trace_spans(trace_id, routes, transitions),
            summary=summary,
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        resilience: ProviderResilienceResponse | None = None,
        write_artifact: bool = True,
    ) -> ProviderResiliencePackResponse:
        resilience = resilience or self.resilience(f"{trace_id}-resilience")
        pack = self._pack_payload(trace_id, resilience)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "provider_resilience"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"provider_resilience_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"provider_resilience_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["provider_resilience_markdown"] = artifact_path
            pack["artifact_paths"]["provider_resilience_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return ProviderResiliencePackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            resilience=resilience,
            trace_id=trace_id,
        )

    def _routes(self) -> list[ProviderResilienceRoute]:
        openai_missing = [] if self.settings.openai_api_key else ["OPENAI_API_KEY"]
        azure_required = ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT"]
        azure_values = {
            "AZURE_OPENAI_ENDPOINT": self.settings.azure_openai_endpoint,
            "AZURE_OPENAI_API_KEY": self.settings.azure_openai_api_key,
            "AZURE_OPENAI_DEPLOYMENT": self.settings.azure_openai_deployment,
        }
        azure_missing = [name for name in azure_required if not azure_values[name]]
        return [
            ProviderResilienceRoute(
                route_id="provider.mock.local",
                provider_mode="mock",
                model="mock-local",
                readiness_status="ready",
                priority=1,
                fallback_route_id=None,
                governance_notes=[
                    "Default route for local demos, tests, CI, and no-key environments.",
                    "Keeps answers deterministic for eval and red-team replay.",
                ],
            ),
            ProviderResilienceRoute(
                route_id="provider.openai.primary",
                provider_mode="openai",
                model=self.settings.openai_model,
                readiness_status="ready" if not openai_missing else "blocked",
                priority=2,
                required_env=["OPENAI_API_KEY"],
                missing_env=openai_missing,
                fallback_route_id="provider.mock.local",
                governance_notes=[
                    "Use only when external provider access is explicitly intended.",
                    "Fallback to mock if credentials are absent or provider smoke tests fail.",
                ],
            ),
            ProviderResilienceRoute(
                route_id="provider.azure_openai.enterprise",
                provider_mode="azure_openai",
                model=self.settings.azure_openai_deployment or "azure-openai-not-configured",
                readiness_status="ready" if not azure_missing else "blocked",
                priority=3,
                required_env=azure_required,
                missing_env=azure_missing,
                fallback_route_id="provider.mock.local",
                governance_notes=[
                    "Enterprise route for Azure OpenAI deployments when endpoint, key, and deployment are set.",
                    "Fallback to mock for local portfolio verification and CI.",
                ],
            ),
        ]

    def _active_route(self, routes: list[ProviderResilienceRoute]) -> ProviderResilienceRoute:
        mode = self.settings.provider_mode.lower()
        if mode == "azure":
            mode = "azure_openai"
        return next((route for route in routes if route.provider_mode == mode), routes[0])

    def _recommended_route(
        self,
        routes: list[ProviderResilienceRoute],
        active: ProviderResilienceRoute,
    ) -> ProviderResilienceRoute:
        if active.readiness_status == "ready":
            return active
        fallback_id = active.fallback_route_id or "provider.mock.local"
        return next(route for route in routes if route.route_id == fallback_id)

    def _status(self, active: ProviderResilienceRoute, recommended: ProviderResilienceRoute) -> str:
        if active.readiness_status == "ready" and active.provider_mode == "mock":
            return "local_ready"
        if active.readiness_status == "ready":
            return "external_provider_ready"
        if recommended.readiness_status == "ready":
            return "fallback_to_mock"
        return "blocked"

    def _transitions(
        self,
        active: ProviderResilienceRoute,
        recommended: ProviderResilienceRoute,
    ) -> list[ProviderResilienceTransition]:
        route_decision = (
            "continue_active_provider"
            if active.route_id == recommended.route_id
            else f"route_to_{recommended.provider_mode}"
        )
        return [
            ProviderResilienceTransition(
                transition_id="provider-route-001",
                from_state="inspect_configuration",
                to_state="select_candidate_provider",
                condition=f"PROVIDER_MODE={self.settings.provider_mode}",
                decision=f"candidate={active.route_id}",
                checkpoint_id="provider-resilience.inspect.v1",
                trace_note="Configuration was inspected without calling an external provider.",
            ),
            ProviderResilienceTransition(
                transition_id="provider-route-002",
                from_state="select_candidate_provider",
                to_state="validate_provider_readiness",
                condition="required environment variables are present",
                decision=f"readiness={active.readiness_status}",
                checkpoint_id="provider-resilience.readiness.v1",
                trace_note="Credential presence gates external-provider activation.",
            ),
            ProviderResilienceTransition(
                transition_id="provider-route-003",
                from_state="validate_provider_readiness",
                to_state="activate_runtime_route",
                condition="candidate is ready, otherwise fallback route is ready",
                decision=route_decision,
                checkpoint_id="provider-resilience.route.v1",
                trace_note=f"Recommended runtime route is {recommended.route_id}.",
            ),
        ]

    def _state_machine(
        self,
        active: ProviderResilienceRoute,
        recommended: ProviderResilienceRoute,
        transitions: list[ProviderResilienceTransition],
    ) -> list[dict[str, Any]]:
        return [
            {
                "state": "inspect_configuration",
                "status": "complete",
                "owner": "platform",
                "checkpoint_id": "provider-resilience.inspect.v1",
                "resumable": True,
                "output": {"active_provider_mode": self.settings.provider_mode},
            },
            {
                "state": "select_candidate_provider",
                "status": "complete",
                "owner": "platform",
                "checkpoint_id": "provider-resilience.candidate.v1",
                "resumable": True,
                "output": {"candidate_route_id": active.route_id},
            },
            {
                "state": "validate_provider_readiness",
                "status": "complete" if active.readiness_status == "ready" else "blocked",
                "owner": "platform",
                "checkpoint_id": "provider-resilience.readiness.v1",
                "resumable": True,
                "output": {"missing_env": active.missing_env},
            },
            {
                "state": "activate_runtime_route",
                "status": "ready" if recommended.readiness_status == "ready" else "blocked",
                "owner": "solution-engineering",
                "checkpoint_id": "provider-resilience.route.v1",
                "resumable": True,
                "output": {
                    "recommended_route_id": recommended.route_id,
                    "transition_count": len(transitions),
                },
            },
        ]

    def _dependency_contract(self, recommended: ProviderResilienceRoute) -> dict[str, Any]:
        return {
            "container_factory": "app.services.container.get_container",
            "provider_factory": "app.providers.factory.build_llm_provider",
            "injected_interface": "app.providers.base.BaseLLMProvider",
            "runtime_consumer": "app.services.draft_generation.DraftGenerationService",
            "selected_provider_mode": recommended.provider_mode,
            "selected_model": recommended.model,
            "test_override": "Set PROVIDER_MODE=mock and clear external provider keys for deterministic tests.",
            "contract_checks": [
                "answer(question, citations) returns LLMResult",
                "draft(section_names, citations) returns LLMResult",
                "token usage, model, and provider are preserved for metrics and audit.",
            ],
        }

    def _evaluator_scenarios(self, routes: list[ProviderResilienceRoute]) -> list[dict[str, Any]]:
        return [
            {
                "scenario_id": "provider-eval-local-mock",
                "provider_mode": "mock",
                "expected_status": "local_ready",
                "assertion": "No external credentials are required and mock is selected.",
                "command": "python -m pytest -q tests/test_provider_resilience.py",
            },
            {
                "scenario_id": "provider-eval-openai-missing-key",
                "provider_mode": "openai",
                "expected_status": "fallback_to_mock",
                "assertion": "Missing OPENAI_API_KEY routes to provider.mock.local.",
                "missing_env": next(route.missing_env for route in routes if route.provider_mode == "openai"),
            },
            {
                "scenario_id": "provider-eval-azure-missing-config",
                "provider_mode": "azure_openai",
                "expected_status": "fallback_to_mock",
                "assertion": "Missing Azure endpoint/key/deployment routes to provider.mock.local.",
                "missing_env": next(route.missing_env for route in routes if route.provider_mode == "azure_openai"),
            },
        ]

    def _operator_runbook(
        self,
        status: str,
        active: ProviderResilienceRoute,
        recommended: ProviderResilienceRoute,
    ) -> list[dict[str, Any]]:
        return [
            {
                "step": 1,
                "owner": "platform",
                "action": "Keep PROVIDER_MODE=mock for local demos, CI, and portfolio review.",
                "status": "ready" if recommended.provider_mode == "mock" else "review",
            },
            {
                "step": 2,
                "owner": "platform",
                "action": f"Current candidate route is {active.route_id}; recommended route is {recommended.route_id}.",
                "status": status,
            },
            {
                "step": 3,
                "owner": "solution-engineering",
                "action": "Run pytest, eval, red-team, dashboard smoke, and demo after provider mode changes.",
                "status": "required",
            },
            {
                "step": 4,
                "owner": "security",
                "action": (
                    "Never commit provider credentials; keep .env local and regenerate audit packs before publish."
                ),
                "status": "required",
            },
        ]

    def _trace_spans(
        self,
        trace_id: str,
        routes: list[ProviderResilienceRoute],
        transitions: list[ProviderResilienceTransition],
    ) -> list[dict[str, Any]]:
        return [
            {
                "span_id": f"{trace_id}.provider-resilience.routes",
                "operation": "provider_route_inventory",
                "status": "ok",
                "route_count": len(routes),
                "blocked_route_count": sum(route.readiness_status == "blocked" for route in routes),
                "pattern": "typed_contracts",
            },
            {
                "span_id": f"{trace_id}.provider-resilience.transitions",
                "operation": "provider_state_transitions",
                "status": "ok",
                "transition_count": len(transitions),
                "pattern": "traceable_node_transitions",
            },
        ]

    def _pack_payload(self, trace_id: str, resilience: ProviderResilienceResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Provider Resilience Runbook Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "resilience": resilience.model_dump(mode="json"),
            "executive_summary": {
                "status": resilience.status,
                "active_provider_mode": resilience.active_provider_mode,
                "recommended_route_id": resilience.recommended_route_id,
                "fallback_required": resilience.summary["fallback_required"],
                "missing_env": resilience.summary["missing_env"],
            },
            "reviewer_checklist": [
                "Confirm local verification keeps PROVIDER_MODE=mock unless a cloud-provider demo is intentional.",
                "Confirm missing external provider env vars route back to provider.mock.local.",
                "Run pytest, ruff, eval, red-team, dashboard smoke, and demo after provider-mode changes.",
                "Regenerate storage/provider_resilience artifacts before reviewer handoff.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        resilience = pack["resilience"]
        summary = pack["executive_summary"]
        lines = [
            "# Provider Resilience Runbook Pack",
            "",
            "## Executive Summary",
            "",
            f"- Status: {summary['status']}",
            f"- Active provider mode: {summary['active_provider_mode']}",
            f"- Recommended route: {summary['recommended_route_id']}",
            f"- Fallback required: {summary['fallback_required']}",
            f"- Missing env: {', '.join(summary['missing_env']) or 'none'}",
            "",
            "## Provider Routes",
            "",
            "| Route | Provider | Model | Readiness | Fallback | Missing env |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for route in resilience["provider_routes"]:
            lines.append(
                f"| {route['route_id']} | {route['provider_mode']} | {route['model']} | "
                f"{route['readiness_status']} | {route['fallback_route_id'] or 'none'} | "
                f"{', '.join(route['missing_env']) or 'none'} |"
            )
        lines.extend(["", "## State Machine", ""])
        lines.append("| State | Status | Checkpoint | Owner | Output |")
        lines.append("| --- | --- | --- | --- | --- |")
        for state in resilience["state_machine"]:
            lines.append(
                f"| {state['state']} | {state['status']} | {state['checkpoint_id']} | "
                f"{state['owner']} | {state['output']} |"
            )
        lines.extend(["", "## Traceable Transitions", ""])
        lines.append("| Transition | From | To | Decision | Checkpoint |")
        lines.append("| --- | --- | --- | --- | --- |")
        for transition in resilience["transitions"]:
            lines.append(
                f"| {transition['transition_id']} | {transition['from_state']} | "
                f"{transition['to_state']} | {transition['decision']} | {transition['checkpoint_id']} |"
            )
        lines.extend(["", "## Dependency Injection Contract", ""])
        for key, value in resilience["dependency_injection_contract"].items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Evaluator Scenarios", ""])
        for scenario in resilience["evaluator_scenarios"]:
            lines.append(f"- {scenario['scenario_id']}: {scenario['assertion']}")
        lines.extend(["", "## Operator Runbook", ""])
        for step in resilience["operator_runbook"]:
            lines.append(f"- Step {step['step']} ({step['owner']}): {step['action']} [{step['status']}]")
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in resilience["local_proof_commands"])
        lines.extend(["", "## Reviewer Checklist", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_checklist"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in resilience["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Provider Resilience Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/ops/provider-resilience" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/ops/provider-resilience-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m pytest -q tests/test_provider_resilience.py",
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            (
                'rg "provider-resilience|Provider Resilience|provider_resilience|provider.mock.local" '
                "app dashboard docs README.md tests Makefile"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            (
                "Provider resilience checks validate local configuration and route policy; they do not call "
                "OpenAI or Azure."
            ),
            (
                "Runtime fallback is documented as a governance route; production systems should add retries "
                "and circuit breakers."
            ),
            "Mock mode remains the default so tests, evals, and demos are deterministic without paid API keys.",
            (
                "Credential presence does not prove quota, network reachability, model availability, "
                "or compliance approval."
            ),
        ]
