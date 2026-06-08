import json

from app.core.config import Settings
from app.models.domain import AuditEvent
from app.repositories.memory import InMemoryRepository


class AuditService:
    def __init__(self, repo: InMemoryRepository, settings: Settings) -> None:
        self.repo = repo
        self.settings = settings

    def record(
        self,
        trace_id: str,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        actor: str = "demo-user",
        metadata: dict | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            trace_id=trace_id,
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata or {},
        )
        self.repo.audit_events.append(event)
        self.settings.storage_dir.mkdir(parents=True, exist_ok=True)
        with self.settings.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")
        return event

    def list_events(self, limit: int = 100) -> list[AuditEvent]:
        if self.repo.audit_events:
            return self.repo.audit_events[-limit:]
        if not self.settings.audit_path.exists():
            return []
        events: list[AuditEvent] = []
        for line in self.settings.audit_path.read_text(encoding="utf-8").splitlines()[-limit:]:
            events.append(AuditEvent.model_validate(json.loads(line)))
        return events
