from pathlib import Path


def test_submission_exception_register_and_pack(client, auth_headers):
    register_response = client.post("/rfp/exception-register", headers=auth_headers, json={})

    assert register_response.status_code == 200
    register = register_response.json()
    assert register["title"] == "Submission Exception Register"
    assert register["register_status"] in {"blocked", "requires_approval", "conditional", "clear"}
    assert register["exceptions"]
    assert register["summary"]["exception_count"] == len(register["exceptions"])
    assert register["summary"]["requires_approval_count"] >= 1
    assert register["approval_queue"]
    assert any(item["path"] == "/rfp/exception-pack" for item in register["endpoint_references"])
    assert any("exception-pack" in command for command in register["local_proof_commands"])

    first = register["exceptions"][0]
    assert first["exception_id"].startswith("exc_")
    assert first["waiver_type"]
    assert first["approver_role"]
    assert first["expires_at"]
    assert first["required_evidence"]
    assert first["local_policy"]

    pack_response = client.post(
        "/rfp/exception-pack",
        headers=auth_headers,
        json={"exception_register": register, "write_artifact": True},
    )
    assert pack_response.status_code == 200
    pack = pack_response.json()
    artifact_path = Path(pack["artifact_path"])
    json_artifact_path = Path(pack["json_artifact_path"])
    assert artifact_path.exists()
    assert json_artifact_path.exists()
    assert "exception_registers" in str(artifact_path)
    assert "Submission Exception Register Pack" in pack["markdown"]
    assert "## Approval Queue" in pack["markdown"]
    assert pack["pack"]["summary"]["exception_count"] == register["summary"]["exception_count"]


def test_submission_exceptions_in_smoke_inventory_and_dashboard(client, auth_headers):
    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"] for row in smoke["rows"]}
    assert "/rfp/exception-register" in paths
    assert "/rfp/exception-pack" in paths
    assert any(
        "storage/exception_registers" in expectation
        for row in smoke["rows"]
        for expectation in row["required_artifact_expectations"]
    )

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "exception_registers" in {item["key"] for item in inventory["directories"]}

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard_smoke["status"] == "pass"
    assert any(view["label"] == "Submission Exceptions" for view in dashboard_smoke["expected_views"])
    assert any(endpoint["path"] == "/rfp/exception-pack" for endpoint in dashboard_smoke["endpoint_references"])
