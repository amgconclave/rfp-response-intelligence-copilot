from pathlib import Path


def test_reviewer_signoff_ledger_and_pack(client, auth_headers):
    board = client.post("/rfp/reviewer-collaboration", headers=auth_headers, json={}).json()
    workflow = client.post(
        "/rfp/reviewer-workflow",
        headers=auth_headers,
        json={"collaboration": board},
    ).json()

    response = client.post(
        "/rfp/reviewer-signoff-ledger",
        headers=auth_headers,
        json={
            "collaboration": board,
            "workflow": workflow,
            "signoff_overrides": [
                {
                    "reviewer_role": "sales",
                    "approval_status": "approved",
                    "signed_by": "Ava Sales Lead",
                    "evidence_note": "Sales reviewed the local submission context.",
                }
            ],
        },
    )

    assert response.status_code == 200
    ledger = response.json()
    assert ledger["title"] == "Reviewer Signoff Ledger"
    assert ledger["ledger_status"] in {"blocked", "conditional", "pending_review", "ready_for_submission"}
    assert ledger["records"]
    assert ledger["summary"]["record_count"] == len(ledger["records"])
    assert ledger["summary"]["source_board_status"] == board["board_status"]
    assert ledger["workflow_snapshot"]["workflow_status"] == workflow["workflow_status"]
    assert ledger["governance_gates"]
    assert ledger["transition_log"]
    assert "human-in-the-loop signoff" in ledger["summary"]["patterns"]
    assert any("reviewer-signoff-pack" in command for command in ledger["local_proof_commands"])

    pack_response = client.post(
        "/rfp/reviewer-signoff-pack",
        headers=auth_headers,
        json={"collaboration": board, "workflow": workflow, "ledger": ledger, "write_artifact": True},
    )
    assert pack_response.status_code == 200
    pack = pack_response.json()
    artifact_path = Path(pack["artifact_path"])
    json_artifact_path = Path(pack["json_artifact_path"])
    assert artifact_path.exists()
    assert json_artifact_path.exists()
    assert "reviewer_signoffs" in str(artifact_path)
    assert "Reviewer Signoff Ledger Pack" in pack["markdown"]
    assert "## Signoff Records" in pack["markdown"]
    assert "## Governance Gates" in pack["markdown"]
    assert pack["pack"]["ledger"]["summary"]["record_count"] == len(ledger["records"])


def test_reviewer_signoff_is_registered_for_local_review_surfaces(client, auth_headers):
    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"] for row in smoke["rows"]}
    assert "/rfp/reviewer-signoff-ledger" in paths
    assert "/rfp/reviewer-signoff-pack" in paths
    assert any(
        "storage/reviewer_signoffs" in expectation
        for row in smoke["rows"]
        for expectation in row["required_artifact_expectations"]
    )

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "reviewer_signoffs" in {item["key"] for item in inventory["directories"]}

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard_smoke["status"] == "pass"
    assert any(
        endpoint["path"] == "/rfp/reviewer-signoff-pack"
        for endpoint in dashboard_smoke["endpoint_references"]
    )
