# Product Overview - RFP Response Intelligence Copilot

The RFP Response Intelligence Copilot ingests enterprise documents, chunks source text, indexes embeddings, and retrieves ranked snippets for RFP questions. It supports PDFs, Markdown, and plain text fixtures in local mode.

Core capabilities include document Q&A, requirement extraction, response drafting, citation review, missing-evidence warnings, evaluation reporting, audit logs, and token/cost monitoring.

The API is built with FastAPI and Pydantic service models. The local runtime uses deterministic mock LLM behavior for demos, with optional OpenAI and Azure OpenAI providers behind the same provider interface.

The retrieval layer supports a Qdrant adapter for Docker Compose deployments and a local FAISS-style fallback for lightweight demos. Future adapters can connect Azure AI Search, Azure Document Intelligence, and Azure Translator.
