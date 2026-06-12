from pathlib import Path

from tests.conftest import ingest_corpus


def _analysis(client, auth_headers):
    response = client.post(
        "/rfp/analyze",
        headers=auth_headers,
        json={"fixture_path": "sample_data/acme_enterprise_rfp.md"},
    )
    assert response.status_code == 200
    return response.json()


def test_answer_reuse_coverage_maps_requirements_to_governed_snippets(client, auth_headers):
    ingest_corpus(client, auth_headers)
    analysis = _analysis(client, auth_headers)

    response = client.post(
        "/rfp/answer-reuse-coverage",
        headers=auth_headers,
        json={
            "analyzed_payload": analysis,
            "customer_profile_id": "regulated_healthcare",
            "min_match_score": 2,
        },
    )

    assert response.status_code == 200
    coverage = response.json()
    assert coverage["title"] == "Answer Reuse Coverage Map"
    assert coverage["summary"]["requirement_count"] == len(analysis["requirements"])
    assert coverage["summary"]["reuse_ready_count"] >= 1
    assert coverage["summary"]["gap_count"] >= 0
    assert coverage["workflow"]["pattern"] == "state_machine_workflow"
    assert coverage["trace_spans"]
    assert any(row["matched_snippets"] for row in coverage["requirements"])
    assert all(row["transition_trace"][-1]["checkpoint_key"] for row in coverage["requirements"])
    assert any("/rfp/answer-reuse-coverage-pack" in command for command in coverage["local_proof_commands"])


def test_answer_reuse_coverage_pack_writes_markdown_and_json(client, auth_headers):
    ingest_corpus(client, auth_headers)
    analysis = _analysis(client, auth_headers)

    response = client.post(
        "/rfp/answer-reuse-coverage-pack",
        headers=auth_headers,
        json={
            "analyzed_payload": analysis,
            "customer_profile_id": "regulated_healthcare",
            "write_artifact": True,
        },
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "answer_reuse_coverage" in pack["artifact_path"]
    assert "Answer Reuse Coverage Pack" in pack["markdown"]
    assert pack["pack"]["governance_controls"]
    assert pack["coverage"]["summary"]["requirement_count"] == len(analysis["requirements"])


def test_answer_reuse_coverage_dashboard_inventory_and_contract_wiring(client, auth_headers):
    analysis = _analysis(client, auth_headers)
    response = client.post(
        "/rfp/answer-reuse-coverage-pack",
        headers=auth_headers,
        json={"analyzed_payload": analysis, "write_artifact": True},
    )
    assert response.status_code == 200

    smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    view = next(view for view in smoke["expected_views"] if view["label"] == "Answer Reuse Coverage")
    assert view["status"] == "pass"
    assert view["artifact_root"] == "answer_reuse_coverage"
    endpoints = {endpoint["path"]: endpoint for endpoint in smoke["endpoint_references"]}
    assert endpoints["/rfp/answer-reuse-coverage"]["status"] == "pass"
    assert endpoints["/rfp/answer-reuse-coverage-pack"]["status"] == "pass"

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    directories = {item["key"]: item for item in inventory["directories"]}
    assert directories["answer_reuse_coverage"]["producer_endpoint"] == "POST /rfp/answer-reuse-coverage-pack"

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    rfp_paths = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["rfp_workflow"]}
    assert {"/rfp/answer-reuse-coverage", "/rfp/answer-reuse-coverage-pack"} <= rfp_paths
    assert "/rfp/answer-reuse-coverage-pack" not in contract["generated_artifact_endpoint_coverage"][
        "missing_paths"
    ]
