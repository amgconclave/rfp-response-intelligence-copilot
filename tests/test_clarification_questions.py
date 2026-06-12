from pathlib import Path

import pytest

from app.core.config import get_settings
from app.repositories.memory import repository
from app.services.container import get_container
from tests.conftest import ingest_corpus


@pytest.mark.asyncio
async def test_clarification_service_generates_hitl_questions_and_pack(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    get_container.cache_clear()
    repository.reset()
    container = get_container()
    for fixture_path, document_type in [
        ("sample_data/acme_enterprise_rfp.md", "rfp"),
        ("sample_data/security_policy.md", "security"),
        ("sample_data/compliance_policy.md", "compliance"),
        ("sample_data/pricing_notes.md", "pricing"),
        ("sample_data/implementation_guide.md", "implementation"),
        ("sample_data/customer_contract_terms.md", "contract"),
        ("sample_data/dpa_privacy_policy.md", "privacy"),
        ("sample_data/customer_success_onboarding.md", "customer_success"),
    ]:
        await container.ingestion.ingest_path(fixture_path, document_type=document_type, source="test")

    rfp_text = (container.settings.sample_data_dir / "acme_enterprise_rfp.md").read_text(encoding="utf-8")
    analysis = container.analysis.analyze(rfp_text, "clarification-analysis")
    matrix = container.workbench.create_requirement_matrix(analysis)
    review = container.review_board.review_package("clarification-review", requirement_matrix=matrix)
    action_plan, _ = container.action_plan.create_action_plan(
        "clarification-action-plan",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review.findings,
    )
    readiness = container.deal_readiness.create_scorecard(
        "clarification-readiness",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review.findings,
        action_plan=action_plan,
    )
    contract = container.contract_risk.analyze(
        (container.settings.sample_data_dir / "customer_contract_terms.md").read_text(encoding="utf-8"),
        "clarification-contract",
        customer_profile_id="regulated_healthcare",
    )
    gaps, _ = container.evidence_gap.create_gap_plan(
        "clarification-gaps",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review.findings,
        readiness_scorecard=readiness,
        contract_risk=contract,
        action_plan=action_plan,
    )

    result = await container.clarification_questions.create_questions(
        "clarification-service-test",
        analysis=analysis,
        requirement_matrix=matrix,
        evidence_gaps=gaps,
        review_findings=review.findings,
        readiness_scorecard=readiness,
        contract_risk=contract,
        top_k=4,
        max_questions=6,
    )

    assert result.title == "RFP Clarification Question Workflow"
    assert result.summary["question_count"] >= 3
    assert result.summary["approval_required_count"] >= 1
    assert result.workflow_summary["replay_status"] == "pass"
    assert result.trace_spans
    assert all(question.owner_role and question.reviewer_role for question in result.questions)
    assert all(len(question.workflow_trace) >= 4 for question in result.questions)
    assert all(assertion.passed for assertion in result.eval_assertions)
    assert any(endpoint["path"] == "/rfp/clarification-question-pack" for endpoint in result.endpoint_references)

    pack = container.clarification_questions.question_pack("clarification-pack", result, write_artifact=True)
    assert pack.artifact_path
    assert pack.json_artifact_path
    assert Path(pack.artifact_path).exists()
    assert Path(pack.json_artifact_path).exists()
    assert "clarification_questions" in pack.artifact_path
    assert "RFP Clarification Question Pack" in pack.markdown
    assert "## Workflow Trace" in pack.markdown
    assert pack.pack["reviewer_queue"]
    assert pack.pack["trace_spans"]
    repository.reset()
    get_settings.cache_clear()
    get_container.cache_clear()


def test_clarification_endpoints_dashboard_and_contract_wiring(client, auth_headers):
    ingest_corpus(client, auth_headers)

    response = client.post(
        "/rfp/clarification-questions",
        headers=auth_headers,
        json={"top_k": 4, "max_questions": 6},
    )
    assert response.status_code == 200
    questions = response.json()
    assert questions["summary"]["question_count"] >= 3
    assert questions["summary"]["approval_required_count"] >= 1
    assert questions["workflow_summary"]["replay_status"] == "pass"
    assert questions["trace_spans"]
    assert all(item["workflow_trace"] for item in questions["questions"])
    assert all(assertion["passed"] for assertion in questions["eval_assertions"])

    pack_response = client.post(
        "/rfp/clarification-question-pack",
        headers=auth_headers,
        json={"clarification_questions": questions, "write_artifact": True},
    )
    assert pack_response.status_code == 200
    pack = pack_response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "clarification_questions" in pack["artifact_path"]
    assert "## Eval Assertions" in pack["markdown"]

    smoke_response = client.get("/ui/dashboard-smoke", headers=auth_headers)
    assert smoke_response.status_code == 200
    smoke = smoke_response.json()
    clarification_view = next(view for view in smoke["expected_views"] if view["label"] == "Clarification Questions")
    assert clarification_view["status"] == "pass"
    assert clarification_view["artifact_root"] == "clarification_questions"
    endpoint_paths = {endpoint["path"]: endpoint for endpoint in smoke["endpoint_references"]}
    assert endpoint_paths["/rfp/clarification-questions"]["status"] == "pass"
    assert endpoint_paths["/rfp/clarification-question-pack"]["status"] == "pass"

    launch_response = client.get("/ops/smoke-matrix", headers=auth_headers)
    assert launch_response.status_code == 200
    rows = {row["path"]: row for row in launch_response.json()["rows"]}
    assert "/rfp/clarification-questions" in rows
    assert "storage/clarification_questions/*.md" in rows["/rfp/clarification-question-pack"][
        "required_artifact_expectations"
    ]

    contract_response = client.get("/api/contract-audit", headers=auth_headers)
    assert contract_response.status_code == 200
    contract = contract_response.json()
    paths = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["rfp_workflow"]}
    assert {"/rfp/clarification-questions", "/rfp/clarification-question-pack"} <= paths
    assert "/rfp/clarification-question-pack" not in contract["generated_artifact_endpoint_coverage"][
        "missing_paths"
    ]
