import time

from app.models.domain import Answer, DraftResponse, DraftSection
from app.providers.base import BaseLLMProvider
from app.repositories.memory import InMemoryRepository
from app.services.metrics import MetricsService
from app.services.retrieval import RetrievalService


class DraftGenerationService:
    def __init__(
        self,
        repo: InMemoryRepository,
        retrieval: RetrievalService,
        provider: BaseLLMProvider,
        metrics: MetricsService,
    ) -> None:
        self.repo = repo
        self.retrieval = retrieval
        self.provider = provider
        self.metrics = metrics

    async def answer_question(self, question: str, trace_id: str, top_k: int = 4) -> Answer:
        citations = await self.retrieval.search(question, top_k)
        start = time.perf_counter()
        result = await self.provider.answer(question, citations)
        latency_ms = (time.perf_counter() - start) * 1000
        self.metrics.record(
            trace_id=trace_id,
            provider=result.provider,
            model=result.model,
            usage=result.token_usage,
            latency_ms=latency_ms,
            endpoint="/rfp/query",
            metadata={"citation_count": len(citations)},
        )
        missing = [] if citations else [f"No sufficiently relevant source evidence found for: {question}"]
        confidence = min(0.95, 0.45 + sum(c.score for c in citations[:3]) / 3) if citations else 0.15
        return Answer(
            question=question,
            answer_text=result.text,
            citations=citations,
            confidence=round(confidence, 2),
            missing_evidence=missing,
            token_usage=result.token_usage,
            trace_id=trace_id,
        )

    async def draft_response(
        self,
        trace_id: str,
        requirement_ids: list[str] | None = None,
        section_names: list[str] | None = None,
        top_k: int = 5,
    ) -> DraftResponse:
        chosen_requirements = [
            self.repo.requirements[req_id]
            for req_id in requirement_ids or []
            if req_id in self.repo.requirements
        ]
        if not chosen_requirements:
            chosen_requirements = list(self.repo.requirements.values())[:6]
        query = " ".join(req.text for req in chosen_requirements) or "security compliance implementation pricing"
        citations = await self.retrieval.search(query, top_k)
        titles = section_names or [
            "Executive Summary",
            "Technical Approach",
            "Security and Compliance",
            "Implementation Plan",
            "Pricing Assumptions",
        ]
        start = time.perf_counter()
        result = await self.provider.draft(titles, citations)
        latency_ms = (time.perf_counter() - start) * 1000
        self.metrics.record(
            trace_id=trace_id,
            provider=result.provider,
            model=result.model,
            usage=result.token_usage,
            latency_ms=latency_ms,
            endpoint="/rfp/draft-response",
            metadata={"citation_count": len(citations), "section_count": len(titles)},
        )
        sections = self._sections_from_text(result.text, titles, [req.id for req in chosen_requirements])
        risks = [] if citations else ["Draft contains no verified evidence and should not be submitted."]
        assumptions = [
            "Customer-specific pricing and legal terms require commercial approval.",
            "Final response owner must verify citations before submission.",
        ]
        return DraftResponse(
            sections=sections,
            citations=citations,
            risks=risks,
            assumptions=assumptions,
            revision_notes=["Mock mode produces deterministic draft language for local review."],
            token_usage=result.token_usage,
            trace_id=trace_id,
        )

    def _sections_from_text(
        self, text: str, titles: list[str], requirement_ids: list[str]
    ) -> list[DraftSection]:
        sections: list[DraftSection] = []
        for title in titles:
            marker = f"## {title}"
            if marker in text:
                body = text.split(marker, 1)[1].split("\n## ", 1)[0].strip()
            else:
                body = "Response draft requires review against cited source evidence."
            sections.append(DraftSection(title=title, body=body, requirement_ids=requirement_ids))
        return sections
