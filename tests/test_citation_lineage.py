from pathlib import Path

import pytest

from app.core.config import get_settings
from app.models.domain import Answer, Citation
from app.repositories.memory import repository
from app.services.container import get_container
from tests.conftest import ingest_corpus


@pytest.mark.asyncio
async def test_citation_lineage_service_verifies_and_flags_missing_references(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    get_container.cache_clear()
    repository.reset()
    container = get_container()
    await container.ingestion.ingest_path("sample_data/security_policy.md", document_type="security", source="test")

    answer = await container.generation.answer_question(
        "What SSO and encryption controls are supported?",
        "lineage-service-answer",
        top_k=4,
    )
    valid_report = container.citation_lineage.audit("lineage-service-valid", answers=[answer])

    assert valid_report.title == "Citation Lineage + Integrity Audit"
    assert valid_report.summary["citation_count"] >= 1
    assert valid_report.summary["verified_count"] >= 1
    assert valid_report.summary["missing_reference_count"] == 0
    assert valid_report.status == "pass"

    bad_citation = Citation(
        document_id="doc_missing",
        chunk_id="chk_missing",
        filename="security_policy.md",
        snippet="This stale citation is not present in the repository.",
        score=0.91,
    )
    bad_answer = Answer(
        question="Can we guarantee FedRAMP High?",
        answer_text="We guarantee FedRAMP High and zero data loss for every customer.",
        citations=[bad_citation],
        confidence=0.9,
        trace_id="lineage-bad-answer",
    )
    bad_report = container.citation_lineage.audit("lineage-service-bad", answers=[bad_answer])

    assert bad_report.status == "needs_review"
    assert bad_report.summary["missing_reference_count"] == 1
    assert bad_report.summary["generated_claim_flag_count"] >= 2
    assert bad_report.owner_followups
    repository.reset()
    get_settings.cache_clear()
    get_container.cache_clear()


def test_citation_lineage_endpoints_write_pack_and_artifacts(client, auth_headers):
    ingest_corpus(client, auth_headers)

    response = client.get("/evidence/citation-lineage", headers=auth_headers)
    assert response.status_code == 200
    lineage = response.json()
    assert lineage["summary"]["citation_count"] >= 1
    assert lineage["summary"]["verified_count"] >= 1
    assert lineage["summary"]["blocking_issue_count"] == 0
    assert lineage["endpoint_references"]

    pack_response = client.post("/evidence/citation-lineage-pack", headers=auth_headers, json={"write_artifact": True})
    assert pack_response.status_code == 200
    pack = pack_response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "citation_lineage" in pack["artifact_path"]
    assert "Citation Lineage + Integrity Pack" in pack["markdown"]
    assert pack["pack"]["summary"]["citation_count"] >= 1
    assert pack["lineage"]["summary"]["verified_count"] >= 1


def test_citation_lineage_dashboard_smoke_contract_and_inventory_wiring(client, auth_headers):
    ingest_corpus(client, auth_headers)

    smoke_response = client.get("/ui/dashboard-smoke", headers=auth_headers)
    assert smoke_response.status_code == 200
    smoke = smoke_response.json()
    lineage_view = next(view for view in smoke["expected_views"] if view["label"] == "Citation Lineage")
    assert lineage_view["status"] == "pass"
    assert lineage_view["artifact_root"] == "citation_lineage"
    endpoint_paths = {endpoint["path"]: endpoint for endpoint in smoke["endpoint_references"]}
    assert endpoint_paths["/evidence/citation-lineage"]["status"] == "pass"
    assert endpoint_paths["/evidence/citation-lineage-pack"]["status"] == "pass"

    launch_response = client.get("/ops/smoke-matrix", headers=auth_headers)
    assert launch_response.status_code == 200
    launch = launch_response.json()
    paths = {row["path"]: row for row in launch["rows"]}
    assert "/evidence/citation-lineage" in paths
    assert "storage/citation_lineage/*.md" in paths["/evidence/citation-lineage-pack"][
        "required_artifact_expectations"
    ]

    inventory_response = client.get("/artifacts/inventory", headers=auth_headers)
    assert inventory_response.status_code == 200
    inventory = inventory_response.json()
    directories = {Path(item["directory"]).name: item for item in inventory["directories"]}
    assert "citation_lineage" in directories
    assert directories["citation_lineage"]["producer_endpoint"] == "POST /evidence/citation-lineage-pack"

    contract_response = client.get("/api/contract-audit", headers=auth_headers)
    assert contract_response.status_code == 200
    contract = contract_response.json()
    evidence_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["evidence"]}
    assert {"/evidence/citation-lineage", "/evidence/citation-lineage-pack"} <= evidence_endpoints
    assert "/evidence/citation-lineage-pack" not in contract["generated_artifact_endpoint_coverage"][
        "missing_paths"
    ]
