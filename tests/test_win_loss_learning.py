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
