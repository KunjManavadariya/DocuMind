from app.cache import InMemoryJsonCache
from app.db import StoredDocument
from app.worker import ingest_text_task


def test_ingest_text_task_runs_ingestion_and_clears_answer_cache(monkeypatch) -> None:
    cache = InMemoryJsonCache()
    cache.set_json("answer:old", {"cached": True}, ttl_seconds=60)
    captured = {}

    monkeypatch.setattr("app.worker.create_cache", lambda settings: cache)

    class FakeEmbeddingProvider:
        dimension = 4

        def embed(self, text: str, *, task_type: str = "SEMANTIC_SIMILARITY") -> list[float]:
            return [1.0, 0.0, 0.0, 0.0]

    monkeypatch.setattr(
        "app.worker.create_embedding_provider",
        lambda settings: FakeEmbeddingProvider(),
    )

    def fake_ingest_document(database_url, *, document, embedding_provider):
        captured["document"] = document
        captured["embedding_provider"] = embedding_provider
        return StoredDocument(id="doc-123", chunks_created=2)

    monkeypatch.setattr("app.worker.ingest_document", fake_ingest_document)

    result = ingest_text_task.run(
        {
            "title": "Worker Notes",
            "content": "Celery processes ingestion.",
            "source_type": "text",
            "source_uri": None,
            "chunk_size": 256,
            "chunk_overlap": 40,
        }
    )

    assert result == {"document_id": "doc-123", "chunks_created": 2}
    assert captured["document"].title == "Worker Notes"
    assert cache.get_json("answer:old") is None
