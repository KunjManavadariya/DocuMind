import pytest

from app.config import Settings
from app.generation import (
    GeminiAnswerGenerator,
    LocalGroundedAnswerGenerator,
    build_grounded_prompt,
    create_answer_generator,
)
from app.schemas import RetrievedChunk


def test_local_grounded_answer_generator_returns_citations() -> None:
    chunks = [
        RetrievedChunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            title="Architecture",
            content="Redis powers Celery background ingestion.",
            source_uri="upload://architecture.md",
            chunk_index=0,
            score=0.93,
        ),
        RetrievedChunk(
            chunk_id="chunk-2",
            document_id="doc-1",
            title="Architecture",
            content="pgvector stores embeddings for similarity search.",
            source_uri="upload://architecture.md",
            chunk_index=1,
            score=0.89,
        ),
    ]

    generated = LocalGroundedAnswerGenerator().generate(
        question="How does ingestion and retrieval work?",
        chunks=chunks,
    )

    assert "Redis powers Celery" in generated.answer
    assert "[1]" in generated.answer
    assert "[2]" in generated.answer
    assert [citation.marker for citation in generated.citations] == ["[1]", "[2]"]
    assert generated.citations[0].chunk_id == "chunk-1"


def test_local_grounded_answer_generator_handles_no_sources() -> None:
    generated = LocalGroundedAnswerGenerator().generate(
        question="What is DocuMind?",
        chunks=[],
    )

    assert "could not find enough relevant documentation" in generated.answer
    assert generated.citations == []


def test_build_grounded_prompt_includes_rules_question_and_context() -> None:
    prompt = build_grounded_prompt(
        question="What stores embeddings?",
        chunks=[
            RetrievedChunk(
                chunk_id="chunk-1",
                document_id="doc-1",
                title="Architecture",
                content="pgvector stores embeddings.",
                source_uri=None,
                chunk_index=0,
                score=0.9,
            )
        ],
    )

    assert "Answer only from the provided context" in prompt
    assert "What stores embeddings?" in prompt
    assert "[1] Architecture chunk 0" in prompt
    assert "pgvector stores embeddings." in prompt


def test_create_answer_generator_returns_local_by_default() -> None:
    settings = Settings(generation_provider="local")

    generator = create_answer_generator(settings)

    assert isinstance(generator, LocalGroundedAnswerGenerator)


def test_create_answer_generator_requires_gemini_key() -> None:
    settings = Settings(generation_provider="gemini", gemini_api_key="")

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        create_answer_generator(settings)


def test_gemini_answer_generator_calls_sdk_with_grounded_prompt(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        text = "pgvector stores embeddings for similarity search. [1]"

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            captured["model"] = model
            captured["contents"] = contents
            captured["temperature"] = config.temperature
            return FakeResponse()

    class FakeClient:
        def __init__(self, *, api_key):
            captured["api_key"] = api_key
            self.models = FakeModels()

    monkeypatch.setattr("app.generation.genai.Client", FakeClient)

    generator = GeminiAnswerGenerator(
        api_key="test-key",
        model="gemini-2.5-flash-lite",
        temperature=0.1,
    )
    generated = generator.generate(
        question="What stores embeddings?",
        chunks=[
            RetrievedChunk(
                chunk_id="chunk-1",
                document_id="doc-1",
                title="Architecture",
                content="pgvector stores embeddings for similarity search.",
                source_uri="upload://architecture.md",
                chunk_index=0,
                score=0.92,
            )
        ],
    )

    assert captured["api_key"] == "test-key"
    assert captured["model"] == "gemini-2.5-flash-lite"
    assert captured["temperature"] == 0.1
    assert "Answer only from the provided context" in captured["contents"]
    assert generated.answer == "pgvector stores embeddings for similarity search. [1]"
    assert generated.citations[0].marker == "[1]"
