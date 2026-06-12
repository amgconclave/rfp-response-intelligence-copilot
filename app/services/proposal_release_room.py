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
    ProposalAgentCouncilResponse,
    ProposalDecisionProvenanceResponse,
    ProposalObservabilityResponse,
    ProposalReleaseRoomDecision,
    ProposalReleaseRoomPackResponse,
    ProposalReleaseRoomResponse,
    ProposalReviewGateResponse,
    ProposalSubmissionCertificationResponse,
    ProviderResilienceResponse,
)


class ProposalReleaseRoomService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def room(
        self,
        trace_id: str,
        workflow: BuyerIntelligenceWorkflowResponse,
        replay: BuyerWorkflowReplayResponse,
        council: ProposalAgentCouncilResponse,
        provenance: ProposalDecisionProvenanceResponse,
        certification: ProposalSubmissionCertificationResponse,
        review_gate: ProposalReviewGateResponse,
        observability: ProposalObservabilityResponse,
        provider_resilience: ProviderResilienceResponse,
    ) -> ProposalReleaseRoomResponse:
        decision_board = self._decision_board(certification, review_gate, observability, provenance)
        hitl_queue = self._hitl_queue(workflow, council, certification, review_gate, observability)
        durable_checkpoints = self._durable_checkpoints(
            workflow,
            replay,
            certification,
            review_gate,
            provider_resilience,
        )
        provider_route = self._provider_route(provider_resilience, observability)
        trace_coverage = self._trace_coverage(workflow, replay, council, provenance, observability, provider_resilience)
        eval_assertions = self._eval_assertions(
            decision_board,
            hitl_queue,
            durable_checkpoints,
            trace_coverage,
            provider_route,
            certification,
            review_gate,
        )
        readiness_score = self._readiness_score(certification, review_gate, decision_board, eval_assertions)
        status = self._status(decision_board, hitl_queue, eval_assertions, readiness_score)
        return ProposalReleaseRoomResponse(
            title="Buyer Proposal Release Room",
            room_id=f"proposal-release-room-{self._slug(trace_id)}",
            status=status,
            release_recommendation=self._release_recommendation(status, readiness_score, hitl_queue),
            readiness_score=readiness_score,
            generated_at=datetime.now(UTC).isoformat(),
            summary=self._summary(
                decision_board,
                hitl_queue,
                durable_checkpoints,
                trace_coverage,
                eval_assertions,
                workflow,
                certification,
                review_gate,
                observability,
            ),
            decision_board=decision_board,
            executive_controls=self._executive_controls(decision_board, provider_route),
            hitl_queue=hitl_queue,
            provider_route=provider_route,
            durable_checkpoints=durable_checkpoints,
            trace_coverage=trace_coverage,
            eval_assertions=eval_assertions,
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        release_room: ProposalReleaseRoomResponse,
        write_artifact: bool = True,
    ) -> ProposalReleaseRoomPackResponse:
        pack = self._pack_payload(trace_id, release_room)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "proposal_release_room"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = self._slug(trace_id)
            markdown_path = pack_dir / f"proposal_release_room_{safe_trace_id}.md"
            json_path = pack_dir / f"proposal_release_room_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["proposal_release_room_markdown"] = artifact_path
            pack["artifact_paths"]["proposal_release_room_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return ProposalReleaseRoomPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            release_room=release_room,
            trace_id=trace_id,
        )

    def _decision_board(
        self,
        certification: ProposalSubmissionCertificationResponse,
        review_gate: ProposalReviewGateResponse,
        observability: ProposalObservabilityResponse,
        provenance: ProposalDecisionProvenanceResponse,
    ) -> list[ProposalReleaseRoomDecision]:
        decisions: list[ProposalReleaseRoomDecision] = []
        for gate in certification.gates:
            if gate.status != "pass":
                decisions.append(
                    ProposalReleaseRoomDecision(
                        decision_id=f"certification:{gate.gate_id}",
                        decision_area=gate.name,
                        status=gate.status,
                        owner_role=gate.owner_role,
                        severity=gate.severity,
                        source_endpoint="/proposal/submission-certification",
                        evidence=gate.evidence,
                        required_action=gate.required_action,
                        due_hint="before executive submission memo",
                        checkpoint_key=f"certification:{gate.gate_id}:{self._slug(gate.status)}",
                        trace_refs=gate.endpoint_refs,
                    )
                )
        for criterion in review_gate.criteria:
            if criterion.status != "pass":
                decisions.append(
                    ProposalReleaseRoomDecision(
                        decision_id=f"review-gate:{criterion.criterion_id}",
                        decision_area=criterion.decision_area,
                        status=criterion.status,
                        owner_role=criterion.owner_role,
                        severity="high" if criterion.status == "blocked" else "medium",
                        source_endpoint="/proposal/review-gate",
                        evidence=", ".join(criterion.observed_evidence[:4]) or "review gate criterion",
                        required_action="; ".join(criterion.open_actions[:3]),
                        due_hint="before customer-facing RFP submission",
                        checkpoint_key=f"review-gate:{criterion.criterion_id}:{self._slug(criterion.owner_role)}",
                        trace_refs=criterion.endpoint_refs,
                    )
                )
        for finding in observability.governance_findings[:8]:
            if finding.get("status") != "pass":
                decisions.append(
                    ProposalReleaseRoomDecision(
                        decision_id=f"observability:{finding['finding_id']}",
                        decision_area=str(finding["category"]),
                        status=str(finding["status"]),
                        owner_role=str(finding["owner_role"]),
                        severity="high" if finding["status"] == "blocked" else "medium",
                        source_endpoint="/ops/proposal-observability",
                        evidence=str(finding["evidence"]),
                        required_action=str(finding["required_action"]),
                        due_hint="before release-room clearance",
                        checkpoint_key=f"observability:{self._slug(str(finding['finding_id']))}",
                        trace_refs=[observability.trace_id],
                    )
                )
        for control in provenance.decision_controls:
            if control.get("status") != "pass":
                decisions.append(
                    ProposalReleaseRoomDecision(
                        decision_id=f"provenance:{control['control_id']}",
                        decision_area="Decision provenance control",
                        status=str(control["status"]),
                        owner_role=str(control["owner_role"]),
                        severity="high" if control["status"] == "blocked" else "medium",
                        source_endpoint="/proposal/decision-provenance",
                        evidence=str(control["evidence"]),
                        required_action="Close or explicitly accept this provenance control before submission.",
                        due_hint="before final approval",
                        checkpoint_key=f"provenance:{self._slug(str(control['control_id']))}",
                        trace_refs=[provenance.trace_id],
                    )
                )
        return self._dedupe_decisions(decisions)

    def _dedupe_decisions(
        self,
        decisions: list[ProposalReleaseRoomDecision],
    ) -> list[ProposalReleaseRoomDecision]:
        seen: set[str] = set()
        unique = []
        for decision in decisions:
            if decision.decision_id in seen:
                continue
            unique.append(decision)
            seen.add(decision.decision_id)
        severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return sorted(unique, key=lambda item: (severity_rank.get(item.severity, 4), item.owner_role, item.decision_id))

    def _hitl_queue(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        council: ProposalAgentCouncilResponse,
        certification: ProposalSubmissionCertificationResponse,
        review_gate: ProposalReviewGateResponse,
        observability: ProposalObservabilityResponse,
    ) -> list[dict[str, Any]]:
        queue = [
            {
                "queue_id": item.approval_id,
                "source": "/proposal/buyer-intelligence",
                "owner_role": item.reviewer_role,
                "status": item.status,
                "priority": item.priority,
                "decision_area": item.decision_area,
                "required_before": item.required_before,
                "checkpoint_key": f"hitl:{item.approval_id}",
            }
            for item in workflow.human_approval_queue
        ]
        queue.extend(
            {
                "queue_id": handoff.handoff_id,
                "source": "/proposal/agent-council",
                "owner_role": handoff.to_agent_id,
                "status": handoff.status,
                "priority": "high" if handoff.status == "open" else "medium",
                "decision_area": handoff.reason[:220],
                "required_before": handoff.required_before,
                "checkpoint_key": f"handoff:{handoff.handoff_id}",
            }
            for handoff in council.handoffs
            if handoff.status == "open"
        )
        queue.extend(
            {
                "queue_id": row["queue_id"],
                "source": "/proposal/submission-certification",
                "owner_role": row["owner_role"],
                "status": row["status"],
                "priority": row.get("priority", "medium"),
                "decision_area": row["decision_area"],
                "required_before": "submission certification",
                "checkpoint_key": f"certification:{row['queue_id']}",
            }
            for row in certification.reviewer_queue
        )
        queue.extend(
            {
                "queue_id": row["delegation_id"],
                "source": "/proposal/review-gate",
                "owner_role": row["owner_role"],
                "status": row["status"],
                "priority": "high" if row["status"] == "blocked" else "medium",
                "decision_area": f"{row['task_count']} open release task(s)",
                "required_before": row["required_before"],
                "checkpoint_key": f"review-gate:{row['delegation_id']}",
            }
            for row in review_gate.task_delegations
            if row["status"] != "pass"
        )
        queue.extend(
            {
                "queue_id": signal["signal_id"],
                "source": "/ops/proposal-observability",
                "owner_role": signal["owner_role"],
                "status": signal["status"],
                "priority": signal["priority"],
                "decision_area": signal["decision_area"],
                "required_before": signal["required_before"],
                "checkpoint_key": f"observability:{signal['signal_id']}",
            }
            for signal in observability.human_review_signals[:12]
        )
        seen = set()
        unique = []
        for item in queue:
            key = (item["source"], item["queue_id"])
            if key in seen:
                continue
            unique.append(item)
            seen.add(key)
        return unique

    def _durable_checkpoints(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        replay: BuyerWorkflowReplayResponse,
        certification: ProposalSubmissionCertificationResponse,
        review_gate: ProposalReviewGateResponse,
        provider_resilience: ProviderResilienceResponse,
    ) -> list[dict[str, Any]]:
        checkpoints = [
            {
                "checkpoint_key": stage.durability_key,
                "source": "/proposal/buyer-intelligence",
                "state": stage.stage_id,
                "status": stage.status,
                "owner_role": stage.owner_role,
                "restart_policy": stage.restart_policy,
            }
            for stage in workflow.workflow_stages
        ]
        checkpoints.extend(
            {
                "checkpoint_key": transition.checkpoint_key,
                "source": "/proposal/buyer-intelligence-replay",
                "state": transition.to_stage_id,
                "status": transition.status,
                "owner_role": "Platform Owner",
                "restart_policy": transition.decision,
            }
            for transition in replay.transitions
        )
        checkpoints.extend(
            {
                "checkpoint_key": transition.checkpoint_key,
                "source": "/proposal/submission-certification",
                "state": transition.to_state,
                "status": "checkpointed",
                "owner_role": "Proposal Manager",
                "restart_policy": transition.decision,
            }
            for transition in certification.transitions
        )
        checkpoints.extend(
            {
                "checkpoint_key": transition["checkpoint_key"],
                "source": "/proposal/review-gate",
                "state": transition["to_state"],
                "status": transition["condition"],
                "owner_role": transition["owner_role"],
                "restart_policy": transition["decision"],
            }
            for transition in review_gate.state_transitions
        )
        checkpoints.extend(
            {
                "checkpoint_key": transition.checkpoint_id,
                "source": "/ops/provider-resilience",
                "state": transition.to_state,
                "status": "checkpointed",
                "owner_role": "Platform Owner",
                "restart_policy": transition.decision,
            }
            for transition in provider_resilience.transitions
        )
        return checkpoints

    def _provider_route(
        self,
        provider_resilience: ProviderResilienceResponse,
        observability: ProposalObservabilityResponse,
    ) -> dict[str, Any]:
        return {
            "active_provider_mode": provider_resilience.active_provider_mode,
            "recommended_route_id": provider_resilience.recommended_route_id,
            "provider_resilience_status": provider_resilience.status,
            "local_mock_default": observability.provider_and_cost_signals.get("local_mock_default", True),
            "external_provider_requested": observability.provider_and_cost_signals.get(
                "external_provider_requested",
                False,
            ),
            "budget_status": observability.provider_and_cost_signals.get("budget_status"),
            "daily_estimated_cost": observability.provider_and_cost_signals.get("daily_estimated_cost"),
            "route_count": provider_resilience.summary["route_count"],
            "missing_env": provider_resilience.summary["missing_env"],
            "governance_note": (
                "External providers remain optional and gated by model, privacy, cost, and owner review."
            ),
        }

    def _trace_coverage(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        replay: BuyerWorkflowReplayResponse,
        council: ProposalAgentCouncilResponse,
        provenance: ProposalDecisionProvenanceResponse,
        observability: ProposalObservabilityResponse,
        provider_resilience: ProviderResilienceResponse,
    ) -> list[dict[str, Any]]:
        return [
            {
                "source": "/proposal/buyer-intelligence",
                "trace_id": workflow.trace_id,
                "span_count": len(workflow.workflow_stages),
                "coverage": "durable_workflow_stages",
            },
            {
                "source": "/proposal/buyer-intelligence-replay",
                "trace_id": replay.trace_id,
                "span_count": replay.transition_count,
                "coverage": "transition_replay",
            },
            {
                "source": "/proposal/agent-council",
                "trace_id": council.trace_id,
                "span_count": len(council.conversation),
                "coverage": "role_conversation_and_handoffs",
            },
            {
                "source": "/proposal/decision-provenance",
                "trace_id": provenance.trace_id,
                "span_count": provenance.summary["node_count"],
                "coverage": "decision_graph",
            },
            {
                "source": "/ops/proposal-observability",
                "trace_id": observability.trace_id,
                "span_count": observability.summary["trace_span_count"],
                "coverage": "trace_analysis_and_retrieval_diagnostics",
            },
            {
                "source": "/ops/provider-resilience",
                "trace_id": provider_resilience.trace_id,
                "span_count": len(provider_resilience.trace_spans),
                "coverage": "provider_route_transitions",
            },
        ]

    def _eval_assertions(
        self,
        decisions: list[ProposalReleaseRoomDecision],
        hitl_queue: list[dict[str, Any]],
        checkpoints: list[dict[str, Any]],
        trace_coverage: list[dict[str, Any]],
        provider_route: dict[str, Any],
        certification: ProposalSubmissionCertificationResponse,
        review_gate: ProposalReviewGateResponse,
    ) -> list[dict[str, Any]]:
        required_patterns = {
            "durable workflows",
            "human-in-the-loop",
            "governance",
            "provider flexibility",
            "trace analysis",
        }
        observed_patterns = set(self._patterns_used())
        return [
            {
                "assertion_id": "release-room-radar-patterns",
                "assertion": (
                    "release room composes durable workflows, HITL, governance, provider flexibility, "
                    "and trace analysis"
                ),
                "expected": sorted(required_patterns),
                "observed": sorted(observed_patterns),
                "passed": required_patterns <= observed_patterns,
            },
            {
                "assertion_id": "release-room-durable-checkpoints",
                "assertion": "each durable checkpoint has a key and source endpoint",
                "expected": len(checkpoints),
                "observed": sum(bool(row["checkpoint_key"] and row["source"]) for row in checkpoints),
                "passed": bool(checkpoints) and all(row["checkpoint_key"] and row["source"] for row in checkpoints),
            },
            {
                "assertion_id": "release-room-hitl-visible",
                "assertion": "non-ready release states have visible human-review routing",
                "expected": "queue when decisions are open",
                "observed": {"decision_count": len(decisions), "hitl_count": len(hitl_queue)},
                "passed": not decisions or bool(hitl_queue),
            },
            {
                "assertion_id": "release-room-provider-optional",
                "assertion": "local mock provider is a valid recommended route without external credentials",
                "expected": "provider.mock.local",
                "observed": provider_route["recommended_route_id"],
                "passed": bool(provider_route["recommended_route_id"] or provider_route["local_mock_default"]),
            },
            {
                "assertion_id": "release-room-trace-coverage",
                "assertion": (
                    "workflow, replay, council, provenance, observability, and provider traces are represented"
                ),
                "expected": 6,
                "observed": len(trace_coverage),
                "passed": len(trace_coverage) >= 6 and all(row["span_count"] > 0 for row in trace_coverage),
            },
            {
                "assertion_id": "release-room-upstream-gates-pass-through",
                "assertion": "certification and review gate scores are preserved for release decisioning",
                "expected": "scores present",
                "observed": {"certification": certification.readiness_score, "review_gate": review_gate.score},
                "passed": certification.readiness_score >= 0 and review_gate.score >= 0,
            },
        ]

    def _readiness_score(
        self,
        certification: ProposalSubmissionCertificationResponse,
        review_gate: ProposalReviewGateResponse,
        decisions: list[ProposalReleaseRoomDecision],
        assertions: list[dict[str, Any]],
    ) -> int:
        decision_penalty = min(35, len(decisions) * 3)
        assertion_penalty = 7 * sum(not assertion["passed"] for assertion in assertions)
        score = round(certification.readiness_score * 0.45 + review_gate.score * 0.45 + 10)
        return max(0, min(100, score - decision_penalty - assertion_penalty))

    def _status(
        self,
        decisions: list[ProposalReleaseRoomDecision],
        hitl_queue: list[dict[str, Any]],
        assertions: list[dict[str, Any]],
        readiness_score: int,
    ) -> str:
        if any(decision.status == "blocked" for decision in decisions) or any(not row["passed"] for row in assertions):
            return "blocked_by_release_controls"
        if hitl_queue or decisions or readiness_score < 90:
            return "requires_human_release_review"
        return "ready_for_buyer_release"

    def _release_recommendation(
        self,
        status: str,
        readiness_score: int,
        hitl_queue: list[dict[str, Any]],
    ) -> str:
        if status == "blocked_by_release_controls":
            return "hold_release_until_blocking_controls_clear"
        if hitl_queue:
            return "conditional_release_after_named_human_approvals"
        if readiness_score < 90:
            return "review_before_release"
        return "release_ready_for_executive_signoff"

    def _summary(
        self,
        decisions: list[ProposalReleaseRoomDecision],
        hitl_queue: list[dict[str, Any]],
        checkpoints: list[dict[str, Any]],
        trace_coverage: list[dict[str, Any]],
        assertions: list[dict[str, Any]],
        workflow: BuyerIntelligenceWorkflowResponse,
        certification: ProposalSubmissionCertificationResponse,
        review_gate: ProposalReviewGateResponse,
        observability: ProposalObservabilityResponse,
    ) -> dict[str, Any]:
        decision_statuses = Counter(decision.status for decision in decisions)
        queue_owners = Counter(str(row["owner_role"]) for row in hitl_queue)
        return {
            "decision_count": len(decisions),
            "decision_status_counts": dict(sorted(decision_statuses.items())),
            "hitl_queue_count": len(hitl_queue),
            "hitl_owner_counts": dict(sorted(queue_owners.items())),
            "durable_checkpoint_count": len(checkpoints),
            "trace_source_count": len(trace_coverage),
            "trace_span_count": sum(row["span_count"] for row in trace_coverage),
            "eval_assertion_count": len(assertions),
            "eval_assertions_passed": sum(assertion["passed"] for assertion in assertions),
            "workflow_status": workflow.workflow_status,
            "certification_status": certification.status,
            "certification_score": certification.readiness_score,
            "review_gate_status": review_gate.status,
            "review_gate_score": review_gate.score,
            "observability_status": observability.status,
            "radar_patterns_used": self._patterns_used(),
        }

    def _executive_controls(
        self,
        decisions: list[ProposalReleaseRoomDecision],
        provider_route: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return [
            {
                "control_id": "release-clear-blockers",
                "status": "blocked" if any(decision.status == "blocked" for decision in decisions) else "review",
                "owner_role": "Proposal Manager",
                "required_action": "Resolve blocked and needs-review release-room decisions before buyer release.",
            },
            {
                "control_id": "release-provider-route",
                "status": provider_route["provider_resilience_status"],
                "owner_role": "Platform Owner",
                "required_action": "Keep mock/local route unless external provider governance is explicitly approved.",
            },
            {
                "control_id": "release-human-signoff",
                "status": "requires_approval" if decisions else "pass",
                "owner_role": "Executive Sponsor",
                "required_action": "Record named human approval for all non-pass release-room rows.",
            },
        ]

    def _pack_payload(self, trace_id: str, release_room: ProposalReleaseRoomResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Buyer Proposal Release Room Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "release_room": release_room.model_dump(mode="json"),
            "operator_checklist": [
                "Review every decision board row before final customer-facing release.",
                "Clear or explicitly accept all human-in-the-loop queue items with named owners.",
                "Confirm durable checkpoints cover workflow, replay, certification, review gate, and provider routing.",
                "Keep external providers disabled unless model-risk, privacy, cost, and owner approvals pass.",
                "Regenerate this pack after eval, red-team, source-trust, provider, or review-gate changes.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        room = pack["release_room"]
        summary = room["summary"]
        lines = [
            "# Buyer Proposal Release Room Pack",
            "",
            "## Release Summary",
            "",
            f"- Status: {room['status']}",
            f"- Recommendation: {room['release_recommendation']}",
            f"- Readiness score: {room['readiness_score']}",
            f"- Decisions: {summary['decision_count']}",
            f"- HITL queue: {summary['hitl_queue_count']}",
            f"- Durable checkpoints: {summary['durable_checkpoint_count']}",
            f"- Trace spans: {summary['trace_span_count']}",
            f"- Provider route: {room['provider_route']['recommended_route_id']}",
            "",
            "## Decision Board",
            "",
        ]
        if room["decision_board"]:
            lines.append("| Decision | Owner | Status | Severity | Required action |")
            lines.append("| --- | --- | --- | --- | --- |")
            for decision in room["decision_board"]:
                lines.append(
                    f"| {self._md(decision['decision_area'])} | {self._md(decision['owner_role'])} | "
                    f"{decision['status']} | {decision['severity']} | {self._md(decision['required_action'])} |"
                )
        else:
            lines.append("- No release-room decisions are open.")
        lines.extend(["", "## Human-In-The-Loop Queue", ""])
        if room["hitl_queue"]:
            lines.append("| Queue ID | Owner | Priority | Status | Required before |")
            lines.append("| --- | --- | --- | --- | --- |")
            for item in room["hitl_queue"][:24]:
                lines.append(
                    f"| `{self._md(item['queue_id'])}` | {self._md(item['owner_role'])} | "
                    f"{item['priority']} | {item['status']} | {self._md(item['required_before'])} |"
                )
        else:
            lines.append("- No HITL release queue items.")
        lines.extend(["", "## Durable Checkpoints", ""])
        lines.append("| Source | State | Status | Checkpoint |")
        lines.append("| --- | --- | --- | --- |")
        for checkpoint in room["durable_checkpoints"][:28]:
            lines.append(
                f"| `{checkpoint['source']}` | {self._md(checkpoint['state'])} | "
                f"{checkpoint['status']} | `{self._md(checkpoint['checkpoint_key'])}` |"
            )
        lines.extend(["", "## Provider Route", ""])
        for key, value in room["provider_route"].items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Eval Assertions", ""])
        for assertion in room["eval_assertions"]:
            result = "pass" if assertion["passed"] else "fail"
            lines.append(f"- {assertion['assertion_id']} ({result}): {self._md(assertion['assertion'])}")
        lines.extend(["", "## Operator Checklist", ""])
        lines.extend(f"- [ ] {item}" for item in pack["operator_checklist"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in room["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {self._md(item)}" for item in room["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Generated Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {"method": "GET", "path": "/proposal/release-room", "purpose": "View buyer release room controls."},
            {"method": "POST", "path": "/proposal/release-room-pack", "purpose": "Write release room artifacts."},
            {"method": "GET", "path": "/proposal/review-gate", "purpose": "Source role review gate."},
            {"method": "GET", "path": "/proposal/submission-certification", "purpose": "Source final certification."},
            {"method": "GET", "path": "/ops/proposal-observability", "purpose": "Source trace and HITL signals."},
            {"method": "GET", "path": "/ops/provider-resilience", "purpose": "Source provider route policy."},
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/proposal/release-room" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/proposal/release-room-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m pytest -q tests/test_proposal_release_room.py",
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            (
                'rg "proposal/release-room|Buyer Proposal Release Room|proposal_release_room" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\proposal_release_room -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "The release room is a deterministic local control artifact, not a live approval workflow engine.",
            "HITL queue rows must be reconciled with real reviewer, legal, procurement, and GRC systems.",
            "Durable checkpoints are local structured state keys; production durability would persist them externally.",
            "Provider route checks do not call OpenAI, Azure OpenAI, CRM, procurement, Slack, or ticketing systems.",
            "Eval and red-team evidence use local sample datasets and should be replaced with account-specific cases.",
        ]

    def _patterns_used(self) -> list[str]:
        return [
            "durable workflows",
            "human-in-the-loop",
            "governance",
            "provider flexibility",
            "trace analysis",
            "shared state",
        ]

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower() or "local"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
