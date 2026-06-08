# Architecture

## Objective

The RFP Response Intelligence Copilot helps sales and presales teams produce grounded RFP/RFI answers from approved enterprise documents. It favors local reproducibility, citations, auditability, and measurable retrieval quality over broad CRM or landing-page scope.

## Runtime Components

- FastAPI app: exposes authenticated JSON endpoints for ingestion, analysis, question answering, drafting, evaluation, usage metrics, audit events, and health.
- Service layer: keeps business logic behind explicit async-friendly service boundaries.
- Provider layer: `BaseLLMProvider` defines answer and draft methods. `MockLLMProvider` is deterministic and free. OpenAI and Azure OpenAI adapters are optional.
- Vector layer: `BaseVectorStore` defines upsert and search. `QdrantStore` is the default adapter surface and currently delegates to a FAISS-style local fallback when a live Qdrant client is unavailable.
- Repository: in-memory state for local demo and tests, with audit and metrics persisted to JSONL files under `storage/`.
- Dashboard: Streamlit client that exercises the API workflows.

## Required Services

- `DocumentIngestionService`: parses PDF/TXT/Markdown, chunks content, indexes vectors, stores document metadata.
- `RetrievalService`: searches vector stores, applies relevance gates, returns citation objects with snippets and scores.
- `RfpAnalysisService`: extracts requirements, deadlines, compliance asks, security questions, pricing mentions, risks, and missing info.
- `DraftGenerationService`: answers questions and drafts response sections using retrieved evidence.
- `EvaluationService`: measures retrieval precision, citation coverage, missing-evidence detection, latency, tokens, and cost.
- `AuditService`: records approval-relevant events with trace IDs.
- `MetricsService`: records provider, model, token, latency, and cost metrics.

## Request Flow

1. A client sends `X-API-Key`.
2. `TraceIdMiddleware` creates or propagates `X-Trace-Id`.
3. The endpoint delegates to services through `ServiceContainer`.
4. Retrieval returns ranked citations from ingested chunks.
5. The selected LLM provider produces answer or draft text.
6. Metrics and audit events are written.
7. The response includes citations, confidence, missing evidence, and trace ID where relevant.

## Local-First Behavior

Fresh clones use mock generation and local vector fallback. Docker Compose includes Qdrant so the adapter boundary is ready for a production-grade vector service without making local tests dependent on infrastructure.
