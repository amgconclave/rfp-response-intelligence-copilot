from pathlib import Path

import pytest

from app.core.config import get_settings
from app.models.api import ProcurementRiskDecisionOverride
from app.repositories.memory import repository
from app.services.container import get_container
from tests.conftest import ingest_corpus


@pytest.mark.asyncio
async def test_procurement_risk_decision_service_applies_owner_overrides(tmp_path, monkeypatch):
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
        ("sample_data/dpa_privacy_policy.md", "privacy"),
        ("sample_data/sla_support_policy.md", "support"),
        ("sample_data/customer_success_onboarding.md", "customer_success"),
        ("sample_data/customer_contract_terms.md", "contract"),
    ]:
        await container.ingestion.ingest_path(fixture_path, document_type=document_type, source="test")

    rfp_text = (container.settings.sample_data_dir / "acme_enterprise_rfp.md").read_text(encoding="utf-8")
    analysis = container.analysis.analyze(rfp_text, "risk-decision-analysis")
    matrix = container.workbench.create_requirement_matrix(analysis)
    review = container.review_board.review_package("risk-decision-review", requirement_matrix=matrix)
    contract_risk = container.contract_risk.analyze(
        (container.settings.sample_data_dir / "customer_contract_terms.md").read_text(encoding="utf-8"),
        "risk-decision-contract",
        customer_profile_id="regulated_healthcare",
    )
    procurement_risk = await container.procurement.question_risk(
        "risk-decision-procurement",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review.findings,
    )
    desk = await container.procurement_risk_desk.risk_desk(
        "risk-decision-desk",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review.findings,
        contract_risk=contract_risk,
        procurement_risk=procurement_risk,
    )

    ledger = container.procurement_risk_decisions.decision_ledger(
        "risk-decision-ledger",
        desk,
        [
            ProcurementRiskDecisionOverride(
                risk_id="prd_legal_terms",
                decision_status="exception_granted",
                decided_by="Legal Counsel",
                evidence_reference="customer_contract_terms.md",
                expires_at="2026-12-31",
            )
        ],
    )

    assert ledger.title == "Procurement Risk Decision Ledger"
    assert ledger.summary["decision_count"] == desk.summary["risk_count"]
    assert ledger.summary["override_count"] == 1
    assert set(ledger.durable_state["implemented_patterns"]) >= {
        "human_in_the_loop",
        "durable_workflows",
        "governance",
        "trace_analysis",
    }
    legal = next(decision for decision in ledger.decisions if decision.risk_id == "prd_legal_terms")
    assert legal.decision_status == "exception_granted"
    assert legal.decision_state == "approved"
    assert legal.approval_gate == "exception_control"
    assert legal.evidence_reference == "customer_contract_terms.md"
    assert ledger.release_gate["status"] in {
        "hold_submission",
        "owner_review_required",
        "conditional_release",
        "can_submit",
    }
    assert ledger.governance_gates
    assert {span["operation"] for span in ledger.trace_spans} >= {
        "owner_decision_ledger",
        "decision_release_gate",
    }

    pack = container.procurement_risk_decisions.decision_pack("risk-decision-pack", ledger, desk, write_artifact=True)
    assert pack.artifact_path
    assert pack.json_artifact_path
    assert Path(pack.artifact_path).exists()
    assert Path(pack.json_artifact_path).exists()
    assert "procurement_risk_decisions" in pack.artifact_path
    assert "## Release Gate" in pack.markdown
    assert "## Governance Gates" in pack.markdown
    assert pack.pack["decisions"]
    repository.reset()
    get_settings.cache_clear()
    get_container.cache_clear()


def test_procurement_risk_decision_endpoints_and_repo_wiring(client, auth_headers):
    ingest_corpus(client, auth_headers)

    response = client.get("/procurement/risk-decision-ledger", headers=auth_headers)
    assert response.status_code == 200
    ledger = response.json()
    assert ledger["summary"]["decision_count"] == 5
    assert ledger["durable_state"]["checkpoint_id"] == "procurement-risk-decisions.owner-ledger.v1"
    assert ledger["governance_gates"]
    assert ledger["trace_spans"]
    assert ledger["release_gate"]["status"] in {
        "hold_submission",
        "owner_review_required",
        "conditional_release",
        "can_submit",
    }

    pack_response = client.post(
        "/procurement/risk-decision-pack",
        headers=auth_headers,
        json={
            "write_artifact": True,
            "decision_overrides": [
                {
                    "risk_id": "prd_legal_terms",
                    "decision_status": "exception_granted",
                    "decided_by": "Legal Counsel",
                    "evidence_reference": "customer_contract_terms.md",
                }
            ],
        },
    )
    assert pack_response.status_code == 200
    pack = pack_response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "procurement_risk_decisions" in pack["artifact_path"]
    assert pack["ledger"]["summary"]["override_count"] == 1
    assert "Procurement Risk Decision Pack" in pack["markdown"]

    smoke_response = client.get("/ui/dashboard-smoke", headers=auth_headers)
    assert smoke_response.status_code == 200
    smoke = smoke_response.json()
    ledger_view = next(view for view in smoke["expected_views"] if view["label"] == "Risk Decision Ledger")
    assert ledger_view["status"] == "pass"
    assert ledger_view["artifact_root"] == "procurement_risk_decisions"
    endpoint_paths = {endpoint["path"]: endpoint for endpoint in smoke["endpoint_references"]}
    assert endpoint_paths["/procurement/risk-decision-ledger"]["status"] == "pass"
    assert endpoint_paths["/procurement/risk-decision-pack"]["status"] == "pass"

    launch_response = client.get("/ops/smoke-matrix", headers=auth_headers)
    assert launch_response.status_code == 200
    launch = launch_response.json()
    paths = {row["path"]: row for row in launch["rows"]}
    assert "/procurement/risk-decision-ledger" in paths
    assert "storage/procurement_risk_decisions/*.md" in paths["/procurement/risk-decision-pack"][
        "required_artifact_expectations"
    ]

    contract_response = client.get("/api/contract-audit", headers=auth_headers)
    assert contract_response.status_code == 200
    contract = contract_response.json()
    procurement_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["procurement"]}
    assert {"/procurement/risk-decision-ledger", "/procurement/risk-decision-pack"} <= procurement_endpoints
    assert "/procurement/risk-decision-pack" not in contract["generated_artifact_endpoint_coverage"][
        "missing_paths"
    ]
