from pathlib import Path

import pytest

from app.core.config import get_settings
from app.repositories.memory import repository
from app.services.container import get_container
from tests.conftest import ingest_corpus


@pytest.mark.asyncio
async def test_evidence_conflict_service_detects_scope_and_precedence_conflicts(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    get_container.cache_clear()
    repository.reset()
    container = get_container()
    for fixture_path, document_type in [
        ("sample_data/prior_proposal.md", "proposal"),
        ("sample_data/implementation_guide.md", "implementation"),
        ("sample_data/dpa_privacy_policy.md", "privacy"),
        ("sample_data/pricing_notes.md", "pricing"),
        ("sample_data/security_policy.md", "security"),
        ("sample_data/disaster_recovery_plan.md", "disaster_recovery"),
    ]:
        await container.ingestion.ingest_path(fixture_path, document_type=document_type, source="test")

    report = container.evidence_conflicts.conflict_report("conflict-service-test")

    assert report.title == "Evidence Conflict Resolver"
    assert report.summary["conflict_count"] >= 5
    assert report.summary["blocking_conflict_count"] >= 1
    assert report.summary["claim_count"] >= 10
    conflict_ids = {item.conflict_id for item in report.conflicts}
    assert "conflict_subprocessor_scope" in conflict_ids
    assert "conflict_disaster_recovery_sla" in conflict_ids
    subprocessor = next(item for item in report.conflicts if item.conflict_id == "conflict_subprocessor_scope")
    assert subprocessor.reviewer_owner == "legal"
    assert subprocessor.status == "blocked"
    assert subprocessor.citations
    assert any(reference["endpoint"] == "/compliance/evidence-matrix" for reference in subprocessor.endpoint_references)
    repository.reset()
    get_settings.cache_clear()
    get_container.cache_clear()


def test_evidence_conflict_endpoints_write_pack_and_artifacts(client, auth_headers):
    response = client.get("/evidence/conflicts", headers=auth_headers)
    assert response.status_code == 200
    conflicts = response.json()
    assert conflicts["summary"]["conflict_count"] >= 5
    assert conflicts["summary"]["blocking_conflict_count"] >= 1
    assert conflicts["reviewer_queue"]
    assert conflicts["endpoint_references"]
    assert any(item["conflict_id"] == "conflict_commercial_scope" for item in conflicts["conflicts"])

    pack_response = client.post("/evidence/conflict-pack", headers=auth_headers, json={"write_artifact": True})
    assert pack_response.status_code == 200
    pack = pack_response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "conflict_packs" in pack["artifact_path"]
    assert "Evidence Conflict Resolver Pack" in pack["markdown"]
    assert pack["pack"]["summary"]["conflict_count"] >= 5


def test_conflict_dashboard_smoke_launch_contract_and_inventory_wiring(client, auth_headers):
    ingest_corpus(client, auth_headers)

    smoke_response = client.get("/ui/dashboard-smoke", headers=auth_headers)
    assert smoke_response.status_code == 200
    smoke = smoke_response.json()
    conflict_view = next(view for view in smoke["expected_views"] if view["label"] == "Evidence Conflicts")
    assert conflict_view["status"] == "pass"
    assert conflict_view["artifact_root"] == "conflict_packs"
    endpoint_paths = {endpoint["path"]: endpoint for endpoint in smoke["endpoint_references"]}
    assert endpoint_paths["/evidence/conflicts"]["status"] == "pass"
    assert endpoint_paths["/evidence/conflict-pack"]["status"] == "pass"

    launch_response = client.get("/ops/smoke-matrix", headers=auth_headers)
    assert launch_response.status_code == 200
    launch = launch_response.json()
    paths = {row["path"]: row for row in launch["rows"]}
    assert "/evidence/conflicts" in paths
    assert "storage/conflict_packs/*.md" in paths["/evidence/conflict-pack"]["required_artifact_expectations"]

    inventory_response = client.get("/artifacts/inventory", headers=auth_headers)
    assert inventory_response.status_code == 200
    inventory = inventory_response.json()
    directories = {Path(item["directory"]).name: item for item in inventory["directories"]}
    assert "conflict_packs" in directories
    assert directories["conflict_packs"]["producer_endpoint"] == "POST /evidence/conflict-pack"

    contract_response = client.get("/api/contract-audit", headers=auth_headers)
    assert contract_response.status_code == 200
    contract = contract_response.json()
    evidence_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["evidence"]}
    assert {"/evidence/conflicts", "/evidence/conflict-pack"} <= evidence_endpoints
    assert "/evidence/conflict-pack" not in contract["generated_artifact_endpoint_coverage"]["missing_paths"]
