from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from app.chunking import TextChunk
from app.embeddings import format_vector


@dataclass(frozen=True)
class StoredDocument:
    id: str
    chunks_created: int


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def ensure_schema(database_url: str, *, embedding_dimension: int = 384) -> None:
    if embedding_dimension < 1 or embedding_dimension > 4096:
        raise ValueError("embedding_dimension must be between 1 and 4096")

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id UUID PRIMARY KEY,
                    title TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_uri TEXT,
                    content_sha256 TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id UUID PRIMARY KEY,
                    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    embedding VECTOR({embedding_dimension}) NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (document_id, chunk_index)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS document_chunks_document_id_idx
                ON document_chunks (document_id)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx
                ON document_chunks
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
                """
            )
        conn.commit()


def store_text_document(
    database_url: str,
    *,
    title: str,
    content: str,
    source_uri: str | None,
    source_type: str = "text",
    chunks: Iterable[TextChunk],
    embeddings: Iterable[list[float]],
) -> StoredDocument:
    document_id = str(uuid4())
    chunk_rows = list(zip(chunks, embeddings, strict=True))

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents (id, title, source_type, source_uri, content_sha256)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (content_sha256) DO UPDATE
                SET title = EXCLUDED.title,
                    source_uri = EXCLUDED.source_uri
                RETURNING id
                """,
                (document_id, title, source_type, source_uri, content_sha256(content)),
            )
            document_id = str(cur.fetchone()[0])

            cur.execute("DELETE FROM document_chunks WHERE document_id = %s", (document_id,))

            for chunk, embedding in chunk_rows:
                cur.execute(
                    """
                    INSERT INTO document_chunks (
                        id,
                        document_id,
                        chunk_index,
                        content,
                        token_count,
                        embedding,
                        metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::vector, %s)
                    """,
                    (
                        str(uuid4()),
                        document_id,
                        chunk.index,
                        chunk.content,
                        chunk.token_count,
                        format_vector(embedding),
                        "{}",
                    ),
                )
        conn.commit()

    return StoredDocument(id=document_id, chunks_created=len(chunk_rows))


def list_documents(database_url: str) -> list[dict]:
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    d.id,
                    d.title,
                    d.source_type,
                    d.source_uri,
                    d.created_at,
                    COUNT(c.id)::int AS chunks_created
                FROM documents d
                LEFT JOIN document_chunks c ON c.document_id = d.id
                GROUP BY d.id
                ORDER BY d.created_at DESC
                """
            )
            return list(cur.fetchall())


def clear_corpus(database_url: str) -> dict[str, int]:
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*)::int AS count FROM documents")
            documents_deleted = cur.fetchone()["count"]
            cur.execute("SELECT COUNT(*)::int AS count FROM document_chunks")
            chunks_deleted = cur.fetchone()["count"]
            cur.execute("DELETE FROM documents")
        conn.commit()

    return {
        "documents_deleted": documents_deleted,
        "chunks_deleted": chunks_deleted,
    }


def retrieve_similar_chunks(
    database_url: str,
    *,
    query_embedding: list[float],
    top_k: int,
    document_ids: list[str] | None = None,
) -> list[dict]:
    scoped_document_ids = document_ids or None

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL ivfflat.probes = 100")
            cur.execute(
                """
                SELECT
                    c.id AS chunk_id,
                    c.document_id,
                    d.title,
                    d.source_uri,
                    c.chunk_index,
                    c.content,
                    1 - (c.embedding <=> %s::vector) AS score
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE (%s::uuid[] IS NULL OR c.document_id = ANY(%s::uuid[]))
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                (
                    format_vector(query_embedding),
                    scoped_document_ids,
                    scoped_document_ids,
                    format_vector(query_embedding),
                    top_k,
                ),
            )
            return list(cur.fetchall())
