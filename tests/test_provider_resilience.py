from pathlib import Path

from app.core.config import get_settings
from app.repositories.memory import repository
from app.services.container import get_container


def test_provider_resilience_service_defaults_to_local_mock(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    get_settings.cache_clear()
    get_container.cache_clear()
    repository.reset()

    container = get_container()
    resilience = container.provider_resilience.resilience("provider-resilience-service-test")

    assert resilience.title == "Provider Resilience Runbook"
    assert resilience.status == "local_ready"
    assert resilience.recommended_route_id == "provider.mock.local"
    assert resilience.summary["fallback_required"] is False
    assert set(resilience.summary["implemented_patterns"]) >= {
        "typed_contracts",
        "dependency_injection",
        "state_machine_workflow",
        "conditional_routing",
        "traceable_node_transitions",
    }
    assert any(
        route.provider_mode == "openai" and "OPENAI_API_KEY" in route.missing_env
        for route in resilience.provider_routes
    )
    assert all(transition.checkpoint_id.startswith("provider-resilience.") for transition in resilience.transitions)
    assert resilience.dependency_injection_contract["injected_interface"] == "app.providers.base.BaseLLMProvider"

    pack = container.provider_resilience.pack("provider-resilience-pack-test", resilience=resilience)
    assert pack.artifact_path
    assert pack.json_artifact_path
    assert Path(pack.artifact_path).exists()
    assert Path(pack.json_artifact_path).exists()
    assert "provider_resilience" in pack.artifact_path
    assert "## Provider Routes" in pack.markdown
    assert "## Traceable Transitions" in pack.markdown

    repository.reset()
    get_settings.cache_clear()
    get_container.cache_clear()


def test_provider_resilience_routes_missing_openai_to_mock(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("PROVIDER_MODE", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    get_container.cache_clear()

    resilience = get_container().provider_resilience.resilience("provider-resilience-openai-test")

    assert resilience.status == "fallback_to_mock"
    assert resilience.active_provider_mode == "openai"
    assert resilience.recommended_route_id == "provider.mock.local"
    assert resilience.summary["fallback_required"] is True
    assert "OPENAI_API_KEY" in resilience.summary["missing_env"]

    get_settings.cache_clear()
    get_container.cache_clear()


def test_provider_resilience_endpoints_and_wiring(client, auth_headers):
    response = client.get("/ops/provider-resilience", headers=auth_headers)

    assert response.status_code == 200
    resilience = response.json()
    assert resilience["title"] == "Provider Resilience Runbook"
    assert resilience["recommended_route_id"] == "provider.mock.local"
    assert resilience["provider_routes"]
    assert resilience["state_machine"]
    assert resilience["transitions"]
    assert "dependency_injection" in resilience["summary"]["implemented_patterns"]

    pack_response = client.post(
        "/ops/provider-resilience-pack",
        headers=auth_headers,
        json={"write_artifact": True},
    )
    assert pack_response.status_code == 200
    pack = pack_response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "provider_resilience" in pack["artifact_path"]
    assert "Provider Resilience Runbook Pack" in pack["markdown"]

    smoke_response = client.get("/ui/dashboard-smoke", headers=auth_headers)
    assert smoke_response.status_code == 200
    smoke = smoke_response.json()
    provider_view = next(view for view in smoke["expected_views"] if view["label"] == "Provider Resilience")
    assert provider_view["status"] == "pass"
    assert provider_view["artifact_root"] == "provider_resilience"
    endpoint_paths = {endpoint["path"]: endpoint for endpoint in smoke["endpoint_references"]}
    assert endpoint_paths["/ops/provider-resilience"]["status"] == "pass"
    assert endpoint_paths["/ops/provider-resilience-pack"]["status"] == "pass"

    launch_response = client.get("/ops/smoke-matrix", headers=auth_headers)
    assert launch_response.status_code == 200
    launch = launch_response.json()
    paths = {row["path"]: row for row in launch["rows"]}
    assert "/ops/provider-resilience" in paths
    assert "storage/provider_resilience/*.md" in paths["/ops/provider-resilience-pack"][
        "required_artifact_expectations"
    ]

    contract_response = client.get("/api/contract-audit", headers=auth_headers)
    assert contract_response.status_code == 200
    contract = contract_response.json()
    operation_paths = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["operations"]}
    assert {"/ops/provider-resilience", "/ops/provider-resilience-pack"} <= operation_paths
    assert "/ops/provider-resilience-pack" not in contract["generated_artifact_endpoint_coverage"]["missing_paths"]
