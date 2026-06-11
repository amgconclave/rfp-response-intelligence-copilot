from pathlib import Path


def _passing_results() -> list[dict]:
    return [
        {"command_id": "pytest", "status": "pass", "observed_output": "all tests passed"},
        {"command_id": "ruff", "status": "pass", "observed_output": "All checks passed!"},
        {"command_id": "standard_eval", "status": "pass", "observed_output": "Pass/fail summary: PASS"},
        {"command_id": "red_team", "status": "pass", "observed_output": "Pass/fail summary: PASS"},
        {"command_id": "dashboard_smoke", "status": "pass", "observed_output": "Dashboard smoke status: pass"},
        {"command_id": "demo", "status": "pass", "observed_output": "Final demo summary ... red_team=True"},
    ]


def test_verification_evidence_get_returns_pending_local_ledger(client, auth_headers):
    response = client.get("/ops/verification-evidence", headers=auth_headers)

    assert response.status_code == 200
    evidence = response.json()
    assert evidence["title"] == "Verification Evidence Ledger"
    assert evidence["status"] in {"pending_command_evidence", "blocked", "needs_dashboard_review"}
    assert evidence["summary"]["required_command_count"] == 6
    assert evidence["summary"]["recorded_command_count"] == 0
    assert evidence["summary"]["external_services_required"] is False
    assert {row["command_id"] for row in evidence["command_evidence"]} == {
        "pytest",
        "ruff",
        "standard_eval",
        "red_team",
        "dashboard_smoke",
        "demo",
    }
    assert evidence["release_gate_snapshot"]["verification_check_count"] > 0
    assert evidence["artifact_inventory_snapshot"]["verification_evidence_indexed"] is True
    assert any("/ops/verification-evidence-pack" in command for command in evidence["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "ops.verification_evidence_viewed" for event in audit["events"])


def test_verification_evidence_post_accepts_observed_command_results(client, auth_headers):
    response = client.post(
        "/ops/verification-evidence",
        headers=auth_headers,
        json={"command_results": _passing_results()},
    )

    assert response.status_code == 200
    evidence = response.json()
    assert evidence["summary"]["recorded_command_count"] == 6
    assert evidence["summary"]["passed_command_count"] == 6
    assert evidence["summary"]["failed_command_count"] == 0
    assert evidence["summary"]["unrecorded_command_ids"] == []
    assert evidence["status"] in {"accepted", "blocked", "needs_dashboard_review"}
    assert all(row["status"] == "pass" for row in evidence["command_evidence"])


def test_verification_evidence_pack_writes_artifacts_and_is_indexed(client, auth_headers):
    response = client.post(
        "/ops/verification-evidence-pack",
        headers=auth_headers,
        json={"write_artifact": True, "command_results": _passing_results()},
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "verification_evidence" in pack["artifact_path"]
    assert "Verification Evidence Pack" in pack["markdown"]
    assert "Command Evidence" in pack["markdown"]
    assert pack["pack"]["evidence"]["summary"]["recorded_command_count"] == 6

    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"]: row for row in smoke["rows"]}
    assert "/ops/verification-evidence" in paths
    assert "/ops/verification-evidence-pack" in paths
    assert "storage/verification_evidence/*.json" in paths["/ops/verification-evidence-pack"][
        "required_artifact_expectations"
    ]

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard_smoke["status"] == "pass"
    assert any(view["label"] == "Verification Evidence" for view in dashboard_smoke["expected_views"])
    endpoint_paths = {endpoint["path"] for endpoint in dashboard_smoke["endpoint_references"]}
    assert {"/ops/verification-evidence", "/ops/verification-evidence-pack"} <= endpoint_paths

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "verification_evidence" in {item["key"] for item in inventory["directories"]}

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    ops_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["operations"]}
    assert {"/ops/verification-evidence", "/ops/verification-evidence-pack"} <= ops_endpoints
    assert "/ops/verification-evidence-pack" not in contract["generated_artifact_endpoint_coverage"][
        "missing_paths"
    ]

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "ops.verification_evidence_pack_generated" for event in audit["events"])
