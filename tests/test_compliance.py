from pathlib import Path

import pytest

from app.core.config import get_settings
from app.repositories.memory import repository
from app.services.container import get_container
from tests.conftest import ingest_corpus


@pytest.mark.asyncio
async def test_compliance_service_maps_controls_and_flags_claims(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    get_container.cache_clear()
    repository.reset()
    container = get_container()
    for fixture_path, document_type in [
        ("sample_data/acme_enterprise_rfp.md", "rfp"),
        ("sample_data/security_policy.md", "security"),
        ("sample_data/compliance_policy.md", "compliance"),
        ("sample_data/dpa_privacy_policy.md", "privacy"),
        ("sample_data/sla_support_policy.md", "support"),
        ("sample_data/ai_governance_security.md", "security"),
        ("sample_data/disaster_recovery_plan.md", "disaster_recovery"),
        ("sample_data/customer_contract_terms.md", "contract"),
    ]:
        await container.ingestion.ingest_path(fixture_path, document_type=document_type, source="test")

    rfp_text = (container.settings.sample_data_dir / "acme_enterprise_rfp.md").read_text(encoding="utf-8")
    analysis = container.analysis.analyze(rfp_text, "compliance-service-analysis")
    matrix = container.workbench.create_requirement_matrix(analysis)
    review = container.review_board.review_package("compliance-service-review", requirement_matrix=matrix)
    result = container.compliance.evidence_matrix(
        "compliance-service-test",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review.findings,
    )

    families = {mapping.control_family for mapping in result.control_mappings}
    assert {
        "access control/SSO",
        "encryption/key management",
        "privacy/DPA/subprocessors",
        "audit logging",
        "AI governance/model claims",
        "SLA/support",
        "disaster recovery/BCP",
        "data residency/export",
    } <= families
    assert result.coverage_summary["control_family_count"] == 8
    assert result.coverage_summary["coverage_ratio"] >= 0.75
    sso = next(mapping for mapping in result.control_mappings if mapping.control_family == "access control/SSO")
    assert sso.requirement_links
    assert any(source.filename == "security_policy.md" for source in sso.source_docs)
    assert result.unsupported_claims
    assert any("uptime" in claim["claim"].lower() for claim in result.unsupported_claims)
    assert result.owner_followups
    repository.reset()
    get_settings.cache_clear()
    get_container.cache_clear()


def test_compliance_endpoints_return_matrix_and_write_pack(client, auth_headers):
    ingest_corpus(client, auth_headers)

    matrix_response = client.get("/compliance/evidence-matrix", headers=auth_headers)
    assert matrix_response.status_code == 200
    matrix = matrix_response.json()
    assert matrix["title"] == "Compliance Evidence Matrix + Control Mapping"
    assert matrix["coverage_summary"]["control_family_count"] == 8
    assert matrix["coverage_summary"]["coverage_ratio"] >= 0.75
    assert matrix["unsupported_claims"]
    assert any(mapping["missing_evidence_warnings"] for mapping in matrix["control_mappings"])
    assert any(mapping["source_docs"] for mapping in matrix["control_mappings"])

    pack_response = client.post("/compliance/control-pack", headers=auth_headers, json={"write_artifact": True})
    assert pack_response.status_code == 200
    pack = pack_response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "compliance_packs" in pack["artifact_path"]
    assert "Control Mapping Pack" in pack["markdown"]
    assert "## Control Coverage" in pack["markdown"]
    assert pack["pack"]["control_coverage"]["control_family_count"] == 8
    assert pack["pack"]["unsupported_claims"]
    assert pack["pack"]["owner_actions"]


def test_compliance_dashboard_smoke_api_contract_and_launch_wiring(client, auth_headers):
    smoke_response = client.get("/ui/dashboard-smoke", headers=auth_headers)
    assert smoke_response.status_code == 200
    smoke = smoke_response.json()
    compliance_view = next(view for view in smoke["expected_views"] if view["label"] == "Compliance Evidence")
    assert compliance_view["status"] == "pass"
    assert compliance_view["artifact_root"] == "compliance_packs"
    endpoint_paths = {endpoint["path"]: endpoint for endpoint in smoke["endpoint_references"]}
    assert endpoint_paths["/compliance/evidence-matrix"]["status"] == "pass"
    assert endpoint_paths["/compliance/control-pack"]["status"] == "pass"

    launch_response = client.get("/ops/smoke-matrix", headers=auth_headers)
    assert launch_response.status_code == 200
    launch = launch_response.json()
    paths = {row["path"]: row for row in launch["rows"]}
    assert "/compliance/evidence-matrix" in paths
    assert "storage/compliance_packs/*.md" in paths["/compliance/control-pack"]["required_artifact_expectations"]

    contract_response = client.get("/api/contract-audit", headers=auth_headers)
    assert contract_response.status_code == 200
    contract = contract_response.json()
    compliance_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["compliance"]}
    assert {"/compliance/evidence-matrix", "/compliance/control-pack"} <= compliance_endpoints
    assert "/compliance/control-pack" not in contract["generated_artifact_endpoint_coverage"]["missing_paths"]
