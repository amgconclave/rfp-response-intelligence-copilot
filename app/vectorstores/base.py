from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.models.domain import Chunk


class SearchResult(BaseModel):
    chunk: Chunk
    score: float


class BaseVectorStore(ABC):
    mode: str

    @abstractmethod
    async def upsert(self, chunks: list[Chunk]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def search(self, query: str, top_k: int = 4) -> list[SearchResult]:
        raise NotImplementedError
