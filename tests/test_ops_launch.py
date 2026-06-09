from pathlib import Path


def test_smoke_matrix_lists_core_and_enterprise_endpoints(client, auth_headers):
    response = client.get("/ops/smoke-matrix", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    paths = {row["path"] for row in payload["rows"]}
    assert "/health" in paths
    assert "/documents/ingest" in paths
    assert "/rfp/submission-regression" in paths
    assert "/rfp/executive-submission-memo" in paths
    assert "/ops/launch-checklist" in paths
    assert "/ops/ci-doctor" in paths
    assert "/ops/audit-pack" in paths
    assert "/api/contract-audit" in paths
    assert "/api/reviewer-collection" in paths
    assert "/rag/corpus-coverage" in paths
    assert "/rag/eval-coverage-pack" in paths
    assert "/portfolio/evidence-index" in paths
    assert "/portfolio/interview-pack" in paths
    assert payload["readiness_summary"]["local_mock_ready"] is True
    assert payload["readiness_summary"]["artifact_writing_endpoints"] >= 10
    assert "python -m app.demo" in payload["readiness_summary"]["required_local_commands"]
    assert any(
        "storage/launch_checklists" in expectation
        for row in payload["rows"]
        for expectation in row["required_artifact_expectations"]
    )
    assert any(
        "storage/portfolio_packs" in expectation
        for row in payload["rows"]
        for expectation in row["required_artifact_expectations"]
    )
    assert any(
        "storage/api_contracts" in expectation
        for row in payload["rows"]
        for expectation in row["required_artifact_expectations"]
    )
    assert any(
        "storage/rag_coverage" in expectation
        for row in payload["rows"]
        for expectation in row["required_artifact_expectations"]
    )


def test_launch_checklist_writes_markdown_and_json(client, auth_headers):
    response = client.post("/ops/launch-checklist", headers=auth_headers, json={"write_artifact": True})

    assert response.status_code == 200
    payload = response.json()
    artifact_path = Path(payload["artifact_path"])
    json_artifact_path = Path(payload["json_artifact_path"])
    assert artifact_path.exists()
    assert json_artifact_path.exists()
    assert "launch_checklists" in str(artifact_path)
    assert "## API Smoke Matrix" in payload["markdown"]
    assert "## Eval and Red-Team Commands" in payload["markdown"]
    assert "Five Interviewer Talking Points" in payload["markdown"]
    assert payload["checklist"]["demo_command"] == "python -m app.demo"
    assert len(payload["checklist"]["interviewer_talking_points"]) == 5
    assert "portfolio_packs" in payload["checklist"]["generated_artifact_paths"]
    assert payload["smoke_matrix"]["readiness_summary"]["total_endpoints"] == len(payload["smoke_matrix"]["rows"])


def test_ci_doctor_returns_structured_local_audit(client, auth_headers):
    response = client.get("/ops/ci-doctor", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    check_ids = {check["check_id"] for check in payload["checks"]}
    assert payload["title"] == "Local CI Doctor + Dependency/Secrets Audit"
    assert payload["score"] >= 80
    assert "pytest_command" in check_ids
    assert "ruff_command" in check_ids
    assert "eval_command" in check_ids
    assert "red_team_command" in check_ids
    assert "demo_command" in check_ids
    assert "github_actions" in check_ids
    assert "docker_compose" in check_ids
    assert "env_example" in check_ids
    assert "readme_sections" in check_ids
    assert "docs_presence" in check_ids
    assert "generated_artifact_ignores" in check_ids
    assert "dependency_files" in check_ids
    assert "local_mock_provider_notes" in check_ids
    assert "secret_scan" in check_ids
    assert payload["secret_scan"]["files_scanned"] > 0
    assert "pyproject.toml" in {
        item["path"] for item in payload["dependency_inventory"]["dependency_files"]
    }
    assert any("python -m pytest -q" == command for command in payload["local_verification_commands"])


def test_audit_pack_writes_markdown_and_json(client, auth_headers):
    response = client.post("/ops/audit-pack", headers=auth_headers, json={"write_artifact": True})

    assert response.status_code == 200
    payload = response.json()
    artifact_path = Path(payload["artifact_path"])
    json_artifact_path = Path(payload["json_artifact_path"])
    assert artifact_path.exists()
    assert json_artifact_path.exists()
    assert "audit_packs" in str(artifact_path)
    assert "## CI Doctor Summary" in payload["markdown"]
    assert "## Secret Scan Summary" in payload["markdown"]
    assert "recruiter_interviewer_explanation" in payload["pack"]
    assert payload["ci_doctor"]["summary"]["audit_pack_path"].endswith("audit_packs")


def test_api_contract_audit_and_reviewer_collection(client, auth_headers):
    audit_response = client.get("/api/contract-audit", headers=auth_headers)

    assert audit_response.status_code == 200
    audit = audit_response.json()
    assert audit["title"] == "API Contract Snapshot"
    assert audit["openapi_route_count"] >= 55
    assert audit["auth_protected_endpoint_count"] >= 50
    assert "/api/reviewer-collection" in {
        endpoint["path"]
        for endpoints in audit["endpoint_inventory"].values()
        for endpoint in endpoints
    }
    assert audit["docs_api_coverage"]["total"] >= 15
    assert audit["dashboard_smoke_alignment"]["status"] == "pass"
    assert audit["generated_artifact_endpoint_coverage"]["status"] == "pass"
    assert audit["rag_eval_red_team_endpoint_coverage"]["status"] == "pass"
    assert "OpenAPI" in audit["title"] or audit["openapi_route_count"] > 0

    collection_response = client.post(
        "/api/reviewer-collection",
        headers=auth_headers,
        json={"write_artifact": True},
    )
    assert collection_response.status_code == 200
    collection = collection_response.json()
    artifact_path = Path(collection["artifact_path"])
    json_artifact_path = Path(collection["json_artifact_path"])
    assert artifact_path.exists()
    assert json_artifact_path.exists()
    assert "api_contracts" in str(artifact_path)
    assert "Reviewer Collection Pack" in collection["markdown"]
    assert "OpenAPI routes" in collection["markdown"]
    assert "X-API-Key" in collection["markdown"]
    assert "/api/contract-audit" in collection["collection"]["endpoint_inventory_by_domain"]["contract"][0]["path"]
    assert collection["contract_audit"]["openapi_route_count"] == audit["openapi_route_count"]
