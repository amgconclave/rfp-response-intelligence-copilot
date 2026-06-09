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
    LeadershipBriefResponse,
)
from app.models.domain import (
    Answer,
    DraftResponse,
    RequirementMatrixRow,
    ResponseMemoryMatch,
    ReviewFinding,
    StakeholderTask,
)


class LeadershipBriefService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def export_brief(
        self,
        trace_id: str,
        documents_ingested: int,
        analysis: AnalyzeResponse | None = None,
        requirement_matrix: list[RequirementMatrixRow] | None = None,
        draft_response: DraftResponse | None = None,
        answers: list[Answer] | None = None,
        export_payload: dict[str, Any] | None = None,
        export_artifact_path: str | None = None,
        export_json_artifact_path: str | None = None,
        review_findings: list[ReviewFinding] | None = None,
        review_passed: bool | None = None,
        customer_fit: CustomerFitResponse | None = None,
        response_memory_matches: list[ResponseMemoryMatch] | None = None,
        action_plan: list[StakeholderTask] | None = None,
        handoff_board: dict[str, Any] | None = None,
        handoff_artifact_path: str | None = None,
        handoff_json_artifact_path: str | None = None,
        readiness_scorecard: DealReadinessScorecardResponse | None = None,
        executive_report: ExecutiveRiskReportResponse | None = None,
        executive_report_artifact_path: str | None = None,
        executive_report_json_artifact_path: str | None = None,
        eval_metrics: EvaluationMetrics | None = None,
        red_team_summary: dict[str, Any] | None = None,
        write_artifact: bool = True,
    ) -> LeadershipBriefResponse:
        matrix = requirement_matrix or []
        findings = review_findings or []
        tasks = action_plan or []
        matches = response_memory_matches or []
        answer_list = answers or []
        report_path = executive_report_artifact_path or (executive_report.artifact_path if executive_report else None)
        report_json_path = executive_report_json_artifact_path or (
            executive_report.json_artifact_path if executive_report else None
        )
        export_path = export_artifact_path
        export_json_path = export_json_artifact_path

        if export_payload is None and executive_report is not None:
            export_payload = {}
        metrics = {
            "docs_ingested": documents_ingested,
            "requirements": self._requirement_count(analysis, matrix, export_payload),
            "evidence_coverage": self._evidence_coverage(matrix, readiness_scorecard),
            "evidence_backed_requirements": sum(1 for row in matrix if row.evidence_refs),
            "citations": self._citation_count(draft_response, answer_list, export_payload),
            "red_team_pass": self._red_team_pass(red_team_summary),
            "customer_fit_score": self._customer_fit_score(customer_fit, export_payload, readiness_scorecard),
            "task_counts": self._task_counts(tasks, handoff_board),
            "readiness_score": readiness_scorecard.readiness_score if readiness_scorecard else None,
            "readiness_level": readiness_scorecard.readiness_level if readiness_scorecard else None,
        }
        artifact_links = {
            "rfp_analysis": self._analysis_link(analysis),
            "requirement_matrix": {"rows": len(matrix)},
            "draft_response": self._draft_link(draft_response),
            "export_package": {
                "artifact_path": export_path,
                "json_artifact_path": export_json_path,
                "summary": (export_payload or {}).get("executive_summary"),
            },
            "review_board": {
                "passed": review_passed,
                "finding_count": len(findings),
                "categories": dict(sorted(Counter(finding.category for finding in findings).items())),
            },
            "red_team": red_team_summary or {},
            "customer_fit": self._customer_fit_link(customer_fit, export_payload),
            "response_memory": {
                "match_count": len(matches),
                "matches": [match.title for match in matches],
            },
            "action_plan": {"task_count": len(tasks), "owners": metrics["task_counts"]["by_owner"]},
            "handoff_board": {
                "artifact_path": handoff_artifact_path,
                "json_artifact_path": handoff_json_artifact_path,
                "agenda_count": len(self._meeting_agenda(handoff_board, readiness_scorecard)),
            },
            "readiness_scorecard": self._readiness_link(readiness_scorecard),
            "executive_report": {
                "artifact_path": report_path,
                "json_artifact_path": report_json_path,
                "submission_recommendation": self._submission_recommendation(executive_report),
            },
        }
        brief = {
            "trace_id": trace_id,
            "title": "Portfolio Demo Summary + RFP Leadership Brief",
            "metrics": metrics,
            "artifact_links": artifact_links,
            "recommended_next_meeting_agenda": self._meeting_agenda(handoff_board, readiness_scorecard),
            "recommended_next_actions": readiness_scorecard.recommended_next_actions if readiness_scorecard else [],
            "portfolio_story": [
                "Ingest approved local documents.",
                "Analyze the RFP and convert requirements into an ownership matrix.",
                "Draft cited responses and export a Markdown/JSON package.",
                "Review answer and package risks, then run red-team checks.",
                "Score customer fit and reuse approved local response memory.",
                "Create stakeholder action plans, handoff boards, readiness scorecards, and executive reports.",
            ],
        }
        markdown = self._render_markdown(brief)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            brief_dir = self.settings.storage_dir / "leadership_briefs"
            brief_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = brief_dir / f"leadership_brief_{safe_trace_id}.md"
            json_path = brief_dir / f"leadership_brief_{safe_trace_id}.json"
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(brief, indent=2), encoding="utf-8")
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
        return LeadershipBriefResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            brief=brief,
            trace_id=trace_id,
        )

    def _requirement_count(
        self,
        analysis: AnalyzeResponse | None,
        matrix: list[RequirementMatrixRow],
        export_payload: dict[str, Any] | None,
    ) -> int:
        if analysis:
            return len(analysis.requirements)
        if matrix:
            return len(matrix)
        summary = (export_payload or {}).get("executive_summary", {})
        return int(summary.get("requirement_count", 0))

    def _evidence_coverage(
        self,
        matrix: list[RequirementMatrixRow],
        readiness_scorecard: DealReadinessScorecardResponse | None,
    ) -> float:
        if readiness_scorecard:
            return readiness_scorecard.evidence_coverage
        if not matrix:
            return 0.0
        covered = sum(1 for row in matrix if row.evidence_refs and not row.missing_evidence)
        return round(covered / len(matrix), 2)

    def _citation_count(
        self,
        draft_response: DraftResponse | None,
        answers: list[Answer],
        export_payload: dict[str, Any] | None,
    ) -> int:
        citation_keys = set()
        if draft_response:
            citation_keys.update(
                self._citation_key(citation.model_dump(mode="json"))
                for citation in draft_response.citations
            )
        for answer in answers:
            citation_keys.update(self._citation_key(citation.model_dump(mode="json")) for citation in answer.citations)
        for citation in (export_payload or {}).get("citations", []):
            citation_keys.add(self._citation_key(citation))
        return len(citation_keys)

    def _citation_key(self, citation: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(citation.get("document_id", "")),
            str(citation.get("chunk_id", "")),
            str(citation.get("filename", "")),
        )

    def _red_team_pass(self, red_team_summary: dict[str, Any] | None) -> bool | None:
        if not red_team_summary:
            return None
        value = red_team_summary.get("passed")
        return bool(value) if value is not None else None

    def _customer_fit_score(
        self,
        customer_fit: CustomerFitResponse | None,
        export_payload: dict[str, Any] | None,
        readiness_scorecard: DealReadinessScorecardResponse | None,
    ) -> float | None:
        if customer_fit:
            return customer_fit.fit_score
        if readiness_scorecard and readiness_scorecard.customer_fit_score is not None:
            return readiness_scorecard.customer_fit_score
        fit = (export_payload or {}).get("customer_fit")
        return fit.get("fit_score") if fit else None

    def _task_counts(self, tasks: list[StakeholderTask], handoff_board: dict[str, Any] | None) -> dict[str, Any]:
        if not tasks and handoff_board:
            summary = handoff_board.get("summary", {})
            return {
                "total": summary.get("task_count", 0),
                "blocked": summary.get("blocked_tasks", 0),
                "by_owner": summary.get("task_counts_by_owner", {}),
                "by_status": summary.get("task_counts_by_status", {}),
            }
        return {
            "total": len(tasks),
            "blocked": sum(1 for task in tasks if task.status == "blocked"),
            "by_owner": dict(sorted(Counter(task.owner_role for task in tasks).items())),
            "by_status": dict(sorted(Counter(task.status for task in tasks).items())),
        }

    def _analysis_link(self, analysis: AnalyzeResponse | None) -> dict[str, Any]:
        if not analysis:
            return {"trace_id": None, "requirements": 0}
        return {
            "trace_id": analysis.trace_id,
            "requirements": len(analysis.requirements),
            "deadlines": analysis.deadlines,
            "missing_information": analysis.missing_information,
        }

    def _draft_link(self, draft_response: DraftResponse | None) -> dict[str, Any]:
        if not draft_response:
            return {"trace_id": None, "sections": 0, "citations": 0}
        return {
            "trace_id": draft_response.trace_id,
            "sections": len(draft_response.sections),
            "citations": len(draft_response.citations),
        }

    def _customer_fit_link(
        self,
        customer_fit: CustomerFitResponse | None,
        export_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if customer_fit:
            return {
                "trace_id": customer_fit.trace_id,
                "customer": customer_fit.customer_profile.name,
                "fit_score": customer_fit.fit_score,
                "profile_risks": len(customer_fit.profile_risks),
            }
        fit = (export_payload or {}).get("customer_fit")
        if not fit:
            return {"trace_id": None, "fit_score": None}
        profile = fit.get("customer_profile", {})
        return {
            "trace_id": fit.get("trace_id"),
            "customer": profile.get("name"),
            "fit_score": fit.get("fit_score"),
            "profile_risks": len(fit.get("profile_risks", [])),
        }

    def _readiness_link(self, readiness_scorecard: DealReadinessScorecardResponse | None) -> dict[str, Any]:
        if not readiness_scorecard:
            return {"trace_id": None, "readiness_score": None}
        return {
            "trace_id": readiness_scorecard.trace_id,
            "readiness_score": readiness_scorecard.readiness_score,
            "readiness_level": readiness_scorecard.readiness_level,
            "blockers": readiness_scorecard.blockers,
        }

    def _meeting_agenda(
        self,
        handoff_board: dict[str, Any] | None,
        readiness_scorecard: DealReadinessScorecardResponse | None,
    ) -> list[str]:
        if handoff_board and handoff_board.get("next_meeting_agenda"):
            return list(handoff_board["next_meeting_agenda"])
        if readiness_scorecard and readiness_scorecard.recommended_next_actions:
            return [
                "Confirm executive owner for each readiness blocker.",
                *readiness_scorecard.recommended_next_actions[:4],
            ]
        return [
            "Review evidence coverage, open risks, and owner assignments.",
            "Confirm submission recommendation and next executive approval step.",
        ]

    def _submission_recommendation(self, executive_report: ExecutiveRiskReportResponse | None) -> str | None:
        if not executive_report:
            return None
        return executive_report.report.get("submission_recommendation")

    def _render_markdown(self, brief: dict[str, Any]) -> str:
        metrics = brief["metrics"]
        links = brief["artifact_links"]
        lines = [
            "# Portfolio Demo Summary + RFP Leadership Brief",
            "",
            "## Executive Snapshot",
            "",
            f"- Docs ingested: {metrics['docs_ingested']}",
            f"- Requirements: {metrics['requirements']}",
            f"- Evidence coverage: {metrics['evidence_coverage']}",
            f"- Citations: {metrics['citations']}",
            f"- Red-team pass: {metrics['red_team_pass']}",
            f"- Customer fit score: {metrics['customer_fit_score']}",
            f"- Tasks: {metrics['task_counts']['total']} total / {metrics['task_counts']['blocked']} blocked",
            f"- Readiness score: {metrics['readiness_score']} ({metrics['readiness_level']})",
            "",
            "## Local Artifact Links",
            "",
            f"- RFP analysis trace: {links['rfp_analysis']['trace_id']}",
            f"- Requirement matrix rows: {links['requirement_matrix']['rows']}",
            f"- Draft response trace: {links['draft_response']['trace_id']}",
            f"- Export package: {links['export_package']['artifact_path']}",
            "- Review board: "
            f"passed={links['review_board']['passed']} findings={links['review_board']['finding_count']}",
            f"- Red team: passed={metrics['red_team_pass']}",
            f"- Customer fit: {links['customer_fit'].get('customer')} score={links['customer_fit'].get('fit_score')}",
            f"- Response memory matches: {links['response_memory']['match_count']}",
            f"- Action plan tasks: {links['action_plan']['task_count']}",
            f"- Handoff board: {links['handoff_board']['artifact_path']}",
            f"- Readiness scorecard trace: {links['readiness_scorecard']['trace_id']}",
            f"- Executive report: {links['executive_report']['artifact_path']}",
            "",
            "## Recommended Next Meeting Agenda",
            "",
        ]
        lines.extend(f"- {item}" for item in brief["recommended_next_meeting_agenda"])
        lines.extend(["", "## Portfolio Demo Story", ""])
        lines.extend(f"- {item}" for item in brief["portfolio_story"])
        if brief["recommended_next_actions"]:
            lines.extend(["", "## Recommended Next Actions", ""])
            lines.extend(f"- {item}" for item in brief["recommended_next_actions"])
        return "\n".join(lines).strip() + "\n"
