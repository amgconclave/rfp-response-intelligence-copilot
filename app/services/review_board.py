from collections import Counter
from typing import Any

from app.models.domain import (
    Answer,
    Citation,
    DraftResponse,
    RequirementMatrixRow,
    ReviewFinding,
    ReviewReport,
    TokenUsage,
)

REVIEW_CATEGORIES = {
    "unsupported_claim",
    "weak_citation",
    "missing_evidence",
    "high_risk_requirement",
    "cost_latency_warning",
}


class RfpReviewBoardService:
    def review_answer(
        self,
        question: str,
        answer_text: str,
        citations: list[Citation],
        missing_evidence: list[str],
        token_usage: TokenUsage,
        trace_id: str,
    ) -> ReviewReport:
        findings: list[ReviewFinding] = []
        citation_refs = self._citation_refs(citations)
        no_verified_citations = not citations

        if no_verified_citations:
            findings.append(
                ReviewFinding(
                    severity="high",
                    category="missing_evidence",
                    message="The answer has no local source evidence attached.",
                    related_question=question,
                    citation_refs=[],
                    recommendation=(
                        "Do not submit this answer as a supported claim. Ingest approved source material or "
                        "respond with an explicit no-evidence caveat."
                    ),
                )
            )
            findings.append(
                ReviewFinding(
                    severity="medium",
                    category="weak_citation",
                    message="Citation quality is insufficient because no citations were provided.",
                    related_question=question,
                    citation_refs=[],
                    recommendation="Add at least one relevant citation from an approved document before release.",
                )
            )

        if no_verified_citations and self._looks_like_confident_claim(answer_text):
            findings.append(
                ReviewFinding(
                    severity="high",
                    category="unsupported_claim",
                    message="The answer appears to make a confident claim without supporting evidence.",
                    related_question=question,
                    citation_refs=[],
                    recommendation=(
                        "Rewrite as a missing-evidence response or attach local evidence that supports the claim."
                    ),
                )
            )

        weak_citations = [citation for citation in citations if citation.score < 0.18]
        if weak_citations:
            findings.append(
                ReviewFinding(
                    severity="medium",
                    category="weak_citation",
                    message="One or more citations have low retrieval scores for the question.",
                    related_question=question,
                    citation_refs=self._citation_refs(weak_citations),
                    recommendation=(
                        "Replace weak citations with higher-overlap evidence or mark the answer for SME review."
                    ),
                )
            )

        question_gap = self._question_specific_gap(question, citations)
        if citations and question_gap:
            findings.append(
                ReviewFinding(
                    severity="high",
                    category="missing_evidence",
                    message=question_gap,
                    related_question=question,
                    citation_refs=citation_refs,
                    recommendation=(
                        "Treat the retrieved sources as insufficient for this adversarial or highly specific ask."
                    ),
                )
            )
            findings.append(
                ReviewFinding(
                    severity="medium",
                    category="weak_citation",
                    message="Citations were retrieved, but they do not cover the key risky terms in the question.",
                    related_question=question,
                    citation_refs=citation_refs,
                    recommendation="Find evidence that explicitly mentions the requested control, guarantee, or term.",
                )
            )

        for item in missing_evidence:
            findings.append(
                ReviewFinding(
                    severity="high",
                    category="missing_evidence",
                    message=item,
                    related_question=question,
                    citation_refs=citation_refs,
                    recommendation="Resolve the missing evidence item before using the answer in a customer response.",
                )
            )

        cost_finding = self._token_usage_finding(token_usage, question)
        if cost_finding:
            findings.append(cost_finding)

        return self._report(findings, trace_id, {"reviewed_scope": "answer", "citation_count": len(citations)})

    def review_package(
        self,
        trace_id: str,
        requirement_matrix: list[RequirementMatrixRow] | None = None,
        draft_response: DraftResponse | None = None,
        answer_payloads: list[Answer] | None = None,
        export_payload: dict[str, Any] | None = None,
    ) -> ReviewReport:
        findings: list[ReviewFinding] = []
        matrix = requirement_matrix or self._matrix_from_export(export_payload)
        package = self._package_payload(export_payload)

        for row in matrix:
            if row.risk_level == "high" or row.status == "blocked":
                findings.append(
                    ReviewFinding(
                        severity="high",
                        category="high_risk_requirement",
                        message=(
                            f"Requirement {row.requirement_id} is marked {row.risk_level} risk "
                            f"with status {row.status}."
                        ),
                        related_requirement_id=row.requirement_id,
                        citation_refs=row.evidence_refs,
                        recommendation=(
                            "Assign the listed owner, confirm supportability, and document an exception "
                            "or evidence trail."
                        ),
                    )
                )
            if row.missing_evidence or not row.evidence_refs:
                missing = "; ".join(row.missing_evidence) if row.missing_evidence else "No evidence refs on row."
                findings.append(
                    ReviewFinding(
                        severity="high",
                        category="missing_evidence",
                        message=f"Requirement {row.requirement_id} is missing evidence: {missing}",
                        related_requirement_id=row.requirement_id,
                        citation_refs=row.evidence_refs,
                        recommendation="Do not mark this requirement ready until approved evidence is attached.",
                    )
                )

        if draft_response is not None:
            findings.extend(self._review_draft(draft_response))

        for answer in answer_payloads or []:
            answer_report = self.review_answer(
                answer.question,
                answer.answer_text,
                answer.citations,
                answer.missing_evidence,
                answer.token_usage,
                trace_id=answer.trace_id,
            )
            findings.extend(answer_report.findings)

        if package:
            findings.extend(self._review_export_package(package))

        summary = {
            "reviewed_scope": "package",
            "requirements_reviewed": len(matrix),
            "draft_sections_reviewed": len(draft_response.sections) if draft_response else 0,
            "answers_reviewed": len(answer_payloads or []),
        }
        return self._report(findings, trace_id, summary)

    def _review_draft(self, draft: DraftResponse) -> list[ReviewFinding]:
        findings: list[ReviewFinding] = []
        citation_refs = self._citation_refs(draft.citations)
        if draft.sections and not draft.citations:
            findings.append(
                ReviewFinding(
                    severity="high",
                    category="missing_evidence",
                    message="Draft package has sections but no citations.",
                    citation_refs=[],
                    recommendation="Regenerate or revise the draft with source citations before export.",
                )
            )
        if draft.citations and len(draft.citations) < max(1, min(2, len(draft.sections) // 2)):
            findings.append(
                ReviewFinding(
                    severity="medium",
                    category="weak_citation",
                    message="Draft has limited citation coverage relative to the number of sections.",
                    citation_refs=citation_refs,
                    recommendation=(
                        "Add citations to each claim-heavy section or split unsupported sections into assumptions."
                    ),
                )
            )
        if not draft.citations:
            for section in draft.sections:
                if self._looks_like_confident_claim(section.body):
                    findings.append(
                        ReviewFinding(
                            severity="high",
                            category="unsupported_claim",
                            message=f"Draft section '{section.title}' contains claim-like language without citations.",
                            related_requirement_id=", ".join(section.requirement_ids) or None,
                            citation_refs=[],
                            recommendation="Tie this section to local evidence or rewrite it as an assumption.",
                        )
                    )
        cost_finding = self._token_usage_finding(draft.token_usage, "draft package")
        return findings + ([cost_finding] if cost_finding else [])

    def _review_export_package(self, package: dict[str, Any]) -> list[ReviewFinding]:
        findings: list[ReviewFinding] = []
        citations = package.get("citations", [])
        citation_refs = [
            str(citation.get("filename") or citation.get("chunk_id") or citation)
            for citation in citations
            if isinstance(citation, dict)
        ]
        if package.get("drafted_sections") and not citation_refs:
            findings.append(
                ReviewFinding(
                    severity="high",
                    category="missing_evidence",
                    message="Export package contains drafted sections without citation records.",
                    citation_refs=[],
                    recommendation="Attach citations to the export package before distributing it.",
                )
            )
        for item in package.get("missing_evidence", []):
            findings.append(
                ReviewFinding(
                    severity="high",
                    category="missing_evidence",
                    message=str(item),
                    citation_refs=citation_refs,
                    recommendation="Resolve or explicitly disclose this missing evidence item in the package.",
                )
            )
        usage = package.get("eval_usage_summary", {})
        if isinstance(usage, dict):
            estimated_cost = float(usage.get("estimated_cost", 0.0) or 0.0)
            average_latency_ms = float(usage.get("average_latency_ms", 0.0) or 0.0)
            if estimated_cost >= 0.1 or average_latency_ms >= 2500:
                findings.append(
                    ReviewFinding(
                        severity="medium",
                        category="cost_latency_warning",
                        message=(
                            "Package usage summary exceeds the local review threshold "
                            f"(cost={estimated_cost}, latency_ms={average_latency_ms})."
                        ),
                        citation_refs=[],
                        recommendation=(
                            "Review retrieval depth, model choice, and draft length before scaling this workflow."
                        ),
                    )
                )
        return findings

    def _token_usage_finding(self, token_usage: TokenUsage, related_question: str) -> ReviewFinding | None:
        total_tokens = token_usage.input_tokens + token_usage.output_tokens
        if total_tokens < 3000 and token_usage.estimated_cost < 0.1:
            return None
        return ReviewFinding(
            severity="medium",
            category="cost_latency_warning",
            message=(
                "Token usage exceeds the local review threshold "
                f"(input={token_usage.input_tokens}, output={token_usage.output_tokens}, "
                f"cost={token_usage.estimated_cost})."
            ),
            related_question=related_question,
            citation_refs=[],
            recommendation="Shorten context, reduce top_k, or route the item for batch review before production use.",
        )

    def _looks_like_confident_claim(self, text: str) -> bool:
        lowered = text.lower()
        safe_caveats = [
            "do not have enough",
            "no verified",
            "not have enough verified",
            "missing evidence",
            "cannot answer",
            "please ingest",
            "do not claim",
        ]
        if any(caveat in lowered for caveat in safe_caveats):
            return False
        claim_terms = [
            "supports",
            "supported",
            "provides",
            "includes",
            "complies",
            "meets",
            "guarantees",
            "certified",
            "encrypts",
            "offers",
            "available",
        ]
        return any(term in lowered for term in claim_terms)

    def _question_specific_gap(self, question: str, citations: list[Citation]) -> str | None:
        lowered = question.lower()
        source_text = " ".join(f"{citation.filename} {citation.snippet}" for citation in citations).lower()
        risky_term_groups = [
            ("FedRAMP High authorization", ["fedramp"]),
            ("quantum-resistant satellite telemetry", ["quantum", "satellite", "telemetry"]),
            ("exact discount or deal terms", ["discount", "five-year", "unlimited"]),
        ]
        if any(term in lowered for term in ["99.99", "zero data loss", "uptime sla"]):
            return (
                "The question asks for an unconditional SLA or disaster recovery commitment, "
                "but local policy requires customer-specific contractual approval."
            )
        if "without human review" in lowered or "submit final rfp language" in lowered:
            return (
                "The question asks to bypass human review, but AI governance requires reviewer signoff "
                "before customer submission."
            )
        if (
            (("subprocessor" in lowered or "subprocesser" in lowered) and "only in the united states" in lowered)
            or "all optional subprocessors" in lowered
            or "all optional subprocessers" in lowered
        ):
            return (
                "The question asks for an unsupported privacy subprocessor commitment; retrieved policy "
                "requires customer-approved subprocessor review."
            )
        for label, terms in risky_term_groups:
            if any(term in lowered for term in terms) and not any(term in source_text for term in terms):
                return f"The question asks for {label}, but the retrieved citations do not explicitly support it."
        if "guarantee" in lowered and not any(term in source_text for term in ["guarantee", "sla", "contract"]):
            return "The question asks for a guarantee, but the citations do not contain contractual guarantee evidence."
        return None

    def _citation_refs(self, citations: list[Citation]) -> list[str]:
        refs = []
        for citation in citations:
            page = f" p.{citation.page}" if citation.page else ""
            refs.append(f"{citation.filename}{page}#{citation.chunk_id}")
        return refs

    def matrix_from_export(self, export_payload: dict[str, Any] | None) -> list[RequirementMatrixRow]:
        return self._matrix_from_export(export_payload)

    def _matrix_from_export(self, export_payload: dict[str, Any] | None) -> list[RequirementMatrixRow]:
        package = self._package_payload(export_payload)
        rows = package.get("requirement_matrix", []) if package else []
        return [RequirementMatrixRow.model_validate(row) for row in rows if isinstance(row, dict)]

    def _package_payload(self, export_payload: dict[str, Any] | None) -> dict[str, Any]:
        if not export_payload:
            return {}
        package = export_payload.get("package", export_payload)
        return package if isinstance(package, dict) else {}

    def _report(self, findings: list[ReviewFinding], trace_id: str, summary: dict[str, Any]) -> ReviewReport:
        severity_counts = Counter(finding.severity for finding in findings)
        category_counts = Counter(finding.category for finding in findings)
        passed = not any(finding.severity in {"critical", "high"} for finding in findings)
        return ReviewReport(
            findings=findings,
            passed=passed,
            summary={
                **summary,
                "finding_count": len(findings),
                "severity_counts": dict(severity_counts),
                "category_counts": dict(category_counts),
                "supported_categories": sorted(REVIEW_CATEGORIES),
            },
            trace_id=trace_id,
        )
