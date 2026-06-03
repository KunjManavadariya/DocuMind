from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

from google import genai
from google.genai import types

from app.cache import JsonCache, stable_cache_key
from app.config import Settings


class EmbeddingProvider(Protocol):
    dimension: int

    def embed(self, text: str, *, task_type: str = "SEMANTIC_SIMILARITY") -> list[float]:
        ...


class LocalHashEmbeddingProvider:
    """Deterministic local embeddings for tests and offline development."""

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def embed(self, text: str, *, task_type: str = "SEMANTIC_SIMILARITY") -> list[float]:
        vector = [0.0] * self.dimension
        terms = re.findall(r"[a-z0-9]+", text.lower())

        for term in terms:
            digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector

        return [value / norm for value in vector]


class GeminiEmbeddingProvider:
    def __init__(self, *, api_key: str, model: str, dimension: int) -> None:
        self.model = model
        self.dimension = dimension
        self.client = genai.Client(api_key=api_key)

    def embed(self, text: str, *, task_type: str = "SEMANTIC_SIMILARITY") -> list[float]:
        response = self.client.models.embed_content(
            model=self.model,
            contents=text,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=self.dimension,
            ),
        )
        if not response.embeddings:
            raise ValueError("Gemini returned no embeddings")

        values = response.embeddings[0].values
        if values is None:
            raise ValueError("Gemini returned an empty embedding")

        return list(values)


class CachedEmbeddingProvider:
    def __init__(
        self,
        *,
        provider: EmbeddingProvider,
        cache: JsonCache,
        ttl_seconds: int,
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.ttl_seconds = ttl_seconds
        self.dimension = provider.dimension

    def embed(self, text: str, *, task_type: str = "SEMANTIC_SIMILARITY") -> list[float]:
        key = stable_cache_key(
            "embedding",
            {
                "provider": self.provider.__class__.__name__,
                "model": getattr(self.provider, "model", "local"),
                "dimension": self.dimension,
                "task_type": task_type,
                "text": text,
            },
        )
        cached = self.cache.get_json(key)
        if isinstance(cached, list):
            return [float(value) for value in cached]

        embedding = self.provider.embed(text, task_type=task_type)
        self.cache.set_json(key, embedding, ttl_seconds=self.ttl_seconds)
        return embedding


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    match settings.embedding_provider:
        case "local":
            return LocalHashEmbeddingProvider(dimension=settings.embedding_dimension)
        case "gemini":
            if not settings.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is required when EMBEDDING_PROVIDER=gemini")
            return GeminiEmbeddingProvider(
                api_key=settings.gemini_api_key,
                model=settings.gemini_embedding_model,
                dimension=settings.embedding_dimension,
            )
        case unsupported:
            raise ValueError(f"Unsupported EMBEDDING_PROVIDER '{unsupported}'")


def format_vector(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"
