from pathlib import Path

import pytest

from app.core.config import get_settings
from app.models.api import ProcurementRiskDecisionOverride
from app.repositories.memory import repository
from app.services.container import get_container
from tests.conftest import ingest_corpus


@pytest.mark.asyncio
async def test_procurement_exception_monitor_replays_expiry_and_evidence_controls(tmp_path, monkeypatch):
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
    analysis = container.analysis.analyze(rfp_text, "exception-monitor-analysis")
    matrix = container.workbench.create_requirement_matrix(analysis)
    review = container.review_board.review_package("exception-monitor-review", requirement_matrix=matrix)
    contract_risk = container.contract_risk.analyze(
        (container.settings.sample_data_dir / "customer_contract_terms.md").read_text(encoding="utf-8"),
        "exception-monitor-contract",
        customer_profile_id="regulated_healthcare",
    )
    procurement_risk = await container.procurement.question_risk(
        "exception-monitor-procurement",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review.findings,
    )
    desk = await container.procurement_risk_desk.risk_desk(
        "exception-monitor-desk",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=review.findings,
        contract_risk=contract_risk,
        procurement_risk=procurement_risk,
    )
    ledger = container.procurement_risk_decisions.decision_ledger(
        "exception-monitor-ledger",
        desk,
        [
            ProcurementRiskDecisionOverride(
                risk_id="prd_legal_terms",
                decision_status="exception_granted",
                decided_by="Legal Counsel",
                evidence_reference="customer_contract_terms.md",
                expires_at="2026-06-01",
            ),
            ProcurementRiskDecisionOverride(
                risk_id="prd_pricing_commercial",
                decision_status="approved_with_conditions",
                decided_by="Sales Operations",
                evidence_reference="pricing_notes.md",
                expires_at="2026-06-30",
            ),
        ],
    )

    monitor = container.procurement_exception_monitor.monitor(
        "exception-monitor-test",
        ledger,
        reference_date="2026-06-13",
    )

    assert monitor.title == "Procurement Exception Monitor"
    assert monitor.monitor_status == "hold_submission"
    assert monitor.summary["exception_count"] == desk.summary["risk_count"]
    assert monitor.summary["expiring_or_expired_count"] >= 2
    assert monitor.summary["critical_count"] >= 1
    assert set(monitor.state_machine["implemented_patterns"]) >= {
        "typed_contracts",
        "structured_outputs",
        "state_machine_workflow",
        "checkpointing",
        "conditional_routing",
        "traceable_node_transitions",
    }
    expired = next(item for item in monitor.exceptions if item.risk_id == "prd_legal_terms")
    assert expired.expiry_status == "expired"
    assert expired.monitor_state == "expired_hold"
    assert expired.severity == "critical"
    assert expired.transition_log
    assert monitor.owner_queues
    assert any(gate["gate_id"] == "exception-expiry-control" for gate in monitor.governance_gates)
    assert {span["operation"] for span in monitor.trace_spans} >= {
        "decision_ledger_replay",
        "exception_release_control",
    }

    pack = container.procurement_exception_monitor.monitor_pack(
        "exception-monitor-pack",
        monitor,
        ledger,
        write_artifact=True,
    )
    assert pack.artifact_path
    assert pack.json_artifact_path
    assert Path(pack.artifact_path).exists()
    assert Path(pack.json_artifact_path).exists()
    assert "procurement_exception_monitor" in pack.artifact_path
    assert "## State Machine" in pack.markdown
    assert "## Governance Gates" in pack.markdown
    repository.reset()
    get_settings.cache_clear()
    get_container.cache_clear()


def test_procurement_exception_monitor_endpoints_and_repo_wiring(client, auth_headers):
    ingest_corpus(client, auth_headers)

    response = client.get("/procurement/exception-monitor", headers=auth_headers)
    assert response.status_code == 200
    monitor = response.json()
    assert monitor["summary"]["exception_count"] == 5
    assert monitor["state_machine"]["checkpoint_id"] == "procurement-exception-monitor.release-control.v1"
    assert monitor["owner_queues"]
    assert monitor["trace_spans"]

    replay_response = client.post(
        "/procurement/exception-monitor",
        headers=auth_headers,
        json={
            "reference_date": "2026-06-13",
            "decision_overrides": [
                {
                    "risk_id": "prd_legal_terms",
                    "decision_status": "exception_granted",
                    "decided_by": "Legal Counsel",
                    "evidence_reference": "customer_contract_terms.md",
                    "expires_at": "2026-06-01",
                }
            ],
        },
    )
    assert replay_response.status_code == 200
    replay = replay_response.json()
    assert replay["summary"]["expiring_or_expired_count"] >= 1
    assert any(item["monitor_state"] == "expired_hold" for item in replay["exceptions"])

    pack_response = client.post(
        "/procurement/exception-monitor-pack",
        headers=auth_headers,
        json={
            "write_artifact": True,
            "reference_date": "2026-06-13",
            "decision_overrides": [
                {
                    "risk_id": "prd_legal_terms",
                    "decision_status": "exception_granted",
                    "decided_by": "Legal Counsel",
                    "evidence_reference": "customer_contract_terms.md",
                    "expires_at": "2026-06-01",
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
    assert "procurement_exception_monitor" in pack["artifact_path"]
    assert "Procurement Exception Monitor Pack" in pack["markdown"]
    assert pack["monitor"]["summary"]["exception_count"] == 5

    smoke_response = client.get("/ui/dashboard-smoke", headers=auth_headers)
    assert smoke_response.status_code == 200
    smoke = smoke_response.json()
    monitor_view = next(view for view in smoke["expected_views"] if view["label"] == "Exception Monitor")
    assert monitor_view["status"] == "pass"
    assert monitor_view["artifact_root"] == "procurement_exception_monitor"
    endpoint_paths = {endpoint["path"]: endpoint for endpoint in smoke["endpoint_references"]}
    assert endpoint_paths["/procurement/exception-monitor"]["status"] == "pass"
    assert endpoint_paths["/procurement/exception-monitor-pack"]["status"] == "pass"

    launch_response = client.get("/ops/smoke-matrix", headers=auth_headers)
    assert launch_response.status_code == 200
    launch = launch_response.json()
    paths = {row["path"]: row for row in launch["rows"]}
    assert "/procurement/exception-monitor" in paths
    assert "storage/procurement_exception_monitor/*.md" in paths["/procurement/exception-monitor-pack"][
        "required_artifact_expectations"
    ]

    contract_response = client.get("/api/contract-audit", headers=auth_headers)
    assert contract_response.status_code == 200
    contract = contract_response.json()
    procurement_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["procurement"]}
    assert {"/procurement/exception-monitor", "/procurement/exception-monitor-pack"} <= procurement_endpoints
    assert "/procurement/exception-monitor-pack" not in contract["generated_artifact_endpoint_coverage"][
        "missing_paths"
    ]
