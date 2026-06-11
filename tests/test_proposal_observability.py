from pathlib import Path


def test_proposal_observability_rolls_up_traces_diagnostics_governance_and_provider_signals(client, auth_headers):
    response = client.get("/ops/proposal-observability", headers=auth_headers)

    assert response.status_code == 200
    observability = response.json()
    assert observability["title"] == "Proposal Observability Control Plane"
    assert observability["status"] in {
        "ready_for_observability_review",
        "needs_human_review",
        "needs_retrieval_review",
        "blocked_by_governance",
        "insufficient_trace_coverage",
    }
    assert observability["summary"]["trace_span_count"] == len(observability["trace_map"])
    assert observability["summary"]["trace_span_count"] >= 20
    assert {
        "trace analysis",
        "retrieval diagnostics",
        "experiment comparison",
        "governance",
        "human-in-the-loop",
        "provider flexibility",
    } <= set(observability["summary"]["radar_patterns_used"])
    assert {row["trace_type"] for row in observability["trace_map"]} >= {
        "workflow_stage",
        "workflow_transition",
        "agent_turn",
        "provenance_node",
        "retrieval_experiment",
    }
    assert observability["retrieval_diagnostics"]
    assert observability["experiment_comparison"]["recommended_policy_id"]
    assert observability["provider_and_cost_signals"]["provider_mode"] == "mock"
    assert observability["provider_and_cost_signals"]["local_mock_default"] is True
    assert observability["human_review_signals"]
    assert any("/ops/proposal-observability-pack" in command for command in observability["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "ops.proposal_observability_viewed" for event in audit["events"])


def test_proposal_observability_pack_writes_artifacts_and_is_indexed(client, auth_headers):
    response = client.post(
        "/ops/proposal-observability-pack",
        headers=auth_headers,
        json={"write_artifact": True},
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "proposal_observability" in pack["artifact_path"]
    assert "Proposal Observability Pack" in pack["markdown"]
    assert "Retrieval Diagnostics" in pack["markdown"]
    assert pack["pack"]["observability"]["summary"]["trace_span_count"] == len(pack["observability"]["trace_map"])

    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"]: row for row in smoke["rows"]}
    assert "/ops/proposal-observability" in paths
    assert "/ops/proposal-observability-pack" in paths
    assert "storage/proposal_observability/*.json" in paths["/ops/proposal-observability-pack"][
        "required_artifact_expectations"
    ]

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard_smoke["status"] == "pass"
    assert any(view["label"] == "Proposal Observability" for view in dashboard_smoke["expected_views"])
    endpoint_paths = {endpoint["path"] for endpoint in dashboard_smoke["endpoint_references"]}
    assert {"/ops/proposal-observability", "/ops/proposal-observability-pack"} <= endpoint_paths

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "proposal_observability" in {item["key"] for item in inventory["directories"]}

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    ops_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["operations"]}
    assert {"/ops/proposal-observability", "/ops/proposal-observability-pack"} <= ops_endpoints
    assert "/ops/proposal-observability-pack" not in contract["generated_artifact_endpoint_coverage"][
        "missing_paths"
    ]

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "ops.proposal_observability_pack_generated" for event in audit["events"])
