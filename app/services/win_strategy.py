from __future__ import annotations

import json
import re
from typing import Any

from app.core.config import Settings
from app.models.api import (
    AnalyzeResponse,
    CustomerFitResponse,
    DealReadinessScorecardResponse,
    PricingRiskMemoResponse,
    WinStrategyResponse,
)
from app.models.domain import RequirementMatrixRow, ResponseMemoryMatch, ReviewFinding, StakeholderTask
from app.repositories.memory import InMemoryRepository
from app.vectorstores.embedding import tokenize


class WinStrategyService:
    def __init__(self, repo: InMemoryRepository, settings: Settings) -> None:
        self.repo = repo
        self.settings = settings

    def create_win_strategy(
        self,
        trace_id: str,
        analysis: AnalyzeResponse | None = None,
        requirement_matrix: list[RequirementMatrixRow] | None = None,
        customer_fit: CustomerFitResponse | None = None,
        readiness_scorecard: DealReadinessScorecardResponse | None = None,
        response_memory_matches: list[ResponseMemoryMatch] | None = None,
        action_plan: list[StakeholderTask] | None = None,
        review_findings: list[ReviewFinding] | None = None,
        competitor_context: list[str] | None = None,
        pricing_notes: list[str] | None = None,
    ) -> WinStrategyResponse:
        matrix = requirement_matrix or []
        findings = review_findings or []
        tasks = action_plan or []
        memory_matches = response_memory_matches or []
        competitor_profile = self._competitor_risk_profile(analysis, matrix, competitor_context or [])
        pricing_risk = self._pricing_risk(analysis, matrix, competitor_profile, pricing_notes or [])
        proof_points = self._proof_points(analysis, matrix, memory_matches)
        differentiators = self._differentiators(proof_points, customer_fit)
        red_flags = self._red_flags(
            matrix,
            findings,
            readiness_scorecard,
            customer_fit,
            pricing_risk,
            competitor_profile,
        )
        assumptions = self._assumptions(analysis, pricing_notes or [], competitor_context or [], proof_points)
        next_actions = self._next_actions(matrix, tasks, findings, pricing_risk, competitor_profile, red_flags)
        win_score = self._win_score(
            matrix=matrix,
            proof_points=proof_points,
            red_flags=red_flags,
            competitor_profile=competitor_profile,
            pricing_risk=pricing_risk,
            customer_fit=customer_fit,
            readiness_scorecard=readiness_scorecard,
        )
        posture = self._recommended_posture(win_score, competitor_profile, pricing_risk, red_flags)
        return WinStrategyResponse(
            win_score=win_score,
            win_level=self._win_level(win_score),
            competitor_risk_profile=competitor_profile,
            pricing_risk=pricing_risk,
            compliance_security_differentiators=differentiators,
            proof_points=proof_points,
            recommended_response_posture=posture,
            red_flags=red_flags,
            assumptions=assumptions,
            next_actions_by_owner=next_actions,
            trace_id=trace_id,
        )

    def export_pricing_risk_memo(
        self,
        trace_id: str,
        win_strategy: WinStrategyResponse,
        analysis: AnalyzeResponse | None = None,
        requirement_matrix: list[RequirementMatrixRow] | None = None,
        customer_fit: CustomerFitResponse | None = None,
        write_artifact: bool = True,
    ) -> PricingRiskMemoResponse:
        matrix = requirement_matrix or []
        memo = {
            "trace_id": trace_id,
            "win_score": win_strategy.win_score,
            "win_level": win_strategy.win_level,
            "pricing_assumptions": self._memo_pricing_assumptions(analysis, win_strategy),
            "discount_packaging_risks": win_strategy.pricing_risk["risk_drivers"],
            "compliance_blockers": self._memo_compliance_blockers(analysis, matrix, win_strategy),
            "competitor_framing": self._competitor_framing(win_strategy),
            "cited_proof_points": win_strategy.proof_points[:8],
            "leadership_recommendation": self._leadership_recommendation(win_strategy),
            "local_commands": [
                "python -m uvicorn app.main:app --reload",
                "streamlit run dashboard/app.py",
                "python -m app.demo",
                "python -m pytest -q",
                "python -m ruff check .",
                "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
                "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
                (
                    'curl -X POST "http://127.0.0.1:8000/rfp/win-strategy" '
                    '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
                ),
                (
                    'curl -X POST "http://127.0.0.1:8000/rfp/pricing-risk-memo" '
                    '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
                ),
            ],
            "jd_skills_demonstrated": [
                "Presales decision support that combines RAG evidence with pricing and compliance risk.",
                "Deterministic FastAPI service composition with typed Pydantic workflow contracts.",
                "Local artifact generation for leadership review without external CRM or pricing systems.",
                (
                    "Citation-aware proof-point extraction from approved security, compliance, pricing, and "
                    "memory sources."
                ),
                "Risk scoring, owner routing, eval commands, and interview-ready storytelling in one workflow.",
            ],
            "interviewer_talking_points": [
                "The simulator moves beyond answer generation into competitive deal strategy and executive risk.",
                "Pricing risk is not invented from a CRM; it is derived from local RFP, matrix, and pricing notes.",
                "The memo carries cited proof points so leadership can see which claims are actually supportable.",
                "High competitor or discount pressure lowers the win score and creates owner-specific next actions.",
                "All outputs are deterministic, local, test-covered, and reproducible with the listed commands.",
            ],
            "customer_fit": self._customer_fit_summary(customer_fit),
        }
        markdown = self._render_memo_markdown(memo)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            memo_dir = self.settings.storage_dir / "pricing_memos"
            memo_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = memo_dir / f"pricing_risk_memo_{safe_trace_id}.md"
            json_path = memo_dir / f"pricing_risk_memo_{safe_trace_id}.json"
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(memo, indent=2), encoding="utf-8")
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
        return PricingRiskMemoResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            memo=memo,
            trace_id=trace_id,
        )

    def _competitor_risk_profile(
        self,
        analysis: AnalyzeResponse | None,
        matrix: list[RequirementMatrixRow],
        competitor_context: list[str],
    ) -> dict[str, Any]:
        text = " ".join(competitor_context + [row.requirement_text for row in matrix])
        if analysis:
            text = " ".join([text, *analysis.pricing_mentions, *analysis.risks])
        lowered = text.lower()
        drivers: list[str] = []
        score = 18
        pressure_terms = {
            "incumbent": 18,
            "discount": 16,
            "cheaper": 14,
            "bundle": 12,
            "bundled": 12,
            "microsoft": 10,
            "salesforce": 10,
            "servicenow": 10,
            "azure": 8,
            "price match": 14,
            "commodity": 10,
        }
        for term, weight in pressure_terms.items():
            if term in lowered:
                score += weight
                drivers.append(f"Competitor pressure signal: {term}.")
        blocked = sum(1 for row in matrix if row.status == "blocked" or row.risk_level == "high")
        if blocked:
            score += min(22, blocked * 4)
            drivers.append(f"{blocked} blocked or high-risk requirements can be exploited by competitors.")
        pricing_rows = [row for row in matrix if row.category == "pricing"]
        if pricing_rows:
            score += 8
            drivers.append("Commercial terms are explicit in the RFP and need proactive framing.")
        score = min(100, score)
        level = "high" if score >= 70 else "medium" if score >= 40 else "low"
        likely_angles = self._likely_competitor_angles(lowered, matrix)
        return {
            "risk_score": score,
            "risk_level": level,
            "likely_competitor_angles": likely_angles,
            "risk_drivers": list(dict.fromkeys(drivers)) or ["No explicit competitor pressure supplied."],
            "recommended_counter_moves": self._counter_moves(level, likely_angles),
        }

    def _pricing_risk(
        self,
        analysis: AnalyzeResponse | None,
        matrix: list[RequirementMatrixRow],
        competitor_profile: dict[str, Any],
        pricing_notes: list[str],
    ) -> dict[str, Any]:
        pricing_rows = [row for row in matrix if row.category == "pricing"]
        note_lines = pricing_notes or self._pricing_note_lines()
        text = " ".join(note_lines + [row.requirement_text for row in pricing_rows])
        if analysis:
            text = " ".join([text, *analysis.pricing_mentions])
        lowered = text.lower()
        drivers: list[str] = []
        score = 20 + len(pricing_rows) * 6
        for term in ["discount", "volume", "custom", "usage", "payment", "public-sector", "price", "pricing"]:
            if term in lowered:
                score += 6
                drivers.append(f"Pricing assumption requires review: {term}.")
        for row in pricing_rows:
            if row.status == "blocked" or row.risk_level == "high" or row.missing_evidence:
                score += 18
                drivers.append(f"{row.requirement_id} needs commercial evidence or approval.")
        if competitor_profile["risk_level"] == "high":
            score += 12
            drivers.append("High competitor pressure increases discount and packaging risk.")
        score = min(100, score)
        level = "high" if score >= 70 else "medium" if score >= 40 else "low"
        return {
            "risk_score": score,
            "risk_level": level,
            "pricing_assumptions": note_lines[:6],
            "risk_drivers": list(dict.fromkeys(drivers)) or ["No material pricing risk detected."],
            "recommended_controls": self._pricing_controls(level),
        }

    def _proof_points(
        self,
        analysis: AnalyzeResponse | None,
        matrix: list[RequirementMatrixRow],
        memory_matches: list[ResponseMemoryMatch],
    ) -> list[dict[str, Any]]:
        points: list[dict[str, Any]] = []
        for match in memory_matches:
            points.append(
                {
                    "claim": match.title,
                    "category": match.category,
                    "source": "approved_response_memory",
                    "citations": match.citations,
                    "source_snippet": self._clip(match.text),
                    "confidence": match.confidence,
                }
            )
        query_text = " ".join([row.requirement_text for row in matrix])
        if analysis:
            query_text = " ".join([query_text, *analysis.security_questions, *analysis.compliance_asks])
        tokens = self._signal_tokens(query_text)
        for chunk in self.repo.chunks.values():
            document = self.repo.documents.get(chunk.document_id)
            if not document or document.document_type == "rfp":
                continue
            chunk_tokens = self._signal_tokens(chunk.text)
            score = len(tokens & chunk_tokens) + self._document_weight(document.document_type)
            if score < 3 and document.document_type not in {"security", "compliance", "pricing"}:
                continue
            filename = chunk.metadata.get("filename", document.filename)
            page = chunk.metadata.get("page")
            citation = f"{filename} p.{page}" if page else filename
            points.append(
                {
                    "claim": self._claim_for_chunk(document.document_type, chunk.text),
                    "category": document.document_type,
                    "source": filename,
                    "citations": [citation],
                    "source_snippet": self._clip(chunk.text),
                    "confidence": round(min(0.95, 0.45 + score / 20), 2),
                }
            )
        if not points:
            points.extend(self._fallback_proof_points())
        ranked = sorted(points, key=lambda item: (-float(item["confidence"]), item["category"], item["claim"]))
        return self._dedupe_proof_points(ranked)[:10]

    def _differentiators(
        self,
        proof_points: list[dict[str, Any]],
        customer_fit: CustomerFitResponse | None,
    ) -> list[dict[str, Any]]:
        differentiators = [
            {
                "differentiator": point["claim"],
                "category": point["category"],
                "why_it_matters": self._differentiator_reason(point["category"], customer_fit),
                "citations": point["citations"],
                "source_snippet": point["source_snippet"],
            }
            for point in proof_points
            if point["category"] in {"security", "compliance", "approved_response_memory"}
            or point["category"] in {"implementation", "pricing"}
        ]
        return differentiators[:6]

    def _red_flags(
        self,
        matrix: list[RequirementMatrixRow],
        findings: list[ReviewFinding],
        readiness: DealReadinessScorecardResponse | None,
        customer_fit: CustomerFitResponse | None,
        pricing_risk: dict[str, Any],
        competitor_profile: dict[str, Any],
    ) -> list[str]:
        flags = []
        flags.extend(f"{row.requirement_id}: {row.requirement_text}" for row in matrix if row.status == "blocked")
        flags.extend(f"{finding.severity} {finding.category}: {finding.message}" for finding in findings[:4])
        if readiness:
            flags.extend(readiness.blockers[:4])
        if customer_fit:
            flags.extend(customer_fit.profile_risks[:3])
        if pricing_risk["risk_level"] == "high":
            flags.append("Pricing risk is high; do not offer discounts or custom packaging without approval.")
        if competitor_profile["risk_level"] == "high":
            flags.append("Competitor pressure is high; unsupported parity claims can damage credibility.")
        return list(dict.fromkeys(flag for flag in flags if flag))[:10]

    def _assumptions(
        self,
        analysis: AnalyzeResponse | None,
        pricing_notes: list[str],
        competitor_context: list[str],
        proof_points: list[dict[str, Any]],
    ) -> list[str]:
        assumptions = [
            "No external CRM, pricing system, or Azure dependency was used.",
            "Competitor pressure is modeled from supplied context and local RFP/commercial signals.",
            "Win score is directional and should be reviewed by the account team before submission.",
        ]
        if analysis and analysis.deadlines:
            assumptions.append(f"Submission timing is based on detected deadlines: {', '.join(analysis.deadlines)}.")
        if not competitor_context:
            assumptions.append("No named competitor context was supplied; simulator used generic incumbent pressure.")
        if not pricing_notes:
            assumptions.append("Pricing assumptions came from local sample pricing notes or ingested pricing docs.")
        if proof_points:
            assumptions.append("Proof points are limited to approved local documents and response memory.")
        return assumptions

    def _next_actions(
        self,
        matrix: list[RequirementMatrixRow],
        tasks: list[StakeholderTask],
        findings: list[ReviewFinding],
        pricing_risk: dict[str, Any],
        competitor_profile: dict[str, Any],
        red_flags: list[str],
    ) -> list[dict[str, Any]]:
        owner_actions: dict[str, list[str]] = {
            "sales": [
                "Confirm target discount guardrail and package boundary before final pricing language.",
                "Frame business value against competitor pressure using cited differentiators.",
            ],
            "solutions": ["Tailor the response posture and demo narrative to the highest-risk requirements."],
        }
        for row in matrix:
            if row.status == "blocked" or row.risk_level == "high":
                owner = self._owner_slug(row.owner_role)
                owner_actions.setdefault(owner, []).append(f"Resolve {row.requirement_id}: {row.requirement_text}")
        for task in tasks:
            if task.status in {"blocked", "needs_review"}:
                owner_actions.setdefault(task.owner_role, []).append(task.title)
        for finding in findings:
            owner = self._owner_for_finding(finding)
            owner_actions.setdefault(owner, []).append(f"Close review finding: {finding.message}")
        if pricing_risk["risk_level"] == "high":
            owner_actions.setdefault("finance", []).append("Approve discount, usage-cost, and packaging assumptions.")
        if competitor_profile["risk_level"] == "high":
            owner_actions.setdefault("sales_leadership", []).append(
                "Approve competitive talk track and walk-away line."
            )
        if red_flags:
            owner_actions.setdefault("legal", []).append("Review red flags and required exception language.")
        return [
            {"owner": owner, "actions": list(dict.fromkeys(actions))[:4]}
            for owner, actions in sorted(owner_actions.items())
            if actions
        ]

    def _win_score(
        self,
        matrix: list[RequirementMatrixRow],
        proof_points: list[dict[str, Any]],
        red_flags: list[str],
        competitor_profile: dict[str, Any],
        pricing_risk: dict[str, Any],
        customer_fit: CustomerFitResponse | None,
        readiness_scorecard: DealReadinessScorecardResponse | None,
    ) -> int:
        evidence_coverage = 0.0
        if matrix:
            evidence_coverage = sum(1 for row in matrix if row.evidence_refs and not row.missing_evidence) / len(matrix)
        score = 58 + int(round(evidence_coverage * 18)) + min(10, len(proof_points) * 2)
        if customer_fit:
            score += int(round((customer_fit.fit_score - 60) * 0.25))
        if readiness_scorecard:
            score += int(round((readiness_scorecard.readiness_score - 70) * 0.3))
        score -= int(round(competitor_profile["risk_score"] * 0.16))
        score -= int(round(pricing_risk["risk_score"] * 0.18))
        score -= min(18, len(red_flags) * 3)
        return max(0, min(100, score))

    def _win_level(self, score: int) -> str:
        if score >= 80:
            return "strong"
        if score >= 62:
            return "competitive"
        if score >= 45:
            return "at_risk"
        return "unlikely_without_changes"

    def _recommended_posture(
        self,
        score: int,
        competitor_profile: dict[str, Any],
        pricing_risk: dict[str, Any],
        red_flags: list[str],
    ) -> str:
        if score >= 80 and pricing_risk["risk_level"] != "high":
            return "Lead with differentiated security/compliance proof and hold pricing discipline."
        if competitor_profile["risk_level"] == "high" or pricing_risk["risk_level"] == "high":
            return (
                "Use a value-defense posture: cite proof points, avoid blanket price matching, and require "
                "sales leadership approval for discounts or custom packaging."
            )
        if red_flags:
            return "Conditionally pursue: resolve red flags, attach evidence, then submit with explicit assumptions."
        return "Pursue with balanced technical proof, implementation clarity, and standard commercial terms."

    def _memo_pricing_assumptions(
        self,
        analysis: AnalyzeResponse | None,
        win_strategy: WinStrategyResponse,
    ) -> list[str]:
        assumptions = list(win_strategy.pricing_risk.get("pricing_assumptions", []))
        if analysis and analysis.pricing_mentions:
            assumptions.extend(analysis.pricing_mentions)
        return list(dict.fromkeys(assumptions))[:8]

    def _memo_compliance_blockers(
        self,
        analysis: AnalyzeResponse | None,
        matrix: list[RequirementMatrixRow],
        win_strategy: WinStrategyResponse,
    ) -> list[str]:
        blockers = [
            row.requirement_text
            for row in matrix
            if row.category in {"security", "compliance"} and (row.status == "blocked" or row.risk_level == "high")
        ]
        if analysis:
            blockers.extend(analysis.missing_information)
        blockers.extend(flag for flag in win_strategy.red_flags if "compliance" in flag.lower())
        return list(dict.fromkeys(blockers))[:8] or ["No hard compliance blocker detected in local inputs."]

    def _competitor_framing(self, win_strategy: WinStrategyResponse) -> list[str]:
        profile = win_strategy.competitor_risk_profile
        return [
            f"Competitor risk is {profile['risk_level']} ({profile['risk_score']}/100).",
            *profile["likely_competitor_angles"][:3],
            *profile["recommended_counter_moves"][:3],
        ]

    def _leadership_recommendation(self, win_strategy: WinStrategyResponse) -> str:
        if win_strategy.win_score >= 80:
            return "Proceed with standard approval; protect margin and lead with cited proof."
        if win_strategy.win_score >= 62:
            return "Proceed after sales, finance, and security approve listed risks and proof-point framing."
        if win_strategy.win_score >= 45:
            return "Hold final submission until pricing risk and compliance blockers are resolved."
        return "Do not submit without executive exception approval and a revised commercial strategy."

    def _render_memo_markdown(self, memo: dict[str, Any]) -> str:
        lines = [
            "# Pricing Risk Memo",
            "",
            "## Leadership Recommendation",
            "",
            memo["leadership_recommendation"],
            "",
            "## Win Strategy Snapshot",
            "",
            f"- Win score: {memo['win_score']}",
            f"- Win level: {memo['win_level']}",
            "",
            "## Pricing Assumptions",
            "",
        ]
        self._append_list(lines, memo["pricing_assumptions"])
        lines.extend(["", "## Discount and Packaging Risks", ""])
        self._append_list(lines, memo["discount_packaging_risks"])
        lines.extend(["", "## Compliance Blockers", ""])
        self._append_list(lines, memo["compliance_blockers"])
        lines.extend(["", "## Competitor Framing", ""])
        self._append_list(lines, memo["competitor_framing"])
        lines.extend(["", "## Cited Proof Points", ""])
        if memo["cited_proof_points"]:
            lines.extend(["| Claim | Category | Citations | Source snippet |", "| --- | --- | --- | --- |"])
            for point in memo["cited_proof_points"]:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            self._md_cell(point["claim"]),
                            self._md_cell(point["category"]),
                            self._md_cell(", ".join(point["citations"])),
                            self._md_cell(point["source_snippet"]),
                        ]
                    )
                    + " |"
                )
        else:
            lines.append("- None")
        lines.extend(["", "## Exact Local Commands", ""])
        lines.extend(f"```bash\n{command}\n```" for command in memo["local_commands"])
        lines.extend(["", "## JD Skills Demonstrated", ""])
        self._append_list(lines, memo["jd_skills_demonstrated"])
        lines.extend(["", "## Five Interviewer Talking Points", ""])
        self._append_list(lines, memo["interviewer_talking_points"])
        return "\n".join(lines).strip() + "\n"

    def _pricing_note_lines(self) -> list[str]:
        lines = []
        for chunk in self.repo.chunks.values():
            document = self.repo.documents.get(chunk.document_id)
            if document and document.document_type == "pricing":
                lines.extend(self._meaningful_lines(chunk.text))
        if lines:
            return list(dict.fromkeys(lines))[:8]
        path = self.settings.sample_data_dir / "pricing_notes.md"
        if path.exists():
            return self._meaningful_lines(path.read_text(encoding="utf-8"))[:8]
        return ["Pricing assumptions must be approved by sales and finance before submission."]

    def _fallback_proof_points(self) -> list[dict[str, Any]]:
        points = []
        fallback_files = [
            ("security", self.settings.sample_data_dir / "security_policy.md"),
            ("compliance", self.settings.sample_data_dir / "compliance_policy.md"),
            ("pricing", self.settings.sample_data_dir / "pricing_notes.md"),
        ]
        for category, path in fallback_files:
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            points.append(
                {
                    "claim": self._claim_for_chunk(category, text),
                    "category": category,
                    "source": path.name,
                    "citations": [path.name],
                    "source_snippet": self._clip(text),
                    "confidence": 0.55,
                }
            )
        return points

    def _likely_competitor_angles(self, text: str, matrix: list[RequirementMatrixRow]) -> list[str]:
        angles = []
        if any(term in text for term in ["discount", "cheaper", "price match"]):
            angles.append("Undercut price or push a broad discount.")
        if any(term in text for term in ["incumbent", "bundle", "bundled", "microsoft", "salesforce", "servicenow"]):
            angles.append("Position lower switching risk through an incumbent or bundled platform.")
        if any(row.status == "blocked" for row in matrix):
            angles.append("Highlight unresolved evidence or compliance blockers.")
        if any(row.category == "implementation" for row in matrix):
            angles.append("Question implementation effort, timeline, and owner coverage.")
        return angles or ["Generic feature parity and procurement-risk pressure."]

    def _counter_moves(self, level: str, angles: list[str]) -> list[str]:
        moves = [
            "Anchor every differentiator in a cited proof point.",
            "Translate security and compliance evidence into buyer-risk reduction.",
        ]
        if level == "high":
            moves.append("Set an explicit approval path for discounts, exceptions, and price-match requests.")
        if any("implementation" in angle.lower() for angle in angles):
            moves.append("Attach a named implementation plan and stakeholder handoff.")
        return moves

    def _pricing_controls(self, level: str) -> list[str]:
        controls = [
            "Confirm tier, implementation scope, support expectations, and usage-cost assumptions.",
            "Separate discount approval from compliance exception approval.",
        ]
        if level == "high":
            controls.append("Require finance and sales leadership sign-off before submitting final commercial terms.")
        return controls

    def _claim_for_chunk(self, category: str, text: str) -> str:
        lowered = text.lower()
        if category == "security" or any(term in lowered for term in ["sso", "encryption", "tls", "aes-256"]):
            return "Security controls include SSO, encryption, auditability, and reviewable deployment boundaries."
        if category == "compliance" or any(term in lowered for term in ["soc 2", "gdpr", "subprocessor"]):
            return "Compliance posture is supported by SOC 2/GDPR-oriented evidence and approval workflows."
        if category == "pricing":
            return "Commercial packaging is scoped by tier, implementation services, and usage assumptions."
        if category == "implementation":
            return "Implementation can be framed around discovery, configuration, validation, and controlled rollout."
        return "Local RFP response workflow is backed by cited retrieval and review artifacts."

    def _differentiator_reason(self, category: str, customer_fit: CustomerFitResponse | None) -> str:
        profile = customer_fit.customer_profile.name if customer_fit else "the buyer"
        reasons = {
            "security": f"Reduces trust risk for {profile} by grounding identity, encryption, and audit claims.",
            "compliance": f"Helps {profile} evaluate regulated controls without unsupported assurance claims.",
            "pricing": "Protects margin by tying commercial terms to explicit package and usage assumptions.",
            "implementation": "Turns delivery risk into a named plan with owners and validation checkpoints.",
            "approved_response_memory": f"Reuses approved language already aligned to {profile} where applicable.",
        }
        return reasons.get(category, f"Provides cited support for {profile}'s evaluation criteria.")

    def _customer_fit_summary(self, customer_fit: CustomerFitResponse | None) -> dict[str, Any] | None:
        if customer_fit is None:
            return None
        return {
            "customer": customer_fit.customer_profile.name,
            "fit_score": customer_fit.fit_score,
            "risk_tolerance": customer_fit.customer_profile.risk_tolerance,
            "profile_risks": customer_fit.profile_risks,
        }

    def _document_weight(self, document_type: str) -> int:
        return {"security": 4, "compliance": 4, "pricing": 3, "proposal": 2, "product": 2}.get(document_type, 1)

    def _dedupe_proof_points(self, points: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped = []
        seen = set()
        for point in points:
            key = (point["claim"], tuple(point["citations"]))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(point)
        return deduped

    def _owner_slug(self, owner_role: str) -> str:
        lowered = owner_role.lower()
        if "security" in lowered:
            return "security"
        if "compliance" in lowered or "legal" in lowered:
            return "legal"
        if "commercial" in lowered or "sales" in lowered:
            return "sales"
        if "implementation" in lowered:
            return "solutions"
        return lowered.replace(" ", "_")

    def _owner_for_finding(self, finding: ReviewFinding) -> str:
        text = f"{finding.category} {finding.message} {finding.recommendation}".lower()
        if any(term in text for term in ["price", "pricing", "discount", "commercial"]):
            return "sales"
        if any(term in text for term in ["security", "encryption", "incident", "control"]):
            return "security"
        if any(term in text for term in ["compliance", "gdpr", "dpa", "contract", "legal"]):
            return "legal"
        return "solutions"

    def _meaningful_lines(self, text: str) -> list[str]:
        return [
            line.strip("- ").strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    def _signal_tokens(self, text: str) -> set[str]:
        stop_words = {
            "and",
            "are",
            "can",
            "for",
            "from",
            "must",
            "shall",
            "should",
            "the",
            "this",
            "with",
        }
        return {token for token in tokenize(text) if len(token) > 2 and token not in stop_words}

    def _clip(self, text: str, limit: int = 320) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3].rstrip() + "..."

    def _append_list(self, lines: list[str], items: list[Any]) -> None:
        if not items:
            lines.append("- None")
            return
        lines.extend(f"- {item}" for item in items)

    def _md_cell(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
