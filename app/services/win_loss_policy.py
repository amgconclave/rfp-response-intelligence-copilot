from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    RetrievalExperimentResponse,
    WinLossLearningResponse,
    WinLossPolicyActivationResponse,
    WinLossPolicyPackResponse,
)


class WinLossPolicyActivationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def activation_plan(
        self,
        trace_id: str,
        learning: WinLossLearningResponse,
        retrieval_experiment: RetrievalExperimentResponse,
        activation_mode: str = "shadow_eval",
    ) -> WinLossPolicyActivationResponse:
        mode = self._activation_mode(activation_mode)
        rules = self._policy_rules(learning, retrieval_experiment, mode)
        transitions = self._state_transitions(retrieval_experiment, rules, mode)
        checkpoints = self._checkpoints(retrieval_experiment, learning)
        owner_queue = self._owner_review_queue(rules, checkpoints)
        status = self._status(retrieval_experiment, checkpoints)
        return WinLossPolicyActivationResponse(
            title="Win/Loss Policy Activation Plan",
            status=status,
            activation_mode=mode,
            recommended_policy_id=retrieval_experiment.recommended_policy_id,
            policy_rules=rules,
            state_transitions=transitions,
            checkpoints=checkpoints,
            owner_review_queue=owner_queue,
            rollback_plan=self._rollback_plan(retrieval_experiment),
            governance_summary={
                "outcome_count": learning.outcome_count,
                "win_rate": learning.win_rate,
                "retrieval_experiment_status": retrieval_experiment.status,
                "recommended_policy_id": retrieval_experiment.recommended_policy_id,
                "approval_required": retrieval_experiment.governance_decision.get("approval_required", True),
                "score_delta_vs_baseline": retrieval_experiment.governance_decision.get("score_delta_vs_baseline"),
                "patterns_used": [
                    "typed_contracts",
                    "structured_outputs",
                    "state_machine_workflow",
                    "checkpointing",
                    "conditional_routing",
                    "traceable_node_transitions",
                ],
            },
            local_proof_commands=self._local_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def policy_pack(
        self,
        trace_id: str,
        activation_plan: WinLossPolicyActivationResponse,
        write_artifact: bool = True,
    ) -> WinLossPolicyPackResponse:
        pack = self._pack_payload(trace_id, activation_plan)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "win_loss_policy"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"win_loss_policy_activation_{safe_trace_id}.md"
            json_path = pack_dir / f"win_loss_policy_activation_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["win_loss_policy_markdown"] = artifact_path
            pack["artifact_paths"]["win_loss_policy_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return WinLossPolicyPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            activation_plan=activation_plan,
            trace_id=trace_id,
        )

    def _policy_rules(
        self,
        learning: WinLossLearningResponse,
        experiment: RetrievalExperimentResponse,
        mode: str,
    ) -> list[dict[str, Any]]:
        rules = []
        for index, recommendation in enumerate(learning.retrieval_recommendations[:8], start=1):
            rule_type = recommendation["type"]
            priority = recommendation["priority"]
            rule_state = self._rule_state(priority, experiment)
            rules.append(
                {
                    "rule_id": f"wlp-{index:02d}-{self._slug(recommendation['recommendation_id'])}",
                    "source_recommendation_id": recommendation["recommendation_id"],
                    "rule_type": rule_type,
                    "category": recommendation["category"],
                    "source": recommendation.get("source"),
                    "priority": priority,
                    "state": rule_state,
                    "activation_mode": mode,
                    "owner": self._owner(rule_type, recommendation["category"]),
                    "condition": self._condition(recommendation, experiment),
                    "action": recommendation["change"],
                    "query_expansion_terms": recommendation.get("query_expansion_terms", []),
                    "expected_impact": recommendation["expected_impact"],
                    "rollback_signal": self._rollback_signal(rule_type, recommendation["category"]),
                    "trace_refs": {
                        "learning_trace_id": learning.trace_id,
                        "experiment_trace_id": experiment.trace_id,
                        "recommended_policy_id": experiment.recommended_policy_id,
                    },
                }
            )
        return rules

    def _state_transitions(
        self,
        experiment: RetrievalExperimentResponse,
        rules: list[dict[str, Any]],
        mode: str,
    ) -> list[dict[str, Any]]:
        approval_required = bool(experiment.governance_decision.get("approval_required", True))
        target_after_draft = "human_review" if approval_required else mode
        active_rules = len([rule for rule in rules if rule["state"] != "blocked"])
        transitions = [
            {
                "transition_id": "draft-to-review-or-shadow",
                "from_state": "draft",
                "to_state": target_after_draft,
                "condition": "Learning and retrieval experiment outputs are present with typed activation rules.",
                "owner": "ai_engineering",
                "traceable": True,
            },
            {
                "transition_id": "shadow-to-review",
                "from_state": "shadow_eval",
                "to_state": "reviewer_approval",
                "condition": "Standard eval, red-team eval, and citation coverage checkpoints pass.",
                "owner": "ai_engineering",
                "traceable": True,
            },
            {
                "transition_id": "review-to-limited-rollout",
                "from_state": "reviewer_approval",
                "to_state": "limited_rollout",
                "condition": "Security, legal, sales, and proposal owners approve high-priority rules.",
                "owner": "proposal_manager",
                "traceable": True,
            },
            {
                "transition_id": "limited-rollout-to-active",
                "from_state": "limited_rollout",
                "to_state": "active",
                "condition": f"{active_rules} activation rule(s) complete one local shadow cycle without blockers.",
                "owner": "solutions",
                "traceable": True,
            },
            {
                "transition_id": "any-to-rolled-back",
                "from_state": "*",
                "to_state": "rolled_back",
                "condition": (
                    "Unsupported claims, lower retrieval score, or missed missing-evidence guardrail is detected."
                ),
                "owner": "ai_engineering",
                "traceable": True,
            },
        ]
        if target_after_draft == "human_review":
            transitions.insert(
                1,
                {
                    "transition_id": "human-review-to-shadow",
                    "from_state": "human_review",
                    "to_state": "shadow_eval",
                    "condition": "Governance blockers are dispositioned and reviewer approvals are attached.",
                    "owner": experiment.governance_decision.get("owner", "ai_engineering"),
                    "traceable": True,
                },
            )
        return transitions

    def _checkpoints(
        self,
        experiment: RetrievalExperimentResponse,
        learning: WinLossLearningResponse,
    ) -> list[dict[str, Any]]:
        blockers = list(experiment.governance_decision.get("blockers", []))
        return [
            {
                "checkpoint_id": "cp-standard-eval",
                "name": "Standard retrieval eval",
                "status": "required",
                "owner": "ai_engineering",
                "command": "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
                "pass_condition": "Pass/fail summary is PASS and citation coverage does not regress.",
            },
            {
                "checkpoint_id": "cp-red-team-missing-evidence",
                "name": "Red-team missing-evidence guardrail",
                "status": "blocked" if blockers else "required",
                "owner": "security",
                "command": "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
                "pass_condition": "Unsupported buyer claims are refused or routed to evidence-gap planning.",
                "blockers": blockers,
            },
            {
                "checkpoint_id": "cp-policy-shadow",
                "name": "Shadow retrieval policy comparison",
                "status": "required",
                "owner": "ai_engineering",
                "command": (
                    'curl -X POST "http://127.0.0.1:8000/rag/retrieval-experiments" '
                    '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
                ),
                "pass_condition": (
                    f"Recommended policy remains {experiment.recommended_policy_id} with non-negative baseline delta."
                ),
            },
            {
                "checkpoint_id": "cp-outcome-fixture-review",
                "name": "Outcome fixture reviewer signoff",
                "status": "required",
                "owner": "proposal_manager",
                "command": "rg \"outcome_id|missing_evidence|evidence_used\" sample_data/rfp_outcomes.json",
                "pass_condition": f"{learning.outcome_count} local outcome records are reviewed as fake demo inputs.",
            },
        ]

    def _owner_review_queue(
        self,
        rules: list[dict[str, Any]],
        checkpoints: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        queue: dict[str, dict[str, Any]] = {}
        for rule in rules:
            owner = rule["owner"]
            entry = queue.setdefault(
                owner,
                {
                    "owner": owner,
                    "review_type": "policy_rule_approval",
                    "items": [],
                    "required_before_state": "limited_rollout",
                },
            )
            entry["items"].append(rule["rule_id"])
        for checkpoint in checkpoints:
            owner = checkpoint["owner"]
            entry = queue.setdefault(
                owner,
                {
                    "owner": owner,
                    "review_type": "checkpoint_approval",
                    "items": [],
                    "required_before_state": "limited_rollout",
                },
            )
            entry["items"].append(checkpoint["checkpoint_id"])
            if checkpoint["status"] == "blocked":
                entry["required_before_state"] = "shadow_eval"
        return sorted(queue.values(), key=lambda item: item["owner"])

    def _rollback_plan(self, experiment: RetrievalExperimentResponse) -> dict[str, Any]:
        return {
            "rollback_state": "rolled_back",
            "default_policy_id": "baseline",
            "current_recommended_policy_id": experiment.recommended_policy_id,
            "triggers": [
                "Standard eval score falls below baseline.",
                "Red-team run finds an unsupported answer where the baseline refused or flagged missing evidence.",
                (
                    "Citation coverage decreases or source trust flags a boosted source as stale, conflicting, "
                    "or unapproved."
                ),
            ],
            "steps": [
                "Disable activation rules by setting their state to rolled_back in the generated policy artifact.",
                "Re-run retrieval experiments with baseline and balanced policies.",
                "Route failed categories to evidence-gap and source-trust review before another shadow cycle.",
            ],
        }

    def _pack_payload(self, trace_id: str, activation_plan: WinLossPolicyActivationResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Win/Loss Policy Activation Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "executive_summary": {
                "status": activation_plan.status,
                "activation_mode": activation_plan.activation_mode,
                "recommended_policy_id": activation_plan.recommended_policy_id,
                "rules": len(activation_plan.policy_rules),
                "checkpoints": len(activation_plan.checkpoints),
                "owner_reviews": len(activation_plan.owner_review_queue),
            },
            "policy_rules": activation_plan.policy_rules,
            "state_transitions": activation_plan.state_transitions,
            "checkpoints": activation_plan.checkpoints,
            "owner_review_queue": activation_plan.owner_review_queue,
            "rollback_plan": activation_plan.rollback_plan,
            "governance_summary": activation_plan.governance_summary,
            "proof_commands": activation_plan.local_proof_commands,
            "limitations": activation_plan.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        summary = pack["executive_summary"]
        lines = [
            "# Win/Loss Policy Activation Pack",
            "",
            "## Executive Summary",
            "",
            f"- Status: {summary['status']}",
            f"- Activation mode: {summary['activation_mode']}",
            f"- Recommended policy: {summary['recommended_policy_id']}",
            f"- Rules: {summary['rules']}",
            f"- Checkpoints: {summary['checkpoints']}",
            f"- Owner reviews: {summary['owner_reviews']}",
            "",
            "## Policy Rules",
            "",
            "| Rule | Type | Category | Priority | State | Owner |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for rule in pack["policy_rules"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._md(rule["rule_id"]),
                        self._md(rule["rule_type"]),
                        self._md(rule["category"]),
                        self._md(rule["priority"]),
                        self._md(rule["state"]),
                        self._md(rule["owner"]),
                    ]
                )
                + " |"
            )
        lines.extend(["", "## State Transitions", ""])
        for transition in pack["state_transitions"]:
            lines.append(
                f"- {transition['transition_id']}: {transition['from_state']} -> "
                f"{transition['to_state']} ({transition['owner']})"
            )
        lines.extend(["", "## Checkpoints", ""])
        for checkpoint in pack["checkpoints"]:
            lines.append(
                f"- {checkpoint['checkpoint_id']} [{checkpoint['status']}]: "
                f"{checkpoint['command']}"
            )
        lines.extend(["", "## Owner Review Queue", ""])
        for item in pack["owner_review_queue"]:
            lines.append(
                f"- {item['owner']}: {item['review_type']} before {item['required_before_state']} "
                f"({', '.join(item['items'])})"
            )
        lines.extend(["", "## Rollback Plan", ""])
        lines.append(f"- Rollback state: {pack['rollback_plan']['rollback_state']}")
        lines.append(f"- Default policy: {pack['rollback_plan']['default_policy_id']}")
        for trigger in pack["rollback_plan"]["triggers"]:
            lines.append(f"- Trigger: {trigger}")
        lines.extend(["", "## Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _status(self, experiment: RetrievalExperimentResponse, checkpoints: list[dict[str, Any]]) -> str:
        if any(checkpoint["status"] == "blocked" for checkpoint in checkpoints):
            return "human_review_required"
        if experiment.status == "ready_for_shadow_eval":
            return "ready_for_shadow_eval"
        return "draft"

    def _activation_mode(self, activation_mode: str) -> str:
        allowed = {"shadow_eval", "review_only", "limited_rollout"}
        return activation_mode if activation_mode in allowed else "shadow_eval"

    def _rule_state(self, priority: str, experiment: RetrievalExperimentResponse) -> str:
        if experiment.status != "ready_for_shadow_eval":
            return "blocked"
        if priority in {"critical", "high"}:
            return "shadow_ready"
        return "draft"

    def _condition(self, recommendation: dict[str, Any], experiment: RetrievalExperimentResponse) -> str:
        if recommendation["type"] == "source_boost":
            return (
                f"Apply only when query category is {recommendation['category']} and "
                f"{experiment.recommended_policy_id} remains above baseline."
            )
        return (
            f"Apply when query category is {recommendation['category']} and retrieved evidence lacks explicit "
            "approved citations."
        )

    def _owner(self, rule_type: str, category: str) -> str:
        if rule_type == "source_boost":
            return "ai_engineering"
        return {
            "security": "security",
            "compliance": "legal",
            "pricing": "finance",
            "support": "solutions",
            "implementation": "solutions",
            "ai_governance": "security",
        }.get(category, "proposal_manager")

    def _rollback_signal(self, rule_type: str, category: str) -> str:
        if rule_type == "source_boost":
            return f"Disable boost if {category} precision or citation coverage regresses in eval diagnostics."
        return f"Keep guardrail active until {category} missing-evidence red-team cases pass with explicit citations."

    def _local_commands(self) -> list[str]:
        return [
            (
                'curl -X POST "http://127.0.0.1:8000/learning/win-loss-policy" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/learning/win-loss-policy-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            'rg "win-loss-policy|Win/Loss Policy Activation|win_loss_policy" app dashboard docs README.md tests',
        ]

    def _limitations(self) -> list[str]:
        return [
            "Activation artifacts are local governance plans and do not mutate runtime retrieval defaults.",
            "Post-RFP outcomes are fake deterministic fixtures, not CRM records.",
            "Shadow and rollout states require human approval before production use.",
            "Rollback is represented as structured artifact guidance, not an automated feature flag integration.",
        ]

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "item"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
