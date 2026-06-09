from __future__ import annotations

import json
import re
from typing import Any

from app.core.config import Settings
from app.models.api import (
    ContractRiskResponse,
    DealReadinessScorecardResponse,
    EvaluationMetrics,
    ExecutiveSubmissionMemoResponse,
    SubmissionDecisionResponse,
    TimelinePlanResponse,
    WinStrategyResponse,
)
from app.models.domain import Answer, DraftResponse, EvidenceGap, RequirementMatrixRow, ReviewFinding, StakeholderTask


class SubmissionDecisionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_decision(
        self,
        trace_id: str,
        requirement_matrix: list[RequirementMatrixRow] | None = None,
        draft_response: DraftResponse | None = None,
        answers: list[Answer] | None = None,
        review_findings: list[ReviewFinding] | None = None,
        review_passed: bool | None = None,
        action_plan: list[StakeholderTask] | None = None,
        readiness_scorecard: DealReadinessScorecardResponse | None = None,
        eval_metrics: EvaluationMetrics | None = None,
        red_team_summary: dict[str, Any] | None = None,
        win_strategy: WinStrategyResponse | None = None,
        contract_risk: ContractRiskResponse | None = None,
        evidence_gaps: list[EvidenceGap] | None = None,
        source_request_pack: dict[str, Any] | None = None,
        timeline_plan: TimelinePlanResponse | None = None,
        leadership_brief: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        artifact_links: dict[str, Any] | None = None,
    ) -> SubmissionDecisionResponse:
        matrix = requirement_matrix or []
        findings = review_findings or []
        tasks = action_plan or []
        gaps = evidence_gaps or []
        answer_list = answers or []
        blocking_issues = self._blocking_issues(
            matrix=matrix,
            findings=findings,
            tasks=tasks,
            readiness=readiness_scorecard,
            eval_metrics=eval_metrics,
            red_team=red_team_summary,
            win_strategy=win_strategy,
            contract_risk=contract_risk,
            gaps=gaps,
            timeline=timeline_plan,
            draft=draft_response,
            answers=answer_list,
        )
        exceptions = self._exceptions(
            findings=findings,
            tasks=tasks,
            readiness=readiness_scorecard,
            red_team=red_team_summary,
            win_strategy=win_strategy,
            contract_risk=contract_risk,
            gaps=gaps,
            source_request_pack=source_request_pack,
            timeline=timeline_plan,
        )
        score = self._score(
            blocking_issues=blocking_issues,
            exceptions=exceptions,
            readiness=readiness_scorecard,
            eval_metrics=eval_metrics,
            red_team=red_team_summary,
            win_strategy=win_strategy,
            contract_risk=contract_risk,
            gaps=gaps,
            timeline=timeline_plan,
            draft=draft_response,
            answers=answer_list,
        )
        decision = self._decision(score, blocking_issues)
        approvals = self._approvals_required(decision, exceptions, blocking_issues, win_strategy, contract_risk, gaps)
        owner_actions = self._owner_actions(
            tasks=tasks,
            readiness=readiness_scorecard,
            win_strategy=win_strategy,
            contract_risk=contract_risk,
            gaps=gaps,
            source_request_pack=source_request_pack,
            timeline=timeline_plan,
        )
        links = self._artifact_links(
            supplied_links=artifact_links or {},
            leadership_brief=leadership_brief,
            source_request_pack=source_request_pack,
            timeline=timeline_plan,
        )
        summary = self._summary(
            matrix=matrix,
            draft=draft_response,
            answers=answer_list,
            findings=findings,
            review_passed=review_passed,
            readiness=readiness_scorecard,
            eval_metrics=eval_metrics,
            red_team=red_team_summary,
            win_strategy=win_strategy,
            contract_risk=contract_risk,
            gaps=gaps,
            timeline=timeline_plan,
            metrics=metrics,
        )
        rationale = self._rationale(decision, score, summary, blocking_issues, exceptions)
        return SubmissionDecisionResponse(
            decision=decision,
            score=score,
            blocking_issues=blocking_issues,
            exception_list=exceptions,
            approvals_required=approvals,
            owner_actions=owner_actions,
            artifact_links=links,
            rationale=rationale,
            local_verification_commands=self._local_commands(),
            summary=summary,
            trace_id=trace_id,
        )

    def export_memo(
        self,
        trace_id: str,
        decision: SubmissionDecisionResponse,
        write_artifact: bool = True,
    ) -> ExecutiveSubmissionMemoResponse:
        memo = {
            "trace_id": trace_id,
            "go_no_go_summary": {
                "decision": decision.decision,
                "score": decision.score,
                "rationale": decision.rationale,
            },
            "risks_exceptions": {
                "blocking_issues": decision.blocking_issues,
                "exception_list": decision.exception_list,
                "approvals_required": decision.approvals_required,
            },
            "evidence_posture": {
                "evidence_coverage": decision.summary.get("evidence_coverage"),
                "citation_count": decision.summary.get("citation_count"),
                "evidence_gaps": decision.summary.get("evidence_gap_count"),
                "high_severity_gaps": decision.summary.get("high_severity_gap_count"),
                "source_request_pack": decision.artifact_links.get("source_request_pack"),
            },
            "owner_signoffs": decision.owner_actions,
            "timeline_readiness": {
                "submission_deadline": decision.summary.get("submission_deadline"),
                "timeline_blocked_count": decision.summary.get("timeline_blocked_count"),
                "readiness_level": decision.summary.get("readiness_level"),
                "readiness_score": decision.summary.get("readiness_score"),
                "timeline_plan": decision.artifact_links.get("timeline_plan"),
            },
            "artifact_links": decision.artifact_links,
            "local_commands": decision.local_verification_commands,
            "jd_skills_demonstrated": [
                (
                    "Final go/no-go orchestration across readiness, RAG evidence, review, red-team, legal, pricing, "
                    "and timeline signals."
                ),
                "Deterministic FastAPI service with typed Pydantic inputs and local-only Markdown/JSON artifacts.",
                "Executive decision memo generation that maps risks to owner actions and approval paths.",
                "Citation and evidence posture checks that prevent unsupported claims from reaching submission.",
                (
                    "Portfolio-ready verification loop with pytest, ruff, evals, red-team checks, demo, and "
                    "dashboard coverage."
                ),
            ],
            "interviewer_talking_points": [
                (
                    "The final gate converts many workflow artifacts into one leadership decision instead of "
                    "another report."
                ),
                "Submit, submit with exceptions, and do-not-submit outcomes are deterministic and explainable.",
                "Legal, security, finance, sales, and executive approvals are derived from the actual risk signals.",
                "The memo is fully local and writes both Markdown and JSON under ignored storage.",
                "The dashboard and demo make the same service visible without needing external systems.",
            ],
        }
        markdown = self._render_memo_markdown(memo)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            memo_dir = self.settings.storage_dir / "submission_memos"
            memo_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = memo_dir / f"executive_submission_memo_{safe_trace_id}.md"
            json_path = memo_dir / f"executive_submission_memo_{safe_trace_id}.json"
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(memo, indent=2), encoding="utf-8")
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
        return ExecutiveSubmissionMemoResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            memo=memo,
            trace_id=trace_id,
        )

    def _score(
        self,
        blocking_issues: list[dict[str, Any]],
        exceptions: list[dict[str, Any]],
        readiness: DealReadinessScorecardResponse | None,
        eval_metrics: EvaluationMetrics | None,
        red_team: dict[str, Any] | None,
        win_strategy: WinStrategyResponse | None,
        contract_risk: ContractRiskResponse | None,
        gaps: list[EvidenceGap],
        timeline: TimelinePlanResponse | None,
        draft: DraftResponse | None,
        answers: list[Answer],
    ) -> int:
        score = readiness.readiness_score if readiness else 70
        score -= min(26, sum(self._severity_penalty(item["severity"]) for item in blocking_issues))
        score -= min(12, len(exceptions) * 2)
        if eval_metrics and not eval_metrics.passed:
            score -= 8
        if eval_metrics and eval_metrics.citation_coverage < 0.75:
            score -= min(8, int(round((0.75 - eval_metrics.citation_coverage) * 20)))
        if red_team and not red_team.get("passed", True):
            score -= 12
        if win_strategy:
            if win_strategy.win_score < 60:
                score -= 8
            if win_strategy.pricing_risk.get("risk_level") == "high":
                score -= 8
        if contract_risk and contract_risk.status in {"critical", "high_risk"}:
            score -= 10
        score -= min(10, sum(1 for gap in gaps if gap.severity in {"critical", "high"}) * 3)
        if timeline:
            score -= min(8, int(timeline.summary.get("blocked_count", 0)) * 2)
        citation_count = self._citation_count(draft, answers)
        if draft and not draft.sections:
            score -= 8
        if citation_count == 0:
            score -= 10
        return max(0, min(100, int(round(score))))

    def _decision(self, score: int, blocking_issues: list[dict[str, Any]]) -> str:
        critical_blockers = [item for item in blocking_issues if item["severity"] == "critical"]
        high_blockers = [item for item in blocking_issues if item["severity"] == "high"]
        if score >= 85 and not critical_blockers and not high_blockers:
            return "submit"
        if score >= 65 and not critical_blockers:
            return "submit_with_exceptions"
        return "do_not_submit"

    def _blocking_issues(
        self,
        matrix: list[RequirementMatrixRow],
        findings: list[ReviewFinding],
        tasks: list[StakeholderTask],
        readiness: DealReadinessScorecardResponse | None,
        eval_metrics: EvaluationMetrics | None,
        red_team: dict[str, Any] | None,
        win_strategy: WinStrategyResponse | None,
        contract_risk: ContractRiskResponse | None,
        gaps: list[EvidenceGap],
        timeline: TimelinePlanResponse | None,
        draft: DraftResponse | None,
        answers: list[Answer],
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        for row in matrix:
            if row.status == "blocked" or (row.priority == "high" and not row.evidence_refs):
                issues.append(
                    self._issue(
                        "requirement",
                        "high" if row.risk_level != "critical" else "critical",
                        row.owner_role,
                        f"{row.requirement_id}: {row.requirement_text}",
                        row.requirement_id,
                    )
                )
        for finding in findings:
            if finding.severity in {"critical", "high"}:
                issues.append(
                    self._issue(
                        "review_board",
                        finding.severity,
                        self._owner_for_text(f"{finding.category} {finding.message}"),
                        finding.message,
                        finding.related_requirement_id,
                    )
                )
        for task in tasks:
            if task.status == "blocked":
                issues.append(
                    self._issue(
                        "owner_status",
                        task.risk_level,
                        task.owner_role,
                        task.title,
                        task.source_requirement_id,
                    )
                )
        if readiness:
            for blocker in readiness.blockers:
                issues.append(self._issue("readiness", "high", "proposal_manager", blocker, None))
        if eval_metrics and not eval_metrics.passed:
            issues.append(self._issue("standard_eval", "high", "proposal_manager", "Standard eval did not pass.", None))
        if red_team and not red_team.get("passed", True):
            issues.append(self._issue("red_team", "high", "security", "Red-team checks did not pass.", None))
        if win_strategy and win_strategy.pricing_risk.get("risk_level") == "high":
            issues.append(self._issue("pricing", "high", "finance", "Pricing risk is high.", None))
        if contract_risk and contract_risk.status in {"critical", "high_risk"}:
            severity = "critical" if contract_risk.status == "critical" else "high"
            issues.append(self._issue("contract", severity, "legal", f"Contract risk is {contract_risk.status}.", None))
        for gap in gaps:
            if gap.severity in {"critical", "high"}:
                issues.append(self._issue("evidence_gap", gap.severity, gap.owner_team, gap.title, gap.gap_id))
        if timeline:
            for blocked in timeline.blocked_items:
                issues.append(
                    self._issue(
                        "timeline",
                        "high",
                        str(blocked.get("owner_role", "proposal_manager")),
                        str(blocked.get("title", "Timeline blocked item")),
                        str(blocked.get("source_id") or ""),
                    )
                )
        if not draft or not draft.sections:
            issues.append(self._issue("draft", "critical", "proposal_manager", "No draft sections are ready.", None))
        if self._citation_count(draft, answers) == 0:
            issues.append(self._issue("citations", "high", "proposal_manager", "No citations are attached.", None))
        return self._dedupe_issues(issues)[:16]

    def _exceptions(
        self,
        findings: list[ReviewFinding],
        tasks: list[StakeholderTask],
        readiness: DealReadinessScorecardResponse | None,
        red_team: dict[str, Any] | None,
        win_strategy: WinStrategyResponse | None,
        contract_risk: ContractRiskResponse | None,
        gaps: list[EvidenceGap],
        source_request_pack: dict[str, Any] | None,
        timeline: TimelinePlanResponse | None,
    ) -> list[dict[str, Any]]:
        exceptions: list[dict[str, Any]] = []
        for finding in findings:
            if finding.severity == "medium":
                exceptions.append(
                    self._exception("review_board", "proposal_manager", finding.message, finding.recommendation)
                )
        for task in tasks:
            if task.status in {"needs_review", "ready_for_handoff"} and task.risk_level in {"medium", "high"}:
                exceptions.append(self._exception("owner_status", task.owner_role, task.title, task.description))
        if readiness and readiness.readiness_level == "mostly_ready":
            exceptions.append(
                self._exception(
                    "readiness",
                    "executive_sponsor",
                    "Readiness is mostly ready but not clean.",
                    "Approve listed blockers as exceptions or require closure before submission.",
                )
            )
        if red_team and red_team.get("missing_evidence_detection_count", 0):
            exceptions.append(
                self._exception(
                    "red_team",
                    "security",
                    "Red-team found missing-evidence-sensitive questions.",
                    "Confirm all detections are cited, refused, or approved as exceptions.",
                )
            )
        if win_strategy and win_strategy.pricing_risk.get("risk_level") in {"medium", "high"}:
            exceptions.append(
                self._exception(
                    "pricing",
                    "finance",
                    f"Pricing risk is {win_strategy.pricing_risk.get('risk_level')}.",
                    "Approve discount, payment, and packaging assumptions.",
                )
            )
        if contract_risk and contract_risk.status in {"needs_legal_review", "high_risk", "critical"}:
            exceptions.append(
                self._exception(
                    "contract",
                    "legal",
                    f"Contract status is {contract_risk.status}.",
                    "Approve redlines, fallbacks, or walk-away terms.",
                )
            )
        for gap in gaps:
            if gap.severity == "medium":
                exceptions.append(
                    self._exception("evidence_gap", gap.owner_team, gap.title, gap.suggested_sme_or_source_request)
                )
        if source_request_pack:
            summary = source_request_pack.get("summary", {})
            if summary.get("gap_count", 0):
                exceptions.append(
                    self._exception(
                        "source_request_pack",
                        "proposal_manager",
                        f"{summary.get('gap_count')} source request gap(s) remain tracked.",
                        "Confirm each source request has an owner, due date, and closure criteria.",
                    )
                )
        if timeline:
            for gate in timeline.readiness_gates:
                if gate.get("status") == "blocked":
                    exceptions.append(
                        self._exception(
                            "timeline_gate",
                            str(gate.get("owner_role", "proposal_manager")),
                            str(gate.get("gate", "Readiness gate")) + " is blocked.",
                            "Approve gate exception or move submission date.",
                        )
                    )
        return self._dedupe_exceptions(exceptions)[:16]

    def _approvals_required(
        self,
        decision: str,
        exceptions: list[dict[str, Any]],
        blockers: list[dict[str, Any]],
        win_strategy: WinStrategyResponse | None,
        contract_risk: ContractRiskResponse | None,
        gaps: list[EvidenceGap],
    ) -> list[dict[str, Any]]:
        owners = {"sales_leadership": "Final sales submission approval."}
        if decision != "submit":
            owners["executive_sponsor"] = "Approve exception path or do-not-submit recommendation."
        for item in exceptions + blockers:
            owner = self._approval_owner(str(item.get("owner", "")), str(item.get("source", "")))
            owners[owner] = self._approval_reason(owner)
        if win_strategy and win_strategy.pricing_risk.get("risk_level") in {"medium", "high"}:
            owners["finance"] = "Approve pricing, discount, payment, and packaging risk."
        if contract_risk and contract_risk.status != "acceptable":
            owners["legal"] = "Approve contract redlines and exception posture."
        if any(gap.owner_team == "security" for gap in gaps):
            owners["security"] = "Approve security evidence and red-team posture."
        return [{"owner": owner, "reason": reason} for owner, reason in sorted(owners.items())]

    def _owner_actions(
        self,
        tasks: list[StakeholderTask],
        readiness: DealReadinessScorecardResponse | None,
        win_strategy: WinStrategyResponse | None,
        contract_risk: ContractRiskResponse | None,
        gaps: list[EvidenceGap],
        source_request_pack: dict[str, Any] | None,
        timeline: TimelinePlanResponse | None,
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for task in tasks:
            if task.status in {"blocked", "needs_review"}:
                actions.append(
                    {
                        "owner": task.owner_role,
                        "action": task.title,
                        "status": task.status,
                        "due": task.due_hint,
                        "source": "action_plan",
                    }
                )
        if readiness:
            actions.extend(
                {
                    "owner": "proposal_manager",
                    "action": action,
                    "status": "open",
                    "due": "before executive submission review",
                    "source": "readiness",
                }
                for action in readiness.recommended_next_actions
            )
        if win_strategy:
            actions.extend(
                {
                    "owner": action.get("owner", "sales"),
                    "action": action.get("action", action.get("next_action", "Resolve win-strategy action.")),
                    "status": "open",
                    "due": "before final pricing approval",
                    "source": "win_strategy",
                }
                for action in win_strategy.next_actions_by_owner
            )
        if contract_risk:
            actions.extend(
                {
                    "owner": action.get("owner", "legal"),
                    "action": action.get("action", action.get("title", "Resolve contract-risk action.")),
                    "status": "open",
                    "due": "before legal sign-off",
                    "source": "contract_risk",
                }
                for action in contract_risk.owner_actions
            )
        actions.extend(
            {
                "owner": gap.owner_team,
                "action": gap.suggested_sme_or_source_request,
                "status": "open",
                "due": gap.due_date_recommendation,
                "source": "evidence_gap",
            }
            for gap in gaps[:8]
        )
        for request in (source_request_pack or {}).get("source_request_emails_tasks", [])[:6]:
            actions.append(
                {
                    "owner": request.get("owner_team", "proposal_manager"),
                    "action": request.get("subject", "Complete source request."),
                    "status": "open",
                    "due": request.get("due", "before final QA"),
                    "source": "source_request_pack",
                }
            )
        if timeline:
            actions.extend(
                {
                    "owner": item.get("owner_role", "proposal_manager"),
                    "action": item.get("resolution", item.get("title", "Resolve blocked timeline item.")),
                    "status": "blocked",
                    "due": "before final QA",
                    "source": "timeline",
                }
                for item in timeline.blocked_items[:6]
            )
        return self._dedupe_actions(actions)[:24]

    def _summary(
        self,
        matrix: list[RequirementMatrixRow],
        draft: DraftResponse | None,
        answers: list[Answer],
        findings: list[ReviewFinding],
        review_passed: bool | None,
        readiness: DealReadinessScorecardResponse | None,
        eval_metrics: EvaluationMetrics | None,
        red_team: dict[str, Any] | None,
        win_strategy: WinStrategyResponse | None,
        contract_risk: ContractRiskResponse | None,
        gaps: list[EvidenceGap],
        timeline: TimelinePlanResponse | None,
        metrics: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "requirements": len(matrix),
            "draft_sections": len(draft.sections) if draft else 0,
            "citation_count": self._citation_count(draft, answers),
            "evidence_coverage": readiness.evidence_coverage if readiness else self._matrix_evidence_coverage(matrix),
            "review_passed": review_passed,
            "review_findings": len(findings),
            "readiness_score": readiness.readiness_score if readiness else None,
            "readiness_level": readiness.readiness_level if readiness else None,
            "eval_passed": eval_metrics.passed if eval_metrics else None,
            "red_team_passed": red_team.get("passed") if red_team else None,
            "win_score": win_strategy.win_score if win_strategy else None,
            "pricing_risk": win_strategy.pricing_risk.get("risk_level") if win_strategy else None,
            "contract_risk_score": contract_risk.risk_score if contract_risk else None,
            "contract_status": contract_risk.status if contract_risk else None,
            "evidence_gap_count": len(gaps),
            "high_severity_gap_count": sum(1 for gap in gaps if gap.severity in {"critical", "high"}),
            "timeline_blocked_count": timeline.summary.get("blocked_count") if timeline else None,
            "submission_deadline": timeline.summary.get("submission_deadline") if timeline else None,
            "metrics": metrics or {},
        }

    def _rationale(
        self,
        decision: str,
        score: int,
        summary: dict[str, Any],
        blockers: list[dict[str, Any]],
        exceptions: list[dict[str, Any]],
    ) -> list[str]:
        label = decision.replace("_", " ")
        rationale = [f"Decision is {label} with final gate score {score}/100."]
        readiness = summary.get("readiness_score")
        if readiness is not None:
            rationale.append(f"Readiness is {readiness} ({summary.get('readiness_level')}).")
        rationale.append(
            f"Evidence posture: coverage={summary.get('evidence_coverage')} citations={summary.get('citation_count')} "
            f"gaps={summary.get('evidence_gap_count')} high_gaps={summary.get('high_severity_gap_count')}."
        )
        rationale.append(
            f"Risk posture: blockers={len(blockers)} exceptions={len(exceptions)} "
            f"contract={summary.get('contract_status')} pricing={summary.get('pricing_risk')} "
            f"red_team_passed={summary.get('red_team_passed')}."
        )
        if decision == "do_not_submit":
            rationale.append(
                "Leadership should hold submission until critical/high blockers are closed or the deal is re-scoped."
            )
        elif decision == "submit_with_exceptions":
            rationale.append("Submission can proceed only with explicit owner approvals for listed exceptions.")
        else:
            rationale.append("No high-severity blockers remain in the provided local signals.")
        return rationale

    def _artifact_links(
        self,
        supplied_links: dict[str, Any],
        leadership_brief: dict[str, Any] | None,
        source_request_pack: dict[str, Any] | None,
        timeline: TimelinePlanResponse | None,
    ) -> dict[str, Any]:
        links = dict(supplied_links)
        if leadership_brief:
            links.setdefault("leadership_brief", leadership_brief.get("artifact_links", {}))
        if source_request_pack:
            links.setdefault("source_request_pack", source_request_pack.get("summary", {}))
        if timeline:
            links.setdefault(
                "timeline_plan",
                {
                    "trace_id": timeline.trace_id,
                    "milestones": timeline.summary.get("milestone_count"),
                    "blocked": timeline.summary.get("blocked_count"),
                },
            )
        return links

    def _render_memo_markdown(self, memo: dict[str, Any]) -> str:
        summary = memo["go_no_go_summary"]
        risks = memo["risks_exceptions"]
        evidence = memo["evidence_posture"]
        timeline = memo["timeline_readiness"]
        lines = [
            "# Executive Submission Decision Memo",
            "",
            "## Go/No-Go Summary",
            "",
            f"- Decision: {summary['decision']}",
            f"- Score: {summary['score']}",
            "",
            "Rationale:",
            *[f"- {item}" for item in summary["rationale"]],
            "",
            "## Risks and Exceptions",
            "",
            f"- Blocking issues: {len(risks['blocking_issues'])}",
            f"- Exceptions: {len(risks['exception_list'])}",
            f"- Approvals required: {len(risks['approvals_required'])}",
            "",
            "Blocking issues:",
        ]
        self._append_dict_list(lines, risks["blocking_issues"], ["source", "severity", "owner", "title"])
        lines.extend(["", "Exceptions:"])
        self._append_dict_list(lines, risks["exception_list"], ["source", "owner", "title", "resolution"])
        lines.extend(["", "Approvals required:"])
        self._append_dict_list(lines, risks["approvals_required"], ["owner", "reason"])
        lines.extend(
            [
                "",
                "## Evidence Posture",
                "",
                f"- Evidence coverage: {evidence['evidence_coverage']}",
                f"- Citation count: {evidence['citation_count']}",
                f"- Evidence gaps: {evidence['evidence_gaps']}",
                f"- High-severity gaps: {evidence['high_severity_gaps']}",
                "",
                "## Owner Sign-Offs",
                "",
            ]
        )
        self._append_dict_list(lines, memo["owner_signoffs"], ["owner", "action", "status", "due", "source"])
        lines.extend(
            [
                "",
                "## Timeline Readiness",
                "",
                f"- Submission deadline: {timeline['submission_deadline']}",
                f"- Timeline blocked count: {timeline['timeline_blocked_count']}",
                f"- Readiness: {timeline['readiness_score']} ({timeline['readiness_level']})",
                "",
                "## Artifact Links",
                "",
            ]
        )
        for key, value in sorted(memo["artifact_links"].items()):
            lines.append(f"- {self._md_cell(key)}: {self._md_cell(value)}")
        lines.extend(["", "## Local Commands", ""])
        lines.extend(f"```bash\n{command}\n```" for command in memo["local_commands"])
        lines.extend(["", "## JD Skills Demonstrated", ""])
        lines.extend(f"- {item}" for item in memo["jd_skills_demonstrated"])
        lines.extend(["", "## Five Interviewer Talking Points", ""])
        lines.extend(f"- {item}" for item in memo["interviewer_talking_points"])
        return "\n".join(lines).strip() + "\n"

    def _local_commands(self) -> list[str]:
        return [
            "python -m pytest -q",
            "python -m ruff check .",
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            "python -m app.demo",
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/submission-decision" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/executive-submission-memo" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'rg "submission-decision|executive-submission-memo|Submission Decision|submission_memos|go/no-go" '
                "app dashboard docs README.md tests sample_data Makefile"
            ),
            "Get-ChildItem storage\\submission_memos",
        ]

    def _issue(self, source: str, severity: str, owner: str, title: str, related_id: str | None) -> dict[str, Any]:
        return {
            "source": source,
            "severity": self._normalize_severity(severity),
            "owner": self._owner_slug(owner),
            "title": title,
            "related_id": related_id,
        }

    def _exception(self, source: str, owner: str, title: str, resolution: str) -> dict[str, Any]:
        return {
            "source": source,
            "owner": self._owner_slug(owner),
            "title": title,
            "resolution": resolution,
        }

    def _citation_count(self, draft: DraftResponse | None, answers: list[Answer]) -> int:
        keys = set()
        if draft:
            keys.update((citation.document_id, citation.chunk_id, citation.filename) for citation in draft.citations)
        for answer in answers:
            keys.update((citation.document_id, citation.chunk_id, citation.filename) for citation in answer.citations)
        return len(keys)

    def _matrix_evidence_coverage(self, matrix: list[RequirementMatrixRow]) -> float:
        if not matrix:
            return 0.0
        covered = sum(1 for row in matrix if row.evidence_refs and not row.missing_evidence)
        return round(covered / len(matrix), 2)

    def _severity_penalty(self, severity: str) -> int:
        return {"critical": 8, "high": 5, "medium": 2, "low": 1}.get(self._normalize_severity(severity), 2)

    def _normalize_severity(self, severity: str) -> str:
        lowered = severity.lower()
        if lowered in {"critical", "high", "medium", "low"}:
            return lowered
        if lowered in {"blocked", "not_ready"}:
            return "high"
        return "medium"

    def _approval_owner(self, owner: str, source: str) -> str:
        normalized = self._owner_slug(owner)
        if source in {"contract", "timeline_gate"} and normalized in {"proposal_manager", "solutions"}:
            return "legal"
        if source == "pricing":
            return "finance"
        if source in {"red_team", "citations"}:
            return "security"
        if normalized in {"sales", "finance", "legal", "security", "executive_sponsor"}:
            return normalized
        return "proposal_manager"

    def _approval_reason(self, owner: str) -> str:
        return {
            "executive_sponsor": "Approve final go/no-go outcome and accepted exceptions.",
            "proposal_manager": "Confirm package completeness, owner status, and submission operations.",
            "sales_leadership": "Approve customer-facing submission posture.",
            "sales": "Approve account strategy and buyer-facing caveats.",
            "finance": "Approve pricing, discount, payment, and packaging assumptions.",
            "legal": "Approve contract exceptions, redlines, privacy, and liability posture.",
            "security": "Approve security evidence, citations, and red-team remediation.",
        }.get(owner, "Approve assigned submission exception.")

    def _owner_for_text(self, text: str) -> str:
        lowered = text.lower()
        if any(term in lowered for term in ["contract", "legal", "dpa", "gdpr", "liability", "indemnity"]):
            return "legal"
        if any(term in lowered for term in ["pricing", "price", "discount", "commercial", "payment"]):
            return "finance"
        if any(term in lowered for term in ["security", "sso", "encryption", "red-team", "audit"]):
            return "security"
        if any(term in lowered for term in ["feature", "roadmap", "workflow"]):
            return "product"
        return "proposal_manager"

    def _owner_slug(self, owner: str) -> str:
        normalized = owner.lower().replace(" ", "_")
        aliases = {
            "security_architect": "security",
            "compliance_lead": "legal",
            "commercial_owner": "sales",
            "implementation_lead": "solutions",
            "solutions_engineer": "solutions",
            "sales_leadership": "sales_leadership",
            "executive": "executive_sponsor",
        }
        return aliases.get(normalized, normalized or "proposal_manager")

    def _dedupe_issues(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._dedupe_dicts(items, ("source", "owner", "title"))

    def _dedupe_exceptions(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._dedupe_dicts(items, ("source", "owner", "title"))

    def _dedupe_actions(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._dedupe_dicts(items, ("owner", "action", "source"))

    def _dedupe_dicts(self, items: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
        seen = set()
        deduped = []
        for item in items:
            key = tuple(str(item.get(field, "")) for field in keys)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _append_dict_list(self, lines: list[str], items: list[dict[str, Any]], fields: list[str]) -> None:
        if not items:
            lines.append("- None")
            return
        for item in items:
            parts = [f"{field}={self._md_cell(item.get(field))}" for field in fields]
            lines.append(f"- {'; '.join(parts)}")

    def _md_cell(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
