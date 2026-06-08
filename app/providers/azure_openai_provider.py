from app.core.config import Settings
from app.providers.openai_provider import OpenAIProvider


class AzureOpenAIProvider(OpenAIProvider):
    name = "azure_openai"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.model = settings.azure_openai_deployment or "azure-openai-deployment"

    def _client(self):
        if not all(
            [
                self.settings.azure_openai_endpoint,
                self.settings.azure_openai_api_key,
                self.settings.azure_openai_deployment,
            ]
        ):
            raise RuntimeError(
                "AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, and "
                "AZURE_OPENAI_DEPLOYMENT are required when PROVIDER_MODE=azure_openai."
            )
        try:
            from openai import AsyncAzureOpenAI
        except ImportError as exc:
            raise RuntimeError("Install the openai extra to use AzureOpenAIProvider.") from exc
        return AsyncAzureOpenAI(
            azure_endpoint=self.settings.azure_openai_endpoint,
            api_key=self.settings.azure_openai_api_key,
            api_version="2024-08-01-preview",
        )
