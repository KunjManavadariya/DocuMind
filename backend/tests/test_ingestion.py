from app.chunking import TextChunk
from app.db import StoredDocument
from app.ingestion import IngestionInput, ingest_document


class FakeEmbeddingProvider:
    dimension = 4

    def embed(self, text: str, *, task_type: str = "SEMANTIC_SIMILARITY") -> list[float]:
        return [1.0, 0.0, 0.0, 0.0]


def test_ingest_document_chunks_embeds_and_stores(monkeypatch) -> None:
    captured = {}

    def fake_ensure_schema(database_url: str, *, embedding_dimension: int) -> None:
        captured["database_url"] = database_url
        captured["embedding_dimension"] = embedding_dimension

    def fake_store_text_document(database_url: str, **kwargs) -> StoredDocument:
        captured["store_kwargs"] = kwargs
        return StoredDocument(id="stored-1", chunks_created=len(kwargs["chunks"]))

    monkeypatch.setattr("app.ingestion.ensure_schema", fake_ensure_schema)
    monkeypatch.setattr("app.ingestion.store_text_document", fake_store_text_document)

    document = IngestionInput(
        title="Architecture Notes",
        content=" ".join(["FastAPI Redis pgvector Celery"] * 30),
        source_type="upload",
        source_uri="upload://notes.md",
        chunk_size=80,
        chunk_overlap=10,
    )

    stored = ingest_document(
        "postgresql://example",
        document=document,
        embedding_provider=FakeEmbeddingProvider(),
    )

    assert stored.id == "stored-1"
    assert captured["database_url"] == "postgresql://example"
    assert captured["embedding_dimension"] == 4
    assert captured["store_kwargs"]["source_type"] == "upload"
    assert captured["store_kwargs"]["source_uri"] == "upload://notes.md"
    assert all(isinstance(chunk, TextChunk) for chunk in captured["store_kwargs"]["chunks"])
    assert captured["store_kwargs"]["embeddings"][0] == [1.0, 0.0, 0.0, 0.0]
