from pathlib import Path


def test_submission_escrow_exposes_hash_lock_queue_checkpoints_and_eval_assertions(client, auth_headers):
    response = client.get("/proposal/submission-escrow", headers=auth_headers)

    assert response.status_code == 200
    escrow = response.json()
    assert escrow["title"] == "Proposal Submission Escrow Ledger"
    assert escrow["status"] in {
        "release_locked",
        "awaiting_owner_signoff",
        "requires_artifact_regeneration",
        "blocked_by_release_controls",
        "blocked_by_escrow_controls",
    }
    assert 0 <= escrow["custody_score"] <= 100
    assert escrow["escrow_records"]
    assert all(record["checkpoint_key"] for record in escrow["escrow_records"])
    assert all(record["source_endpoint"] for record in escrow["escrow_records"])
    assert escrow["summary"]["record_count"] == len(escrow["escrow_records"])
    assert escrow["summary"]["checkpoint_count"] == len(escrow["custody_checkpoints"])
    assert {
        "typed contracts",
        "structured outputs",
        "dependency injection",
        "state machine workflow",
        "checkpointing",
        "traceable node transitions",
        "eval-friendly design",
    } <= set(escrow["summary"]["radar_patterns_used"])
    assert all(assertion["passed"] for assertion in escrow["eval_assertions"])
    assert any("/proposal/submission-escrow-pack" in command for command in escrow["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.submission_escrow_viewed" for event in audit["events"])


def test_submission_escrow_pack_writes_artifacts_and_is_registered(client, auth_headers):
    response = client.post(
        "/proposal/submission-escrow-pack",
        headers=auth_headers,
        json={"write_artifact": True},
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "proposal_submission_escrow" in pack["artifact_path"]
    assert "Proposal Submission Escrow Pack" in pack["markdown"]
    assert pack["pack"]["escrow"]["summary"]["record_count"] == len(pack["escrow"]["escrow_records"])

    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"]: row for row in smoke["rows"]}
    assert "/proposal/submission-escrow" in paths
    assert "/proposal/submission-escrow-pack" in paths
    assert "storage/proposal_submission_escrow/*.json" in paths["/proposal/submission-escrow-pack"][
        "required_artifact_expectations"
    ]

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard_smoke["status"] == "pass"
    assert any(view["label"] == "Submission Escrow" for view in dashboard_smoke["expected_views"])
    endpoint_paths = {endpoint["path"] for endpoint in dashboard_smoke["endpoint_references"]}
    assert {"/proposal/submission-escrow", "/proposal/submission-escrow-pack"} <= endpoint_paths

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "proposal_submission_escrow" in {item["key"] for item in inventory["directories"]}

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    proposal_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["proposal"]}
    assert {"/proposal/submission-escrow", "/proposal/submission-escrow-pack"} <= proposal_endpoints
    assert "/proposal/submission-escrow-pack" not in contract["generated_artifact_endpoint_coverage"][
        "missing_paths"
    ]

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.submission_escrow_pack_generated" for event in audit["events"])
