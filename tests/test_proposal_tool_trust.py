from pathlib import Path


def test_proposal_tool_trust_registry_scores_tools_and_blocks_external_provider(client, auth_headers):
    response = client.get("/proposal/tool-trust-registry", headers=auth_headers)

    assert response.status_code == 200
    registry = response.json()
    assert registry["title"] == "Proposal Tool Trust Registry"
    assert registry["status"] in {"pass", "needs_tool_owner_review", "blocked_tools_present"}
    assert registry["trust_registry"]
    assert registry["tool_risk_matrix"]
    assert registry["agent_policy_rollups"]
    assert {row["tool_id"] for row in registry["trust_registry"]} >= {
        "retrieval",
        "source_trust",
        "external_provider_without_governance",
        "submit_without_human_approval",
    }
    assert registry["provider_constraints"]["active_provider_mode"] == "mock"
    assert registry["provider_constraints"]["blocked_until_governance"] is True
    assert registry["budget_guardrails"]["decision"] == "pass"
    assert registry["shared_state_policy"]["append_only"] is True
    assert registry["human_approval_queue"]
    assert all(assertion["passed"] for assertion in registry["eval_assertions"])
    assert any("/proposal/tool-trust-pack" in command for command in registry["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.tool_trust_registry_viewed" for event in audit["events"])


def test_proposal_tool_trust_pack_writes_markdown_and_json(client, auth_headers):
    response = client.post("/proposal/tool-trust-pack", headers=auth_headers, json={"write_artifact": True})

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "tool_trust" in pack["artifact_path"]
    assert "Proposal Tool Trust Registry Pack" in pack["markdown"]
    assert "Provider Constraints" in pack["markdown"]
    assert pack["pack"]["registry"]["budget_guardrails"]["decision"] == "pass"

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.tool_trust_pack_generated" for event in audit["events"])


def test_proposal_tool_trust_is_in_smoke_dashboard_inventory_and_api_contract(client, auth_headers):
    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"]: row for row in smoke["rows"]}
    assert "/proposal/tool-trust-registry" in paths
    assert "/proposal/tool-trust-pack" in paths
    assert "storage/tool_trust/*.json" in paths["/proposal/tool-trust-pack"]["required_artifact_expectations"]

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard_smoke["status"] == "pass"
    endpoint_paths = {endpoint["path"] for endpoint in dashboard_smoke["endpoint_references"]}
    assert {"/proposal/tool-trust-registry", "/proposal/tool-trust-pack"} <= endpoint_paths

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "tool_trust" in {item["key"] for item in inventory["directories"]}

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    proposal_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["proposal"]}
    assert {"/proposal/tool-trust-registry", "/proposal/tool-trust-pack"} <= proposal_endpoints
    assert "/proposal/tool-trust-pack" not in contract["generated_artifact_endpoint_coverage"]["missing_paths"]
