from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.core.config import Settings
from app.models.api import (
    SubmissionRegressionCheck,
    SubmissionRegressionRequest,
    SubmissionRegressionResponse,
)

if TYPE_CHECKING:
    from app.models.api import AnalyzeResponse
    from app.models.domain import RequirementMatrixRow
    from app.services.container import ServiceContainer


SAMPLE_DOCS = [
    ("acme_enterprise_rfp.md", "rfp"),
    ("prior_proposal.md", "proposal"),
    ("product_overview.md", "product"),
    ("security_policy.md", "security"),
    ("compliance_policy.md", "compliance"),
    ("pricing_notes.md", "pricing"),
    ("implementation_guide.md", "implementation"),
    ("dpa_privacy_policy.md", "privacy"),
    ("sla_support_policy.md", "support"),
    ("ai_governance_security.md", "security"),
    ("disaster_recovery_plan.md", "disaster_recovery"),
    ("customer_success_onboarding.md", "customer_success"),
]


class SubmissionRegressionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def run(
        self,
        container: ServiceContainer,
        payload: SubmissionRegressionRequest | None = None,
        trace_id: str | None = None,
    ) -> SubmissionRegressionResponse:
        request = payload or SubmissionRegressionRequest()
        suite_trace_id = trace_id or f"submission-regression-{uuid4().hex[:8]}"
        checks: list[SubmissionRegressionCheck] = []
        warnings: list[str] = []

        await self._ensure_sample_corpus(container)
        rfp_text = self._read_fixture(request.rfp_fixture_path)
        analysis = container.analysis.analyze(rfp_text, f"{suite_trace_id}-analysis")
        matrix = container.workbench.create_requirement_matrix(analysis)
        checks.append(
            self._check(
                "document_ingestion_analysis_coverage",
                len(container.repo.documents) >= len(SAMPLE_DOCS)
                and len(container.repo.chunks) >= len(SAMPLE_DOCS)
                and len(analysis.requirements) >= 6,
                len(analysis.requirements),
                {
                    "documents": len(container.repo.documents),
                    "chunks": len(container.repo.chunks),
                    "requirements": len(analysis.requirements),
                    "deadlines": analysis.deadlines,
                    "security_questions": len(analysis.security_questions),
                    "compliance_asks": len(analysis.compliance_asks),
                },
            )
        )

        evidence_backed_rows = sum(1 for row in matrix if row.evidence_refs)
        missing_rows = sum(1 for row in matrix if row.missing_evidence or not row.evidence_refs)
        checks.append(
            self._check(
                "requirement_matrix_evidence_coverage",
                bool(matrix) and evidence_backed_rows >= 1,
                evidence_backed_rows,
                {
                    "matrix_rows": len(matrix),
                    "evidence_backed_rows": evidence_backed_rows,
                    "missing_or_blocked_rows": missing_rows,
                    "statuses": self._counts(row.status for row in matrix),
                },
            )
        )

        supported_answer = await container.generation.answer_question(
            "What SSO and encryption controls are supported?",
            f"{suite_trace_id}-supported-answer",
            request.top_k,
        )
        missing_answer = await container.generation.answer_question(
            "Does the product include quantum-resistant satellite telemetry controls?",
            f"{suite_trace_id}-missing-answer",
            request.top_k,
        )
        checks.append(
            self._check(
                "cited_query_and_missing_evidence_behavior",
                bool(supported_answer.citations)
                and not supported_answer.missing_evidence
                and not missing_answer.citations
                and bool(missing_answer.missing_evidence),
                len(supported_answer.citations),
                {
                    "supported_citations": len(supported_answer.citations),
                    "supported_confidence": supported_answer.confidence,
                    "missing_citations": len(missing_answer.citations),
                    "missing_evidence_items": len(missing_answer.missing_evidence),
                },
            )
        )

        draft = await container.generation.draft_response(
            f"{suite_trace_id}-draft",
            requirement_ids=[requirement.id for requirement in analysis.requirements],
            top_k=5,
        )
        checks.append(
            self._check(
                "draft_response_sections",
                len(draft.sections) >= 4 and bool(draft.citations),
                len(draft.sections),
                {
                    "sections": [section.title for section in draft.sections],
                    "citations": len(draft.citations),
                    "assumptions": len(draft.assumptions),
                },
            )
        )

        supported_review = container.review_board.review_answer(
            supported_answer.question,
            supported_answer.answer_text,
            supported_answer.citations,
            supported_answer.missing_evidence,
            supported_answer.token_usage,
            f"{suite_trace_id}-supported-review",
        )
        missing_review = container.review_board.review_answer(
            missing_answer.question,
            "Yes, quantum-resistant satellite telemetry controls are fully supported.",
            missing_answer.citations,
            missing_answer.missing_evidence,
            missing_answer.token_usage,
            f"{suite_trace_id}-missing-review",
        )
        package_review = container.review_board.review_package(
            trace_id=f"{suite_trace_id}-package-review",
            requirement_matrix=matrix,
            draft_response=draft,
            answer_payloads=[supported_answer, missing_answer],
        )
        package_categories = {finding.category for finding in package_review.findings}
        missing_categories = {finding.category for finding in missing_review.findings}
        checks.append(
            self._check(
                "answer_review_package_review_status",
                supported_review.passed
                and not missing_review.passed
                and "missing_evidence" in missing_categories
                and "unsupported_claim" in missing_categories
                and "missing_evidence" in package_categories,
                len(package_review.findings),
                {
                    "supported_answer_review_passed": supported_review.passed,
                    "missing_answer_review_passed": missing_review.passed,
                    "missing_answer_categories": sorted(missing_categories),
                    "package_review_passed": package_review.passed,
                    "package_findings": len(package_review.findings),
                    "package_categories": sorted(package_categories),
                },
            )
        )

        customer_fit = container.customer_intelligence.customer_fit(
            request.customer_profile_id,
            f"{suite_trace_id}-customer-fit",
            analysis=analysis,
            requirement_matrix=matrix,
        )
        memory_matches = container.customer_intelligence.search_response_memory(
            "SSO encryption SOC 2 implementation pricing",
            f"{suite_trace_id}-response-memory",
            customer_profile_id=request.customer_profile_id,
            top_k=5,
        )
        checks.append(
            self._check(
                "customer_fit_response_memory_signals",
                customer_fit.fit_score > 0 and bool(memory_matches),
                len(memory_matches),
                {
                    "customer_profile": customer_fit.customer_profile.name,
                    "fit_score": customer_fit.fit_score,
                    "profile_risks": len(customer_fit.profile_risks),
                    "requirements_needing_review": len(customer_fit.requirements_needing_review),
                    "memory_matches": [match.title for match in memory_matches],
                },
            )
        )

        export = container.workbench.export_package(
            analysis,
            draft,
            f"{suite_trace_id}-export",
            write_artifact=request.write_artifacts,
            customer_fit=customer_fit,
            response_memory_matches=memory_matches,
        )
        action_plan, action_summary = container.action_plan.create_action_plan(
            trace_id=f"{suite_trace_id}-action-plan",
            analysis=analysis,
            requirement_matrix=matrix,
            customer_fit=customer_fit,
            review_findings=package_review.findings,
        )
        handoff = container.action_plan.export_handoff_board(
            trace_id=f"{suite_trace_id}-handoff",
            tasks=action_plan,
            analysis=analysis,
            requirement_matrix=matrix,
            customer_fit=customer_fit,
            review_findings=package_review.findings,
            write_artifact=request.write_artifacts,
        )
        checks.append(
            self._check(
                "action_plan_handoff_readiness",
                bool(action_plan)
                and action_summary["blocked_tasks"] >= 1
                and bool(handoff.board["blocked_items"])
                and bool(handoff.board["next_meeting_agenda"]),
                len(action_plan),
                {
                    "tasks": len(action_plan),
                    "blocked_tasks": action_summary["blocked_tasks"],
                    "handoff_blocked_items": len(handoff.board["blocked_items"]),
                    "handoff_artifact_path": handoff.artifact_path,
                },
            )
        )

        eval_metrics = await container.evaluation.run(
            request.eval_dataset_path,
            f"{suite_trace_id}-eval",
            request.top_k,
        )
        checks.append(
            self._check(
                "standard_eval_summary",
                eval_metrics.passed and eval_metrics.missing_evidence_detection_count >= 1,
                eval_metrics.question_count,
                eval_metrics.model_dump(mode="json", exclude={"details"}),
            )
        )

        red_team_summary = await self._run_red_team(
            container,
            request.red_team_dataset_path,
            f"{suite_trace_id}-red-team",
            request.top_k,
        )
        checks.append(
            self._check(
                "red_team_summary",
                bool(red_team_summary["passed"])
                and red_team_summary["missing_evidence_detection_count"]
                >= red_team_summary["expected_missing_evidence"],
                int(red_team_summary["question_count"]),
                {
                    "questions": red_team_summary["question_count"],
                    "expected_missing_evidence": red_team_summary["expected_missing_evidence"],
                    "missing_evidence_detection_count": red_team_summary["missing_evidence_detection_count"],
                    "review_finding_count": red_team_summary["review_finding_count"],
                    "passed": red_team_summary["passed"],
                },
            )
        )

        scorecard = container.deal_readiness.create_scorecard(
            trace_id=f"{suite_trace_id}-readiness",
            analysis=analysis,
            requirement_matrix=matrix,
            review_findings=package_review.findings,
            customer_fit=customer_fit,
            action_plan=action_plan,
            eval_metrics=eval_metrics,
        )
        executive_report = container.deal_readiness.export_executive_report(
            trace_id=f"{suite_trace_id}-executive-report",
            scorecard=scorecard,
            analysis=analysis,
            requirement_matrix=matrix,
            review_findings=package_review.findings,
            customer_fit=customer_fit,
            action_plan=action_plan,
            eval_metrics=eval_metrics,
            red_team_summary=red_team_summary,
            write_artifact=request.write_artifacts,
        )
        leadership_brief = container.leadership_brief.export_brief(
            trace_id=f"{suite_trace_id}-leadership-brief",
            documents_ingested=len(container.repo.documents),
            analysis=analysis,
            requirement_matrix=matrix,
            draft_response=draft,
            answers=[supported_answer, missing_answer],
            export_payload=export.package,
            export_artifact_path=export.artifact_path,
            export_json_artifact_path=export.json_artifact_path,
            review_findings=package_review.findings,
            review_passed=package_review.passed,
            customer_fit=customer_fit,
            response_memory_matches=memory_matches,
            action_plan=action_plan,
            handoff_board=handoff.board,
            handoff_artifact_path=handoff.artifact_path,
            handoff_json_artifact_path=handoff.json_artifact_path,
            readiness_scorecard=scorecard,
            executive_report=executive_report,
            eval_metrics=eval_metrics,
            red_team_summary=red_team_summary,
            write_artifact=request.write_artifacts,
        )
        submission_decision = container.submission_decision.create_decision(
            trace_id=f"{suite_trace_id}-submission-decision",
            requirement_matrix=matrix,
            draft_response=draft,
            answers=[supported_answer, missing_answer],
            review_findings=package_review.findings,
            review_passed=package_review.passed,
            action_plan=action_plan,
            readiness_scorecard=scorecard,
            eval_metrics=eval_metrics,
            red_team_summary=red_team_summary,
            leadership_brief=leadership_brief.brief,
            metrics=container.metrics.totals(),
            artifact_links={
                "export_package": {
                    "artifact_path": export.artifact_path,
                    "json_artifact_path": export.json_artifact_path,
                },
                "leadership_brief": {
                    "artifact_path": leadership_brief.artifact_path,
                    "json_artifact_path": leadership_brief.json_artifact_path,
                },
            },
        )
        submission_memo = container.submission_decision.export_memo(
            trace_id=f"{suite_trace_id}-executive-submission-memo",
            decision=submission_decision,
            write_artifact=request.write_artifacts,
        )
        checks.append(
            self._check(
                "readiness_scorecard_executive_risk_report_status",
                scorecard.readiness_score >= 0
                and bool(scorecard.readiness_level)
                and bool(executive_report.report["submission_recommendation"])
                and (not request.write_artifacts or bool(executive_report.artifact_path)),
                scorecard.readiness_score,
                {
                    "readiness_score": scorecard.readiness_score,
                    "readiness_level": scorecard.readiness_level,
                    "blockers": len(scorecard.blockers),
                    "executive_report_artifact_path": executive_report.artifact_path,
                    "submission_recommendation": executive_report.report["submission_recommendation"],
                },
            )
        )
        checks.append(
            self._check(
                "submission_decision_memo_status",
                submission_decision.decision in {"submit", "submit_with_exceptions", "do_not_submit"}
                and submission_decision.score >= 0
                and (not request.write_artifacts or bool(submission_memo.artifact_path)),
                submission_decision.score,
                {
                    "decision": submission_decision.decision,
                    "score": submission_decision.score,
                    "blocking_issues": len(submission_decision.blocking_issues),
                    "exceptions": len(submission_decision.exception_list),
                    "memo_artifact_path": submission_memo.artifact_path,
                },
            )
        )
        if scorecard.readiness_level != "ready":
            warnings.append(
                f"Sample deal readiness is {scorecard.readiness_level}; regression passes because missing-evidence "
                "and readiness risk are detected and carried into review artifacts."
            )

        usage_totals = container.metrics.totals()
        checks.append(
            self._check(
                "latency_token_cost_audit_metrics",
                int(usage_totals["request_count"]) >= 4
                and int(usage_totals["input_tokens"]) > 0
                and "average_latency_ms" in usage_totals,
                int(usage_totals["request_count"]),
                {
                    "usage_totals": usage_totals,
                    "audit_events": len(container.audit.list_events()),
                },
            )
        )

        failed_checks = [check.name for check in checks if not check.passed]
        evidence_counts = self._evidence_counts(
            analysis,
            matrix,
            supported_answer_citations=len(supported_answer.citations),
            missing_answer_evidence=len(missing_answer.missing_evidence),
            draft_sections=len(draft.sections),
            draft_citations=len(draft.citations),
            review_findings=len(package_review.findings),
            memory_matches=len(memory_matches),
            action_plan_tasks=len(action_plan),
            blocked_tasks=action_summary["blocked_tasks"],
            eval_questions=eval_metrics.question_count,
            red_team_questions=int(red_team_summary["question_count"]),
            readiness_score=scorecard.readiness_score,
            metrics_recorded=int(usage_totals["request_count"]),
            audit_events=len(container.audit.list_events()),
        )
        artifact_paths = {
            "export_markdown": export.artifact_path,
            "export_json": export.json_artifact_path,
            "handoff_markdown": handoff.artifact_path,
            "handoff_json": handoff.json_artifact_path,
            "executive_report_markdown": executive_report.artifact_path,
            "executive_report_json": executive_report.json_artifact_path,
            "leadership_brief_markdown": leadership_brief.artifact_path,
            "leadership_brief_json": leadership_brief.json_artifact_path,
            "submission_memo_markdown": submission_memo.artifact_path,
            "submission_memo_json": submission_memo.json_artifact_path,
        }
        summary = self._interview_summary(
            passed=not failed_checks,
            requirements=len(analysis.requirements),
            evidence_backed_rows=evidence_backed_rows,
            missing_rows=missing_rows,
            eval_passed=eval_metrics.passed,
            red_team_passed=bool(red_team_summary["passed"]),
            readiness_score=scorecard.readiness_score,
            readiness_level=scorecard.readiness_level,
            artifact_paths=artifact_paths,
        )
        return SubmissionRegressionResponse(
            passed=not failed_checks,
            checks=checks,
            evidence_counts=evidence_counts,
            failed_checks=failed_checks,
            warnings=warnings,
            artifact_paths=artifact_paths,
            eval_summary=eval_metrics,
            red_team_summary=red_team_summary,
            interview_ready_summary=summary,
            trace_id=suite_trace_id,
        )

    async def _ensure_sample_corpus(self, container: ServiceContainer) -> None:
        indexed = {
            (document.filename, document.document_type)
            for document in container.repo.documents.values()
            if document.source == "sample_data"
        }
        for filename, document_type in SAMPLE_DOCS:
            if (filename, document_type) in indexed:
                continue
            await container.ingestion.ingest_path(
                self.settings.sample_data_dir / filename,
                document_type=document_type,
                source="sample_data",
                tags=["sample", document_type],
            )

    def _read_fixture(self, fixture_path: str) -> str:
        path = Path(fixture_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            sample_path = self.settings.sample_data_dir / fixture_path
            if sample_path.exists():
                path = sample_path
        return path.read_text(encoding="utf-8")

    async def _run_red_team(
        self,
        container: ServiceContainer,
        dataset_path: str,
        trace_id: str,
        top_k: int,
    ) -> dict[str, Any]:
        path = Path(dataset_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        dataset = json.loads(path.read_text(encoding="utf-8"))
        details: list[dict[str, Any]] = []
        missing_detection_count = 0
        review_finding_count = 0
        for index, item in enumerate(dataset["questions"], start=1):
            answer = await container.generation.answer_question(item["question"], f"{trace_id}-{index}", top_k)
            report = container.review_board.review_answer(
                item["question"],
                answer.answer_text,
                answer.citations,
                answer.missing_evidence,
                answer.token_usage,
                f"{trace_id}-review-{index}",
            )
            actual_categories = {finding.category for finding in report.findings}
            expected_categories = set(item.get("expected_review_categories", []))
            detected_missing = bool(answer.missing_evidence) or "missing_evidence" in actual_categories
            if item.get("expect_missing_evidence") and detected_missing:
                missing_detection_count += 1
            review_finding_count += len(report.findings)
            category_pass = expected_categories.issubset(actual_categories)
            missing_pass = not item.get("expect_missing_evidence") or detected_missing
            details.append(
                {
                    "question": item["question"],
                    "risk_type": item.get("risk_type", "unknown"),
                    "citation_count": len(answer.citations),
                    "missing_evidence_detected": detected_missing,
                    "review_ready": report.passed,
                    "review_categories": sorted(actual_categories),
                    "finding_count": len(report.findings),
                    "passed": category_pass and missing_pass,
                }
            )
        expected_missing = sum(1 for item in dataset["questions"] if item.get("expect_missing_evidence"))
        return {
            "question_count": len(dataset["questions"]),
            "expected_missing_evidence": expected_missing,
            "missing_evidence_detection_count": missing_detection_count,
            "review_finding_count": review_finding_count,
            "passed": all(detail["passed"] for detail in details),
            "details": details,
        }

    def _check(
        self,
        name: str,
        passed: bool,
        evidence_count: int | float,
        details: dict[str, Any],
    ) -> SubmissionRegressionCheck:
        return SubmissionRegressionCheck(
            name=name,
            passed=passed,
            evidence_count=int(evidence_count),
            details=details,
        )

    def _evidence_counts(
        self,
        analysis: AnalyzeResponse,
        matrix: list[RequirementMatrixRow],
        **counts: int,
    ) -> dict[str, int | float | bool | str | None]:
        return {
            "documents": len(SAMPLE_DOCS),
            "requirements": len(analysis.requirements),
            "deadlines": len(analysis.deadlines),
            "security_questions": len(analysis.security_questions),
            "compliance_asks": len(analysis.compliance_asks),
            "matrix_rows": len(matrix),
            "matrix_evidence_refs": sum(len(row.evidence_refs) for row in matrix),
            "matrix_missing_evidence_rows": sum(1 for row in matrix if row.missing_evidence or not row.evidence_refs),
            **counts,
        }

    def _counts(self, values: Any) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in values:
            counts[str(value)] = counts.get(str(value), 0) + 1
        return counts

    def _interview_summary(
        self,
        passed: bool,
        requirements: int,
        evidence_backed_rows: int,
        missing_rows: int,
        eval_passed: bool,
        red_team_passed: bool,
        readiness_score: int,
        readiness_level: str,
        artifact_paths: dict[str, str | None],
    ) -> str:
        gate = "PASS" if passed else "FAIL"
        report_path = artifact_paths.get("executive_report_markdown") or "not written"
        return (
            f"Submission regression {gate}: analyzed {requirements} requirements, found "
            f"{evidence_backed_rows} evidence-backed rows, preserved {missing_rows} missing-evidence risk rows, "
            f"standard eval pass={eval_passed}, red-team pass={red_team_passed}, and produced a "
            f"{readiness_score}/{readiness_level} readiness view. Executive artifact: {report_path}."
        )
