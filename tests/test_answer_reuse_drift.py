from pathlib import Path

from tests.conftest import ingest_corpus


def test_answer_reuse_drift_monitor_emits_checkpointed_findings(client, auth_headers):
    ingest_corpus(client, auth_headers)

    response = client.post(
        "/rfp/answer-reuse-drift",
        headers=auth_headers,
        json={"customer_profile_id": "regulated_healthcare", "min_source_overlap": 4},
    )

    assert response.status_code == 200
    drift = response.json()
    assert drift["title"] == "Answer Reuse Drift Monitor"
    assert drift["summary"]["snippet_count"] >= 4
    assert drift["workflow"]["pattern"] == "state_machine_workflow"
    assert drift["workflow"]["checkpointing"]
    assert drift["endpoint_references"]
    assert any("/rfp/answer-reuse-drift-pack" in command for command in drift["local_proof_commands"])

    first = drift["findings"][0]
    assert first["drift_status"] in {"stable", "watch", "owner_review", "retire_or_rewrite"}
    assert first["transition_trace"]
    assert first["transition_trace"][-1]["checkpoint_key"].startswith("answer-reuse-drift:")
    assert first["workflow_state"] == "reuse_gate"
    assert "source_text_present" in first["evidence"]


def test_answer_reuse_drift_pack_writes_artifacts(client, auth_headers):
    response = client.post(
        "/rfp/answer-reuse-drift-pack",
        headers=auth_headers,
        json={"category": "security", "write_artifact": True},
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "answer_reuse_drift" in pack["artifact_path"]
    assert "Answer Reuse Drift Pack" in pack["markdown"]
    assert "Drift Findings" in pack["markdown"]
    assert pack["pack"]["governance_controls"]
    assert pack["drift_report"]["summary"]["snippet_count"] >= 3


def test_answer_reuse_drift_dashboard_contract_and_inventory_wiring(client, auth_headers):
    pack_response = client.post(
        "/rfp/answer-reuse-drift-pack",
        headers=auth_headers,
        json={"write_artifact": True},
    )
    assert pack_response.status_code == 200

    smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    drift_view = next(view for view in smoke["expected_views"] if view["label"] == "Answer Reuse Drift")
    assert drift_view["status"] == "pass"
    assert drift_view["artifact_root"] == "answer_reuse_drift"
    endpoint_paths = {endpoint["path"]: endpoint for endpoint in smoke["endpoint_references"]}
    assert endpoint_paths["/rfp/answer-reuse-drift"]["status"] == "pass"
    assert endpoint_paths["/rfp/answer-reuse-drift-pack"]["status"] == "pass"

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    directories = {item["key"]: item for item in inventory["directories"]}
    assert "answer_reuse_drift" in directories
    assert directories["answer_reuse_drift"]["producer_endpoint"] == "POST /rfp/answer-reuse-drift-pack"

    launch = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    launch_paths = {row["path"]: row for row in launch["rows"]}
    assert "storage/answer_reuse_drift/*.md" in launch_paths["/rfp/answer-reuse-drift-pack"][
        "required_artifact_expectations"
    ]

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    rfp_paths = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["rfp_workflow"]}
    assert {"/rfp/answer-reuse-drift", "/rfp/answer-reuse-drift-pack"} <= rfp_paths
    assert "/rfp/answer-reuse-drift-pack" not in contract["generated_artifact_endpoint_coverage"]["missing_paths"]
