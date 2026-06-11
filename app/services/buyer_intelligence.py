from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    AnalyzeResponse,
    BuyerApprovalQueueItem,
    BuyerGovernanceGate,
    BuyerIntelligencePackResponse,
    BuyerIntelligenceWorkflowResponse,
    BuyerProviderRoute,
    BuyerWorkflowReplayPackResponse,
    BuyerWorkflowReplayResponse,
    BuyerWorkflowStage,
    BuyerWorkflowTransition,
    CostGovernanceResponse,
    ModelRiskRegisterResponse,
    ProcurementQuestionRiskResponse,
    SourceTrustGateResponse,
)
from app.models.domain import RequirementMatrixRow, ReviewFinding


class BuyerProposalIntelligenceService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def workflow(
        self,
        trace_id: str,
        analysis: AnalyzeResponse,
        requirement_matrix: list[RequirementMatrixRow],
        review_findings: list[ReviewFinding],
        cost_governance: CostGovernanceResponse,
        source_trust: SourceTrustGateResponse,
        model_risk: ModelRiskRegisterResponse,
        procurement_risk: ProcurementQuestionRiskResponse,
    ) -> BuyerIntelligenceWorkflowResponse:
        stages = self._stages(
            trace_id,
            analysis,
            requirement_matrix,
            review_findings,
            source_trust,
            model_risk,
            procurement_risk,
        )
        approvals = self._approval_queue(
            review_findings,
            source_trust,
            model_risk,
            procurement_risk,
            requirement_matrix,
        )
        gates = self._governance_gates(cost_governance, source_trust, model_risk, procurement_risk, approvals)
        status = self._workflow_status(stages, gates, approvals)
        durable_state = self._durable_state(trace_id, status, stages)
        return BuyerIntelligenceWorkflowResponse(
            title="Buyer-Grade Proposal Intelligence Workflow",
            workflow_id=f"buyer-workflow-{self._slug(trace_id)}",
            workflow_status=status,
            generated_at=datetime.now(UTC).isoformat(),
            durable_state=durable_state,
            shared_state=self._shared_state(analysis, requirement_matrix, review_findings),
            workflow_stages=stages,
            human_approval_queue=approvals,
            governance_gates=gates,
            provider_routes=self._provider_routes(cost_governance),
            trace_analysis=self._trace_analysis(trace_id, stages, gates),
            buyer_readout=self._buyer_readout(analysis, requirement_matrix, approvals, gates, source_trust),
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        workflow: BuyerIntelligenceWorkflowResponse,
        write_artifact: bool = True,
    ) -> BuyerIntelligencePackResponse:
        pack = self._pack_payload(trace_id, workflow)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        state_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "buyer_intelligence"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = self._slug(trace_id)
            markdown_path = pack_dir / f"buyer_intelligence_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"buyer_intelligence_pack_{safe_trace_id}.json"
            state_path = pack_dir / f"buyer_workflow_state_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            state_artifact_path = str(state_path.resolve())
            pack["artifact_paths"]["buyer_intelligence_markdown"] = artifact_path
            pack["artifact_paths"]["buyer_intelligence_json"] = json_artifact_path
            pack["artifact_paths"]["durable_workflow_state"] = state_artifact_path
            pack["workflow"]["durable_state"]["state_store_path"] = state_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
            state_payload = {
                "workflow_id": workflow.workflow_id,
                "workflow_status": workflow.workflow_status,
                "trace_id": trace_id,
                "durable_state": pack["workflow"]["durable_state"],
                "stage_checkpoints": [
                    {
                        "stage_id": stage["stage_id"],
                        "status": stage["status"],
                        "durability_key": stage["durability_key"],
                        "restart_policy": stage["restart_policy"],
                    }
                    for stage in pack["workflow"]["workflow_stages"]
                ],
                "approval_queue": pack["workflow"]["human_approval_queue"],
                "governance_gates": pack["workflow"]["governance_gates"],
            }
            state_path.write_text(json.dumps(state_payload, indent=2), encoding="utf-8")

        return BuyerIntelligencePackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            state_artifact_path=state_artifact_path,
            markdown=markdown,
            pack=pack,
            workflow=workflow,
            trace_id=trace_id,
        )

    def replay(
        self,
        trace_id: str,
        workflow: BuyerIntelligenceWorkflowResponse,
    ) -> BuyerWorkflowReplayResponse:
        transitions = self._transitions(workflow)
        checkpoint_validation = self._checkpoint_validation(workflow, transitions)
        route_decisions = self._route_decisions(workflow, transitions)
        status = "pass" if checkpoint_validation["status"] == "pass" else "needs_review"
        return BuyerWorkflowReplayResponse(
            title="Buyer Workflow Replay and Transition Audit",
            status=status,
            generated_at=datetime.now(UTC).isoformat(),
            workflow_id=workflow.workflow_id,
            transition_count=len(transitions),
            transitions=transitions,
            route_decisions=route_decisions,
            checkpoint_validation=checkpoint_validation,
            replay_summary=self._replay_summary(workflow, transitions, checkpoint_validation),
            eval_scenarios=self._eval_scenarios(workflow, transitions),
            local_proof_commands=self._replay_local_proof_commands(),
            limitations=self._replay_limitations(),
            trace_id=trace_id,
        )

    def replay_pack(
        self,
        trace_id: str,
        replay: BuyerWorkflowReplayResponse,
        write_artifact: bool = True,
    ) -> BuyerWorkflowReplayPackResponse:
        pack = self._replay_pack_payload(trace_id, replay)
        markdown = self._render_replay_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "buyer_intelligence"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = self._slug(trace_id)
            markdown_path = pack_dir / f"buyer_workflow_replay_{safe_trace_id}.md"
            json_path = pack_dir / f"buyer_workflow_replay_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["buyer_workflow_replay_markdown"] = artifact_path
            pack["artifact_paths"]["buyer_workflow_replay_json"] = json_artifact_path
            markdown = self._render_replay_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return BuyerWorkflowReplayPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            replay=replay,
            trace_id=trace_id,
        )

    def _stages(
        self,
        trace_id: str,
        analysis: AnalyzeResponse,
        matrix: list[RequirementMatrixRow],
        review_findings: list[ReviewFinding],
        source_trust: SourceTrustGateResponse,
        model_risk: ModelRiskRegisterResponse,
        procurement_risk: ProcurementQuestionRiskResponse,
    ) -> list[BuyerWorkflowStage]:
        uncovered = [row for row in matrix if row.missing_evidence]
        blocked_sources = source_trust.summary.get("blocked_count", 0)
        approvals_required = procurement_risk.approval_summary.get("approvals_required_count", 0)
        model_review = model_risk.summary.get("needs_review_count", 0)
        return [
            self._stage(
                trace_id,
                1,
                "intake",
                "RFP intake and requirement extraction",
                "Proposal Manager",
                "complete" if analysis.requirements else "blocked",
                ["sample RFP", "uploaded RFP"],
                ["requirements", "deadlines", "risks"],
                ["input_traceability"],
                [analysis.trace_id],
            ),
            self._stage(
                trace_id,
                2,
                "evidence",
                "Grounded retrieval and requirement matrix",
                "Solutions Architect",
                "needs_review" if uncovered else "complete",
                ["requirements", "local corpus"],
                ["requirement matrix", "evidence refs", "missing evidence"],
                ["citation_coverage", "source_trust"],
                [trace_id, source_trust.trace_id],
            ),
            self._stage(
                trace_id,
                3,
                "review",
                "Human review and claim approval",
                "Proposal Manager",
                "needs_review" if review_findings else "complete",
                ["draft answers", "review findings"],
                ["reviewer queue", "approval comments"],
                ["human_in_the_loop", "unsupported_claim_block"],
                [trace_id],
            ),
            self._stage(
                trace_id,
                4,
                "procurement",
                "Buyer question risk and procurement desk",
                "Procurement Lead",
                "needs_review" if approvals_required else "complete",
                ["buyer questions", "contract terms", "pricing notes"],
                ["approval workflow", "risk owner routing"],
                ["procurement_approval", "commercial_exception_review"],
                [procurement_risk.trace_id],
            ),
            self._stage(
                trace_id,
                5,
                "governance",
                "Model, provider, and source governance",
                "AI Governance Reviewer",
                "blocked" if blocked_sources else "needs_review" if model_review else "complete",
                ["model risk register", "source trust gate", "cost governance"],
                ["release gates", "provider route policy", "retrieval policy updates"],
                ["model_risk", "provider_flexibility", "source_trust"],
                [model_risk.trace_id, source_trust.trace_id],
            ),
            self._stage(
                trace_id,
                6,
                "submission",
                "Durable final submission checkpoint",
                "Executive Sponsor",
                "waiting_on_approvals" if approvals_required or review_findings or model_review else "ready",
                ["review approvals", "governance gates", "evidence matrix"],
                ["go/no-go packet", "durable state checkpoint"],
                ["executive_signoff", "state_checkpoint"],
                [trace_id],
            ),
        ]

    def _stage(
        self,
        trace_id: str,
        sequence: int,
        slug: str,
        name: str,
        owner: str,
        status: str,
        inputs: list[str],
        outputs: list[str],
        gates: list[str],
        trace_refs: list[str],
    ) -> BuyerWorkflowStage:
        stage_id = f"buyer_{sequence:02d}_{slug}"
        return BuyerWorkflowStage(
            stage_id=stage_id,
            sequence=sequence,
            name=name,
            owner_role=owner,
            status=status,
            durability_key=f"{self._slug(trace_id)}:{stage_id}",
            restart_policy="resume_from_checkpoint_after_human_or_governance_clearance",
            inputs=inputs,
            outputs=outputs,
            governance_gates=gates,
            trace_refs=trace_refs,
        )

    def _approval_queue(
        self,
        review_findings: list[ReviewFinding],
        source_trust: SourceTrustGateResponse,
        model_risk: ModelRiskRegisterResponse,
        procurement_risk: ProcurementQuestionRiskResponse,
        matrix: list[RequirementMatrixRow],
    ) -> list[BuyerApprovalQueueItem]:
        rows: list[BuyerApprovalQueueItem] = []
        severe_findings = [finding for finding in review_findings if finding.severity in {"high", "critical"}]
        missing_rows = [row for row in matrix if row.missing_evidence][:5]
        if severe_findings or missing_rows:
            rows.append(
                BuyerApprovalQueueItem(
                    approval_id="approval-proposal-manager-claims",
                    reviewer_role="Proposal Manager",
                    decision_area="Unsupported or incomplete customer-facing claims",
                    priority="high" if severe_findings else "medium",
                    status="requires_approval",
                    reason=f"{len(severe_findings)} severe review finding(s), {len(missing_rows)} evidence gap row(s).",
                    required_before="final draft export",
                    related_stage_ids=["buyer_02_evidence", "buyer_03_review"],
                    evidence_refs=[ref for row in missing_rows for ref in row.evidence_refs][:6],
                )
            )
        procurement_questions = [
            question
            for question in procurement_risk.questions
            if question.approval_status in {"requires_approval", "blocked", "needs_review"}
        ]
        for question in procurement_questions[:4]:
            rows.append(
                BuyerApprovalQueueItem(
                    approval_id=f"approval-procurement-{self._slug(question.question_id)}",
                    reviewer_role=question.required_reviewer_role,
                    decision_area=question.question,
                    priority=question.risk_level,
                    status=question.approval_status,
                    reason=question.approval_rationale,
                    required_before="buyer Q&A submission",
                    related_stage_ids=["buyer_04_procurement"],
                    evidence_refs=[citation.filename for citation in question.citations],
                )
            )
        for source in source_trust.reviewer_queue[:4]:
            rows.append(
                BuyerApprovalQueueItem(
                    approval_id=f"approval-source-{self._slug(source['source_id'])}",
                    reviewer_role=", ".join(source["owners"]),
                    decision_area=f"Source trust: {source['filename']}",
                    priority="critical" if source["decision"] == "blocked_until_owner_review" else "high",
                    status="requires_approval",
                    reason=source["action"],
                    required_before="retrieval reuse or final citation",
                    related_stage_ids=["buyer_02_evidence", "buyer_05_governance"],
                    evidence_refs=[source["filename"]],
                )
            )
        for risk in model_risk.reviewer_queue[:4]:
            rows.append(
                BuyerApprovalQueueItem(
                    approval_id=f"approval-model-risk-{self._slug(risk['reviewer_owner'])}",
                    reviewer_role=str(risk["reviewer_owner"]),
                    decision_area="Model/provider governance",
                    priority=str(risk["highest_severity"]),
                    status="requires_approval",
                    reason=str(risk["next_action"]),
                    required_before="provider change or executive submission memo",
                    related_stage_ids=["buyer_05_governance", "buyer_06_submission"],
                    evidence_refs=[str(risk_id) for risk_id in risk["risk_ids"]],
                )
            )
        return rows

    def _governance_gates(
        self,
        cost_governance: CostGovernanceResponse,
        source_trust: SourceTrustGateResponse,
        model_risk: ModelRiskRegisterResponse,
        procurement_risk: ProcurementQuestionRiskResponse,
        approvals: list[BuyerApprovalQueueItem],
    ) -> list[BuyerGovernanceGate]:
        return [
            BuyerGovernanceGate(
                gate_id="gate-durable-state",
                name="Durable workflow checkpoint",
                status="pass",
                owner_role="Platform Owner",
                evidence="Workflow stages include durability keys and restart policy.",
                required_action="Persist the pack before external review.",
                endpoint_refs=["/proposal/buyer-intelligence-pack"],
            ),
            BuyerGovernanceGate(
                gate_id="gate-human-approval",
                name="Human-in-the-loop approval",
                status="needs_review" if approvals else "pass",
                owner_role="Proposal Manager",
                evidence=f"{len(approvals)} approval queue item(s).",
                required_action="Clear approval queue before final submission.",
                endpoint_refs=["/rfp/reviewer-collaboration-pack", "/rfp/exception-pack"],
            ),
            BuyerGovernanceGate(
                gate_id="gate-source-trust",
                name="Source trust and citation reuse",
                status=source_trust.status,
                owner_role="Knowledge Owner",
                evidence=f"{source_trust.summary['blocked_count']} blocked source(s), "
                f"{source_trust.summary['approval_required_count']} approval-required source(s).",
                required_action="Resolve blocked or restricted source decisions before final citation reuse.",
                endpoint_refs=["/evidence/source-trust", "/evidence/source-trust-pack"],
            ),
            BuyerGovernanceGate(
                gate_id="gate-model-risk",
                name="Model and provider governance",
                status=model_risk.register_status,
                owner_role="AI Governance Reviewer",
                evidence=f"{model_risk.summary['risk_count']} risk(s), "
                f"{model_risk.summary['needs_review_count']} needing review.",
                required_action="Review model-risk gates before non-mock provider use or executive memo.",
                endpoint_refs=["/governance/model-risk-register", "/governance/model-risk-pack"],
            ),
            BuyerGovernanceGate(
                gate_id="gate-provider-cost",
                name="Provider routing and cost budget",
                status="pass" if cost_governance.governance_status == "ready" else "needs_review",
                owner_role="Sales Operations",
                evidence=f"provider={cost_governance.provider_readiness['provider_mode']}, "
                f"budget={cost_governance.budget_summary['budget_utilization']}.",
                required_action=(
                    "Keep mock mode for local verification; review budget and env before external providers."
                ),
                endpoint_refs=["/ops/cost-governance", "/ops/cost-governance-pack"],
            ),
            BuyerGovernanceGate(
                gate_id="gate-procurement-risk",
                name="Buyer procurement approval",
                status="needs_review"
                if procurement_risk.approval_summary.get("approvals_required_count", 0)
                else "pass",
                owner_role="Procurement Lead",
                evidence=f"{procurement_risk.approval_summary.get('approvals_required_count', 0)} buyer answer "
                "approval(s) required.",
                required_action="Clear high-risk buyer answers before Q&A submission.",
                endpoint_refs=["/procurement/question-risk", "/procurement/approval-pack"],
            ),
        ]

    def _provider_routes(self, cost_governance: CostGovernanceResponse) -> list[BuyerProviderRoute]:
        readiness = cost_governance.provider_readiness
        return [
            BuyerProviderRoute(
                provider_mode="mock",
                readiness="ready",
                use_when="Default local portfolio, CI, demos, and deterministic evaluation.",
                governance_notes=[
                    "No external provider calls.",
                    "Use for buyer workflow proof unless cloud verification is explicitly requested.",
                ],
            ),
            BuyerProviderRoute(
                provider_mode="openai",
                readiness="ready" if readiness["openai_configured"] else "not_configured",
                use_when="Optional live-model validation after local eval and governance gates pass.",
                required_env=["OPENAI_API_KEY"],
                governance_notes=[
                    "Re-run eval, red-team, cost governance, model risk, and privacy review after enabling.",
                    "Do not make this provider mandatory for local verification.",
                ],
            ),
            BuyerProviderRoute(
                provider_mode="azure_openai",
                readiness="ready" if readiness["azure_openai_configured"] else "not_configured",
                use_when="Optional enterprise Azure path for customer-controlled cloud environments.",
                required_env=["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT"],
                governance_notes=[
                    "Re-run the same durable workflow and approval gates after provider change.",
                    "Keep Azure credentials outside generated artifacts.",
                ],
            ),
        ]

    def _durable_state(
        self,
        trace_id: str,
        status: str,
        stages: list[BuyerWorkflowStage],
    ) -> dict[str, Any]:
        return {
            "state_backend": "local_json_artifact",
            "state_store_path": None,
            "idempotency_key": f"buyer-intelligence:{self._slug(trace_id)}",
            "workflow_status": status,
            "checkpoint_count": len(stages),
            "resume_policy": "resume incomplete stages by durability_key after reviewer or governance updates",
            "retention_note": "Generated state artifacts live under ignored storage/buyer_intelligence/.",
        }

    def _shared_state(
        self,
        analysis: AnalyzeResponse,
        matrix: list[RequirementMatrixRow],
        review_findings: list[ReviewFinding],
    ) -> dict[str, Any]:
        priorities = Counter(row.priority for row in matrix)
        owners = Counter(row.owner_role for row in matrix)
        risk_levels = Counter(row.risk_level for row in matrix)
        return {
            "requirements": len(analysis.requirements),
            "deadline_count": len(analysis.deadlines),
            "matrix_rows": len(matrix),
            "priority_counts": dict(sorted(priorities.items())),
            "owner_counts": dict(sorted(owners.items())),
            "risk_counts": dict(sorted(risk_levels.items())),
            "review_findings": len(review_findings),
            "missing_information": analysis.missing_information[:8],
        }

    def _workflow_status(
        self,
        stages: list[BuyerWorkflowStage],
        gates: list[BuyerGovernanceGate],
        approvals: list[BuyerApprovalQueueItem],
    ) -> str:
        if any(stage.status == "blocked" for stage in stages) or any(gate.status == "blocked" for gate in gates):
            return "blocked"
        if approvals or any(gate.status == "needs_review" for gate in gates):
            return "waiting_on_human_approval"
        return "ready_for_submission_review"

    def _trace_analysis(
        self,
        trace_id: str,
        stages: list[BuyerWorkflowStage],
        gates: list[BuyerGovernanceGate],
    ) -> dict[str, Any]:
        stage_statuses = Counter(stage.status for stage in stages)
        gate_statuses = Counter(gate.status for gate in gates)
        return {
            "root_trace_id": trace_id,
            "stage_status_counts": dict(sorted(stage_statuses.items())),
            "gate_status_counts": dict(sorted(gate_statuses.items())),
            "span_count": len(stages) + len(gates),
            "trace_refs": sorted({trace for stage in stages for trace in stage.trace_refs}),
            "observability_note": (
                "This local trace summary uses deterministic workflow spans and service trace IDs; "
                "external trace backends remain optional."
            ),
        }

    def _buyer_readout(
        self,
        analysis: AnalyzeResponse,
        matrix: list[RequirementMatrixRow],
        approvals: list[BuyerApprovalQueueItem],
        gates: list[BuyerGovernanceGate],
        source_trust: SourceTrustGateResponse,
    ) -> dict[str, Any]:
        blocked_gates = [gate.gate_id for gate in gates if gate.status == "blocked"]
        review_gates = [gate.gate_id for gate in gates if gate.status == "needs_review"]
        high_priority = sum(1 for row in matrix if row.priority == "high")
        return {
            "recommended_posture": "submit_after_approval" if not blocked_gates else "do_not_submit_yet",
            "requirements": len(analysis.requirements),
            "high_priority_requirements": high_priority,
            "approval_items": len(approvals),
            "blocked_gates": blocked_gates,
            "review_gates": review_gates,
            "source_trust_status": source_trust.status,
            "executive_summary": (
                "Buyer-grade workflow is locally runnable, evidence-first, and ready only after human "
                "approval and governance gates clear."
            ),
        }

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {
                "path": "/proposal/buyer-intelligence",
                "method": "GET",
                "purpose": "Return composed durable workflow, HITL queue, governance gates, and provider routes.",
            },
            {
                "path": "/proposal/buyer-intelligence-pack",
                "method": "POST",
                "purpose": "Write Markdown/JSON pack plus local durable workflow state JSON.",
            },
            {"path": "/evidence/source-trust", "method": "GET", "purpose": "Source trust input signal."},
            {"path": "/governance/model-risk-register", "method": "GET", "purpose": "Model governance input signal."},
            {"path": "/procurement/question-risk", "method": "GET", "purpose": "Buyer approval input signal."},
            {"path": "/ops/cost-governance", "method": "GET", "purpose": "Provider and budget input signal."},
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/proposal/buyer-intelligence" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/proposal/buyer-intelligence-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m pytest -q",
            "python -m ruff check .",
            (
                'rg "proposal/buyer-intelligence|Buyer-Grade Proposal Intelligence|buyer_intelligence" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\buyer_intelligence -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Workflow durability is represented by local JSON checkpoints, not an external orchestrator.",
            "Human approvals are deterministic queue items and do not update a live ticketing or GRC system.",
            "Provider routes describe readiness and governance; OpenAI and Azure OpenAI remain optional.",
            "Trace analysis is local structured metadata and can be exported to a tracing backend later.",
        ]

    def _transitions(self, workflow: BuyerIntelligenceWorkflowResponse) -> list[BuyerWorkflowTransition]:
        transitions: list[BuyerWorkflowTransition] = []
        previous: BuyerWorkflowStage | None = None
        for stage in sorted(workflow.workflow_stages, key=lambda item: item.sequence):
            transitions.append(
                BuyerWorkflowTransition(
                    transition_id=f"transition-{stage.sequence:02d}-{self._slug(stage.stage_id)}",
                    replay_order=stage.sequence,
                    from_stage_id=previous.stage_id if previous else None,
                    to_stage_id=stage.stage_id,
                    condition=self._transition_condition(previous, stage),
                    decision=self._transition_decision(stage),
                    status=stage.status,
                    evidence=self._transition_evidence(stage),
                    checkpoint_key=stage.durability_key,
                    trace_refs=stage.trace_refs,
                )
            )
            previous = stage
        return transitions

    def _transition_condition(self, previous: BuyerWorkflowStage | None, stage: BuyerWorkflowStage) -> str:
        if previous is None:
            return "start when RFP intake is available"
        if previous.status in {"blocked", "waiting_on_approvals"}:
            return f"hold after {previous.stage_id} until reviewer or governance clearance"
        if stage.status in {"needs_review", "waiting_on_approvals"}:
            return f"route to {stage.owner_role} review because stage status is {stage.status}"
        return f"advance from {previous.stage_id} after checkpoint {previous.durability_key}"

    def _transition_decision(self, stage: BuyerWorkflowStage) -> str:
        if stage.status == "blocked":
            return "blocked_until_governance_or_owner_action"
        if stage.status in {"needs_review", "waiting_on_approvals"}:
            return "route_to_human_approval_queue"
        if stage.status == "ready":
            return "ready_for_submission_review"
        return "continue"

    def _transition_evidence(self, stage: BuyerWorkflowStage) -> str:
        gates = ", ".join(stage.governance_gates) or "no gate"
        outputs = ", ".join(stage.outputs) or "no output"
        return f"{stage.name} produced {outputs}; governed by {gates}."

    def _checkpoint_validation(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        transitions: list[BuyerWorkflowTransition],
    ) -> dict[str, Any]:
        expected_orders = list(range(1, len(transitions) + 1))
        actual_orders = [transition.replay_order for transition in transitions]
        missing_checkpoint_transitions = [
            transition.transition_id
            for transition in transitions
            if not transition.checkpoint_key or ":" not in transition.checkpoint_key
        ]
        missing_trace_transitions = [
            transition.transition_id for transition in transitions if not transition.trace_refs
        ]
        terminal_transition = transitions[-1].to_stage_id if transitions else None
        terminal_matches_status = bool(
            transitions
            and transitions[-1].status in {"ready", "waiting_on_approvals", "blocked", "needs_review", "complete"}
            and workflow.workflow_status in {"ready_for_submission_review", "waiting_on_human_approval", "blocked"}
        )
        failures = []
        if actual_orders != expected_orders:
            failures.append("transition_order_not_contiguous")
        if missing_checkpoint_transitions:
            failures.append("missing_checkpoint_key")
        if missing_trace_transitions:
            failures.append("missing_trace_refs")
        if not terminal_matches_status:
            failures.append("terminal_status_not_supported")
        return {
            "status": "pass" if not failures else "fail",
            "failures": failures,
            "expected_orders": expected_orders,
            "actual_orders": actual_orders,
            "checkpoint_count": workflow.durable_state.get("checkpoint_count"),
            "transition_count": len(transitions),
            "missing_checkpoint_transitions": missing_checkpoint_transitions,
            "missing_trace_transitions": missing_trace_transitions,
            "terminal_transition": terminal_transition,
            "terminal_matches_status": terminal_matches_status,
        }

    def _route_decisions(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        transitions: list[BuyerWorkflowTransition],
    ) -> list[dict[str, Any]]:
        approval_stage_ids = {
            stage_id
            for item in workflow.human_approval_queue
            for stage_id in item.related_stage_ids
        }
        gate_by_stage = {
            stage.stage_id: [
                gate.gate_id
                for gate in workflow.governance_gates
                if any(gate_ref in stage.governance_gates for gate_ref in self._gate_aliases(gate.gate_id))
            ]
            for stage in workflow.workflow_stages
        }
        decisions = []
        for transition in transitions:
            decisions.append(
                {
                    "transition_id": transition.transition_id,
                    "stage_id": transition.to_stage_id,
                    "decision": transition.decision,
                    "requires_human_review": transition.to_stage_id in approval_stage_ids
                    or transition.decision == "route_to_human_approval_queue",
                    "governance_gate_refs": gate_by_stage.get(transition.to_stage_id, []),
                    "checkpoint_key": transition.checkpoint_key,
                    "eval_assertion": "checkpointed" if transition.checkpoint_key else "missing_checkpoint",
                }
            )
        return decisions

    def _gate_aliases(self, gate_id: str) -> list[str]:
        aliases = {
            "gate-human-approval": ["human_in_the_loop", "unsupported_claim_block", "executive_signoff"],
            "gate-source-trust": ["source_trust", "citation_coverage"],
            "gate-model-risk": ["model_risk", "provider_flexibility"],
            "gate-provider-cost": ["provider_flexibility"],
            "gate-procurement-risk": ["procurement_approval", "commercial_exception_review"],
            "gate-durable-state": ["state_checkpoint", "input_traceability"],
        }
        return aliases.get(gate_id, [gate_id])

    def _replay_summary(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        transitions: list[BuyerWorkflowTransition],
        checkpoint_validation: dict[str, Any],
    ) -> dict[str, Any]:
        decisions = Counter(transition.decision for transition in transitions)
        statuses = Counter(transition.status for transition in transitions)
        return {
            "workflow_status": workflow.workflow_status,
            "transition_count": len(transitions),
            "decision_counts": dict(sorted(decisions.items())),
            "status_counts": dict(sorted(statuses.items())),
            "checkpoint_validation_status": checkpoint_validation["status"],
            "approval_queue_items": len(workflow.human_approval_queue),
            "governance_gate_count": len(workflow.governance_gates),
            "replayable_from_local_state": checkpoint_validation["status"] == "pass",
        }

    def _eval_scenarios(
        self,
        workflow: BuyerIntelligenceWorkflowResponse,
        transitions: list[BuyerWorkflowTransition],
    ) -> list[dict[str, Any]]:
        observed_orders = [transition.replay_order for transition in transitions]
        expected_orders = list(range(1, len(transitions) + 1))
        return [
            {
                "scenario_id": "buyer-workflow-ordering",
                "assertion": "transition replay order is contiguous and follows workflow stage sequence",
                "expected": expected_orders,
                "observed": observed_orders,
                "passed": observed_orders == expected_orders,
            },
            {
                "scenario_id": "buyer-workflow-hitl-routing",
                "assertion": "reviewable workflow states produce human approval or governance routing",
                "expected": "approval queue when workflow is not ready",
                "observed": {
                    "workflow_status": workflow.workflow_status,
                    "approval_queue_items": len(workflow.human_approval_queue),
                },
                "passed": workflow.workflow_status == "ready_for_submission_review"
                or bool(workflow.human_approval_queue),
            },
            {
                "scenario_id": "buyer-workflow-checkpoints",
                "assertion": "every transition includes a durable local checkpoint key",
                "expected": len(transitions),
                "observed": sum(1 for transition in transitions if transition.checkpoint_key),
                "passed": all(transition.checkpoint_key for transition in transitions),
            },
            {
                "scenario_id": "buyer-workflow-traceability",
                "assertion": "transitions retain source trace references for audit review",
                "expected": len(transitions),
                "observed": sum(1 for transition in transitions if transition.trace_refs),
                "passed": all(transition.trace_refs for transition in transitions),
            },
        ]

    def _replay_local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/proposal/buyer-intelligence-replay" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/proposal/buyer-intelligence-replay-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'rg "buyer-intelligence-replay|Buyer Workflow Replay|buyer_workflow_replay" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\buyer_intelligence -Filter "
                "*replay* -ErrorAction SilentlyContinue | Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _replay_limitations(self) -> list[str]:
        return [
            "Replay uses deterministic local workflow snapshots and does not call an external orchestrator.",
            "Transition decisions are auditable control outputs, not asynchronous job execution state.",
            "Checkpoint validation confirms local keys and trace refs, not durable cloud storage recovery.",
            "Eval scenarios are contract-style assertions designed for local regression and reviewer inspection.",
        ]

    def _replay_pack_payload(self, trace_id: str, replay: BuyerWorkflowReplayResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Buyer Workflow Replay Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "replay": replay.model_dump(mode="json"),
            "reviewer_controls": [
                "Verify replay status is pass before using the buyer pack as a submission control artifact.",
                "Inspect route decisions for human approval and governance handoffs.",
                "Confirm every transition carries a checkpoint key and trace refs.",
                "Regenerate after changing stage routing, source trust, procurement, or model-risk policy.",
            ],
            "artifact_paths": {},
        }

    def _pack_payload(self, trace_id: str, workflow: BuyerIntelligenceWorkflowResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Buyer-Grade Proposal Intelligence Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "workflow": workflow.model_dump(mode="json"),
            "executive_controls": [
                "Do not submit customer-facing wording until human approval queue is clear.",
                "Keep PROVIDER_MODE=mock for local verification unless external provider review is explicit.",
                "Resolve blocked source trust decisions before citation reuse.",
                "Re-run eval, red-team, model risk, cost governance, and this pack after provider changes.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        workflow = pack["workflow"]
        readout = workflow["buyer_readout"]
        lines = [
            "# Buyer-Grade Proposal Intelligence Pack",
            "",
            "## Executive Readout",
            "",
            f"- Workflow status: {workflow['workflow_status']}",
            f"- Recommended posture: {readout['recommended_posture']}",
            f"- Requirements: {readout['requirements']}",
            f"- Approval items: {readout['approval_items']}",
            f"- Source trust: {readout['source_trust_status']}",
            f"- Summary: {readout['executive_summary']}",
            "",
            "## Durable Workflow",
            "",
            "| Seq | Stage | Owner | Status | Durability key | Gates |",
            "| ---: | --- | --- | --- | --- | --- |",
        ]
        for stage in workflow["workflow_stages"]:
            lines.append(
                "| {seq} | {name} | {owner} | {status} | `{key}` | {gates} |".format(
                    seq=stage["sequence"],
                    name=self._md(stage["name"]),
                    owner=self._md(stage["owner_role"]),
                    status=stage["status"],
                    key=self._md(stage["durability_key"]),
                    gates=self._md(", ".join(stage["governance_gates"])),
                )
            )
        lines.extend(["", "## Human Approval Queue", ""])
        if workflow["human_approval_queue"]:
            lines.append("| Reviewer | Priority | Status | Area | Required before |")
            lines.append("| --- | --- | --- | --- | --- |")
            for item in workflow["human_approval_queue"]:
                lines.append(
                    f"| {self._md(item['reviewer_role'])} | {item['priority']} | {item['status']} | "
                    f"{self._md(item['decision_area'])} | {self._md(item['required_before'])} |"
                )
        else:
            lines.append("- No approval queue items are currently open.")
        lines.extend(["", "## Governance Gates", ""])
        for gate in workflow["governance_gates"]:
            lines.append(
                f"- {gate['gate_id']} ({gate['status']}): {self._md(gate['required_action'])} "
                f"Evidence: {self._md(gate['evidence'])}"
            )
        lines.extend(["", "## Provider Routes", ""])
        for route in workflow["provider_routes"]:
            lines.append(
                f"- {route['provider_mode']} ({route['readiness']}): {self._md(route['use_when'])}"
            )
        lines.extend(["", "## Trace Analysis", ""])
        lines.append(f"- Span count: {workflow['trace_analysis']['span_count']}")
        lines.append(f"- Stage statuses: {workflow['trace_analysis']['stage_status_counts']}")
        lines.append(f"- Gate statuses: {workflow['trace_analysis']['gate_status_counts']}")
        lines.extend(["", "## Executive Controls", ""])
        lines.extend(f"- [ ] {item}" for item in pack["executive_controls"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in workflow["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {self._md(item)}" for item in workflow["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Generated Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _render_replay_markdown(self, pack: dict[str, Any]) -> str:
        replay = pack["replay"]
        summary = replay["replay_summary"]
        lines = [
            "# Buyer Workflow Replay Pack",
            "",
            "## Summary",
            "",
            f"- Replay status: {replay['status']}",
            f"- Workflow status: {summary['workflow_status']}",
            f"- Transitions: {summary['transition_count']}",
            f"- Approval queue items: {summary['approval_queue_items']}",
            f"- Checkpoint validation: {summary['checkpoint_validation_status']}",
            "",
            "## Transition Replay",
            "",
            "| Order | From | To | Decision | Status | Checkpoint |",
            "| ---: | --- | --- | --- | --- | --- |",
        ]
        for transition in replay["transitions"]:
            lines.append(
                "| {order} | {from_stage} | {to_stage} | {decision} | {status} | `{checkpoint}` |".format(
                    order=transition["replay_order"],
                    from_stage=self._md(transition["from_stage_id"] or "START"),
                    to_stage=self._md(transition["to_stage_id"]),
                    decision=self._md(transition["decision"]),
                    status=self._md(transition["status"]),
                    checkpoint=self._md(transition["checkpoint_key"]),
                )
            )
        lines.extend(["", "## Route Decisions", ""])
        for decision in replay["route_decisions"]:
            gates = self._md(", ".join(decision["governance_gate_refs"]) or "none")
            lines.append(
                f"- {decision['transition_id']}: {decision['decision']} "
                f"(human_review={decision['requires_human_review']}, gates={gates})"
            )
        lines.extend(["", "## Checkpoint Validation", ""])
        validation = replay["checkpoint_validation"]
        lines.append(f"- Status: {validation['status']}")
        lines.append(f"- Failures: {', '.join(validation['failures']) or 'none'}")
        lines.append(f"- Terminal transition: {validation['terminal_transition']}")
        lines.extend(["", "## Eval Scenarios", ""])
        for scenario in replay["eval_scenarios"]:
            result = "pass" if scenario["passed"] else "fail"
            lines.append(f"- {scenario['scenario_id']} ({result}): {scenario['assertion']}")
        lines.extend(["", "## Reviewer Controls", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_controls"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in replay["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {self._md(item)}" for item in replay["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Generated Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower() or "local"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
