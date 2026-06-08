from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.models.domain import Citation, TokenUsage


class LLMResult(BaseModel):
    text: str
    token_usage: TokenUsage
    model: str
    provider: str


class BaseLLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    async def answer(self, question: str, citations: list[Citation]) -> LLMResult:
        raise NotImplementedError

    @abstractmethod
    async def draft(self, section_names: list[str], citations: list[Citation]) -> LLMResult:
        raise NotImplementedError
