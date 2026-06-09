import os
import shutil
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.repositories.memory import repository
from app.services.container import get_container


@pytest.fixture()
def client(tmp_path) -> Generator[TestClient, None, None]:
    os.environ["API_KEY"] = "test-key"
    os.environ["STORAGE_DIR"] = str(tmp_path / "storage")
    get_settings.cache_clear()
    repository.reset()
    get_container.cache_clear()
    settings = get_settings()
    if settings.storage_dir.exists():
        shutil.rmtree(settings.storage_dir)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": get_settings().api_key}


def ingest_sample(
    client: TestClient,
    auth_headers: dict[str, str],
    filename: str,
    document_type: str = "knowledge_base",
) -> dict:
    response = client.post(
        "/documents/ingest",
        headers=auth_headers,
        json={
            "fixture_path": f"sample_data/{filename}",
            "document_type": document_type,
            "source": "sample",
        },
    )
    assert response.status_code == 200
    return response.json()


def ingest_corpus(client: TestClient, auth_headers: dict[str, str]) -> None:
    docs = [
        ("sample_data/acme_enterprise_rfp.md", "rfp"),
        ("sample_data/prior_proposal.md", "proposal"),
        ("sample_data/product_overview.md", "product"),
        ("sample_data/security_policy.md", "security"),
        ("sample_data/compliance_policy.md", "compliance"),
        ("sample_data/pricing_notes.md", "pricing"),
        ("sample_data/implementation_guide.md", "implementation"),
        ("sample_data/dpa_privacy_policy.md", "privacy"),
        ("sample_data/sla_support_policy.md", "support"),
        ("sample_data/ai_governance_security.md", "security"),
        ("sample_data/disaster_recovery_plan.md", "disaster_recovery"),
        ("sample_data/customer_success_onboarding.md", "customer_success"),
    ]
    for fixture_path, document_type in docs:
        response = client.post(
            "/documents/ingest",
            headers=auth_headers,
            json={"fixture_path": fixture_path, "document_type": document_type, "source": "sample"},
        )
        assert response.status_code == 200


def ingest_samples(client: TestClient, auth_headers: dict[str, str]) -> None:
    ingest_corpus(client, auth_headers)
