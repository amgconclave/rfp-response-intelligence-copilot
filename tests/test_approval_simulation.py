from pathlib import Path


def test_approval_simulation_defaults_to_checkpointed_human_review(client, auth_headers):
    response = client.post("/proposal/approval-simulation", headers=auth_headers, json={})

    assert response.status_code == 200
    simulation = response.json()
    assert simulation["title"] == "Proposal Approval Resolution Simulator"
    assert simulation["status"] in {
        "waiting_on_human_approval",
        "blocked_by_reviewer_decision",
        "ready_after_simulated_approval",
        "no_approval_queue",
    }
    assert simulation["workflow_id"].startswith("buyer-workflow-")
    assert simulation["decision_records"]
    assert all(record["checkpoint_key"] for record in simulation["decision_records"])
    assert all(record["trace_refs"] for record in simulation["decision_records"])
    assert simulation["durable_state_update"]["state_backend"] == "local_json_artifact"
    assert simulation["provider_policy"]["external_provider_required"] is False
    assert simulation["provider_policy"]["active_provider_mode"] == "mock"
    assert simulation["trace_analysis"]["span_count"] >= len(simulation["decision_records"])
    assert all(assertion["passed"] for assertion in simulation["eval_assertions"])
    assert any("/proposal/approval-simulation-pack" in command for command in simulation["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.approval_simulation_created" for event in audit["events"])


def test_approval_simulation_can_clear_human_gate_with_explicit_approvals(client, auth_headers):
    workflow = client.get("/proposal/buyer-intelligence", headers=auth_headers).json()
    decisions = [
        {
            "approval_id": item["approval_id"],
            "decision": "approve",
            "reviewer_role": item["reviewer_role"],
            "rationale": "Approved in local simulation for gate-clearance regression.",
        }
        for item in workflow["human_approval_queue"]
    ]

    response = client.post(
        "/proposal/approval-simulation",
        headers=auth_headers,
        json={"workflow": workflow, "requested_by": "qa_reviewer", "decisions": decisions},
    )

    assert response.status_code == 200
    simulation = response.json()
    assert simulation["requested_by"] == "qa_reviewer"
    assert simulation["unresolved_approval_count"] == 0
    assert {record["simulated_status"] for record in simulation["decision_records"]} == {"resolved"}
    human_gate = next(gate for gate in simulation["gate_impacts"] if gate["gate_id"] == "gate-human-approval")
    assert human_gate["simulated_status"] == "pass"
    assert simulation["simulated_workflow_status"] in {
        "ready_for_submission_review",
        "waiting_on_human_approval",
        "blocked",
    }


def test_approval_simulation_pack_writes_artifacts_and_is_indexed(client, auth_headers):
    response = client.post(
        "/proposal/approval-simulation-pack",
        headers=auth_headers,
        json={"write_artifact": True},
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert pack["state_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert Path(pack["state_artifact_path"]).exists()
    assert "approval_simulations" in pack["artifact_path"]
    assert "Proposal Approval Simulation Pack" in pack["markdown"]
    assert pack["pack"]["simulation"]["durable_state_update"]["state_store_path"] == pack["state_artifact_path"]

    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"]: row for row in smoke["rows"]}
    assert "/proposal/approval-simulation" in paths
    assert "/proposal/approval-simulation-pack" in paths
    assert "storage/approval_simulations/*.json" in paths["/proposal/approval-simulation-pack"][
        "required_artifact_expectations"
    ]

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    endpoint_paths = {endpoint["path"] for endpoint in dashboard_smoke["endpoint_references"]}
    assert {"/proposal/approval-simulation", "/proposal/approval-simulation-pack"} <= endpoint_paths

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "approval_simulations" in {item["key"] for item in inventory["directories"]}

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    proposal_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["proposal"]}
    assert {"/proposal/approval-simulation", "/proposal/approval-simulation-pack"} <= proposal_endpoints
    assert "/proposal/approval-simulation-pack" not in contract["generated_artifact_endpoint_coverage"][
        "missing_paths"
    ]

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.approval_simulation_pack_generated" for event in audit["events"])
