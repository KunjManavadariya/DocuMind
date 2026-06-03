from __future__ import annotations

from dataclasses import dataclass

from app.chunking import chunk_text
from app.db import StoredDocument, ensure_schema, store_text_document
from app.embeddings import EmbeddingProvider


@dataclass(frozen=True)
class IngestionInput:
    title: str
    content: str
    source_type: str
    source_uri: str | None
    chunk_size: int
    chunk_overlap: int


def ingest_document(
    database_url: str,
    *,
    document: IngestionInput,
    embedding_provider: EmbeddingProvider,
) -> StoredDocument:
    if document.chunk_overlap >= document.chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    chunks = chunk_text(
        document.content,
        chunk_size=document.chunk_size,
        chunk_overlap=document.chunk_overlap,
    )
    if not chunks:
        raise ValueError("content did not produce any chunks")

    embeddings = [
        embedding_provider.embed(chunk.content, task_type="RETRIEVAL_DOCUMENT")
        for chunk in chunks
    ]

    ensure_schema(database_url, embedding_dimension=embedding_provider.dimension)
    return store_text_document(
        database_url,
        title=document.title,
        content=document.content,
        source_uri=document.source_uri,
        source_type=document.source_type,
        chunks=chunks,
        embeddings=embeddings,
    )
