from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    ContractRiskResponse,
    ReviewerAssignment,
    ReviewerCollaborationPackResponse,
    ReviewerCollaborationResponse,
    ReviewerDecisionComment,
    SubmissionDecisionResponse,
)
from app.models.domain import (
    DraftResponse,
    EvidenceGap,
    RequirementMatrixRow,
    ReviewFinding,
    StakeholderTask,
)

REVIEWER_DIRECTORY = {
    "sales": "Ava Sales Lead",
    "solutions": "Noah Solutions Architect",
    "security": "Maya Security Reviewer",
    "legal": "Liam Legal Counsel",
    "product": "Priya Product Owner",
    "engineering": "Ethan Engineering Lead",
    "finance": "Sofia Finance Approver",
    "executive_sponsor": "Jordan Executive Sponsor",
}


class ReviewerCollaborationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_board(
        self,
        trace_id: str,
        requirement_matrix: list[RequirementMatrixRow] | None = None,
        draft_response: DraftResponse | None = None,
        review_findings: list[ReviewFinding] | None = None,
        review_passed: bool | None = None,
        action_plan: list[StakeholderTask] | None = None,
        evidence_gaps: list[EvidenceGap] | None = None,
        contract_risk: ContractRiskResponse | None = None,
        submission_decision: SubmissionDecisionResponse | None = None,
    ) -> ReviewerCollaborationResponse:
        matrix = requirement_matrix or []
        findings = review_findings or []
        tasks = action_plan or []
        gaps = evidence_gaps or []
        assignments = self._assignments(matrix, findings, tasks, gaps, contract_risk, submission_decision)
        comments = self._decision_comments(findings, matrix, gaps, contract_risk, submission_decision)
        approval_summary = self._approval_summary(assignments, comments, review_passed, submission_decision)
        redline_summary = self._redline_summary(contract_risk, findings, draft_response)
        board_status = self._board_status(approval_summary, redline_summary)
        return ReviewerCollaborationResponse(
            title="Reviewer Collaboration Board",
            board_status=board_status,
            assignments=assignments,
            decision_comments=comments,
            approval_summary=approval_summary,
            redline_summary=redline_summary,
            reviewer_queue=self._reviewer_queue(assignments, comments),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def collaboration_pack(
        self,
        trace_id: str,
        collaboration: ReviewerCollaborationResponse,
        write_artifact: bool = True,
    ) -> ReviewerCollaborationPackResponse:
        pack = self._pack_payload(trace_id, collaboration)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "review_boards"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"reviewer_collaboration_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"reviewer_collaboration_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["collaboration_pack_markdown"] = artifact_path
            pack["artifact_paths"]["collaboration_pack_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return ReviewerCollaborationPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            collaboration=collaboration,
            trace_id=trace_id,
        )

    def _assignments(
        self,
        matrix: list[RequirementMatrixRow],
        findings: list[ReviewFinding],
        tasks: list[StakeholderTask],
        gaps: list[EvidenceGap],
        contract_risk: ContractRiskResponse | None,
        submission_decision: SubmissionDecisionResponse | None,
    ) -> list[ReviewerAssignment]:
        roles = sorted(
            {
                row.owner_role
                for row in matrix
            }
            | {task.owner_role for task in tasks}
            | {self._role_for_finding(finding) for finding in findings}
            | {self._role_for_gap(gap) for gap in gaps}
        )
        if contract_risk and contract_risk.risky_clauses:
            roles.append("legal")
        if submission_decision and submission_decision.approvals_required:
            roles.extend(self._normalise_role(item.get("owner", "")) for item in submission_decision.approvals_required)
        assignments: list[ReviewerAssignment] = []
        for role in sorted({role for role in roles if role}):
            role_rows = [row for row in matrix if row.owner_role == role]
            role_tasks = [task for task in tasks if task.owner_role == role]
            role_findings = [finding for finding in findings if self._role_for_finding(finding) == role]
            role_gaps = [gap for gap in gaps if self._role_for_gap(gap) == role]
            blocking_items = self._blocking_items(role_rows, role_tasks, role_findings, role_gaps, role, contract_risk)
            status = self._assignment_status(role_rows, role_tasks, role_findings, role_gaps, blocking_items)
            priority = "high" if blocking_items else self._role_priority(role_rows, role_tasks, role_findings)
            assignments.append(
                ReviewerAssignment(
                    assignment_id=f"review_{role}_{len(assignments) + 1}",
                    reviewer_role=role,
                    reviewer_name=REVIEWER_DIRECTORY.get(role, f"{role.title()} Reviewer"),
                    scope=self._assignment_scope(role, role_rows, role_findings, role_gaps, contract_risk),
                    priority=priority,
                    status=status,
                    approval_status=self._approval_status(status, role_findings, role_gaps),
                    due_hint=self._due_hint(role, priority),
                    requirement_ids=sorted(
                        {row.requirement_id for row in role_rows} | self._finding_req_ids(role_findings)
                    ),
                    source_signals=self._source_signals(role_rows, role_tasks, role_findings, role_gaps),
                    blocking_items=blocking_items,
                    citation_refs=sorted({ref for row in role_rows for ref in row.evidence_refs}),
                )
            )
        if not assignments:
            assignments.append(
                ReviewerAssignment(
                    assignment_id="review_sales_1",
                    reviewer_role="sales",
                    reviewer_name=REVIEWER_DIRECTORY["sales"],
                    scope="Confirm the response package has enough workflow context for review.",
                    priority="medium",
                    status="pending_review",
                    approval_status="pending_review",
                    due_hint="before draft freeze",
                    source_signals=["No matrix, findings, or action-plan inputs were provided."],
                )
            )
        return assignments

    def _decision_comments(
        self,
        findings: list[ReviewFinding],
        matrix: list[RequirementMatrixRow],
        gaps: list[EvidenceGap],
        contract_risk: ContractRiskResponse | None,
        submission_decision: SubmissionDecisionResponse | None,
    ) -> list[ReviewerDecisionComment]:
        comments: list[ReviewerDecisionComment] = []
        for finding in findings:
            role = self._role_for_finding(finding)
            comments.append(
                self._comment(
                    comments,
                    role,
                    finding.category,
                    finding.severity,
                    finding.message,
                    finding.recommendation,
                    related_requirement_id=finding.related_requirement_id,
                    citation_refs=finding.citation_refs,
                    related_artifact="review_board",
                )
            )
        for row in matrix:
            if row.missing_evidence or row.status == "blocked":
                comments.append(
                    self._comment(
                        comments,
                        row.owner_role,
                        "missing_evidence",
                        "high" if row.status == "blocked" else row.risk_level,
                        f"{row.requirement_id} cannot be approved without evidence closure.",
                        "; ".join(row.missing_evidence) or "Attach approved source evidence or approve an exception.",
                        related_requirement_id=row.requirement_id,
                        citation_refs=row.evidence_refs,
                        related_artifact="requirement_matrix",
                    )
                )
        for gap in gaps[:8]:
            role = self._role_for_gap(gap)
            comments.append(
                self._comment(
                    comments,
                    role,
                    "evidence_gap",
                    gap.severity,
                    f"{gap.title} blocks {', '.join(gap.impacted_sections) or 'the response package'}.",
                    gap.suggested_sme_or_source_request,
                    related_requirement_id=gap.requirement_ids[0] if gap.requirement_ids else None,
                    citation_refs=gap.related_citations,
                    related_artifact="source_request_pack",
                )
            )
        if contract_risk:
            for clause in contract_risk.risky_clauses[:8]:
                comments.append(
                    self._comment(
                        comments,
                        "legal",
                        "redline",
                        clause.risk_level,
                        f"{clause.title} needs legal redline approval.",
                        clause.suggested_redline,
                        related_requirement_id=clause.clause_id,
                        citation_refs=[str(point.get("source", "")) for point in clause.proof_points],
                        related_artifact="contract_risk",
                    )
                )
        if submission_decision:
            for issue in submission_decision.blocking_issues[:8]:
                role = self._normalise_role(str(issue.get("owner", "")))
                comments.append(
                    self._comment(
                        comments,
                        role,
                        "submission_decision",
                        str(issue.get("severity", "high")),
                        str(issue.get("issue", issue.get("blocker", "Submission blocker requires approval."))),
                        str(issue.get("required_action", issue.get("resolution", "Resolve before submission."))),
                        related_requirement_id=issue.get("requirement_id"),
                        related_artifact="submission_decision",
                    )
                )
        return comments

    def _comment(
        self,
        comments: list[ReviewerDecisionComment],
        role: str,
        category: str,
        severity: str,
        comment: str,
        required_action: str,
        related_requirement_id: str | None = None,
        related_artifact: str | None = None,
        citation_refs: list[str] | None = None,
    ) -> ReviewerDecisionComment:
        normalised_role = self._normalise_role(role)
        severity_label = severity if severity in {"low", "medium", "high", "critical"} else "medium"
        return ReviewerDecisionComment(
            comment_id=f"comment_{len(comments) + 1}",
            reviewer_role=normalised_role,
            reviewer_name=REVIEWER_DIRECTORY.get(normalised_role, f"{normalised_role.title()} Reviewer"),
            category=category,
            severity=severity_label,
            sentiment="blocker" if severity_label in {"high", "critical"} else "concern",
            comment=comment,
            required_action=required_action,
            status="open" if severity_label in {"high", "critical"} else "needs_review",
            related_requirement_id=related_requirement_id,
            related_artifact=related_artifact,
            citation_refs=citation_refs or [],
        )

    def _approval_summary(
        self,
        assignments: list[ReviewerAssignment],
        comments: list[ReviewerDecisionComment],
        review_passed: bool | None,
        submission_decision: SubmissionDecisionResponse | None,
    ) -> dict[str, Any]:
        status_counts = Counter(assignment.approval_status for assignment in assignments)
        role_status = {
            assignment.reviewer_role: assignment.approval_status
            for assignment in assignments
        }
        blockers = [comment for comment in comments if comment.sentiment == "blocker" and comment.status == "open"]
        return {
            "assignment_count": len(assignments),
            "approved_count": status_counts.get("approved", 0),
            "conditional_count": status_counts.get("conditional_approval", 0),
            "blocked_count": status_counts.get("blocked", 0),
            "pending_count": status_counts.get("pending_review", 0),
            "open_decision_comment_count": sum(comment.status == "open" for comment in comments),
            "blocker_comment_count": len(blockers),
            "review_passed": review_passed,
            "submission_decision": submission_decision.decision if submission_decision else None,
            "roles": role_status,
            "ready_for_submission": (
                not blockers
                and status_counts.get("blocked", 0) == 0
                and review_passed is not False
            ),
        }

    def _redline_summary(
        self,
        contract_risk: ContractRiskResponse | None,
        findings: list[ReviewFinding],
        draft_response: DraftResponse | None,
    ) -> dict[str, Any]:
        contract_items = []
        if contract_risk:
            for clause in contract_risk.risky_clauses:
                contract_items.append(
                    {
                        "source": "contract",
                        "id": clause.clause_id,
                        "category": clause.category,
                        "title": clause.title,
                        "risk_level": clause.risk_level,
                        "suggested_redline": clause.suggested_redline,
                        "fallback_position": clause.fallback_position,
                    }
                )
        draft_items = [
            {
                "source": "draft_or_answer",
                "id": finding.finding_id,
                "category": finding.category,
                "title": finding.message,
                "risk_level": finding.severity,
                "suggested_redline": finding.recommendation,
                "fallback_position": "Rewrite as an assumption or no-evidence caveat until cited support exists.",
            }
            for finding in findings
            if finding.category in {"unsupported_claim", "missing_evidence", "weak_citation"}
        ]
        section_count = len(draft_response.sections) if draft_response else 0
        redlines = contract_items + draft_items
        category_counts = Counter(item["category"] for item in redlines)
        return {
            "redline_count": len(redlines),
            "contract_redline_count": len(contract_items),
            "draft_redline_count": len(draft_items),
            "draft_sections_reviewed": section_count,
            "critical_or_high_count": sum(item["risk_level"] in {"critical", "high"} for item in redlines),
            "requires_legal_approval": bool(contract_items),
            "category_counts": dict(category_counts),
            "items": redlines[:20],
        }

    def _reviewer_queue(
        self,
        assignments: list[ReviewerAssignment],
        comments: list[ReviewerDecisionComment],
    ) -> list[dict[str, Any]]:
        comment_counts = Counter(comment.reviewer_role for comment in comments if comment.status == "open")
        return [
            {
                "reviewer_role": assignment.reviewer_role,
                "reviewer_name": assignment.reviewer_name,
                "priority": assignment.priority,
                "approval_status": assignment.approval_status,
                "open_comments": comment_counts.get(assignment.reviewer_role, 0),
                "next_action": assignment.blocking_items[0] if assignment.blocking_items else assignment.scope,
            }
            for assignment in sorted(
                assignments,
                key=lambda item: (
                    item.approval_status != "blocked",
                    item.priority != "high",
                    item.reviewer_role,
                ),
            )
        ]

    def _pack_payload(self, trace_id: str, collaboration: ReviewerCollaborationResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Reviewer Collaboration Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "board_status": collaboration.board_status,
            "approval_summary": collaboration.approval_summary,
            "assignments": [assignment.model_dump(mode="json") for assignment in collaboration.assignments],
            "decision_comments": [comment.model_dump(mode="json") for comment in collaboration.decision_comments],
            "redline_summary": collaboration.redline_summary,
            "reviewer_queue": collaboration.reviewer_queue,
            "local_proof_commands": collaboration.local_proof_commands,
            "limitations": collaboration.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        summary = pack["approval_summary"]
        lines = [
            "# Reviewer Collaboration Pack",
            "",
            "## Approval Summary",
            "",
            f"- Board status: {pack['board_status']}",
            f"- Assignments: {summary['assignment_count']}",
            f"- Approved: {summary['approved_count']}",
            f"- Conditional: {summary['conditional_count']}",
            f"- Blocked: {summary['blocked_count']}",
            f"- Pending: {summary['pending_count']}",
            f"- Open decision comments: {summary['open_decision_comment_count']}",
            f"- Ready for submission: {summary['ready_for_submission']}",
            "",
            "## Reviewer Assignments",
            "",
            "| Reviewer | Role | Priority | Status | Approval | Requirements | Blocking Items |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for assignment in pack["assignments"]:
            lines.append(
                f"| {assignment['reviewer_name']} | {assignment['reviewer_role']} | {assignment['priority']} | "
                f"{assignment['status']} | {assignment['approval_status']} | "
                f"{', '.join(assignment['requirement_ids']) or 'None'} | "
                f"{'; '.join(assignment['blocking_items']) or 'None'} |"
            )
        lines.extend(["", "## Decision Comments", ""])
        lines.append("| Reviewer | Category | Severity | Status | Comment | Required Action |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for comment in pack["decision_comments"]:
            lines.append(
                f"| {comment['reviewer_name']} | {comment['category']} | {comment['severity']} | "
                f"{comment['status']} | {comment['comment']} | {comment['required_action']} |"
            )
        redlines = pack["redline_summary"]
        lines.extend(["", "## Redline Summary", ""])
        lines.append(f"- Redlines: {redlines['redline_count']}")
        lines.append(f"- Contract redlines: {redlines['contract_redline_count']}")
        lines.append(f"- Draft redlines: {redlines['draft_redline_count']}")
        lines.append(f"- Requires legal approval: {redlines['requires_legal_approval']}")
        lines.extend(["", "## Redline Items", ""])
        for item in redlines["items"]:
            lines.append(
                f"- {item['source']} {item['id']} ({item['risk_level']}): "
                f"{item['suggested_redline']} Fallback: {item['fallback_position']}"
            )
        lines.extend(["", "## Reviewer Queue", ""])
        for item in pack["reviewer_queue"]:
            lines.append(
                f"- {item['reviewer_name']} ({item['approval_status']}): "
                f"{item['open_comments']} open comments. Next: {item['next_action']}"
            )
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```bash\n{command}\n```" for command in pack["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Collaboration Pack Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _blocking_items(
        self,
        rows: list[RequirementMatrixRow],
        tasks: list[StakeholderTask],
        findings: list[ReviewFinding],
        gaps: list[EvidenceGap],
        role: str,
        contract_risk: ContractRiskResponse | None,
    ) -> list[str]:
        items = []
        items.extend(
            f"{row.requirement_id}: {'; '.join(row.missing_evidence) or row.status}"
            for row in rows
            if row.status == "blocked" or row.missing_evidence
        )
        items.extend(task.title for task in tasks if task.status == "blocked")
        items.extend(finding.message for finding in findings if finding.severity in {"high", "critical"})
        items.extend(gap.title for gap in gaps if gap.severity in {"high", "critical"})
        if role == "legal" and contract_risk and contract_risk.status in {"high_risk", "critical"}:
            items.append(f"Contract risk is {contract_risk.status}; approve redlines before submission.")
        return items[:8]

    def _assignment_status(
        self,
        rows: list[RequirementMatrixRow],
        tasks: list[StakeholderTask],
        findings: list[ReviewFinding],
        gaps: list[EvidenceGap],
        blocking_items: list[str],
    ) -> str:
        if blocking_items:
            return "blocked"
        if findings or gaps or any(row.status == "needs_review" for row in rows):
            return "needs_review"
        if rows and all(row.status == "evidence_found" for row in rows):
            return "approved"
        if tasks and all(task.status == "ready_for_handoff" for task in tasks):
            return "approved"
        return "pending_review"

    def _approval_status(
        self,
        status: str,
        findings: list[ReviewFinding],
        gaps: list[EvidenceGap],
    ) -> str:
        if status == "blocked":
            return "blocked"
        if status == "approved":
            return "approved"
        if findings or gaps:
            return "conditional_approval"
        return "pending_review"

    def _role_priority(
        self,
        rows: list[RequirementMatrixRow],
        tasks: list[StakeholderTask],
        findings: list[ReviewFinding],
    ) -> str:
        if any(row.risk_level == "high" for row in rows) or any(finding.severity == "high" for finding in findings):
            return "high"
        if any(task.priority == "high" for task in tasks):
            return "high"
        if rows or tasks or findings:
            return "medium"
        return "low"

    def _assignment_scope(
        self,
        role: str,
        rows: list[RequirementMatrixRow],
        findings: list[ReviewFinding],
        gaps: list[EvidenceGap],
        contract_risk: ContractRiskResponse | None,
    ) -> str:
        if role == "legal" and contract_risk and contract_risk.risky_clauses:
            return "Approve customer contract redlines, fallback positions, and legal exception language."
        if gaps:
            return "Close source requests and confirm missing evidence before draft freeze."
        if findings:
            return "Resolve review-board comments and approve revised response language."
        if rows:
            categories = sorted({row.category for row in rows})
            return f"Approve {', '.join(categories)} response rows and attached evidence."
        return "Confirm assigned response area is ready for submission."

    def _source_signals(
        self,
        rows: list[RequirementMatrixRow],
        tasks: list[StakeholderTask],
        findings: list[ReviewFinding],
        gaps: list[EvidenceGap],
    ) -> list[str]:
        signals = []
        if rows:
            signals.append(f"{len(rows)} requirement row(s)")
        if tasks:
            signals.append(f"{len(tasks)} stakeholder task(s)")
        if findings:
            signals.append(f"{len(findings)} review finding(s)")
        if gaps:
            signals.append(f"{len(gaps)} evidence gap(s)")
        return signals or ["Manual reviewer assignment"]

    def _due_hint(self, role: str, priority: str) -> str:
        if priority == "high":
            return "before executive submission review"
        if role in {"legal", "security", "finance"}:
            return "before final approval gate"
        return "before draft freeze"

    def _board_status(self, approval_summary: dict[str, Any], redline_summary: dict[str, Any]) -> str:
        if approval_summary["blocked_count"] or approval_summary["blocker_comment_count"]:
            return "blocked"
        if redline_summary["critical_or_high_count"] or approval_summary["conditional_count"]:
            return "needs_review"
        if approval_summary["pending_count"]:
            return "pending_review"
        return "approved"

    def _role_for_finding(self, finding: ReviewFinding) -> str:
        text = f"{finding.category} {finding.message} {finding.recommendation}".lower()
        if "legal" in text or "contract" in text or "redline" in text or "privacy" in text:
            return "legal"
        if "pricing" in text or "discount" in text or "commercial" in text:
            return "finance"
        if "security" in text or "encryption" in text or "sso" in text or "fedramp" in text:
            return "security"
        if "product" in text or "roadmap" in text or "feature" in text:
            return "product"
        if finding.related_requirement_id:
            return "solutions"
        return "sales"

    def _role_for_gap(self, gap: EvidenceGap) -> str:
        return self._normalise_role(gap.owner_team)

    def _normalise_role(self, value: str) -> str:
        lowered = value.lower().replace(" ", "_").replace("-", "_")
        if "legal" in lowered or "privacy" in lowered or "contract" in lowered:
            return "legal"
        if "security" in lowered or "compliance" in lowered:
            return "security"
        if "finance" in lowered or "pricing" in lowered or "commercial" in lowered:
            return "finance"
        if "product" in lowered:
            return "product"
        if "engineering" in lowered or "implementation" in lowered:
            return "engineering"
        if "executive" in lowered:
            return "executive_sponsor"
        if "solution" in lowered or "presales" in lowered:
            return "solutions"
        if lowered in REVIEWER_DIRECTORY:
            return lowered
        return "sales"

    def _finding_req_ids(self, findings: list[ReviewFinding]) -> set[str]:
        return {finding.related_requirement_id for finding in findings if finding.related_requirement_id}

    def _local_proof_commands(self) -> list[str]:
        return [
            "python -m pytest -q",
            "python -m ruff check .",
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/reviewer-collaboration" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/reviewer-collaboration-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'rg "reviewer-collaboration|Reviewer Collaboration|review_boards" '
                "app dashboard docs README.md tests Makefile"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Reviewer assignments are deterministic local workflow suggestions, not persisted user accounts.",
            (
                "Approval status is derived from local RFP signals and still requires human confirmation "
                "before submission."
            ),
            (
                "Redline summaries are generated from sample contract-risk and review findings; "
                "no legal system is integrated."
            ),
            "Artifacts under storage/review_boards are ignored by git and should be regenerated for each local review.",
        ]
