# API

Base URL: `http://127.0.0.1:8000`

Authenticated endpoints require `X-API-Key`. In local mode the default key is `local-demo-key`.

## Endpoints

### `POST /auth/demo-token`

Returns the local demo API key and header name.

### `GET /health`

Returns service status, provider mode, vector store mode, and version.

### `POST /documents/ingest`

Ingests a local fixture path.

```json
{
  "fixture_path": "sample_data/security_policy.md",
  "document_type": "knowledge_base",
  "source": "sample_data",
  "tags": ["security"]
}
```

### `GET /documents`

Lists processed documents.

### `POST /rfp/analyze`

Analyzes text, an ingested RFP document ID, or a fixture path.

```json
{
  "fixture_path": "sample_data/acme_enterprise_rfp.md"
}
```

### `POST /rfp/query`

Answers a question using cited source evidence.

```json
{
  "question": "What SSO and encryption controls are supported?",
  "top_k": 4
}
```

### `POST /rfp/draft-response`

Generates response sections grounded in retrieved citations.

```json
{
  "section_names": [
    "Executive Summary",
    "Technical Response",
    "Security Response",
    "Compliance Response"
  ],
  "top_k": 5
}
```

### `POST /rfp/evaluate`

Runs the eval dataset against the current corpus.

```json
{
  "dataset_path": "sample_data/eval_dataset.json",
  "top_k": 4
}
```

### `GET /metrics/usage`

Returns recent usage metrics and totals.

### `GET /audit/events`

Returns recent audit events.

## Error Handling

Unsupported questions return low confidence and a `missing_evidence` warning rather than inventing unsupported claims. Authentication failures return `401`.
