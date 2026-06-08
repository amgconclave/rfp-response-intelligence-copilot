from app.core.config import Settings
from app.models.domain import Citation, TokenUsage
from app.providers.base import BaseLLMProvider, LLMResult


class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model = settings.openai_model

    def _client(self):
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when PROVIDER_MODE=openai.")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError("Install the openai extra to use OpenAIProvider.") from exc
        return AsyncOpenAI(api_key=self.settings.openai_api_key)

    async def answer(self, question: str, citations: list[Citation]) -> LLMResult:
        client = self._client()
        context = "\n".join(f"- {c.filename}: {c.snippet}" for c in citations)
        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Answer only from cited RFP evidence."},
                {"role": "user", "content": f"Question: {question}\nEvidence:\n{context}"},
            ],
        )
        usage = response.usage
        text = response.choices[0].message.content or ""
        return LLMResult(
            text=text,
            token_usage=TokenUsage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
            model=self.model,
            provider=self.name,
        )

    async def draft(self, section_names: list[str], citations: list[Citation]) -> LLMResult:
        client = self._client()
        context = "\n".join(f"- {c.filename}: {c.snippet}" for c in citations)
        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Draft concise RFP response sections with source discipline."},
                {
                    "role": "user",
                    "content": f"Sections: {', '.join(section_names)}\nEvidence:\n{context}",
                },
            ],
        )
        usage = response.usage
        return LLMResult(
            text=response.choices[0].message.content or "",
            token_usage=TokenUsage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
            model=self.model,
            provider=self.name,
        )
