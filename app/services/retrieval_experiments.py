from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.models.api import (
    RetrievalExperimentPackResponse,
    RetrievalExperimentResponse,
    WinLossLearningResponse,
)
from app.models.domain import Citation
from app.services.retrieval import RetrievalService
from app.services.win_loss_learning import WinLossLearningService


class RetrievalExperimentComparisonService:
    def __init__(
        self,
        settings: Settings,
        retrieval: RetrievalService,
        win_loss_learning: WinLossLearningService,
    ) -> None:
        self.settings = settings
        self.retrieval = retrieval
        self.win_loss_learning = win_loss_learning

    async def compare(
        self,
        trace_id: str,
        dataset_path: str = "sample_data/eval_dataset.json",
        outcomes_fixture_path: str = "sample_data/rfp_outcomes.json",
        top_k: int = 4,
        policy_ids: list[str] | None = None,
    ) -> RetrievalExperimentResponse:
        questions = self._load_questions(dataset_path)
        learning = self.win_loss_learning.learn(
            trace_id=f"{trace_id}-win-loss",
            outcomes_fixture_path=outcomes_fixture_path,
            top_k_patterns=6,
        )
        policies = self._policies(policy_ids)
        diagnostics: list[dict[str, Any]] = []
        trace_spans: list[dict[str, Any]] = []
        policy_rows: list[dict[str, Any]] = []
        top_k = max(1, min(10, top_k))

        for policy in policies:
            started = time.perf_counter()
            policy_diagnostics = []
            for index, item in enumerate(questions, start=1):
                question_start = time.perf_counter()
                candidates = await self.retrieval.search(item["question"], top_k=top_k + 4, min_score=0.0)
                selected, guardrails = self._apply_policy(policy["policy_id"], item, candidates, learning, top_k)
                latency_ms = (time.perf_counter() - question_start) * 1000
                diagnostic = self._diagnostic_row(policy, item, index, candidates, selected, guardrails, latency_ms)
                policy_diagnostics.append(diagnostic)
                diagnostics.append(diagnostic)
            elapsed_ms = (time.perf_counter() - started) * 1000
            result = self._policy_result(policy, policy_diagnostics, elapsed_ms)
            policy_rows.append(result)
            trace_spans.append(
                {
                    "span_id": f"{trace_id}-{policy['policy_id']}",
                    "name": "retrieval_policy_experiment",
                    "policy_id": policy["policy_id"],
                    "dataset_path": dataset_path,
                    "question_count": len(questions),
                    "duration_ms": round(elapsed_ms, 2),
                    "attributes": {
                        "patterns": policy["patterns"],
                        "top_k": top_k,
                        "unsupported_risk_count": result["unsupported_risk_count"],
                        "missing_evidence_hits": result["missing_evidence_hits"],
                    },
                }
            )

        recommended = self._recommended_policy(policy_rows)
        governance = self._governance_decision(recommended, policy_rows)
        return RetrievalExperimentResponse(
            title="Retrieval Experiment Comparison",
            status=governance["status"],
            recommended_policy_id=recommended["policy_id"],
            summary={
                "dataset_path": dataset_path,
                "question_count": len(questions),
                "top_k": top_k,
                "policy_count": len(policy_rows),
                "radar_patterns_used": ["retrieval diagnostics", "experiment comparison", "governance"],
                "recommended_score": recommended["experiment_score"],
                "baseline_score": next(
                    (row["experiment_score"] for row in policy_rows if row["policy_id"] == "baseline"),
                    None,
                ),
            },
            policy_results=policy_rows,
            question_diagnostics=diagnostics,
            trace_spans=trace_spans,
            governance_decision=governance,
            local_proof_commands=self._local_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    async def experiment_pack(
        self,
        trace_id: str,
        comparison: RetrievalExperimentResponse | None = None,
        dataset_path: str = "sample_data/eval_dataset.json",
        outcomes_fixture_path: str = "sample_data/rfp_outcomes.json",
        top_k: int = 4,
        policy_ids: list[str] | None = None,
        write_artifact: bool = True,
    ) -> RetrievalExperimentPackResponse:
        comparison = comparison or await self.compare(
            trace_id=f"{trace_id}-comparison",
            dataset_path=dataset_path,
            outcomes_fixture_path=outcomes_fixture_path,
            top_k=top_k,
            policy_ids=policy_ids,
        )
        pack = self._pack_payload(trace_id, comparison)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "retrieval_experiments"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"retrieval_experiment_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"retrieval_experiment_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["retrieval_experiment_markdown"] = artifact_path
            pack["artifact_paths"]["retrieval_experiment_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return RetrievalExperimentPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            comparison=comparison,
            trace_id=trace_id,
        )

    def _load_questions(self, dataset_path: str) -> list[dict[str, Any]]:
        path = Path(dataset_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            sample_path = self.settings.sample_data_dir / Path(dataset_path).name
            if sample_path.exists():
                path = sample_path
        if not path.exists():
            raise FileNotFoundError(f"Retrieval experiment dataset not found: {dataset_path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return list(payload.get("questions", []))

    def _policies(self, policy_ids: list[str] | None) -> list[dict[str, Any]]:
        defaults = [
            {
                "policy_id": "baseline",
                "label": "Baseline vector retrieval",
                "patterns": ["retrieval diagnostics"],
            },
            {
                "policy_id": "win_loss_source_boost",
                "label": "Win/loss source boost",
                "patterns": ["retrieval diagnostics", "experiment comparison"],
            },
            {
                "policy_id": "gap_guarded",
                "label": "Loss-gap guardrails",
                "patterns": ["retrieval diagnostics", "governance"],
            },
            {
                "policy_id": "balanced_governed",
                "label": "Balanced governed retrieval",
                "patterns": ["retrieval diagnostics", "experiment comparison", "governance"],
            },
        ]
        requested = set(policy_ids or [])
        return [policy for policy in defaults if not requested or policy["policy_id"] in requested] or defaults

    def _apply_policy(
        self,
        policy_id: str,
        item: dict[str, Any],
        candidates: list[Citation],
        learning: WinLossLearningResponse,
        top_k: int,
    ) -> tuple[list[Citation], list[str]]:
        guardrails = []
        if policy_id == "baseline":
            return candidates[:top_k], guardrails
        if policy_id == "win_loss_source_boost":
            return self._boosted(candidates, item, learning)[:top_k], ["win_loss_source_boost"]
        if policy_id == "gap_guarded":
            if self._should_guard(item, candidates, learning):
                return [], ["loss_gap_guardrail", "human_review_required"]
            return candidates[:top_k], guardrails
        if policy_id == "balanced_governed":
            boosted = self._boosted(candidates, item, learning)
            if self._should_guard(item, boosted, learning):
                return [], ["loss_gap_guardrail", "human_review_required"]
            return boosted[:top_k], ["win_loss_source_boost", "source_rank_experiment"]
        return candidates[:top_k], guardrails

    def _boosted(
        self,
        candidates: list[Citation],
        item: dict[str, Any],
        learning: WinLossLearningResponse,
    ) -> list[Citation]:
        winning_sources = {
            str(pattern["source"])
            for pattern in learning.winning_evidence_patterns
            if pattern.get("source")
        }
        category_terms = {
            str(pattern["category"]): set(pattern.get("query_expansion_terms", []))
            for pattern in learning.retrieval_recommendations
            if pattern.get("type") == "source_boost"
        }
        question_terms = set(self._tokens(item["question"]))

        def rank(citation: Citation) -> tuple[float, float, str]:
            source_boost = 0.12 if citation.filename in winning_sources else 0.0
            category_boost = 0.0
            for terms in category_terms.values():
                if terms.intersection(question_terms):
                    category_boost = max(category_boost, 0.04)
            return (citation.score + source_boost + category_boost, citation.score, citation.filename)

        return sorted(candidates, key=rank, reverse=True)

    def _should_guard(
        self,
        item: dict[str, Any],
        candidates: list[Citation],
        learning: WinLossLearningResponse,
    ) -> bool:
        if item.get("expect_missing_evidence"):
            return True
        question = item["question"].lower()
        risky_terms = {"guarantee", "zero", "fedramp", "stateramp", "active-active", "unsupported"}
        if not any(term in question for term in risky_terms):
            return False
        loss_terms = {
            token
            for recommendation in learning.retrieval_recommendations
            if recommendation.get("type") == "gap_guardrail"
            for token in recommendation.get("query_expansion_terms", [])
        }
        if loss_terms.intersection(self._tokens(question)):
            return True
        return not candidates or max(citation.score for citation in candidates) < 0.35

    def _diagnostic_row(
        self,
        policy: dict[str, Any],
        item: dict[str, Any],
        index: int,
        candidates: list[Citation],
        selected: list[Citation],
        guardrails: list[str],
        latency_ms: float,
    ) -> dict[str, Any]:
        expected_docs = set(item.get("expected_evidence_documents", []))
        cited_docs = {citation.filename for citation in selected}
        hit_count = len(expected_docs.intersection(cited_docs))
        expected_missing = bool(item.get("expect_missing_evidence"))
        missing_hit = expected_missing and not selected
        if expected_docs:
            precision = hit_count / min(max(1, len(expected_docs)), max(1, len(selected)))
            recall = hit_count / len(expected_docs)
            citation_hit = hit_count > 0
        else:
            precision = 1.0 if not selected else 0.0
            recall = 1.0 if not selected else 0.0
            citation_hit = not selected
        return {
            "diagnostic_id": f"{policy['policy_id']}-q{index}",
            "policy_id": policy["policy_id"],
            "question": item["question"],
            "expected_documents": sorted(expected_docs),
            "candidate_documents": [citation.filename for citation in candidates[:8]],
            "selected_documents": [citation.filename for citation in selected],
            "hit_count": hit_count,
            "precision_at_k": round(precision, 3),
            "recall_at_k": round(recall, 3),
            "citation_hit": citation_hit,
            "expected_missing_evidence": expected_missing,
            "missing_evidence_detected": missing_hit,
            "unsupported_risk": expected_missing and bool(selected),
            "guardrails_triggered": guardrails,
            "max_candidate_score": round(max((citation.score for citation in candidates), default=0.0), 4),
            "latency_ms": round(latency_ms, 2),
        }

    def _policy_result(
        self,
        policy: dict[str, Any],
        diagnostics: list[dict[str, Any]],
        elapsed_ms: float,
    ) -> dict[str, Any]:
        count = len(diagnostics)
        precision = self._avg(row["precision_at_k"] for row in diagnostics)
        recall = self._avg(row["recall_at_k"] for row in diagnostics)
        citation_coverage = self._ratio(sum(1 for row in diagnostics if row["citation_hit"]), count)
        missing_hits = sum(1 for row in diagnostics if row["missing_evidence_detected"])
        missing_expected = sum(1 for row in diagnostics if row["expected_missing_evidence"])
        missing_rate = self._ratio(missing_hits, missing_expected) if missing_expected else 1.0
        unsupported_risk_count = sum(1 for row in diagnostics if row["unsupported_risk"])
        guardrail_count = sum(1 for row in diagnostics if row["guardrails_triggered"])
        score = round(
            precision * 38
            + recall * 22
            + citation_coverage * 18
            + missing_rate * 16
            - unsupported_risk_count * 8
            + min(6, guardrail_count),
            2,
        )
        return {
            "policy_id": policy["policy_id"],
            "label": policy["label"],
            "patterns": policy["patterns"],
            "experiment_score": score,
            "retrieval_precision_at_k": round(precision, 3),
            "retrieval_recall_at_k": round(recall, 3),
            "citation_coverage": round(citation_coverage, 3),
            "missing_evidence_hits": missing_hits,
            "missing_evidence_expected": missing_expected,
            "unsupported_risk_count": unsupported_risk_count,
            "guardrail_count": guardrail_count,
            "average_latency_ms": round(elapsed_ms / count, 2) if count else 0.0,
            "decision": "eligible" if unsupported_risk_count == 0 else "needs_review",
        }

    def _recommended_policy(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        return sorted(
            rows,
            key=lambda row: (
                row["unsupported_risk_count"] == 0,
                row["experiment_score"],
                row["citation_coverage"],
                -row["average_latency_ms"],
            ),
            reverse=True,
        )[0]

    def _governance_decision(
        self,
        recommended: dict[str, Any],
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        baseline = next((row for row in rows if row["policy_id"] == "baseline"), recommended)
        delta = round(recommended["experiment_score"] - baseline["experiment_score"], 2)
        status = "ready_for_shadow_eval"
        blockers = []
        if recommended["unsupported_risk_count"]:
            status = "human_review_required"
            blockers.append("Recommended policy still retrieved evidence for missing-evidence questions.")
        if delta < 0:
            status = "human_review_required"
            blockers.append("Recommended policy did not improve over baseline.")
        return {
            "status": status,
            "recommended_policy_id": recommended["policy_id"],
            "baseline_policy_id": baseline["policy_id"],
            "score_delta_vs_baseline": delta,
            "approval_required": status != "ready_for_shadow_eval",
            "owner": "ai_engineering",
            "blockers": blockers,
            "next_step": (
                "Run as a shadow retrieval policy against standard and red-team evals before making it default."
                if status == "ready_for_shadow_eval"
                else "Review diagnostics and adjust guardrails before shadow testing."
            ),
        }

    def _pack_payload(self, trace_id: str, comparison: RetrievalExperimentResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Retrieval Experiment Comparison Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "executive_summary": {
                "status": comparison.status,
                "recommended_policy_id": comparison.recommended_policy_id,
                "question_count": comparison.summary["question_count"],
                "policy_count": comparison.summary["policy_count"],
                "score_delta_vs_baseline": comparison.governance_decision["score_delta_vs_baseline"],
            },
            "policy_results": comparison.policy_results,
            "question_diagnostics": comparison.question_diagnostics,
            "trace_spans": comparison.trace_spans,
            "governance_decision": comparison.governance_decision,
            "proof_commands": comparison.local_proof_commands,
            "limitations": comparison.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        summary = pack["executive_summary"]
        lines = [
            "# Retrieval Experiment Comparison Pack",
            "",
            "## Executive Summary",
            "",
            f"- Status: {summary['status']}",
            f"- Recommended policy: {summary['recommended_policy_id']}",
            f"- Questions: {summary['question_count']}",
            f"- Policies compared: {summary['policy_count']}",
            f"- Score delta vs baseline: {summary['score_delta_vs_baseline']}",
            "",
            "## Policy Results",
            "",
            "| Policy | Score | Precision | Recall | Citation Coverage | Missing Hits | Unsupported Risk |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for row in pack["policy_results"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._md(row["policy_id"]),
                        self._md(row["experiment_score"]),
                        self._md(row["retrieval_precision_at_k"]),
                        self._md(row["retrieval_recall_at_k"]),
                        self._md(row["citation_coverage"]),
                        self._md(f"{row['missing_evidence_hits']}/{row['missing_evidence_expected']}"),
                        self._md(row["unsupported_risk_count"]),
                    ]
                )
                + " |"
            )
        lines.extend(["", "## Governance Decision", ""])
        decision = pack["governance_decision"]
        lines.extend(
            [
                f"- Status: {decision['status']}",
                f"- Approval required: {decision['approval_required']}",
                f"- Owner: {decision['owner']}",
                f"- Next step: {decision['next_step']}",
            ]
        )
        if decision["blockers"]:
            lines.extend(["", "## Blockers", ""])
            lines.extend(f"- {item}" for item in decision["blockers"])
        lines.extend(["", "## Trace Spans", ""])
        for span in pack["trace_spans"]:
            lines.append(
                f"- {span['span_id']}: {span['policy_id']} "
                f"{span['duration_ms']} ms over {span['question_count']} questions"
            )
        lines.extend(["", "## Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _local_commands(self) -> list[str]:
        return [
            (
                'curl -X POST "http://127.0.0.1:8000/rag/retrieval-experiments" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/rag/retrieval-experiment-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            'rg "retrieval-experiments|retrieval_experiments|Retrieval Experiment" app dashboard docs README.md tests',
        ]

    def _limitations(self) -> list[str]:
        return [
            "Experiments run against deterministic local fixtures, not live buyer traffic.",
            "Policy comparison reranks local retrieval results; it does not mutate the vector index.",
            "Win/loss learning inputs are fake local outcomes and require human approval before production rollout.",
            "Trace spans are local diagnostic records, not exported to an external observability backend.",
        ]

    def _tokens(self, text: str) -> set[str]:
        return set(re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]{2,}", text.lower()))

    def _avg(self, values: Any) -> float:
        rows = list(values)
        return sum(rows) / len(rows) if rows else 0.0

    def _ratio(self, passed: int, total: int) -> float:
        return round(passed / total, 3) if total else 0.0

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
