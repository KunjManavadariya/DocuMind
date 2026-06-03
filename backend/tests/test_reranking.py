from app.reranking import LocalLexicalReranker, NoOpReranker
from app.schemas import RetrievedChunk


def test_local_lexical_reranker_promotes_term_overlap() -> None:
    chunks = [
        _chunk("general", "FastAPI serves the backend API.", score=0.95),
        _chunk("specific", "pgvector stores embeddings for semantic search.", score=0.65),
    ]

    reranked = LocalLexicalReranker().rerank(
        question="What stores embeddings for semantic search?",
        chunks=chunks,
        top_k=1,
    )

    assert reranked[0].title == "specific"


def test_noop_reranker_preserves_vector_order() -> None:
    chunks = [
        _chunk("first", "A", score=0.9),
        _chunk("second", "B", score=0.8),
    ]

    reranked = NoOpReranker().rerank(question="anything", chunks=chunks, top_k=2)

    assert [chunk.title for chunk in reranked] == ["first", "second"]


def _chunk(title: str, content: str, *, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=title,
        document_id="doc-1",
        title=title,
        content=content,
        source_uri=None,
        chunk_index=0,
        score=score,
    )
