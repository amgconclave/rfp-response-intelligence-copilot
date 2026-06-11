from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    ProposalBenchmarkScenario,
    ProposalObservabilityResponse,
    ProposalQualityBenchmarkPackResponse,
    ProposalQualityBenchmarkResponse,
    ProposalSubmissionCertificationResponse,
    ProviderResilienceResponse,
)


class ProposalQualityBenchmarkService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def benchmark(
        self,
        trace_id: str,
        certification: ProposalSubmissionCertificationResponse,
        observability: ProposalObservabilityResponse,
        provider_resilience: ProviderResilienceResponse,
    ) -> ProposalQualityBenchmarkResponse:
        scenarios = self._scenarios(certification, observability, provider_resilience)
        score = self._score(scenarios)
        status = self._status(scenarios)
        return ProposalQualityBenchmarkResponse(
            title="Proposal Quality Benchmark",
            benchmark_id=f"proposal-benchmark-{self._slug(trace_id)}",
            status=status,
            generated_at=datetime.now(UTC).isoformat(),
            score=score,
            scenario_count=len(scenarios),
            passed_count=sum(scenario.status == "pass" for scenario in scenarios),
            warning_count=sum(scenario.status == "warn" for scenario in scenarios),
            failed_count=sum(scenario.status == "fail" for scenario in scenarios),
            injected_dependencies=self._injected_dependencies(provider_resilience),
            benchmark_summary=self._summary(certification, observability, provider_resilience, scenarios),
            scenarios=scenarios,
            role_scorecard=self._role_scorecard(scenarios),
            state_transitions=self._state_transitions(trace_id, scenarios),
            eval_assertions=self._eval_assertions(scenarios, certification, observability, provider_resilience),
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        benchmark: ProposalQualityBenchmarkResponse,
        write_artifact: bool = True,
    ) -> ProposalQualityBenchmarkPackResponse:
        pack = self._pack_payload(trace_id, benchmark)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "proposal_benchmarks"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = self._slug(trace_id)
            markdown_path = pack_dir / f"proposal_quality_benchmark_{safe_trace_id}.md"
            json_path = pack_dir / f"proposal_quality_benchmark_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["proposal_benchmark_markdown"] = artifact_path
            pack["artifact_paths"]["proposal_benchmark_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return ProposalQualityBenchmarkPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            benchmark=benchmark,
            trace_id=trace_id,
        )

    def _scenarios(
        self,
        certification: ProposalSubmissionCertificationResponse,
        observability: ProposalObservabilityResponse,
        provider_resilience: ProviderResilienceResponse,
    ) -> list[ProposalBenchmarkScenario]:
        gate_status = {gate.gate_id: gate.status for gate in certification.gates}
        eval_passed = sum(assertion.get("passed") for assertion in certification.eval_assertions)
        eval_total = len(certification.eval_assertions)
        trace_spans = observability.summary["trace_span_count"]
        review_signals = observability.summary["human_review_signal_count"]
        provider_ready = provider_resilience.summary["ready_route_count"]
        provider_blocked = provider_resilience.summary["blocked_route_count"]
        return [
            self._scenario(
                "benchmark-structured-contracts",
                "Structured output contracts remain stable",
                "Platform Owner",
                "typed_contracts",
                "pass" if gate_status.get("gate-structured-output-contracts") == "pass" else "fail",
                18,
                "buyer contract audit passes certification gate",
                gate_status.get("gate-structured-output-contracts", "missing"),
                ["/proposal/buyer-contracts", certification.source_artifacts.get("contract_version", "")],
                "Repair failed schema, role, or eval contract checks.",
                "contract gate must pass before benchmark approval",
            ),
            self._scenario(
                "benchmark-checkpoint-replay",
                "Workflow transitions are checkpointed and replayable",
                "Platform Owner",
                "checkpointing",
                "pass" if gate_status.get("gate-checkpoint-replay") == "pass" else "fail",
                16,
                "checkpoint replay gate passes",
                gate_status.get("gate-checkpoint-replay", "missing"),
                ["/proposal/buyer-intelligence-replay"],
                "Repair missing checkpoint keys or trace references.",
                "replay checkpoint validation must pass",
            ),
            self._scenario(
                "benchmark-human-review-routing",
                "Human review queues are visible and routed",
                "Proposal Manager",
                "conditional_routing",
                "pass"
                if certification.reviewer_queue and review_signals >= len(certification.reviewer_queue)
                else "warn",
                14,
                "review queue items are mirrored in observability signals",
                f"queue={len(certification.reviewer_queue)} signals={review_signals}",
                ["/proposal/submission-certification", "/ops/proposal-observability"],
                "Clear or explicitly approve named review queue items.",
                "non-certified submissions must expose reviewer routing",
            ),
            self._scenario(
                "benchmark-trace-coverage",
                "Control-plane trace coverage is sufficient",
                "AI Governance Reviewer",
                "traceability",
                "pass" if trace_spans >= 30 else "warn",
                12,
                "at least 30 deterministic trace spans",
                str(trace_spans),
                ["/ops/proposal-observability"],
                "Regenerate observability after workflow or retrieval policy changes.",
                "trace map should cover workflow, replay, council, provenance, and retrieval spans",
            ),
            self._scenario(
                "benchmark-provider-optionality",
                "External providers remain optional",
                "Platform Owner",
                "dependency_injection",
                "pass"
                if (
                    self.settings.provider_mode == "mock"
                    and provider_resilience.recommended_route_id == "provider.mock.local"
                )
                else "warn",
                14,
                "mock provider is active and recommended for local benchmark",
                (
                    f"active={provider_resilience.active_provider_mode} "
                    f"recommended={provider_resilience.recommended_route_id}"
                ),
                ["/ops/provider-resilience", "/ops/cost-governance"],
                "Keep mock mode unless provider, cost, privacy, and model-risk controls approve external use.",
                "benchmark must not require OpenAI or Azure OpenAI credentials",
            ),
            self._scenario(
                "benchmark-provider-routes",
                "Provider fallback routes are explicitly modeled",
                "Platform Owner",
                "state_machine_workflow",
                "pass" if provider_ready >= 1 and provider_blocked >= 1 and provider_resilience.transitions else "fail",
                10,
                "ready local route, blocked cloud routes without keys, and transitions present",
                f"ready={provider_ready} blocked={provider_blocked} transitions={len(provider_resilience.transitions)}",
                ["/ops/provider-resilience"],
                "Define provider route transitions before changing PROVIDER_MODE.",
                "fallback state machine must be inspectable",
            ),
            self._scenario(
                "benchmark-certification-evals",
                "Certification eval assertions are attached",
                "AI Governance Reviewer",
                "eval_friendly_design",
                "pass" if eval_total and eval_passed == eval_total else "fail",
                16,
                "all certification eval assertions pass",
                f"{eval_passed}/{eval_total}",
                ["/proposal/submission-certification"],
                "Fix failed certification assertions before using the benchmark pack.",
                "all certification assertions must pass",
            ),
        ]

    def _scenario(
        self,
        scenario_id: str,
        title: str,
        owner_role: str,
        category: str,
        status: str,
        weight: int,
        expected: str,
        observed: str,
        evidence_refs: list[str],
        reviewer_action: str,
        eval_assertion: str,
    ) -> ProposalBenchmarkScenario:
        return ProposalBenchmarkScenario(
            scenario_id=scenario_id,
            title=title,
            owner_role=owner_role,
            category=category,
            status=status,
            weight=weight,
            expected=expected,
            observed=observed,
            evidence_refs=[ref for ref in evidence_refs if ref],
            reviewer_action=reviewer_action,
            eval_assertion=eval_assertion,
        )

    def _score(self, scenarios: list[ProposalBenchmarkScenario]) -> int:
        total_weight = sum(scenario.weight for scenario in scenarios)
        earned = sum(
            scenario.weight if scenario.status == "pass" else scenario.weight * 0.5 if scenario.status == "warn" else 0
            for scenario in scenarios
        )
        return round(earned / total_weight * 100) if total_weight else 0

    def _status(self, scenarios: list[ProposalBenchmarkScenario]) -> str:
        if any(scenario.status == "fail" for scenario in scenarios):
            return "fail"
        if any(scenario.status == "warn" for scenario in scenarios):
            return "pass_with_review_items"
        return "pass"

    def _injected_dependencies(self, provider_resilience: ProviderResilienceResponse) -> dict[str, Any]:
        return {
            "service": "ProposalQualityBenchmarkService",
            "settings_provider_mode": self.settings.provider_mode,
            "settings_vector_store_mode": self.settings.vector_store_mode,
            "provider_resilience_service": provider_resilience.dependency_injection_contract.get("service"),
            "external_provider_required": False,
        }

    def _summary(
        self,
        certification: ProposalSubmissionCertificationResponse,
        observability: ProposalObservabilityResponse,
        provider_resilience: ProviderResilienceResponse,
        scenarios: list[ProposalBenchmarkScenario],
    ) -> dict[str, Any]:
        statuses = Counter(scenario.status for scenario in scenarios)
        categories = Counter(scenario.category for scenario in scenarios)
        return {
            "certification_status": certification.status,
            "certification_readiness_score": certification.readiness_score,
            "observability_status": observability.status,
            "trace_span_count": observability.summary["trace_span_count"],
            "human_review_signal_count": observability.summary["human_review_signal_count"],
            "provider_resilience_status": provider_resilience.status,
            "recommended_provider_route": provider_resilience.recommended_route_id,
            "scenario_status_counts": dict(sorted(statuses.items())),
            "scenario_category_counts": dict(sorted(categories.items())),
            "radar_patterns_used": [
                "typed_contracts",
                "structured_outputs",
                "dependency_injection",
                "eval_friendly_design",
                "state_machine_workflow",
                "checkpointing",
                "conditional_routing",
                "traceable_node_transitions",
            ],
        }

    def _role_scorecard(self, scenarios: list[ProposalBenchmarkScenario]) -> list[dict[str, Any]]:
        roles = sorted({scenario.owner_role for scenario in scenarios})
        rows = []
        for role in roles:
            scoped = [scenario for scenario in scenarios if scenario.owner_role == role]
            rows.append(
                {
                    "owner_role": role,
                    "scenario_count": len(scoped),
                    "passed": sum(scenario.status == "pass" for scenario in scoped),
                    "warnings": sum(scenario.status == "warn" for scenario in scoped),
                    "failed": sum(scenario.status == "fail" for scenario in scoped),
                    "reviewer_actions": [scenario.reviewer_action for scenario in scoped if scenario.status != "pass"],
                }
            )
        return rows

    def _state_transitions(self, trace_id: str, scenarios: list[ProposalBenchmarkScenario]) -> list[dict[str, Any]]:
        transitions = []
        prior = "benchmark_loaded"
        for sequence, scenario in enumerate(scenarios, start=1):
            to_state = f"evaluate_{self._slug(scenario.scenario_id)}"
            transitions.append(
                {
                    "transition_id": f"benchmark-transition-{sequence:02d}",
                    "sequence": sequence,
                    "from_state": prior,
                    "to_state": to_state,
                    "decision": "continue" if scenario.status == "pass" else "route_to_reviewer",
                    "condition": scenario.eval_assertion,
                    "checkpoint_key": f"{self._slug(trace_id)}:{sequence:02d}:{to_state}",
                    "scenario_id": scenario.scenario_id,
                }
            )
            prior = to_state
        return transitions

    def _eval_assertions(
        self,
        scenarios: list[ProposalBenchmarkScenario],
        certification: ProposalSubmissionCertificationResponse,
        observability: ProposalObservabilityResponse,
        provider_resilience: ProviderResilienceResponse,
    ) -> list[dict[str, Any]]:
        linked_controls = [
            certification.certification_id,
            observability.trace_id,
            provider_resilience.trace_id,
        ]
        return [
            {
                "assertion_id": "benchmark-scenarios-typed",
                "assertion": "every benchmark scenario is a typed structured output with owner and evidence refs",
                "expected": len(scenarios),
                "observed": sum(bool(s.owner_role and s.evidence_refs) for s in scenarios),
                "passed": all(s.owner_role and s.evidence_refs for s in scenarios),
            },
            {
                "assertion_id": "benchmark-no-hard-failures",
                "assertion": "quality benchmark has no failed scenarios",
                "expected": 0,
                "observed": sum(s.status == "fail" for s in scenarios),
                "passed": not any(s.status == "fail" for s in scenarios),
            },
            {
                "assertion_id": "benchmark-source-controls-linked",
                "assertion": "certification, observability, and provider resilience source controls are linked",
                "expected": 3,
                "observed": sum(bool(value) for value in linked_controls),
                "passed": all(linked_controls),
            },
        ]

    def _pack_payload(self, trace_id: str, benchmark: ProposalQualityBenchmarkResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Proposal Quality Benchmark Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "benchmark": benchmark.model_dump(mode="json"),
            "reviewer_controls": [
                "Treat failed scenarios as blockers before final proposal submission.",
                "Treat warnings as named-review items; attach the source pack and owner decision.",
                "Keep the benchmark local and deterministic unless external provider review is explicit.",
                "Regenerate after changing buyer workflow, certification, observability, provider, or eval logic.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        benchmark = pack["benchmark"]
        summary = benchmark["benchmark_summary"]
        lines = [
            "# Proposal Quality Benchmark Pack",
            "",
            "## Summary",
            "",
            f"- Status: {benchmark['status']}",
            f"- Score: {benchmark['score']}",
            f"- Scenarios: {benchmark['scenario_count']}",
            f"- Certification: {summary['certification_status']} ({summary['certification_readiness_score']})",
            f"- Observability: {summary['observability_status']}",
            f"- Provider route: {summary['recommended_provider_route']}",
            "",
            "## Benchmark Scenarios",
            "",
            "| Scenario | Owner | Category | Status | Weight | Observed |",
            "| --- | --- | --- | --- | ---: | --- |",
        ]
        for scenario in benchmark["scenarios"]:
            lines.append(
                f"| {self._md(scenario['title'])} | {self._md(scenario['owner_role'])} | "
                f"{scenario['category']} | {scenario['status']} | {scenario['weight']} | "
                f"{self._md(scenario['observed'])} |"
            )
        lines.extend(["", "## Role Scorecard", ""])
        for row in benchmark["role_scorecard"]:
            lines.append(
                f"- {self._md(row['owner_role'])}: {row['passed']} pass, "
                f"{row['warnings']} warn, {row['failed']} fail."
            )
        lines.extend(["", "## State Transitions", ""])
        lines.append("| Seq | From | To | Decision | Checkpoint |")
        lines.append("| ---: | --- | --- | --- | --- |")
        for transition in benchmark["state_transitions"]:
            lines.append(
                f"| {transition['sequence']} | {self._md(transition['from_state'])} | "
                f"{self._md(transition['to_state'])} | {transition['decision']} | "
                f"`{self._md(transition['checkpoint_key'])}` |"
            )
        lines.extend(["", "## Eval Assertions", ""])
        for assertion in benchmark["eval_assertions"]:
            result = "pass" if assertion["passed"] else "fail"
            lines.append(f"- {assertion['assertion_id']} ({result}): {self._md(assertion['assertion'])}")
        lines.extend(["", "## Reviewer Controls", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_controls"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in benchmark["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {self._md(item)}" for item in benchmark["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Generated Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {"method": "GET", "path": "/proposal/quality-benchmark", "purpose": "View benchmark scenarios."},
            {"method": "POST", "path": "/proposal/quality-benchmark-pack", "purpose": "Write benchmark artifacts."},
            {"method": "GET", "path": "/proposal/submission-certification", "purpose": "Source certification gates."},
            {"method": "GET", "path": "/ops/proposal-observability", "purpose": "Source trace and HITL signals."},
            {"method": "GET", "path": "/ops/provider-resilience", "purpose": "Source provider route policy."},
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/proposal/quality-benchmark" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/proposal/quality-benchmark-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            (
                'rg "proposal/quality-benchmark|Proposal Quality Benchmark|proposal_benchmarks" '
                "app dashboard docs README.md tests Makefile"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Benchmark scenarios are deterministic local control checks, not live customer acceptance tests.",
            "Warnings indicate named review work remains; they are not automatically cleared by the benchmark.",
            (
                "Provider checks confirm optional local routing and do not call OpenAI, Azure OpenAI, CRM, GRC, "
                "or procurement APIs."
            ),
            "Human approvals are modeled from local artifacts and must be reconciled with real reviewer systems.",
        ]

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower() or "local"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
