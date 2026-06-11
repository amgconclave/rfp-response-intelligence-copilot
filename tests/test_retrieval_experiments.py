from pathlib import Path


def test_retrieval_experiments_compare_policies_and_recommend_guarded_policy(client, auth_headers):
    response = client.post(
        "/rag/retrieval-experiments",
        headers=auth_headers,
        json={"dataset_path": "sample_data/eval_dataset.json", "top_k": 4},
    )

    assert response.status_code == 200
    comparison = response.json()
    assert comparison["title"] == "Retrieval Experiment Comparison"
    assert comparison["recommended_policy_id"]
    assert comparison["summary"]["question_count"] == 12
    assert comparison["summary"]["policy_count"] >= 4
    assert "retrieval diagnostics" in comparison["summary"]["radar_patterns_used"]
    assert "experiment comparison" in comparison["summary"]["radar_patterns_used"]
    assert any(row["policy_id"] == "baseline" for row in comparison["policy_results"])
    assert any(row["policy_id"] == "balanced_governed" for row in comparison["policy_results"])
    assert any(row["guardrails_triggered"] for row in comparison["question_diagnostics"])
    assert comparison["trace_spans"]
    assert comparison["governance_decision"]["owner"] == "ai_engineering"
    assert any("/rag/retrieval-experiment-pack" in command for command in comparison["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "rag.retrieval_experiments_compared" for event in audit["events"])


def test_retrieval_experiment_pack_writes_artifacts_and_dashboard_smoke_tracks_it(client, auth_headers):
    response = client.post(
        "/rag/retrieval-experiment-pack",
        headers=auth_headers,
        json={"write_artifact": True},
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "retrieval_experiments" in pack["artifact_path"]
    assert "Retrieval Experiment Comparison Pack" in pack["markdown"]
    assert pack["pack"]["policy_results"]
    assert pack["comparison"]["policy_results"]

    smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert smoke["status"] == "pass"
    assert any(view["label"] == "Retrieval Experiments" for view in smoke["expected_views"])
    assert any(endpoint["path"] == "/rag/retrieval-experiment-pack" for endpoint in smoke["endpoint_references"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "rag.retrieval_experiment_pack_generated" for event in audit["events"])
