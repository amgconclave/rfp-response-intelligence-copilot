from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    AnalyzeResponse,
    ProposalIntakeOwnerTask,
    ProposalIntakeSignal,
    ProposalIntakeTransition,
    ProposalIntakeTriagePackResponse,
    ProposalIntakeTriageResponse,
)
from app.models.domain import RequirementMatrixRow


class ProposalIntakeTriageService:
    def __init__(self, settings: Settings, role_policy: dict[str, str] | None = None) -> None:
        self.settings = settings
        self.role_policy = role_policy or {
            "sales": "Own bid strategy, buyer fit, commercial timing, and executive sponsor alignment.",
            "presales": "Own technical feasibility, solution fit, and evidence-backed architecture questions.",
            "compliance": "Own security, privacy, compliance, AI governance, and unsupported regulated claims.",
            "procurement": "Own pricing, contract, legal, insurance, and buyer procurement risk.",
            "proposal_manager": "Own intake completeness, workflow checkpointing, and reviewer handoffs.",
        }

    def triage(
        self,
        trace_id: str,
        analysis: AnalyzeResponse,
        requirement_matrix: list[RequirementMatrixRow],
    ) -> ProposalIntakeTriageResponse:
        signals = self._signals(analysis, requirement_matrix)
        owner_tasks = self._owner_tasks(signals, analysis, requirement_matrix)
        readiness_score = self._readiness_score(signals, requirement_matrix)
        recommended_route = self._recommended_route(readiness_score, signals)
        status = self._status(recommended_route)
        transitions = self._transitions(trace_id, recommended_route, signals, owner_tasks)
        return ProposalIntakeTriageResponse(
            title="Proposal Intake Triage Gate",
            intake_id=f"proposal-intake-{self._slug(trace_id)}",
            status=status,
            generated_at=datetime.now(UTC).isoformat(),
            readiness_score=readiness_score,
            recommended_route=recommended_route,
            summary=self._summary(analysis, requirement_matrix, signals, owner_tasks),
            signals=signals,
            owner_tasks=owner_tasks,
            state_transitions=transitions,
            dependency_contract=self._dependency_contract(),
            eval_assertions=self._eval_assertions(signals, owner_tasks, transitions, recommended_route),
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        triage: ProposalIntakeTriageResponse,
        write_artifact: bool = True,
    ) -> ProposalIntakeTriagePackResponse:
        pack = self._pack_payload(trace_id, triage)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "proposal_intake"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = self._slug(trace_id)
            markdown_path = pack_dir / f"proposal_intake_triage_{safe_trace_id}.md"
            json_path = pack_dir / f"proposal_intake_triage_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["proposal_intake_markdown"] = artifact_path
            pack["artifact_paths"]["proposal_intake_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return ProposalIntakeTriagePackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            triage=triage,
            trace_id=trace_id,
        )

    def _signals(
        self,
        analysis: AnalyzeResponse,
        matrix: list[RequirementMatrixRow],
    ) -> list[ProposalIntakeSignal]:
        signals = [
            self._signal(
                "requirements",
                "proposal_manager",
                "low" if analysis.requirements else "critical",
                f"{len(analysis.requirements)} extracted requirement(s).",
                "advance" if analysis.requirements else "block_until_rfp_parsed",
            ),
            self._signal(
                "deadline",
                "proposal_manager",
                "medium" if analysis.deadlines else "high",
                f"{len(analysis.deadlines)} deadline signal(s) found.",
                "route_to_timeline" if analysis.deadlines else "request_deadline_confirmation",
            ),
            self._signal(
                "security",
                "presales",
                "high" if analysis.security_questions else "low",
                f"{len(analysis.security_questions)} security question(s) detected.",
                "route_to_presales_and_security_review" if analysis.security_questions else "monitor",
            ),
            self._signal(
                "compliance",
                "compliance",
                "high" if analysis.compliance_asks else "low",
                f"{len(analysis.compliance_asks)} compliance ask(s) detected.",
                "route_to_compliance_review" if analysis.compliance_asks else "monitor",
            ),
            self._signal(
                "pricing",
                "procurement",
                "medium" if analysis.pricing_mentions else "low",
                f"{len(analysis.pricing_mentions)} pricing mention(s) detected.",
                "route_to_procurement_review" if analysis.pricing_mentions else "monitor",
            ),
        ]
        missing_rows = [row for row in matrix if row.missing_evidence]
        if missing_rows or analysis.missing_information:
            signals.append(
                self._signal(
                    "evidence_gap",
                    "presales",
                    "critical" if len(missing_rows) > 3 else "high",
                    (
                        f"{len(missing_rows)} requirement row(s) have missing evidence; "
                        f"{len(analysis.missing_information)} missing-info item(s) from analysis."
                    ),
                    "route_to_evidence_gap_plan",
                )
            )
        if analysis.risks:
            signals.append(
                self._signal(
                    "deal_risk",
                    "sales",
                    "high",
                    f"{len(analysis.risks)} risk signal(s) found in intake.",
                    "route_to_bid_no_bid_review",
                )
            )
        return signals

    def _signal(
        self,
        category: str,
        owner_role: str,
        severity: str,
        evidence: str,
        route_hint: str,
    ) -> ProposalIntakeSignal:
        return ProposalIntakeSignal(
            signal_id=f"signal-{self._slug(category)}",
            category=category,
            severity=severity,
            owner_role=owner_role,
            evidence=evidence,
            route_hint=route_hint,
        )

    def _owner_tasks(
        self,
        signals: list[ProposalIntakeSignal],
        analysis: AnalyzeResponse,
        matrix: list[RequirementMatrixRow],
    ) -> list[ProposalIntakeOwnerTask]:
        tasks: list[ProposalIntakeOwnerTask] = []
        signal_by_owner: dict[str, list[ProposalIntakeSignal]] = {}
        for signal in signals:
            if signal.severity in {"medium", "high", "critical"}:
                signal_by_owner.setdefault(signal.owner_role, []).append(signal)
        owner_actions = {
            "sales": "Decide bid posture and document executive sponsor assumptions.",
            "presales": "Confirm technical feasibility and create an evidence gap plan for unsupported claims.",
            "compliance": "Review security, privacy, compliance, and AI governance claims before drafting.",
            "procurement": "Review pricing, contract, and commercial exception exposure.",
            "proposal_manager": "Checkpoint intake completeness and route owner reviews before drafting.",
        }
        for owner, owner_signals in sorted(signal_by_owner.items()):
            max_severity = self._max_severity(owner_signals)
            refs = [signal.signal_id for signal in owner_signals]
            tasks.append(
                ProposalIntakeOwnerTask(
                    task_id=f"task-{self._slug(owner)}-intake",
                    owner_role=owner,
                    priority=max_severity,
                    action=owner_actions.get(owner, "Review intake findings and record a decision."),
                    due_hint=self._due_hint(max_severity),
                    evidence_refs=refs,
                    depends_on=["task-proposal_manager-intake"] if owner != "proposal_manager" else [],
                )
            )
        if not tasks:
            tasks.append(
                ProposalIntakeOwnerTask(
                    task_id="task-proposal_manager-intake",
                    owner_role="proposal_manager",
                    priority="low",
                    action="Confirm intake packet can advance to buyer workflow.",
                    due_hint="before requirement matrix review",
                    evidence_refs=["signal-requirements"],
                )
            )
        uncovered = [row.requirement_id for row in matrix if row.missing_evidence][:6]
        if uncovered and not any(task.owner_role == "presales" for task in tasks):
            tasks.append(
                ProposalIntakeOwnerTask(
                    task_id="task-presales-evidence-gaps",
                    owner_role="presales",
                    priority="high",
                    action="Resolve uncovered requirement evidence before drafting customer-facing answers.",
                    due_hint="before first draft",
                    evidence_refs=uncovered,
                    depends_on=["task-proposal_manager-intake"],
                )
            )
        if analysis.deadlines and not any(task.owner_role == "proposal_manager" for task in tasks):
            tasks.append(
                ProposalIntakeOwnerTask(
                    task_id="task-proposal_manager-deadline",
                    owner_role="proposal_manager",
                    priority="medium",
                    action="Convert RFP deadlines into timeline and submission calendar checkpoints.",
                    due_hint="same business day",
                    evidence_refs=analysis.deadlines[:4],
                )
            )
        return tasks

    def _transitions(
        self,
        trace_id: str,
        route: str,
        signals: list[ProposalIntakeSignal],
        tasks: list[ProposalIntakeOwnerTask],
    ) -> list[ProposalIntakeTransition]:
        critical = [signal.signal_id for signal in signals if signal.severity == "critical"]
        high = [signal.signal_id for signal in signals if signal.severity == "high"]
        states = [
            ("received", "classified", "RFP packet is available for local analysis.", "classify_intake"),
            ("classified", "owner_routed", f"{len(tasks)} owner task(s) created.", "delegate_tasks"),
            (
                "owner_routed",
                "governance_checked",
                f"{len(critical)} critical and {len(high)} high signal(s) evaluated.",
                "apply_governance_gate",
            ),
            ("governance_checked", route, f"Recommended route is {route}.", "route_next_workflow"),
        ]
        transitions: list[ProposalIntakeTransition] = []
        for index, (from_state, to_state, condition, decision) in enumerate(states, start=1):
            transitions.append(
                ProposalIntakeTransition(
                    transition_id=f"intake-transition-{index:02d}",
                    sequence=index,
                    from_state=from_state,
                    to_state=to_state,
                    condition=condition,
                    decision=decision,
                    checkpoint_key=f"{self._slug(trace_id)}:proposal_intake:{index:02d}",
                    owner_role="proposal_manager" if index in {1, 4} else "proposal_manager",
                    trace_refs=[signal.signal_id for signal in signals[:6]],
                )
            )
        return transitions

    def _summary(
        self,
        analysis: AnalyzeResponse,
        matrix: list[RequirementMatrixRow],
        signals: list[ProposalIntakeSignal],
        tasks: list[ProposalIntakeOwnerTask],
    ) -> dict[str, Any]:
        severity_counts = Counter(signal.severity for signal in signals)
        owner_counts = Counter(task.owner_role for task in tasks)
        missing_rows = sum(1 for row in matrix if row.missing_evidence)
        return {
            "requirement_count": len(analysis.requirements),
            "matrix_rows": len(matrix),
            "missing_evidence_rows": missing_rows,
            "deadline_count": len(analysis.deadlines),
            "security_question_count": len(analysis.security_questions),
            "compliance_ask_count": len(analysis.compliance_asks),
            "pricing_mention_count": len(analysis.pricing_mentions),
            "risk_count": len(analysis.risks),
            "signal_count": len(signals),
            "severity_counts": dict(sorted(severity_counts.items())),
            "owner_task_counts": dict(sorted(owner_counts.items())),
            "provider_mode": self.settings.provider_mode,
            "external_provider_required": False,
        }

    def _readiness_score(self, signals: list[ProposalIntakeSignal], matrix: list[RequirementMatrixRow]) -> int:
        penalty = 0
        severity_penalty = {"low": 0, "medium": 6, "high": 12, "critical": 20}
        for signal in signals:
            penalty += severity_penalty.get(signal.severity, 0)
        penalty += min(20, sum(1 for row in matrix if row.missing_evidence) * 2)
        return max(0, 100 - penalty)

    def _recommended_route(self, score: int, signals: list[ProposalIntakeSignal]) -> str:
        if any(signal.category == "evidence_gap" and signal.severity == "critical" for signal in signals):
            return "route_to_evidence_gap_plan"
        if any(signal.category in {"compliance", "security"} and signal.severity == "high" for signal in signals):
            return "qualify_with_compliance_and_presales_review"
        if score < 60:
            return "hold_for_bid_no_bid_review"
        return "advance_to_buyer_workflow"

    def _status(self, route: str) -> str:
        if route == "advance_to_buyer_workflow":
            return "ready"
        if route == "hold_for_bid_no_bid_review":
            return "blocked_pending_qualification"
        return "needs_owner_review"

    def _dependency_contract(self) -> dict[str, Any]:
        return {
            "service": "ProposalIntakeTriageService",
            "settings_provider_mode": self.settings.provider_mode,
            "settings_vector_store_mode": self.settings.vector_store_mode,
            "role_policy": self.role_policy,
            "external_provider_required": False,
            "downstream_workflows": [
                "/proposal/buyer-intelligence",
                "/rfp/evidence-gaps",
                "/bid/scenario-analysis",
                "/rfp/timeline-plan",
            ],
        }

    def _eval_assertions(
        self,
        signals: list[ProposalIntakeSignal],
        tasks: list[ProposalIntakeOwnerTask],
        transitions: list[ProposalIntakeTransition],
        route: str,
    ) -> list[dict[str, Any]]:
        task_refs = {ref for task in tasks for ref in task.evidence_refs}
        signal_ids = {signal.signal_id for signal in signals}
        orders = [transition.sequence for transition in transitions]
        return [
            {
                "assertion_id": "intake-signals-owner-routed",
                "assertion": "medium, high, and critical intake signals create owner task coverage",
                "expected": "all reviewable signals referenced by owner tasks",
                "observed": sorted(signal_ids & task_refs),
                "passed": all(
                    signal.severity == "low" or signal.signal_id in task_refs
                    for signal in signals
                ),
            },
            {
                "assertion_id": "intake-transitions-checkpointed",
                "assertion": "every intake transition has a checkpoint key",
                "expected": len(transitions),
                "observed": sum(1 for transition in transitions if transition.checkpoint_key),
                "passed": all(transition.checkpoint_key for transition in transitions),
            },
            {
                "assertion_id": "intake-route-is-terminal",
                "assertion": "last transition terminates in the recommended route",
                "expected": route,
                "observed": transitions[-1].to_state if transitions else None,
                "passed": bool(transitions and transitions[-1].to_state == route),
            },
            {
                "assertion_id": "intake-transition-order",
                "assertion": "transition sequence is deterministic and contiguous",
                "expected": list(range(1, len(transitions) + 1)),
                "observed": orders,
                "passed": orders == list(range(1, len(transitions) + 1)),
            },
        ]

    def _pack_payload(self, trace_id: str, triage: ProposalIntakeTriageResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Proposal Intake Triage Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "triage": triage.model_dump(mode="json"),
            "reviewer_controls": [
                "Use this gate before drafting or running the full buyer workflow on a new RFP packet.",
                "Resolve critical intake signals before generating customer-facing proposal language.",
                "Keep the local mock provider as default; this triage gate does not require an LLM call.",
                "Regenerate after adding RFP addenda, pricing terms, or new compliance attachments.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        triage = pack["triage"]
        lines = [
            "# Proposal Intake Triage Pack",
            "",
            "## Summary",
            "",
            f"- Status: {triage['status']}",
            f"- Readiness score: {triage['readiness_score']}",
            f"- Recommended route: {triage['recommended_route']}",
            f"- Requirements: {triage['summary']['requirement_count']}",
            f"- Missing evidence rows: {triage['summary']['missing_evidence_rows']}",
            f"- External provider required: {triage['summary']['external_provider_required']}",
            "",
            "## Intake Signals",
            "",
            "| Signal | Category | Severity | Owner | Route hint | Evidence |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for signal in triage["signals"]:
            lines.append(
                f"| {signal['signal_id']} | {signal['category']} | {signal['severity']} | "
                f"{signal['owner_role']} | {self._md(signal['route_hint'])} | {self._md(signal['evidence'])} |"
            )
        lines.extend(["", "## Owner Task Delegation", ""])
        lines.append("| Task | Owner | Priority | Due | Action |")
        lines.append("| --- | --- | --- | --- | --- |")
        for task in triage["owner_tasks"]:
            lines.append(
                f"| {task['task_id']} | {task['owner_role']} | {task['priority']} | "
                f"{self._md(task['due_hint'])} | {self._md(task['action'])} |"
            )
        lines.extend(["", "## State Transitions", ""])
        for transition in triage["state_transitions"]:
            lines.append(
                f"- {transition['transition_id']}: {transition['from_state']} -> {transition['to_state']} "
                f"via {transition['decision']} (`{self._md(transition['checkpoint_key'])}`)"
            )
        lines.extend(["", "## Dependency Contract", ""])
        for key, value in triage["dependency_contract"].items():
            lines.append(f"- {key}: {self._md(value)}")
        lines.extend(["", "## Eval Assertions", ""])
        for assertion in triage["eval_assertions"]:
            result = "pass" if assertion["passed"] else "fail"
            lines.append(f"- {assertion['assertion_id']} ({result}): {self._md(assertion['assertion'])}")
        lines.extend(["", "## Reviewer Controls", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_controls"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in triage["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {self._md(item)}" for item in triage["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Generated Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {"method": "GET", "path": "/proposal/intake-triage", "purpose": "View proposal intake routing gate."},
            {
                "method": "POST",
                "path": "/proposal/intake-triage-pack",
                "purpose": "Write proposal intake triage artifacts.",
            },
            {"method": "GET", "path": "/proposal/buyer-intelligence", "purpose": "Downstream buyer workflow."},
            {"method": "POST", "path": "/rfp/evidence-gaps", "purpose": "Downstream missing-evidence remediation."},
            {"method": "GET", "path": "/bid/scenario-analysis", "purpose": "Downstream bid/no-bid route."},
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/proposal/intake-triage" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/proposal/intake-triage-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'rg "proposal/intake-triage|Proposal Intake Triage|proposal_intake" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\proposal_intake -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "The triage gate is deterministic local analysis and not a CRM opportunity-scoring integration.",
            "Owner tasks are structured routing recommendations; real approvals remain outside this repo.",
            "Readiness scoring is designed for local regression and reviewer inspection, not financial forecasting.",
            "OpenAI, Azure OpenAI, procurement, GRC, ticketing, and calendar systems are not called.",
        ]

    def _max_severity(self, signals: list[ProposalIntakeSignal]) -> str:
        order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        return max((signal.severity for signal in signals), key=lambda severity: order.get(severity, 0))

    def _due_hint(self, severity: str) -> str:
        return {
            "critical": "before any draft generation",
            "high": "before first draft",
            "medium": "same business day",
            "low": "before executive review",
        }.get(severity, "before executive review")

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower() or "local"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
