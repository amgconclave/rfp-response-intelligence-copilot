from pathlib import Path


def test_proposal_intake_triage_routes_signals_tasks_and_checkpoints(client, auth_headers):
    response = client.get("/proposal/intake-triage", headers=auth_headers)

    assert response.status_code == 200
    triage = response.json()
    assert triage["title"] == "Proposal Intake Triage Gate"
    assert triage["status"] in {"ready", "needs_owner_review", "blocked_pending_qualification"}
    assert 0 <= triage["readiness_score"] <= 100
    assert triage["recommended_route"]
    assert triage["summary"]["requirement_count"] > 0
    assert triage["summary"]["external_provider_required"] is False
    assert triage["signals"]
    assert any(signal["owner_role"] == "compliance" for signal in triage["signals"])
    assert triage["owner_tasks"]
    assert all(task["task_id"].startswith("task-") for task in triage["owner_tasks"])
    assert [transition["sequence"] for transition in triage["state_transitions"]] == list(
        range(1, len(triage["state_transitions"]) + 1)
    )
    assert all(transition["checkpoint_key"] for transition in triage["state_transitions"])
    assert triage["dependency_contract"]["external_provider_required"] is False
    assert all(assertion["passed"] for assertion in triage["eval_assertions"])
    assert any("/proposal/intake-triage-pack" in command for command in triage["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.intake_triage_viewed" for event in audit["events"])


def test_proposal_intake_triage_pack_writes_markdown_and_json(client, auth_headers):
    response = client.post("/proposal/intake-triage-pack", headers=auth_headers, json={"write_artifact": True})

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "proposal_intake" in pack["artifact_path"]
    assert "Proposal Intake Triage Pack" in pack["markdown"]
    assert "Owner Task Delegation" in pack["markdown"]
    assert pack["pack"]["triage"]["dependency_contract"]["external_provider_required"] is False

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.intake_triage_pack_generated" for event in audit["events"])


def test_proposal_intake_is_in_smoke_dashboard_inventory_and_api_contract(client, auth_headers):
    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"]: row for row in smoke["rows"]}
    assert "/proposal/intake-triage" in paths
    assert "/proposal/intake-triage-pack" in paths
    assert "storage/proposal_intake/*.json" in paths["/proposal/intake-triage-pack"][
        "required_artifact_expectations"
    ]

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard_smoke["status"] == "pass"
    assert any(view["label"] == "Proposal Intake Triage" for view in dashboard_smoke["expected_views"])
    endpoint_paths = {endpoint["path"] for endpoint in dashboard_smoke["endpoint_references"]}
    assert {"/proposal/intake-triage", "/proposal/intake-triage-pack"} <= endpoint_paths

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "proposal_intake" in {item["key"] for item in inventory["directories"]}

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    proposal_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["proposal"]}
    assert {"/proposal/intake-triage", "/proposal/intake-triage-pack"} <= proposal_endpoints
    assert "/proposal/intake-triage-pack" not in contract["generated_artifact_endpoint_coverage"]["missing_paths"]
