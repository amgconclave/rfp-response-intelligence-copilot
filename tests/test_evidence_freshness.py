from pathlib import Path

import pytest

from app.core.config import get_settings
from app.repositories.memory import repository
from app.services.container import get_container
from tests.conftest import ingest_corpus


@pytest.mark.asyncio
async def test_evidence_freshness_service_scores_sources_and_flags_risks(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    get_container.cache_clear()
    repository.reset()
    container = get_container()
    for fixture_path, document_type in [
        ("sample_data/security_policy.md", "security"),
        ("sample_data/compliance_policy.md", "compliance"),
        ("sample_data/dpa_privacy_policy.md", "privacy"),
        ("sample_data/sla_support_policy.md", "support"),
        ("sample_data/disaster_recovery_plan.md", "disaster_recovery"),
    ]:
        await container.ingestion.ingest_path(fixture_path, document_type=document_type, source="test")

    report = container.evidence_freshness.freshness_report("freshness-service-test")

    assert report.title == "Evidence Freshness + Expiry Risk"
    assert report.summary["source_count"] == 5
    assert report.summary["expired_count"] >= 1
    assert report.summary["unsupported_claim_count"] >= 1
    assert report.renewal_calendar
    assert report.owner_followups
    dr_source = next(source for source in report.sources if source.filename == "disaster_recovery_plan.md")
    assert dr_source.policy_owner == "engineering"
    assert dr_source.expiry_status == "expired"
    assert dr_source.unsupported_claim_flags
    assert "/compliance/evidence-matrix" in dr_source.endpoint_references
    assert report.review_workflow["status"] == "blocked_until_owner_review"
    assert "durable workflows" in report.review_workflow["patterns_applied"]
    assert any(item["workflow_state"] == "blocked_source_quarantine" for item in report.human_review_queue)
    assert report.governance_policy["policy_id"] == "local-evidence-freshness-gate-v1"
    assert any(span["span_id"] == "freshness.route_human_review" for span in report.trace_spans)
    sla = container.evidence_sla.ledger("freshness-sla-service-test", report)
    assert sla.status == "blocked"
    assert sla.summary["sla_item_count"] >= 1
    assert sla.summary["breached_count"] >= 1
    assert sla.summary["blocked_endpoint_count"] >= 1
    assert "state machine workflow" in sla.summary["patterns_applied"]
    assert any(item.workflow_state == "quarantine_source" for item in sla.ledger_items)
    assert any(row["process_mode"] == "sequential_blocking_review" for row in sla.role_crew_queue)
    assert any(checkpoint["state"] == "endpoint_release_gate" for checkpoint in sla.checkpoints)
    repository.reset()
    get_settings.cache_clear()
    get_container.cache_clear()


def test_evidence_freshness_endpoints_write_pack_and_artifacts(client, auth_headers):
    response = client.get("/evidence/freshness", headers=auth_headers)
    assert response.status_code == 200
    freshness = response.json()
    assert freshness["summary"]["source_count"] >= 11
    assert freshness["summary"]["expired_count"] >= 1
    assert freshness["summary"]["unsupported_claim_count"] >= 1
    assert freshness["renewal_calendar"]
    assert freshness["owner_followups"]
    assert freshness["review_workflow"]["current_state"] == "blocked_source_quarantine"
    assert freshness["human_review_queue"]
    assert freshness["governance_policy"]["enforcement_mode"] == "review_gate_only"
    assert len(freshness["trace_spans"]) >= 3
    assert freshness["endpoint_references"]
    assert any(source["filename"] == "dpa_privacy_policy.md" for source in freshness["sources"])

    pack_response = client.post("/evidence/freshness-pack", headers=auth_headers, json={"write_artifact": True})
    assert pack_response.status_code == 200
    pack = pack_response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "freshness_packs" in pack["artifact_path"]
    assert "Evidence Freshness + Expiry Risk Pack" in pack["markdown"]
    assert "Freshness Review Workflow" in pack["markdown"]
    assert pack["pack"]["review_workflow"]["status"] == "blocked_until_owner_review"
    assert pack["pack"]["human_review_queue"]
    assert pack["pack"]["trace_spans"]
    assert pack["pack"]["summary"]["source_count"] >= 11
    assert pack["pack"]["renewal_calendar"]
    assert pack["pack"]["owner_followups"]

    sla_response = client.get("/evidence/freshness-sla", headers=auth_headers)
    assert sla_response.status_code == 200
    sla = sla_response.json()
    assert sla["status"] == "blocked"
    assert sla["summary"]["sla_item_count"] >= 1
    assert sla["summary"]["breached_count"] >= 1
    assert sla["endpoint_impact"]
    assert sla["owner_rollups"]
    assert sla["role_crew_queue"]
    assert sla["governance_policy"]["policy_id"] == "local-freshness-sla-ledger-v1"

    sla_pack_response = client.post("/evidence/freshness-sla-pack", headers=auth_headers, json={"write_artifact": True})
    assert sla_pack_response.status_code == 200
    sla_pack = sla_pack_response.json()
    assert sla_pack["artifact_path"]
    assert sla_pack["json_artifact_path"]
    assert Path(sla_pack["artifact_path"]).exists()
    assert Path(sla_pack["json_artifact_path"]).exists()
    assert "freshness_sla" in sla_pack["artifact_path"]
    assert "Evidence Freshness SLA Ledger Pack" in sla_pack["markdown"]
    assert sla_pack["pack"]["summary"]["sla_item_count"] >= 1
    assert sla_pack["sla"]["summary"]["blocked_endpoint_count"] >= 1


def test_freshness_dashboard_smoke_launch_contract_and_inventory_wiring(client, auth_headers):
    ingest_corpus(client, auth_headers)

    smoke_response = client.get("/ui/dashboard-smoke", headers=auth_headers)
    assert smoke_response.status_code == 200
    smoke = smoke_response.json()
    freshness_view = next(view for view in smoke["expected_views"] if view["label"] == "Evidence Freshness")
    assert freshness_view["status"] == "pass"
    assert freshness_view["artifact_root"] == "freshness_packs"
    endpoint_paths = {endpoint["path"]: endpoint for endpoint in smoke["endpoint_references"]}
    assert endpoint_paths["/evidence/freshness"]["status"] == "pass"
    assert endpoint_paths["/evidence/freshness-pack"]["status"] == "pass"
    assert endpoint_paths["/evidence/freshness-sla"]["status"] == "pass"
    assert endpoint_paths["/evidence/freshness-sla-pack"]["status"] == "pass"

    launch_response = client.get("/ops/smoke-matrix", headers=auth_headers)
    assert launch_response.status_code == 200
    launch = launch_response.json()
    paths = {row["path"]: row for row in launch["rows"]}
    assert "/evidence/freshness" in paths
    assert "storage/freshness_packs/*.md" in paths["/evidence/freshness-pack"]["required_artifact_expectations"]
    assert "storage/freshness_sla/*.md" in paths["/evidence/freshness-sla-pack"]["required_artifact_expectations"]

    inventory_response = client.get("/artifacts/inventory", headers=auth_headers)
    assert inventory_response.status_code == 200
    inventory = inventory_response.json()
    directories = {Path(item["directory"]).name: item for item in inventory["directories"]}
    assert "freshness_packs" in directories
    assert directories["freshness_packs"]["producer_endpoint"] == "POST /evidence/freshness-pack"
    assert "freshness_sla" in directories
    assert directories["freshness_sla"]["producer_endpoint"] == "POST /evidence/freshness-sla-pack"

    contract_response = client.get("/api/contract-audit", headers=auth_headers)
    assert contract_response.status_code == 200
    contract = contract_response.json()
    evidence_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["evidence"]}
    assert {
        "/evidence/freshness",
        "/evidence/freshness-pack",
        "/evidence/freshness-sla",
        "/evidence/freshness-sla-pack",
    } <= evidence_endpoints
    assert "/evidence/freshness-pack" not in contract["generated_artifact_endpoint_coverage"]["missing_paths"]
    assert "/evidence/freshness-sla-pack" not in contract["generated_artifact_endpoint_coverage"]["missing_paths"]
