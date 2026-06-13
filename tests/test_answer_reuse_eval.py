from pathlib import Path

from tests.conftest import ingest_corpus


def test_answer_reuse_eval_scores_cases_and_compares_policies(client, auth_headers):
    ingest_corpus(client, auth_headers)

    response = client.post(
        "/rfp/answer-reuse-eval",
        headers=auth_headers,
        json={
            "customer_profile_id": "regulated_healthcare",
            "min_source_overlap": 4,
            "policy_thresholds": [2, 4, 6],
        },
    )

    assert response.status_code == 200
    evaluation = response.json()
    assert evaluation["title"] == "Answer Reuse Evaluation Pack"
    assert evaluation["summary"]["case_count"] >= 4
    assert evaluation["summary"]["policy_count"] == 3
    assert evaluation["summary"]["recommended_threshold"] in {2, 4, 6}
    assert evaluation["eval_cases"]
    assert evaluation["experiment_comparison"]
    assert any(row["recommended"] for row in evaluation["experiment_comparison"])
    assert any(span["pattern"] == "eval_dataset" for span in evaluation["trace_spans"])
    assert any(span["pattern"] == "experiment_comparison" for span in evaluation["trace_spans"])
    assert any("/rfp/answer-reuse-eval-pack" in command for command in evaluation["local_proof_commands"])


def test_answer_reuse_eval_pack_writes_artifacts(client, auth_headers):
    ingest_corpus(client, auth_headers)

    response = client.post(
        "/rfp/answer-reuse-eval-pack",
        headers=auth_headers,
        json={"category": "security", "write_artifact": True},
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "answer_reuse_evals" in pack["artifact_path"]
    assert "Answer Reuse Evaluation Pack" in pack["markdown"]
    assert "Experiment Comparison" in pack["markdown"]
    assert pack["pack"]["governance_controls"]
    assert pack["evaluation"]["summary"]["case_count"] >= 3


def test_answer_reuse_eval_dashboard_contract_and_inventory_wiring(client, auth_headers):
    pack_response = client.post(
        "/rfp/answer-reuse-eval-pack",
        headers=auth_headers,
        json={"write_artifact": True},
    )
    assert pack_response.status_code == 200

    smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    eval_view = next(view for view in smoke["expected_views"] if view["label"] == "Answer Reuse Evaluation")
    assert eval_view["status"] == "pass"
    assert eval_view["artifact_root"] == "answer_reuse_evals"
    endpoint_paths = {endpoint["path"]: endpoint for endpoint in smoke["endpoint_references"]}
    assert endpoint_paths["/rfp/answer-reuse-eval"]["status"] == "pass"
    assert endpoint_paths["/rfp/answer-reuse-eval-pack"]["status"] == "pass"

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    directories = {item["key"]: item for item in inventory["directories"]}
    assert "answer_reuse_evals" in directories
    assert directories["answer_reuse_evals"]["producer_endpoint"] == "POST /rfp/answer-reuse-eval-pack"

    launch = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    launch_paths = {row["path"]: row for row in launch["rows"]}
    assert "storage/answer_reuse_evals/*.md" in launch_paths["/rfp/answer-reuse-eval-pack"][
        "required_artifact_expectations"
    ]

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    rfp_paths = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["rfp_workflow"]}
    assert {"/rfp/answer-reuse-eval", "/rfp/answer-reuse-eval-pack"} <= rfp_paths
    assert "/rfp/answer-reuse-eval-pack" not in contract["generated_artifact_endpoint_coverage"][
        "missing_paths"
    ]
