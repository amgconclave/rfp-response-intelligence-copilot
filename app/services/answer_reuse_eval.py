from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    AnswerReuseEvalPackResponse,
    AnswerReuseEvalResponse,
    AnswerReuseSnippet,
)
from app.services.answer_reuse_drift import AnswerReuseDriftService
from app.services.answer_reuse_library import AnswerReuseLibraryService


class AnswerReuseEvalService:
    def __init__(
        self,
        settings: Settings,
        answer_reuse_library: AnswerReuseLibraryService,
        answer_reuse_drift: AnswerReuseDriftService,
    ) -> None:
        self.settings = settings
        self.answer_reuse_library = answer_reuse_library
        self.answer_reuse_drift = answer_reuse_drift

    def evaluate(
        self,
        trace_id: str,
        category: str | None = None,
        customer_profile_id: str | None = None,
        include_expired: bool = True,
        min_source_overlap: int = 4,
        policy_thresholds: list[int] | None = None,
    ) -> AnswerReuseEvalResponse:
        thresholds = self._thresholds(policy_thresholds, min_source_overlap)
        library = self.answer_reuse_library.library(
            f"{trace_id}-library",
            category=category,
            customer_profile_id=customer_profile_id,
            include_expired=include_expired,
        )
        eval_cases = [self._eval_case(snippet, min_source_overlap) for snippet in library.snippets]
        comparison = [
            self._experiment_row(
                trace_id,
                threshold,
                category=category,
                customer_profile_id=customer_profile_id,
                include_expired=include_expired,
            )
            for threshold in thresholds
        ]
        summary = self._summary(eval_cases, comparison, min_source_overlap)
        return AnswerReuseEvalResponse(
            title="Answer Reuse Evaluation Pack",
            status="pass" if summary["failed_case_count"] == 0 else "needs_review",
            summary=summary,
            eval_cases=eval_cases,
            experiment_comparison=comparison,
            trace_spans=self._trace_spans(trace_id, eval_cases, comparison),
            owner_queue=self._owner_queue(eval_cases, comparison, summary["recommended_threshold"]),
            workflow=self._workflow(summary),
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        evaluation: AnswerReuseEvalResponse | None = None,
        category: str | None = None,
        customer_profile_id: str | None = None,
        include_expired: bool = True,
        min_source_overlap: int = 4,
        policy_thresholds: list[int] | None = None,
        write_artifact: bool = True,
    ) -> AnswerReuseEvalPackResponse:
        evaluation = evaluation or self.evaluate(
            f"{trace_id}-eval",
            category=category,
            customer_profile_id=customer_profile_id,
            include_expired=include_expired,
            min_source_overlap=min_source_overlap,
            policy_thresholds=policy_thresholds,
        )
        pack = self._pack_payload(trace_id, evaluation)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "answer_reuse_evals"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"answer_reuse_eval_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"answer_reuse_eval_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["answer_reuse_eval_markdown"] = artifact_path
            pack["artifact_paths"]["answer_reuse_eval_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return AnswerReuseEvalPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            evaluation=evaluation,
            trace_id=trace_id,
        )

    def _eval_case(self, snippet: AnswerReuseSnippet, min_source_overlap: int) -> dict[str, Any]:
        verified_lineage = sum(
            1 for lineage in snippet.citation_lineage if lineage["lineage_status"] == "verified"
        )
        lineage_issue_count = len(snippet.citation_lineage) - verified_lineage
        expected_decision = self._expected_decision(snippet, min_source_overlap)
        checks = {
            "owner_present": bool(snippet.owner),
            "expiry_present": bool(snippet.expires_at),
            "citation_present": bool(snippet.citation_refs),
            "lineage_verified_for_auto_reuse": (
                snippet.reuse_decision != "approved_for_reuse" or lineage_issue_count == 0
            ),
            "source_overlap_meets_threshold": all(
                lineage["evidence_overlap"] >= min_source_overlap
                for lineage in snippet.citation_lineage
                if lineage["lineage_status"] == "verified"
            ),
            "decision_matches_policy": snippet.reuse_decision == expected_decision,
        }
        status = "pass" if all(checks.values()) else "review"
        return {
            "case_id": f"answer-reuse-eval:{snippet.snippet_id}",
            "snippet_id": snippet.snippet_id,
            "title": snippet.title,
            "category": snippet.category,
            "owner": snippet.owner,
            "expected_decision": expected_decision,
            "actual_decision": snippet.reuse_decision,
            "status": status,
            "score": self._case_score(checks, snippet.confidence),
            "checks": checks,
            "min_source_overlap": min_source_overlap,
            "verified_lineage_count": verified_lineage,
            "lineage_issue_count": lineage_issue_count,
            "citation_refs": snippet.citation_refs,
            "recommended_action": self._case_action(snippet, checks),
        }

    def _expected_decision(self, snippet: AnswerReuseSnippet, min_source_overlap: int) -> str:
        if snippet.approval_status not in {"accepted", "approved"} or snippet.expiry_status in {
            "expired",
            "invalid_expiry",
        }:
            return "blocked"
        if snippet.expiry_status in {"renewal_due", "renewal_watch"}:
            return "review_before_reuse"
        if any(lineage["lineage_status"] != "verified" for lineage in snippet.citation_lineage):
            return "review_before_reuse"
        if any(lineage["evidence_overlap"] < min_source_overlap for lineage in snippet.citation_lineage):
            return "review_before_reuse"
        return "approved_for_reuse"

    def _case_score(self, checks: dict[str, bool], confidence: float) -> int:
        base = round(confidence * 100)
        penalty = sum(10 for passed in checks.values() if not passed)
        return max(0, min(100, base - penalty))

    def _case_action(self, snippet: AnswerReuseSnippet, checks: dict[str, bool]) -> str:
        failed = [key for key, passed in checks.items() if not passed]
        if not failed:
            return "Keep snippet eligible for governed reuse under the current policy."
        if "source_overlap_meets_threshold" in failed or "lineage_verified_for_auto_reuse" in failed:
            return f"{snippet.owner} should refresh cited source evidence before broad reuse."
        if "decision_matches_policy" in failed:
            return f"{snippet.owner} should reconcile policy decision and eval expectation."
        return f"{snippet.owner} should complete missing governance metadata before reuse."

    def _experiment_row(
        self,
        trace_id: str,
        threshold: int,
        category: str | None,
        customer_profile_id: str | None,
        include_expired: bool,
    ) -> dict[str, Any]:
        drift = self.answer_reuse_drift.drift_report(
            f"{trace_id}-threshold-{threshold}",
            category=category,
            customer_profile_id=customer_profile_id,
            include_expired=include_expired,
            min_source_overlap=threshold,
        )
        findings = drift.findings
        stable = sum(1 for finding in findings if finding.drift_status == "stable")
        review = sum(1 for finding in findings if finding.drift_status in {"watch", "owner_review"})
        rewrite = sum(1 for finding in findings if finding.drift_status == "retire_or_rewrite")
        score = round((stable * 100 + review * 60) / max(1, len(findings)) - rewrite * 8, 2)
        return {
            "policy_name": f"source-overlap-{threshold}",
            "min_source_overlap": threshold,
            "snippet_count": len(findings),
            "stable_count": stable,
            "review_count": review,
            "rewrite_count": rewrite,
            "average_drift_score": drift.summary["average_drift_score"],
            "policy_score": max(0, min(100, score)),
            "recommended": False,
            "tradeoff": self._tradeoff(threshold, stable, review, rewrite),
        }

    def _tradeoff(self, threshold: int, stable: int, review: int, rewrite: int) -> str:
        if rewrite:
            return f"Threshold {threshold} catches high-risk stale evidence but creates rewrite work."
        if review:
            return f"Threshold {threshold} keeps reuse available while routing weak evidence to owners."
        return f"Threshold {threshold} allows all evaluated snippets to remain stable."

    def _summary(
        self,
        eval_cases: list[dict[str, Any]],
        comparison: list[dict[str, Any]],
        selected_threshold: int,
    ) -> dict[str, Any]:
        decisions = Counter(case["actual_decision"] for case in eval_cases)
        statuses = Counter(case["status"] for case in eval_cases)
        recommended = max(
            comparison,
            key=lambda row: (row["policy_score"], -row["rewrite_count"], row["min_source_overlap"]),
        )
        for row in comparison:
            row["recommended"] = row["min_source_overlap"] == recommended["min_source_overlap"]
        pass_count = statuses.get("pass", 0)
        case_count = len(eval_cases)
        return {
            "case_count": case_count,
            "passed_case_count": pass_count,
            "failed_case_count": case_count - pass_count,
            "pass_rate": round(pass_count / max(1, case_count), 3),
            "average_case_score": round(
                sum(case["score"] for case in eval_cases) / max(1, case_count),
                2,
            ),
            "selected_threshold": selected_threshold,
            "recommended_threshold": recommended["min_source_overlap"],
            "recommended_policy_score": recommended["policy_score"],
            "decision_counts": dict(sorted(decisions.items())),
            "policy_count": len(comparison),
        }

    def _trace_spans(
        self,
        trace_id: str,
        eval_cases: list[dict[str, Any]],
        comparison: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        spans = [
            {
                "span_id": f"{trace_id}:dataset",
                "name": "compile_answer_reuse_eval_dataset",
                "status": "pass",
                "case_count": len(eval_cases),
                "pattern": "eval_dataset",
            },
            {
                "span_id": f"{trace_id}:experiment-comparison",
                "name": "compare_answer_reuse_thresholds",
                "status": "pass",
                "policy_count": len(comparison),
                "pattern": "experiment_comparison",
            },
        ]
        spans.extend(
            {
                "span_id": f"{trace_id}:{case['snippet_id']}",
                "name": "answer_reuse_case_trace",
                "status": case["status"],
                "snippet_id": case["snippet_id"],
                "score": case["score"],
                "pattern": "trace_analysis",
            }
            for case in eval_cases
        )
        return spans

    def _owner_queue(
        self,
        eval_cases: list[dict[str, Any]],
        comparison: list[dict[str, Any]],
        recommended_threshold: int,
    ) -> list[dict[str, Any]]:
        queue = [
            {
                "owner": case["owner"],
                "snippet_id": case["snippet_id"],
                "title": case["title"],
                "status": case["status"],
                "score": case["score"],
                "required_action": case["recommended_action"],
            }
            for case in eval_cases
            if case["status"] != "pass"
        ]
        if comparison and recommended_threshold != comparison[0]["min_source_overlap"]:
            queue.append(
                {
                    "owner": "proposal_manager",
                    "snippet_id": "policy-threshold",
                    "title": "Answer reuse source-overlap threshold",
                    "status": "review",
                    "score": 0,
                    "required_action": (
                        f"Review changing min_source_overlap to {recommended_threshold} before rollout."
                    ),
                }
            )
        return sorted(queue, key=lambda item: (item["owner"], item["snippet_id"]))

    def _workflow(self, summary: dict[str, Any]) -> dict[str, Any]:
        return {
            "pattern": "eval_dataset_experiment_comparison_trace_analysis",
            "states": [
                "compile_eval_cases",
                "score_governance_checks",
                "compare_policy_thresholds",
                "route_owner_review",
            ],
            "selected_threshold": summary["selected_threshold"],
            "recommended_threshold": summary["recommended_threshold"],
            "release_gate": "pass" if summary["failed_case_count"] == 0 else "human_review_required",
        }

    def _pack_payload(self, trace_id: str, evaluation: AnswerReuseEvalResponse) -> dict[str, Any]:
        return {
            "title": "Answer Reuse Evaluation Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "trace_id": trace_id,
            "evaluation": evaluation.model_dump(mode="json"),
            "governance_controls": [
                "Treat reusable-answer policy changes as evaluated experiments, not silent defaults.",
                "Require owner action for failed eval cases before broad customer-facing reuse.",
                "Keep trace spans, case scores, and threshold comparisons with the generated artifact.",
            ],
            "reviewer_checklist": [
                "Inspect failed cases and source-overlap evidence.",
                "Compare recommended threshold with current threshold and document rollout decision.",
                "Run the standard eval and red-team commands after approving reuse policy changes.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        evaluation = pack["evaluation"]
        summary = evaluation["summary"]
        lines = [
            f"# {pack['title']}",
            "",
            f"- Generated at: {pack['generated_at']}",
            f"- Trace ID: {pack['trace_id']}",
            f"- Status: {evaluation['status']}",
            f"- Eval cases: {summary['case_count']}",
            f"- Pass rate: {summary['pass_rate']}",
            f"- Recommended threshold: {summary['recommended_threshold']}",
            "",
            "## Eval Cases",
            "",
            "| Case | Snippet | Owner | Status | Score | Expected | Actual |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for case in evaluation["eval_cases"]:
            lines.append(
                "| "
                f"{self._md(case['case_id'])} | "
                f"{self._md(case['title'])} | "
                f"{self._md(case['owner'])} | "
                f"{self._md(case['status'])} | "
                f"{case['score']} | "
                f"{self._md(case['expected_decision'])} | "
                f"{self._md(case['actual_decision'])} |"
            )
        lines.extend(["", "## Experiment Comparison", ""])
        lines.append("| Policy | Threshold | Score | Stable | Review | Rewrite | Recommended |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for row in evaluation["experiment_comparison"]:
            lines.append(
                "| "
                f"{self._md(row['policy_name'])} | "
                f"{row['min_source_overlap']} | "
                f"{row['policy_score']} | "
                f"{row['stable_count']} | "
                f"{row['review_count']} | "
                f"{row['rewrite_count']} | "
                f"{row['recommended']} |"
            )
        lines.extend(["", "## Owner Queue", ""])
        if evaluation["owner_queue"]:
            lines.extend(
                f"- {item['owner']} / {item['snippet_id']}: {item['required_action']}"
                for item in evaluation["owner_queue"]
            )
        else:
            lines.append("- No owner review required.")
        lines.extend(["", "## Governance Controls", ""])
        lines.extend(f"- {item}" for item in pack["governance_controls"])
        lines.extend(["", "## Reviewer Checklist", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_checklist"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"- `{command}`" for command in evaluation["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in evaluation["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Artifact Paths", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _thresholds(self, policy_thresholds: list[int] | None, min_source_overlap: int) -> list[int]:
        raw_thresholds = policy_thresholds or [2, min_source_overlap, 6]
        raw_thresholds.append(min_source_overlap)
        return sorted({max(1, min(12, threshold)) for threshold in raw_thresholds})

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {
                "method": "POST",
                "path": "/rfp/answer-reuse-eval",
                "purpose": "Score reusable-answer governance eval cases and compare threshold policies.",
            },
            {
                "method": "POST",
                "path": "/rfp/answer-reuse-eval-pack",
                "purpose": "Write Markdown/JSON reusable-answer evaluation artifacts.",
                "expected_artifacts": ["storage/answer_reuse_evals/*.md", "storage/answer_reuse_evals/*.json"],
            },
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/answer-reuse-eval" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" '
                '-d "{\\"customer_profile_id\\":\\"regulated_healthcare\\",\\"min_source_overlap\\":4}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/answer-reuse-eval-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'rg "answer-reuse-eval|Answer Reuse Evaluation|answer_reuse_evals" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\answer_reuse_evals -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Eval cases are deterministic checks over local sample accepted-answer fixtures.",
            "Experiment comparison scores policy thresholds; it does not mutate production defaults.",
            "Trace spans are local diagnostics, not an external observability backend export.",
        ]

    def _md(self, value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")
