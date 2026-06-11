from pathlib import Path

import pytest

from app.core.config import get_settings
from app.repositories.memory import repository
from app.services.container import get_container
from tests.conftest import ingest_corpus


@pytest.mark.asyncio
async def test_procurement_risk_desk_service_routes_packet_risks(tmp_path, monkeypatch):
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
        ("sample_data/customer_success_onboarding.md", "customer_success"),
        ("sample_data/customer_contract_terms.md", "contract"),
    ]:
        await container.ingestion.ingest_path(fixture_path, document_type=document_type, source="test")

    rfp_text = (container.settings.sample_data_dir / "acme_enterprise_rfp.md").read_text(encoding="utf-8")
    analysis = container.analysis.analyze(rfp_text, "risk-desk-analysis")
    matrix = container.workbench.create_requirement_matrix(analysis)
    review = container.review_board.review_package("risk-desk-review", requirement_matrix=matrix)
    customer_fit = container.customer_intelligence.customer_fit(
        "regulated_healthcare",
        "risk-desk-customer-fit",
        analysis=analysis,
        requirement_matrix=matrix,
    )
    readiness = container.deal_readiness.create_scorecard(
        "risk-desk-readiness",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review.findings,
        customer_fit=customer_fit,
    )
    win_strategy = container.win_strategy.create_win_strategy(
        "risk-desk-win-strategy",
        analysis=analysis,
        requirement_matrix=matrix,
        customer_fit=customer_fit,
        readiness_scorecard=readiness,
        review_findings=review.findings,
    )
    contract_risk = container.contract_risk.analyze(
        (container.settings.sample_data_dir / "customer_contract_terms.md").read_text(encoding="utf-8"),
        "risk-desk-contract",
        customer_profile_id="regulated_healthcare",
    )
    procurement_risk = await container.procurement.question_risk(
        "risk-desk-procurement",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review.findings,
    )

    desk = await container.procurement_risk_desk.risk_desk(
        "risk-desk-service-test",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review.findings,
        contract_risk=contract_risk,
        win_strategy=win_strategy,
        procurement_risk=procurement_risk,
    )

    assert desk.title == "Procurement Risk Desk Pack"
    assert desk.summary["risk_count"] == 5
    assert {"legal", "pricing", "data_residency", "insurance", "implementation"} == {
        item.category for item in desk.risks
    }
    assert desk.summary["citation_count"] > 0
    assert desk.owner_routing
    assert desk.workflow_stages
    assert desk.workflow_stages[0]["checkpoint_id"] == "procurement-risk-desk.packet-scan.v1"
    assert set(desk.governance_summary["implemented_patterns"]) >= {
        "durable_workflows",
        "human_in_the_loop",
        "trace_analysis",
    }
    assert desk.human_review_queue
    assert all(row["required_decision"] for row in desk.human_review_queue)
    assert {span["operation"] for span in desk.trace_spans} >= {
        "packet_category_scan",
        "owner_review_routing",
        "submission_release_gate",
    }
    assert any(item.owner_role == "Legal Counsel" for item in desk.risks)
    assert any(item.category == "insurance" for item in desk.risks)

    pack = container.procurement_risk_desk.risk_desk_pack("risk-desk-pack-test", desk, write_artifact=True)
    assert pack.artifact_path
    assert pack.json_artifact_path
    assert Path(pack.artifact_path).exists()
    assert Path(pack.json_artifact_path).exists()
    assert "procurement_risk_desk" in pack.artifact_path
    assert "## Owner Routing" in pack.markdown
    assert "## Durable Workflow Gates" in pack.markdown
    assert "## Human Review Queue" in pack.markdown
    assert "## Trace Analysis" in pack.markdown
    assert pack.pack["risks"]
    assert pack.pack["workflow_stages"]
    assert pack.pack["human_review_queue"]
    assert pack.pack["trace_spans"]
    repository.reset()
    get_settings.cache_clear()
    get_container.cache_clear()


def test_procurement_risk_desk_endpoints_and_repo_wiring(client, auth_headers):
    ingest_corpus(client, auth_headers)

    response = client.get("/procurement/risk-desk", headers=auth_headers)
    assert response.status_code == 200
    desk = response.json()
    assert desk["summary"]["risk_count"] == 5
    assert desk["summary"]["citation_count"] > 0
    assert {item["category"] for item in desk["risks"]} >= {"legal", "pricing", "data_residency"}
    assert desk["owner_routing"]
    assert desk["workflow_stages"]
    assert desk["human_review_queue"]
    assert desk["trace_spans"]
    assert desk["governance_summary"]["release_gate"] in {
        "hold_submission",
        "owner_review_required",
        "can_submit",
    }

    pack_response = client.post(
        "/procurement/risk-desk-pack",
        headers=auth_headers,
        json={"write_artifact": True},
    )
    assert pack_response.status_code == 200
    pack = pack_response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "procurement_risk_desk" in pack["artifact_path"]
    assert "Procurement Risk Desk Pack" in pack["markdown"]
    assert "Durable Workflow Gates" in pack["markdown"]
    assert pack["pack"]["governance_summary"]["implemented_patterns"][:2] == [
        "durable_workflows",
        "human_in_the_loop",
    ]

    smoke_response = client.get("/ui/dashboard-smoke", headers=auth_headers)
    assert smoke_response.status_code == 200
    smoke = smoke_response.json()
    risk_desk_view = next(view for view in smoke["expected_views"] if view["label"] == "Procurement Risk Desk")
    assert risk_desk_view["status"] == "pass"
    assert risk_desk_view["artifact_root"] == "procurement_risk_desk"
    endpoint_paths = {endpoint["path"]: endpoint for endpoint in smoke["endpoint_references"]}
    assert endpoint_paths["/procurement/risk-desk"]["status"] == "pass"
    assert endpoint_paths["/procurement/risk-desk-pack"]["status"] == "pass"

    launch_response = client.get("/ops/smoke-matrix", headers=auth_headers)
    assert launch_response.status_code == 200
    launch = launch_response.json()
    paths = {row["path"]: row for row in launch["rows"]}
    assert "/procurement/risk-desk" in paths
    assert "storage/procurement_risk_desk/*.md" in paths["/procurement/risk-desk-pack"][
        "required_artifact_expectations"
    ]

    contract_response = client.get("/api/contract-audit", headers=auth_headers)
    assert contract_response.status_code == 200
    contract = contract_response.json()
    procurement_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["procurement"]}
    assert {"/procurement/risk-desk", "/procurement/risk-desk-pack"} <= procurement_endpoints
    assert "/procurement/risk-desk-pack" not in contract["generated_artifact_endpoint_coverage"]["missing_paths"]
