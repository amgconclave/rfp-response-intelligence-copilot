import json
from pathlib import Path

from app.core.config import Settings
from app.models.api import AnalyzeResponse, CustomerFitResponse
from app.models.domain import (
    ApprovedResponseSnippet,
    CustomerFitRequirement,
    CustomerProfile,
    RequirementMatrixRow,
    ResponseMemoryMatch,
    RfpRequirement,
)
from app.vectorstores.embedding import tokenize


class CustomerIntelligenceService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def list_profiles(self) -> list[CustomerProfile]:
        return [
            CustomerProfile(**item)
            for item in self._read_json(self.settings.sample_data_dir / "customer_profiles.json")["profiles"]
        ]

    def customer_fit(
        self,
        customer_profile_id: str,
        trace_id: str,
        analysis: AnalyzeResponse | None = None,
        requirement_matrix: list[RequirementMatrixRow] | None = None,
    ) -> CustomerFitResponse:
        profile = self.get_profile(customer_profile_id)
        requirements = self._requirements_from_inputs(analysis, requirement_matrix)
        matrix_by_id = {row.requirement_id: row for row in requirement_matrix or []}
        profile_tokens = self._profile_tokens(profile)
        emphasize: list[CustomerFitRequirement] = []
        review: list[CustomerFitRequirement] = []

        for requirement in requirements:
            row = matrix_by_id.get(requirement.id)
            req_tokens = self._tokens(f"{requirement.category} {requirement.text}")
            overlap = req_tokens & profile_tokens
            if overlap or requirement.category in {"security", "compliance"}:
                emphasize.append(
                    CustomerFitRequirement(
                        requirement_id=requirement.id,
                        category=requirement.category,
                        requirement_text=requirement.text,
                        priority=requirement.priority,
                        reason=self._emphasis_reason(profile, requirement, overlap),
                    )
                )
            if self._needs_review(profile, requirement, row, overlap):
                review.append(
                    CustomerFitRequirement(
                        requirement_id=requirement.id,
                        category=requirement.category,
                        requirement_text=requirement.text,
                        priority=requirement.priority,
                        reason=self._review_reason(profile, requirement, row, overlap),
                    )
                )

        profile_risks = self._profile_risks(profile, requirements, review, requirement_matrix or [])
        positioning = self._positioning(profile, emphasize, review)
        fit_score = self._fit_score(requirements, emphasize, review, profile_risks, requirement_matrix or [])
        return CustomerFitResponse(
            customer_profile=profile,
            fit_score=fit_score,
            profile_risks=profile_risks,
            recommended_positioning=positioning,
            requirements_to_emphasize=emphasize[:8],
            requirements_needing_review=review[:8],
            trace_id=trace_id,
        )

    def search_response_memory(
        self,
        query: str,
        trace_id: str,
        category: str | None = None,
        customer_profile_id: str | None = None,
        top_k: int = 5,
    ) -> list[ResponseMemoryMatch]:
        query_tokens = self._tokens(query)
        profile = self.get_profile(customer_profile_id) if customer_profile_id else None
        profile_tokens = self._profile_tokens(profile) if profile else set()
        matches: list[tuple[float, ResponseMemoryMatch]] = []
        for snippet in self._snippets():
            score = self._memory_score(snippet, query_tokens, profile_tokens, category, customer_profile_id)
            if score <= 0:
                continue
            matches.append(
                (
                    score,
                    ResponseMemoryMatch(
                        **snippet.model_dump(),
                        confidence=round(min(0.95, 0.25 + score / 18), 2),
                    ),
                )
            )
        ranked = [match for _, match in sorted(matches, key=lambda item: (-item[0], item[1].id))]
        return ranked[: max(1, top_k)]

    def get_profile(self, customer_profile_id: str | None) -> CustomerProfile:
        for profile in self.list_profiles():
            if profile.id == customer_profile_id:
                return profile
        raise ValueError(f"Unknown customer profile: {customer_profile_id}")

    def _requirements_from_inputs(
        self,
        analysis: AnalyzeResponse | None,
        requirement_matrix: list[RequirementMatrixRow] | None,
    ) -> list[RfpRequirement]:
        if analysis is not None:
            return analysis.requirements
        return [
            RfpRequirement(
                id=row.requirement_id,
                category=row.category,
                text=row.requirement_text,
                priority=row.priority,
                evidence_refs=row.evidence_refs,
                missing_info=row.missing_evidence,
            )
            for row in requirement_matrix or []
        ]

    def _profile_risks(
        self,
        profile: CustomerProfile,
        requirements: list[RfpRequirement],
        review: list[CustomerFitRequirement],
        matrix: list[RequirementMatrixRow],
    ) -> list[str]:
        risks: list[str] = []
        text = " ".join(requirement.text.lower() for requirement in requirements)
        for framework in profile.compliance_frameworks:
            framework_token = framework.lower()
            if framework_token not in text:
                risks.append(f"{framework} alignment is important for {profile.name} but is not explicit in the RFP.")
        blocked = [row for row in matrix if row.status == "blocked" or row.risk_level == "high"]
        if blocked and profile.risk_tolerance == "low":
            risks.append("Low risk tolerance means blocked or high-risk rows need executive review before submission.")
        if len(review) >= 3:
            risks.append("Several requirements need customer-profile review before reuse of standard language.")
        if profile.industry in {"healthcare", "public sector"} and "data residency" in text:
            risks.append("Data residency language should be validated against regional hosting and support boundaries.")
        return list(dict.fromkeys(risks))[:6]

    def _positioning(
        self,
        profile: CustomerProfile,
        emphasize: list[CustomerFitRequirement],
        review: list[CustomerFitRequirement],
    ) -> list[str]:
        priorities = ", ".join(profile.security_priorities[:3])
        frameworks = ", ".join(profile.compliance_frameworks[:3])
        positioning = [
            f"Lead with {priorities} for {profile.industry} buyers in {profile.region}.",
            f"Tie proof points to {frameworks} and require citations for every control claim.",
            f"Frame the response for {', '.join(profile.buyer_personas[:2])} with clear implementation ownership.",
        ]
        if review:
            positioning.append("Use approved language only where evidence exists; route exceptions through review.")
        elif emphasize:
            positioning.append("Reuse approved response patterns for matching security and compliance requirements.")
        return positioning

    def _fit_score(
        self,
        requirements: list[RfpRequirement],
        emphasize: list[CustomerFitRequirement],
        review: list[CustomerFitRequirement],
        risks: list[str],
        matrix: list[RequirementMatrixRow],
    ) -> float:
        if not requirements:
            return 0.0
        evidence_rows = sum(1 for row in matrix if row.evidence_refs)
        score = 58 + (len(emphasize) / len(requirements)) * 25 + evidence_rows * 2
        score -= len(review) * 4 + len(risks) * 5
        return round(max(10.0, min(95.0, score)), 1)

    def _needs_review(
        self,
        profile: CustomerProfile,
        requirement: RfpRequirement,
        row: RequirementMatrixRow | None,
        overlap: set[str],
    ) -> bool:
        if row and (row.status == "blocked" or row.risk_level == "high" or row.missing_evidence):
            return True
        if profile.risk_tolerance == "low" and requirement.priority == "high" and not overlap:
            return True
        if requirement.category in {"security", "compliance"} and not overlap:
            return True
        if requirement.category == "pricing" and profile.industry in {"fintech", "public sector"}:
            return True
        return False

    def _emphasis_reason(
        self,
        profile: CustomerProfile,
        requirement: RfpRequirement,
        overlap: set[str],
    ) -> str:
        if overlap:
            terms = ", ".join(sorted(overlap)[:4])
            return f"Matches {profile.name} profile signals: {terms}."
        return f"{requirement.category.title()} requirement maps to buyer priorities for {profile.industry}."

    def _review_reason(
        self,
        profile: CustomerProfile,
        requirement: RfpRequirement,
        row: RequirementMatrixRow | None,
        overlap: set[str],
    ) -> str:
        if row and row.missing_evidence:
            return f"Missing evidence for {profile.name}: {'; '.join(row.missing_evidence[:2])}."
        if row and row.status == "blocked":
            return "Workbench row is blocked and needs approval before standard response reuse."
        if requirement.category == "pricing":
            return "Commercial language should be validated against customer procurement expectations."
        if not overlap:
            return "High-priority profile controls are not clearly matched in this requirement."
        return "Review recommended before adapting approved language."

    def _memory_score(
        self,
        snippet: ApprovedResponseSnippet,
        query_tokens: set[str],
        profile_tokens: set[str],
        category: str | None,
        customer_profile_id: str | None,
    ) -> float:
        haystack = self._tokens(" ".join([snippet.title, snippet.category, snippet.text, " ".join(snippet.tags)]))
        score = len(query_tokens & haystack) * 2.0
        score += len(profile_tokens & haystack) * 0.8
        if category and snippet.category == category:
            score += 4
        elif category:
            score -= 2
        if customer_profile_id and customer_profile_id in snippet.customer_profile_ids:
            score += 5
        if "all" in snippet.customer_profile_ids:
            score += 1
        return score

    def _snippets(self) -> list[ApprovedResponseSnippet]:
        return [
            ApprovedResponseSnippet(**item)
            for item in self._read_json(self.settings.sample_data_dir / "approved_responses.json")["snippets"]
        ]

    def _profile_tokens(self, profile: CustomerProfile) -> set[str]:
        return self._tokens(
            " ".join(
                [
                    profile.industry,
                    profile.region,
                    profile.risk_tolerance,
                    " ".join(profile.security_priorities),
                    " ".join(profile.compliance_frameworks),
                    " ".join(profile.buyer_personas),
                ]
            )
        )

    def _tokens(self, text: str) -> set[str]:
        return {token for token in tokenize(text) if len(token) > 2}

    def _read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))
