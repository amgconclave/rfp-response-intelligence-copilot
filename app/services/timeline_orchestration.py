from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

from app.core.config import Settings
from app.models.api import (
    AnalyzeResponse,
    ContractRiskResponse,
    DealReadinessScorecardResponse,
    SubmissionCalendarPackResponse,
    TimelineMilestone,
    TimelinePlanResponse,
    WinStrategyResponse,
)
from app.models.domain import EvidenceGap, RequirementMatrixRow, ReviewFinding, StakeholderTask


class TimelineOrchestrationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_plan(
        self,
        trace_id: str,
        analysis: AnalyzeResponse | None = None,
        requirement_matrix: list[RequirementMatrixRow] | None = None,
        action_plan: list[StakeholderTask] | None = None,
        evidence_gaps: list[EvidenceGap] | None = None,
        contract_risk: ContractRiskResponse | None = None,
        win_strategy: WinStrategyResponse | None = None,
        readiness_scorecard: DealReadinessScorecardResponse | None = None,
        source_request_pack: dict[str, Any] | None = None,
        leadership_brief: dict[str, Any] | None = None,
        review_findings: list[ReviewFinding] | None = None,
        red_team_summary: dict[str, Any] | None = None,
    ) -> TimelinePlanResponse:
        matrix = requirement_matrix or []
        tasks = action_plan or []
        gaps = evidence_gaps or []
        findings = review_findings or []
        deadline = self._submission_deadline(analysis)
        blocked_items = self._blocked_items(tasks, gaps, readiness_scorecard, contract_risk, findings)
        buffers = self._risk_buffers(deadline, gaps, contract_risk, win_strategy, readiness_scorecard, red_team_summary)
        milestones = self._milestones(
            deadline=deadline,
            analysis=analysis,
            matrix=matrix,
            tasks=tasks,
            gaps=gaps,
            blocked_items=blocked_items,
            buffers=buffers,
            contract_risk=contract_risk,
            win_strategy=win_strategy,
            readiness_scorecard=readiness_scorecard,
            source_request_pack=source_request_pack,
            leadership_brief=leadership_brief,
        )
        dependencies = self._dependencies(milestones)
        gates = self._readiness_gates(
            deadline,
            matrix,
            tasks,
            gaps,
            blocked_items,
            contract_risk,
            win_strategy,
            readiness_scorecard,
            findings,
        )
        escalations = self._escalation_triggers(
            deadline,
            blocked_items,
            gaps,
            contract_risk,
            win_strategy,
            readiness_scorecard,
            red_team_summary,
        )
        owner_assignments = self._owner_assignments(milestones, tasks, gaps, contract_risk, win_strategy)
        calendar_entries = [self._calendar_entry(milestone) for milestone in milestones]
        summary = {
            "submission_deadline": deadline.isoformat(),
            "milestone_count": len(milestones),
            "blocked_count": len(blocked_items),
            "readiness_score": readiness_scorecard.readiness_score if readiness_scorecard else None,
            "readiness_level": readiness_scorecard.readiness_level if readiness_scorecard else None,
            "high_severity_gap_count": sum(1 for gap in gaps if gap.severity in {"critical", "high"}),
            "contract_risk_status": contract_risk.status if contract_risk else None,
            "win_level": win_strategy.win_level if win_strategy else None,
            "calendar_entry_count": len(calendar_entries),
        }
        return TimelinePlanResponse(
            milestones=milestones,
            owner_assignments=owner_assignments,
            dependencies=dependencies,
            risk_buffers=buffers,
            blocked_items=blocked_items,
            readiness_gates=gates,
            escalation_triggers=escalations,
            calendar_entries=calendar_entries,
            summary=summary,
            trace_id=trace_id,
        )

    def export_submission_calendar_pack(
        self,
        trace_id: str,
        plan: TimelinePlanResponse,
        analysis: AnalyzeResponse | None = None,
        source_request_pack: dict[str, Any] | None = None,
        leadership_brief: dict[str, Any] | None = None,
        write_artifact: bool = True,
    ) -> SubmissionCalendarPackResponse:
        pack = {
            "trace_id": trace_id,
            "summary": plan.summary,
            "milestone_calendar": [milestone.model_dump(mode="json") for milestone in plan.milestones],
            "owner_matrix": plan.owner_assignments,
            "dependencies": plan.dependencies,
            "dependency_risk_buffers": plan.risk_buffers,
            "blocked_items": plan.blocked_items,
            "readiness_gates": plan.readiness_gates,
            "escalation_triggers": plan.escalation_triggers,
            "calendar_entries": plan.calendar_entries,
            "source_request_context": self._source_request_context(source_request_pack),
            "leadership_context": self._leadership_context(leadership_brief),
            "deadline_references": analysis.deadlines if analysis else [],
            "local_commands": [
                "python -m uvicorn app.main:app --reload",
                "streamlit run dashboard/app.py",
                "python -m app.demo",
                "python -m pytest -q",
                "python -m ruff check .",
                "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
                "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
                (
                    'curl -X POST "http://127.0.0.1:8000/rfp/timeline-plan" '
                    '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
                ),
                (
                    'curl -X POST "http://127.0.0.1:8000/rfp/submission-calendar-pack" '
                    '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
                ),
            ],
            "jd_skills_demonstrated": [
                "Deterministic workflow orchestration across RFP analysis, RAG evidence, readiness, and deal risk.",
                "Typed FastAPI contracts that convert AI-assisted outputs into owner-routed execution plans.",
                "Calendar-friendly local artifacts for sales, presales, security, legal, finance, and executives.",
                "Risk buffers, dependencies, gates, and escalations derived from evidence gaps and contract risk.",
                "Fully local/mock implementation with tests, evals, red-team checks, dashboard, and demo coverage.",
            ],
            "interviewer_talking_points": [
                "This turns the copilot from a response drafter into a submission operating system.",
                "The plan makes deadline risk visible through buffers, dependencies, and escalation triggers.",
                "External calendars are intentionally not called; the output is portable Markdown and JSON.",
                "Readiness gates link directly to missing evidence, legal/security review, pricing, and final QA.",
                "The same deterministic service powers the API, dashboard, one-command demo, and regression tests.",
            ],
        }
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            calendar_dir = self.settings.storage_dir / "submission_calendars"
            calendar_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = calendar_dir / f"submission_calendar_pack_{safe_trace_id}.md"
            json_path = calendar_dir / f"submission_calendar_pack_{safe_trace_id}.json"
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
        return SubmissionCalendarPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            trace_id=trace_id,
        )

    def _milestones(
        self,
        deadline: date,
        analysis: AnalyzeResponse | None,
        matrix: list[RequirementMatrixRow],
        tasks: list[StakeholderTask],
        gaps: list[EvidenceGap],
        blocked_items: list[dict[str, Any]],
        buffers: list[dict[str, Any]],
        contract_risk: ContractRiskResponse | None,
        win_strategy: WinStrategyResponse | None,
        readiness_scorecard: DealReadinessScorecardResponse | None,
        source_request_pack: dict[str, Any] | None,
        leadership_brief: dict[str, Any] | None,
    ) -> list[TimelineMilestone]:
        high_gaps = [gap for gap in gaps if gap.severity in {"critical", "high"}]
        contract_blocked = bool(contract_risk and contract_risk.status in {"critical", "high_risk"})
        pricing_blocked = bool(
            win_strategy and win_strategy.pricing_risk.get("risk_level") == "high"
        )
        readiness_blocked = bool(readiness_scorecard and readiness_scorecard.readiness_level != "ready")
        milestone_specs = [
            {
                "slug": "kickoff-triage",
                "offset": 18,
                "title": "Kickoff, requirement triage, and owner lock",
                "owner": "proposal_manager",
                "category": "planning",
                "status": "scheduled",
                "description": (
                    f"Confirm {len(matrix) or (len(analysis.requirements) if analysis else 0)} requirements, "
                    "submission deadline, review cadence, and response owners."
                ),
                "dependencies": [],
                "signals": self._deadline_signals(analysis),
            },
            {
                "slug": "evidence-source-requests",
                "offset": 14,
                "title": "Evidence gaps and source requests dispatched",
                "owner": "solutions",
                "category": "evidence",
                "status": "blocked" if high_gaps else "scheduled",
                "description": (
                    f"Dispatch {len(gaps)} source requests and prioritize "
                    f"{len(high_gaps)} high-severity evidence gaps."
                ),
                "dependencies": ["timeline_01_kickoff_triage"],
                "signals": self._gap_signals(gaps, source_request_pack),
            },
            {
                "slug": "draft-freeze",
                "offset": 10,
                "title": "Draft freeze and SME review",
                "owner": "solutions",
                "category": "drafting",
                "status": "blocked" if any(task.status == "blocked" for task in tasks) else "scheduled",
                "description": "Freeze response draft, resolve SME comments, and attach cited evidence.",
                "dependencies": ["timeline_02_evidence_source_requests"],
                "signals": [f"Action plan tasks: {len(tasks)}", f"Blocked items: {len(blocked_items)}"],
            },
            {
                "slug": "legal-security-redlines",
                "offset": 7,
                "title": "Legal, security, and redline review",
                "owner": "legal",
                "category": "legal_security",
                "status": "blocked" if contract_blocked or high_gaps else "scheduled",
                "description": "Approve contract exceptions, security claims, compliance evidence, and redlines.",
                "dependencies": ["timeline_03_draft_freeze"],
                "signals": self._contract_signals(contract_risk),
            },
            {
                "slug": "pricing-win-approval",
                "offset": 5,
                "title": "Pricing approval and win-strategy checkpoint",
                "owner": "sales",
                "category": "commercial",
                "status": "blocked" if pricing_blocked else "scheduled",
                "description": "Approve discount guardrails, commercial assumptions, and competitive posture.",
                "dependencies": ["timeline_04_legal_security_redlines"],
                "signals": self._win_signals(win_strategy),
            },
            {
                "slug": "readiness-gate",
                "offset": 3,
                "title": "Submission readiness gate",
                "owner": "proposal_manager",
                "category": "readiness",
                "status": "blocked" if readiness_blocked else "scheduled",
                "description": "Run final readiness scorecard, evidence coverage check, and exception review.",
                "dependencies": ["timeline_05_pricing_win_approval"],
                "signals": self._readiness_signals(readiness_scorecard, leadership_brief),
            },
            {
                "slug": "final-qa",
                "offset": 1,
                "title": "Final QA, packaging, and submission rehearsal",
                "owner": "proposal_manager",
                "category": "qa",
                "status": "blocked" if blocked_items else "scheduled",
                "description": "Validate attachments, answer completeness, citations, redlines, and portal steps.",
                "dependencies": ["timeline_06_readiness_gate"],
                "signals": [f"Risk buffers: {len(buffers)}", f"Open blocked items: {len(blocked_items)}"],
            },
            {
                "slug": "submit",
                "offset": 0,
                "title": "Submit response package",
                "owner": "sales",
                "category": "submission",
                "status": "ready_if_gates_pass" if blocked_items else "scheduled",
                "description": "Submit the final RFP response and archive the local artifact package.",
                "dependencies": ["timeline_07_final_qa"],
                "signals": [f"Submission deadline: {deadline.isoformat()}"],
            },
        ]
        milestones = []
        for sequence, spec in enumerate(milestone_specs, start=1):
            milestone_id = f"timeline_{sequence:02d}_{spec['slug'].replace('-', '_')}"
            milestones.append(
                TimelineMilestone(
                    milestone_id=milestone_id,
                    sequence=sequence,
                    title=spec["title"],
                    owner_role=spec["owner"],
                    due_date=(deadline - timedelta(days=spec["offset"])).isoformat(),
                    status=spec["status"],
                    category=spec["category"],
                    description=spec["description"],
                    dependencies=spec["dependencies"],
                    related_requirement_ids=self._related_requirement_ids(spec["category"], matrix, gaps),
                    source_signals=self._unique(spec["signals"]),
                )
            )
        return sorted(milestones, key=lambda milestone: (milestone.due_date, milestone.sequence))

    def _dependencies(self, milestones: list[TimelineMilestone]) -> list[dict[str, Any]]:
        lookup = {milestone.milestone_id: milestone for milestone in milestones}
        edges = []
        for milestone in milestones:
            for dependency_id in milestone.dependencies:
                dependency = lookup.get(dependency_id)
                edges.append(
                    {
                        "from": dependency_id,
                        "to": milestone.milestone_id,
                        "dependency": f"{dependency.title if dependency else dependency_id} before {milestone.title}",
                        "risk_if_missed": self._dependency_risk(milestone.category),
                    }
                )
        return edges

    def _risk_buffers(
        self,
        deadline: date,
        gaps: list[EvidenceGap],
        contract_risk: ContractRiskResponse | None,
        win_strategy: WinStrategyResponse | None,
        readiness_scorecard: DealReadinessScorecardResponse | None,
        red_team_summary: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        buffers = [
            {
                "name": "Final packaging buffer",
                "owner_role": "proposal_manager",
                "buffer_days": 1,
                "start_date": (deadline - timedelta(days=1)).isoformat(),
                "reason": "Protects portal upload, attachment validation, and final QA.",
            }
        ]
        high_gap_count = sum(1 for gap in gaps if gap.severity in {"critical", "high"})
        if high_gap_count:
            buffers.append(
                {
                    "name": "Evidence remediation buffer",
                    "owner_role": "solutions",
                    "buffer_days": min(4, 1 + high_gap_count),
                    "start_date": (deadline - timedelta(days=8)).isoformat(),
                    "reason": f"{high_gap_count} high-severity evidence gap(s) require closure before QA.",
                }
            )
        if contract_risk and contract_risk.status in {"critical", "high_risk", "needs_legal_review"}:
            buffers.append(
                {
                    "name": "Legal redline buffer",
                    "owner_role": "legal",
                    "buffer_days": 2 if contract_risk.status != "critical" else 3,
                    "start_date": (deadline - timedelta(days=7)).isoformat(),
                    "reason": f"Contract risk status is {contract_risk.status}.",
                }
            )
        if win_strategy and win_strategy.pricing_risk.get("risk_level") in {"medium", "high"}:
            buffers.append(
                {
                    "name": "Pricing approval buffer",
                    "owner_role": "sales",
                    "buffer_days": 2 if win_strategy.pricing_risk.get("risk_level") == "high" else 1,
                    "start_date": (deadline - timedelta(days=5)).isoformat(),
                    "reason": f"Pricing risk is {win_strategy.pricing_risk.get('risk_level')}.",
                }
            )
        if readiness_scorecard and readiness_scorecard.readiness_score < 70:
            buffers.append(
                {
                    "name": "Readiness recovery buffer",
                    "owner_role": "proposal_manager",
                    "buffer_days": 3,
                    "start_date": (deadline - timedelta(days=4)).isoformat(),
                    "reason": (
                        f"Readiness score is {readiness_scorecard.readiness_score} "
                        f"({readiness_scorecard.readiness_level})."
                    ),
                }
            )
        if red_team_summary and not red_team_summary.get("passed", True):
            buffers.append(
                {
                    "name": "Red-team remediation buffer",
                    "owner_role": "security",
                    "buffer_days": 2,
                    "start_date": (deadline - timedelta(days=6)).isoformat(),
                    "reason": "Red-team summary did not pass all local checks.",
                }
            )
        return buffers

    def _blocked_items(
        self,
        tasks: list[StakeholderTask],
        gaps: list[EvidenceGap],
        readiness_scorecard: DealReadinessScorecardResponse | None,
        contract_risk: ContractRiskResponse | None,
        findings: list[ReviewFinding],
    ) -> list[dict[str, Any]]:
        items = [
            {
                "source": "action_plan",
                "owner_role": task.owner_role,
                "title": task.title,
                "severity": task.risk_level,
                "due_hint": task.due_hint,
                "related_requirement_id": task.source_requirement_id,
                "resolution": "Owner must attach evidence, complete review, or document an approved exception.",
            }
            for task in tasks
            if task.status == "blocked"
        ]
        for gap in gaps:
            if gap.severity not in {"critical", "high"}:
                continue
            items.append(
                {
                    "source": "evidence_gap",
                    "owner_role": gap.owner_team,
                    "title": gap.title,
                    "severity": gap.severity,
                    "due_hint": gap.due_date_recommendation,
                    "related_requirement_id": ", ".join(gap.requirement_ids),
                    "resolution": gap.closure_acceptance_criteria[0] if gap.closure_acceptance_criteria else "",
                }
            )
        if readiness_scorecard:
            for blocker in readiness_scorecard.blockers:
                items.append(
                    {
                        "source": "readiness_scorecard",
                        "owner_role": "proposal_manager",
                        "title": blocker,
                        "severity": "high",
                        "due_hint": "before readiness gate",
                        "related_requirement_id": self._first_req_id(blocker),
                        "resolution": "Regenerate the readiness scorecard after closure or executive exception.",
                    }
                )
        if contract_risk and contract_risk.status in {"critical", "high_risk"}:
            for action in contract_risk.owner_actions:
                items.append(
                    {
                        "source": "contract_risk",
                        "owner_role": action["owner"],
                        "title": "; ".join(action["actions"][:2]),
                        "severity": contract_risk.status,
                        "due_hint": "before legal/security redline review",
                        "related_requirement_id": None,
                        "resolution": "Approve redline, fallback position, or explicit business exception.",
                    }
                )
        for finding in findings:
            if finding.severity not in {"critical", "high"}:
                continue
            items.append(
                {
                    "source": "review_board",
                    "owner_role": self._owner_for_text(finding.message),
                    "title": finding.message,
                    "severity": finding.severity,
                    "due_hint": "before draft freeze",
                    "related_requirement_id": finding.related_requirement_id,
                    "resolution": finding.recommendation,
                }
            )
        return self._dedupe_dicts(items, ("source", "title", "owner_role"))[:20]

    def _readiness_gates(
        self,
        deadline: date,
        matrix: list[RequirementMatrixRow],
        tasks: list[StakeholderTask],
        gaps: list[EvidenceGap],
        blocked_items: list[dict[str, Any]],
        contract_risk: ContractRiskResponse | None,
        win_strategy: WinStrategyResponse | None,
        readiness_scorecard: DealReadinessScorecardResponse | None,
        findings: list[ReviewFinding],
    ) -> list[dict[str, Any]]:
        high_gaps = [gap for gap in gaps if gap.severity in {"critical", "high"}]
        high_findings = [finding for finding in findings if finding.severity in {"critical", "high"}]
        pricing_high = bool(win_strategy and win_strategy.pricing_risk.get("risk_level") == "high")
        final_gate_blocked = bool(
            blocked_items or (readiness_scorecard and readiness_scorecard.readiness_score < 70)
        )
        gates = [
            {
                "gate": "Evidence closure",
                "owner_role": "solutions",
                "due_date": (deadline - timedelta(days=8)).isoformat(),
                "status": "blocked" if high_gaps else "pass",
                "criteria": [
                    "All high-severity evidence gaps have source requests, owners, and acceptance criteria.",
                    "Requirement matrix rows have evidence_refs or documented exception approvals.",
                ],
                "blocking_items": [gap.title for gap in high_gaps[:6]],
            },
            {
                "gate": "Review-board QA",
                "owner_role": "proposal_manager",
                "due_date": (deadline - timedelta(days=4)).isoformat(),
                "status": "blocked" if high_findings else "pass",
                "criteria": [
                    "No critical/high review findings remain unresolved.",
                    "Draft claims are backed by citations or explicit missing-evidence refusals.",
                ],
                "blocking_items": [finding.message for finding in high_findings[:6]],
            },
            {
                "gate": "Legal and security approval",
                "owner_role": "legal",
                "due_date": (deadline - timedelta(days=3)).isoformat(),
                "status": "blocked" if contract_risk and contract_risk.status in {"critical", "high_risk"} else "pass",
                "criteria": [
                    "Contract redlines, security obligations, data processing, and fallback positions are approved.",
                    "Risky clauses have owner actions or executive exception language.",
                ],
                "blocking_items": contract_risk.missing_evidence_warnings[:6] if contract_risk else [],
            },
            {
                "gate": "Pricing and win approval",
                "owner_role": "sales",
                "due_date": (deadline - timedelta(days=2)).isoformat(),
                "status": "blocked" if pricing_high else "pass",
                "criteria": [
                    "Discount, packaging, and payment assumptions are approved.",
                    "Competitive posture and proof points are aligned with sales leadership.",
                ],
                "blocking_items": win_strategy.pricing_risk.get("risk_drivers", [])[:6] if win_strategy else [],
            },
            {
                "gate": "Final submit/no-submit",
                "owner_role": "executive_sponsor",
                "due_date": (deadline - timedelta(days=1)).isoformat(),
                "status": "blocked" if final_gate_blocked else "pass",
                "criteria": [
                    "Readiness score is acceptable or executive exception is recorded.",
                    "No unresolved blocked action-plan tasks remain before portal submission.",
                ],
                "blocking_items": [item["title"] for item in blocked_items[:8]],
            },
        ]
        if matrix and not any(row.evidence_refs for row in matrix):
            gates[0]["status"] = "blocked"
            gates[0]["blocking_items"].append("No requirement matrix rows have attached evidence.")
        if tasks and all(task.status == "ready_for_handoff" for task in tasks):
            gates[-1]["criteria"].append("Stakeholder action plan is ready for handoff.")
        return gates

    def _escalation_triggers(
        self,
        deadline: date,
        blocked_items: list[dict[str, Any]],
        gaps: list[EvidenceGap],
        contract_risk: ContractRiskResponse | None,
        win_strategy: WinStrategyResponse | None,
        readiness_scorecard: DealReadinessScorecardResponse | None,
        red_team_summary: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        triggers = []
        if blocked_items:
            triggers.append(
                {
                    "trigger": "Blocked items remain open",
                    "condition": f"{len(blocked_items)} blocked item(s) exist after owner assignment.",
                    "owner_role": "proposal_manager",
                    "escalate_to": "executive_sponsor",
                    "escalate_by": (deadline - timedelta(days=5)).isoformat(),
                    "action": "Run a blocker review and record owner/date/exception for every item.",
                }
            )
        high_gaps = [gap for gap in gaps if gap.severity in {"critical", "high"}]
        if high_gaps:
            triggers.append(
                {
                    "trigger": "High-severity evidence gap",
                    "condition": f"{len(high_gaps)} high-severity gap(s) affect submission readiness.",
                    "owner_role": "solutions",
                    "escalate_to": "sales_engineering_lead",
                    "escalate_by": (deadline - timedelta(days=7)).isoformat(),
                    "action": "Escalate missing source requests to SMEs and document fallback language.",
                }
            )
        if contract_risk and contract_risk.status in {"critical", "high_risk"}:
            triggers.append(
                {
                    "trigger": "Contract risk above approval threshold",
                    "condition": f"Contract status is {contract_risk.status} with score {contract_risk.risk_score}.",
                    "owner_role": "legal",
                    "escalate_to": "legal_leadership",
                    "escalate_by": (deadline - timedelta(days=6)).isoformat(),
                    "action": "Approve redlines or create an executive exception before pricing approval.",
                }
            )
        if win_strategy and win_strategy.pricing_risk.get("risk_level") == "high":
            triggers.append(
                {
                    "trigger": "High pricing risk",
                    "condition": f"Pricing risk score is {win_strategy.pricing_risk.get('risk_score')}.",
                    "owner_role": "sales",
                    "escalate_to": "finance_and_sales_leadership",
                    "escalate_by": (deadline - timedelta(days=4)).isoformat(),
                    "action": "Approve discount guardrails, payment terms, and walk-away position.",
                }
            )
        if readiness_scorecard and readiness_scorecard.readiness_score < 70:
            triggers.append(
                {
                    "trigger": "Readiness score below submit threshold",
                    "condition": (
                        f"Readiness is {readiness_scorecard.readiness_score}/100 "
                        f"({readiness_scorecard.readiness_level})."
                    ),
                    "owner_role": "proposal_manager",
                    "escalate_to": "executive_sponsor",
                    "escalate_by": (deadline - timedelta(days=3)).isoformat(),
                    "action": "Hold final QA until blockers close or submit/no-submit exception is approved.",
                }
            )
        if red_team_summary and not red_team_summary.get("passed", True):
            triggers.append(
                {
                    "trigger": "Red-team check failed",
                    "condition": "Adversarial local checks found unresolved risk.",
                    "owner_role": "security",
                    "escalate_to": "security_leadership",
                    "escalate_by": (deadline - timedelta(days=5)).isoformat(),
                    "action": "Resolve unsupported claims or convert them into explicit missing-evidence refusals.",
                }
            )
        return triggers or [
            {
                "trigger": "No active escalations",
                "condition": "All provided local signals are within normal submission thresholds.",
                "owner_role": "proposal_manager",
                "escalate_to": "executive_sponsor",
                "escalate_by": (deadline - timedelta(days=2)).isoformat(),
                "action": "Keep the final QA and submission rehearsal on calendar.",
            }
        ]

    def _owner_assignments(
        self,
        milestones: list[TimelineMilestone],
        tasks: list[StakeholderTask],
        gaps: list[EvidenceGap],
        contract_risk: ContractRiskResponse | None,
        win_strategy: WinStrategyResponse | None,
    ) -> list[dict[str, Any]]:
        owner_set = {milestone.owner_role for milestone in milestones}
        owner_set.update(task.owner_role for task in tasks)
        owner_set.update(gap.owner_team for gap in gaps)
        if contract_risk:
            owner_set.update(action["owner"] for action in contract_risk.owner_actions)
        if win_strategy:
            owner_set.update(action["owner"] for action in win_strategy.next_actions_by_owner)
        owners = sorted(owner_set)
        task_counts = Counter(task.owner_role for task in tasks)
        blocked_counts = Counter(task.owner_role for task in tasks if task.status == "blocked")
        gap_counts = Counter(gap.owner_team for gap in gaps)
        milestone_lookup: dict[str, list[str]] = {}
        for milestone in milestones:
            milestone_lookup.setdefault(milestone.owner_role, []).append(milestone.milestone_id)
        return [
            {
                "owner_role": owner,
                "milestone_ids": milestone_lookup.get(owner, []),
                "milestone_count": len(milestone_lookup.get(owner, [])),
                "action_plan_items": task_counts.get(owner, 0),
                "blocked_items": blocked_counts.get(owner, 0),
                "evidence_gaps": gap_counts.get(owner, 0),
                "responsibility": self._owner_responsibility(owner),
            }
            for owner in owners
        ]

    def _calendar_entry(self, milestone: TimelineMilestone) -> dict[str, Any]:
        return {
            "uid": f"{milestone.milestone_id}@local-rfp-copilot",
            "title": milestone.title,
            "date": milestone.due_date,
            "start_time": "09:00",
            "end_time": "10:00",
            "owner_role": milestone.owner_role,
            "location": "Local RFP workspace",
            "description": milestone.description,
            "category": milestone.category,
            "depends_on": milestone.dependencies,
            "local_command": "python -m app.demo" if milestone.category == "submission" else None,
        }

    def _submission_deadline(self, analysis: AnalyzeResponse | None) -> date:
        if analysis:
            for item in analysis.deadlines:
                parsed = self._parse_deadline(item)
                if parsed:
                    return parsed
        return date(2026, 7, 18)

    def _parse_deadline(self, value: str) -> date | None:
        cleaned = value.strip()
        for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(cleaned, fmt).date()
            except ValueError:
                continue
        return None

    def _deadline_signals(self, analysis: AnalyzeResponse | None) -> list[str]:
        if not analysis:
            return ["No RFP analysis supplied; fallback sample deadline used."]
        signals = [f"Detected deadline: {deadline}" for deadline in analysis.deadlines]
        signals.extend(f"RFP risk: {risk}" for risk in analysis.risks[:3])
        return signals

    def _gap_signals(self, gaps: list[EvidenceGap], source_request_pack: dict[str, Any] | None) -> list[str]:
        signals = [f"{gap.gap_id}: {gap.severity} / {gap.owner_team}" for gap in gaps[:6]]
        if source_request_pack:
            summary = source_request_pack.get("summary", {})
            signals.append(f"Source request pack gaps: {summary.get('gap_count')}")
        return signals

    def _contract_signals(self, contract_risk: ContractRiskResponse | None) -> list[str]:
        if not contract_risk:
            return ["No contract risk supplied."]
        signals = [
            f"Contract status: {contract_risk.status}",
            f"Contract score: {contract_risk.risk_score}",
        ]
        signals.extend(f"{clause.clause_id}: {clause.category}" for clause in contract_risk.risky_clauses[:4])
        return signals

    def _win_signals(self, win_strategy: WinStrategyResponse | None) -> list[str]:
        if not win_strategy:
            return ["No win strategy supplied."]
        return [
            f"Win score: {win_strategy.win_score}",
            f"Win level: {win_strategy.win_level}",
            f"Pricing risk: {win_strategy.pricing_risk.get('risk_level')}",
            *win_strategy.red_flags[:4],
        ]

    def _readiness_signals(
        self,
        readiness_scorecard: DealReadinessScorecardResponse | None,
        leadership_brief: dict[str, Any] | None,
    ) -> list[str]:
        if not readiness_scorecard:
            return ["No readiness scorecard supplied."]
        signals = [
            f"Readiness score: {readiness_scorecard.readiness_score}",
            f"Readiness level: {readiness_scorecard.readiness_level}",
        ]
        signals.extend(readiness_scorecard.blockers[:4])
        if leadership_brief:
            metrics = leadership_brief.get("metrics", {})
            signals.append(f"Leadership brief requirements: {metrics.get('requirements')}")
        return signals

    def _source_request_context(self, pack: dict[str, Any] | None) -> dict[str, Any] | None:
        if not pack:
            return None
        return {
            "summary": pack.get("summary", {}),
            "owner_matrix": pack.get("owner_matrix", []),
            "source_request_count": len(pack.get("source_request_emails_tasks", [])),
        }

    def _leadership_context(self, brief: dict[str, Any] | None) -> dict[str, Any] | None:
        if not brief:
            return None
        return {
            "metrics": brief.get("metrics", {}),
            "recommended_next_meeting_agenda": brief.get("recommended_next_meeting_agenda", []),
            "artifact_links": brief.get("artifact_links", {}),
        }

    def _related_requirement_ids(
        self,
        category: str,
        matrix: list[RequirementMatrixRow],
        gaps: list[EvidenceGap],
    ) -> list[str]:
        if category == "evidence":
            return self._unique([req_id for gap in gaps for req_id in gap.requirement_ids])[:8]
        if category in {"legal_security", "commercial"}:
            wanted = {"security", "compliance", "pricing", "legal"} if category == "legal_security" else {"pricing"}
            return [row.requirement_id for row in matrix if row.category in wanted][:8]
        if category == "drafting":
            return [row.requirement_id for row in matrix[:8]]
        return []

    def _dependency_risk(self, category: str) -> str:
        return {
            "evidence": "SMEs may not have enough time to source approved proof before draft freeze.",
            "drafting": "Late content changes can invalidate citations and review-board findings.",
            "legal_security": "Unapproved redlines or security claims can block submission approval.",
            "commercial": "Pricing assumptions can be submitted without finance or sales leadership approval.",
            "readiness": "Final submit/no-submit decision may lack current blockers and exception status.",
            "qa": "Portal upload and attachment checks can compress into submission day.",
            "submission": "Missed gate can cause a late or incomplete response package.",
        }.get(category, "Missed dependency can compress downstream response work.")

    def _owner_responsibility(self, owner: str) -> str:
        return {
            "proposal_manager": "Owns timeline, readiness gates, QA, escalation cadence, and final package.",
            "solutions": "Owns response substance, SME coordination, implementation details, and evidence closure.",
            "security": "Owns security proof, red-team remediation, control claims, and security approvals.",
            "legal": "Owns contract terms, DPA/privacy posture, redlines, and legal exception language.",
            "sales": "Owns customer coordination, win posture, pricing alignment, and final submission.",
            "finance": "Owns discount, payment, and packaging approval.",
            "product": "Owns roadmap, feature, workflow, and product evidence approvals.",
            "engineering": "Owns integration feasibility and technical implementation commitments.",
            "executive_sponsor": "Owns submit/no-submit approval and exception acceptance.",
        }.get(owner, "Owns assigned RFP response actions and exception closure.")

    def _owner_for_text(self, text: str) -> str:
        lowered = text.lower()
        if any(term in lowered for term in ["contract", "legal", "dpa", "gdpr", "liability", "indemnity"]):
            return "legal"
        if any(term in lowered for term in ["security", "encryption", "sso", "fedramp", "audit", "control"]):
            return "security"
        if any(term in lowered for term in ["pricing", "price", "discount", "commercial"]):
            return "sales"
        if any(term in lowered for term in ["feature", "dashboard", "workflow", "roadmap"]):
            return "product"
        return "solutions"

    def _first_req_id(self, text: str) -> str | None:
        match = re.search(r"\breq[_a-zA-Z0-9-]+", text)
        return match.group(0) if match else None

    def _dedupe_dicts(self, items: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
        deduped = []
        seen = set()
        for item in items:
            key = tuple(item.get(field) for field in keys)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _unique(self, items: list[str]) -> list[str]:
        return [item for item in dict.fromkeys(str(item) for item in items if str(item).strip())]

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        summary = pack["summary"]
        lines = [
            "# Proposal Timeline Orchestrator + Submission Calendar Pack",
            "",
            "## Summary",
            "",
            f"- Submission deadline: {summary['submission_deadline']}",
            f"- Milestone count: {summary['milestone_count']}",
            f"- Blocked count: {summary['blocked_count']}",
            f"- Readiness: {summary['readiness_score']} ({summary['readiness_level']})",
            f"- Contract status: {summary['contract_risk_status']}",
            "",
            "## Milestone Calendar",
            "",
            "| Date | Milestone | Owner | Status | Dependencies |",
            "| --- | --- | --- | --- | --- |",
        ]
        for milestone in pack["milestone_calendar"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._md_cell(milestone["due_date"]),
                        self._md_cell(milestone["title"]),
                        self._md_cell(milestone["owner_role"]),
                        self._md_cell(milestone["status"]),
                        self._md_cell(", ".join(milestone["dependencies"]) or "None"),
                    ]
                )
                + " |"
            )
        lines.extend(["", "## Owner Matrix", ""])
        lines.extend(["| Owner | Milestones | Action Items | Blocked | Evidence Gaps | Responsibility |"])
        lines.extend(["| --- | --- | --- | --- | --- | --- |"])
        for owner in pack["owner_matrix"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._md_cell(owner["owner_role"]),
                        self._md_cell(owner["milestone_count"]),
                        self._md_cell(owner["action_plan_items"]),
                        self._md_cell(owner["blocked_items"]),
                        self._md_cell(owner["evidence_gaps"]),
                        self._md_cell(owner["responsibility"]),
                    ]
                )
                + " |"
            )
        lines.extend(["", "## Dependency and Risk Buffers", ""])
        lines.extend(["### Dependencies", ""])
        self._append_dict_list(lines, pack["dependencies"], ["from", "to", "risk_if_missed"])
        lines.extend(["", "### Risk Buffers", ""])
        self._append_dict_list(lines, pack["dependency_risk_buffers"], ["name", "owner_role", "buffer_days", "reason"])
        lines.extend(["", "## Blocked Items", ""])
        self._append_dict_list(lines, pack["blocked_items"], ["source", "owner_role", "title", "resolution"])
        lines.extend(["", "## Readiness Gates", ""])
        self._append_dict_list(lines, pack["readiness_gates"], ["gate", "owner_role", "due_date", "status"])
        lines.extend(["", "## Escalation Triggers", ""])
        self._append_dict_list(lines, pack["escalation_triggers"], ["trigger", "owner_role", "escalate_to", "action"])
        lines.extend(["", "## Local Calendar-Friendly Entries", ""])
        self._append_dict_list(lines, pack["calendar_entries"], ["date", "start_time", "title", "owner_role"])
        lines.extend(["", "## Exact Local Commands", ""])
        lines.extend(f"```bash\n{command}\n```" for command in pack["local_commands"])
        lines.extend(["", "## JD Skills Demonstrated", ""])
        lines.extend(f"- {item}" for item in pack["jd_skills_demonstrated"])
        lines.extend(["", "## Five Interviewer Talking Points", ""])
        lines.extend(f"- {item}" for item in pack["interviewer_talking_points"])
        return "\n".join(lines).strip() + "\n"

    def _append_dict_list(self, lines: list[str], items: list[dict[str, Any]], fields: list[str]) -> None:
        if not items:
            lines.append("- None")
            return
        for item in items:
            parts = [f"{field}={self._md_cell(item.get(field))}" for field in fields]
            lines.append(f"- {'; '.join(parts)}")

    def _md_cell(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
