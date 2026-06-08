from app.core.config import Settings
from app.vectorstores.base import BaseVectorStore
from app.vectorstores.faiss_store import FaissStore
from app.vectorstores.qdrant_store import QdrantStore


def build_vector_store(settings: Settings) -> BaseVectorStore:
    if settings.vector_store_mode == "qdrant":
        return QdrantStore(settings)
    if settings.vector_store_mode == "azure_ai_search":
        from app.vectorstores.azure_search_store import AzureAISearchStore

        return AzureAISearchStore(settings)
    return FaissStore(settings)
