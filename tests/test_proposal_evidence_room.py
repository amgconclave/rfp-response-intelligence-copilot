from pathlib import Path


def test_proposal_evidence_room_manifest_links_release_state_artifact_hashes_and_approvals(client, auth_headers):
    client.post("/proposal/release-room-pack", headers=auth_headers, json={"write_artifact": True})

    response = client.get("/proposal/evidence-room", headers=auth_headers)

    assert response.status_code == 200
    manifest = response.json()
    assert manifest["title"] == "Buyer Proposal Evidence Room Manifest"
    assert manifest["status"] in {
        "ready_for_buyer_evidence_review",
        "requires_human_evidence_review",
        "requires_artifact_regeneration",
        "blocked_by_release_controls",
    }
    assert manifest["release_snapshot"]["room_id"].startswith("proposal-release-room-")
    assert manifest["summary"]["manifest_item_count"] == len(manifest["manifest_items"])
    assert manifest["summary"]["required_item_count"] >= 8
    assert {
        "durable workflows",
        "human-in-the-loop",
        "governance",
        "provider flexibility",
        "trace analysis",
    } <= set(manifest["summary"]["radar_patterns_used"])
    assert {item["artifact_root"] for item in manifest["manifest_items"]} >= {
        "buyer_intelligence",
        "proposal_release_room",
        "proposal_observability",
        "verification_evidence",
    }
    present_items = [item for item in manifest["manifest_items"] if item["status"] == "present"]
    assert present_items
    assert all(len(item["sha256"]) == 64 for item in present_items)
    assert all(Path(item["latest_file_path"]).exists() for item in present_items)
    assert manifest["approval_manifest"]["approval_policy"]
    assert any(
        control["control_id"] == "evidence-room-required-artifacts"
        for control in manifest["integrity_controls"]
    )
    assert any("/proposal/evidence-room-pack" in command for command in manifest["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.evidence_room_viewed" for event in audit["events"])


def test_proposal_evidence_room_pack_writes_artifacts_and_is_registered(client, auth_headers):
    response = client.post(
        "/proposal/evidence-room-pack",
        headers=auth_headers,
        json={"write_artifact": True},
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "proposal_evidence_room" in pack["artifact_path"]
    assert "Buyer Proposal Evidence Room Pack" in pack["markdown"]
    assert "Artifact Manifest" in pack["markdown"]
    assert pack["pack"]["manifest"]["summary"]["manifest_item_count"] == len(pack["manifest"]["manifest_items"])

    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"]: row for row in smoke["rows"]}
    assert "/proposal/evidence-room" in paths
    assert "/proposal/evidence-room-pack" in paths
    assert "storage/proposal_evidence_room/*.json" in paths["/proposal/evidence-room-pack"][
        "required_artifact_expectations"
    ]

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard_smoke["status"] == "pass"
    assert any(view["label"] == "Evidence Room" for view in dashboard_smoke["expected_views"])
    endpoint_paths = {endpoint["path"] for endpoint in dashboard_smoke["endpoint_references"]}
    assert {"/proposal/evidence-room", "/proposal/evidence-room-pack"} <= endpoint_paths

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "proposal_evidence_room" in {item["key"] for item in inventory["directories"]}

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    proposal_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["proposal"]}
    assert {"/proposal/evidence-room", "/proposal/evidence-room-pack"} <= proposal_endpoints
    assert "/proposal/evidence-room-pack" not in contract["generated_artifact_endpoint_coverage"]["missing_paths"]

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.evidence_room_pack_generated" for event in audit["events"])
