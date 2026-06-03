from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from google import genai
from google.genai import types

from app.config import Settings
from app.schemas import RetrievedChunk, SourceCitation


@dataclass(frozen=True)
class GeneratedAnswer:
    answer: str
    citations: list[SourceCitation]


class AnswerGenerator(Protocol):
    def generate(self, *, question: str, chunks: list[RetrievedChunk]) -> GeneratedAnswer:
        ...


class LocalGroundedAnswerGenerator:
    """Deterministic cited answer generator for offline development and tests."""

    def generate(self, *, question: str, chunks: list[RetrievedChunk]) -> GeneratedAnswer:
        if not chunks:
            return GeneratedAnswer(
                answer=(
                    "I could not find enough relevant documentation to answer this question "
                    "with citations."
                ),
                citations=[],
            )

        cited_sentences: list[str] = []
        citations: list[SourceCitation] = []

        for index, chunk in enumerate(chunks[:3], start=1):
            marker = f"[{index}]"
            cited_sentences.append(f"{_compact(chunk.content)} {marker}")
            citations.append(
                SourceCitation(
                    marker=marker,
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    title=chunk.title,
                    source_uri=chunk.source_uri,
                    chunk_index=chunk.chunk_index,
                    score=chunk.score,
                )
            )

        answer = (
            f"Based on the retrieved documentation for '{question}', "
            + " ".join(cited_sentences)
        )
        return GeneratedAnswer(answer=answer, citations=citations)


class GeminiAnswerGenerator:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        temperature: float = 0.2,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.client = genai.Client(api_key=api_key)

    def generate(self, *, question: str, chunks: list[RetrievedChunk]) -> GeneratedAnswer:
        citations = [
            SourceCitation(
                marker=f"[{index}]",
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                title=chunk.title,
                source_uri=chunk.source_uri,
                chunk_index=chunk.chunk_index,
                score=chunk.score,
            )
            for index, chunk in enumerate(chunks, start=1)
        ]
        if not chunks:
            return GeneratedAnswer(
                answer=(
                    "I could not find enough relevant documentation to answer this question "
                    "with citations."
                ),
                citations=[],
            )

        prompt = build_grounded_prompt(question=question, chunks=chunks)
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=self.temperature,
            ),
        )

        answer = (response.text or "").strip()
        if not answer:
            answer = "I could not generate an answer from the retrieved documentation."

        return GeneratedAnswer(answer=answer, citations=citations)


def create_answer_generator(settings: Settings) -> AnswerGenerator:
    match settings.generation_provider:
        case "local":
            return LocalGroundedAnswerGenerator()
        case "gemini":
            if not settings.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is required when GENERATION_PROVIDER=gemini")
            return GeminiAnswerGenerator(
                api_key=settings.gemini_api_key,
                model=settings.gemini_generation_model,
                temperature=settings.gemini_temperature,
            )
        case unsupported:
            raise ValueError(f"Unsupported GENERATION_PROVIDER '{unsupported}'")


def build_grounded_prompt(*, question: str, chunks: list[RetrievedChunk]) -> str:
    context_blocks = "\n\n".join(
        f"[{index}] {chunk.title} chunk {chunk.chunk_index}\n{chunk.content}"
        for index, chunk in enumerate(chunks, start=1)
    )
    return (
        "You are DocuMind, a documentation assistant. Answer only from the provided "
        "context. If the context is insufficient, say so. Use inline citation markers "
        "like [1] that correspond to the context blocks.\n\n"
        f"Question:\n{question}\n\n"
        f"Context:\n{context_blocks}"
    )


def _compact(text: str, max_length: int = 240) -> str:
    compacted = " ".join(text.split())
    if len(compacted) <= max_length:
        return compacted
    return compacted[: max_length - 3].rstrip() + "..."
