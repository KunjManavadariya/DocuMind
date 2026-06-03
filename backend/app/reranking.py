from __future__ import annotations

import re
from typing import Protocol

from app.config import Settings
from app.schemas import RetrievedChunk


class Reranker(Protocol):
    def rerank(self, *, question: str, chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
        ...


class NoOpReranker:
    def rerank(self, *, question: str, chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
        return chunks[:top_k]


class LocalLexicalReranker:
    def rerank(self, *, question: str, chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
        question_terms = set(_terms(question))
        if not question_terms:
            return chunks[:top_k]

        scored = [
            (
                _lexical_score(question_terms, chunk),
                chunk.score,
                -index,
                chunk,
            )
            for index, chunk in enumerate(chunks)
        ]
        scored.sort(reverse=True)
        return [chunk for _, _, _, chunk in scored[:top_k]]


class CrossEncoderReranker:
    def __init__(self, *, model_name: str) -> None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise ValueError(
                "sentence-transformers is required when RERANKER_PROVIDER=cross-encoder"
            ) from exc

        self.model = CrossEncoder(model_name)

    def rerank(self, *, question: str, chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
        pairs = [(question, chunk.content) for chunk in chunks]
        scores = self.model.predict(pairs)
        scored = [
            (
                float(score),
                chunk.score,
                -index,
                chunk,
            )
            for index, (score, chunk) in enumerate(zip(scores, chunks, strict=True))
        ]
        scored.sort(reverse=True)
        return [chunk for _, _, _, chunk in scored[:top_k]]


def create_reranker(settings: Settings) -> Reranker:
    match settings.reranker_provider:
        case "none":
            return NoOpReranker()
        case "local":
            return LocalLexicalReranker()
        case "cross-encoder":
            return CrossEncoderReranker(model_name=settings.reranker_model)
        case unsupported:
            raise ValueError(f"Unsupported RERANKER_PROVIDER '{unsupported}'")


def _lexical_score(question_terms: set[str], chunk: RetrievedChunk) -> float:
    haystack_terms = set(_terms(" ".join([chunk.title, chunk.content, chunk.source_uri or ""])))
    if not haystack_terms:
        return 0.0
    overlap = question_terms & haystack_terms
    return len(overlap) / len(question_terms)


def _terms(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())
