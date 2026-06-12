from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from app.core.config import Settings
from app.models.api import (
    BuyerIntelligenceWorkflowResponse,
    BuyerStructuredContractResponse,
    BuyerWorkflowReplayResponse,
    ProposalAgentCouncilResponse,
    ProposalAssuranceBundlePackResponse,
    ProposalAssuranceBundleResponse,
    ProposalAssuranceEvidenceItem,
    ProposalDecisionProvenanceResponse,
    ProposalObservabilityResponse,
    ProposalQualityBenchmarkResponse,
    ProposalSubmissionCertificationResponse,
    ProviderResilienceResponse,
)


class ProposalAssuranceBundleService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def bundle(
        self,
        trace_id: str,
        workflow: BuyerIntelligenceWorkflowResponse,
        replay: BuyerWorkflowReplayResponse,
        contract_audit: BuyerStructuredContractResponse,
        council: ProposalAgentCouncilResponse,
        provenance: ProposalDecisionProvenanceResponse,
        certification: ProposalSubmissionCertificationResponse,
        observability: ProposalObservabilityResponse,
        benchmark: ProposalQualityBenchmarkResponse,
        provider_resilience: ProviderResilienceResponse,
    ) -> ProposalAssuranceBundleResponse:
        evidence_items = self._evidence_items(
            workflow,
            replay,
            contract_audit,
            council,
            provenance,
            certification,
            observability,
            benchmark,
            provider_resilience,
        )
        eval_assertions = self._eval_assertions(evidence_items, workflow, replay, contract_audit, benchmark)
        score = self._score(evidence_items, eval_assertions)
        status = self._status(evidence_items, eval_assertions, score)
        return ProposalAssuranceBundleResponse(
            title="Proposal Assurance Bundle",
            assurance_id=f"proposal-assurance-{self._slug(trace_id)}",
            status=status,
            score=score,
            generated_at=datetime.now(UTC).isoformat(),
            injected_dependencies=self._injected_dependencies(),
            control_summary=self._control_summary(evidence_items, eval_assertions),
            artifact_manifest=evidence_items,
            state_transitions=self._state_transitions(trace_id, evidence_items),
            reviewer_queue=self._reviewer_queue(evidence_items),
            eval_assertions=eval_assertions,
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        bundle: ProposalAssuranceBundleResponse,
        write_artifact: bool = True,
    ) -> ProposalAssuranceBundlePackResponse:
        pack = self._pack_payload(trace_id, bundle)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "proposal_assurance"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = self._slug(trace_id)
            markdown_path = pack_dir / f"proposal_assurance_bundle_{safe_trace_id}.md"
            json_path = pack_dir / f"proposal_assurance_bundle_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["proposal_assurance_markdown"] = artifact_path
            pack["artifact_paths"]["proposal_assurance_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return ProposalAssuranceBundlePackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            assurance=bundle,
            trace_id=trace_id,
        )

    def _evidence_items(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        replay: BuyerWorkflowReplayResponse,
        contract_audit: BuyerStructuredContractResponse,
        council: ProposalAgentCouncilResponse,
        provenance: ProposalDecisionProvenanceResponse,
        certification: ProposalSubmissionCertificationResponse,
        observability: ProposalObservabilityResponse,
        benchmark: ProposalQualityBenchmarkResponse,
        provider_resilience: ProviderResilienceResponse,
    ) -> list[ProposalAssuranceEvidenceItem]:
        specs: list[tuple[str, str, str, str, str, BaseModel, dict[str, Any]]] = [
            (
                "buyer-workflow",
                "/proposal/buyer-intelligence",
                "durable_workflow",
                workflow.workflow_status,
                "Proposal Manager",
                workflow,
                {
                    "stages": len(workflow.workflow_stages),
                    "approvals": len(workflow.human_approval_queue),
                    "gates": len(workflow.governance_gates),
                },
            ),
            (
                "workflow-replay",
                "/proposal/buyer-intelligence-replay",
                "checkpoint_replay",
                replay.status,
                "Platform Owner",
                replay,
                {
                    "transitions": replay.transition_count,
                    "checkpoint_status": replay.checkpoint_validation.get("status"),
                },
            ),
            (
                "structured-contracts",
                "/proposal/buyer-contracts",
                "typed_contract",
                contract_audit.status,
                "Platform Owner",
                contract_audit,
                {
                    "score": contract_audit.score,
                    "checks": len(contract_audit.checks),
                    "contract_version": contract_audit.contract_version,
                },
            ),
            (
                "agent-council",
                "/proposal/agent-council",
                "role_crew",
                council.status,
                "Proposal Manager",
                council,
                {
                    "agents": len(council.agents),
                    "handoffs": len(council.handoffs),
                    "tokens": council.budget_ledger.get("total_token_estimate"),
                },
            ),
            (
                "decision-provenance",
                "/proposal/decision-provenance",
                "decision_graph",
                provenance.status,
                "AI Governance Reviewer",
                provenance,
                {
                    "nodes": provenance.summary.get("node_count"),
                    "edges": provenance.summary.get("edge_count"),
                },
            ),
            (
                "submission-certification",
                "/proposal/submission-certification",
                "certification_gate",
                certification.status,
                "Executive Sponsor",
                certification,
                {
                    "readiness_score": certification.readiness_score,
                    "gates": len(certification.gates),
                    "review_items": len(certification.reviewer_queue),
                },
            ),
            (
                "proposal-observability",
                "/ops/proposal-observability",
                "observability_control",
                observability.status,
                "AI Governance Reviewer",
                observability,
                {
                    "trace_spans": observability.summary.get("trace_span_count"),
                    "human_review_signals": observability.summary.get("human_review_signal_count"),
                },
            ),
            (
                "quality-benchmark",
                "/proposal/quality-benchmark",
                "quality_benchmark",
                benchmark.status,
                "Platform Owner",
                benchmark,
                {
                    "score": benchmark.score,
                    "scenarios": benchmark.scenario_count,
                    "warnings": benchmark.warning_count,
                    "failures": benchmark.failed_count,
                },
            ),
            (
                "provider-resilience",
                "/ops/provider-resilience",
                "provider_route",
                provider_resilience.status,
                "Platform Owner",
                provider_resilience,
                {
                    "active_provider": provider_resilience.active_provider_mode,
                    "recommended_route": provider_resilience.recommended_route_id,
                    "external_provider_required": False,
                },
            ),
        ]
        return [
            ProposalAssuranceEvidenceItem(
                item_id=item_id,
                source_endpoint=source_endpoint,
                source_type=source_type,
                status=status,
                owner_role=owner_role,
                summary=summary,
                evidence_refs=self._evidence_refs(payload, source_endpoint),
                checksum=self._checksum(payload),
                blocking=self._blocking(status),
                reviewer_action=self._reviewer_action(status, owner_role),
            )
            for item_id, source_endpoint, source_type, status, owner_role, payload, summary in specs
        ]

    def _evidence_refs(self, payload: BaseModel, source_endpoint: str) -> list[str]:
        data = payload.model_dump(mode="json")
        refs = [source_endpoint]
        for key in ("trace_id", "workflow_id", "council_id", "provenance_id", "certification_id", "benchmark_id"):
            value = data.get(key)
            if value:
                refs.append(str(value))
        return refs[:8]

    def _checksum(self, payload: BaseModel) -> str:
        normalized = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _blocking(self, status: str) -> bool:
        return status in {"fail", "blocked", "blocked_by_governance"}

    def _reviewer_action(self, status: str, owner_role: str) -> str:
        if self._blocking(status):
            return f"{owner_role} must resolve this blocker before customer-facing submission."
        if status in {"needs_review", "needs_human_review", "needs_human_handoff", "pass_with_review_items"}:
            return f"{owner_role} should review and document the decision before final export."
        return "Retain this item as part of the local assurance evidence bundle."

    def _eval_assertions(
        self,
        items: list[ProposalAssuranceEvidenceItem],
        workflow: BuyerIntelligenceWorkflowResponse,
        replay: BuyerWorkflowReplayResponse,
        contract_audit: BuyerStructuredContractResponse,
        benchmark: ProposalQualityBenchmarkResponse,
    ) -> list[dict[str, Any]]:
        checksums = [item.checksum for item in items]
        return [
            {
                "assertion_id": "assurance-items-checksummed",
                "assertion": "every source control output has a stable checksum",
                "expected": len(items),
                "observed": sum(bool(checksum) for checksum in checksums),
                "passed": all(checksums) and len(checksums) == len(set(checksums)),
            },
            {
                "assertion_id": "assurance-required-artifacts-present",
                "assertion": (
                    "workflow, replay, contracts, council, provenance, certification, observability, "
                    "benchmark, and provider controls are bundled"
                ),
                "expected": 9,
                "observed": len(items),
                "passed": len(items) >= 9,
            },
            {
                "assertion_id": "assurance-contracts-and-benchmark-pass",
                "assertion": "typed contracts and benchmark eval assertions are usable for reviewer regression",
                "expected": "contract pass and benchmark score >= 80",
                "observed": {"contract_status": contract_audit.status, "benchmark_score": benchmark.score},
                "passed": contract_audit.status == "pass" and benchmark.score >= 80,
            },
            {
                "assertion_id": "assurance-checkpoints-replayable",
                "assertion": "buyer workflow stages and replay transitions retain checkpoint keys",
                "expected": len(workflow.workflow_stages) + replay.transition_count,
                "observed": sum(bool(stage.durability_key) for stage in workflow.workflow_stages)
                + sum(bool(transition.checkpoint_key) for transition in replay.transitions),
                "passed": all(stage.durability_key for stage in workflow.workflow_stages)
                and all(transition.checkpoint_key for transition in replay.transitions),
            },
            {
                "assertion_id": "assurance-provider-optional",
                "assertion": "assurance bundle does not require OpenAI or Azure OpenAI credentials",
                "expected": False,
                "observed": self.settings.provider_mode != "mock",
                "passed": self.settings.provider_mode == "mock",
            },
        ]

    def _score(self, items: list[ProposalAssuranceEvidenceItem], assertions: list[dict[str, Any]]) -> int:
        checksum_ratio = sum(bool(item.checksum) for item in items) / len(items) if items else 0
        assertion_ratio = sum(assertion["passed"] for assertion in assertions) / len(assertions) if assertions else 0
        blocker_penalty = min(12, sum(item.blocking for item in items) * 2)
        review_penalty = min(
            8,
            sum((not item.blocking) and "review" in item.reviewer_action for item in items),
        )
        return max(0, round(checksum_ratio * 40 + assertion_ratio * 60 - blocker_penalty - review_penalty))

    def _status(self, items: list[ProposalAssuranceEvidenceItem], assertions: list[dict[str, Any]], score: int) -> str:
        if any(item.blocking for item in items) or any(not assertion["passed"] for assertion in assertions):
            return "blocked_by_assurance"
        if score < 90 or any("review" in item.reviewer_action for item in items):
            return "ready_with_review_items"
        return "ready_for_buyer_review"

    def _control_summary(
        self,
        items: list[ProposalAssuranceEvidenceItem],
        assertions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        statuses = Counter(item.status for item in items)
        source_types = Counter(item.source_type for item in items)
        owners = Counter(item.owner_role for item in items)
        return {
            "artifact_count": len(items),
            "blocking_count": sum(item.blocking for item in items),
            "status_counts": dict(sorted(statuses.items())),
            "source_type_counts": dict(sorted(source_types.items())),
            "owner_counts": dict(sorted(owners.items())),
            "eval_assertion_count": len(assertions),
            "eval_assertions_passed": sum(assertion["passed"] for assertion in assertions),
            "radar_patterns_used": [
                "typed contracts",
                "structured outputs",
                "dependency injection",
                "eval-friendly design",
                "state machine workflow",
                "checkpointing",
                "traceable node transitions",
            ],
        }

    def _state_transitions(self, trace_id: str, items: list[ProposalAssuranceEvidenceItem]) -> list[dict[str, Any]]:
        transitions = []
        prior = "assurance_bundle_started"
        for sequence, item in enumerate(items, start=1):
            to_state = f"verify_{self._slug(item.item_id)}"
            transitions.append(
                {
                    "transition_id": f"assurance-transition-{sequence:02d}",
                    "sequence": sequence,
                    "from_state": prior,
                    "to_state": to_state,
                    "decision": (
                        "block"
                        if item.blocking
                        else "route_to_review"
                        if "review" in item.reviewer_action
                        else "accept"
                    ),
                    "condition": item.status,
                    "checkpoint_key": f"{self._slug(trace_id)}:{sequence:02d}:{to_state}",
                    "source_endpoint": item.source_endpoint,
                    "checksum": item.checksum,
                }
            )
            prior = to_state
        return transitions

    def _reviewer_queue(self, items: list[ProposalAssuranceEvidenceItem]) -> list[dict[str, Any]]:
        return [
            {
                "item_id": item.item_id,
                "owner_role": item.owner_role,
                "status": item.status,
                "blocking": item.blocking,
                "reviewer_action": item.reviewer_action,
                "source_endpoint": item.source_endpoint,
            }
            for item in items
            if item.blocking or "review" in item.reviewer_action
        ]

    def _injected_dependencies(self) -> dict[str, Any]:
        return {
            "service": "ProposalAssuranceBundleService",
            "settings_provider_mode": self.settings.provider_mode,
            "settings_vector_store_mode": self.settings.vector_store_mode,
            "storage_dir": str(self.settings.storage_dir),
            "external_provider_required": False,
        }

    def _pack_payload(self, trace_id: str, bundle: ProposalAssuranceBundleResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Proposal Assurance Bundle Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "assurance": bundle.model_dump(mode="json"),
            "reviewer_controls": [
                "Verify checksum rows before sharing generated artifacts with reviewers.",
                "Treat blocked assurance items as release blockers and review items as named owner tasks.",
                (
                    "Rebuild this bundle after changing buyer workflow, contracts, council, provenance, "
                    "certification, observability, benchmark, or provider routing."
                ),
                (
                    "Keep provider mode local/mock unless model, cost, privacy, and governance owners "
                    "explicitly approve external calls."
                ),
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        assurance = pack["assurance"]
        summary = assurance["control_summary"]
        lines = [
            "# Proposal Assurance Bundle Pack",
            "",
            "## Summary",
            "",
            f"- Status: {assurance['status']}",
            f"- Score: {assurance['score']}",
            f"- Artifacts: {summary['artifact_count']}",
            f"- Blocking items: {summary['blocking_count']}",
            f"- Eval assertions: {summary['eval_assertions_passed']}/{summary['eval_assertion_count']}",
            f"- Provider mode: {assurance['injected_dependencies']['settings_provider_mode']}",
            "",
            "## Artifact Manifest",
            "",
            "| Item | Endpoint | Status | Owner | Blocking | Checksum |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for item in assurance["artifact_manifest"]:
            lines.append(
                f"| {item['item_id']} | `{item['source_endpoint']}` | {item['status']} | "
                f"{self._md(item['owner_role'])} | {item['blocking']} | `{item['checksum'][:16]}` |"
            )
        lines.extend(["", "## Reviewer Queue", ""])
        if assurance["reviewer_queue"]:
            for item in assurance["reviewer_queue"]:
                lines.append(
                    f"- {item['item_id']} ({item['status']}): {self._md(item['reviewer_action'])}"
                )
        else:
            lines.append("- No open assurance review items.")
        lines.extend(["", "## State Transitions", ""])
        lines.append("| Seq | From | To | Decision | Checkpoint |")
        lines.append("| ---: | --- | --- | --- | --- |")
        for transition in assurance["state_transitions"]:
            lines.append(
                f"| {transition['sequence']} | {self._md(transition['from_state'])} | "
                f"{self._md(transition['to_state'])} | {transition['decision']} | "
                f"`{self._md(transition['checkpoint_key'])}` |"
            )
        lines.extend(["", "## Eval Assertions", ""])
        for assertion in assurance["eval_assertions"]:
            result = "pass" if assertion["passed"] else "fail"
            lines.append(f"- {assertion['assertion_id']} ({result}): {self._md(assertion['assertion'])}")
        lines.extend(["", "## Reviewer Controls", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_controls"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in assurance["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {self._md(item)}" for item in assurance["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Generated Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {"method": "GET", "path": "/proposal/assurance-bundle", "purpose": "View consolidated assurance ledger."},
            {"method": "POST", "path": "/proposal/assurance-bundle-pack", "purpose": "Write assurance artifacts."},
            {"method": "GET", "path": "/proposal/buyer-intelligence", "purpose": "Source durable buyer workflow."},
            {"method": "GET", "path": "/proposal/buyer-contracts", "purpose": "Source structured contracts."},
            {"method": "GET", "path": "/proposal/quality-benchmark", "purpose": "Source benchmark checks."},
            {"method": "GET", "path": "/ops/proposal-observability", "purpose": "Source observability controls."},
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/proposal/assurance-bundle" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/proposal/assurance-bundle-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'rg "proposal/assurance-bundle|Proposal Assurance Bundle|proposal_assurance" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\proposal_assurance -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            (
                "The bundle records local deterministic control outputs; it does not replace a legal or "
                "procurement approval system."
            ),
            "Checksums prove local structured payload integrity for this run, not long-term notarization.",
            "Reviewer queue items must be reconciled with real sales, compliance, and procurement owners.",
            "OpenAI, Azure OpenAI, CRM, GRC, procurement, and ticketing systems remain optional and are not called.",
        ]

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower() or "local"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
