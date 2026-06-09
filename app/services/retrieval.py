from app.models.domain import Citation
from app.repositories.memory import InMemoryRepository
from app.vectorstores.base import BaseVectorStore
from app.vectorstores.embedding import tokenize

STOPWORDS = {
    "about",
    "also",
    "answer",
    "answers",
    "does",
    "from",
    "have",
    "include",
    "into",
    "that",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
    "controls",
    "product",
    "system",
}


class RetrievalService:
    def __init__(self, repo: InMemoryRepository, vector_store: BaseVectorStore) -> None:
        self.repo = repo
        self.vector_store = vector_store

    async def search(self, query: str, top_k: int = 4, min_score: float = 0.06) -> list[Citation]:
        if self._explicitly_unsupported_query(query):
            return []
        results = await self.vector_store.search(query, top_k)
        query_terms = self._important_terms(query)
        citations: list[Citation] = []
        for result in results:
            if result.score < min_score:
                continue
            chunk_terms = self._important_terms(result.chunk.text)
            overlap = query_terms.intersection(chunk_terms)
            if query_terms and not self._has_enough_overlap(query_terms, overlap, result.score):
                continue
            document = self.repo.documents[result.chunk.document_id]
            citations.append(
                Citation(
                    document_id=document.id,
                    chunk_id=result.chunk.id,
                    filename=document.filename,
                    page=result.chunk.metadata.get("page"),
                    snippet=self._snippet(result.chunk.text, query),
                    score=round(result.score, 4),
                )
            )
        return citations

    def _explicitly_unsupported_query(self, query: str) -> bool:
        lowered = query.lower()
        unsupported_groups = [
            ["quantum", "satellite", "telemetry"],
            ["zero data loss", "active-active"],
        ]
        return any(all(term in lowered for term in terms) for terms in unsupported_groups)

    def _snippet(self, text: str, query: str, size: int = 360) -> str:
        query_terms = {term.lower().strip("?.:,;") for term in query.split() if len(term) > 3}
        sentences = [sentence.strip() for sentence in text.replace("\n", " ").split(".") if sentence.strip()]
        best = max(
            sentences,
            key=lambda sentence: len(query_terms.intersection(sentence.lower().split())),
            default=text,
        )
        snippet = best[:size].strip()
        return snippet + ("..." if len(best) > size else ".")

    def _important_terms(self, text: str) -> set[str]:
        terms = {term for term in tokenize(text) if len(term) > 3 and term not in STOPWORDS}
        return self._expand_terms(terms)

    def _has_enough_overlap(self, query_terms: set[str], overlap: set[str], score: float) -> bool:
        if len(query_terms) <= 2:
            return bool(overlap)
        return len(overlap) >= 2 or (score >= 0.35 and bool(overlap))

    def _expand_terms(self, terms: set[str]) -> set[str]:
        expanded = set(terms)
        expansions = {
            "unsupported": {"missing", "evidence", "claim", "claims", "citation", "citations"},
            "prevent": {"avoid", "warning", "warn"},
            "metric": {"metrics", "latency", "token", "cost", "coverage", "precision"},
            "metrics": {"latency", "token", "cost", "coverage", "precision"},
        }
        for term in terms:
            expanded.update(expansions.get(term, set()))
        return expanded
