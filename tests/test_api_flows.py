from pathlib import Path

from tests.conftest import ingest_corpus, ingest_sample


def test_health_and_auth(client, auth_headers):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["provider_mode"] == "mock"

    token = client.post("/auth/demo-token")
    assert token.status_code == 200
    assert token.json()["api_key"] == "test-key"

    unauthorized = client.get("/documents")
    assert unauthorized.status_code == 401

    authorized = client.get("/documents", headers=auth_headers)
    assert authorized.status_code == 200


def test_ingestion_and_document_listing(client, auth_headers):
    result = ingest_sample(client, auth_headers, "product_overview.md")
    assert result["document"]["filename"] == "product_overview.md"
    assert result["chunk_count"] >= 1

    documents = client.get("/documents", headers=auth_headers).json()
    assert len(documents) == 1
    assert documents[0]["document_type"] == "knowledge_base"


def test_rfp_analysis_extracts_business_fields(client, auth_headers):
    text = Path("sample_data/acme_enterprise_rfp.md").read_text(encoding="utf-8")
    response = client.post("/rfp/analyze", headers=auth_headers, json={"text": text})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["requirements"]) >= 8
    assert "July 18, 2026" in payload["deadlines"]
    assert payload["security_questions"]
    assert payload["compliance_asks"]
    assert payload["pricing_mentions"]


def test_query_returns_cited_answer_and_metrics(client, auth_headers):
    ingest_corpus(client, auth_headers)
    response = client.post(
        "/rfp/query",
        headers=auth_headers,
        json={"question": "What SSO and encryption controls are supported?", "top_k": 4},
    )
    assert response.status_code == 200
    answer = response.json()
    assert answer["citations"]
    assert answer["confidence"] >= 0.45
    assert not answer["missing_evidence"]
    assert any(citation["filename"] == "security_policy.md" for citation in answer["citations"])
    assert answer["trace_id"]

    usage = client.get("/metrics/usage", headers=auth_headers).json()
    assert usage["totals"]["request_count"] >= 1
    assert usage["totals"]["input_tokens"] > 0


def test_missing_evidence_is_flagged(client, auth_headers):
    ingest_corpus(client, auth_headers)
    response = client.post(
        "/rfp/query",
        headers=auth_headers,
        json={
            "question": "Does the product include quantum-resistant satellite telemetry controls?",
            "top_k": 4,
        },
    )
    assert response.status_code == 200
    answer = response.json()
    assert answer["citations"] == []
    assert answer["missing_evidence"]
    assert answer["confidence"] < 0.3


def test_draft_response_has_required_sections(client, auth_headers):
    ingest_corpus(client, auth_headers)
    analyze = client.post(
        "/rfp/analyze",
        headers=auth_headers,
        json={"fixture_path": "sample_data/acme_enterprise_rfp.md"},
    )
    assert analyze.status_code == 200

    response = client.post(
        "/rfp/draft-response",
        headers=auth_headers,
        json={
            "section_names": [
                "Executive Summary",
                "Technical Response",
                "Security Response",
                "Compliance Response",
            ],
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    draft = response.json()
    assert len(draft["sections"]) >= 4
    assert draft["citations"]
    assert draft["assumptions"]


def test_evaluation_and_audit_events(client, auth_headers):
    ingest_corpus(client, auth_headers)
    response = client.post(
        "/rfp/evaluate",
        headers=auth_headers,
        json={"dataset_path": "sample_data/eval_dataset.json", "top_k": 4},
    )
    assert response.status_code == 200
    metrics = response.json()
    assert metrics["question_count"] == 5
    assert metrics["citation_coverage"] >= 0.7
    assert metrics["missing_evidence_detection_count"] >= 1
    assert metrics["input_tokens"] > 0
    assert "estimated_cost" in metrics

    audit = client.get("/audit/events", headers=auth_headers).json()
    actions = {event["action"] for event in audit["events"]}
    assert "document.ingested" in actions
    assert "eval.completed" in actions
