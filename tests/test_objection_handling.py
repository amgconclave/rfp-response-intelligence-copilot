from pathlib import Path

import pytest

from app.core.config import get_settings
from app.repositories.memory import repository
from app.services.container import get_container
from tests.conftest import ingest_corpus


@pytest.mark.asyncio
async def test_objection_service_generates_cited_confidence_and_review_workflow(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    get_container.cache_clear()
    repository.reset()
    container = get_container()
    for fixture_path, document_type in [
        ("sample_data/acme_enterprise_rfp.md", "rfp"),
        ("sample_data/prior_proposal.md", "proposal"),
        ("sample_data/product_overview.md", "product"),
        ("sample_data/security_policy.md", "security"),
        ("sample_data/compliance_policy.md", "compliance"),
        ("sample_data/pricing_notes.md", "pricing"),
        ("sample_data/implementation_guide.md", "implementation"),
        ("sample_data/dpa_privacy_policy.md", "privacy"),
        ("sample_data/ai_governance_security.md", "security"),
        ("sample_data/customer_success_onboarding.md", "customer_success"),
    ]:
        await container.ingestion.ingest_path(fixture_path, document_type=document_type, source="test")

    rfp_text = (container.settings.sample_data_dir / "acme_enterprise_rfp.md").read_text(encoding="utf-8")
    analysis = container.analysis.analyze(rfp_text, "objection-service-analysis")
    matrix = container.workbench.create_requirement_matrix(analysis)
    strategy = container.win_strategy.create_win_strategy(
        trace_id="objection-service-win",
        analysis=analysis,
        requirement_matrix=matrix,
        competitor_context=["Incumbent competitor is cheaper and bundling workflow tooling."],
        pricing_notes=["Discounts and custom packaging require approval."],
    )
    result = await container.objection_handling.objection_handling(
        "objection-service-test",
        analysis=analysis,
        requirement_matrix=matrix,
        win_strategy=strategy,
        competitor_context=["Incumbent competitor is cheaper and bundling workflow tooling."],
        pricing_notes=["Discounts and custom packaging require approval."],
        top_k=4,
    )

    assert result.title == "Competitive Objection Handling Pack"
    assert result.coverage_summary["objection_count"] == 5
    assert result.coverage_summary["coverage_ratio"] >= 0.8
    assert result.confidence_summary["average_confidence"] >= 0.45
    assert {"competitor", "pricing", "security", "compliance", "implementation"} == {
        item.concern_type for item in result.objections
    }
    assert any(item.citations for item in result.objections)
    assert all(item.required_reviewer_role for item in result.objections)
    assert any(endpoint["path"] == "/rfp/objection-handling-pack" for endpoint in result.endpoint_references)
    assert result.workflow_summary["replay_status"] == "pass"
    assert result.workflow_summary["transition_count"] >= result.coverage_summary["objection_count"] * 5
    assert all(item.checkpoint_key and item.route_decision for item in result.objections)
    assert all(len(item.workflow_trace) >= 5 for item in result.objections)
    assert all(assertion.passed for assertion in result.eval_assertions)

    pack = container.objection_handling.handling_pack("objection-service-pack", result, write_artifact=True)
    assert pack.artifact_path
    assert pack.json_artifact_path
    assert Path(pack.artifact_path).exists()
    assert Path(pack.json_artifact_path).exists()
    assert "objection_packs" in pack.artifact_path
    assert "Competitive Objection Handling Pack" in pack.markdown
    assert pack.pack["reviewer_workflow"]
    assert pack.pack["workflow_transitions"]
    assert pack.pack["eval_assertions"]
    assert "## Workflow Trace" in pack.markdown
    assert "## Eval Assertions" in pack.markdown
    repository.reset()
    get_settings.cache_clear()
    get_container.cache_clear()


def test_objection_endpoints_return_catalog_and_write_pack(client, auth_headers):
    ingest_corpus(client, auth_headers)

    response = client.post(
        "/rfp/objection-handling",
        headers=auth_headers,
        json={
            "competitor_context": ["Incumbent competitor is cheaper and bundled."],
            "pricing_notes": ["Any discount requires approval."],
            "top_k": 4,
        },
    )
    assert response.status_code == 200
    handling = response.json()
    assert handling["coverage_summary"]["objection_count"] == 5
    assert handling["coverage_summary"]["coverage_ratio"] >= 0.8
    assert handling["confidence_summary"]["average_confidence"] >= 0.45
    assert any(item["citations"] for item in handling["objections"])
    assert any(item["concern_type"] == "security" for item in handling["objections"])
    assert handling["workflow_summary"]["replay_status"] == "pass"
    assert handling["workflow_summary"]["transition_count"] >= handling["coverage_summary"]["objection_count"] * 5
    assert all(item["checkpoint_key"] for item in handling["objections"])
    assert all(assertion["passed"] for assertion in handling["eval_assertions"])

    pack_response = client.post(
        "/rfp/objection-handling-pack",
        headers=auth_headers,
        json={"objection_handling": handling, "write_artifact": True},
    )
    assert pack_response.status_code == 200
    pack = pack_response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "objection_packs" in pack["artifact_path"]
    assert "## Reviewer Workflow" in pack["markdown"]
    assert "## Workflow Trace" in pack["markdown"]
    assert "## Eval Assertions" in pack["markdown"]
    assert pack["pack"]["high_risk_objections"]
    assert pack["pack"]["endpoint_references"]
    assert pack["pack"]["workflow_transitions"]
    assert pack["pack"]["eval_assertions"]


def test_objection_dashboard_smoke_launch_and_contract_wiring(client, auth_headers):
    smoke_response = client.get("/ui/dashboard-smoke", headers=auth_headers)
    assert smoke_response.status_code == 200
    smoke = smoke_response.json()
    objection_view = next(view for view in smoke["expected_views"] if view["label"] == "Objection Handling Pack")
    assert objection_view["status"] == "pass"
    assert objection_view["artifact_root"] == "objection_packs"
    endpoint_paths = {endpoint["path"]: endpoint for endpoint in smoke["endpoint_references"]}
    assert endpoint_paths["/rfp/objection-handling"]["status"] == "pass"
    assert endpoint_paths["/rfp/objection-handling-pack"]["status"] == "pass"

    launch_response = client.get("/ops/smoke-matrix", headers=auth_headers)
    assert launch_response.status_code == 200
    launch = launch_response.json()
    paths = {row["path"]: row for row in launch["rows"]}
    assert "/rfp/objection-handling" in paths
    assert "storage/objection_packs/*.md" in paths["/rfp/objection-handling-pack"]["required_artifact_expectations"]

    inventory_response = client.get("/artifacts/inventory", headers=auth_headers)
    assert inventory_response.status_code == 200
    inventory_keys = {item["key"] for item in inventory_response.json()["directories"]}
    assert "objection_packs" in inventory_keys

    contract_response = client.get("/api/contract-audit", headers=auth_headers)
    assert contract_response.status_code == 200
    contract = contract_response.json()
    rfp_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["rfp_workflow"]}
    assert {"/rfp/objection-handling", "/rfp/objection-handling-pack"} <= rfp_endpoints
    assert "/rfp/objection-handling-pack" not in contract["generated_artifact_endpoint_coverage"]["missing_paths"]
