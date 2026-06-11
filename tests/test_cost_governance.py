from pathlib import Path


def test_cost_governance_reports_provider_budget_and_workflows(client, auth_headers):
    response = client.get("/ops/cost-governance", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Cost and Provider Governance"
    assert payload["governance_status"] == "ready"
    assert payload["provider_readiness"]["provider_mode"] == "mock"
    assert payload["provider_readiness"]["local_mock_ready"] is True
    assert payload["budget_summary"]["daily_budget_usd"] == 25.0
    assert payload["budget_summary"]["daily_estimated_cost"] == 0.0
    assert {item["workflow_name"] for item in payload["workflow_estimates"]} >= {
        "cited_rfp_questions",
        "draft_sections",
        "standard_eval_questions",
        "red_team_questions",
        "artifact_pack_generation",
    }
    assert any(command.startswith("python -m app.demo") for command in payload["local_proof_commands"])


def test_cost_governance_custom_assumptions_and_pack_artifacts(client, auth_headers):
    custom_payload = {
        "daily_rfp_count": 2,
        "questions_per_rfp": 6,
        "draft_sections_per_rfp": 4,
        "eval_runs_per_day": 1,
        "red_team_runs_per_day": 0,
        "daily_budget_usd": 10.0,
    }
    report_response = client.post("/ops/cost-governance", headers=auth_headers, json=custom_payload)
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["budget_summary"]["daily_budget_usd"] == 10.0
    query_estimate = next(
        item for item in report["workflow_estimates"] if item["workflow_name"] == "cited_rfp_questions"
    )
    assert query_estimate["request_count"] == 12

    pack_response = client.post(
        "/ops/cost-governance-pack",
        headers=auth_headers,
        json={**custom_payload, "governance": report, "write_artifact": True},
    )
    assert pack_response.status_code == 200
    pack = pack_response.json()
    artifact_path = Path(pack["artifact_path"])
    json_artifact_path = Path(pack["json_artifact_path"])
    assert artifact_path.exists()
    assert json_artifact_path.exists()
    assert "cost_governance" in str(artifact_path)
    assert "Cost Governance Pack" in pack["markdown"]
    assert pack["governance"]["budget_summary"]["daily_budget_usd"] == 10.0
    assert pack["pack"]["artifact_paths"]["cost_governance_markdown"] == str(artifact_path.resolve())


def test_cost_governance_is_in_smoke_dashboard_and_inventory(client, auth_headers):
    client.post("/ops/cost-governance-pack", headers=auth_headers, json={"write_artifact": True})

    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    smoke_paths = {row["path"] for row in smoke["rows"]}
    assert {"/ops/cost-governance", "/ops/cost-governance-pack"} <= smoke_paths
    assert any(
        "storage/cost_governance" in expectation
        for row in smoke["rows"]
        for expectation in row["required_artifact_expectations"]
    )

    dashboard = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard["status"] == "pass"
    assert any(view["label"] == "Cost Governance" for view in dashboard["expected_views"])
    assert any(endpoint["path"] == "/ops/cost-governance-pack" for endpoint in dashboard["endpoint_references"])

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    cost_item = next(item for item in inventory["directories"] if item["key"] == "cost_governance")
    assert cost_item["file_count"] >= 2
    assert cost_item["producer_endpoint"] == "POST /ops/cost-governance-pack"
