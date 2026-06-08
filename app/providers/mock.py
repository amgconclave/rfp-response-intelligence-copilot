from app.models.domain import Citation, TokenUsage
from app.providers.base import BaseLLMProvider, LLMResult


def count_tokens(text: str) -> int:
    return max(1, len(text.split()))


class MockLLMProvider(BaseLLMProvider):
    name = "mock"
    model = "deterministic-rfp-local"

    async def answer(self, question: str, citations: list[Citation]) -> LLMResult:
        input_tokens = count_tokens(question) + sum(count_tokens(c.snippet) for c in citations)
        if not citations:
            text = (
                "I do not have enough verified source evidence to answer this safely. "
                "Please ingest the relevant product, security, compliance, or pricing document."
            )
        else:
            strongest = citations[0]
            supporting = "; ".join(c.filename for c in citations[:3])
            text = (
                f"Based on the retrieved RFP knowledge base, {strongest.snippet} "
                f"Supporting sources include {supporting}. Review the cited snippets before submission."
            )
        output_tokens = count_tokens(text)
        return LLMResult(
            text=text,
            token_usage=TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens),
            model=self.model,
            provider=self.name,
        )

    async def draft(self, section_names: list[str], citations: list[Citation]) -> LLMResult:
        titles = section_names or ["Executive Summary", "Technical Approach", "Security", "Pricing"]
        source_hint = citations[0].snippet if citations else "No verified supporting evidence was found."
        sections = []
        for title in titles:
            sections.append(
                f"## {title}\n"
                f"This response should be grounded in the approved knowledge base. {source_hint} "
                "Validate every customer-specific claim against the cited evidence before release."
            )
        text = "\n\n".join(sections)
        return LLMResult(
            text=text,
            token_usage=TokenUsage(
                input_tokens=sum(count_tokens(c.snippet) for c in citations) + len(titles) * 3,
                output_tokens=count_tokens(text),
            ),
            model=self.model,
            provider=self.name,
        )
