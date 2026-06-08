from app.vectorstores.qdrant_store import QdrantStore


class AzureAISearchStore(QdrantStore):
    mode = "azure_ai_search"
