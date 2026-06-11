from pathlib import Path

from tests.conftest import ingest_corpus


def test_answer_reuse_approval_ledger_builds_hitl_records(client, auth_headers):
    ingest_corpus(client, auth_headers)

    response = client.post(
        "/rfp/answer-reuse-approval-ledger",
        headers=auth_headers,
        json={"customer_profile_id": "regulated_healthcare"},
    )

    assert response.status_code == 200
    ledger = response.json()
    assert ledger["title"] == "Answer Reuse Approval Ledger"
    assert ledger["summary"]["record_count"] >= 4
    assert ledger["summary"]["approved_count"] >= 1
    assert ledger["workflow"]["pattern"] == "durable_human_in_the_loop_governance"
    assert "human-in-the-loop" in ledger["governance_policy"]["patterns"]
    assert ledger["trace_spans"]
    assert any("/rfp/answer-reuse-approval-pack" in command for command in ledger["local_proof_commands"])

    first = ledger["records"][0]
    assert first["required_approvers"]
    assert first["checkpoint_key"].startswith("answer-reuse-approval:")
    assert first["transitions"][-1]["to_state"] == "reuse_decision_recorded"


def test_answer_reuse_approval_pack_writes_artifacts_and_preserves_overrides(client, auth_headers):
    ingest_corpus(client, auth_headers)

    response = client.post(
        "/rfp/answer-reuse-approval-pack",
        headers=auth_headers,
        json={
            "customer_profile_id": "regulated_healthcare",
            "approver_overrides": {"resp_sso_001": "approve"},
            "write_artifact": True,
        },
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "answer_reuse_approvals" in pack["artifact_path"]
    assert "Answer Reuse Approval Pack" in pack["markdown"]
    assert pack["pack"]["governance_controls"]
    override_record = next(
        record for record in pack["ledger"]["records"] if record["snippet_id"] == "resp_sso_001"
    )
    assert override_record["override_applied"] is True
    assert override_record["approval_decision"] == "approved_by_named_owner"


def test_answer_reuse_approval_dashboard_contract_and_inventory_wiring(client, auth_headers):
    pack_response = client.post(
        "/rfp/answer-reuse-approval-pack",
        headers=auth_headers,
        json={"write_artifact": True},
    )
    assert pack_response.status_code == 200

    smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    approval_view = next(view for view in smoke["expected_views"] if view["label"] == "Answer Reuse Approval Ledger")
    assert approval_view["status"] == "pass"
    assert approval_view["artifact_root"] == "answer_reuse_approvals"
    endpoint_paths = {endpoint["path"]: endpoint for endpoint in smoke["endpoint_references"]}
    assert endpoint_paths["/rfp/answer-reuse-approval-ledger"]["status"] == "pass"
    assert endpoint_paths["/rfp/answer-reuse-approval-pack"]["status"] == "pass"

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    directories = {item["key"]: item for item in inventory["directories"]}
    assert "answer_reuse_approvals" in directories
    assert directories["answer_reuse_approvals"]["producer_endpoint"] == "POST /rfp/answer-reuse-approval-pack"

    launch = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    launch_paths = {row["path"]: row for row in launch["rows"]}
    assert "storage/answer_reuse_approvals/*.md" in launch_paths["/rfp/answer-reuse-approval-pack"][
        "required_artifact_expectations"
    ]

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    rfp_paths = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["rfp_workflow"]}
    assert {"/rfp/answer-reuse-approval-ledger", "/rfp/answer-reuse-approval-pack"} <= rfp_paths
    assert "/rfp/answer-reuse-approval-pack" not in contract["generated_artifact_endpoint_coverage"][
        "missing_paths"
    ]
