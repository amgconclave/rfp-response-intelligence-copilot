from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.models.api import (
    WinLossEvalCasePackResponse,
    WinLossEvalCaseResponse,
    WinLossLearningResponse,
)


class WinLossEvalCaseService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def compile_cases(
        self,
        trace_id: str,
        learning: WinLossLearningResponse,
        eval_dataset_path: str = "sample_data/eval_dataset.json",
        red_team_dataset_path: str = "sample_data/red_team_questions.json",
        max_cases_per_type: int = 6,
    ) -> WinLossEvalCaseResponse:
        eval_questions = self._load_questions(eval_dataset_path)
        red_team_questions = self._load_questions(red_team_dataset_path)
        max_cases = max(1, min(12, max_cases_per_type))
        existing_questions = {
            self._normalize_question(item.get("question", "")) for item in [*eval_questions, *red_team_questions]
        }

        positive_cases = self._positive_cases(learning, existing_questions, max_cases)
        red_team_cases = self._red_team_cases(learning, existing_questions, max_cases)
        duplicate_count = sum(1 for item in [*positive_cases, *red_team_cases] if item["status"] == "duplicate")
        candidate_count = sum(1 for item in [*positive_cases, *red_team_cases] if item["status"] == "candidate")
        status = "ready_for_review" if candidate_count else "no_new_cases"
        dataset_patch = {
            "patch_mode": "candidate_artifacts_only",
            "eval_dataset_path": eval_dataset_path,
            "red_team_dataset_path": red_team_dataset_path,
            "existing_eval_questions": len(eval_questions),
            "existing_red_team_questions": len(red_team_questions),
            "candidate_eval_cases": sum(1 for item in positive_cases if item["status"] == "candidate"),
            "candidate_red_team_cases": sum(1 for item in red_team_cases if item["status"] == "candidate"),
            "duplicate_questions": duplicate_count,
            "mutation": "No checked-in dataset is modified; pack generation writes candidate JSON artifacts.",
        }
        return WinLossEvalCaseResponse(
            title="Win/Loss Eval Case Compiler",
            status=status,
            summary={
                "outcome_count": learning.outcome_count,
                "win_rate": learning.win_rate,
                "winning_patterns": len(learning.winning_evidence_patterns),
                "losing_patterns": len(learning.losing_risk_patterns),
                "candidate_case_count": candidate_count,
                "duplicate_case_count": duplicate_count,
            },
            positive_eval_cases=positive_cases,
            red_team_cases=red_team_cases,
            dataset_patch=dataset_patch,
            governance_summary={
                "patterns_used": [
                    "typed_contracts",
                    "structured_outputs",
                    "state_machine_workflow",
                    "traceable_node_transitions",
                    "eval_friendly_design",
                ],
                "approval_gate": "ai_engineering_review",
                "rollout_rule": (
                    "Append candidate rows to eval fixtures only after reviewer approval and a passing replay run."
                ),
            },
            trace_spans=self._trace_spans(trace_id, learning, positive_cases, red_team_cases),
            owner_review_queue=self._owner_review_queue(positive_cases, red_team_cases),
            local_proof_commands=self._local_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def eval_case_pack(
        self,
        trace_id: str,
        eval_case_plan: WinLossEvalCaseResponse,
        write_artifact: bool = True,
    ) -> WinLossEvalCasePackResponse:
        pack = self._pack_payload(trace_id, eval_case_plan)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        candidate_eval_path: str | None = None
        candidate_red_team_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "win_loss_eval_cases"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"win_loss_eval_case_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"win_loss_eval_case_pack_{safe_trace_id}.json"
            eval_path = pack_dir / f"candidate_eval_cases_{safe_trace_id}.json"
            red_team_path = pack_dir / f"candidate_red_team_cases_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            candidate_eval_path = str(eval_path.resolve())
            candidate_red_team_path = str(red_team_path.resolve())
            pack["artifact_paths"]["win_loss_eval_case_markdown"] = artifact_path
            pack["artifact_paths"]["win_loss_eval_case_json"] = json_artifact_path
            pack["artifact_paths"]["candidate_eval_dataset"] = candidate_eval_path
            pack["artifact_paths"]["candidate_red_team_dataset"] = candidate_red_team_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
            eval_path.write_text(
                json.dumps({"questions": self._eval_dataset_rows(eval_case_plan)}, indent=2),
                encoding="utf-8",
            )
            red_team_path.write_text(
                json.dumps({"questions": self._red_team_dataset_rows(eval_case_plan)}, indent=2),
                encoding="utf-8",
            )

        return WinLossEvalCasePackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            candidate_eval_dataset_path=candidate_eval_path,
            candidate_red_team_dataset_path=candidate_red_team_path,
            markdown=markdown,
            pack=pack,
            eval_case_plan=eval_case_plan,
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
            raise FileNotFoundError(f"Eval dataset not found: {dataset_path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return list(payload.get("questions", []))

    def _positive_cases(
        self,
        learning: WinLossLearningResponse,
        existing_questions: set[str],
        max_cases: int,
    ) -> list[dict[str, Any]]:
        cases = []
        for pattern in learning.winning_evidence_patterns[:max_cases]:
            question = f"Which approved evidence supports {pattern['category']} claims from {pattern['source']}?"
            cases.append(
                {
                    "case_id": f"wl-eval-{pattern['pattern_id']}",
                    "case_type": "positive_regression_case",
                    "question": question,
                    "expected_evidence_documents": [pattern["source"]] if pattern.get("source") else [],
                    "expected_answer_themes": self._themes(pattern.get("representative_claims", [])),
                    "source_citations": pattern.get("citations", []),
                    "learning_pattern_ids": [pattern["pattern_id"]],
                    "source_recommendation_ids": self._recommendation_ids(
                        learning.retrieval_recommendations,
                        pattern["category"],
                        "source_boost",
                    ),
                    "review_owner": "ai_engineering",
                    "status": self._case_status(question, existing_questions),
                }
            )
        return cases

    def _red_team_cases(
        self,
        learning: WinLossLearningResponse,
        existing_questions: set[str],
        max_cases: int,
    ) -> list[dict[str, Any]]:
        cases = []
        for pattern in learning.losing_risk_patterns[:max_cases]:
            gap = str(pattern.get("common_gaps", ["unsupported guarantee"])[0])
            question = f"Can we guarantee the buyer requirement implied by this prior loss gap: {gap}?"
            cases.append(
                {
                    "case_id": f"wl-red-team-{pattern['pattern_id']}",
                    "case_type": "red_team_missing_evidence_case",
                    "question": question,
                    "risk_type": f"win_loss_{pattern['category']}_gap",
                    "expect_missing_evidence": True,
                    "expected_review_categories": ["missing_evidence", "weak_citation"],
                    "common_gaps": pattern.get("common_gaps", []),
                    "learning_pattern_ids": [pattern["pattern_id"]],
                    "source_recommendation_ids": self._recommendation_ids(
                        learning.retrieval_recommendations,
                        pattern["category"],
                        "gap_guardrail",
                    ),
                    "review_owner": self._owner_for_category(pattern["category"]),
                    "severity": pattern.get("severity", "medium"),
                    "status": self._case_status(question, existing_questions),
                }
            )
        return cases

    def _eval_dataset_rows(self, plan: WinLossEvalCaseResponse) -> list[dict[str, Any]]:
        rows = []
        for case in plan.positive_eval_cases:
            if case["status"] != "candidate":
                continue
            rows.append(
                {
                    "question": case["question"],
                    "expected_evidence_documents": case["expected_evidence_documents"],
                    "expected_answer_themes": case["expected_answer_themes"],
                }
            )
        return rows

    def _red_team_dataset_rows(self, plan: WinLossEvalCaseResponse) -> list[dict[str, Any]]:
        rows = []
        for case in plan.red_team_cases:
            if case["status"] != "candidate":
                continue
            rows.append(
                {
                    "question": case["question"],
                    "risk_type": case["risk_type"],
                    "expect_missing_evidence": True,
                    "expected_review_categories": case["expected_review_categories"],
                }
            )
        return rows

    def _trace_spans(
        self,
        trace_id: str,
        learning: WinLossLearningResponse,
        positive_cases: list[dict[str, Any]],
        red_team_cases: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        nodes = [
            ("load_learning", "loaded", {"outcome_count": learning.outcome_count}),
            (
                "compile_positive_cases",
                "compiled",
                {"case_count": len(positive_cases), "source": "winning_evidence_patterns"},
            ),
            (
                "compile_red_team_cases",
                "compiled",
                {"case_count": len(red_team_cases), "source": "losing_risk_patterns"},
            ),
            (
                "route_owner_review",
                "queued",
                {
                    "review_items": sum(
                        1 for item in [*positive_cases, *red_team_cases] if item["status"] == "candidate"
                    )
                },
            ),
        ]
        spans = []
        previous: str | None = None
        for sequence, (node, status, output) in enumerate(nodes, start=1):
            spans.append(
                {
                    "span_id": f"{trace_id}-{sequence:02d}-{node}",
                    "sequence": sequence,
                    "from_state": previous,
                    "to_state": node,
                    "status": status,
                    "checkpoint_key": f"{trace_id}:{sequence:02d}:{node}",
                    "output": output,
                }
            )
            previous = node
        return spans

    def _owner_review_queue(
        self,
        positive_cases: list[dict[str, Any]],
        red_team_cases: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows = []
        for case in [*positive_cases, *red_team_cases]:
            if case["status"] != "candidate":
                continue
            rows.append(
                {
                    "case_id": case["case_id"],
                    "case_type": case["case_type"],
                    "owner": case["review_owner"],
                    "required_decision": "Approve, edit, or reject this candidate before fixture append.",
                    "question": case["question"],
                }
            )
        return rows

    def _pack_payload(self, trace_id: str, plan: WinLossEvalCaseResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Win/Loss Eval Case Compiler Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "status": plan.status,
            "summary": plan.summary,
            "dataset_patch": plan.dataset_patch,
            "governance_summary": plan.governance_summary,
            "positive_eval_cases": plan.positive_eval_cases,
            "red_team_cases": plan.red_team_cases,
            "trace_spans": plan.trace_spans,
            "owner_review_queue": plan.owner_review_queue,
            "proof_commands": plan.local_proof_commands,
            "limitations": plan.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        lines = [
            "# Win/Loss Eval Case Compiler Pack",
            "",
            "## Executive Summary",
            "",
            f"- Status: {pack['status']}",
            f"- Candidate cases: {pack['summary']['candidate_case_count']}",
            f"- Duplicate cases: {pack['summary']['duplicate_case_count']}",
            f"- Eval candidates: {pack['dataset_patch']['candidate_eval_cases']}",
            f"- Red-team candidates: {pack['dataset_patch']['candidate_red_team_cases']}",
            f"- Mutation mode: {pack['dataset_patch']['mutation']}",
            "",
            "## Positive Eval Candidates",
            "",
            "| Case | Status | Evidence Docs | Question |",
            "| --- | --- | --- | --- |",
        ]
        for case in pack["positive_eval_cases"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._md(case["case_id"]),
                        self._md(case["status"]),
                        self._md(", ".join(case["expected_evidence_documents"])),
                        self._md(case["question"]),
                    ]
                )
                + " |"
            )
        lines.extend(
            [
                "",
                "## Red-Team Candidates",
                "",
                "| Case | Status | Risk | Owner | Question |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for case in pack["red_team_cases"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._md(case["case_id"]),
                        self._md(case["status"]),
                        self._md(case["risk_type"]),
                        self._md(case["review_owner"]),
                        self._md(case["question"]),
                    ]
                )
                + " |"
            )
        lines.extend(["", "## Trace Spans", ""])
        for span in pack["trace_spans"]:
            lines.append(
                f"- {span['sequence']}. {span['from_state'] or 'START'} -> {span['to_state']} "
                f"({span['status']}): {span['output']}"
            )
        lines.extend(["", "## Owner Review Queue", ""])
        if pack["owner_review_queue"]:
            for item in pack["owner_review_queue"]:
                lines.append(f"- {item['owner']} / {item['case_id']}: {item['required_decision']}")
        else:
            lines.append("- None")
        lines.extend(["", "## Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _recommendation_ids(
        self,
        recommendations: list[dict[str, Any]],
        category: str,
        recommendation_type: str,
    ) -> list[str]:
        return [
            item["recommendation_id"]
            for item in recommendations
            if item.get("category") == category and item.get("type") == recommendation_type
        ][:4]

    def _themes(self, claims: list[str]) -> list[str]:
        tokens = []
        stop_words = {"and", "are", "for", "from", "that", "this", "with"}
        for claim in claims:
            tokens.extend(re.findall(r"[a-zA-Z0-9]{4,}", claim.lower()))
        themes = list(dict.fromkeys(token for token in tokens if token not in stop_words))[:6]
        return themes or ["approved evidence", "citation", "grounded answer"]

    def _case_status(self, question: str, existing_questions: set[str]) -> str:
        return "duplicate" if self._normalize_question(question) in existing_questions else "candidate"

    def _normalize_question(self, question: str) -> str:
        return re.sub(r"\s+", " ", question.strip().lower())

    def _owner_for_category(self, category: str) -> str:
        return {
            "security": "security",
            "compliance": "compliance",
            "pricing": "finance",
            "implementation": "solutions",
            "support": "customer_success",
            "ai_governance": "ai_governance",
        }.get(category, "proposal_manager")

    def _local_commands(self) -> list[str]:
        return [
            (
                'curl -X POST "http://127.0.0.1:8000/learning/win-loss-eval-cases" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/learning/win-loss-eval-case-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            'rg "win-loss-eval-cases|Win/Loss Eval Case" app dashboard docs README.md tests',
        ]

    def _limitations(self) -> list[str]:
        return [
            "Candidate datasets are generated under storage and do not modify checked-in eval fixtures.",
            "Compiled cases are deterministic heuristics from fake post-RFP outcomes, not CRM win/loss records.",
            "Human review is required before appending generated cases to release-gating eval datasets.",
            "The compiler validates dataset shape locally but does not run a live model or external provider.",
        ]

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
