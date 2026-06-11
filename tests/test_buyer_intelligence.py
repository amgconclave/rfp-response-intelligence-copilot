from pathlib import Path


def test_buyer_intelligence_workflow_exposes_durable_hilt_governance_and_provider_routes(client, auth_headers):
    response = client.get("/proposal/buyer-intelligence", headers=auth_headers)

    assert response.status_code == 200
    workflow = response.json()
    assert workflow["title"] == "Buyer-Grade Proposal Intelligence Workflow"
    assert workflow["workflow_status"] in {
        "ready_for_submission_review",
        "waiting_on_human_approval",
        "blocked",
    }
    assert workflow["durable_state"]["state_backend"] == "local_json_artifact"
    assert workflow["durable_state"]["checkpoint_count"] >= 6
    assert len(workflow["workflow_stages"]) >= 6
    assert any(stage["durability_key"] for stage in workflow["workflow_stages"])
    assert workflow["human_approval_queue"]
    assert any(gate["gate_id"] == "gate-human-approval" for gate in workflow["governance_gates"])
    assert {route["provider_mode"] for route in workflow["provider_routes"]} >= {
        "mock",
        "openai",
        "azure_openai",
    }
    assert workflow["trace_analysis"]["span_count"] >= 10
    assert any("/proposal/buyer-intelligence-pack" in command for command in workflow["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.buyer_intelligence_viewed" for event in audit["events"])


def test_buyer_intelligence_pack_writes_artifacts_and_state(client, auth_headers):
    response = client.post("/proposal/buyer-intelligence-pack", headers=auth_headers, json={"write_artifact": True})

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert pack["state_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert Path(pack["state_artifact_path"]).exists()
    assert "buyer_intelligence" in pack["artifact_path"]
    assert "Buyer-Grade Proposal Intelligence Pack" in pack["markdown"]
    assert "Durable Workflow" in pack["markdown"]
    assert pack["pack"]["workflow"]["durable_state"]["state_store_path"] == pack["state_artifact_path"]
    assert pack["workflow"]["durable_state"]["state_store_path"] is None

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.buyer_intelligence_pack_generated" for event in audit["events"])


def test_buyer_intelligence_is_in_smoke_dashboard_inventory_and_api_contract(client, auth_headers):
    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"]: row for row in smoke["rows"]}
    assert "/proposal/buyer-intelligence" in paths
    assert "/proposal/buyer-intelligence-pack" in paths
    assert "storage/buyer_intelligence/*.json" in paths["/proposal/buyer-intelligence-pack"][
        "required_artifact_expectations"
    ]

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard_smoke["status"] == "pass"
    assert any(view["label"] == "Buyer Intelligence Pack" for view in dashboard_smoke["expected_views"])
    endpoint_paths = {endpoint["path"] for endpoint in dashboard_smoke["endpoint_references"]}
    assert {"/proposal/buyer-intelligence", "/proposal/buyer-intelligence-pack"} <= endpoint_paths

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "buyer_intelligence" in {item["key"] for item in inventory["directories"]}

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    proposal_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["proposal"]}
    assert {"/proposal/buyer-intelligence", "/proposal/buyer-intelligence-pack"} <= proposal_endpoints
    assert "/proposal/buyer-intelligence-pack" not in contract["generated_artifact_endpoint_coverage"][
        "missing_paths"
    ]


def test_buyer_workflow_replay_exposes_transition_validation_and_eval_scenarios(client, auth_headers):
    response = client.get("/proposal/buyer-intelligence-replay", headers=auth_headers)

    assert response.status_code == 200
    replay = response.json()
    assert replay["title"] == "Buyer Workflow Replay and Transition Audit"
    assert replay["status"] == "pass"
    assert replay["transition_count"] >= 6
    assert replay["checkpoint_validation"]["status"] == "pass"
    assert replay["checkpoint_validation"]["transition_count"] == replay["transition_count"]
    assert [item["replay_order"] for item in replay["transitions"]] == list(range(1, replay["transition_count"] + 1))
    assert all(item["checkpoint_key"] for item in replay["transitions"])
    assert all(item["trace_refs"] for item in replay["transitions"])
    assert any(item["requires_human_review"] for item in replay["route_decisions"])
    assert {scenario["scenario_id"] for scenario in replay["eval_scenarios"]} >= {
        "buyer-workflow-ordering",
        "buyer-workflow-hitl-routing",
        "buyer-workflow-checkpoints",
        "buyer-workflow-traceability",
    }
    assert all(scenario["passed"] for scenario in replay["eval_scenarios"])
    assert any("/proposal/buyer-intelligence-replay-pack" in command for command in replay["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.buyer_intelligence_replay_viewed" for event in audit["events"])


def test_buyer_workflow_replay_pack_writes_artifacts_and_is_indexed(client, auth_headers):
    response = client.post(
        "/proposal/buyer-intelligence-replay-pack",
        headers=auth_headers,
        json={"write_artifact": True},
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "buyer_intelligence" in pack["artifact_path"]
    assert "buyer_workflow_replay" in pack["artifact_path"]
    assert "Buyer Workflow Replay Pack" in pack["markdown"]
    assert "Transition Replay" in pack["markdown"]
    assert pack["replay"]["checkpoint_validation"]["status"] == "pass"

    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"]: row for row in smoke["rows"]}
    assert "/proposal/buyer-intelligence-replay" in paths
    assert "/proposal/buyer-intelligence-replay-pack" in paths
    assert "storage/buyer_intelligence/*replay*.json" in paths["/proposal/buyer-intelligence-replay-pack"][
        "required_artifact_expectations"
    ]

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    endpoint_paths = {endpoint["path"] for endpoint in dashboard_smoke["endpoint_references"]}
    assert {
        "/proposal/buyer-intelligence-replay",
        "/proposal/buyer-intelligence-replay-pack",
    } <= endpoint_paths

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    proposal_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["proposal"]}
    assert {
        "/proposal/buyer-intelligence-replay",
        "/proposal/buyer-intelligence-replay-pack",
    } <= proposal_endpoints
    assert "/proposal/buyer-intelligence-replay-pack" not in contract["generated_artifact_endpoint_coverage"][
        "missing_paths"
    ]

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.buyer_intelligence_replay_pack_generated" for event in audit["events"])
