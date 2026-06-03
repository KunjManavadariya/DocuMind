from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app import main as main_module
from app.cache import InMemoryJsonCache
from app.db import StoredDocument
from app.document_loaders import FetchedUrlDocument


def test_ingest_text_endpoint_chunks_and_stores(monkeypatch) -> None:
    captured = {}

    def fake_ingest_document(database_url: str, *, document, embedding_provider) -> StoredDocument:
        captured["database_url"] = database_url
        captured["document"] = document
        captured["embedding_provider"] = embedding_provider
        return StoredDocument(id="doc-123", chunks_created=2)

    monkeypatch.setattr(main_module, "ingest_document", fake_ingest_document)

    client = TestClient(main_module.app)
    content = " ".join(
        [
            "FastAPI serves the API.",
            "Redis powers Celery.",
            "pgvector stores embeddings.",
        ]
        * 15
    )
    response = client.post(
        "/documents/ingest-text",
        json={
            "title": "Architecture Notes",
            "content": content,
            "chunk_size": 80,
            "chunk_overlap": 10,
        },
    )

    assert response.status_code == 201
    assert response.json() == {"document_id": "doc-123", "chunks_created": 2}
    assert captured["document"].title == "Architecture Notes"
    assert captured["document"].source_type == "text"
    assert captured["document"].chunk_size == 80


def test_upload_document_endpoint_loads_file_and_ingests(monkeypatch) -> None:
    captured = {}

    def fake_ingest_document(database_url: str, *, document, embedding_provider) -> StoredDocument:
        captured["document"] = document
        return StoredDocument(id="upload-123", chunks_created=1)

    monkeypatch.setattr(main_module, "ingest_document", fake_ingest_document)

    class FakeStorage:
        def store_upload(self, *, filename, data, content_type=None):
            captured["stored_upload"] = {
                "filename": filename,
                "data": data,
                "content_type": content_type,
            }
            return "local://uploads/stored-notes.md"

    monkeypatch.setattr(main_module, "document_storage", FakeStorage())

    client = TestClient(main_module.app)
    response = client.post(
        "/documents/upload",
        params={"chunk_size": 80, "chunk_overlap": 10},
        files={
            "file": (
                "notes.md",
                b"# Notes\n\nFastAPI serves the API and pgvector stores embeddings.",
                "text/markdown",
            )
        },
    )

    assert response.status_code == 201
    assert response.json() == {"document_id": "upload-123", "chunks_created": 1}
    assert captured["document"].title == "notes"
    assert captured["document"].source_type == "upload"
    assert captured["document"].source_uri == "local://uploads/stored-notes.md"
    assert captured["stored_upload"]["filename"] == "notes.md"
    assert captured["stored_upload"]["content_type"] == "text/markdown"


def test_upload_document_rejects_unsupported_file_type() -> None:
    client = TestClient(main_module.app)
    response = client.post(
        "/documents/upload",
        files={"file": ("image.png", b"not a supported document", "image/png")},
    )

    assert response.status_code == 422
    assert "Unsupported file type" in response.json()["detail"]


def test_ingest_text_async_enqueues_celery_task(monkeypatch) -> None:
    captured = {}

    class FakeTask:
        id = "task-123"

    def fake_delay(payload):
        captured["payload"] = payload
        return FakeTask()

    monkeypatch.setattr(main_module.ingest_text_task, "delay", fake_delay)

    client = TestClient(main_module.app)
    response = client.post(
        "/documents/ingest-text-async",
        json={
            "title": "Async Notes",
            "content": " ".join(["Celery processes ingestion in the background."] * 30),
            "chunk_size": 80,
            "chunk_overlap": 10,
        },
    )

    assert response.status_code == 202
    assert response.json() == {"task_id": "task-123", "status": "queued"}
    assert captured["payload"]["title"] == "Async Notes"
    assert captured["payload"]["source_type"] == "text"


def test_ingest_url_endpoint_fetches_stores_and_ingests(monkeypatch) -> None:
    captured = {}

    monkeypatch.setattr(
        main_module,
        "fetch_url_document",
        lambda url, *, timeout_seconds, max_bytes: FetchedUrlDocument(
            title="Docs Guide",
            content="FastAPI serves the API and pgvector stores embeddings.",
            source_type="url",
            source_uri=url,
            filename="guide.html",
            data=b"<main>FastAPI serves the API and pgvector stores embeddings.</main>",
            content_type="text/html",
        ),
    )

    class FakeStorage:
        def store_upload(self, *, filename, data, content_type=None):
            captured["stored_upload"] = {
                "filename": filename,
                "data": data,
                "content_type": content_type,
            }
            return "local://uploads/stored-guide.html"

    def fake_ingest_document(database_url: str, *, document, embedding_provider) -> StoredDocument:
        captured["document"] = document
        return StoredDocument(id="url-doc-123", chunks_created=1)

    monkeypatch.setattr(main_module, "document_storage", FakeStorage())
    monkeypatch.setattr(main_module, "ingest_document", fake_ingest_document)

    client = TestClient(main_module.app)
    response = client.post(
        "/documents/ingest-url",
        json={"url": "https://docs.example.com/guide", "chunk_size": 80, "chunk_overlap": 10},
    )

    assert response.status_code == 201
    assert response.json() == {"document_id": "url-doc-123", "chunks_created": 1}
    assert captured["document"].title == "Docs Guide"
    assert captured["document"].source_type == "url"
    assert captured["document"].source_uri == "local://uploads/stored-guide.html"
    assert captured["stored_upload"]["filename"] == "guide.html"
    assert captured["stored_upload"]["content_type"] == "text/html"


def test_ingest_url_async_fetches_stores_and_enqueues(monkeypatch) -> None:
    captured = {}

    class FakeTask:
        id = "url-task-123"

    monkeypatch.setattr(
        main_module,
        "fetch_url_document",
        lambda url, *, timeout_seconds, max_bytes: FetchedUrlDocument(
            title="Docs Guide",
            content="Celery processes URL ingestion in the background.",
            source_type="url",
            source_uri=url,
            filename="guide.html",
            data=b"<main>Celery processes URL ingestion in the background.</main>",
            content_type="text/html",
        ),
    )

    class FakeStorage:
        def store_upload(self, *, filename, data, content_type=None):
            captured["stored_upload"] = {
                "filename": filename,
                "data": data,
                "content_type": content_type,
            }
            return "local://uploads/stored-guide.html"

    def fake_delay(payload):
        captured["payload"] = payload
        return FakeTask()

    monkeypatch.setattr(main_module, "document_storage", FakeStorage())
    monkeypatch.setattr(main_module.ingest_text_task, "delay", fake_delay)

    client = TestClient(main_module.app)
    response = client.post(
        "/documents/ingest-url-async",
        json={"url": "https://docs.example.com/guide", "chunk_size": 80, "chunk_overlap": 10},
    )

    assert response.status_code == 202
    assert response.json() == {"task_id": "url-task-123", "status": "queued"}
    assert captured["payload"]["title"] == "Docs Guide"
    assert captured["payload"]["source_type"] == "url"
    assert captured["payload"]["source_uri"] == "local://uploads/stored-guide.html"
    assert captured["stored_upload"]["filename"] == "guide.html"


def test_upload_document_async_loads_file_and_enqueues(monkeypatch) -> None:
    captured = {}

    class FakeTask:
        id = "upload-task-123"

    def fake_delay(payload):
        captured["payload"] = payload
        return FakeTask()

    monkeypatch.setattr(main_module.ingest_text_task, "delay", fake_delay)

    class FakeStorage:
        def store_upload(self, *, filename, data, content_type=None):
            captured["stored_upload"] = {
                "filename": filename,
                "data": data,
                "content_type": content_type,
            }
            return "local://uploads/stored-async-notes.md"

    monkeypatch.setattr(main_module, "document_storage", FakeStorage())

    client = TestClient(main_module.app)
    response = client.post(
        "/documents/upload-async",
        params={"chunk_size": 80, "chunk_overlap": 10},
        files={
            "file": (
                "async-notes.md",
                b"# Async\n\nCelery processes document ingestion in the background.",
                "text/markdown",
            )
        },
    )

    assert response.status_code == 202
    assert response.json() == {"task_id": "upload-task-123", "status": "queued"}
    assert captured["payload"]["title"] == "async-notes"
    assert captured["payload"]["source_type"] == "upload"
    assert captured["payload"]["source_uri"] == "local://uploads/stored-async-notes.md"
    assert captured["stored_upload"]["filename"] == "async-notes.md"


def test_get_ingestion_job_returns_success_result(monkeypatch) -> None:
    class FakeAsyncResult:
        status = "SUCCESS"
        result = {"document_id": "doc-123", "chunks_created": 4}

        def successful(self):
            return True

        def failed(self):
            return False

    monkeypatch.setattr(
        main_module.celery_app,
        "AsyncResult",
        lambda task_id: FakeAsyncResult(),
    )

    client = TestClient(main_module.app)
    response = client.get("/documents/jobs/task-123")

    assert response.status_code == 200
    assert response.json() == {
        "task_id": "task-123",
        "status": "SUCCESS",
        "result": {"document_id": "doc-123", "chunks_created": 4},
        "error": None,
    }


def test_get_ingestion_job_returns_failure_error(monkeypatch) -> None:
    class FakeAsyncResult:
        status = "FAILURE"
        result = RuntimeError("embedding provider failed")

        def successful(self):
            return False

        def failed(self):
            return True

    monkeypatch.setattr(
        main_module.celery_app,
        "AsyncResult",
        lambda task_id: FakeAsyncResult(),
    )

    client = TestClient(main_module.app)
    response = client.get("/documents/jobs/task-123")

    assert response.status_code == 200
    assert response.json()["status"] == "FAILURE"
    assert response.json()["result"] is None
    assert "embedding provider failed" in response.json()["error"]


def test_list_documents_returns_indexed_corpus(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "ensure_schema",
        lambda database_url, *, embedding_dimension: None,
    )
    monkeypatch.setattr(
        main_module,
        "list_documents",
        lambda database_url: [
            {
                "id": "doc-1",
                "title": "Architecture Notes",
                "source_type": "upload",
                "source_uri": "upload://notes.md",
                "chunks_created": 3,
                "created_at": datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
            }
        ],
    )

    client = TestClient(main_module.app)
    response = client.get("/documents")

    assert response.status_code == 200
    assert response.json() == {
        "documents": [
            {
                "id": "doc-1",
                "title": "Architecture Notes",
                "source_type": "upload",
                "source_uri": "upload://notes.md",
                "chunks_created": 3,
                "created_at": "2026-06-01T10:00:00+00:00",
            }
        ]
    }


def test_delete_documents_clears_corpus_and_answer_cache(monkeypatch) -> None:
    cache = InMemoryJsonCache()
    cache.set_json("answer:existing", {"cached": True}, ttl_seconds=60)
    main_module.cache = cache

    monkeypatch.setattr(
        main_module,
        "ensure_schema",
        lambda database_url, *, embedding_dimension: None,
    )
    monkeypatch.setattr(
        main_module,
        "clear_corpus",
        lambda database_url: {"documents_deleted": 2, "chunks_deleted": 7},
    )

    client = TestClient(main_module.app)
    response = client.delete("/documents")

    assert response.status_code == 200
    assert response.json() == {"documents_deleted": 2, "chunks_deleted": 7}
    assert cache.get_json("answer:existing") is None


def test_retrieve_endpoint_returns_ranked_chunks(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(
        main_module,
        "ensure_schema",
        lambda database_url, *, embedding_dimension: None,
    )

    def fake_retrieve_similar_chunks(database_url, *, query_embedding, top_k, document_ids=None):
        captured["top_k"] = top_k
        return [
            {
                "chunk_id": "chunk-1",
                "document_id": "doc-1",
                "title": "Architecture Notes",
                "source_uri": None,
                "chunk_index": 0,
                "content": "Redis powers Celery background ingestion.",
                "score": 0.91,
            }
        ]

    monkeypatch.setattr(main_module, "retrieve_similar_chunks", fake_retrieve_similar_chunks)

    client = TestClient(main_module.app)
    response = client.post(
        "/query/retrieve",
        json={"question": "What powers background ingestion?", "top_k": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["question"] == "What powers background ingestion?"
    assert body["results"][0]["content"] == "Redis powers Celery background ingestion."
    assert body["results"][0]["score"] == 0.91
    assert captured["top_k"] > 3


def test_retrieve_endpoint_passes_document_scope(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(
        main_module,
        "ensure_schema",
        lambda database_url, *, embedding_dimension: None,
    )

    def fake_retrieve_similar_chunks(database_url, *, query_embedding, top_k, document_ids=None):
        captured["document_ids"] = document_ids
        return []

    monkeypatch.setattr(main_module, "retrieve_similar_chunks", fake_retrieve_similar_chunks)

    client = TestClient(main_module.app)
    response = client.post(
        "/query/retrieve",
        json={
            "question": "What stores embeddings?",
            "top_k": 3,
            "document_ids": ["11111111-1111-1111-1111-111111111111"],
        },
    )

    assert response.status_code == 200
    assert captured["document_ids"] == ["11111111-1111-1111-1111-111111111111"]


def test_retrieve_endpoint_reranks_candidates(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "ensure_schema",
        lambda database_url, *, embedding_dimension: None,
    )
    monkeypatch.setattr(
        main_module,
        "retrieve_similar_chunks",
        lambda database_url, *, query_embedding, top_k, document_ids=None: [
            {
                "chunk_id": "chunk-1",
                "document_id": "doc-1",
                "title": "General Notes",
                "source_uri": None,
                "chunk_index": 0,
                "content": "FastAPI serves the backend API.",
                "score": 0.99,
            },
            {
                "chunk_id": "chunk-2",
                "document_id": "doc-1",
                "title": "Vector Notes",
                "source_uri": None,
                "chunk_index": 1,
                "content": "pgvector stores embeddings for semantic search.",
                "score": 0.65,
            },
        ],
    )

    client = TestClient(main_module.app)
    response = client.post(
        "/query/retrieve",
        json={"question": "What stores embeddings for semantic search?", "top_k": 1},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["chunk_id"] == "chunk-2"


def test_answer_endpoint_returns_answer_with_citations(monkeypatch) -> None:
    main_module.cache = InMemoryJsonCache()
    monkeypatch.setattr(
        main_module,
        "ensure_schema",
        lambda database_url, *, embedding_dimension: None,
    )
    monkeypatch.setattr(
        main_module,
        "retrieve_similar_chunks",
        lambda database_url, *, query_embedding, top_k, document_ids=None: [
            {
                "chunk_id": "chunk-1",
                "document_id": "doc-1",
                "title": "Architecture Notes",
                "source_uri": "upload://notes.md",
                "chunk_index": 0,
                "content": "pgvector stores embeddings for similarity search.",
                "score": 0.94,
            }
        ],
    )

    client = TestClient(main_module.app)
    response = client.post(
        "/query/answer",
        json={"question": "What stores embeddings?", "top_k": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["question"] == "What stores embeddings?"
    assert "pgvector stores embeddings" in body["answer"]
    assert body["citations"][0]["marker"] == "[1]"
    assert body["citations"][0]["chunk_id"] == "chunk-1"
    assert body["sources"][0]["title"] == "Architecture Notes"
    assert body["cache_hit"] is False


def test_answer_endpoint_serves_repeated_question_from_cache(monkeypatch) -> None:
    main_module.cache = InMemoryJsonCache()
    calls = {"retrieval": 0}

    monkeypatch.setattr(
        main_module,
        "ensure_schema",
        lambda database_url, *, embedding_dimension: None,
    )

    def fake_retrieve_similar_chunks(database_url, *, query_embedding, top_k, document_ids=None):
        calls["retrieval"] += 1
        return [
            {
                "chunk_id": "chunk-1",
                "document_id": "doc-1",
                "title": "Architecture Notes",
                "source_uri": "upload://notes.md",
                "chunk_index": 0,
                "content": "Redis caches repeated answers.",
                "score": 0.94,
            }
        ]

    monkeypatch.setattr(main_module, "retrieve_similar_chunks", fake_retrieve_similar_chunks)

    client = TestClient(main_module.app)
    first = client.post(
        "/query/answer",
        json={"question": "What caches repeated answers?", "top_k": 3},
    )
    second = client.post(
        "/query/answer",
        json={"question": "What caches repeated answers?", "top_k": 3},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["cache_hit"] is False
    assert second.json()["cache_hit"] is True
    assert calls["retrieval"] == 1


def test_answer_cache_key_includes_document_scope(monkeypatch) -> None:
    main_module.cache = InMemoryJsonCache()
    calls = {"retrieval": 0}

    monkeypatch.setattr(
        main_module,
        "ensure_schema",
        lambda database_url, *, embedding_dimension: None,
    )

    def fake_retrieve_similar_chunks(database_url, *, query_embedding, top_k, document_ids=None):
        calls["retrieval"] += 1
        return [
            {
                "chunk_id": f"chunk-{calls['retrieval']}",
                "document_id": document_ids[0] if document_ids else "doc-all",
                "title": "Scoped Notes",
                "source_uri": "upload://notes.md",
                "chunk_index": 0,
                "content": "Redis caches repeated answers.",
                "score": 0.94,
            }
        ]

    monkeypatch.setattr(main_module, "retrieve_similar_chunks", fake_retrieve_similar_chunks)

    client = TestClient(main_module.app)
    first = client.post(
        "/query/answer",
        json={
            "question": "What caches repeated answers?",
            "top_k": 3,
            "document_ids": ["11111111-1111-1111-1111-111111111111"],
        },
    )
    second = client.post(
        "/query/answer",
        json={
            "question": "What caches repeated answers?",
            "top_k": 3,
            "document_ids": ["22222222-2222-2222-2222-222222222222"],
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["cache_hit"] is False
    assert second.json()["cache_hit"] is False
    assert calls["retrieval"] == 2


def test_eval_run_endpoint_compares_configs(monkeypatch) -> None:
    def fake_retrieve_chunks(*, question, top_k, document_ids=None):
        results = [
            {
                "chunk_id": "chunk-1",
                "document_id": "doc-1",
                "title": "Architecture Notes",
                "source_uri": "upload://notes.md",
                "chunk_index": 0,
                "content": "Redis caches repeated answers.",
                "score": 0.95,
            },
            {
                "chunk_id": "chunk-2",
                "document_id": "doc-1",
                "title": "Architecture Notes",
                "source_uri": "upload://notes.md",
                "chunk_index": 1,
                "content": "pgvector stores embeddings.",
                "score": 0.9,
            },
        ]
        return [
            main_module.RetrievedChunk(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                title=row["title"],
                source_uri=row["source_uri"],
                chunk_index=row["chunk_index"],
                content=row["content"],
                score=row["score"],
            )
            for row in results[:top_k]
        ]

    monkeypatch.setattr(main_module, "_retrieve_chunks", fake_retrieve_chunks)

    client = TestClient(main_module.app)
    response = client.post(
        "/eval/run",
        json={
            "cases": [
                {
                    "id": "vectors",
                    "question": "Where are embeddings stored?",
                    "expected_terms": ["pgvector", "embeddings"],
                }
            ],
            "configs": [
                {"name": "top-1", "top_k": 1},
                {"name": "top-2", "top_k": 2},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["runs"][0]["recall_at_k"] == 0.0
    assert body["runs"][1]["recall_at_k"] == 1.0
    assert body["runs"][1]["mean_faithfulness"] == 1.0
    assert body["runs"][1]["mean_answer_relevance"] == 1.0
    assert "pgvector stores embeddings" in body["runs"][1]["case_results"][0]["answer"]


def test_eval_run_endpoint_passes_document_scope(monkeypatch) -> None:
    captured = {}

    def fake_retrieve_chunks(*, question, top_k, document_ids=None):
        captured["document_ids"] = document_ids
        return []

    monkeypatch.setattr(main_module, "_retrieve_chunks", fake_retrieve_chunks)

    client = TestClient(main_module.app)
    response = client.post(
        "/eval/run",
        json={
            "cases": [
                {
                    "id": "vectors",
                    "question": "Where are embeddings stored?",
                    "expected_terms": ["pgvector", "embeddings"],
                }
            ],
            "configs": [{"name": "top-1", "top_k": 1}],
            "document_ids": ["11111111-1111-1111-1111-111111111111"],
        },
    )

    assert response.status_code == 200
    assert captured["document_ids"] == ["11111111-1111-1111-1111-111111111111"]


def test_ingestion_clears_cached_answers(monkeypatch) -> None:
    cache = InMemoryJsonCache()
    cache.set_json("answer:existing", {"cached": True}, ttl_seconds=60)
    main_module.cache = cache

    monkeypatch.setattr(
        main_module,
        "ingest_document",
        lambda database_url, *, document, embedding_provider: StoredDocument(
            id="doc-123",
            chunks_created=1,
        ),
    )

    client = TestClient(main_module.app)
    response = client.post(
        "/documents/ingest-text",
        json={"title": "Notes", "content": " ".join(["Redis cache invalidation"] * 40)},
    )

    assert response.status_code == 201
    assert cache.get_json("answer:existing") is None
