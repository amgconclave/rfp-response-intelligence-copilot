from pathlib import Path


def test_release_quality_gate_returns_publish_readiness(client, auth_headers):
    response = client.get("/release/quality-gate", headers=auth_headers)

    assert response.status_code == 200
    gate = response.json()
    assert gate["title"] == "Release Candidate Quality Gate"
    assert gate["status"] in {"ready", "ready_with_warnings", "needs_work", "blocked"}
    assert 0 <= gate["score"] <= 100
    assert gate["verification_checklist"]
    assert gate["coverage"]["api"]["release_endpoints"]["/release/quality-gate"] is True
    assert gate["coverage"]["api"]["release_endpoints"]["/release/publish-pack"] is True
    assert gate["coverage"]["docs"]["complete"] is True
    assert gate["coverage"]["tests"]["has_release_tests"] is True
    assert gate["artifact_coverage"]["release_pack_path"].endswith("release_packs")
    assert gate["artifact_coverage"]["ignored_by_git"] == "storage/"
    assert gate["publish_readiness"]["required_before_push"]
    assert any("mock" in note.lower() for note in gate["runtime_notes"])


def test_release_publish_pack_writes_markdown_and_json(client, auth_headers):
    response = client.post("/release/publish-pack", headers=auth_headers, json={"write_artifact": True})

    assert response.status_code == 200
    payload = response.json()
    artifact_path = Path(payload["artifact_path"])
    json_artifact_path = Path(payload["json_artifact_path"])
    assert artifact_path.exists()
    assert json_artifact_path.exists()
    assert "release_packs" in str(artifact_path)
    assert "Release Candidate GitHub Publish Pack" in payload["markdown"]
    assert "## Endpoint Inventory" in payload["markdown"]
    assert "## GitHub Repo Checklist" in payload["markdown"]
    assert "## Known Limitations" in payload["markdown"]
    assert payload["pack"]["release_summary"]["score"] == payload["quality_gate"]["score"]
    assert payload["pack"]["artifact_paths"]["publish_pack_markdown"] == str(artifact_path.resolve())
    assert any(endpoint["path"] == "/release/quality-gate" for endpoint in payload["pack"]["endpoint_inventory"])
    assert any(endpoint["path"] == "/release/publish-pack" for endpoint in payload["pack"]["endpoint_inventory"])


def test_smoke_matrix_includes_release_endpoints(client, auth_headers):
    response = client.get("/ops/smoke-matrix", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    paths = {row["path"] for row in payload["rows"]}
    assert "/release/quality-gate" in paths
    assert "/release/publish-pack" in paths
    assert "/ui/dashboard-smoke" in paths
    assert "/ui/verification-pack" in paths
    assert any(
        "storage/release_packs" in expectation
        for row in payload["rows"]
        for expectation in row["required_artifact_expectations"]
    )


def test_dashboard_smoke_and_ui_verification_pack(client, auth_headers):
    smoke_response = client.get("/ui/dashboard-smoke", headers=auth_headers)

    assert smoke_response.status_code == 200
    smoke = smoke_response.json()
    assert smoke["title"] == "Dashboard Smoke + UI Verification"
    assert smoke["status"] == "pass"
    assert smoke["summary"]["views_present"] == smoke["summary"]["view_count"]
    assert smoke["summary"]["routes_defined"] == smoke["summary"]["endpoint_count"]
    assert any(view["label"] == "UI Verification" for view in smoke["expected_views"])
    assert any(endpoint["path"] == "/ui/dashboard-smoke" for endpoint in smoke["endpoint_references"])
    assert any(endpoint["path"] == "/ui/verification-pack" for endpoint in smoke["endpoint_references"])
    assert any(tab["artifact_root"] == "storage/ui_verification" for tab in smoke["generated_artifact_tabs"])
    assert any("python scripts\\dashboard_smoke.py" in command for command in smoke["local_run_commands"])
    assert any("does not launch Streamlit" in limitation for limitation in smoke["limitations"])

    pack_response = client.post("/ui/verification-pack", headers=auth_headers, json={"write_artifact": True})
    assert pack_response.status_code == 200
    pack = pack_response.json()
    artifact_path = Path(pack["artifact_path"])
    json_artifact_path = Path(pack["json_artifact_path"])
    assert artifact_path.exists()
    assert json_artifact_path.exists()
    assert "ui_verification" in str(artifact_path)
    assert "UI Verification Pack" in pack["markdown"]
    assert "Dashboard Smoke" in pack["markdown"]
    assert pack["dashboard_smoke"]["status"] == "pass"
    assert pack["pack"]["streamlit_run_command"] == "python -m streamlit run dashboard/app.py"
    assert pack["pack"]["reviewer_checklist"]
    assert pack["pack"]["screenshot_placeholders"]
    assert pack["pack"]["troubleshooting"]
