from pathlib import Path


def test_proposal_release_room_composes_governance_hitl_provider_and_trace_controls(client, auth_headers):
    response = client.get("/proposal/release-room", headers=auth_headers)

    assert response.status_code == 200
    room = response.json()
    assert room["title"] == "Buyer Proposal Release Room"
    assert room["status"] in {
        "ready_for_buyer_release",
        "requires_human_release_review",
        "blocked_by_release_controls",
    }
    assert room["release_recommendation"]
    assert 0 <= room["readiness_score"] <= 100
    assert room["decision_board"]
    assert room["hitl_queue"]
    assert room["provider_route"]["recommended_route_id"] == "provider.mock.local"
    assert room["provider_route"]["local_mock_default"] is True
    assert room["summary"]["durable_checkpoint_count"] == len(room["durable_checkpoints"])
    assert room["summary"]["trace_source_count"] == len(room["trace_coverage"])
    assert room["summary"]["trace_span_count"] >= 20
    assert {
        "durable workflows",
        "human-in-the-loop",
        "governance",
        "provider flexibility",
        "trace analysis",
    } <= set(room["summary"]["radar_patterns_used"])
    assert all(assertion["passed"] for assertion in room["eval_assertions"])
    assert any("/proposal/release-room-pack" in command for command in room["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.release_room_viewed" for event in audit["events"])


def test_proposal_release_room_pack_writes_artifacts_and_is_registered(client, auth_headers):
    response = client.post(
        "/proposal/release-room-pack",
        headers=auth_headers,
        json={"write_artifact": True},
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "proposal_release_room" in pack["artifact_path"]
    assert "Buyer Proposal Release Room Pack" in pack["markdown"]
    assert "Decision Board" in pack["markdown"]
    assert pack["pack"]["release_room"]["summary"]["hitl_queue_count"] == len(pack["release_room"]["hitl_queue"])

    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"]: row for row in smoke["rows"]}
    assert "/proposal/release-room" in paths
    assert "/proposal/release-room-pack" in paths
    assert "storage/proposal_release_room/*.json" in paths["/proposal/release-room-pack"][
        "required_artifact_expectations"
    ]

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard_smoke["status"] == "pass"
    assert any(view["label"] == "Release Room" for view in dashboard_smoke["expected_views"])
    endpoint_paths = {endpoint["path"] for endpoint in dashboard_smoke["endpoint_references"]}
    assert {"/proposal/release-room", "/proposal/release-room-pack"} <= endpoint_paths

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "proposal_release_room" in {item["key"] for item in inventory["directories"]}

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    proposal_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["proposal"]}
    assert {"/proposal/release-room", "/proposal/release-room-pack"} <= proposal_endpoints
    assert "/proposal/release-room-pack" not in contract["generated_artifact_endpoint_coverage"]["missing_paths"]

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.release_room_pack_generated" for event in audit["events"])
