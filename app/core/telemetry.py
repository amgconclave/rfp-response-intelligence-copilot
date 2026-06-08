import logging
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("rfp_copilot")
_LOG_RECORD_FACTORY = logging.getLogRecordFactory()


def configure_logging() -> None:
    def record_factory(*args, **kwargs):
        record = _LOG_RECORD_FACTORY(*args, **kwargs)
        if not hasattr(record, "trace_id"):
            record.trace_id = "-"
        return record

    logging.setLogRecordFactory(record_factory)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s trace_id=%(trace_id)s %(message)s",
    )


class TraceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        trace_id = request.headers.get("X-Trace-Id", str(uuid4()))
        request.state.trace_id = trace_id
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        response.headers["X-Latency-Ms"] = str(round((time.perf_counter() - start) * 1000, 2))
        return response


def get_trace_id(request: Request | None = None) -> str:
    if request is not None and hasattr(request.state, "trace_id"):
        return request.state.trace_id
    return str(uuid4())
