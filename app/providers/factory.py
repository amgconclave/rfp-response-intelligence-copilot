from app.core.config import Settings
from app.providers.base import BaseLLMProvider
from app.providers.mock import MockLLMProvider
from app.providers.openai_provider import OpenAIProvider


def build_llm_provider(settings: Settings) -> BaseLLMProvider:
    if settings.provider_mode == "openai":
        return OpenAIProvider(settings)
    if settings.provider_mode == "azure_openai":
        from app.providers.azure_openai_provider import AzureOpenAIProvider

        return AzureOpenAIProvider(settings)
    return MockLLMProvider()
