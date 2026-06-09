from pathlib import Path


def test_final_audit_returns_structured_readme_consistency_checks(client, auth_headers):
    response = client.get("/handoff/final-audit", headers=auth_headers)

    assert response.status_code == 200
    audit = response.json()
    assert audit["title"] == "README Consistency Final Audit"
    assert audit["status"] in {"pass", "needs_work"}
    assert 0 <= audit["score"] <= 100
    check_ids = {check["check_id"] for check in audit["checks"]}
    assert {
        "readme_endpoint_mentions",
        "docs_api_coverage",
        "architecture_evaluation_coverage",
        "demo_output_claims",
        "scripts_present",
        "dashboard_smoke_script_present",
        "generated_artifact_directory_docs",
        "rag_eval_red_team_local_mock_clarity",
        "azure_optional_notes",
        "final_endpoints_in_smoke_matrix",
        "final_handoff_artifact_inventory",
    }.issubset(check_ids)
    final_endpoints = audit["endpoint_inventory"]["final_handoff_endpoints"]
    assert any(endpoint["path"] == "/handoff/final-audit" for endpoint in final_endpoints)
    assert any(endpoint["path"] == "/handoff/final-pack" for endpoint in final_endpoints)
    assert "final_handoff" in audit["artifact_inventory"]["directory_keys"]
    assert any(command == "python scripts\\dashboard_smoke.py" for command in audit["local_verification_commands"])


def test_final_pack_writes_markdown_and_json_under_final_handoff(client, auth_headers):
    response = client.post("/handoff/final-pack", headers=auth_headers, json={"write_artifact": True})

    assert response.status_code == 200
    payload = response.json()
    artifact_path = Path(payload["artifact_path"])
    json_artifact_path = Path(payload["json_artifact_path"])
    assert artifact_path.exists()
    assert json_artifact_path.exists()
    assert "final_handoff" in str(artifact_path)
    assert "Final Handoff Pack" in payload["markdown"]
    assert "README Consistency" in payload["markdown"]
    assert payload["pack"]["final_audit"]["title"] == "README Consistency Final Audit"
    assert payload["pack"]["dashboard_smoke_summary"]["script_command"] == "python scripts\\dashboard_smoke.py"
    assert payload["pack"]["rag_eval_proof_summary"]["commands"]
    endpoint_name = payload["pack"]["endpoint_inventory_summary"]["final_handoff_endpoints"][0]["endpoint_name"]
    assert "README Consistency final audit" in endpoint_name
    assert payload["pack"]["artifact_paths"]["final_handoff_markdown"] == str(artifact_path.resolve())


def test_smoke_matrix_and_artifact_inventory_include_final_handoff(client, auth_headers):
    smoke_response = client.get("/ops/smoke-matrix", headers=auth_headers)
    inventory_response = client.get("/artifacts/inventory", headers=auth_headers)

    assert smoke_response.status_code == 200
    assert inventory_response.status_code == 200
    smoke_paths = {row["path"] for row in smoke_response.json()["rows"]}
    assert "/handoff/final-audit" in smoke_paths
    assert "/handoff/final-pack" in smoke_paths
    assert any(
        "storage/final_handoff" in expectation
        for row in smoke_response.json()["rows"]
        for expectation in row["required_artifact_expectations"]
    )
    inventory_keys = {item["key"] for item in inventory_response.json()["directories"]}
    assert "final_handoff" in inventory_keys
