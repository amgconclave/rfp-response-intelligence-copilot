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
    ProposalAgentCouncilResponse,
    ProposalDecisionProvenanceResponse,
    ProposalObservabilityPackResponse,
    ProposalObservabilityResponse,
    RetrievalExperimentResponse,
)
from app.models.domain import AuditEvent, UsageMetric


class ProposalObservabilityService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def report(
        self,
        trace_id: str,
        workflow: BuyerIntelligenceWorkflowResponse,
        replay: BuyerWorkflowReplayResponse,
        council: ProposalAgentCouncilResponse,
        provenance: ProposalDecisionProvenanceResponse,
        retrieval_experiment: RetrievalExperimentResponse,
        cost_governance: CostGovernanceResponse,
        usage_metrics: list[UsageMetric],
        audit_events: list[AuditEvent],
    ) -> ProposalObservabilityResponse:
        trace_map = self._trace_map(workflow, replay, council, provenance, retrieval_experiment)
        retrieval_diagnostics = self._retrieval_diagnostics(retrieval_experiment)
        governance_findings = self._governance_findings(workflow, council, provenance, retrieval_experiment)
        human_review_signals = self._human_review_signals(workflow, council, provenance)
        summary = self._summary(
            trace_map,
            retrieval_diagnostics,
            governance_findings,
            human_review_signals,
            usage_metrics,
            audit_events,
        )
        return ProposalObservabilityResponse(
            title="Proposal Observability Control Plane",
            status=self._status(summary, retrieval_experiment, governance_findings, human_review_signals),
            generated_at=datetime.now(UTC).isoformat(),
            summary=summary,
            trace_map=trace_map,
            retrieval_diagnostics=retrieval_diagnostics,
            experiment_comparison=self._experiment_comparison(retrieval_experiment),
            provider_and_cost_signals=self._provider_and_cost_signals(cost_governance, usage_metrics),
            governance_findings=governance_findings,
            human_review_signals=human_review_signals,
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        observability: ProposalObservabilityResponse,
        write_artifact: bool = True,
    ) -> ProposalObservabilityPackResponse:
        pack = self._pack_payload(trace_id, observability)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "proposal_observability"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = self._slug(trace_id)
            markdown_path = pack_dir / f"proposal_observability_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"proposal_observability_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["proposal_observability_markdown"] = artifact_path
            pack["artifact_paths"]["proposal_observability_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return ProposalObservabilityPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            observability=observability,
            trace_id=trace_id,
        )

    def _trace_map(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        replay: BuyerWorkflowReplayResponse,
        council: ProposalAgentCouncilResponse,
        provenance: ProposalDecisionProvenanceResponse,
        retrieval_experiment: RetrievalExperimentResponse,
    ) -> list[dict[str, Any]]:
        rows = [
            {
                "trace_type": "workflow_stage",
                "trace_id": workflow.trace_id,
                "span_id": stage.stage_id,
                "status": stage.status,
                "owner_role": stage.owner_role,
                "evidence": stage.durability_key,
                "source": "/proposal/buyer-intelligence",
            }
            for stage in workflow.workflow_stages
        ]
        rows.extend(
            {
                "trace_type": "workflow_transition",
                "trace_id": replay.trace_id,
                "span_id": transition.transition_id,
                "status": transition.status,
                "owner_role": "Platform Owner",
                "evidence": transition.checkpoint_key,
                "source": "/proposal/buyer-intelligence-replay",
            }
            for transition in replay.transitions
        )
        rows.extend(
            {
                "trace_type": "agent_turn",
                "trace_id": council.trace_id,
                "span_id": message.message_id,
                "status": "needs_review" if message.governance_flags else "complete",
                "owner_role": message.role,
                "evidence": ", ".join(message.governance_flags) or "governed_turn",
                "source": "/proposal/agent-council",
            }
            for message in council.conversation
        )
        rows.extend(
            {
                "trace_type": "provenance_node",
                "trace_id": provenance.trace_id,
                "span_id": node.node_id,
                "status": node.status,
                "owner_role": node.owner_role or "n/a",
                "evidence": node.evidence[:180],
                "source": "/proposal/decision-provenance",
            }
            for node in provenance.nodes
        )
        rows.extend(
            {
                "trace_type": "retrieval_experiment",
                "trace_id": retrieval_experiment.trace_id,
                "span_id": span["span_id"],
                "status": retrieval_experiment.status,
                "owner_role": retrieval_experiment.governance_decision["owner"],
                "evidence": f"{span['policy_id']} duration={span['duration_ms']}ms",
                "source": "/rag/retrieval-experiments",
            }
            for span in retrieval_experiment.trace_spans
        )
        return rows

    def _retrieval_diagnostics(self, retrieval_experiment: RetrievalExperimentResponse) -> list[dict[str, Any]]:
        risky = [
            row
            for row in retrieval_experiment.question_diagnostics
            if row.get("unsupported_risk") or row.get("guardrails_triggered") or not row.get("citation_hit")
        ]
        return sorted(
            risky,
            key=lambda row: (
                not bool(row.get("unsupported_risk")),
                -len(row.get("guardrails_triggered", [])),
                row.get("precision_at_k", 0.0),
            ),
        )[:12]

    def _experiment_comparison(self, retrieval_experiment: RetrievalExperimentResponse) -> dict[str, Any]:
        return {
            "status": retrieval_experiment.status,
            "recommended_policy_id": retrieval_experiment.recommended_policy_id,
            "score_delta_vs_baseline": retrieval_experiment.governance_decision["score_delta_vs_baseline"],
            "policy_count": retrieval_experiment.summary["policy_count"],
            "question_count": retrieval_experiment.summary["question_count"],
            "policy_results": retrieval_experiment.policy_results,
            "governance_decision": retrieval_experiment.governance_decision,
        }

    def _provider_and_cost_signals(
        self,
        cost_governance: CostGovernanceResponse,
        usage_metrics: list[UsageMetric],
    ) -> dict[str, Any]:
        providers = Counter(metric.provider for metric in usage_metrics)
        endpoints = Counter(metric.endpoint or "unknown" for metric in usage_metrics)
        return {
            "provider_mode": cost_governance.provider_readiness["provider_mode"],
            "local_mock_default": cost_governance.provider_readiness["local_mock_ready"],
            "external_provider_requested": cost_governance.provider_readiness["external_provider_requested"],
            "budget_status": cost_governance.governance_status,
            "daily_estimated_cost": cost_governance.budget_summary["daily_estimated_cost"],
            "budget_utilization": cost_governance.budget_summary["budget_utilization"],
            "observed_provider_counts": dict(sorted(providers.items())),
            "observed_endpoint_counts": dict(sorted(endpoints.items())),
            "metric_count": len(usage_metrics),
        }

    def _governance_findings(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        council: ProposalAgentCouncilResponse,
        provenance: ProposalDecisionProvenanceResponse,
        retrieval_experiment: RetrievalExperimentResponse,
    ) -> list[dict[str, Any]]:
        rows = [
            {
                "finding_id": gate.gate_id,
                "category": "workflow_gate",
                "status": gate.status,
                "owner_role": gate.owner_role,
                "evidence": gate.evidence,
                "required_action": gate.required_action,
            }
            for gate in workflow.governance_gates
            if gate.status != "pass"
        ]
        rows.extend(
            {
                "finding_id": control["control_id"],
                "category": "decision_control",
                "status": control["status"],
                "owner_role": control["owner_role"],
                "evidence": control["evidence"],
                "required_action": "Resolve before external submission.",
            }
            for control in provenance.decision_controls
            if control["status"] != "pass"
        )
        rows.extend(
            {
                "finding_id": row["agent_id"],
                "category": "tool_governance",
                "status": row["policy"],
                "owner_role": row["role"],
                "evidence": f"blocked_tools={', '.join(row['blocked_tools'])}",
                "required_action": "Keep blocked tools unavailable unless owner approval is recorded.",
            }
            for row in council.tool_governance
            if row["policy"] == "blocked"
        )
        if retrieval_experiment.governance_decision["approval_required"]:
            rows.append(
                {
                    "finding_id": "retrieval-policy-approval",
                    "category": "retrieval_experiment",
                    "status": retrieval_experiment.status,
                    "owner_role": retrieval_experiment.governance_decision["owner"],
                    "evidence": retrieval_experiment.governance_decision["next_step"],
                    "required_action": "Review retrieval diagnostics before shadow rollout.",
                }
            )
        return rows

    def _human_review_signals(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        council: ProposalAgentCouncilResponse,
        provenance: ProposalDecisionProvenanceResponse,
    ) -> list[dict[str, Any]]:
        rows = [
            {
                "signal_id": item.approval_id,
                "signal_type": "approval_queue",
                "owner_role": item.reviewer_role,
                "status": item.status,
                "priority": item.priority,
                "decision_area": item.decision_area,
                "required_before": item.required_before,
            }
            for item in workflow.human_approval_queue
        ]
        rows.extend(
            {
                "signal_id": handoff.handoff_id,
                "signal_type": "agent_handoff",
                "owner_role": handoff.to_agent_id,
                "status": handoff.status,
                "priority": "high" if handoff.status == "open" else "medium",
                "decision_area": handoff.reason[:180],
                "required_before": handoff.required_before,
            }
            for handoff in council.handoffs
        )
        rows.extend(
            {
                "signal_id": node.node_id,
                "signal_type": node.node_type,
                "owner_role": node.owner_role or "n/a",
                "status": node.status,
                "priority": "high" if node.status in {"blocked", "open", "needs_review"} else "medium",
                "decision_area": node.label,
                "required_before": "final response submission",
            }
            for node in provenance.nodes
            if node.status in {"blocked", "open", "needs_review", "waiting_on_approvals"}
        )
        return rows

    def _summary(
        self,
        trace_map: list[dict[str, Any]],
        diagnostics: list[dict[str, Any]],
        governance_findings: list[dict[str, Any]],
        human_review_signals: list[dict[str, Any]],
        usage_metrics: list[UsageMetric],
        audit_events: list[AuditEvent],
    ) -> dict[str, Any]:
        trace_types = Counter(row["trace_type"] for row in trace_map)
        statuses = Counter(row["status"] for row in trace_map)
        return {
            "trace_span_count": len(trace_map),
            "trace_type_counts": dict(sorted(trace_types.items())),
            "trace_status_counts": dict(sorted(statuses.items())),
            "retrieval_diagnostic_count": len(diagnostics),
            "unsupported_risk_count": sum(1 for row in diagnostics if row.get("unsupported_risk")),
            "guardrail_trigger_count": sum(1 for row in diagnostics if row.get("guardrails_triggered")),
            "governance_finding_count": len(governance_findings),
            "human_review_signal_count": len(human_review_signals),
            "usage_metric_count": len(usage_metrics),
            "audit_event_count": len(audit_events),
            "radar_patterns_used": [
                "trace analysis",
                "retrieval diagnostics",
                "experiment comparison",
                "governance",
                "human-in-the-loop",
                "provider flexibility",
            ],
        }

    def _status(
        self,
        summary: dict[str, Any],
        retrieval_experiment: RetrievalExperimentResponse,
        governance_findings: list[dict[str, Any]],
        human_review_signals: list[dict[str, Any]],
    ) -> str:
        if any(row["status"] == "blocked" for row in governance_findings):
            return "blocked_by_governance"
        if retrieval_experiment.status == "human_review_required":
            return "needs_retrieval_review"
        if human_review_signals or governance_findings:
            return "needs_human_review"
        if summary["trace_span_count"] < 10:
            return "insufficient_trace_coverage"
        return "ready_for_observability_review"

    def _pack_payload(self, trace_id: str, observability: ProposalObservabilityResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Proposal Observability Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "observability": observability.model_dump(mode="json"),
            "reviewer_controls": [
                "Review unsupported-risk diagnostics before changing retrieval policy.",
                "Clear human-review signals before external response submission.",
                "Keep local mock mode as the default unless provider, cost, privacy, and model-risk gates pass.",
                "Regenerate after changing retrieval policy, buyer workflow, agent council, or governance rules.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        observability = pack["observability"]
        summary = observability["summary"]
        experiment = observability["experiment_comparison"]
        provider = observability["provider_and_cost_signals"]
        lines = [
            "# Proposal Observability Pack",
            "",
            "## Summary",
            "",
            f"- Status: {observability['status']}",
            f"- Trace spans: {summary['trace_span_count']}",
            f"- Retrieval diagnostics: {summary['retrieval_diagnostic_count']}",
            f"- Governance findings: {summary['governance_finding_count']}",
            f"- Human review signals: {summary['human_review_signal_count']}",
            f"- Provider mode: {provider['provider_mode']}",
            f"- Recommended retrieval policy: {experiment['recommended_policy_id']}",
            "",
            "## Trace Map",
            "",
            "| Type | Span | Status | Owner | Source |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in observability["trace_map"][:20]:
            lines.append(
                f"| {row['trace_type']} | `{self._md(row['span_id'])}` | {row['status']} | "
                f"{self._md(row['owner_role'])} | `{row['source']}` |"
            )
        lines.extend(["", "## Retrieval Diagnostics", ""])
        if observability["retrieval_diagnostics"]:
            lines.append("| Diagnostic | Policy | Citation hit | Unsupported risk | Guardrails |")
            lines.append("| --- | --- | --- | --- | --- |")
            for row in observability["retrieval_diagnostics"]:
                lines.append(
                    f"| {row['diagnostic_id']} | {row['policy_id']} | {row['citation_hit']} | "
                    f"{row['unsupported_risk']} | {self._md(', '.join(row['guardrails_triggered']))} |"
                )
        else:
            lines.append("- No risky retrieval diagnostics in the current comparison.")
        lines.extend(["", "## Governance Findings", ""])
        if observability["governance_findings"]:
            for row in observability["governance_findings"]:
                lines.append(
                    f"- {row['finding_id']} ({row['status']}): {self._md(row['required_action'])} "
                    f"Owner: {self._md(row['owner_role'])}"
                )
        else:
            lines.append("- No open governance findings.")
        lines.extend(["", "## Human Review Signals", ""])
        if observability["human_review_signals"]:
            for row in observability["human_review_signals"][:20]:
                lines.append(
                    f"- {row['signal_id']} ({row['status']}): {self._md(row['owner_role'])} "
                    f"before {self._md(row['required_before'])}"
                )
        else:
            lines.append("- No open human review signals.")
        lines.extend(["", "## Reviewer Controls", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_controls"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in observability["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {self._md(item)}" for item in observability["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Generated Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/ops/proposal-observability" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/ops/proposal-observability-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            (
                'rg "proposal-observability|Proposal Observability|proposal_observability" '
                "app dashboard docs README.md tests Makefile"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Trace spans are deterministic local control records, not exported to a live tracing backend.",
            "Retrieval diagnostics use sample eval fixtures and fake win/loss outcomes.",
            "Human-review signals model local approval queues and must be reconciled with real reviewer systems.",
            "Provider and cost signals keep OpenAI and Azure optional; no external provider is called by default.",
        ]

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower() or "local"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
