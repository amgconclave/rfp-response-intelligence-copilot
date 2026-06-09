import json
import re
from collections import Counter
from typing import Any

from app.core.config import Settings
from app.models.api import (
    AnalyzeResponse,
    CustomerFitResponse,
    DealReadinessScorecardResponse,
    EvaluationMetrics,
    ExecutiveRiskReportResponse,
)
from app.models.domain import RequirementMatrixRow, ReviewFinding, StakeholderTask


class DealReadinessService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_scorecard(
        self,
        trace_id: str,
        analysis: AnalyzeResponse | None = None,
        requirement_matrix: list[RequirementMatrixRow] | None = None,
        review_findings: list[ReviewFinding] | None = None,
        customer_fit: CustomerFitResponse | None = None,
        action_plan: list[StakeholderTask] | None = None,
        eval_metrics: EvaluationMetrics | None = None,
    ) -> DealReadinessScorecardResponse:
        matrix = requirement_matrix or []
        findings = review_findings or []
        tasks = action_plan or []
        evidence_coverage = self._evidence_coverage(matrix)
        review_risk_count = self._review_risk_count(findings)
        missing_evidence = self._missing_evidence(analysis, matrix, findings)
        owner_bottlenecks = self._owner_bottlenecks(matrix, tasks)
        blockers = self._blockers(matrix, findings, missing_evidence, customer_fit, eval_metrics)
        score = self._score(
            matrix,
            missing_evidence,
            evidence_coverage,
            review_risk_count,
            customer_fit,
            owner_bottlenecks,
            eval_metrics,
        )
        return DealReadinessScorecardResponse(
            readiness_score=score,
            readiness_level=self._readiness_level(score, blockers),
            blockers=blockers,
            evidence_coverage=evidence_coverage,
            review_risk_count=review_risk_count,
            customer_fit_score=customer_fit.fit_score if customer_fit else None,
            owner_bottlenecks=owner_bottlenecks,
            recommended_next_actions=self._next_actions(
                blockers,
                matrix,
                findings,
                missing_evidence,
                customer_fit,
                tasks,
                owner_bottlenecks,
            ),
            trace_id=trace_id,
        )

    def export_executive_report(
        self,
        trace_id: str,
        scorecard: DealReadinessScorecardResponse,
        analysis: AnalyzeResponse | None = None,
        requirement_matrix: list[RequirementMatrixRow] | None = None,
        review_findings: list[ReviewFinding] | None = None,
        customer_fit: CustomerFitResponse | None = None,
        action_plan: list[StakeholderTask] | None = None,
        eval_metrics: EvaluationMetrics | None = None,
        red_team_summary: dict[str, Any] | None = None,
        write_artifact: bool = True,
    ) -> ExecutiveRiskReportResponse:
        matrix = requirement_matrix or []
        findings = review_findings or []
        tasks = action_plan or []
        missing_evidence = self._missing_evidence(analysis, matrix, findings)
        report = {
            "trace_id": trace_id,
            "readiness": scorecard.model_dump(mode="json"),
            "top_blockers": scorecard.blockers[:5],
            "evidence_coverage": scorecard.evidence_coverage,
            "missing_evidence_count": len(missing_evidence),
            "owner_bottlenecks": scorecard.owner_bottlenecks,
            "customer_fit": self._customer_fit_payload(customer_fit),
            "red_team_summary": self._red_team_summary(red_team_summary, findings, eval_metrics),
            "submission_recommendation": self._submission_recommendation(scorecard),
            "review_risk_summary": self._review_risk_summary(findings),
            "action_plan_summary": self._action_plan_summary(tasks),
        }
        markdown = self._render_markdown(report)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            report_dir = self.settings.storage_dir / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = report_dir / f"executive_risk_report_{safe_trace_id}.md"
            json_path = report_dir / f"executive_risk_report_{safe_trace_id}.json"
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
        return ExecutiveRiskReportResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            report=report,
            trace_id=trace_id,
        )

    def _score(
        self,
        matrix: list[RequirementMatrixRow],
        missing_evidence: list[str],
        evidence_coverage: float,
        review_risk_count: int,
        customer_fit: CustomerFitResponse | None,
        owner_bottlenecks: list[dict[str, Any]],
        eval_metrics: EvaluationMetrics | None,
    ) -> int:
        blocked_rows = sum(1 for row in matrix if row.status == "blocked")
        high_risk_rows = sum(1 for row in matrix if row.risk_level == "high")
        score = 100.0
        score -= min(30, blocked_rows * 8)
        score -= min(15, high_risk_rows * 3)
        score -= min(20, len(missing_evidence) * 4)
        score -= min(25, int(round((1 - evidence_coverage) * 25)))
        score -= min(25, review_risk_count * 7)
        if customer_fit and customer_fit.fit_score < 70:
            score -= min(16, int(round((70 - customer_fit.fit_score) * 0.4)))
        if owner_bottlenecks and owner_bottlenecks[0]["open_items"] >= 4:
            score -= 6
        if eval_metrics:
            if not eval_metrics.passed:
                score -= 10
            if eval_metrics.citation_coverage < 0.75:
                score -= int(round((0.75 - eval_metrics.citation_coverage) * 20))
        return max(0, min(100, int(round(score))))

    def _readiness_level(self, score: int, blockers: list[str]) -> str:
        if score >= 85 and not blockers:
            return "ready"
        if score >= 70:
            return "mostly_ready"
        if score >= 50:
            return "at_risk"
        return "not_ready"

    def _evidence_coverage(self, matrix: list[RequirementMatrixRow]) -> float:
        if not matrix:
            return 0.0
        covered = sum(1 for row in matrix if row.evidence_refs and not row.missing_evidence)
        return round(covered / len(matrix), 2)

    def _review_risk_count(self, findings: list[ReviewFinding]) -> int:
        return sum(
            1
            for finding in findings
            if finding.severity in {"critical", "high"}
            or finding.category in {"unsupported_claim", "missing_evidence", "high_risk_requirement"}
        )

    def _missing_evidence(
        self,
        analysis: AnalyzeResponse | None,
        matrix: list[RequirementMatrixRow],
        findings: list[ReviewFinding],
    ) -> list[str]:
        items = {
            item
            for row in matrix
            for item in row.missing_evidence
        }
        if analysis:
            items.update(analysis.missing_information)
        items.update(
            finding.message
            for finding in findings
            if finding.category == "missing_evidence"
        )
        return sorted(item for item in items if item)

    def _blockers(
        self,
        matrix: list[RequirementMatrixRow],
        findings: list[ReviewFinding],
        missing_evidence: list[str],
        customer_fit: CustomerFitResponse | None,
        eval_metrics: EvaluationMetrics | None,
    ) -> list[str]:
        blockers = []
        blockers.extend(
            f"{row.requirement_id}: {row.requirement_text}"
            for row in matrix
            if row.status == "blocked"
        )
        blockers.extend(
            f"{finding.severity} {finding.category}: {finding.message}"
            for finding in findings
            if finding.severity in {"critical", "high"}
        )
        if missing_evidence:
            blockers.append(f"{len(missing_evidence)} missing evidence items remain open.")
        if customer_fit and customer_fit.fit_score < 55:
            blockers.append(f"Customer fit score is low at {customer_fit.fit_score}.")
        if eval_metrics and not eval_metrics.passed:
            blockers.append("Standard evaluation did not pass current quality gates.")
        return list(dict.fromkeys(blockers))[:8]

    def _owner_bottlenecks(
        self,
        matrix: list[RequirementMatrixRow],
        tasks: list[StakeholderTask],
    ) -> list[dict[str, Any]]:
        owner_rows: dict[str, dict[str, int]] = {}
        for row in matrix:
            owner = row.owner_role.lower().replace(" ", "_")
            counts = owner_rows.setdefault(
                owner,
                {"open_items": 0, "blocked_items": 0, "high_priority_items": 0, "risk_items": 0},
            )
            if row.status != "evidence_found":
                counts["open_items"] += 1
            if row.status == "blocked":
                counts["blocked_items"] += 1
            if row.priority == "high":
                counts["high_priority_items"] += 1
            if row.risk_level == "high":
                counts["risk_items"] += 1
        for task in tasks:
            owner = task.owner_role
            counts = owner_rows.setdefault(
                owner,
                {"open_items": 0, "blocked_items": 0, "high_priority_items": 0, "risk_items": 0},
            )
            if task.status in {"blocked", "needs_review"}:
                counts["open_items"] += 1
            if task.status == "blocked":
                counts["blocked_items"] += 1
            if task.priority == "high":
                counts["high_priority_items"] += 1
            if task.risk_level == "high":
                counts["risk_items"] += 1
        bottlenecks = [
            {"owner_role": owner, **counts}
            for owner, counts in owner_rows.items()
            if counts["open_items"] or counts["blocked_items"] or counts["risk_items"]
        ]
        return sorted(
            bottlenecks,
            key=lambda item: (
                -item["blocked_items"],
                -item["open_items"],
                -item["risk_items"],
                item["owner_role"],
            ),
        )[:6]

    def _next_actions(
        self,
        blockers: list[str],
        matrix: list[RequirementMatrixRow],
        findings: list[ReviewFinding],
        missing_evidence: list[str],
        customer_fit: CustomerFitResponse | None,
        tasks: list[StakeholderTask],
        owner_bottlenecks: list[dict[str, Any]],
    ) -> list[str]:
        actions = []
        blocked_tasks = [task for task in tasks if task.status == "blocked"]
        actions.extend(f"{task.owner_role}: {task.title}" for task in blocked_tasks[:3])
        if missing_evidence:
            actions.append("Attach approved evidence or document exceptions for all missing-evidence items.")
        high_rows = [row for row in matrix if row.status == "blocked" or row.risk_level == "high"]
        if high_rows:
            actions.append("Review high-risk requirements with legal, security, and sales leadership.")
        if findings:
            actions.append("Resolve review-board findings before sending an executive-ready package.")
        if customer_fit and customer_fit.requirements_needing_review:
            actions.append("Validate customer-fit risk tolerance and positioning with the account team.")
        if owner_bottlenecks:
            owner = owner_bottlenecks[0]["owner_role"]
            actions.append(f"Clear the largest owner bottleneck first: {owner}.")
        if not actions and not blockers:
            actions.append("Proceed to final submission review and executive approval.")
        return list(dict.fromkeys(actions))[:6]

    def _customer_fit_payload(self, customer_fit: CustomerFitResponse | None) -> dict[str, Any] | None:
        if not customer_fit:
            return None
        profile = customer_fit.customer_profile
        return {
            "customer": profile.name,
            "industry": profile.industry,
            "region": profile.region,
            "risk_tolerance": profile.risk_tolerance,
            "fit_score": customer_fit.fit_score,
            "profile_risks": customer_fit.profile_risks,
            "recommended_positioning": customer_fit.recommended_positioning,
            "requirements_needing_review": [
                requirement.model_dump(mode="json")
                for requirement in customer_fit.requirements_needing_review
            ],
        }

    def _red_team_summary(
        self,
        red_team_summary: dict[str, Any] | None,
        findings: list[ReviewFinding],
        eval_metrics: EvaluationMetrics | None,
    ) -> dict[str, Any]:
        if red_team_summary:
            return red_team_summary
        risky_categories = Counter(finding.category for finding in findings)
        return {
            "source": "review_findings_and_eval_metrics",
            "high_risk_findings": self._review_risk_count(findings),
            "risk_categories": dict(sorted(risky_categories.items())),
            "standard_eval_passed": eval_metrics.passed if eval_metrics else None,
        }

    def _review_risk_summary(self, findings: list[ReviewFinding]) -> dict[str, Any]:
        return {
            "finding_count": len(findings),
            "severity_counts": dict(sorted(Counter(finding.severity for finding in findings).items())),
            "category_counts": dict(sorted(Counter(finding.category for finding in findings).items())),
        }

    def _action_plan_summary(self, tasks: list[StakeholderTask]) -> dict[str, Any]:
        return {
            "task_count": len(tasks),
            "blocked_tasks": sum(1 for task in tasks if task.status == "blocked"),
            "needs_review_tasks": sum(1 for task in tasks if task.status == "needs_review"),
            "owners": dict(sorted(Counter(task.owner_role for task in tasks).items())),
        }

    def _submission_recommendation(self, scorecard: DealReadinessScorecardResponse) -> str:
        if scorecard.readiness_level == "ready":
            return "Submit after final executive sign-off."
        if scorecard.readiness_level == "mostly_ready":
            return "Conditionally submit after listed blockers are closed or explicitly approved as exceptions."
        if scorecard.readiness_level == "at_risk":
            return "Hold submission until top blockers and owner bottlenecks are resolved."
        return "Do not submit; evidence, review, or customer-fit risk is too high."

    def _render_markdown(self, report: dict[str, Any]) -> str:
        readiness = report["readiness"]
        lines = [
            "# Executive Risk Report",
            "",
            "## Submission Recommendation",
            "",
            report["submission_recommendation"],
            "",
            "## Deal Readiness Scorecard",
            "",
            f"- Readiness score: {readiness['readiness_score']}",
            f"- Readiness level: {readiness['readiness_level']}",
            f"- Evidence coverage: {report['evidence_coverage']}",
            f"- Missing evidence count: {report['missing_evidence_count']}",
            f"- Review risk count: {readiness['review_risk_count']}",
            f"- Customer fit score: {readiness['customer_fit_score']}",
            "",
            "## Top Blockers",
            "",
        ]
        self._append_list(lines, report["top_blockers"])
        lines.extend(["", "## Owner Bottlenecks", ""])
        if report["owner_bottlenecks"]:
            lines.extend(
                "- {owner_role}: open={open_items}, blocked={blocked_items}, "
                "high_priority={high_priority_items}, risk={risk_items}".format(**item)
                for item in report["owner_bottlenecks"]
            )
        else:
            lines.append("- None")
        lines.extend(["", "## Customer Fit", ""])
        fit = report["customer_fit"]
        if fit:
            lines.extend(
                [
                    f"- Customer: {fit['customer']}",
                    f"- Industry: {fit['industry']}",
                    f"- Region: {fit['region']}",
                    f"- Risk tolerance: {fit['risk_tolerance']}",
                    f"- Fit score: {fit['fit_score']}",
                    "",
                    "Profile risks:",
                ]
            )
            self._append_list(lines, fit["profile_risks"])
            lines.extend(["", "Recommended positioning:"])
            self._append_list(lines, fit["recommended_positioning"])
        else:
            lines.append("- No customer fit supplied.")
        lines.extend(["", "## Red-Team Summary", ""])
        for key, value in report["red_team_summary"].items():
            lines.append(f"- {self._md_cell(key)}: {self._md_cell(value)}")
        lines.extend(["", "## Recommended Next Actions", ""])
        self._append_list(lines, readiness["recommended_next_actions"])
        return "\n".join(lines).strip() + "\n"

    def _append_list(self, lines: list[str], items: list[Any]) -> None:
        if not items:
            lines.append("- None")
            return
        lines.extend(f"- {item}" for item in items)

    def _md_cell(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
