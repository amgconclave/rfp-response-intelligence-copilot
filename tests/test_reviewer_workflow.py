from pathlib import Path


def test_reviewer_workflow_and_pack_from_collaboration_board(client, auth_headers):
    board = client.post(
        "/rfp/reviewer-collaboration",
        headers=auth_headers,
        json={},
    ).json()

    response = client.post(
        "/rfp/reviewer-workflow",
        headers=auth_headers,
        json={"collaboration": board},
    )

    assert response.status_code == 200
    workflow = response.json()
    assert workflow["title"] == "Reviewer Collaboration Workflow"
    assert workflow["workflow_status"] in {
        "blocked",
        "needs_review",
        "pending_review",
        "ready_for_submission",
    }
    assert workflow["checkpoints"]
    assert workflow["transitions"]
    assert workflow["state_summary"]["checkpoint_count"] == len(workflow["checkpoints"])
    assert workflow["state_summary"]["transition_count"] == len(workflow["transitions"])
    assert "state machine workflow" in workflow["state_summary"]["patterns"]
    assert "traceable node transitions" in workflow["state_summary"]["patterns"]
    assert any(checkpoint["state"] == "redline_gate" for checkpoint in workflow["checkpoints"])
    assert any("reviewer-workflow-pack" in command for command in workflow["local_proof_commands"])

    pack_response = client.post(
        "/rfp/reviewer-workflow-pack",
        headers=auth_headers,
        json={"collaboration": board, "workflow": workflow, "write_artifact": True},
    )

    assert pack_response.status_code == 200
    pack = pack_response.json()
    artifact_path = Path(pack["artifact_path"])
    json_artifact_path = Path(pack["json_artifact_path"])
    assert artifact_path.exists()
    assert json_artifact_path.exists()
    assert "review_boards" in str(artifact_path)
    assert "Reviewer Collaboration Workflow Pack" in pack["markdown"]
    assert "## Checkpoints" in pack["markdown"]
    assert "## Transitions" in pack["markdown"]
    assert pack["workflow"]["state_summary"]["checkpoint_count"] >= 5


def test_reviewer_workflow_in_smoke_and_dashboard(client, auth_headers):
    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"] for row in smoke["rows"]}
    assert "/rfp/reviewer-workflow" in paths
    assert "/rfp/reviewer-workflow-pack" in paths
    assert any(
        row["path"] == "/rfp/reviewer-workflow-pack"
        and "storage/review_boards/*.md" in row["required_artifact_expectations"]
        for row in smoke["rows"]
    )

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard_smoke["status"] == "pass"
    assert any(
        endpoint["path"] == "/rfp/reviewer-workflow-pack"
        for endpoint in dashboard_smoke["endpoint_references"]
    )
