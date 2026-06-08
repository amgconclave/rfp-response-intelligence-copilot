from fastapi import FastAPI

from app.api.routes import router
from app.core.telemetry import TraceIdMiddleware, configure_logging


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="RFP Response Intelligence Copilot",
        version="0.1.0",
        description="Enterprise-style local-first RFP response copilot with RAG, citations, evals, and auditability.",
    )
    app.add_middleware(TraceIdMiddleware)
    app.include_router(router)
    return app


app = create_app()
