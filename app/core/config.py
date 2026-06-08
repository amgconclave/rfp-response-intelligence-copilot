from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "RFP Response Intelligence Copilot"
    environment: str = "local"
    api_key: str = Field(default="local-demo-key", validation_alias="API_KEY")
    provider_mode: str = Field(default="mock", validation_alias="PROVIDER_MODE")
    vector_store_mode: str = Field(default="qdrant", validation_alias="VECTOR_STORE_MODE")
    embedding_dimensions: int = 128
    storage_dir: Path = Path("storage")
    sample_data_dir: Path = Path("sample_data")
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", validation_alias="OPENAI_MODEL")
    azure_openai_endpoint: str | None = Field(default=None, validation_alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str | None = Field(default=None, validation_alias="AZURE_OPENAI_API_KEY")
    azure_openai_deployment: str | None = Field(default=None, validation_alias="AZURE_OPENAI_DEPLOYMENT")
    qdrant_url: str = Field(default="http://localhost:6333", validation_alias="QDRANT_URL")
    qdrant_collection: str = Field(default="rfp_chunks", validation_alias="QDRANT_COLLECTION")
    estimated_input_cost_per_1k: float = 0.0
    estimated_output_cost_per_1k: float = 0.0

    @property
    def audit_path(self) -> Path:
        return self.storage_dir / "audit_events.jsonl"

    @property
    def metrics_path(self) -> Path:
        return self.storage_dir / "usage_metrics.jsonl"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    return settings
