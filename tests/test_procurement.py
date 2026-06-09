from pathlib import Path

import pytest

from app.core.config import get_settings
from app.repositories.memory import repository
from app.services.container import get_container
from tests.conftest import ingest_corpus


@pytest.mark.asyncio
async def test_procurement_service_classifies_question_risk_and_approval_rules(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    get_container.cache_clear()
    repository.reset()
    container = get_container()
    for fixture_path, document_type in [
        ("sample_data/acme_enterprise_rfp.md", "rfp"),
        ("sample_data/security_policy.md", "security"),
        ("sample_data/compliance_policy.md", "compliance"),
        ("sample_data/pricing_notes.md", "pricing"),
        ("sample_data/implementation_guide.md", "implementation"),
        ("sample_data/dpa_privacy_policy.md", "privacy"),
        ("sample_data/sla_support_policy.md", "support"),
        ("sample_data/ai_governance_security.md", "security"),
        ("sample_data/disaster_recovery_plan.md", "disaster_recovery"),
        ("sample_data/customer_success_onboarding.md", "customer_success"),
        ("sample_data/customer_contract_terms.md", "contract"),
    ]:
        await container.ingestion.ingest_path(fixture_path, document_type=document_type, source="test")

    rfp_text = (container.settings.sample_data_dir / "acme_enterprise_rfp.md").read_text(encoding="utf-8")
    analysis = container.analysis.analyze(rfp_text, "procurement-service-analysis")
    matrix = container.workbench.create_requirement_matrix(analysis)
    review = container.review_board.review_package("procurement-service-review", requirement_matrix=matrix)
    result = await container.procurement.question_risk(
        "procurement-service-test",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review.findings,
    )

    assert result.title == "Procurement Q&A Risk Simulator + Approval Workflow"
    assert result.coverage_summary["question_count"] == 8
    assert {
        "security architecture",
        "privacy/DPA",
        "SLA/support",
        "disaster recovery",
        "AI governance/model claims",
        "pricing/commercial",
        "implementation timeline",
        "out-of-scope/adversarial unsupported claim",
    } <= set(result.coverage_summary["question_types"])
    assert result.approval_summary["auto_ready_count"] >= 1
    assert result.approval_summary["approvals_required_count"] >= 5
    assert result.approval_summary["blocked_count"] >= 1

    implementation = next(item for item in result.questions if item.question_type == "implementation timeline")
    assert implementation.approval_status == "auto_ready"
    assert implementation.evidence_support == "supported"
    assert implementation.citations

    security = next(item for item in result.questions if item.question_type == "security architecture")
    assert security.approval_status == "requires_reviewer_approval"
    assert security.required_reviewer_role == "Security Architect"
    assert security.citations

    adversarial = next(item for item in result.questions if item.question_id == "pq_adversarial_unsupported")
    assert adversarial.approval_status == "blocked"
    assert adversarial.unsupported_claim_flag is True
    assert adversarial.evidence_gaps
    repository.reset()
    get_settings.cache_clear()
    get_container.cache_clear()


@pytest.mark.asyncio
async def test_procurement_service_blocks_missing_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    get_container.cache_clear()
    repository.reset()
    container = get_container()
    for fixture_path, document_type in [
        ("sample_data/acme_enterprise_rfp.md", "rfp"),
        ("sample_data/security_policy.md", "security"),
    ]:
        await container.ingestion.ingest_path(fixture_path, document_type=document_type, source="test")

    rfp_text = (container.settings.sample_data_dir / "acme_enterprise_rfp.md").read_text(encoding="utf-8")
    analysis = container.analysis.analyze(rfp_text, "procurement-missing-analysis")
    matrix = container.workbench.create_requirement_matrix(analysis)
    result = await container.procurement.question_risk(
        "procurement-missing-test",
        analysis=analysis,
        requirement_matrix=matrix,
    )

    privacy = next(item for item in result.questions if item.question_type == "privacy/DPA")
    assert privacy.approval_status == "blocked"
    assert privacy.evidence_support == "missing"
    assert any("Priority evidence not retrieved" in gap for gap in privacy.evidence_gaps)
    assert result.approval_summary["blocked_count"] >= 2
    repository.reset()
    get_settings.cache_clear()
    get_container.cache_clear()


def test_procurement_endpoints_return_catalog_and_write_pack(client, auth_headers):
    ingest_corpus(client, auth_headers)

    risk_response = client.get("/procurement/question-risk", headers=auth_headers)
    assert risk_response.status_code == 200
    risk = risk_response.json()
    assert risk["coverage_summary"]["question_count"] == 8
    assert risk["approval_summary"]["blocked_count"] >= 1
    assert risk["approval_summary"]["auto_ready_count"] >= 1
    assert any(item["snippets"] for item in risk["questions"])
    assert any(item["unsupported_claim_flag"] for item in risk["questions"])

    pack_response = client.post(
        "/procurement/approval-pack",
        headers=auth_headers,
        json={"write_artifact": True},
    )
    assert pack_response.status_code == 200
    pack = pack_response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "procurement_packs" in pack["artifact_path"]
    assert "Approval Workflow Pack" in pack["markdown"]
    assert "## High-Risk Questions" in pack["markdown"]
    assert pack["pack"]["high_risk_questions"]
    assert pack["pack"]["reviewer_checklist"]
    assert pack["pack"]["escalation_owners"]
    assert pack["pack"]["evidence_gaps"]


def test_procurement_dashboard_smoke_api_contract_and_launch_wiring(client, auth_headers):
    smoke_response = client.get("/ui/dashboard-smoke", headers=auth_headers)
    assert smoke_response.status_code == 200
    smoke = smoke_response.json()
    procurement_view = next(view for view in smoke["expected_views"] if view["label"] == "Procurement Q&A")
    assert procurement_view["status"] == "pass"
    assert procurement_view["artifact_root"] == "procurement_packs"
    endpoint_paths = {endpoint["path"]: endpoint for endpoint in smoke["endpoint_references"]}
    assert endpoint_paths["/procurement/question-risk"]["status"] == "pass"
    assert endpoint_paths["/procurement/approval-pack"]["status"] == "pass"

    launch_response = client.get("/ops/smoke-matrix", headers=auth_headers)
    assert launch_response.status_code == 200
    launch = launch_response.json()
    paths = {row["path"]: row for row in launch["rows"]}
    assert "/procurement/question-risk" in paths
    assert "storage/procurement_packs/*.md" in paths["/procurement/approval-pack"]["required_artifact_expectations"]

    contract_response = client.get("/api/contract-audit", headers=auth_headers)
    assert contract_response.status_code == 200
    contract = contract_response.json()
    procurement_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["procurement"]}
    assert {"/procurement/question-risk", "/procurement/approval-pack"} <= procurement_endpoints
    assert "/procurement/approval-pack" not in contract["generated_artifact_endpoint_coverage"]["missing_paths"]
