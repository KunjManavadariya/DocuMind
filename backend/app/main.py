from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
import psycopg
from redis import Redis

from app.answer_evaluation import create_answer_quality_evaluator
from app.cache import create_cache, stable_cache_key
from app.config import get_settings
from app.db import clear_corpus, ensure_schema, list_documents, retrieve_similar_chunks
from app.document_loaders import fetch_url_document, load_uploaded_document
from app.embeddings import CachedEmbeddingProvider, create_embedding_provider
from app.evaluation import evaluate_configs
from app.generation import create_answer_generator
from app.ingestion import IngestionInput, ingest_document
from app.release import evaluate_release_readiness, is_deployable
from app.reranking import create_reranker
from app.schemas import (
    AnswerRequest,
    AnswerResponse,
    CorpusClearResponse,
    DocumentListResponse,
    DocumentSummary,
    EvalRunRequest,
    EvalRunResponse,
    IngestJobResponse,
    IngestJobStatusResponse,
    IngestTextRequest,
    IngestTextResponse,
    IngestUrlRequest,
    RetrieveRequest,
    RetrieveResponse,
    RetrievedChunk,
    ReleaseReadinessCheck,
    ReleaseReadinessResponse,
)
from app.worker import celery_app, ingest_text_task
from app.storage import create_document_storage

settings = get_settings()
cache = create_cache(settings)
embedding_provider = CachedEmbeddingProvider(
    provider=create_embedding_provider(settings),
    cache=cache,
    ttl_seconds=settings.embedding_cache_ttl_seconds,
)
answer_generator = create_answer_generator(settings)
answer_quality_evaluator = create_answer_quality_evaluator(settings)
document_storage = create_document_storage(settings)
reranker = create_reranker(settings)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "documind-api",
        "environment": settings.app_env,
    }


@app.get("/ready")
def ready() -> dict[str, str]:
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()

    redis_client = Redis.from_url(settings.redis_url)
    redis_client.ping()

    return {
        "status": "ready",
        "database": "ok",
        "redis": "ok",
    }


@app.get("/release/readiness", response_model=ReleaseReadinessResponse)
def release_readiness() -> ReleaseReadinessResponse:
    checks = evaluate_release_readiness(settings)
    return ReleaseReadinessResponse(
        deployable=is_deployable(checks),
        environment=settings.app_env,
        checks=[
            ReleaseReadinessCheck(
                name=check.name,
                status=check.status,
                message=check.message,
            )
            for check in checks
        ],
    )


@app.get("/documents", response_model=DocumentListResponse)
def get_documents() -> DocumentListResponse:
    ensure_schema(settings.database_url, embedding_dimension=embedding_provider.dimension)
    rows = list_documents(settings.database_url)

    return DocumentListResponse(
        documents=[
            DocumentSummary(
                id=str(row["id"]),
                title=row["title"],
                source_type=row["source_type"],
                source_uri=row["source_uri"],
                chunks_created=row["chunks_created"],
                created_at=row["created_at"].isoformat(),
            )
            for row in rows
        ]
    )


@app.delete("/documents", response_model=CorpusClearResponse)
def delete_documents() -> CorpusClearResponse:
    ensure_schema(settings.database_url, embedding_dimension=embedding_provider.dimension)
    result = clear_corpus(settings.database_url)
    cache.delete_prefix("answer:")
    return CorpusClearResponse(**result)


@app.post(
    "/documents/ingest-text",
    response_model=IngestTextResponse,
    status_code=status.HTTP_201_CREATED,
)
def ingest_text(payload: IngestTextRequest) -> IngestTextResponse:
    try:
        stored = ingest_document(
            settings.database_url,
            document=IngestionInput(
                title=payload.title,
                content=payload.content,
                source_type="text",
                source_uri=payload.source_uri,
                chunk_size=payload.chunk_size,
                chunk_overlap=payload.chunk_overlap,
            ),
            embedding_provider=embedding_provider,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    cache.delete_prefix("answer:")
    return IngestTextResponse(
        document_id=stored.id,
        chunks_created=stored.chunks_created,
    )


@app.post(
    "/documents/ingest-text-async",
    response_model=IngestJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def ingest_text_async(payload: IngestTextRequest) -> IngestJobResponse:
    task = ingest_text_task.delay(
        IngestionInput(
            title=payload.title,
            content=payload.content,
            source_type="text",
            source_uri=payload.source_uri,
            chunk_size=payload.chunk_size,
            chunk_overlap=payload.chunk_overlap,
        ).__dict__
    )
    return IngestJobResponse(task_id=task.id, status="queued")


@app.post(
    "/documents/ingest-url",
    response_model=IngestTextResponse,
    status_code=status.HTTP_201_CREATED,
)
def ingest_url(payload: IngestUrlRequest) -> IngestTextResponse:
    try:
        fetched = fetch_url_document(
            payload.url,
            timeout_seconds=settings.url_fetch_timeout_seconds,
            max_bytes=settings.url_fetch_max_bytes,
        )
        source_uri = document_storage.store_upload(
            filename=fetched.filename,
            data=fetched.data,
            content_type=fetched.content_type,
        )
        stored = ingest_document(
            settings.database_url,
            document=IngestionInput(
                title=fetched.title,
                content=fetched.content,
                source_type=fetched.source_type,
                source_uri=source_uri,
                chunk_size=payload.chunk_size,
                chunk_overlap=payload.chunk_overlap,
            ),
            embedding_provider=embedding_provider,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    cache.delete_prefix("answer:")
    return IngestTextResponse(
        document_id=stored.id,
        chunks_created=stored.chunks_created,
    )


@app.post(
    "/documents/ingest-url-async",
    response_model=IngestJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def ingest_url_async(payload: IngestUrlRequest) -> IngestJobResponse:
    try:
        fetched = fetch_url_document(
            payload.url,
            timeout_seconds=settings.url_fetch_timeout_seconds,
            max_bytes=settings.url_fetch_max_bytes,
        )
        source_uri = document_storage.store_upload(
            filename=fetched.filename,
            data=fetched.data,
            content_type=fetched.content_type,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    task = ingest_text_task.delay(
        IngestionInput(
            title=fetched.title,
            content=fetched.content,
            source_type=fetched.source_type,
            source_uri=source_uri,
            chunk_size=payload.chunk_size,
            chunk_overlap=payload.chunk_overlap,
        ).__dict__
    )
    return IngestJobResponse(task_id=task.id, status="queued")


@app.post(
    "/documents/upload",
    response_model=IngestTextResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile = File(...),
    chunk_size: int = 256,
    chunk_overlap: int = 40,
) -> IngestTextResponse:
    data = await file.read()
    try:
        loaded = load_uploaded_document(file.filename or "uploaded-document", data)
        source_uri = document_storage.store_upload(
            filename=file.filename or "uploaded-document",
            data=data,
            content_type=file.content_type,
        )
        stored = ingest_document(
            settings.database_url,
            document=IngestionInput(
                title=loaded.title,
                content=loaded.content,
                source_type=loaded.source_type,
                source_uri=source_uri,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            ),
            embedding_provider=embedding_provider,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    cache.delete_prefix("answer:")
    return IngestTextResponse(
        document_id=stored.id,
        chunks_created=stored.chunks_created,
    )


@app.post(
    "/documents/upload-async",
    response_model=IngestJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document_async(
    file: UploadFile = File(...),
    chunk_size: int = 256,
    chunk_overlap: int = 40,
) -> IngestJobResponse:
    data = await file.read()
    try:
        loaded = load_uploaded_document(file.filename or "uploaded-document", data)
        source_uri = document_storage.store_upload(
            filename=file.filename or "uploaded-document",
            data=data,
            content_type=file.content_type,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    task = ingest_text_task.delay(
        IngestionInput(
            title=loaded.title,
            content=loaded.content,
            source_type=loaded.source_type,
            source_uri=source_uri,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        ).__dict__
    )
    return IngestJobResponse(task_id=task.id, status="queued")


@app.get("/documents/jobs/{task_id}", response_model=IngestJobStatusResponse)
def get_ingestion_job(task_id: str) -> IngestJobStatusResponse:
    task = celery_app.AsyncResult(task_id)
    result = None
    error = None

    if task.successful():
        result = IngestTextResponse.model_validate(task.result)
    elif task.failed():
        error = str(task.result)

    return IngestJobStatusResponse(
        task_id=task_id,
        status=task.status,
        result=result,
        error=error,
    )


@app.post("/query/retrieve", response_model=RetrieveResponse)
def retrieve(payload: RetrieveRequest) -> RetrieveResponse:
    results = _retrieve_chunks(
        question=payload.question,
        top_k=payload.top_k,
        document_ids=payload.document_ids,
    )

    return RetrieveResponse(
        question=payload.question,
        results=results,
    )


@app.post("/query/answer", response_model=AnswerResponse)
def answer(payload: AnswerRequest) -> AnswerResponse:
    cache_key = stable_cache_key(
        "answer",
        {
            "question": payload.question,
            "top_k": payload.top_k,
            "document_ids": sorted(payload.document_ids),
            "embedding_provider": settings.embedding_provider,
            "embedding_dimension": embedding_provider.dimension,
            "reranker_provider": settings.reranker_provider,
            "reranker_candidate_multiplier": settings.reranker_candidate_multiplier,
            "generation_provider": settings.generation_provider,
            "generation_model": settings.gemini_generation_model,
        },
    )
    cached = cache.get_json(cache_key)
    if isinstance(cached, dict):
        cached["cache_hit"] = True
        return AnswerResponse.model_validate(cached)

    sources = _retrieve_chunks(
        question=payload.question,
        top_k=payload.top_k,
        document_ids=payload.document_ids,
    )
    generated = answer_generator.generate(question=payload.question, chunks=sources)

    response = AnswerResponse(
        question=payload.question,
        answer=generated.answer,
        citations=generated.citations,
        sources=sources,
    )
    cache.set_json(
        cache_key,
        response.model_dump(mode="json"),
        ttl_seconds=settings.answer_cache_ttl_seconds,
    )
    return response


@app.post("/eval/run", response_model=EvalRunResponse)
def run_eval(payload: EvalRunRequest) -> EvalRunResponse:
    runs = evaluate_configs(
        cases=payload.cases,
        configs=payload.configs,
        retrieve_fn=lambda question, top_k: _retrieve_chunks(
            question=question,
            top_k=top_k,
            document_ids=payload.document_ids,
        ),
        answer_fn=lambda question, chunks: answer_generator.generate(
            question=question,
            chunks=chunks,
        ),
        answer_quality_evaluator=answer_quality_evaluator,
    )
    return EvalRunResponse(runs=runs)


def _retrieve_chunks(
    *,
    question: str,
    top_k: int,
    document_ids: list[str] | None = None,
) -> list[RetrievedChunk]:
    query_embedding = embedding_provider.embed(question, task_type="RETRIEVAL_QUERY")
    ensure_schema(settings.database_url, embedding_dimension=embedding_provider.dimension)
    candidate_k = min(max(top_k, top_k * settings.reranker_candidate_multiplier), 100)
    rows = retrieve_similar_chunks(
        settings.database_url,
        query_embedding=query_embedding,
        top_k=candidate_k,
        document_ids=document_ids,
    )

    candidates = [
        RetrievedChunk(
            chunk_id=str(row["chunk_id"]),
            document_id=str(row["document_id"]),
            title=row["title"],
            content=row["content"],
            source_uri=row["source_uri"],
            chunk_index=row["chunk_index"],
            score=row["score"],
        )
        for row in rows
    ]

    return reranker.rerank(question=question, chunks=candidates, top_k=top_k)
