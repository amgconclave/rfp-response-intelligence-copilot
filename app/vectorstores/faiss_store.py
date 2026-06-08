from app.core.config import Settings
from app.models.domain import Chunk
from app.vectorstores.base import BaseVectorStore, SearchResult
from app.vectorstores.embedding import cosine_similarity, embed_text, tokenize


class FaissStore(BaseVectorStore):
    """Small local vector index with FAISS-like behavior and no native dependency."""

    mode = "faiss"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._vectors: dict[str, list[float]] = {}
        self._chunks: dict[str, Chunk] = {}

    async def upsert(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            chunk.embedding_id = chunk.id
            self._chunks[chunk.id] = chunk
            self._vectors[chunk.id] = embed_text(chunk.text, self.settings.embedding_dimensions)

    async def search(self, query: str, top_k: int = 4) -> list[SearchResult]:
        query_vector = embed_text(query, self.settings.embedding_dimensions)
        query_terms = self._expand_query_terms(set(tokenize(query)))
        scored = [
            SearchResult(
                chunk=self._chunks[chunk_id],
                score=round(
                    0.35 * cosine_similarity(query_vector, vector)
                    + 0.65 * self._lexical_score(query_terms, self._chunks[chunk_id].text),
                    6,
                ),
            )
            for chunk_id, vector in self._vectors.items()
        ]
        return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]

    def _lexical_score(self, query_terms: set[str], text: str) -> float:
        if not query_terms:
            return 0.0
        chunk_terms = set(tokenize(text))
        overlap = query_terms.intersection(chunk_terms)
        coverage = len(overlap) / len(query_terms)
        important_hits = sum(
            1
            for term in overlap
            if term
            in {
                "rfp",
                "evidence",
                "citations",
                "missing",
                "sso",
                "encryption",
                "metrics",
                "evaluation",
                "pricing",
                "cost",
                "audit",
                "token",
            }
        )
        return min(1.0, coverage + important_hits * 0.08)

    def _expand_query_terms(self, terms: set[str]) -> set[str]:
        expanded = set(terms)
        expansions = {
            "unsupported": {"missing", "evidence", "claim", "claims", "citation", "citations"},
            "prevent": {"avoid", "warning", "warn"},
            "answer": {"response", "generated", "source"},
            "answers": {"response", "responses", "generated", "source"},
            "metric": {"metrics", "latency", "token", "cost", "coverage", "precision"},
            "metrics": {"latency", "token", "cost", "coverage", "precision"},
        }
        for term in terms:
            expanded.update(expansions.get(term, set()))
        return expanded
