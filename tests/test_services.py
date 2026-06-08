import pytest

from app.core.config import get_settings
from app.models.domain import TokenUsage
from app.providers.mock import MockLLMProvider
from app.repositories.memory import repository
from app.services.container import get_container
from app.services.metrics import MetricsService


@pytest.mark.asyncio
async def test_service_boundaries_ingest_retrieve_generate_and_measure(tmp_path, monkeypatch):
    monkeypatch.setenv("API_KEY", "service-test-key")
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setenv("VECTOR_STORE_MODE", "qdrant")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    get_container.cache_clear()
    repository.reset()

    container = get_container()
    document, chunks = await container.ingestion.ingest_path(
        "sample_data/security_policy.md",
        document_type="knowledge_base",
        source="test",
        tags=["security"],
    )
    assert document.id in container.repo.documents
    assert chunks

    citations = await container.retrieval.search("SSO SAML OIDC encryption TLS AES-256", top_k=3)
    assert citations
    assert citations[0].filename == "security_policy.md"

    answer = await container.generation.answer_question(
        "What SSO and encryption controls are supported?",
        trace_id="service-trace",
        top_k=3,
    )
    assert answer.citations
    assert answer.token_usage.input_tokens > 0

    analysis = container.analysis.analyze(
        "The vendor must provide SOC 2 evidence. The response deadline is July 18, 2026.",
        trace_id="analysis-trace",
    )
    assert analysis.requirements
    assert analysis.deadlines == ["July 18, 2026"]

    event = container.audit.record("service-trace", "test.event", "test")
    assert event.trace_id == "service-trace"

    get_container.cache_clear()
    get_settings.cache_clear()
    repository.reset()


def test_mock_provider_and_cost_estimation(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    settings = get_settings()
    settings.estimated_input_cost_per_1k = 0.01
    settings.estimated_output_cost_per_1k = 0.02
    metrics = MetricsService(repository, settings)
    usage = TokenUsage(input_tokens=1000, output_tokens=500)
    assert metrics.estimate_cost(usage) == 0.02
    assert MockLLMProvider().name == "mock"
    get_settings.cache_clear()
