from celery import Celery

from app.cache import create_cache
from app.config import get_settings
from app.embeddings import CachedEmbeddingProvider, create_embedding_provider
from app.ingestion import IngestionInput, ingest_document

settings = get_settings()

celery_app = Celery(
    "documind",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    accept_content=["json"],
    result_serializer="json",
    task_serializer="json",
    task_track_started=True,
)


@celery_app.task(name="documind.ping")
def ping() -> str:
    return "pong"


@celery_app.task(bind=True, name="documind.ingest_text")
def ingest_text_task(self, document_payload: dict) -> dict:
    current_settings = get_settings()
    cache = create_cache(current_settings)
    embedding_provider = CachedEmbeddingProvider(
        provider=create_embedding_provider(current_settings),
        cache=cache,
        ttl_seconds=current_settings.embedding_cache_ttl_seconds,
    )

    document = IngestionInput(**document_payload)
    stored = ingest_document(
        current_settings.database_url,
        document=document,
        embedding_provider=embedding_provider,
    )
    cache.delete_prefix("answer:")

    return {
        "document_id": stored.id,
        "chunks_created": stored.chunks_created,
    }
