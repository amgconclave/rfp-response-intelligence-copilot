from pathlib import Path


def test_proposal_agent_council_exposes_roles_shared_state_handoffs_and_budget(client, auth_headers):
    response = client.get("/proposal/agent-council", headers=auth_headers)

    assert response.status_code == 200
    council = response.json()
    assert council["title"] == "Proposal Agent Council"
    assert council["status"] in {
        "ready_for_executive_review",
        "needs_human_handoff",
        "blocked_by_governance",
    }
    assert {agent["agent_id"] for agent in council["agents"]} >= {
        "agent-sales",
        "agent-presales",
        "agent-compliance",
        "agent-procurement",
        "agent-proposal-manager",
    }
    assert council["shared_state"]["requirements"] > 0
    assert council["shared_state"]["state_policy"].startswith("append-only")
    assert [message["turn"] for message in council["conversation"]] == list(
        range(1, len(council["conversation"]) + 1)
    )
    assert any(message["tool_calls"] for message in council["conversation"])
    assert council["handoffs"]
    assert all(row["allowed_tools"] and row["blocked_tools"] for row in council["tool_governance"])
    assert council["budget_ledger"]["provider_mode"] == "mock"
    assert council["budget_ledger"]["total_token_estimate"] > 0
    assert all(scenario["passed"] for scenario in council["eval_scenarios"])
    assert any("/proposal/agent-council-pack" in command for command in council["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.agent_council_viewed" for event in audit["events"])


def test_proposal_agent_council_pack_writes_markdown_json_and_transcript(client, auth_headers):
    response = client.post("/proposal/agent-council-pack", headers=auth_headers, json={"write_artifact": True})

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert pack["transcript_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert Path(pack["transcript_artifact_path"]).exists()
    assert "agent_council" in pack["artifact_path"]
    assert "Proposal Agent Council Pack" in pack["markdown"]
    assert "Tool Governance" in pack["markdown"]
    assert pack["pack"]["council"]["budget_ledger"]["total_token_estimate"] > 0

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.agent_council_pack_generated" for event in audit["events"])


def test_proposal_agent_council_is_in_smoke_dashboard_inventory_and_api_contract(client, auth_headers):
    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"]: row for row in smoke["rows"]}
    assert "/proposal/agent-council" in paths
    assert "/proposal/agent-council-pack" in paths
    assert "storage/agent_council/*.json" in paths["/proposal/agent-council-pack"][
        "required_artifact_expectations"
    ]

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard_smoke["status"] == "pass"
    assert any(view["label"] == "Agent Council" for view in dashboard_smoke["expected_views"])
    endpoint_paths = {endpoint["path"] for endpoint in dashboard_smoke["endpoint_references"]}
    assert {"/proposal/agent-council", "/proposal/agent-council-pack"} <= endpoint_paths

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "agent_council" in {item["key"] for item in inventory["directories"]}

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    proposal_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["proposal"]}
    assert {"/proposal/agent-council", "/proposal/agent-council-pack"} <= proposal_endpoints
    assert "/proposal/agent-council-pack" not in contract["generated_artifact_endpoint_coverage"]["missing_paths"]
