import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    AnalyzeResponse,
    CustomerFitResponse,
    DealReadinessScorecardResponse,
    EvaluationMetrics,
    ExecutiveRiskReportResponse,
    ProposalReadinessScorePackResponse,
)
from app.models.domain import DraftResponse, RequirementMatrixRow, ReviewFinding, StakeholderTask


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

    def create_score_pack(
        self,
        trace_id: str,
        analysis: AnalyzeResponse | None = None,
        requirement_matrix: list[RequirementMatrixRow] | None = None,
        review_findings: list[ReviewFinding] | None = None,
        customer_fit: CustomerFitResponse | None = None,
        action_plan: list[StakeholderTask] | None = None,
        eval_metrics: EvaluationMetrics | None = None,
        draft_response: DraftResponse | None = None,
        red_team_summary: dict[str, Any] | None = None,
        readiness_scorecard: DealReadinessScorecardResponse | None = None,
        executive_report: ExecutiveRiskReportResponse | None = None,
        write_artifact: bool = True,
    ) -> ProposalReadinessScorePackResponse:
        matrix = requirement_matrix or []
        findings = review_findings or []
        tasks = action_plan or []
        scorecard = readiness_scorecard or self.create_scorecard(
            trace_id=f"{trace_id}-scorecard",
            analysis=analysis,
            requirement_matrix=matrix,
            review_findings=findings,
            customer_fit=customer_fit,
            action_plan=tasks,
            eval_metrics=eval_metrics,
        )
        report = executive_report or self.export_executive_report(
            trace_id=f"{trace_id}-executive-report",
            scorecard=scorecard,
            analysis=analysis,
            requirement_matrix=matrix,
            review_findings=findings,
            customer_fit=customer_fit,
            action_plan=tasks,
            eval_metrics=eval_metrics,
            red_team_summary=red_team_summary,
            write_artifact=False,
        )
        section_completeness = self._section_completeness(analysis, matrix, draft_response)
        evidence_coverage = self._evidence_coverage_details(matrix)
        compliance_risk = self._compliance_risk_breakdown(analysis, matrix, findings)
        reviewer_bottlenecks = self._reviewer_bottleneck_details(matrix, tasks, findings)
        status = self._score_pack_status(scorecard, section_completeness, compliance_risk, reviewer_bottlenecks)
        generated_at = datetime.now(UTC).isoformat()
        local_commands = self._score_pack_local_commands()
        limitations = self._score_pack_limitations()
        pack = {
            "trace_id": trace_id,
            "title": "Proposal Readiness Score Pack",
            "generated_at": generated_at,
            "status": status,
            "readiness_scorecard": scorecard.model_dump(mode="json"),
            "executive_report_summary": {
                "submission_recommendation": report.report["submission_recommendation"],
                "top_blockers": report.report["top_blockers"],
                "review_risk_summary": report.report["review_risk_summary"],
                "action_plan_summary": report.report["action_plan_summary"],
            },
            "section_completeness": section_completeness,
            "evidence_coverage": evidence_coverage,
            "compliance_risk": compliance_risk,
            "reviewer_bottlenecks": reviewer_bottlenecks,
            "executive_readiness_artifacts": self._executive_readiness_artifacts(
                scorecard,
                report,
                section_completeness,
                evidence_coverage,
                compliance_risk,
                reviewer_bottlenecks,
            ),
            "endpoint_references": self._score_pack_endpoint_references(),
            "local_proof_commands": local_commands,
            "limitations": limitations,
            "artifact_paths": {},
        }
        markdown = self._render_score_pack_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "readiness_packs"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"proposal_readiness_score_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"proposal_readiness_score_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"] = {
                "proposal_readiness_score_pack_markdown": artifact_path,
                "proposal_readiness_score_pack_json": json_artifact_path,
                "executive_risk_report_markdown": report.artifact_path,
                "executive_risk_report_json": report.json_artifact_path,
            }
            markdown = self._render_score_pack_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return ProposalReadinessScorePackResponse(
            title="Proposal Readiness Score Pack",
            status=status,
            readiness_score=scorecard.readiness_score,
            readiness_level=scorecard.readiness_level,
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            readiness_scorecard=scorecard,
            local_proof_commands=local_commands,
            limitations=limitations,
            generated_at=generated_at,
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

    def _section_completeness(
        self,
        analysis: AnalyzeResponse | None,
        matrix: list[RequirementMatrixRow],
        draft_response: DraftResponse | None,
    ) -> dict[str, Any]:
        categories = {self._normalized_category(row.category) for row in matrix}
        if analysis:
            categories.update(self._normalized_category(requirement.category) for requirement in analysis.requirements)
        categories.discard("")
        categories.add("executive_summary")
        rows_by_category: dict[str, list[RequirementMatrixRow]] = {
            category: [row for row in matrix if self._normalized_category(row.category) == category]
            for category in sorted(categories)
        }
        draft_sections = list(draft_response.sections) if draft_response else []
        section_rows = []
        for category, rows in rows_by_category.items():
            matching_sections = self._matching_draft_sections(category, rows, draft_sections)
            total = len(rows)
            evidence_ready = sum(1 for row in rows if row.evidence_refs and not row.missing_evidence)
            missing_count = sum(len(row.missing_evidence) for row in rows)
            blocked_count = sum(1 for row in rows if row.status == "blocked")
            high_risk_count = sum(1 for row in rows if row.risk_level == "high")
            if total:
                evidence_ratio = evidence_ready / total
                non_missing_ratio = sum(1 for row in rows if not row.missing_evidence) / total
            else:
                evidence_ratio = 1.0 if matching_sections else 0.0
                non_missing_ratio = 1.0 if matching_sections else 0.0
            draft_ratio = 1.0 if matching_sections else 0.0
            score = int(round((evidence_ratio * 0.55 + non_missing_ratio * 0.3 + draft_ratio * 0.15) * 100))
            status = "complete"
            if blocked_count or missing_count:
                status = "blocked" if blocked_count else "needs_evidence"
            elif score < 85:
                status = "needs_review"
            section_rows.append(
                {
                    "section": category,
                    "status": status,
                    "completeness_score": score,
                    "requirement_count": total,
                    "evidence_ready_count": evidence_ready,
                    "missing_evidence_count": missing_count,
                    "blocked_requirement_count": blocked_count,
                    "high_risk_requirement_count": high_risk_count,
                    "draft_section_titles": [section.title for section in matching_sections],
                    "owner_roles": sorted({row.owner_role for row in rows}),
                    "requirement_ids": [row.requirement_id for row in rows],
                }
            )
        average_score = int(round(sum(row["completeness_score"] for row in section_rows) / len(section_rows)))
        blocked_sections = [row["section"] for row in section_rows if row["status"] == "blocked"]
        needs_review_sections = [
            row["section"]
            for row in section_rows
            if row["status"] in {"needs_review", "needs_evidence"}
        ]
        return {
            "average_score": average_score,
            "status": "pass" if average_score >= 85 and not blocked_sections else "needs_review",
            "section_count": len(section_rows),
            "blocked_sections": blocked_sections,
            "needs_review_sections": needs_review_sections,
            "sections": section_rows,
        }

    def _evidence_coverage_details(self, matrix: list[RequirementMatrixRow]) -> dict[str, Any]:
        rows_by_category: dict[str, list[RequirementMatrixRow]] = {}
        for row in matrix:
            rows_by_category.setdefault(self._normalized_category(row.category), []).append(row)
        by_category = []
        uncovered_requirements = []
        citation_refs = sorted({ref for row in matrix for ref in row.evidence_refs})
        for category, rows in sorted(rows_by_category.items()):
            total = len(rows)
            covered = sum(1 for row in rows if row.evidence_refs and not row.missing_evidence)
            missing = sum(len(row.missing_evidence) for row in rows)
            by_category.append(
                {
                    "category": category,
                    "requirement_count": total,
                    "covered_count": covered,
                    "coverage": round(covered / total, 2) if total else 0.0,
                    "missing_evidence_count": missing,
                    "high_risk_count": sum(1 for row in rows if row.risk_level == "high"),
                }
            )
            uncovered_requirements.extend(
                {
                    "requirement_id": row.requirement_id,
                    "category": category,
                    "owner_role": row.owner_role,
                    "status": row.status,
                    "missing_evidence": row.missing_evidence,
                }
                for row in rows
                if not row.evidence_refs or row.missing_evidence
            )
        coverage = self._evidence_coverage(matrix)
        return {
            "overall_coverage": coverage,
            "status": "pass" if coverage >= 0.9 and not uncovered_requirements else "needs_review",
            "citation_ref_count": len(citation_refs),
            "citation_refs": citation_refs,
            "uncovered_requirement_count": len(uncovered_requirements),
            "uncovered_requirements": uncovered_requirements[:12],
            "by_category": by_category,
        }

    def _compliance_risk_breakdown(
        self,
        analysis: AnalyzeResponse | None,
        matrix: list[RequirementMatrixRow],
        findings: list[ReviewFinding],
    ) -> dict[str, Any]:
        risk_terms = {
            "compliance",
            "security",
            "privacy",
            "legal",
            "data_processing",
            "data_residency",
            "audit",
            "soc",
            "hipaa",
            "fedramp",
            "gdpr",
            "dpa",
        }
        compliance_rows = [
            row
            for row in matrix
            if self._row_has_terms(row, risk_terms)
        ]
        compliance_findings = [
            finding
            for finding in findings
            if self._text_has_terms(f"{finding.category} {finding.message}", risk_terms)
        ]
        compliance_asks = analysis.compliance_asks if analysis else []
        blocked = sum(1 for row in compliance_rows if row.status == "blocked")
        high_risk = sum(1 for row in compliance_rows if row.risk_level == "high")
        missing = sum(len(row.missing_evidence) for row in compliance_rows)
        critical_findings = sum(1 for finding in compliance_findings if finding.severity == "critical")
        high_findings = sum(1 for finding in compliance_findings if finding.severity == "high")
        risk_score = min(
            100,
            blocked * 25
            + high_risk * 18
            + missing * 10
            + critical_findings * 25
            + high_findings * 15,
        )
        issues = [
            {
                "source": "requirement_matrix",
                "requirement_id": row.requirement_id,
                "category": self._normalized_category(row.category),
                "severity": "high" if row.status == "blocked" or row.risk_level == "high" else "medium",
                "owner_role": row.owner_role,
                "message": row.requirement_text,
                "missing_evidence": row.missing_evidence,
            }
            for row in compliance_rows
            if row.status == "blocked" or row.risk_level == "high" or row.missing_evidence
        ]
        issues.extend(
            {
                "source": "review_finding",
                "requirement_id": finding.related_requirement_id,
                "category": finding.category,
                "severity": finding.severity,
                "owner_role": self._owner_for_requirement(finding.related_requirement_id, matrix),
                "message": finding.message,
                "missing_evidence": [],
            }
            for finding in compliance_findings
        )
        return {
            "risk_score": risk_score,
            "risk_level": self._risk_level(risk_score),
            "compliance_ask_count": len(compliance_asks),
            "regulated_requirement_count": len(compliance_rows),
            "blocked_requirement_count": blocked,
            "high_risk_requirement_count": high_risk,
            "missing_evidence_count": missing,
            "review_finding_count": len(compliance_findings),
            "issues": issues[:12],
            "required_reviewer_roles": sorted(
                {
                    self._owner_for_requirement(item.get("requirement_id"), matrix)
                    for item in issues
                    if item.get("requirement_id")
                }
                | {"legal", "security"}
            ),
            "recommended_action": self._compliance_action(risk_score, missing, compliance_findings),
        }

    def _reviewer_bottleneck_details(
        self,
        matrix: list[RequirementMatrixRow],
        tasks: list[StakeholderTask],
        findings: list[ReviewFinding],
    ) -> list[dict[str, Any]]:
        base = self._owner_bottlenecks(matrix, tasks)
        rows_by_owner: dict[str, list[RequirementMatrixRow]] = {}
        for row in matrix:
            rows_by_owner.setdefault(row.owner_role.lower().replace(" ", "_"), []).append(row)
        tasks_by_owner: dict[str, list[StakeholderTask]] = {}
        for task in tasks:
            tasks_by_owner.setdefault(task.owner_role, []).append(task)
        details = []
        for item in base:
            owner = item["owner_role"]
            owner_rows = rows_by_owner.get(owner, [])
            owner_tasks = tasks_by_owner.get(owner, [])
            related_ids = {row.requirement_id for row in owner_rows}
            owner_findings = [
                finding
                for finding in findings
                if finding.related_requirement_id in related_ids or self._text_has_terms(finding.message, {owner})
            ]
            blocked_tasks = [task for task in owner_tasks if task.status == "blocked"]
            needs_review_tasks = [task for task in owner_tasks if task.status == "needs_review"]
            escalation_required = bool(
                item["blocked_items"]
                or blocked_tasks
                or any(f.severity == "critical" for f in owner_findings)
            )
            details.append(
                {
                    **item,
                    "task_count": len(owner_tasks),
                    "blocked_task_count": len(blocked_tasks),
                    "needs_review_task_count": len(needs_review_tasks),
                    "review_finding_count": len(owner_findings),
                    "related_requirement_ids": sorted(related_ids)[:8],
                    "escalation_required": escalation_required,
                    "recommended_action": self._reviewer_action(owner, escalation_required, item, blocked_tasks),
                }
            )
        return details

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

    def _score_pack_status(
        self,
        scorecard: DealReadinessScorecardResponse,
        section_completeness: dict[str, Any],
        compliance_risk: dict[str, Any],
        reviewer_bottlenecks: list[dict[str, Any]],
    ) -> str:
        if scorecard.readiness_level == "ready" and section_completeness["status"] == "pass":
            return "ready_for_executive_review"
        if compliance_risk["risk_level"] in {"critical", "high"}:
            return "blocked_by_compliance_risk"
        if any(item["escalation_required"] for item in reviewer_bottlenecks):
            return "blocked_by_reviewer_bottleneck"
        if scorecard.readiness_level in {"mostly_ready", "at_risk"}:
            return "needs_owner_followup"
        return "not_ready"

    def _executive_readiness_artifacts(
        self,
        scorecard: DealReadinessScorecardResponse,
        report: ExecutiveRiskReportResponse,
        section_completeness: dict[str, Any],
        evidence_coverage: dict[str, Any],
        compliance_risk: dict[str, Any],
        reviewer_bottlenecks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "executive_summary": {
                "readiness_score": scorecard.readiness_score,
                "readiness_level": scorecard.readiness_level,
                "section_completeness_score": section_completeness["average_score"],
                "evidence_coverage": evidence_coverage["overall_coverage"],
                "compliance_risk_level": compliance_risk["risk_level"],
                "reviewer_bottleneck_count": len(reviewer_bottlenecks),
                "submission_recommendation": self._submission_recommendation(scorecard),
            },
            "artifact_links": {
                "executive_risk_report_markdown": report.artifact_path,
                "executive_risk_report_json": report.json_artifact_path,
            },
            "boardroom_questions_answered": [
                "Which proposal sections are incomplete or missing evidence?",
                "Which compliance/security risks can block submission?",
                "Which reviewer owners are creating the longest bottleneck?",
                "What proof commands can a local reviewer run without external services?",
            ],
            "approval_gate": (
                "Proceed to executive sign-off."
                if scorecard.readiness_level == "ready"
                else "Resolve blockers or document explicit executive exceptions before submission."
            ),
        }

    def _score_pack_endpoint_references(self) -> list[dict[str, str]]:
        return [
            {
                "method": "POST",
                "path": "/rfp/proposal-readiness-score-pack",
                "purpose": "Writes the executive Proposal Readiness Score Pack.",
            },
            {
                "method": "POST",
                "path": "/rfp/readiness-scorecard",
                "purpose": "Returns the base deterministic readiness scorecard.",
            },
            {
                "method": "POST",
                "path": "/rfp/executive-risk-report",
                "purpose": "Writes the leadership risk report used by the pack.",
            },
        ]

    def _score_pack_local_commands(self) -> list[str]:
        return [
            "python -m pytest -q",
            "python -m ruff check .",
            "python scripts\\dashboard_smoke.py",
            "python -m app.demo",
            (
                'rg "proposal-readiness-score-pack|Proposal Readiness Score Pack|readiness_packs" '
                "app dashboard docs README.md tests"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\readiness_packs -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _score_pack_limitations(self) -> list[str]:
        return [
            "Scores are deterministic local decision-support signals, not legal or procurement approval.",
            "Completeness depends on provided draft sections, matrix rows, findings, and local sample evidence.",
            "External provider calls are optional; the pack is designed to run in mock/local mode by default.",
        ]

    def _normalized_category(self, value: str | None) -> str:
        normalized = (value or "general").lower().replace("-", "_").replace(" ", "_")
        if normalized in {"privacy", "data_privacy", "dpa"}:
            return "privacy"
        if normalized in {"commercial", "price", "pricing"}:
            return "pricing"
        if normalized in {"implementation", "onboarding", "deployment"}:
            return "implementation"
        if normalized in {"legal", "contract", "terms"}:
            return "legal"
        return normalized or "general"

    def _matching_draft_sections(
        self,
        category: str,
        rows: list[RequirementMatrixRow],
        draft_sections: list[Any],
    ) -> list[Any]:
        aliases = {
            "executive_summary": {"executive", "summary", "overview"},
            "security": {"security", "sso", "encryption", "incident"},
            "compliance": {"compliance", "audit", "soc", "fedramp", "hipaa", "gdpr"},
            "privacy": {"privacy", "data", "dpa", "retention"},
            "pricing": {"pricing", "commercial", "discount", "cost"},
            "implementation": {"implementation", "onboarding", "deployment", "timeline"},
            "support": {"support", "sla", "success"},
            "technical": {"technical", "architecture", "integration", "api"},
        }
        category_terms = aliases.get(category, {category})
        row_ids = {row.requirement_id for row in rows}
        matches = []
        for section in draft_sections:
            text = f"{section.title} {section.body}".lower()
            section_ids = set(section.requirement_ids)
            if row_ids and row_ids & section_ids:
                matches.append(section)
            elif any(term in text for term in category_terms):
                matches.append(section)
        return matches

    def _row_has_terms(self, row: RequirementMatrixRow, terms: set[str]) -> bool:
        return self._text_has_terms(
            f"{row.category} {row.requirement_text} {' '.join(row.missing_evidence)}",
            terms,
        )

    def _text_has_terms(self, text: str, terms: set[str]) -> bool:
        normalized = text.lower().replace("-", "_").replace(" ", "_")
        return any(term in normalized for term in terms)

    def _owner_for_requirement(self, requirement_id: str | None, matrix: list[RequirementMatrixRow]) -> str:
        for row in matrix:
            if row.requirement_id == requirement_id:
                return row.owner_role.lower().replace(" ", "_")
        return "proposal_manager"

    def _risk_level(self, score: int) -> str:
        if score >= 75:
            return "critical"
        if score >= 50:
            return "high"
        if score >= 25:
            return "medium"
        return "low"

    def _compliance_action(
        self,
        risk_score: int,
        missing_evidence_count: int,
        findings: list[ReviewFinding],
    ) -> str:
        if risk_score >= 75:
            return "Block submission until legal/security approve exceptions and required evidence is attached."
        if missing_evidence_count or findings:
            return "Route compliance gaps to legal and security owners before executive review."
        return "Keep compliance reviewer in final sign-off and preserve citation evidence."

    def _reviewer_action(
        self,
        owner: str,
        escalation_required: bool,
        item: dict[str, Any],
        blocked_tasks: list[StakeholderTask],
    ) -> str:
        if escalation_required:
            return f"Escalate {owner} blockers in the next readiness standup and require dated closure notes."
        if blocked_tasks:
            return f"Ask {owner} to close blocked tasks before package export."
        if item["open_items"]:
            return f"Pull {owner} open items into reviewer queue with evidence acceptance criteria."
        return f"Keep {owner} on final approval notification."

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

    def _render_score_pack_markdown(self, pack: dict[str, Any]) -> str:
        summary = pack["executive_readiness_artifacts"]["executive_summary"]
        lines = [
            "# Proposal Readiness Score Pack",
            "",
            f"- Generated at: {pack['generated_at']}",
            f"- Status: {pack['status']}",
            f"- Readiness score: {summary['readiness_score']}",
            f"- Readiness level: {summary['readiness_level']}",
            f"- Section completeness score: {summary['section_completeness_score']}",
            f"- Evidence coverage: {summary['evidence_coverage']}",
            f"- Compliance risk level: {summary['compliance_risk_level']}",
            "",
            "## Executive Recommendation",
            "",
            summary["submission_recommendation"],
            "",
            "## Section Completeness",
            "",
            "| Section | Status | Score | Requirements | Evidence Ready | Missing Evidence | Draft Sections |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
        for row in pack["section_completeness"]["sections"]:
            lines.append(
                "| {section} | {status} | {completeness_score} | {requirement_count} | "
                "{evidence_ready_count} | {missing_evidence_count} | {drafts} |".format(
                    **row,
                    drafts=self._md_cell(", ".join(row["draft_section_titles"]) or "None"),
                )
            )
        lines.extend(
            [
                "",
                "## Evidence Coverage",
                "",
                f"- Overall coverage: {pack['evidence_coverage']['overall_coverage']}",
                f"- Citation references: {pack['evidence_coverage']['citation_ref_count']}",
                f"- Uncovered requirements: {pack['evidence_coverage']['uncovered_requirement_count']}",
                "",
                "## Compliance Risk",
                "",
                f"- Risk score: {pack['compliance_risk']['risk_score']}",
                f"- Risk level: {pack['compliance_risk']['risk_level']}",
                f"- Recommended action: {pack['compliance_risk']['recommended_action']}",
                "",
                "## Reviewer Bottlenecks",
                "",
                "| Owner | Open | Blocked | Tasks | Findings | Escalate | Action |",
                "| --- | ---: | ---: | ---: | ---: | --- | --- |",
            ]
        )
        if pack["reviewer_bottlenecks"]:
            for item in pack["reviewer_bottlenecks"]:
                lines.append(
                    "| {owner_role} | {open_items} | {blocked_items} | {task_count} | "
                    "{review_finding_count} | {escalation_required} | {action} |".format(
                        **item,
                        action=self._md_cell(item["recommended_action"]),
                    )
                )
        else:
            lines.append("| None | 0 | 0 | 0 | 0 | False | No bottleneck detected. |")
        lines.extend(["", "## Executive Readiness Artifacts", ""])
        for label, path in pack["artifact_paths"].items():
            lines.append(f"- {label}: {path}")
        lines.extend(["", "## Endpoint References", ""])
        lines.extend(
            f"- `{item['method']} {item['path']}`: {item['purpose']}"
            for item in pack["endpoint_references"]
        )
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        return "\n".join(lines).strip() + "\n"

    def _append_list(self, lines: list[str], items: list[Any]) -> None:
        if not items:
            lines.append("- None")
            return
        lines.extend(f"- {item}" for item in items)

    def _md_cell(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
