from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.models.api import (
    AnalyzeResponse,
    EvaluationMetrics,
    PostRfpOutcome,
    WinLossLearningResponse,
    WinLossStrategyPackResponse,
    WinStrategyResponse,
)
from app.models.domain import RequirementMatrixRow


class WinLossLearningService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def learn(
        self,
        trace_id: str,
        outcomes: list[PostRfpOutcome] | None = None,
        outcomes_fixture_path: str = "sample_data/rfp_outcomes.json",
        analysis: AnalyzeResponse | None = None,
        requirement_matrix: list[RequirementMatrixRow] | None = None,
        win_strategy: WinStrategyResponse | None = None,
        eval_metrics: EvaluationMetrics | None = None,
        top_k_patterns: int = 6,
    ) -> WinLossLearningResponse:
        outcome_rows = outcomes or self.load_outcomes(outcomes_fixture_path)
        top_k = max(1, min(10, top_k_patterns))
        wins = [outcome for outcome in outcome_rows if outcome.result.lower() == "win"]
        losses = [outcome for outcome in outcome_rows if outcome.result.lower() == "loss"]
        pattern_summary = self._pattern_summary(
            outcome_rows,
            wins,
            losses,
            requirement_matrix,
            win_strategy,
            eval_metrics,
        )
        winning_patterns = self._winning_patterns(wins, losses, top_k)
        losing_patterns = self._losing_patterns(losses, top_k)
        retrieval_updates = self._retrieval_recommendations(winning_patterns, losing_patterns, requirement_matrix)
        eval_updates = self._eval_recommendations(winning_patterns, losing_patterns, eval_metrics)
        guidance = self._response_guidance(winning_patterns, losing_patterns, analysis, win_strategy)
        return WinLossLearningResponse(
            title="Win/Loss Learning Loop",
            outcome_count=len(outcome_rows),
            win_rate=round(len(wins) / len(outcome_rows), 2) if outcome_rows else 0.0,
            pattern_summary=pattern_summary,
            winning_evidence_patterns=winning_patterns,
            losing_risk_patterns=losing_patterns,
            retrieval_recommendations=retrieval_updates,
            eval_recommendations=eval_updates,
            response_guidance_updates=guidance,
            recommended_next_actions=self._next_actions(retrieval_updates, eval_updates, guidance),
            local_proof_commands=self._local_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def strategy_pack(
        self,
        trace_id: str,
        learning: WinLossLearningResponse,
        write_artifact: bool = True,
    ) -> WinLossStrategyPackResponse:
        pack = self._pack_payload(trace_id, learning)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "win_loss_packs"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"win_loss_strategy_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"win_loss_strategy_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["win_loss_markdown"] = artifact_path
            pack["artifact_paths"]["win_loss_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return WinLossStrategyPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            learning_response=learning,
            trace_id=trace_id,
        )

    def load_outcomes(self, fixture_path: str) -> list[PostRfpOutcome]:
        path = Path(fixture_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            sample_path = self.settings.sample_data_dir / fixture_path
            if sample_path.exists():
                path = sample_path
        if not path.exists():
            raise FileNotFoundError(f"Outcome fixture not found: {fixture_path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data["outcomes"] if isinstance(data, dict) and "outcomes" in data else data
        return [PostRfpOutcome.model_validate(row) for row in rows]

    def _pattern_summary(
        self,
        outcomes: list[PostRfpOutcome],
        wins: list[PostRfpOutcome],
        losses: list[PostRfpOutcome],
        matrix: list[RequirementMatrixRow] | None,
        win_strategy: WinStrategyResponse | None,
        eval_metrics: EvaluationMetrics | None,
    ) -> dict[str, Any]:
        category_counts = Counter(signal.category for outcome in outcomes for signal in outcome.evidence_used)
        win_categories = Counter(signal.category for outcome in wins for signal in outcome.evidence_used)
        loss_missing = Counter(self._category_for_text(item) for outcome in losses for item in outcome.missing_evidence)
        matrix_rows = matrix or []
        return {
            "wins": len(wins),
            "losses": len(losses),
            "total_deal_value": sum(outcome.deal_value for outcome in outcomes),
            "won_deal_value": sum(outcome.deal_value for outcome in wins),
            "top_evidence_categories": dict(category_counts.most_common(6)),
            "top_winning_categories": dict(win_categories.most_common(6)),
            "top_loss_gap_categories": dict(loss_missing.most_common(6)),
            "current_matrix_coverage": self._matrix_coverage(matrix_rows),
            "current_blocked_categories": dict(
                Counter(row.category for row in matrix_rows if row.status == "blocked" or row.risk_level == "high")
            ),
            "current_win_score": win_strategy.win_score if win_strategy else None,
            "current_win_level": win_strategy.win_level if win_strategy else None,
            "current_eval_passed": eval_metrics.passed if eval_metrics else None,
            "current_citation_coverage": eval_metrics.citation_coverage if eval_metrics else None,
        }

    def _winning_patterns(
        self,
        wins: list[PostRfpOutcome],
        losses: list[PostRfpOutcome],
        top_k: int,
    ) -> list[dict[str, Any]]:
        loss_categories = Counter(signal.category for outcome in losses for signal in outcome.evidence_used)
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for outcome in wins:
            for signal in outcome.evidence_used:
                grouped[(signal.category, signal.source)].append(
                    {
                        "outcome_id": outcome.outcome_id,
                        "claim": signal.claim,
                        "citation": signal.citation,
                        "strength": signal.strength,
                        "deal_value": outcome.deal_value,
                    }
                )
        patterns = []
        for (category, source), rows in grouped.items():
            avg_strength = sum(float(row["strength"]) for row in rows) / len(rows)
            score = round(avg_strength * 60 + len(rows) * 10 - loss_categories[category] * 4, 2)
            patterns.append(
                {
                    "pattern_id": f"win-{self._slug(category)}-{self._slug(source)}",
                    "category": category,
                    "source": source,
                    "wins_supported": len({row["outcome_id"] for row in rows}),
                    "avg_strength": round(avg_strength, 2),
                    "influenced_deal_value": sum(int(row["deal_value"]) for row in rows),
                    "score": score,
                    "representative_claims": list(dict.fromkeys(str(row["claim"]) for row in rows))[:3],
                    "citations": list(dict.fromkeys(str(row["citation"]) for row in rows))[:4],
                    "learning": self._winning_learning(category),
                }
            )
        return sorted(patterns, key=lambda item: (-item["score"], -item["wins_supported"], item["source"]))[:top_k]

    def _losing_patterns(self, losses: list[PostRfpOutcome], top_k: int) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for outcome in losses:
            for gap in outcome.missing_evidence:
                grouped[self._category_for_text(gap)].append(
                    {
                        "outcome_id": outcome.outcome_id,
                        "gap": gap,
                        "competitor": outcome.competitor,
                        "deal_value": outcome.deal_value,
                    }
                )
            for reason in outcome.win_loss_reasons:
                if any(term in reason.lower() for term in ["missing", "unsupported", "weak", "gap", "proof"]):
                    grouped[self._category_for_text(reason)].append(
                        {
                            "outcome_id": outcome.outcome_id,
                            "gap": reason,
                            "competitor": outcome.competitor,
                            "deal_value": outcome.deal_value,
                        }
                    )
        patterns = []
        for category, rows in grouped.items():
            patterns.append(
                {
                    "pattern_id": f"loss-{self._slug(category)}",
                    "category": category,
                    "losses_affected": len({row["outcome_id"] for row in rows}),
                    "at_risk_deal_value": sum(int(row["deal_value"]) for row in rows),
                    "severity": self._loss_severity(len(rows), sum(int(row["deal_value"]) for row in rows)),
                    "common_gaps": list(dict.fromkeys(str(row["gap"]) for row in rows))[:5],
                    "competitors": list(dict.fromkeys(str(row["competitor"]) for row in rows if row["competitor"]))[:4],
                    "learning": self._loss_learning(category),
                }
            )
        return sorted(patterns, key=lambda item: (-item["losses_affected"], -item["at_risk_deal_value"]))[:top_k]

    def _retrieval_recommendations(
        self,
        winning_patterns: list[dict[str, Any]],
        losing_patterns: list[dict[str, Any]],
        matrix: list[RequirementMatrixRow] | None,
    ) -> list[dict[str, Any]]:
        blocked_categories = Counter(
            row.category for row in (matrix or []) if row.status == "blocked" or row.risk_level == "high"
        )
        recommendations = []
        for pattern in winning_patterns[:4]:
            recommendations.append(
                {
                    "recommendation_id": f"retrieval-boost-{pattern['pattern_id']}",
                    "type": "source_boost",
                    "priority": "high" if pattern["score"] >= 60 else "medium",
                    "category": pattern["category"],
                    "source": pattern["source"],
                    "change": (
                        "Boost this source/category during answer retrieval and win-strategy proof-point ranking "
                        "when matching RFP requirements use the same buyer concern."
                    ),
                    "query_expansion_terms": self._query_terms(pattern["representative_claims"]),
                    "expected_impact": "Higher citation precision for evidence patterns associated with won pursuits.",
                }
            )
        for pattern in losing_patterns[:4]:
            recommendations.append(
                {
                    "recommendation_id": f"retrieval-gap-{pattern['pattern_id']}",
                    "type": "gap_guardrail",
                    "priority": "critical" if pattern["severity"] == "critical" else "high",
                    "category": pattern["category"],
                    "source": None,
                    "change": (
                        "Flag answers in this category when retrieval lacks explicit evidence; route to evidence-gap "
                        "planner before draft approval."
                    ),
                    "query_expansion_terms": self._query_terms(pattern["common_gaps"]),
                    "expected_impact": "Better missing-evidence detection for patterns associated with losses.",
                }
            )
        for category, count in blocked_categories.items():
            recommendations.append(
                {
                    "recommendation_id": f"retrieval-current-blocker-{self._slug(category)}",
                    "type": "current_rfp_blocker",
                    "priority": "high",
                    "category": category,
                    "source": None,
                    "change": f"Run targeted retrieval for {category} blockers before response export.",
                    "query_expansion_terms": [category, "approved evidence", "citation", "review"],
                    "expected_impact": f"Addresses {count} high-risk current matrix item(s).",
                }
            )
        return recommendations[:10]

    def _eval_recommendations(
        self,
        winning_patterns: list[dict[str, Any]],
        losing_patterns: list[dict[str, Any]],
        eval_metrics: EvaluationMetrics | None,
    ) -> list[dict[str, Any]]:
        recommendations = []
        for pattern in winning_patterns[:3]:
            recommendations.append(
                {
                    "recommendation_id": f"eval-win-{pattern['pattern_id']}",
                    "type": "positive_regression_case",
                    "priority": "medium",
                    "dataset": "sample_data/eval_dataset.json",
                    "prompt": f"Can we support {pattern['category']} claims with {pattern['source']} evidence?",
                    "expected_behavior": "Return cited answer using winning evidence source and no unsupported claims.",
                    "source_citations": pattern["citations"],
                }
            )
        for pattern in losing_patterns[:4]:
            recommendations.append(
                {
                    "recommendation_id": f"eval-loss-{pattern['pattern_id']}",
                    "type": "red_team_missing_evidence_case",
                    "priority": "high",
                    "dataset": "sample_data/red_team_questions.json",
                    "prompt": f"Can we guarantee the buyer requirement implied by: {pattern['common_gaps'][0]}?",
                    "expected_behavior": (
                        "Refuse or flag missing evidence unless an approved citation explicitly supports it."
                    ),
                    "source_citations": [],
                }
            )
        if eval_metrics and eval_metrics.citation_coverage < 0.9:
            recommendations.append(
                {
                    "recommendation_id": "eval-current-citation-coverage",
                    "type": "quality_threshold",
                    "priority": "high",
                    "dataset": "sample_data/eval_dataset.json",
                    "prompt": "Raise citation coverage for standard RFP evals before release.",
                    "expected_behavior": f"Improve citation coverage from {eval_metrics.citation_coverage} toward 0.9.",
                    "source_citations": [],
                }
            )
        return recommendations[:10]

    def _response_guidance(
        self,
        winning_patterns: list[dict[str, Any]],
        losing_patterns: list[dict[str, Any]],
        analysis: AnalyzeResponse | None,
        win_strategy: WinStrategyResponse | None,
    ) -> list[dict[str, Any]]:
        guidance = []
        for pattern in winning_patterns[:4]:
            guidance.append(
                {
                    "guidance_id": f"guidance-{pattern['pattern_id']}",
                    "section": self._section_for_category(pattern["category"]),
                    "instruction": (
                        f"Lead with {pattern['category']} evidence from {pattern['source']} when the requirement "
                        "matches this concern."
                    ),
                    "proof_required": pattern["citations"],
                    "approval_note": "Allowed only when the cited local evidence still applies to the current buyer.",
                }
            )
        for pattern in losing_patterns[:4]:
            guidance.append(
                {
                    "guidance_id": f"guardrail-{pattern['pattern_id']}",
                    "section": self._section_for_category(pattern["category"]),
                    "instruction": (
                        f"Do not make {pattern['category']} claims without explicit citations; losses showed "
                        f"{pattern['losses_affected']} affected pursuit(s)."
                    ),
                    "proof_required": pattern["common_gaps"],
                    "approval_note": (
                        "Route to security, legal, finance, or solutions based on category before final draft."
                    ),
                }
            )
        if analysis and analysis.deadlines:
            guidance.append(
                {
                    "guidance_id": "guidance-deadline-risk",
                    "section": "Executive Summary",
                    "instruction": (
                        "Connect evidence-gap closure to detected submission deadline(s): "
                        f"{', '.join(analysis.deadlines)}."
                    ),
                    "proof_required": analysis.deadlines,
                    "approval_note": "Use in timeline and submission-decision artifacts.",
                }
            )
        if win_strategy:
            guidance.append(
                {
                    "guidance_id": "guidance-current-win-posture",
                    "section": "Win Strategy",
                    "instruction": win_strategy.recommended_response_posture,
                    "proof_required": [point["claim"] for point in win_strategy.proof_points[:3]],
                    "approval_note": (
                        f"Current directional win score is {win_strategy.win_score}/{win_strategy.win_level}."
                    ),
                }
            )
        return guidance[:10]

    def _next_actions(
        self,
        retrieval_updates: list[dict[str, Any]],
        eval_updates: list[dict[str, Any]],
        guidance: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "owner": "solutions",
                "action": "Apply high-priority retrieval boosts and gap guardrails to the next RFP answer pass.",
                "inputs": [item["recommendation_id"] for item in retrieval_updates[:4]],
            },
            {
                "owner": "ai_engineering",
                "action": "Convert learning recommendations into deterministic eval and red-team fixture rows.",
                "inputs": [item["recommendation_id"] for item in eval_updates[:5]],
            },
            {
                "owner": "proposal_manager",
                "action": "Update response guidance and reviewer checklist before package export.",
                "inputs": [item["guidance_id"] for item in guidance[:5]],
            },
        ]

    def _pack_payload(self, trace_id: str, learning: WinLossLearningResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Win/Loss Learning Strategy Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "executive_summary": {
                "outcome_count": learning.outcome_count,
                "win_rate": learning.win_rate,
                "wins": learning.pattern_summary["wins"],
                "losses": learning.pattern_summary["losses"],
                "recommendation": (
                    "Use prior post-RFP outcomes to boost evidence patterns that helped wins and block unsupported "
                    "claims that contributed to losses."
                ),
            },
            "winning_evidence_patterns": learning.winning_evidence_patterns,
            "losing_risk_patterns": learning.losing_risk_patterns,
            "retrieval_recommendations": learning.retrieval_recommendations,
            "eval_recommendations": learning.eval_recommendations,
            "response_guidance_updates": learning.response_guidance_updates,
            "owner_action_plan": learning.recommended_next_actions,
            "proof_commands": learning.local_proof_commands,
            "limitations": learning.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        summary = pack["executive_summary"]
        lines = [
            "# Win/Loss Learning Strategy Pack",
            "",
            "## Executive Summary",
            "",
            f"- Outcomes analyzed: {summary['outcome_count']}",
            f"- Win rate: {summary['win_rate']}",
            f"- Wins: {summary['wins']}",
            f"- Losses: {summary['losses']}",
            f"- Recommendation: {summary['recommendation']}",
            "",
            "## Winning Evidence Patterns",
            "",
            "| Pattern | Category | Source | Wins | Score | Citations |",
            "| --- | --- | --- | ---: | ---: | --- |",
        ]
        for pattern in pack["winning_evidence_patterns"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._md(pattern["pattern_id"]),
                        self._md(pattern["category"]),
                        self._md(pattern["source"]),
                        self._md(pattern["wins_supported"]),
                        self._md(pattern["score"]),
                        self._md(", ".join(pattern["citations"])),
                    ]
                )
                + " |"
            )
        lines.extend(["", "## Losing Risk Patterns", ""])
        for pattern in pack["losing_risk_patterns"]:
            lines.append(
                f"- {pattern['pattern_id']} ({pattern['severity']}): "
                f"{'; '.join(pattern['common_gaps'])}"
            )
        lines.extend(["", "## Retrieval Recommendations", ""])
        for item in pack["retrieval_recommendations"]:
            lines.append(f"- {item['priority']} | {item['type']} | {item['category']}: {item['change']}")
        lines.extend(["", "## Eval Recommendations", ""])
        for item in pack["eval_recommendations"]:
            lines.append(f"- {item['priority']} | {item['dataset']}: {item['prompt']}")
        lines.extend(["", "## Response Guidance Updates", ""])
        for item in pack["response_guidance_updates"]:
            lines.append(f"- {item['section']}: {item['instruction']}")
        lines.extend(["", "## Owner Action Plan", ""])
        for item in pack["owner_action_plan"]:
            lines.append(f"- {item['owner']}: {item['action']}")
        lines.extend(["", "## Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Win/Loss Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _matrix_coverage(self, matrix: list[RequirementMatrixRow]) -> float:
        if not matrix:
            return 0.0
        covered = sum(1 for row in matrix if row.evidence_refs and not row.missing_evidence)
        return round(covered / len(matrix), 2)

    def _category_for_text(self, text: str) -> str:
        lowered = text.lower()
        terms = {
            "security": ["sso", "encryption", "security", "incident", "audit", "mfa"],
            "compliance": ["soc", "gdpr", "hipaa", "fedramp", "stateramp", "compliance", "dpa"],
            "pricing": ["pricing", "discount", "commercial", "price", "payment", "margin"],
            "implementation": ["implementation", "timeline", "migration", "deployment", "onboarding"],
            "support": ["support", "sla", "uptime", "availability", "rto", "rpo"],
            "ai_governance": ["ai", "model", "bias", "governance", "logging"],
        }
        for category, category_terms in terms.items():
            if any(term in lowered for term in category_terms):
                return category
        return "general"

    def _winning_learning(self, category: str) -> str:
        return {
            "security": "Security wins correlate with explicit identity, encryption, audit, and incident evidence.",
            "compliance": "Compliance wins correlate with named frameworks and controlled approval language.",
            "pricing": "Commercial wins correlate with value framing and approved packaging boundaries.",
            "implementation": "Implementation wins correlate with phased rollout, named owners, and validation proof.",
            "support": "Support wins correlate with operational coverage, SLA boundaries, and escalation clarity.",
        }.get(category, "Winning responses show stronger outcomes when claims are tied to approved local proof.")

    def _loss_learning(self, category: str) -> str:
        return {
            "security": "Security losses are amplified when unsupported guarantees or missing control evidence appear.",
            "compliance": "Compliance losses are amplified by missing attestations or over-claimed regulatory posture.",
            "pricing": "Pricing losses are amplified by weak discount guardrails or unclear commercial assumptions.",
            "implementation": "Implementation losses are amplified by vague timelines and absent owner commitments.",
            "support": "Support losses are amplified by unsupported uptime, RTO, RPO, or support claims.",
        }.get(category, "Losses correlate with unsupported claims, weak citations, and missing reviewer approval.")

    def _loss_severity(self, count: int, deal_value: int) -> str:
        if count >= 3 or deal_value >= 1_000_000:
            return "critical"
        if count >= 2 or deal_value >= 500_000:
            return "high"
        return "medium"

    def _section_for_category(self, category: str) -> str:
        return {
            "security": "Security Response",
            "compliance": "Compliance Response",
            "pricing": "Commercial Response",
            "implementation": "Implementation Plan",
            "support": "Support and SLA Response",
            "ai_governance": "AI Governance Response",
        }.get(category, "Executive Summary")

    def _query_terms(self, values: list[str]) -> list[str]:
        stop_words = {"and", "are", "for", "from", "must", "the", "this", "with", "that", "into"}
        tokens = []
        for value in values:
            tokens.extend(re.findall(r"[a-zA-Z0-9]{3,}", value.lower()))
        return [token for token, _ in Counter(token for token in tokens if token not in stop_words).most_common(8)]

    def _local_commands(self) -> list[str]:
        return [
            (
                'curl -X POST "http://127.0.0.1:8000/learning/win-loss" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/learning/win-loss-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m pytest -q",
            "python -m ruff check .",
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            "python scripts\\dashboard_smoke.py",
            "python -m app.demo",
            (
                'rg "learning/win-loss|Win/Loss Learning|win_loss_packs|rfp_outcomes" '
                "app dashboard docs README.md tests sample_data Makefile"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Outcome records are fake local fixtures for deterministic portfolio demonstration.",
            (
                "The learning loop does not update a live vector index, CRM, pricing system, "
                "or eval dataset automatically."
            ),
            "Recommendations are deterministic heuristics and require human approval before production use.",
            "External services remain optional; the default path uses local sample outcomes and mock behavior.",
        ]

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "item"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
