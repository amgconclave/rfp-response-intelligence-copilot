from __future__ import annotations

import json
import re
from typing import Any

from app.core.config import Settings
from app.models.api import DemoScriptResponse, SubmissionRegressionResponse


class DemoScriptService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(
        self,
        trace_id: str,
        regression: SubmissionRegressionResponse,
        write_artifact: bool = True,
    ) -> DemoScriptResponse:
        script = self._script_payload(trace_id, regression)
        markdown = self._render_markdown(script)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            script_dir = self.settings.storage_dir / "demo_scripts"
            script_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = script_dir / f"interview_demo_script_{safe_trace_id}.md"
            json_path = script_dir / f"interview_demo_script_{safe_trace_id}.json"
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(script, indent=2), encoding="utf-8")
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
        return DemoScriptResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            script=script,
            trace_id=trace_id,
        )

    def _script_payload(self, trace_id: str, regression: SubmissionRegressionResponse) -> dict[str, Any]:
        metrics = regression.evidence_counts
        artifact_paths = regression.artifact_paths
        endpoints = [
            "POST /documents/ingest",
            "POST /rfp/analyze",
            "POST /rfp/requirement-matrix",
            "POST /rfp/query",
            "POST /rfp/draft-response",
            "POST /rfp/review-answer",
            "POST /rfp/review-package",
            "POST /rfp/customer-fit",
            "POST /rfp/response-memory/search",
            "POST /rfp/action-plan",
            "POST /rfp/handoff-board",
            "POST /rfp/evaluate",
            "POST /rfp/readiness-scorecard",
            "POST /rfp/executive-risk-report",
            "POST /rfp/leadership-brief",
            "POST /rfp/timeline-plan",
            "POST /rfp/submission-calendar-pack",
            "POST /rfp/submission-regression",
            "POST /rfp/demo-script",
        ]
        sample_outputs = {
            "regression_passed": regression.passed,
            "failed_checks": regression.failed_checks,
            "requirements": metrics.get("requirements"),
            "evidence_backed_rows": metrics.get("matrix_evidence_refs"),
            "missing_evidence_rows": metrics.get("matrix_missing_evidence_rows"),
            "standard_eval": regression.eval_summary.model_dump(mode="json", exclude={"details"}),
            "red_team": {
                "passed": regression.red_team_summary.get("passed"),
                "missing_evidence_detection_count": regression.red_team_summary.get(
                    "missing_evidence_detection_count"
                ),
                "expected_missing_evidence": regression.red_team_summary.get("expected_missing_evidence"),
            },
            "usage": {
                "metrics_recorded": metrics.get("metrics_recorded"),
                "audit_events": metrics.get("audit_events"),
            },
            "artifacts": artifact_paths,
        }
        return {
            "trace_id": trace_id,
            "title": "RFP Response Intelligence Copilot Interview Demo Script",
            "business_pain": [
                "Enterprise RFP teams need fast answers but cannot submit unsupported GenAI claims.",
                "Security, legal, sales, and solutions teams need an auditable handoff with clear owners.",
                "Interviewers need to see local deterministic behavior, not a demo that depends on live cloud keys.",
            ],
            "architecture_walkthrough": [
                "FastAPI exposes local-first workflow endpoints with API-key auth and trace IDs.",
                (
                    "Document ingestion chunks Markdown/TXT/PDF samples and stores them in an in-memory "
                    "repository plus a local vector adapter."
                ),
                (
                    "Mock LLM and retrieval services produce deterministic answers, drafts, citations, latency, "
                    "token, and cost metrics."
                ),
                (
                    "Workbench, review, customer intelligence, action plan, readiness, and leadership brief "
                    "services compose typed Pydantic artifacts."
                ),
                "Azure/OpenAI providers remain optional adapters; the regression suite stays mock/local by default.",
            ],
            "exact_local_commands": [
                "python -m uvicorn app.main:app --reload",
                "streamlit run dashboard/app.py",
                "python -m app.demo",
                "python -m pytest -q",
                "python -m ruff check .",
                "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
                "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
                (
                    'curl -X POST "http://127.0.0.1:8000/rfp/submission-regression" '
                    '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
                ),
                (
                    'curl -X POST "http://127.0.0.1:8000/rfp/demo-script" '
                    '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
                ),
                (
                    'curl -X POST "http://127.0.0.1:8000/rfp/submission-calendar-pack" '
                    '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
                ),
            ],
            "endpoints_exercised": endpoints,
            "sample_outputs_metrics": sample_outputs,
            "jd_skills_demonstrated": [
                "Agentic AI workflow orchestration with deterministic local tools and safety checks.",
                "RAG grounding, citation coverage, missing-evidence detection, and review-board guardrails.",
                "Typed FastAPI and Pydantic service design with testable dependency boundaries.",
                "Evaluation, red-team testing, telemetry, audit logging, and cost/latency reporting.",
                "Enterprise handoff, timeline, and calendar-pack artifacts for response-team execution.",
            ],
            "interviewer_talking_points": [
                "The system is local/mock by default, so the readiness gate is reproducible without cloud credentials.",
                "Unsupported answers are not hidden; they become review findings, tasks, blockers, and executive risk.",
                "Every generated artifact has a traceable service path from ingestion through citations and review.",
                "The suite demonstrates both happy-path answering and adversarial missing-evidence behavior.",
                "Optional Azure/OpenAI adapters can replace mock providers without changing the workflow contract.",
            ],
            "artifact_paths": artifact_paths,
            "interview_ready_summary": regression.interview_ready_summary,
        }

    def _render_markdown(self, script: dict[str, Any]) -> str:
        lines = [
            "# RFP Response Intelligence Copilot Interview Demo Script",
            "",
            "## Business Pain",
            "",
            *[f"- {item}" for item in script["business_pain"]],
            "",
            "## Architecture Walk-Through",
            "",
            *[f"- {item}" for item in script["architecture_walkthrough"]],
            "",
            "## Exact Local Commands",
            "",
        ]
        lines.extend(f"```bash\n{command}\n```" for command in script["exact_local_commands"])
        lines.extend(
            [
                "",
                "## Endpoints Exercised",
                "",
                *[f"- {endpoint}" for endpoint in script["endpoints_exercised"]],
                "",
                "## Sample Outputs and Metrics",
                "",
            ]
        )
        sample_outputs = script["sample_outputs_metrics"]
        lines.extend(
            [
                f"- Regression passed: {sample_outputs['regression_passed']}",
                f"- Failed checks: {sample_outputs['failed_checks']}",
                f"- Requirements: {sample_outputs['requirements']}",
                f"- Evidence refs: {sample_outputs['evidence_backed_rows']}",
                f"- Missing-evidence rows: {sample_outputs['missing_evidence_rows']}",
                f"- Eval passed: {sample_outputs['standard_eval']['passed']}",
                f"- Eval precision@k: {sample_outputs['standard_eval']['retrieval_precision_at_k']}",
                f"- Citation coverage: {sample_outputs['standard_eval']['citation_coverage']}",
                f"- Red-team passed: {sample_outputs['red_team']['passed']}",
                "- Red-team missing evidence: "
                f"{sample_outputs['red_team']['missing_evidence_detection_count']}/"
                f"{sample_outputs['red_team']['expected_missing_evidence']}",
                f"- Metrics recorded: {sample_outputs['usage']['metrics_recorded']}",
                f"- Audit events: {sample_outputs['usage']['audit_events']}",
                "",
                "## JD Skills Demonstrated",
                "",
                *[f"- {item}" for item in script["jd_skills_demonstrated"]],
                "",
                "## Five Interviewer Talking Points",
                "",
                *[f"- {item}" for item in script["interviewer_talking_points"]],
                "",
                "## Artifact Paths",
                "",
            ]
        )
        for label, path in script["artifact_paths"].items():
            lines.append(f"- {label}: {path}")
        lines.extend(["", "## Close", "", script["interview_ready_summary"]])
        return "\n".join(lines).strip() + "\n"
