from pathlib import Path

from app.core.config import get_settings
from app.services.deal_readiness import DealReadinessService


def test_readiness_score_eval_dataset_pack(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    service = DealReadinessService(get_settings())

    eval_pack = service.evaluate_score_dataset(
        trace_id="readiness-score-eval-test",
        dataset_path="sample_data/readiness_score_eval_dataset.json",
    )

    assert eval_pack.status == "pass"
    assert eval_pack.score == 100
    assert eval_pack.scenario_count == 3
    assert eval_pack.passed_count == 3
    assert eval_pack.failed_count == 0
    assert eval_pack.artifact_path
    assert eval_pack.json_artifact_path
    assert Path(eval_pack.artifact_path).exists()
    assert Path(eval_pack.json_artifact_path).exists()
    assert "readiness_score_evals" in eval_pack.artifact_path
    assert "eval_datasets" in eval_pack.governance_summary["patterns_implemented"]
    assert "experiment_comparison" in eval_pack.governance_summary["patterns_implemented"]
    assert eval_pack.experiment_comparison["failed_scenarios"] == []
    assert eval_pack.trace_analysis["trace_span_count"] == 3
    assert eval_pack.governance_summary["human_review_queue_scenarios"] >= 2
    assert all(scenario["actual"]["workflow_checkpoint_count"] >= 6 for scenario in eval_pack.scenarios)
    assert "## Experiment Comparison" in eval_pack.markdown
    assert "POST /rfp/readiness-score-eval" in eval_pack.markdown
    get_settings.cache_clear()


def test_readiness_score_eval_api_and_dashboard_smoke(client, auth_headers):
    response = client.post(
        "/rfp/readiness-score-eval",
        headers=auth_headers,
        json={
            "dataset_path": "sample_data/readiness_score_eval_dataset.json",
            "write_artifact": True,
        },
    )

    assert response.status_code == 200
    eval_pack = response.json()
    assert eval_pack["status"] == "pass"
    assert eval_pack["scenario_count"] == 3
    assert eval_pack["artifact_path"]
    assert Path(eval_pack["artifact_path"]).exists()
    assert eval_pack["governance_summary"]["release_gate"] == "pass"
    assert eval_pack["trace_analysis"]["largest_deductions"]

    smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    endpoint = next(item for item in smoke["endpoint_references"] if item["path"] == "/rfp/readiness-score-eval")
    assert endpoint["status"] == "pass"
    assert endpoint["dashboard_referenced"] is True
    assert endpoint["route_defined"] is True
