from pathlib import Path

from tests.conftest import ingest_corpus


def test_win_loss_learning_endpoint_returns_patterns_and_recommendations(client, auth_headers):
    ingest_corpus(client, auth_headers)

    response = client.post(
        "/learning/win-loss",
        headers=auth_headers,
        json={"outcomes_fixture_path": "sample_data/rfp_outcomes.json", "top_k_patterns": 6},
    )

    assert response.status_code == 200
    learning = response.json()
    assert learning["title"] == "Win/Loss Learning Loop"
    assert learning["outcome_count"] == 4
    assert learning["win_rate"] == 0.5
    assert learning["pattern_summary"]["wins"] == 2
    assert learning["pattern_summary"]["losses"] == 2
    assert learning["winning_evidence_patterns"]
    assert learning["losing_risk_patterns"]
    assert any(item["type"] == "source_boost" for item in learning["retrieval_recommendations"])
    assert any(item["type"] == "red_team_missing_evidence_case" for item in learning["eval_recommendations"])
    assert any("Security" in item["section"] for item in learning["response_guidance_updates"])
    assert any("/learning/win-loss-pack" in command for command in learning["local_proof_commands"])
    assert learning["limitations"]

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "learning.win_loss_analyzed" for event in audit["events"])


def test_win_loss_strategy_pack_writes_artifacts_and_dashboard_smoke_tracks_it(client, auth_headers):
    response = client.post(
        "/learning/win-loss-pack",
        headers=auth_headers,
        json={"write_artifact": True},
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "win_loss_packs" in pack["artifact_path"]
    assert "Win/Loss Learning Strategy Pack" in pack["markdown"]
    assert pack["pack"]["executive_summary"]["outcome_count"] == 4
    assert pack["pack"]["retrieval_recommendations"]
    assert pack["pack"]["eval_recommendations"]
    assert pack["learning_response"]["winning_evidence_patterns"]

    smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert smoke["status"] == "pass"
    assert any(view["label"] == "Win/Loss Learning" for view in smoke["expected_views"])
    assert any(endpoint["path"] == "/learning/win-loss-pack" for endpoint in smoke["endpoint_references"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "learning.win_loss_pack_generated" for event in audit["events"])


def test_win_loss_eval_case_compiler_returns_candidate_datasets(client, auth_headers):
    response = client.post(
        "/learning/win-loss-eval-cases",
        headers=auth_headers,
        json={"outcomes_fixture_path": "sample_data/rfp_outcomes.json", "max_cases_per_type": 4},
    )

    assert response.status_code == 200
    plan = response.json()
    assert plan["title"] == "Win/Loss Eval Case Compiler"
    assert plan["status"] == "ready_for_review"
    assert plan["positive_eval_cases"]
    assert plan["red_team_cases"]
    assert plan["dataset_patch"]["patch_mode"] == "candidate_artifacts_only"
    assert plan["dataset_patch"]["candidate_eval_cases"] > 0
    assert plan["dataset_patch"]["candidate_red_team_cases"] > 0
    assert "typed_contracts" in plan["governance_summary"]["patterns_used"]
    assert "state_machine_workflow" in plan["governance_summary"]["patterns_used"]
    assert any(span["to_state"] == "route_owner_review" for span in plan["trace_spans"])
    assert plan["owner_review_queue"]
    assert any("/learning/win-loss-eval-case-pack" in command for command in plan["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "learning.win_loss_eval_cases_compiled" for event in audit["events"])


def test_win_loss_eval_case_pack_writes_artifacts_and_dashboard_smoke_tracks_it(client, auth_headers):
    response = client.post(
        "/learning/win-loss-eval-case-pack",
        headers=auth_headers,
        json={"write_artifact": True, "max_cases_per_type": 4},
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert pack["candidate_eval_dataset_path"]
    assert pack["candidate_red_team_dataset_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert Path(pack["candidate_eval_dataset_path"]).exists()
    assert Path(pack["candidate_red_team_dataset_path"]).exists()
    assert "win_loss_eval_cases" in pack["artifact_path"]
    assert "Win/Loss Eval Case Compiler Pack" in pack["markdown"]
    assert pack["pack"]["positive_eval_cases"]
    assert pack["pack"]["red_team_cases"]

    smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert smoke["status"] == "pass"
    assert any(endpoint["path"] == "/learning/win-loss-eval-cases" for endpoint in smoke["endpoint_references"])
    assert any(endpoint["path"] == "/learning/win-loss-eval-case-pack" for endpoint in smoke["endpoint_references"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "learning.win_loss_eval_case_pack_generated" for event in audit["events"])


def test_win_loss_policy_activation_returns_traceable_rules_and_checkpoints(client, auth_headers):
    ingest_corpus(client, auth_headers)

    response = client.post(
        "/learning/win-loss-policy",
        headers=auth_headers,
        json={"activation_mode": "shadow_eval"},
    )

    assert response.status_code == 200
    plan = response.json()
    assert plan["title"] == "Win/Loss Policy Activation Plan"
    assert plan["activation_mode"] == "shadow_eval"
    assert plan["recommended_policy_id"]
    assert plan["policy_rules"]
    assert any(rule["rule_type"] == "source_boost" for rule in plan["policy_rules"])
    assert any(rule["rule_type"] == "gap_guardrail" for rule in plan["policy_rules"])
    assert any(item["to_state"] == "rolled_back" for item in plan["state_transitions"])
    assert any(item["checkpoint_id"] == "cp-red-team-missing-evidence" for item in plan["checkpoints"])
    assert plan["owner_review_queue"]
    assert plan["rollback_plan"]["default_policy_id"] == "baseline"
    assert "state_machine_workflow" in plan["governance_summary"]["patterns_used"]
    assert "typed_contracts" in plan["governance_summary"]["patterns_used"]

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "learning.win_loss_policy_planned" for event in audit["events"])


def test_win_loss_policy_pack_writes_artifacts_and_dashboard_smoke_tracks_it(client, auth_headers):
    response = client.post(
        "/learning/win-loss-policy-pack",
        headers=auth_headers,
        json={"write_artifact": True},
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "win_loss_policy" in pack["artifact_path"]
    assert "Win/Loss Policy Activation Pack" in pack["markdown"]
    assert pack["activation_plan"]["policy_rules"]
    assert pack["pack"]["state_transitions"]
    assert pack["pack"]["rollback_plan"]["rollback_state"] == "rolled_back"

    smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert smoke["status"] == "pass"
    assert any(endpoint["path"] == "/learning/win-loss-policy" for endpoint in smoke["endpoint_references"])
    assert any(endpoint["path"] == "/learning/win-loss-policy-pack" for endpoint in smoke["endpoint_references"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "learning.win_loss_policy_pack_generated" for event in audit["events"])


def test_win_loss_replay_backtest_compares_learned_policy_and_routes_review(client, auth_headers):
    ingest_corpus(client, auth_headers)

    response = client.post(
        "/learning/win-loss-replay",
        headers=auth_headers,
        json={
            "outcomes_fixture_path": "sample_data/rfp_outcomes.json",
            "eval_dataset_path": "sample_data/eval_dataset.json",
            "red_team_dataset_path": "sample_data/red_team_questions.json",
            "activation_mode": "shadow_eval",
        },
    )

    assert response.status_code == 200
    replay = response.json()
    assert replay["title"] == "Win/Loss Replay Backtest"
    assert replay["replay_summary"]["eval_case_count"] == 12
    assert replay["replay_summary"]["red_team_case_count"] == 8
    assert "experiment_comparison" in replay["replay_summary"]["patterns_used"]
    assert "human_in_the_loop" in replay["replay_summary"]["patterns_used"]
    assert replay["policy_delta"]["recommended_policy_id"]
    assert replay["eval_case_results"]
    assert replay["red_team_case_results"]
    assert replay["trace_spans"]
    assert replay["governance_decision"]["status"] in {"ready_for_shadow_eval", "human_review_required"}
    assert any("/learning/win-loss-replay-pack" in command for command in replay["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "learning.win_loss_replay_backtested" for event in audit["events"])


def test_win_loss_replay_pack_writes_artifacts_and_dashboard_smoke_tracks_it(client, auth_headers):
    ingest_corpus(client, auth_headers)

    response = client.post(
        "/learning/win-loss-replay-pack",
        headers=auth_headers,
        json={"write_artifact": True},
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "win_loss_replay" in pack["artifact_path"]
    assert "Win/Loss Replay Backtest Pack" in pack["markdown"]
    assert pack["pack"]["policy_delta"]
    assert pack["replay"]["red_team_case_results"]

    smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert smoke["status"] == "pass"
    assert any(endpoint["path"] == "/learning/win-loss-replay" for endpoint in smoke["endpoint_references"])
    assert any(endpoint["path"] == "/learning/win-loss-replay-pack" for endpoint in smoke["endpoint_references"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "learning.win_loss_replay_pack_generated" for event in audit["events"])
