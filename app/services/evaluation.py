import json
import time
from pathlib import Path

from app.models.api import EvaluationMetrics
from app.services.draft_generation import DraftGenerationService
from app.services.retrieval import RetrievalService


class EvaluationService:
    def __init__(
        self,
        retrieval: RetrievalService,
        generation: DraftGenerationService,
    ) -> None:
        self.retrieval = retrieval
        self.generation = generation

    async def run(self, dataset_path: str, trace_id: str, top_k: int = 4) -> EvaluationMetrics:
        path = Path(dataset_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        dataset = json.loads(path.read_text(encoding="utf-8"))
        questions = dataset["questions"]
        details = []
        precision_scores: list[float] = []
        citation_hits = 0
        missing_hits = 0
        total_latency = 0.0
        input_tokens = 0
        output_tokens = 0
        cost = 0.0

        for index, item in enumerate(questions, start=1):
            start = time.perf_counter()
            answer = await self.generation.answer_question(item["question"], f"{trace_id}-{index}", top_k)
            latency_ms = (time.perf_counter() - start) * 1000
            total_latency += latency_ms
            expected_docs = set(item.get("expected_evidence_documents", []))
            cited_docs = {citation.filename for citation in answer.citations}
            hit_count = len(expected_docs.intersection(cited_docs))
            precision = hit_count / min(top_k, max(1, len(expected_docs)))
            precision_scores.append(precision)
            if answer.citations:
                citation_hits += 1
            if item.get("expect_missing_evidence") and answer.missing_evidence:
                missing_hits += 1
            input_tokens += answer.token_usage.input_tokens
            output_tokens += answer.token_usage.output_tokens
            cost += answer.token_usage.estimated_cost
            details.append(
                {
                    "question": item["question"],
                    "expected_documents": sorted(expected_docs),
                    "cited_documents": sorted(cited_docs),
                    "precision": round(precision, 3),
                    "missing_evidence": bool(answer.missing_evidence),
                    "latency_ms": round(latency_ms, 2),
                }
            )

        question_count = len(questions)
        retrieval_precision = sum(precision_scores) / question_count if question_count else 0.0
        citation_coverage = citation_hits / question_count if question_count else 0.0
        passed = retrieval_precision >= 0.45 and citation_coverage >= 0.7 and missing_hits >= 1
        return EvaluationMetrics(
            question_count=question_count,
            retrieval_precision_at_k=round(retrieval_precision, 3),
            citation_coverage=round(citation_coverage, 3),
            missing_evidence_detection_count=missing_hits,
            average_latency_ms=round(total_latency / question_count, 2) if question_count else 0.0,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=round(cost, 6),
            passed=passed,
            details=details,
        )
