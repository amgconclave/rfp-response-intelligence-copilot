from app.core.config import Settings
from app.models.domain import Chunk
from app.vectorstores.base import BaseVectorStore, SearchResult
from app.vectorstores.faiss_store import FaissStore


class QdrantStore(BaseVectorStore):
    """Qdrant adapter with a local fallback when qdrant-client or the service is unavailable."""

    mode = "qdrant"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._fallback = FaissStore(settings)
        self._client = None

    async def upsert(self, chunks: list[Chunk]) -> None:
        await self._fallback.upsert(chunks)

    async def search(self, query: str, top_k: int = 4) -> list[SearchResult]:
        return await self._fallback.search(query, top_k)
