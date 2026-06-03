import math
import pytest

from app.config import Settings
from app.cache import InMemoryJsonCache
from app.embeddings import (
    CachedEmbeddingProvider,
    GeminiEmbeddingProvider,
    LocalHashEmbeddingProvider,
    create_embedding_provider,
    format_vector,
)


def test_local_hash_embedding_is_deterministic_and_normalized() -> None:
    provider = LocalHashEmbeddingProvider(dimension=32)

    first = provider.embed("FastAPI Redis pgvector")
    second = provider.embed("FastAPI Redis pgvector")

    assert first == second
    assert len(first) == 32
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0)


def test_format_vector_outputs_pgvector_literal() -> None:
    assert format_vector([0.1, -0.25]) == "[0.10000000,-0.25000000]"


def test_create_embedding_provider_returns_local_by_default() -> None:
    provider = create_embedding_provider(Settings(embedding_provider="local", embedding_dimension=16))

    assert isinstance(provider, LocalHashEmbeddingProvider)
    assert provider.dimension == 16


def test_create_embedding_provider_requires_gemini_key() -> None:
    settings = Settings(embedding_provider="gemini", gemini_api_key="")

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        create_embedding_provider(settings)


def test_gemini_embedding_provider_calls_sdk_with_dimension_and_task(monkeypatch) -> None:
    captured = {}

    class FakeEmbedding:
        values = [0.1, 0.2, 0.3]

    class FakeResponse:
        embeddings = [FakeEmbedding()]

    class FakeModels:
        def embed_content(self, *, model, contents, config):
            captured["model"] = model
            captured["contents"] = contents
            captured["task_type"] = config.task_type
            captured["output_dimensionality"] = config.output_dimensionality
            return FakeResponse()

    class FakeClient:
        def __init__(self, *, api_key):
            captured["api_key"] = api_key
            self.models = FakeModels()

    monkeypatch.setattr("app.embeddings.genai.Client", FakeClient)

    provider = GeminiEmbeddingProvider(
        api_key="test-key",
        model="gemini-embedding-001",
        dimension=3,
    )
    embedding = provider.embed("pgvector stores embeddings", task_type="RETRIEVAL_QUERY")

    assert embedding == [0.1, 0.2, 0.3]
    assert captured["api_key"] == "test-key"
    assert captured["model"] == "gemini-embedding-001"
    assert captured["contents"] == "pgvector stores embeddings"
    assert captured["task_type"] == "RETRIEVAL_QUERY"
    assert captured["output_dimensionality"] == 3


def test_cached_embedding_provider_reuses_cached_values() -> None:
    class CountingProvider:
        dimension = 3
        calls = 0

        def embed(self, text: str, *, task_type: str = "SEMANTIC_SIMILARITY") -> list[float]:
            self.calls += 1
            return [1.0, 0.0, 0.0]

    provider = CountingProvider()
    cached = CachedEmbeddingProvider(
        provider=provider,
        cache=InMemoryJsonCache(),
        ttl_seconds=60,
    )

    first = cached.embed("same text", task_type="RETRIEVAL_QUERY")
    second = cached.embed("same text", task_type="RETRIEVAL_QUERY")

    assert first == second == [1.0, 0.0, 0.0]
    assert provider.calls == 1
