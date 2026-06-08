from tests.conftest import ingest_samples


def test_ingestion_and_retrieval_query(client, auth_headers):
    ingest_samples(client, auth_headers)

    documents = client.get("/documents", headers=auth_headers)
    assert documents.status_code == 200
    assert len(documents.json()) == 6

    answer = client.post(
        "/rfp/query",
        headers=auth_headers,
        json={"question": "What SSO and encryption controls are supported?", "top_k": 4},
    )
    assert answer.status_code == 200
    payload = answer.json()
    assert payload["citations"]
    assert payload["confidence"] > 0.4
    assert "security_policy.md" in {citation["filename"] for citation in payload["citations"]}


def test_missing_evidence_is_flagged(client, auth_headers):
    ingest_samples(client, auth_headers)

    answer = client.post(
        "/rfp/query",
        headers=auth_headers,
        json={"question": "Does the product include quantum-resistant satellite telemetry controls?"},
    )
    assert answer.status_code == 200
    payload = answer.json()
    assert payload["citations"] == []
    assert payload["missing_evidence"]
    assert payload["confidence"] < 0.3


def test_analysis_draft_metrics_and_audit(client, auth_headers):
    ingest_samples(client, auth_headers)

    analysis = client.post(
        "/rfp/analyze",
        headers=auth_headers,
        json={"fixture_path": "sample_data/acme_enterprise_rfp.md"},
    )
    assert analysis.status_code == 200
    assert len(analysis.json()["requirements"]) >= 4

    draft = client.post(
        "/rfp/draft-response",
        headers=auth_headers,
        json={"top_k": 5},
    )
    assert draft.status_code == 200
    draft_payload = draft.json()
    assert len(draft_payload["sections"]) >= 4
    assert draft_payload["citations"]

    metrics = client.get("/metrics/usage", headers=auth_headers)
    assert metrics.status_code == 200
    assert metrics.json()["totals"]["request_count"] >= 1

    audit = client.get("/audit/events", headers=auth_headers)
    assert audit.status_code == 200
    actions = {event["action"] for event in audit.json()["events"]}
    assert "document.ingested" in actions
    assert "rfp.draft_generated" in actions


def test_eval_endpoint_passes_in_mock_mode(client, auth_headers):
    ingest_samples(client, auth_headers)

    response = client.post(
        "/rfp/evaluate",
        headers=auth_headers,
        json={"dataset_path": "sample_data/eval_dataset.json", "top_k": 4},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["passed"] is True
    assert payload["retrieval_precision_at_k"] >= 0.7
    assert payload["citation_coverage"] >= 0.8
    assert payload["missing_evidence_detection_count"] == 1
