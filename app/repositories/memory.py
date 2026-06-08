from app.models.domain import AuditEvent, Chunk, Document, RfpRequirement, UsageMetric


class InMemoryRepository:
    def __init__(self) -> None:
        self.documents: dict[str, Document] = {}
        self.chunks: dict[str, Chunk] = {}
        self.requirements: dict[str, RfpRequirement] = {}
        self.audit_events: list[AuditEvent] = []
        self.metrics: list[UsageMetric] = []

    def reset(self) -> None:
        self.documents.clear()
        self.chunks.clear()
        self.requirements.clear()
        self.audit_events.clear()
        self.metrics.clear()


repository = InMemoryRepository()
