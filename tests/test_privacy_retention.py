from pathlib import Path

from tests.conftest import ingest_corpus


def test_privacy_retention_endpoints_write_pack(client, auth_headers):
    ingest_corpus(client, auth_headers)

    guardrails_response = client.get("/privacy/retention-guardrails", headers=auth_headers)
    assert guardrails_response.status_code == 200
    guardrails = guardrails_response.json()
    assert guardrails["title"] == "Privacy + Retention Guardrail Matrix"
    assert guardrails["summary"]["surface_count"] >= 6
    assert guardrails["summary"]["policy_source_count"] >= 2
    assert guardrails["prompt_logging_guidance"]
    assert any(surface["surface_id"] == "provider_prompts" for surface in guardrails["surfaces"])
    assert any(surface["policy_evidence"] for surface in guardrails["surfaces"])
    assert any(surface["redaction_rules"] for surface in guardrails["surfaces"])

    pack_response = client.post("/privacy/retention-pack", headers=auth_headers, json={"write_artifact": True})
    assert pack_response.status_code == 200
    pack = pack_response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "privacy_packs" in pack["artifact_path"]
    assert "Privacy Retention Guardrail Pack" in pack["markdown"]
    assert pack["pack"]["retention_actions"]
    assert pack["guardrails"]["summary"]["surface_count"] == guardrails["summary"]["surface_count"]


def test_privacy_retention_dashboard_smoke_launch_and_contract_wiring(client, auth_headers):
    smoke_response = client.get("/ui/dashboard-smoke", headers=auth_headers)
    assert smoke_response.status_code == 200
    smoke = smoke_response.json()
    privacy_view = next(view for view in smoke["expected_views"] if view["label"] == "Privacy Retention")
    assert privacy_view["status"] == "pass"
    assert privacy_view["artifact_root"] == "privacy_packs"
    endpoint_paths = {endpoint["path"]: endpoint for endpoint in smoke["endpoint_references"]}
    assert endpoint_paths["/privacy/retention-guardrails"]["status"] == "pass"
    assert endpoint_paths["/privacy/retention-pack"]["status"] == "pass"

    launch_response = client.get("/ops/smoke-matrix", headers=auth_headers)
    assert launch_response.status_code == 200
    launch = launch_response.json()
    paths = {row["path"]: row for row in launch["rows"]}
    assert "/privacy/retention-guardrails" in paths
    assert "storage/privacy_packs/*.md" in paths["/privacy/retention-pack"]["required_artifact_expectations"]

    contract_response = client.get("/api/contract-audit", headers=auth_headers)
    assert contract_response.status_code == 200
    contract = contract_response.json()
    privacy_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["privacy"]}
    assert {"/privacy/retention-guardrails", "/privacy/retention-pack"} <= privacy_endpoints
    assert "/privacy/retention-pack" not in contract["generated_artifact_endpoint_coverage"]["missing_paths"]

    inventory_response = client.get("/artifacts/inventory", headers=auth_headers)
    assert inventory_response.status_code == 200
    inventory = inventory_response.json()
    assert "privacy_packs" in {Path(item["directory"]).name for item in inventory["directories"]}
