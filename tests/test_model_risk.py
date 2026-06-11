from pathlib import Path

from tests.conftest import ingest_corpus


def test_model_risk_register_and_pack(client, auth_headers):
    ingest_corpus(client, auth_headers)

    register_response = client.get("/governance/model-risk-register", headers=auth_headers)
    assert register_response.status_code == 200
    register = register_response.json()
    assert register["title"] == "Model Risk Register"
    assert register["register_status"] in {"approved", "needs_review", "blocked"}
    assert register["summary"]["risk_count"] >= 6
    assert register["summary"]["high_or_critical_count"] >= 3
    assert register["release_gates"]
    assert any(risk["risk_id"] == "model_risk_01_groundedness" for risk in register["risks"])
    assert any(risk["evidence_sources"] for risk in register["risks"])
    assert any("run_eval" in command for command in register["local_proof_commands"])
    assert any("run_red_team" in command for command in register["local_proof_commands"])

    pack_response = client.post("/governance/model-risk-pack", headers=auth_headers, json={"write_artifact": True})
    assert pack_response.status_code == 200
    pack = pack_response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "model_risk" in pack["artifact_path"]
    assert "Model Risk Register Pack" in pack["markdown"]
    assert "## Release Gates" in pack["markdown"]
    assert pack["pack"]["summary"]["risk_count"] == register["summary"]["risk_count"]


def test_model_risk_smoke_dashboard_contract_and_inventory(client, auth_headers):
    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"]: row for row in smoke["rows"]}
    assert "/governance/model-risk-register" in paths
    assert "/governance/model-risk-pack" in paths
    assert "storage/model_risk/*.md" in paths["/governance/model-risk-pack"]["required_artifact_expectations"]

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard_smoke["status"] == "pass"
    assert any(view["label"] == "Model Risk Register" for view in dashboard_smoke["expected_views"])
    endpoint_paths = {endpoint["path"] for endpoint in dashboard_smoke["endpoint_references"]}
    assert {"/governance/model-risk-register", "/governance/model-risk-pack"} <= endpoint_paths

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "model_risk" in {item["key"] for item in inventory["directories"]}

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    governance_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["governance"]}
    assert {"/governance/model-risk-register", "/governance/model-risk-pack"} <= governance_endpoints
    assert "/governance/model-risk-pack" not in contract["generated_artifact_endpoint_coverage"]["missing_paths"]
