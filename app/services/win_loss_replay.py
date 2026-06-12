from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.models.api import (
    RetrievalExperimentResponse,
    WinLossLearningResponse,
    WinLossPolicyActivationResponse,
    WinLossReplayPackResponse,
    WinLossReplayResponse,
)


class WinLossReplayService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def replay(
        self,
        trace_id: str,
        learning: WinLossLearningResponse,
        activation_plan: WinLossPolicyActivationResponse,
        retrieval_experiment: RetrievalExperimentResponse,
        eval_dataset_path: str = "sample_data/eval_dataset.json",
        red_team_dataset_path: str = "sample_data/red_team_questions.json",
    ) -> WinLossReplayResponse:
        eval_questions = self._load_questions(eval_dataset_path)
        red_team_questions = self._load_questions(red_team_dataset_path)
        eval_rows = self._eval_case_results(eval_questions, retrieval_experiment, activation_plan)
        red_team_rows = self._red_team_case_results(red_team_questions, learning, activation_plan)
        policy_delta = self._policy_delta(retrieval_experiment)
        human_review_queue = self._human_review_queue(eval_rows, red_team_rows, activation_plan)
        governance_decision = self._governance_decision(policy_delta, eval_rows, red_team_rows, activation_plan)
        trace_spans = self._trace_spans(trace_id, retrieval_experiment, eval_rows, red_team_rows, activation_plan)
        status = governance_decision["status"]
        return WinLossReplayResponse(
            title="Win/Loss Replay Backtest",
            status=status,
            replay_summary={
                "eval_dataset_path": eval_dataset_path,
                "red_team_dataset_path": red_team_dataset_path,
                "eval_case_count": len(eval_rows),
                "red_team_case_count": len(red_team_rows),
                "passed_eval_cases": sum(1 for row in eval_rows if row["passed"]),
                "passed_red_team_cases": sum(1 for row in red_team_rows if row["passed"]),
                "recommended_policy_id": activation_plan.recommended_policy_id,
                "activation_status": activation_plan.status,
                "patterns_used": [
                    "trace_analysis",
                    "experiment_comparison",
                    "governance",
                    "human_in_the_loop",
                ],
            },
            eval_case_results=eval_rows,
            red_team_case_results=red_team_rows,
            policy_delta=policy_delta,
            trace_spans=trace_spans,
            governance_decision=governance_decision,
            human_review_queue=human_review_queue,
            local_proof_commands=self._local_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def replay_pack(
        self,
        trace_id: str,
        replay: WinLossReplayResponse,
        write_artifact: bool = True,
    ) -> WinLossReplayPackResponse:
        pack = self._pack_payload(trace_id, replay)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "win_loss_replay"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"win_loss_replay_backtest_{safe_trace_id}.md"
            json_path = pack_dir / f"win_loss_replay_backtest_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["win_loss_replay_markdown"] = artifact_path
            pack["artifact_paths"]["win_loss_replay_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return WinLossReplayPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            replay=replay,
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
            raise FileNotFoundError(f"Win/loss replay dataset not found: {dataset_path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return list(payload.get("questions", []))

    def _eval_case_results(
        self,
        questions: list[dict[str, Any]],
        experiment: RetrievalExperimentResponse,
        activation_plan: WinLossPolicyActivationResponse,
    ) -> list[dict[str, Any]]:
        baseline = self._diagnostics_by_question(experiment, "baseline")
        recommended = self._diagnostics_by_question(experiment, activation_plan.recommended_policy_id)
        rows = []
        for index, item in enumerate(questions, start=1):
            question = item["question"]
            base = baseline.get(question, {})
            learned = recommended.get(question, base)
            expected_missing = bool(item.get("expect_missing_evidence"))
            improved = self._improved(base, learned, expected_missing)
            passed = bool(learned.get("missing_evidence_detected")) if expected_missing else bool(
                learned.get("citation_hit")
            )
            rows.append(
                {
                    "case_id": f"eval-replay-{index:02d}",
                    "question": question,
                    "expected_missing_evidence": expected_missing,
                    "baseline_selected_documents": base.get("selected_documents", []),
                    "learned_selected_documents": learned.get("selected_documents", []),
                    "baseline_unsupported_risk": bool(base.get("unsupported_risk")),
                    "learned_unsupported_risk": bool(learned.get("unsupported_risk")),
                    "precision_delta": round(
                        float(learned.get("precision_at_k", 0.0)) - float(base.get("precision_at_k", 0.0)),
                        3,
                    ),
                    "guardrails_triggered": learned.get("guardrails_triggered", []),
                    "outcome": "improved" if improved else "held" if passed else "regressed",
                    "passed": passed and not bool(learned.get("unsupported_risk")),
                }
            )
        return rows

    def _red_team_case_results(
        self,
        questions: list[dict[str, Any]],
        learning: WinLossLearningResponse,
        activation_plan: WinLossPolicyActivationResponse,
    ) -> list[dict[str, Any]]:
        guardrail_categories = {
            rule["category"]
            for rule in activation_plan.policy_rules
            if rule["rule_type"] == "gap_guardrail" and rule["state"] != "blocked"
        }
        learned_terms = {
            token
            for recommendation in learning.retrieval_recommendations
            if recommendation.get("type") == "gap_guardrail"
            for token in recommendation.get("query_expansion_terms", [])
        }
        rows = []
        for index, item in enumerate(questions, start=1):
            risk_type = item.get("risk_type", "unknown")
            question = item["question"]
            expected_missing = bool(item.get("expect_missing_evidence"))
            category = self._category_for_text(f"{risk_type} {question}")
            term_match = bool(learned_terms.intersection(self._tokens(question)))
            guardrail_match = category in guardrail_categories or term_match
            passed = not expected_missing or guardrail_match
            rows.append(
                {
                    "case_id": f"red-team-replay-{index:02d}",
                    "risk_type": risk_type,
                    "question": question,
                    "expected_missing_evidence": expected_missing,
                    "mapped_category": category,
                    "guardrail_match": guardrail_match,
                    "matched_terms": sorted(learned_terms.intersection(self._tokens(question))),
                    "recommended_action": (
                        "block_or_route_to_human_review" if expected_missing else "allow_with_cited_evidence"
                    ),
                    "passed": passed,
                }
            )
        return rows

    def _policy_delta(self, experiment: RetrievalExperimentResponse) -> dict[str, Any]:
        baseline = next((row for row in experiment.policy_results if row["policy_id"] == "baseline"), {})
        recommended = next(
            (row for row in experiment.policy_results if row["policy_id"] == experiment.recommended_policy_id),
            {},
        )
        return {
            "baseline_policy_id": baseline.get("policy_id", "baseline"),
            "recommended_policy_id": experiment.recommended_policy_id,
            "score_delta": round(
                float(recommended.get("experiment_score", 0.0)) - float(baseline.get("experiment_score", 0.0)),
                2,
            ),
            "citation_coverage_delta": round(
                float(recommended.get("citation_coverage", 0.0)) - float(baseline.get("citation_coverage", 0.0)),
                3,
            ),
            "unsupported_risk_delta": int(recommended.get("unsupported_risk_count", 0))
            - int(baseline.get("unsupported_risk_count", 0)),
            "missing_evidence_hit_delta": int(recommended.get("missing_evidence_hits", 0))
            - int(baseline.get("missing_evidence_hits", 0)),
            "recommended_decision": recommended.get("decision", "unknown"),
        }

    def _governance_decision(
        self,
        policy_delta: dict[str, Any],
        eval_rows: list[dict[str, Any]],
        red_team_rows: list[dict[str, Any]],
        activation_plan: WinLossPolicyActivationResponse,
    ) -> dict[str, Any]:
        failed_eval = [row["case_id"] for row in eval_rows if not row["passed"]]
        failed_red_team = [row["case_id"] for row in red_team_rows if not row["passed"]]
        blockers = []
        if policy_delta["score_delta"] < 0:
            blockers.append("Recommended policy scores below baseline in retrieval experiment.")
        if policy_delta["unsupported_risk_delta"] > 0:
            blockers.append("Recommended policy increases unsupported-risk count.")
        if failed_eval:
            blockers.append(f"{len(failed_eval)} standard eval replay case(s) failed.")
        if failed_red_team:
            blockers.append(f"{len(failed_red_team)} red-team replay case(s) failed.")
        if activation_plan.status == "human_review_required":
            blockers.append("Policy activation already requires human review.")
        status = "ready_for_shadow_eval" if not blockers else "human_review_required"
        return {
            "status": status,
            "approval_required": bool(blockers),
            "owner": "ai_engineering" if not blockers else "proposal_manager",
            "blockers": blockers,
            "failed_eval_case_ids": failed_eval,
            "failed_red_team_case_ids": failed_red_team,
            "next_step": (
                "Run the learned policy in shadow mode and attach replay artifacts to reviewer signoff."
                if not blockers
                else "Resolve failed replay cases before limited rollout."
            ),
        }

    def _human_review_queue(
        self,
        eval_rows: list[dict[str, Any]],
        red_team_rows: list[dict[str, Any]],
        activation_plan: WinLossPolicyActivationResponse,
    ) -> list[dict[str, Any]]:
        queue = []
        for row in eval_rows:
            if not row["passed"] or row["learned_unsupported_risk"]:
                queue.append(
                    {
                        "owner": "ai_engineering",
                        "review_type": "eval_replay_failure",
                        "item_id": row["case_id"],
                        "reason": row["outcome"],
                        "required_before_state": "limited_rollout",
                    }
                )
        for row in red_team_rows:
            if not row["passed"]:
                queue.append(
                    {
                        "owner": self._owner(row["mapped_category"]),
                        "review_type": "red_team_guardrail_gap",
                        "item_id": row["case_id"],
                        "reason": row["risk_type"],
                        "required_before_state": "shadow_eval",
                    }
                )
        for checkpoint in activation_plan.checkpoints:
            if checkpoint.get("status") == "blocked":
                queue.append(
                    {
                        "owner": checkpoint.get("owner", "proposal_manager"),
                        "review_type": "blocked_policy_checkpoint",
                        "item_id": checkpoint["checkpoint_id"],
                        "reason": checkpoint["name"],
                        "required_before_state": "shadow_eval",
                    }
                )
        return queue[:12]

    def _trace_spans(
        self,
        trace_id: str,
        experiment: RetrievalExperimentResponse,
        eval_rows: list[dict[str, Any]],
        red_team_rows: list[dict[str, Any]],
        activation_plan: WinLossPolicyActivationResponse,
    ) -> list[dict[str, Any]]:
        return [
            {
                "span_id": f"{trace_id}-experiment-comparison",
                "name": "win_loss_replay_experiment_comparison",
                "input_trace_id": experiment.trace_id,
                "attributes": {
                    "recommended_policy_id": experiment.recommended_policy_id,
                    "policy_result_count": len(experiment.policy_results),
                    "diagnostic_count": len(experiment.question_diagnostics),
                },
            },
            {
                "span_id": f"{trace_id}-policy-state",
                "name": "win_loss_replay_policy_state",
                "input_trace_id": activation_plan.trace_id,
                "attributes": {
                    "activation_status": activation_plan.status,
                    "policy_rules": len(activation_plan.policy_rules),
                    "checkpoints": len(activation_plan.checkpoints),
                },
            },
            {
                "span_id": f"{trace_id}-case-replay",
                "name": "win_loss_replay_case_results",
                "attributes": {
                    "eval_cases": len(eval_rows),
                    "red_team_cases": len(red_team_rows),
                    "failed_cases": sum(1 for row in [*eval_rows, *red_team_rows] if not row["passed"]),
                },
            },
        ]

    def _pack_payload(self, trace_id: str, replay: WinLossReplayResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Win/Loss Replay Backtest Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "executive_summary": {
                "status": replay.status,
                "recommended_policy_id": replay.replay_summary["recommended_policy_id"],
                "eval_cases": replay.replay_summary["eval_case_count"],
                "red_team_cases": replay.replay_summary["red_team_case_count"],
                "approval_required": replay.governance_decision["approval_required"],
                "score_delta": replay.policy_delta["score_delta"],
            },
            "policy_delta": replay.policy_delta,
            "eval_case_results": replay.eval_case_results,
            "red_team_case_results": replay.red_team_case_results,
            "trace_spans": replay.trace_spans,
            "governance_decision": replay.governance_decision,
            "human_review_queue": replay.human_review_queue,
            "proof_commands": replay.local_proof_commands,
            "limitations": replay.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        summary = pack["executive_summary"]
        lines = [
            "# Win/Loss Replay Backtest Pack",
            "",
            "## Executive Summary",
            "",
            f"- Status: {summary['status']}",
            f"- Recommended policy: {summary['recommended_policy_id']}",
            f"- Eval cases: {summary['eval_cases']}",
            f"- Red-team cases: {summary['red_team_cases']}",
            f"- Score delta: {summary['score_delta']}",
            f"- Approval required: {summary['approval_required']}",
            "",
            "## Policy Delta",
            "",
        ]
        lines.extend(f"- {key}: {value}" for key, value in pack["policy_delta"].items())
        lines.extend(["", "## Eval Replay Cases", ""])
        for row in pack["eval_case_results"]:
            lines.append(
                f"- {row['case_id']} [{self._status(row['passed'])}]: "
                f"{row['outcome']} | {row['question']}"
            )
        lines.extend(["", "## Red-Team Replay Cases", ""])
        for row in pack["red_team_case_results"]:
            lines.append(
                f"- {row['case_id']} [{self._status(row['passed'])}]: "
                f"{row['risk_type']} -> {row['recommended_action']}"
            )
        lines.extend(["", "## Governance Decision", ""])
        decision = pack["governance_decision"]
        lines.extend(
            [
                f"- Status: {decision['status']}",
                f"- Owner: {decision['owner']}",
                f"- Next step: {decision['next_step']}",
            ]
        )
        if decision["blockers"]:
            lines.extend(["", "## Blockers", ""])
            lines.extend(f"- {item}" for item in decision["blockers"])
        lines.extend(["", "## Human Review Queue", ""])
        if pack["human_review_queue"]:
            for item in pack["human_review_queue"]:
                lines.append(f"- {item['owner']}: {item['review_type']} for {item['item_id']}")
        else:
            lines.append("- None")
        lines.extend(["", "## Trace Spans", ""])
        for span in pack["trace_spans"]:
            lines.append(f"- {span['span_id']}: {span['name']}")
        lines.extend(["", "## Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _diagnostics_by_question(
        self,
        experiment: RetrievalExperimentResponse,
        policy_id: str,
    ) -> dict[str, dict[str, Any]]:
        return {
            row["question"]: row
            for row in experiment.question_diagnostics
            if row.get("policy_id") == policy_id
        }

    def _improved(self, baseline: dict[str, Any], learned: dict[str, Any], expected_missing: bool) -> bool:
        if expected_missing:
            return bool(learned.get("missing_evidence_detected")) and not bool(
                baseline.get("missing_evidence_detected")
            )
        return float(learned.get("precision_at_k", 0.0)) > float(baseline.get("precision_at_k", 0.0))

    def _category_for_text(self, text: str) -> str:
        lowered = text.lower()
        terms = {
            "security": ["sso", "encryption", "security", "incident", "audit", "mfa"],
            "compliance": ["soc", "gdpr", "fedramp", "stateramp", "compliance", "subprocessor"],
            "pricing": ["pricing", "discount", "commercial", "price", "payment", "unlimited"],
            "implementation": ["implementation", "timeline", "migration", "deployment", "onboarding"],
            "support": ["support", "sla", "uptime", "availability", "rto", "rpo", "data loss"],
            "ai_governance": ["ai", "model", "human review", "governance", "unsupported model"],
        }
        for category, category_terms in terms.items():
            if any(term in lowered for term in category_terms):
                return category
        return "general"

    def _owner(self, category: str) -> str:
        return {
            "security": "security",
            "compliance": "legal",
            "pricing": "finance",
            "support": "solutions",
            "implementation": "solutions",
            "ai_governance": "security",
        }.get(category, "proposal_manager")

    def _local_commands(self) -> list[str]:
        return [
            (
                'curl -X POST "http://127.0.0.1:8000/learning/win-loss-replay" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/learning/win-loss-replay-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            'rg "win-loss-replay|Win/Loss Replay|win_loss_replay" app dashboard docs README.md tests',
        ]

    def _limitations(self) -> list[str]:
        return [
            "Replay is deterministic and local; it does not replay live CRM decisions or buyer traffic.",
            "The learned policy is evaluated in shadow mode and does not mutate runtime retrieval defaults.",
            "Outcome, eval, and red-team rows are fake fixtures intended for portfolio-grade verification.",
            "Human review queues are local artifacts and require an external workflow system for production routing.",
        ]

    def _tokens(self, text: str) -> set[str]:
        return set(re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]{2,}", text.lower()))

    def _status(self, passed: bool) -> str:
        return "pass" if passed else "review"
