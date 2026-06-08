# Azure Deployment Notes

This repo is local-first, but the service boundaries are ready for Azure-oriented enterprise deployment.

## Recommended Azure Shape

- API: Azure Container Apps or Azure App Service running the FastAPI container.
- Vector search: Qdrant on managed container infrastructure, Azure AI Search adapter, or another vector database behind `BaseVectorStore`.
- LLM: Azure OpenAI through `AzureOpenAIProvider`.
- Secrets: Azure Key Vault injected as environment variables.
- Storage: Azure Blob Storage for uploaded documents and durable audit/metrics archives.
- Identity: Replace local API key auth with Azure API Management, Entra ID, OAuth, or gateway-issued API keys.
- Observability: Azure Monitor and Application Insights for traces, structured logs, latency, and error rates.

## Environment Variables

Set these when using Azure OpenAI:

```bash
PROVIDER_MODE=azure_openai
AZURE_OPENAI_ENDPOINT=https://example.openai.azure.com
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_DEPLOYMENT=...
```

## Production Hardening

- Store raw documents and chunks durably instead of in-memory.
- Add tenant scoping and RBAC to documents, audit events, and metrics.
- Enforce citation review and approval workflows for final RFP submissions.
- Add private networking for vector search and LLM endpoints.
- Add retention controls for regulated customer material.
- Export audit events to a compliance archive.

## Local Compatibility

No Azure dependency is required for local demos, tests, or CI. `PROVIDER_MODE=mock` remains the default path.
