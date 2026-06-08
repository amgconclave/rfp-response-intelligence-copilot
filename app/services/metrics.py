import json
import time
from collections.abc import Callable
from typing import TypeVar

from app.core.config import Settings
from app.models.domain import TokenUsage, UsageMetric
from app.repositories.memory import InMemoryRepository

T = TypeVar("T")


class MetricsService:
    def __init__(self, repo: InMemoryRepository, settings: Settings) -> None:
        self.repo = repo
        self.settings = settings

    def estimate_cost(self, usage: TokenUsage) -> float:
        input_cost = usage.input_tokens / 1000 * self.settings.estimated_input_cost_per_1k
        output_cost = usage.output_tokens / 1000 * self.settings.estimated_output_cost_per_1k
        return round(input_cost + output_cost, 6)

    def record(
        self,
        trace_id: str,
        provider: str,
        model: str,
        usage: TokenUsage,
        latency_ms: float,
        endpoint: str | None = None,
        metadata: dict | None = None,
    ) -> UsageMetric:
        usage.estimated_cost = self.estimate_cost(usage)
        metric = UsageMetric(
            trace_id=trace_id,
            provider=provider,
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            latency_ms=round(latency_ms, 2),
            estimated_cost=usage.estimated_cost,
            endpoint=endpoint,
            metadata=metadata or {},
        )
        self.repo.metrics.append(metric)
        self.settings.storage_dir.mkdir(parents=True, exist_ok=True)
        with self.settings.metrics_path.open("a", encoding="utf-8") as handle:
            handle.write(metric.model_dump_json() + "\n")
        return metric

    async def timed(self, func: Callable[[], T]) -> tuple[T, float]:
        start = time.perf_counter()
        result = func()
        latency_ms = (time.perf_counter() - start) * 1000
        return result, latency_ms

    def list_metrics(self, limit: int = 100) -> list[UsageMetric]:
        if self.repo.metrics:
            return self.repo.metrics[-limit:]
        if not self.settings.metrics_path.exists():
            return []
        metrics: list[UsageMetric] = []
        for line in self.settings.metrics_path.read_text(encoding="utf-8").splitlines()[-limit:]:
            metrics.append(UsageMetric.model_validate(json.loads(line)))
        return metrics

    def totals(self) -> dict[str, float | int]:
        metrics = self.list_metrics()
        return {
            "request_count": len(metrics),
            "input_tokens": sum(metric.input_tokens for metric in metrics),
            "output_tokens": sum(metric.output_tokens for metric in metrics),
            "estimated_cost": round(sum(metric.estimated_cost for metric in metrics), 6),
            "average_latency_ms": round(
                sum(metric.latency_ms for metric in metrics) / len(metrics), 2
            )
            if metrics
            else 0.0,
        }
