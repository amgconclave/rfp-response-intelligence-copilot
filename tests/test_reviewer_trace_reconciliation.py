from pathlib import Path


def test_reviewer_trace_reconciliation_and_pack(client, auth_headers):
    response = client.post(
        "/rfp/reviewer-trace-reconciliation",
        headers=auth_headers,
        json={},
    )

    assert response.status_code == 200
    reconciliation = response.json()
    assert reconciliation["title"] == "Reviewer Trace Reconciliation"
    assert reconciliation["status"] in {"pass", "needs_review", "blocked"}
    assert reconciliation["reconciliation_score"] <= 100
    assert "trace analysis" in reconciliation["summary"]["patterns"]
    assert "governance" in reconciliation["summary"]["patterns"]
    assert reconciliation["source_state"]["collaboration"]["assignments"] >= 1
    assert len(reconciliation["trace_spans"]) >= 5
    assert any(gate["gate_id"] == "recon_gate_01_status_alignment" for gate in reconciliation["governance_gates"])
    assert any("reviewer-trace-reconciliation-pack" in command for command in reconciliation["local_proof_commands"])

    pack_response = client.post(
        "/rfp/reviewer-trace-reconciliation-pack",
        headers=auth_headers,
        json={"reconciliation": reconciliation, "write_artifact": True},
    )

    assert pack_response.status_code == 200
    pack = pack_response.json()
    artifact_path = Path(pack["artifact_path"])
    json_artifact_path = Path(pack["json_artifact_path"])
    assert artifact_path.exists()
    assert json_artifact_path.exists()
    assert "reviewer_reconciliation" in str(artifact_path)
    assert "Reviewer Trace Reconciliation Pack" in pack["markdown"]
    assert "## Governance Gates" in pack["markdown"]
    assert pack["reconciliation"]["summary"]["finding_count"] == reconciliation["summary"]["finding_count"]


def test_reviewer_trace_reconciliation_detects_inconsistent_ready_workflow(client, auth_headers):
    board = client.post("/rfp/reviewer-collaboration", headers=auth_headers, json={}).json()
    workflow = client.post("/rfp/reviewer-workflow", headers=auth_headers, json={"collaboration": board}).json()
    ledger = client.post(
        "/rfp/reviewer-signoff-ledger",
        headers=auth_headers,
        json={"collaboration": board, "workflow": workflow},
    ).json()
    escalation = client.post(
        "/rfp/reviewer-escalations",
        headers=auth_headers,
        json={"collaboration": board, "workflow": workflow, "ledger": ledger},
    ).json()

    inconsistent_workflow = dict(workflow)
    inconsistent_workflow["workflow_status"] = "ready_for_submission"
    inconsistent_ledger = dict(ledger)
    inconsistent_ledger["ledger_status"] = "blocked"
    inconsistent_ledger["summary"] = {**ledger["summary"], "blocked_count": 1}

    response = client.post(
        "/rfp/reviewer-trace-reconciliation",
        headers=auth_headers,
        json={
            "collaboration": board,
            "workflow": inconsistent_workflow,
            "ledger": inconsistent_ledger,
            "escalation": escalation,
        },
    )

    assert response.status_code == 200
    reconciliation = response.json()
    assert reconciliation["status"] == "blocked"
    assert any(
        finding["status"] == "workflow_ready_but_signoff_not_ready"
        for finding in reconciliation["findings"]
    )
    assert reconciliation["reviewer_followups"]


def test_reviewer_trace_reconciliation_in_smoke_dashboard_and_inventory(client, auth_headers):
    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"] for row in smoke["rows"]}
    assert "/rfp/reviewer-trace-reconciliation" in paths
    assert "/rfp/reviewer-trace-reconciliation-pack" in paths
    assert any(
        "storage/reviewer_reconciliation" in expectation
        for row in smoke["rows"]
        for expectation in row["required_artifact_expectations"]
    )

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "reviewer_reconciliation" in {item["key"] for item in inventory["directories"]}

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard_smoke["status"] == "pass"
    assert any(
        endpoint["path"] == "/rfp/reviewer-trace-reconciliation-pack"
        for endpoint in dashboard_smoke["endpoint_references"]
    )
