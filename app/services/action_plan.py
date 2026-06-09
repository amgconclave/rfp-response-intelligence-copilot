import json
import re
from collections import Counter, defaultdict
from typing import Any

from app.core.config import Settings
from app.models.api import AnalyzeResponse, CustomerFitResponse, HandoffBoardResponse
from app.models.domain import (
    CustomerFitRequirement,
    CustomerProfile,
    RequirementMatrixRow,
    ReviewFinding,
    RfpRequirement,
    StakeholderTask,
)


class StakeholderActionPlanService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_action_plan(
        self,
        trace_id: str,
        analysis: AnalyzeResponse | None = None,
        requirement_matrix: list[RequirementMatrixRow] | None = None,
        customer_profile: CustomerProfile | None = None,
        customer_fit: CustomerFitResponse | None = None,
        review_findings: list[ReviewFinding] | None = None,
    ) -> tuple[list[StakeholderTask], dict[str, Any]]:
        matrix = requirement_matrix or self._matrix_from_analysis(analysis)
        findings = review_findings or []
        findings_by_requirement = self._findings_by_requirement(findings)
        profile = customer_profile or (customer_fit.customer_profile if customer_fit else None)
        fit_review_ids = {
            requirement.requirement_id
            for requirement in customer_fit.requirements_needing_review
        } if customer_fit else set()
        tasks = [
            self._task_for_row(row, findings_by_requirement.get(row.requirement_id, []), profile, fit_review_ids)
            for row in matrix
        ]
        tasks.extend(self._tasks_for_unlinked_findings(findings, trace_id))
        return tasks, self._summary(tasks, matrix, findings, customer_fit)

    def export_handoff_board(
        self,
        trace_id: str,
        tasks: list[StakeholderTask],
        analysis: AnalyzeResponse | None = None,
        requirement_matrix: list[RequirementMatrixRow] | None = None,
        customer_profile: CustomerProfile | None = None,
        customer_fit: CustomerFitResponse | None = None,
        review_findings: list[ReviewFinding] | None = None,
        write_artifact: bool = True,
    ) -> HandoffBoardResponse:
        matrix = requirement_matrix or self._matrix_from_analysis(analysis)
        findings = review_findings or []
        board = self._board_payload(
            trace_id,
            tasks,
            matrix,
            analysis,
            customer_profile or (customer_fit.customer_profile if customer_fit else None),
            customer_fit,
            findings,
        )
        markdown = self._render_markdown(board)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            handoff_dir = self.settings.storage_dir / "handoffs"
            handoff_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = handoff_dir / f"rfp_handoff_{safe_trace_id}.md"
            json_path = handoff_dir / f"rfp_handoff_{safe_trace_id}.json"
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(board, indent=2), encoding="utf-8")
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
        return HandoffBoardResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            board=board,
            trace_id=trace_id,
        )

    def _task_for_row(
        self,
        row: RequirementMatrixRow,
        findings: list[ReviewFinding],
        profile: CustomerProfile | None,
        fit_review_ids: set[str],
    ) -> StakeholderTask:
        owner_role = self._owner_role(row, findings, profile)
        missing_evidence = bool(row.missing_evidence or not row.evidence_refs)
        high_finding = any(finding.severity in {"critical", "high"} for finding in findings)
        blocked = row.status == "blocked" or (missing_evidence and (row.risk_level == "high" or high_finding))
        needs_review = blocked or row.risk_level == "high" or missing_evidence or high_finding
        if row.requirement_id in fit_review_ids:
            needs_review = True
        priority = self._priority(row, findings, profile, missing_evidence)
        status = "blocked" if blocked else "needs_review" if needs_review else "ready_for_handoff"
        title = f"{owner_role.title()}: resolve {row.category} requirement"
        if status == "blocked":
            title = f"{owner_role.title()}: unblock {row.category} requirement"
        description = self._description(row, findings, profile, missing_evidence)
        return StakeholderTask(
            task_id=f"task_{row.requirement_id}_{owner_role}",
            owner_role=owner_role,
            title=title,
            description=description,
            priority=priority,
            due_hint=self._due_hint(priority, status),
            source_requirement_id=row.requirement_id,
            risk_level=row.risk_level,
            status=status,
            evidence_refs=self._evidence_refs(row, findings),
        )

    def _tasks_for_unlinked_findings(self, findings: list[ReviewFinding], trace_id: str) -> list[StakeholderTask]:
        tasks = []
        for index, finding in enumerate(findings, start=1):
            if finding.related_requirement_id:
                continue
            owner_role = self._owner_for_finding(finding)
            priority = "high" if finding.severity in {"critical", "high"} else "medium"
            status = "blocked" if finding.category in {"missing_evidence", "unsupported_claim"} else "needs_review"
            tasks.append(
                StakeholderTask(
                    task_id=f"task_{trace_id}_finding_{index}_{owner_role}",
                    owner_role=owner_role,
                    title=f"{owner_role.title()}: resolve review finding",
                    description=f"{finding.message} Recommendation: {finding.recommendation}",
                    priority=priority,
                    due_hint=self._due_hint(priority, status),
                    risk_level="high" if priority == "high" else "medium",
                    status=status,
                    evidence_refs=finding.citation_refs,
                )
            )
        return tasks

    def _owner_role(
        self,
        row: RequirementMatrixRow,
        findings: list[ReviewFinding],
        profile: CustomerProfile | None,
    ) -> str:
        text = f"{row.category} {row.requirement_text}".lower()
        categories = {finding.category for finding in findings}
        if any(term in text for term in ["contract", "dpa", "gdpr", "privacy", "subprocessor", "terms", "sla"]):
            return "legal"
        if row.category == "compliance":
            return "legal" if row.risk_level == "high" or profile and profile.risk_tolerance == "low" else "security"
        if row.category == "security":
            return "security"
        if row.category == "pricing":
            return "sales"
        if row.category == "implementation":
            if any(term in text for term in ["api", "webhook", "repository", "integration", "migration", "sso"]):
                return "engineering"
            return "solutions"
        if "unsupported_claim" in categories:
            return "solutions"
        if any(term in text for term in ["roadmap", "feature", "dashboard", "workflow", "retention", "report"]):
            return "product"
        if row.missing_evidence and row.category == "functional":
            return "product"
        return "solutions"

    def _owner_for_finding(self, finding: ReviewFinding) -> str:
        text = f"{finding.category} {finding.message} {finding.recommendation}".lower()
        if any(term in text for term in ["contract", "legal", "privacy", "gdpr", "subprocessor"]):
            return "legal"
        if any(term in text for term in ["security", "citation", "evidence", "control", "fedramp", "soc"]):
            return "security"
        if any(term in text for term in ["cost", "pricing", "commercial"]):
            return "sales"
        return "solutions"

    def _priority(
        self,
        row: RequirementMatrixRow,
        findings: list[ReviewFinding],
        profile: CustomerProfile | None,
        missing_evidence: bool,
    ) -> str:
        if row.status == "blocked" or row.risk_level == "high" or any(
            finding.severity in {"critical", "high"} for finding in findings
        ):
            return "high"
        if missing_evidence or row.priority == "high" or profile and profile.risk_tolerance == "low":
            return "medium"
        return "low"

    def _due_hint(self, priority: str, status: str) -> str:
        if status == "blocked":
            return "before the next customer review call"
        if priority == "high":
            return "within 2 business days"
        if priority == "medium":
            return "this week"
        return "before final submission"

    def _description(
        self,
        row: RequirementMatrixRow,
        findings: list[ReviewFinding],
        profile: CustomerProfile | None,
        missing_evidence: bool,
    ) -> str:
        parts = [row.requirement_text]
        if missing_evidence:
            parts.append("Attach approved evidence or document an explicit exception.")
        if profile:
            parts.append(f"Customer profile: {profile.name}, risk tolerance {profile.risk_tolerance}.")
        if findings:
            parts.append("Review findings: " + "; ".join(finding.message for finding in findings[:2]))
        return " ".join(parts)

    def _evidence_refs(self, row: RequirementMatrixRow, findings: list[ReviewFinding]) -> list[str]:
        refs = list(row.evidence_refs)
        for finding in findings:
            refs.extend(finding.citation_refs)
        return list(dict.fromkeys(refs))

    def _board_payload(
        self,
        trace_id: str,
        tasks: list[StakeholderTask],
        matrix: list[RequirementMatrixRow],
        analysis: AnalyzeResponse | None,
        customer_profile: CustomerProfile | None,
        customer_fit: CustomerFitResponse | None,
        review_findings: list[ReviewFinding],
    ) -> dict[str, Any]:
        missing_evidence = sorted(
            {
                item
                for row in matrix
                for item in row.missing_evidence
            }
            | ({item for item in analysis.missing_information} if analysis else set())
            | {
                finding.message
                for finding in review_findings
                if finding.category == "missing_evidence"
            }
        )
        blocked_items = [task.model_dump(mode="json") for task in tasks if task.status == "blocked"]
        high_risk_requirements = [
            row.model_dump(mode="json")
            for row in matrix
            if row.risk_level == "high" or row.status == "blocked"
        ]
        customer_fit_notes = self._customer_fit_notes(customer_profile, customer_fit)
        return {
            "trace_id": trace_id,
            "summary": self._summary(tasks, matrix, review_findings, customer_fit),
            "action_plan": [task.model_dump(mode="json") for task in tasks],
            "blocked_items": blocked_items,
            "high_risk_requirements": high_risk_requirements,
            "customer_fit_notes": customer_fit_notes,
            "missing_evidence": missing_evidence,
            "review_findings": [finding.model_dump(mode="json") for finding in review_findings],
            "next_meeting_agenda": self._agenda(tasks, high_risk_requirements, missing_evidence, customer_fit_notes),
        }

    def _customer_fit_notes(
        self,
        customer_profile: CustomerProfile | None,
        customer_fit: CustomerFitResponse | None,
    ) -> list[str]:
        notes = []
        if customer_profile:
            notes.append(
                f"{customer_profile.name}: {customer_profile.industry}, {customer_profile.region}, "
                f"risk tolerance {customer_profile.risk_tolerance}."
            )
        if customer_fit:
            notes.append(f"Fit score: {customer_fit.fit_score}.")
            notes.extend(customer_fit.recommended_positioning[:3])
            notes.extend(customer_fit.profile_risks[:3])
            notes.extend(self._fit_requirement_notes("Needs review", customer_fit.requirements_needing_review))
        return notes or ["No customer profile or fit notes supplied."]

    def _fit_requirement_notes(self, label: str, requirements: list[CustomerFitRequirement]) -> list[str]:
        return [
            f"{label}: {requirement.requirement_id} - {requirement.reason}"
            for requirement in requirements[:4]
        ]

    def _agenda(
        self,
        tasks: list[StakeholderTask],
        high_risk_requirements: list[dict[str, Any]],
        missing_evidence: list[str],
        customer_fit_notes: list[str],
    ) -> list[str]:
        owner_counts = Counter(task.owner_role for task in tasks if task.status in {"blocked", "needs_review"})
        agenda = [
            "Confirm owners and due hints for all blocked stakeholder tasks.",
            f"Review {len(high_risk_requirements)} high-risk requirements and required exceptions.",
            f"Close or explicitly disclose {len(missing_evidence)} missing evidence items.",
        ]
        if owner_counts:
            owner_summary = ", ".join(f"{owner}={count}" for owner, count in sorted(owner_counts.items()))
            agenda.append(f"Walk through open task load by owner: {owner_summary}.")
        if customer_fit_notes:
            agenda.append("Validate customer-fit positioning and risk tolerance with sales leadership.")
        return agenda

    def _summary(
        self,
        tasks: list[StakeholderTask],
        matrix: list[RequirementMatrixRow],
        review_findings: list[ReviewFinding],
        customer_fit: CustomerFitResponse | None,
    ) -> dict[str, Any]:
        owner_counts = Counter(task.owner_role for task in tasks)
        status_counts = Counter(task.status for task in tasks)
        priority_counts = Counter(task.priority for task in tasks)
        return {
            "task_count": len(tasks),
            "task_counts_by_owner": dict(sorted(owner_counts.items())),
            "task_counts_by_status": dict(sorted(status_counts.items())),
            "task_counts_by_priority": dict(sorted(priority_counts.items())),
            "blocked_tasks": status_counts.get("blocked", 0),
            "high_risk_requirements": sum(1 for row in matrix if row.risk_level == "high" or row.status == "blocked"),
            "review_findings": len(review_findings),
            "customer_fit_score": customer_fit.fit_score if customer_fit else None,
        }

    def _render_markdown(self, board: dict[str, Any]) -> str:
        lines = [
            "# Stakeholder Action Plan and Handoff Board",
            "",
            "## Summary",
            "",
        ]
        summary = board["summary"]
        lines.extend(
            [
                f"- Tasks: {summary['task_count']}",
                f"- Blocked tasks: {summary['blocked_tasks']}",
                f"- High-risk requirements: {summary['high_risk_requirements']}",
                f"- Review findings: {summary['review_findings']}",
                "",
                "## Action Plan",
                "",
                "| Task | Owner | Priority | Status | Risk | Due | Requirement | Evidence |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for task in board["action_plan"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._md_cell(task["title"]),
                        self._md_cell(task["owner_role"]),
                        self._md_cell(task["priority"]),
                        self._md_cell(task["status"]),
                        self._md_cell(task["risk_level"]),
                        self._md_cell(task["due_hint"]),
                        self._md_cell(task.get("source_requirement_id") or ""),
                        self._md_cell(", ".join(task["evidence_refs"]) or "Missing"),
                    ]
                )
                + " |"
            )
        lines.extend(["", "## Blocked Items", ""])
        self._append_task_list(lines, board["blocked_items"])
        lines.extend(["", "## High-Risk Requirements", ""])
        if board["high_risk_requirements"]:
            for row in board["high_risk_requirements"]:
                lines.append(f"- {row['requirement_id']}: {row['requirement_text']}")
        else:
            lines.append("- None")
        lines.extend(["", "## Customer-Fit Notes", ""])
        lines.extend(f"- {note}" for note in board["customer_fit_notes"])
        lines.extend(["", "## Missing Evidence", ""])
        if board["missing_evidence"]:
            lines.extend(f"- {item}" for item in board["missing_evidence"])
        else:
            lines.append("- None")
        lines.extend(["", "## Review Findings", ""])
        if board["review_findings"]:
            for finding in board["review_findings"]:
                lines.append(f"- {finding['severity']} / {finding['category']}: {finding['message']}")
        else:
            lines.append("- None")
        lines.extend(["", "## Next Meeting Agenda", ""])
        lines.extend(f"- {item}" for item in board["next_meeting_agenda"])
        return "\n".join(lines).strip() + "\n"

    def _append_task_list(self, lines: list[str], tasks: list[dict[str, Any]]) -> None:
        if not tasks:
            lines.append("- None")
            return
        for task in tasks:
            lines.append(f"- {task['owner_role']}: {task['title']} ({task['due_hint']})")

    def _matrix_from_analysis(self, analysis: AnalyzeResponse | None) -> list[RequirementMatrixRow]:
        if analysis is None:
            return []
        return [
            RequirementMatrixRow(
                requirement_id=requirement.id,
                category=requirement.category,
                requirement_text=requirement.text,
                priority=requirement.priority,
                owner_role=self._fallback_matrix_owner(requirement),
                status="blocked" if requirement.missing_info else "not_started",
                risk_level="high" if requirement.priority == "high" or requirement.missing_info else "medium",
                suggested_response="Assign a stakeholder to attach approved evidence before submission.",
                missing_evidence=list(requirement.missing_info),
                evidence_refs=list(requirement.evidence_refs),
            )
            for requirement in analysis.requirements
        ]

    def _fallback_matrix_owner(self, requirement: RfpRequirement) -> str:
        return {
            "security": "Security Architect",
            "compliance": "Compliance Lead",
            "pricing": "Commercial Owner",
            "implementation": "Implementation Lead",
        }.get(requirement.category, "Solutions Engineer")

    def _findings_by_requirement(self, findings: list[ReviewFinding]) -> dict[str, list[ReviewFinding]]:
        grouped: dict[str, list[ReviewFinding]] = defaultdict(list)
        for finding in findings:
            if finding.related_requirement_id:
                grouped[finding.related_requirement_id].append(finding)
        return grouped

    def _md_cell(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
