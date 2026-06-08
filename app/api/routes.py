from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app import __version__
from app.core.config import Settings, get_settings
from app.core.security import require_api_key
from app.core.telemetry import get_trace_id
from app.models.api import (
    AnalyzeRequest,
    AnalyzeResponse,
    AuditResponse,
    DemoTokenResponse,
    DraftRequest,
    EvaluateRequest,
    EvaluationMetrics,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    QueryRequest,
    UsageResponse,
)
from app.models.domain import Answer, Document, DraftResponse
from app.services.container import ServiceContainer, get_container

router = APIRouter()


@router.post("/auth/demo-token", response_model=DemoTokenResponse)
async def demo_token(settings: Settings = Depends(get_settings)) -> DemoTokenResponse:
    return DemoTokenResponse(api_key=settings.api_key)


@router.get("/health", response_model=HealthResponse)
async def health(
    settings: Settings = Depends(get_settings),
    container: ServiceContainer = Depends(get_container),
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        provider_mode=settings.provider_mode,
        vector_store_mode=container.vector_store.mode,
        version=__version__,
    )


@router.post("/documents/ingest", response_model=IngestResponse, dependencies=[Depends(require_api_key)])
async def ingest_document(
    request: Request,
    payload: IngestRequest | None = None,
    container: ServiceContainer = Depends(get_container),
) -> IngestResponse:
    if payload is None or not payload.fixture_path:
        raise HTTPException(status_code=400, detail="Provide fixture_path or use /documents/ingest-upload.")
    trace_id = get_trace_id(request)
    document, chunks = await container.ingestion.ingest_path(
        payload.fixture_path,
        payload.document_type,
        payload.source,
        payload.tags,
    )
    container.audit.record(trace_id, "document.ingested", "document", document.id)
    return IngestResponse(document=document, chunk_count=len(chunks))


@router.post(
    "/documents/ingest-upload",
    response_model=IngestResponse,
    dependencies=[Depends(require_api_key)],
)
async def ingest_upload(
    request: Request,
    file: UploadFile = File(...),
    document_type: str = Form("unknown"),
    source: str = Form("upload"),
    tags: str = Form(""),
    container: ServiceContainer = Depends(get_container),
) -> IngestResponse:
    trace_id = get_trace_id(request)
    tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
    document, chunks = await container.ingestion.ingest_upload(file, document_type, source, tag_list)
    container.audit.record(trace_id, "document.ingested", "document", document.id)
    return IngestResponse(document=document, chunk_count=len(chunks))


@router.get("/documents", response_model=list[Document], dependencies=[Depends(require_api_key)])
async def list_documents(container: ServiceContainer = Depends(get_container)) -> list[Document]:
    return container.ingestion.list_documents()


@router.post("/rfp/analyze", response_model=AnalyzeResponse, dependencies=[Depends(require_api_key)])
async def analyze_rfp(
    payload: AnalyzeRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> AnalyzeResponse:
    trace_id = get_trace_id(request)
    if payload.text:
        text = payload.text
    elif payload.rfp_document_id:
        text = container.ingestion.get_text(payload.rfp_document_id)
    elif payload.fixture_path:
        path = Path(payload.fixture_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            sample_path = container.settings.sample_data_dir / payload.fixture_path
            if sample_path.exists():
                path = sample_path
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"RFP fixture not found: {payload.fixture_path}")
        text = path.read_text(encoding="utf-8")
    else:
        raise HTTPException(status_code=400, detail="Provide text, rfp_document_id, or fixture_path.")
    result = container.analysis.analyze(text, trace_id)
    container.audit.record(trace_id, "rfp.analyzed", "rfp", metadata={"requirements": len(result.requirements)})
    return result


@router.post("/rfp/query", response_model=Answer, dependencies=[Depends(require_api_key)])
async def query_rfp(
    payload: QueryRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> Answer:
    trace_id = get_trace_id(request)
    answer = await container.generation.answer_question(payload.question, trace_id, payload.top_k)
    container.audit.record(
        trace_id,
        "rfp.question_answered",
        "answer",
        metadata={"confidence": answer.confidence, "citations": len(answer.citations)},
    )
    return answer


@router.post(
    "/rfp/draft-response",
    response_model=DraftResponse,
    dependencies=[Depends(require_api_key)],
)
async def draft_response(
    payload: DraftRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> DraftResponse:
    trace_id = get_trace_id(request)
    draft = await container.generation.draft_response(
        trace_id,
        payload.requirement_ids,
        payload.section_names,
        payload.top_k,
    )
    container.audit.record(
        trace_id,
        "rfp.draft_generated",
        "draft",
        metadata={"sections": len(draft.sections), "citations": len(draft.citations)},
    )
    return draft


@router.post("/rfp/evaluate", response_model=EvaluationMetrics, dependencies=[Depends(require_api_key)])
async def evaluate(
    payload: EvaluateRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> EvaluationMetrics:
    trace_id = get_trace_id(request)
    result = await container.evaluation.run(payload.dataset_path, trace_id, payload.top_k)
    container.audit.record(trace_id, "eval.completed", "evaluation", metadata=result.model_dump())
    return result


@router.get("/metrics/usage", response_model=UsageResponse, dependencies=[Depends(require_api_key)])
async def usage(container: ServiceContainer = Depends(get_container)) -> UsageResponse:
    return UsageResponse(metrics=container.metrics.list_metrics(), totals=container.metrics.totals())


@router.get("/audit/events", response_model=AuditResponse, dependencies=[Depends(require_api_key)])
async def audit_events(container: ServiceContainer = Depends(get_container)) -> AuditResponse:
    return AuditResponse(events=container.audit.list_events())
