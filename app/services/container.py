from functools import lru_cache

from app.core.config import Settings, get_settings
from app.providers.factory import build_llm_provider
from app.repositories.memory import repository
from app.services.audit import AuditService
from app.services.draft_generation import DraftGenerationService
from app.services.evaluation import EvaluationService
from app.services.ingestion import DocumentIngestionService
from app.services.metrics import MetricsService
from app.services.retrieval import RetrievalService
from app.services.rfp_analysis import RfpAnalysisService
from app.vectorstores.factory import build_vector_store


class ServiceContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repo = repository
        self.vector_store = build_vector_store(settings)
        self.llm_provider = build_llm_provider(settings)
        self.audit = AuditService(self.repo, settings)
        self.metrics = MetricsService(self.repo, settings)
        self.ingestion = DocumentIngestionService(self.repo, self.vector_store, settings)
        self.retrieval = RetrievalService(self.repo, self.vector_store)
        self.analysis = RfpAnalysisService(self.repo)
        self.generation = DraftGenerationService(
            self.repo,
            self.retrieval,
            self.llm_provider,
            self.metrics,
        )
        self.evaluation = EvaluationService(self.retrieval, self.generation)


@lru_cache
def get_container() -> ServiceContainer:
    return ServiceContainer(get_settings())
