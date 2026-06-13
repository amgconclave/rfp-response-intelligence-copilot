from pathlib import Path

from app.core.config import get_settings
from app.models.api import (
    DealReadinessScorecardResponse,
    ProposalReadinessScorePackResponse,
)
from app.services.readiness_drift import ProposalReadinessDriftService


def _current_pack() -> ProposalReadinessScorePackResponse:
    scorecard = DealReadinessScorecardResponse(
        readiness_score=72,
        readiness_level="at_risk",
        blockers=["Missing SOC 2 bridge letter", "Security reviewer queue is blocked"],
        evidence_coverage=0.68,
        review_risk_count=2,
        owner_bottlenecks=[
            {
                "owner_role": "security",
                "open_items": 4,
                "blocked_items": 2,
                "high_priority_items": 3,
                "risk_items": 2,
            }
        ],
        score_trace=[
            {
                "component": "final_readiness_score",
                "category": "final",
                "impact": 0,
                "running_score": 72,
                "rationale": "Final readiness score.",
            }
        ],
        approval_workflow=[],
        human_review_queue=[
            {
                "queue_id": "security-review",
                "owner_role": "security",
                "priority": "high",
                "status": "open",
                "required_decision": "approve_exception",
                "reason": "Missing security evidence.",
            }
        ],
        governance_summary={"controls": ["human_in_the_loop_exception_gate"]},
        recommended_next_actions=["Close evidence gaps before submission."],
        trace_id="current-pack-scorecard",
    )
    pack_payload = {
        "readiness_scorecard": scorecard.model_dump(mode="json"),
        "executive_readiness_artifacts": {
            "executive_summary": {
                "readiness_score": 72,
                "readiness_level": "at_risk",
                "section_completeness_score": 74,
                "evidence_coverage": 0.68,
                "compliance_risk_level": "high",
                "reviewer_bottleneck_count": 1,
            }
        },
        "section_completeness": {"average_score": 74, "status": "needs_review"},
        "evidence_coverage": {"overall_coverage": 0.68, "uncovered_requirement_count": 3},
        "compliance_risk": {"risk_level": "high", "risk_score": 72},
        "reviewer_bottlenecks": [{"owner_role": "security", "escalation_required": True}],
        "human_review_queue": [{"queue_id": "security-review"}],
    }
    return ProposalReadinessScorePackResponse(
        title="Proposal Readiness Score Pack",
        status="blocked_by_compliance_risk",
        readiness_score=72,
        readiness_level="at_risk",
        markdown="# Pack\n",
        pack=pack_payload,
        readiness_scorecard=scorecard,
        generated_at="2026-06-13T00:00:00+00:00",
        trace_id="current-pack",
    )


def test_readiness_drift_service_pack_blocks_regression(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    service = ProposalReadinessDriftService(get_settings())

    drift = service.compare(
        "readiness-drift-test",
        _current_pack(),
        baseline_snapshot={
            "snapshot_id": "approved-baseline",
            "readiness_score": 92,
            "readiness_level": "ready",
            "section_completeness_score": 95,
            "evidence_coverage": 0.95,
            "compliance_risk_level": "low",
            "human_review_queue_count": 0,
            "blocker_count": 0,
        },
    )

    assert drift.status == "blocked"
    assert drift.current_state == "executive_exception_gate"
    assert drift.summary["critical_count"] >= 1
    assert "typed_contracts" in drift.summary["patterns_implemented"]
    assert "traceable_node_transitions" in drift.summary["patterns_implemented"]
    assert any(finding.signal == "compliance_risk" for finding in drift.drift_findings)
    assert all(finding.transition_trace for finding in drift.drift_findings)

    pack = service.pack("readiness-drift-pack-test", _current_pack(), drift=drift)
    assert pack.artifact_path
    assert pack.json_artifact_path
    assert Path(pack.artifact_path).exists()
    assert Path(pack.json_artifact_path).exists()
    assert "readiness_drift" in pack.artifact_path
    assert "## Drift Findings" in pack.markdown
    get_settings.cache_clear()


def test_readiness_drift_api_and_dashboard_smoke(client, auth_headers):
    response = client.post(
        "/rfp/proposal-readiness-drift-pack",
        headers=auth_headers,
        json={
            "baseline_snapshot": {
                "snapshot_id": "api-approved-baseline",
                "readiness_score": 100,
                "readiness_level": "ready",
                "section_completeness_score": 100,
                "evidence_coverage": 1.0,
                "compliance_risk_level": "low",
                "human_review_queue_count": 0,
                "blocker_count": 0,
            },
            "score_drop_warn": 1,
            "score_drop_block": 2,
            "write_artifact": True,
        },
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert pack["drift"]["summary"]["finding_count"] >= 1
    assert pack["drift"]["workflow"]["current_state"] in {
        "owner_review_queue",
        "executive_exception_gate",
    }
    assert "/rfp/proposal-readiness-drift-pack" in pack["drift"]["local_proof_commands"][0]

    smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    endpoint = next(
        item
        for item in smoke["endpoint_references"]
        if item["path"] == "/rfp/proposal-readiness-drift-pack"
    )
    assert endpoint["status"] == "pass"
    assert endpoint["dashboard_referenced"] is True
    assert endpoint["route_defined"] is True
