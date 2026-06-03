import pytest

from app.answer_evaluation import LocalAnswerQualityEvaluator, create_answer_quality_evaluator
from app.config import Settings
from app.evaluation import evaluate_case, evaluate_configs
from app.generation import GeneratedAnswer
from app.schemas import EvalCase, EvalConfig, RetrievedChunk


def chunk(content: str, *, score: float = 0.9, source_uri: str | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"chunk-{abs(hash(content))}",
        document_id="doc-1",
        title="Architecture Notes",
        content=content,
        source_uri=source_uri,
        chunk_index=0,
        score=score,
    )


def test_evaluate_case_scores_match_at_first_rank() -> None:
    result = evaluate_case(
        case=EvalCase(
            id="redis-cache",
            question="What caches answers?",
            expected_terms=["redis", "cache"],
        ),
        chunks=[
            chunk("Redis provides cache storage for repeated answers."),
            chunk("Celery runs ingestion jobs."),
        ],
    )

    assert result.matched is True
    assert result.recall_at_k == 1.0
    assert result.reciprocal_rank == 1.0
    assert result.context_precision == 0.5
    assert result.first_match_rank == 1
    assert result.matched_terms == ["cache", "redis"]


def test_evaluate_case_scores_miss() -> None:
    result = evaluate_case(
        case=EvalCase(
            id="missing",
            question="Where are embeddings stored?",
            expected_terms=["pgvector", "embeddings"],
        ),
        chunks=[chunk("Redis caches repeated answers.")],
    )

    assert result.matched is False
    assert result.recall_at_k == 0.0
    assert result.reciprocal_rank == 0.0
    assert result.context_precision == 0.0


def test_evaluate_configs_compares_top_k() -> None:
    def retrieve(question: str, top_k: int) -> list[RetrievedChunk]:
        results = [
            chunk("Redis caches repeated answers."),
            chunk("pgvector stores embeddings for similarity search."),
        ]
        return results[:top_k]

    runs = evaluate_configs(
        cases=[
            EvalCase(
                id="vectors",
                question="Where are embeddings stored?",
                expected_terms=["pgvector", "embeddings"],
            )
        ],
        configs=[
            EvalConfig(name="top-1", top_k=1),
            EvalConfig(name="top-2", top_k=2),
        ],
        retrieve_fn=retrieve,
    )

    assert runs[0].recall_at_k == 0.0
    assert runs[1].recall_at_k == 1.0
    assert runs[1].mean_reciprocal_rank == 0.5


def test_evaluate_configs_scores_generated_answers() -> None:
    def retrieve(question: str, top_k: int) -> list[RetrievedChunk]:
        return [
            chunk("pgvector stores embeddings for semantic search."),
        ]

    def answer(question: str, chunks: list[RetrievedChunk]) -> GeneratedAnswer:
        return GeneratedAnswer(
            answer="pgvector stores embeddings for semantic search. [1]",
            citations=[],
        )

    runs = evaluate_configs(
        cases=[
            EvalCase(
                id="vectors",
                question="Where are embeddings stored for semantic search?",
                expected_terms=["pgvector", "embeddings"],
            )
        ],
        configs=[EvalConfig(name="top-1", top_k=1)],
        retrieve_fn=retrieve,
        answer_fn=answer,
    )

    assert runs[0].mean_faithfulness == 1.0
    assert runs[0].mean_answer_relevance == 1.0
    assert runs[0].case_results[0].answer_relevance == 1.0
    assert "pgvector stores embeddings" in runs[0].case_results[0].answer


def test_evaluate_configs_penalizes_unsupported_answer_claims() -> None:
    def retrieve(question: str, top_k: int) -> list[RetrievedChunk]:
        return [
            chunk("pgvector stores embeddings for semantic search."),
        ]

    def answer(question: str, chunks: list[RetrievedChunk]) -> GeneratedAnswer:
        return GeneratedAnswer(
            answer="MongoDB stores embeddings for semantic search. [1]",
            citations=[],
        )

    runs = evaluate_configs(
        cases=[
            EvalCase(
                id="vectors",
                question="Where are embeddings stored for semantic search?",
                expected_terms=["pgvector", "embeddings"],
            )
        ],
        configs=[EvalConfig(name="top-1", top_k=1)],
        retrieve_fn=retrieve,
        answer_fn=answer,
    )

    assert runs[0].mean_faithfulness == 0.0
    assert runs[0].mean_answer_relevance > 0.0


def test_create_answer_quality_evaluator_uses_local_by_default() -> None:
    evaluator = create_answer_quality_evaluator(Settings())

    assert isinstance(evaluator, LocalAnswerQualityEvaluator)


def test_ragas_answer_quality_evaluator_requires_gemini_key() -> None:
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        create_answer_quality_evaluator(
            Settings(evaluation_provider="ragas", gemini_api_key=None)
        )
