from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    BidRoiPackResponse,
    BidScenario,
    BidScenarioAnalysisResponse,
    ContractRiskResponse,
    DealReadinessScorecardResponse,
    ProcurementQuestionRiskResponse,
    SubmissionDecisionResponse,
    TimelinePlanResponse,
    WinStrategyResponse,
)
from app.models.domain import CustomerProfile, EvidenceGap, RequirementMatrixRow


class BidScenarioSimulatorService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.blended_hourly_cost = 150

    def scenario_analysis(
        self,
        trace_id: str,
        requirement_matrix: list[RequirementMatrixRow],
        customer_profiles: list[CustomerProfile],
        readiness_scorecard: DealReadinessScorecardResponse | None = None,
        win_strategy: WinStrategyResponse | None = None,
        submission_decision: SubmissionDecisionResponse | None = None,
        evidence_gaps: list[EvidenceGap] | None = None,
        contract_risk: ContractRiskResponse | None = None,
        timeline_plan: TimelinePlanResponse | None = None,
        procurement_risk: ProcurementQuestionRiskResponse | None = None,
    ) -> BidScenarioAnalysisResponse:
        gaps = evidence_gaps or []
        profiles = {profile.id: profile for profile in customer_profiles}
        base = self._base_context(
            matrix=requirement_matrix,
            readiness=readiness_scorecard,
            win_strategy=win_strategy,
            submission_decision=submission_decision,
            gaps=gaps,
            contract_risk=contract_risk,
            timeline=timeline_plan,
            procurement=procurement_risk,
        )
        scenarios = [
            self._scenario(
                spec={
                    "scenario_id": "pursue-standard-enterprise",
                    "name": "Pursue: enterprise fit with controlled proof posture",
                    "profile_id": "fintech",
                    "deal_value": 820000,
                    "effort_hours": 210,
                    "gross_margin": 0.72,
                    "win_probability": 0.64,
                    "evidence_modifier": 1.12,
                    "timeline_status": "manageable",
                    "days_to_deadline": 39,
                    "decision_hint": "pursue",
                    "blockers": [],
                    "assumptions": [
                        "Standard commercial terms are accepted.",
                        "Existing security and implementation proof points can be reused without new exceptions.",
                    ],
                },
                base=base,
                profiles=profiles,
            ),
            self._scenario(
                spec={
                    "scenario_id": "pursue-with-conditions-regulated",
                    "name": "Pursue with conditions: regulated buyer and explicit approvals",
                    "profile_id": "regulated_healthcare",
                    "deal_value": 650000,
                    "effort_hours": 320,
                    "gross_margin": 0.68,
                    "win_probability": 0.48,
                    "evidence_modifier": 0.94,
                    "timeline_status": "compressed",
                    "days_to_deadline": 24,
                    "decision_hint": "pursue_with_conditions",
                    "blockers": [
                        self._blocker(
                            "evidence_gap",
                            "high",
                            "security",
                            "Security, privacy, and support answers need explicit approval before submission.",
                            "Customer-facing claims require cited evidence and reviewer signoff.",
                        ),
                        self._blocker(
                            "procurement",
                            "medium",
                            "legal",
                            "Procurement approval workflow still has reviewer-required questions.",
                            "Final response can proceed only with tracked exception owners.",
                        ),
                    ],
                    "assumptions": [
                        "Executive sponsor accepts listed evidence and procurement exceptions.",
                        "Security, legal, and finance reviews finish before final QA.",
                    ],
                },
                base=base,
                profiles=profiles,
            ),
            self._scenario(
                spec={
                    "scenario_id": "no-bid-compliance-evidence",
                    "name": "No-bid: compliance and evidence risk outweighs value",
                    "profile_id": "public_sector",
                    "deal_value": 900000,
                    "effort_hours": 570,
                    "gross_margin": 0.62,
                    "win_probability": 0.18,
                    "evidence_modifier": 0.42,
                    "timeline_status": "at_risk",
                    "days_to_deadline": 31,
                    "decision_hint": "no_bid_compliance_evidence",
                    "blockers": [
                        self._blocker(
                            "compliance",
                            "critical",
                            "legal",
                            "StateRAMP/FedRAMP-style evidence is not present in the local corpus.",
                            "Unsupported compliance claims could create disqualifying submission risk.",
                        ),
                        self._blocker(
                            "evidence_gap",
                            "critical",
                            "security",
                            "High-risk security and privacy answers cannot be fully proven from approved sources.",
                            "The package would require executive exceptions instead of evidence.",
                        ),
                    ],
                    "assumptions": [
                        "Buyer will score unsupported compliance claims as non-responsive.",
                        "New attestations cannot be produced inside the response window.",
                    ],
                },
                base=base,
                profiles=profiles,
            ),
            self._scenario(
                spec={
                    "scenario_id": "no-bid-commercial-timeline",
                    "name": "No-bid: commercial exposure and timeline compression",
                    "profile_id": "regulated_healthcare",
                    "deal_value": 360000,
                    "effort_hours": 520,
                    "gross_margin": 0.55,
                    "win_probability": 0.22,
                    "evidence_modifier": 0.78,
                    "timeline_status": "blocked",
                    "days_to_deadline": 12,
                    "decision_hint": "no_bid_commercial_timeline",
                    "blockers": [
                        self._blocker(
                            "pricing",
                            "high",
                            "finance",
                            "Discount, payment, and usage assumptions are not approved.",
                            "Risk-adjusted margin cannot justify the bid effort.",
                        ),
                        self._blocker(
                            "timeline",
                            "critical",
                            "proposal_manager",
                            "Legal, security, pricing, and final QA gates collide inside a compressed window.",
                            "Late approvals would create an incomplete or non-compliant response.",
                        ),
                    ],
                    "assumptions": [
                        "Deadline cannot move and the buyer requires full legal/commercial exceptions up front.",
                        "The account team cannot reduce scope or attach a paid discovery phase.",
                    ],
                },
                base=base,
                profiles=profiles,
            ),
        ]
        ranked = sorted(
            scenarios,
            key=lambda scenario: (
                scenario.decision_recommendation != "pursue",
                -scenario.risk_adjusted_roi,
                -scenario.win_probability,
            ),
        )
        return BidScenarioAnalysisResponse(
            title="Bid/No-Bid Scenario Simulator + ROI Impact",
            scenarios=scenarios,
            recommended_scenario_id=ranked[0].scenario_id,
            coverage_summary=self._coverage_summary(base, scenarios),
            local_proof_commands=self._local_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def export_roi_pack(
        self,
        trace_id: str,
        scenario_analysis: BidScenarioAnalysisResponse,
        write_artifact: bool = True,
    ) -> BidRoiPackResponse:
        pack = self._pack_payload(trace_id, scenario_analysis)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "bid_packs"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"bid_roi_impact_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"bid_roi_impact_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["bid_roi_markdown"] = artifact_path
            pack["artifact_paths"]["bid_roi_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return BidRoiPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            scenario_analysis=scenario_analysis,
            trace_id=trace_id,
        )

    def _scenario(
        self,
        spec: dict[str, Any],
        base: dict[str, Any],
        profiles: dict[str, CustomerProfile],
    ) -> BidScenario:
        evidence_coverage = self._clamp(base["evidence_coverage"] * spec["evidence_modifier"], 0.05, 0.98)
        profile = profiles.get(spec["profile_id"]) or next(iter(profiles.values()))
        scenario_blockers = list(spec["blockers"])
        scenario_blockers.extend(self._contextual_blockers(spec, base, evidence_coverage))
        required_reviewers = self._required_reviewers(scenario_blockers, base, spec["decision_hint"])
        win_probability = self._clamp(float(spec["win_probability"]), 0.05, 0.85)
        deal_value = int(spec["deal_value"])
        effort_hours = int(spec["effort_hours"])
        pursuit_cost = effort_hours * self.blended_hourly_cost
        gross_margin = float(spec["gross_margin"])
        risk_adjusted_revenue = round(deal_value * win_probability)
        risk_adjusted_gross_profit = round(deal_value * gross_margin * win_probability)
        risk_adjusted_roi = round((risk_adjusted_gross_profit - pursuit_cost) / pursuit_cost, 2)
        decision = self._decision(
            hint=spec["decision_hint"],
            roi=risk_adjusted_roi,
            win_probability=win_probability,
            blockers=scenario_blockers,
        )
        return BidScenario(
            scenario_id=spec["scenario_id"],
            name=spec["name"],
            decision_recommendation=decision,
            deal_value=deal_value,
            pursuit_effort_hours=effort_hours,
            pursuit_cost=pursuit_cost,
            win_probability=round(win_probability, 2),
            gross_margin=round(gross_margin, 2),
            risk_adjusted_revenue=risk_adjusted_revenue,
            risk_adjusted_gross_profit=risk_adjusted_gross_profit,
            risk_adjusted_roi=risk_adjusted_roi,
            roi_formula=(
                f"(({deal_value} * {gross_margin:.2f} * {win_probability:.2f}) - {pursuit_cost}) "
                f"/ {pursuit_cost} = {risk_adjusted_roi}"
            ),
            blockers=scenario_blockers,
            required_reviewers=required_reviewers,
            evidence_readiness={
                "coverage_ratio": round(evidence_coverage, 2),
                "coverage_status": self._evidence_status(evidence_coverage, scenario_blockers),
                "high_severity_gap_count": base["high_severity_gap_count"],
                "unsupported_procurement_claims": base["unsupported_procurement_claims"],
                "sample_source_count": base["sample_source_count"],
            },
            timeline_pressure={
                "status": spec["timeline_status"],
                "days_to_deadline": spec["days_to_deadline"],
                "submission_deadline": base["submission_deadline"],
                "blocked_timeline_items": base["timeline_blocked_count"],
                "readiness_gate": base["readiness_level"],
            },
            coverage_summary={
                "requirements": base["requirements"],
                "readiness_score": base["readiness_score"],
                "win_score": base["win_score"],
                "submission_decision": base["submission_decision"],
                "contract_status": base["contract_status"],
                "pricing_risk": base["pricing_risk"],
                "procurement_blocked": base["procurement_blocked"],
                "procurement_approvals_required": base["procurement_approvals_required"],
                "risk_adjusted_roi": risk_adjusted_roi,
            },
            customer_profile={
                "id": profile.id,
                "name": profile.name,
                "industry": profile.industry,
                "region": profile.region,
                "risk_tolerance": profile.risk_tolerance,
                "compliance_frameworks": profile.compliance_frameworks,
            },
            assumptions=[
                *spec["assumptions"],
                "ROI is directional and based on local sample data, not CRM, billing, or labor systems.",
            ],
        )

    def _base_context(
        self,
        matrix: list[RequirementMatrixRow],
        readiness: DealReadinessScorecardResponse | None,
        win_strategy: WinStrategyResponse | None,
        submission_decision: SubmissionDecisionResponse | None,
        gaps: list[EvidenceGap],
        contract_risk: ContractRiskResponse | None,
        timeline: TimelinePlanResponse | None,
        procurement: ProcurementQuestionRiskResponse | None,
    ) -> dict[str, Any]:
        evidence_coverage = readiness.evidence_coverage if readiness else self._matrix_evidence_coverage(matrix)
        procurement_summary = procurement.approval_summary if procurement else {}
        procurement_coverage = procurement.coverage_summary if procurement else {}
        return {
            "requirements": len(matrix),
            "sample_source_count": len({source for row in matrix for source in row.evidence_refs}),
            "evidence_coverage": evidence_coverage,
            "readiness_score": readiness.readiness_score if readiness else None,
            "readiness_level": readiness.readiness_level if readiness else None,
            "readiness_blockers": readiness.blockers if readiness else [],
            "win_score": win_strategy.win_score if win_strategy else None,
            "win_level": win_strategy.win_level if win_strategy else None,
            "pricing_risk": win_strategy.pricing_risk.get("risk_level") if win_strategy else None,
            "submission_decision": submission_decision.decision if submission_decision else None,
            "submission_score": submission_decision.score if submission_decision else None,
            "contract_status": contract_risk.status if contract_risk else None,
            "contract_risk_score": contract_risk.risk_score if contract_risk else None,
            "high_severity_gap_count": sum(1 for gap in gaps if gap.severity in {"critical", "high"}),
            "gap_count": len(gaps),
            "timeline_blocked_count": timeline.summary.get("blocked_count", 0) if timeline else 0,
            "submission_deadline": timeline.summary.get("submission_deadline") if timeline else "2026-07-18",
            "procurement_blocked": procurement_summary.get("blocked_count", 0),
            "procurement_approvals_required": procurement_summary.get("approvals_required_count", 0),
            "unsupported_procurement_claims": procurement_coverage.get("unsupported_claim_count", 0),
            "procurement_reviewer_counts": procurement_summary.get("reviewer_role_counts", {}),
        }

    def _coverage_summary(self, base: dict[str, Any], scenarios: list[BidScenario]) -> dict[str, Any]:
        decision_counts = Counter(scenario.decision_recommendation for scenario in scenarios)
        return {
            "scenario_count": len(scenarios),
            "decision_counts": dict(sorted(decision_counts.items())),
            "requirements": base["requirements"],
            "base_readiness_score": base["readiness_score"],
            "base_win_score": base["win_score"],
            "base_evidence_coverage": base["evidence_coverage"],
            "base_submission_decision": base["submission_decision"],
            "base_contract_status": base["contract_status"],
            "base_procurement_blocked": base["procurement_blocked"],
            "best_risk_adjusted_roi": max(scenario.risk_adjusted_roi for scenario in scenarios),
            "worst_risk_adjusted_roi": min(scenario.risk_adjusted_roi for scenario in scenarios),
            "required_reviewer_count": len(
                {reviewer for scenario in scenarios for reviewer in scenario.required_reviewers}
            ),
        }

    def _pack_payload(self, trace_id: str, scenario_analysis: BidScenarioAnalysisResponse) -> dict[str, Any]:
        scenarios = [scenario.model_dump(mode="json") for scenario in scenario_analysis.scenarios]
        recommended = next(
            scenario for scenario in scenarios if scenario["scenario_id"] == scenario_analysis.recommended_scenario_id
        )
        return {
            "trace_id": trace_id,
            "title": "Bid/No-Bid Scenario Simulator + ROI Impact Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "executive_decision_memo": {
                "recommendation": recommended["decision_recommendation"],
                "recommended_scenario_id": recommended["scenario_id"],
                "recommended_scenario": recommended["name"],
                "risk_adjusted_roi": recommended["risk_adjusted_roi"],
                "win_probability": recommended["win_probability"],
                "summary": (
                    "Pursue only where risk-adjusted ROI, evidence readiness, reviewer coverage, and timeline "
                    "pressure support an executive-approved bid."
                ),
            },
            "scenario_comparison_table": [
                {
                    "scenario": scenario["name"],
                    "recommendation": scenario["decision_recommendation"],
                    "deal_value": scenario["deal_value"],
                    "effort_hours": scenario["pursuit_effort_hours"],
                    "win_probability": scenario["win_probability"],
                    "risk_adjusted_roi": scenario["risk_adjusted_roi"],
                    "blocker_count": len(scenario["blockers"]),
                    "required_reviewers": ", ".join(scenario["required_reviewers"]),
                }
                for scenario in scenarios
            ],
            "roi_math": [
                {
                    "scenario_id": scenario["scenario_id"],
                    "risk_adjusted_revenue": scenario["risk_adjusted_revenue"],
                    "risk_adjusted_gross_profit": scenario["risk_adjusted_gross_profit"],
                    "pursuit_cost": scenario["pursuit_cost"],
                    "risk_adjusted_roi": scenario["risk_adjusted_roi"],
                    "formula": scenario["roi_formula"],
                }
                for scenario in scenarios
            ],
            "blockers": self._pack_blockers(scenarios),
            "follow_up_owners": self._follow_up_owners(scenarios),
            "proof_commands": scenario_analysis.local_proof_commands,
            "limitations": scenario_analysis.limitations,
            "scenario_analysis_summary": scenario_analysis.coverage_summary,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        memo = pack["executive_decision_memo"]
        lines = [
            "# Bid/No-Bid Scenario Simulator + ROI Impact Pack",
            "",
            "## Executive Decision Memo",
            "",
            f"- Recommendation: {memo['recommendation']}",
            f"- Recommended scenario: {memo['recommended_scenario']}",
            f"- risk-adjusted ROI: {memo['risk_adjusted_roi']}",
            f"- Win probability: {memo['win_probability']}",
            f"- Summary: {memo['summary']}",
            "",
            "## Scenario Comparison Table",
            "",
            (
                "| Scenario | Recommendation | Deal Value | Effort Hours | Win Probability | "
                "risk-adjusted ROI | Blockers | Reviewers |"
            ),
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
        for row in pack["scenario_comparison_table"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._md(row["scenario"]),
                        self._md(row["recommendation"]),
                        self._md(row["deal_value"]),
                        self._md(row["effort_hours"]),
                        self._md(row["win_probability"]),
                        self._md(row["risk_adjusted_roi"]),
                        self._md(row["blocker_count"]),
                        self._md(row["required_reviewers"]),
                    ]
                )
                + " |"
            )
        lines.extend(["", "## ROI Math", ""])
        for item in pack["roi_math"]:
            lines.extend(
                [
                    f"### {item['scenario_id']}",
                    "",
                    f"- Risk-adjusted revenue: {item['risk_adjusted_revenue']}",
                    f"- Risk-adjusted gross profit: {item['risk_adjusted_gross_profit']}",
                    f"- Pursuit cost: {item['pursuit_cost']}",
                    f"- risk-adjusted ROI: {item['risk_adjusted_roi']}",
                    f"- Formula: `{item['formula']}`",
                    "",
                ]
            )
        lines.extend(["## Blockers", ""])
        if pack["blockers"]:
            for blocker in pack["blockers"]:
                lines.append(
                    f"- {blocker['scenario_id']} | {blocker['severity']} | {blocker['owner']}: "
                    f"{blocker['blocker']} Impact: {blocker['impact']}"
                )
        else:
            lines.append("- None")
        lines.extend(["", "## Follow-Up Owners", ""])
        for owner in pack["follow_up_owners"]:
            lines.append(
                f"- {owner['owner']}: {owner['scenario_count']} scenario(s), "
                f"highest severity={owner['highest_severity']}, actions={'; '.join(owner['actions'])}"
            )
        lines.extend(["", "## Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## ROI Impact Pack Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _pack_blockers(self, scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {"scenario_id": scenario["scenario_id"], **blocker}
            for scenario in scenarios
            for blocker in scenario["blockers"]
        ]

    def _follow_up_owners(self, scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
        owner_map: dict[str, list[dict[str, Any]]] = {}
        for scenario in scenarios:
            for blocker in scenario["blockers"]:
                owner_map.setdefault(blocker["owner"], []).append({"scenario": scenario["scenario_id"], **blocker})
        rows = []
        for owner, blockers in sorted(owner_map.items()):
            severity = self._highest_severity(blocker["severity"] for blocker in blockers)
            rows.append(
                {
                    "owner": owner,
                    "scenario_count": len({blocker["scenario"] for blocker in blockers}),
                    "highest_severity": severity,
                    "actions": [
                        f"{blocker['scenario']}: {blocker['blocker']}"
                        for blocker in blockers[:3]
                    ],
                }
            )
        return rows

    def _contextual_blockers(
        self,
        spec: dict[str, Any],
        base: dict[str, Any],
        evidence_coverage: float,
    ) -> list[dict[str, Any]]:
        blockers = []
        if spec["decision_hint"] == "pursue":
            return blockers
        if (
            base["contract_status"] in {"critical", "high_risk"}
            and spec["decision_hint"] != "no_bid_commercial_timeline"
        ):
            blockers.append(
                self._blocker(
                    "contract",
                    "high",
                    "legal",
                    f"Base contract status is {base['contract_status']}.",
                    "Legal must approve redlines before any pursuit recommendation is final.",
                )
            )
        if evidence_coverage < 0.55:
            blockers.append(
                self._blocker(
                    "evidence_readiness",
                    "high",
                    "solutions",
                    "Evidence coverage is below the no-bid threshold.",
                    "The response would rely on assumptions instead of approved proof.",
                )
            )
        if base["procurement_blocked"] and spec["decision_hint"] in {
            "pursue_with_conditions",
            "no_bid_compliance_evidence",
        }:
            blockers.append(
                self._blocker(
                    "procurement",
                    "high",
                    "proposal_manager",
                    f"{base['procurement_blocked']} procurement answer(s) are blocked.",
                    "Blocked buyer questions must be removed, cited, or approved as explicit exceptions.",
                )
            )
        return blockers

    def _decision(
        self,
        hint: str,
        roi: float,
        win_probability: float,
        blockers: list[dict[str, Any]],
    ) -> str:
        if hint.startswith("no_bid"):
            return "no_bid"
        critical = any(blocker["severity"] == "critical" for blocker in blockers)
        high = any(blocker["severity"] == "high" for blocker in blockers)
        if roi >= 2.0 and win_probability >= 0.55 and not high and not critical:
            return "pursue"
        if roi >= 0.75 and win_probability >= 0.35 and not critical:
            return "pursue_with_conditions"
        return "no_bid"

    def _required_reviewers(
        self,
        blockers: list[dict[str, Any]],
        base: dict[str, Any],
        hint: str,
    ) -> list[str]:
        reviewers = {"sales_leadership", "proposal_manager"}
        owner_to_reviewer = {
            "security": "security",
            "legal": "legal",
            "finance": "finance",
            "solutions": "solutions",
            "proposal_manager": "proposal_manager",
        }
        reviewers.update(owner_to_reviewer.get(blocker["owner"], blocker["owner"]) for blocker in blockers)
        if base["pricing_risk"] in {"medium", "high"} or "commercial" in hint:
            reviewers.add("finance")
        if base["contract_status"] in {"needs_legal_review", "high_risk", "critical"}:
            reviewers.add("legal")
        if base["unsupported_procurement_claims"] or "compliance" in hint:
            reviewers.add("security")
        if hint != "pursue":
            reviewers.add("executive_sponsor")
        return sorted(reviewers)

    def _blocker(self, source: str, severity: str, owner: str, blocker: str, impact: str) -> dict[str, Any]:
        return {
            "source": source,
            "severity": severity,
            "owner": owner,
            "blocker": blocker,
            "impact": impact,
        }

    def _evidence_status(self, evidence_coverage: float, blockers: list[dict[str, Any]]) -> str:
        if any(blocker["source"] in {"compliance", "evidence_gap", "evidence_readiness"} for blocker in blockers):
            return "blocked"
        if evidence_coverage >= 0.85:
            return "ready"
        if evidence_coverage >= 0.65:
            return "conditional"
        return "not_ready"

    def _matrix_evidence_coverage(self, matrix: list[RequirementMatrixRow]) -> float:
        if not matrix:
            return 0.0
        covered = sum(1 for row in matrix if row.evidence_refs and not row.missing_evidence)
        return round(covered / len(matrix), 2)

    def _highest_severity(self, severities: Any) -> str:
        order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        return max(severities, key=lambda severity: order.get(str(severity), 0), default="low")

    def _clamp(self, value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    def _local_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/bid/scenario-analysis" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/bid/roi-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m pytest -q",
            "python -m ruff check .",
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            "python scripts\\dashboard_smoke.py",
            "python -m app.demo",
            (
                'rg "bid/scenario-analysis|bid/roi-pack|Bid/No-Bid|ROI Impact|bid_packs|'
                'risk-adjusted ROI" app dashboard docs README.md tests scripts sample_data Makefile'
            ),
            (
                "Get-ChildItem -Recurse -File storage\\bid_packs -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            (
                "The simulator is deterministic and local; it does not replace sales leadership, legal, "
                "security, or finance approval."
            ),
            (
                "Deal value, effort, margin, and win probability are portfolio scenario assumptions, "
                "not live CRM, billing, or forecasting data."
            ),
            (
                "Risk-adjusted ROI is directional and should be recalculated with real labor rates, "
                "discount guidance, and opportunity data."
            ),
            (
                "Compliance, procurement, and evidence readiness are derived from fake sample documents "
                "and local retrieval artifacts."
            ),
        ]

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
