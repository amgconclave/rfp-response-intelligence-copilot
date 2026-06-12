from pathlib import Path


def test_reviewer_escalation_plan_and_pack(client, auth_headers):
    board = client.post("/rfp/reviewer-collaboration", headers=auth_headers, json={}).json()
    workflow = client.post(
        "/rfp/reviewer-workflow",
        headers=auth_headers,
        json={"collaboration": board},
    ).json()
    ledger = client.post(
        "/rfp/reviewer-signoff-ledger",
        headers=auth_headers,
        json={"collaboration": board, "workflow": workflow},
    ).json()

    response = client.post(
        "/rfp/reviewer-escalations",
        headers=auth_headers,
        json={
            "collaboration": board,
            "workflow": workflow,
            "ledger": ledger,
            "sla_hours": {"critical": 2, "legal": 4},
        },
    )

    assert response.status_code == 200
    escalation = response.json()
    assert escalation["title"] == "Reviewer SLA Escalation Plan"
    assert escalation["status"] in {"blocked_escalation", "escalated", "watch", "clear"}
    assert escalation["summary"]["escalation_count"] == len(escalation["escalation_items"])
    assert escalation["checkpoints"]
    assert escalation["transitions"]
    assert escalation["role_crew_queue"]
    assert "typed contracts" in escalation["summary"]["patterns"]
    assert "role crews" in escalation["summary"]["patterns"]
    assert "conditional routing" in escalation["summary"]["patterns"]
    assert any("reviewer-escalation-pack" in command for command in escalation["local_proof_commands"])

    pack_response = client.post(
        "/rfp/reviewer-escalation-pack",
        headers=auth_headers,
        json={
            "collaboration": board,
            "workflow": workflow,
            "ledger": ledger,
            "escalation": escalation,
            "write_artifact": True,
        },
    )

    assert pack_response.status_code == 200
    pack = pack_response.json()
    artifact_path = Path(pack["artifact_path"])
    json_artifact_path = Path(pack["json_artifact_path"])
    assert artifact_path.exists()
    assert json_artifact_path.exists()
    assert "reviewer_escalations" in str(artifact_path)
    assert "Reviewer SLA Escalation Pack" in pack["markdown"]
    assert "## Escalation Items" in pack["markdown"]
    assert "## Role Crew Queue" in pack["markdown"]
    assert pack["pack"]["escalation"]["summary"]["escalation_count"] == len(escalation["escalation_items"])


def test_reviewer_escalation_registered_for_local_review_surfaces(client, auth_headers):
    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"] for row in smoke["rows"]}
    assert "/rfp/reviewer-escalations" in paths
    assert "/rfp/reviewer-escalation-pack" in paths
    assert any(
        "storage/reviewer_escalations" in expectation
        for row in smoke["rows"]
        for expectation in row["required_artifact_expectations"]
    )

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "reviewer_escalations" in {item["key"] for item in inventory["directories"]}

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard_smoke["status"] == "pass"
    assert any(
        endpoint["path"] == "/rfp/reviewer-escalation-pack"
        for endpoint in dashboard_smoke["endpoint_references"]
    )
