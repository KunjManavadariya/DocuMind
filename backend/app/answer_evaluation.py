from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol

from app.config import Settings
from app.schemas import EvalCase, RetrievedChunk


@dataclass(frozen=True)
class AnswerQualityScore:
    faithfulness: float
    answer_relevance: float


class AnswerQualityEvaluator(Protocol):
    def score(
        self,
        *,
        case: EvalCase,
        answer: str,
        chunks: list[RetrievedChunk],
    ) -> AnswerQualityScore:
        ...


class LocalAnswerQualityEvaluator:
    """Deterministic answer-quality evaluator for offline development and tests."""

    def score(
        self,
        *,
        case: EvalCase,
        answer: str,
        chunks: list[RetrievedChunk],
    ) -> AnswerQualityScore:
        return evaluate_answer_quality(case=case, answer=answer, chunks=chunks)


class RagasAnswerQualityEvaluator:
    def __init__(
        self,
        *,
        api_key: str,
        llm_model: str,
        embedding_model: str,
    ) -> None:
        try:
            from google import genai
            from ragas.embeddings import GoogleEmbeddings
            from ragas.llms import llm_factory
            from ragas.metrics.collections import AnswerRelevancy, Faithfulness
        except ImportError as exc:
            raise RuntimeError(
                "RAGAS evaluation requires ragas and google-genai to be installed."
            ) from exc

        client = genai.Client(api_key=api_key)
        llm = llm_factory(llm_model, provider="google", client=client)
        embeddings = GoogleEmbeddings(client=client, model=embedding_model)

        self.faithfulness = Faithfulness(llm=llm)
        self.answer_relevance = AnswerRelevancy(llm=llm, embeddings=embeddings)

    def score(
        self,
        *,
        case: EvalCase,
        answer: str,
        chunks: list[RetrievedChunk],
    ) -> AnswerQualityScore:
        contexts = [chunk.content for chunk in chunks]
        faithfulness = self.faithfulness.score(
            user_input=case.question,
            response=answer,
            retrieved_contexts=contexts,
        )
        answer_relevance = self.answer_relevance.score(
            user_input=case.question,
            response=answer,
        )

        return AnswerQualityScore(
            faithfulness=_bounded_score(_metric_value(faithfulness)),
            answer_relevance=_bounded_score(_metric_value(answer_relevance)),
        )


def create_answer_quality_evaluator(settings: Settings) -> AnswerQualityEvaluator:
    match settings.evaluation_provider:
        case "local":
            return LocalAnswerQualityEvaluator()
        case "ragas":
            if not settings.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is required when EVALUATION_PROVIDER=ragas")
            return RagasAnswerQualityEvaluator(
                api_key=settings.gemini_api_key,
                llm_model=settings.ragas_llm_model,
                embedding_model=settings.ragas_embedding_model,
            )
        case unsupported:
            raise ValueError(f"Unsupported EVALUATION_PROVIDER '{unsupported}'")


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "based",
    "be",
    "by",
    "does",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "use",
    "used",
    "what",
    "where",
    "which",
    "with",
}


def evaluate_answer_quality(
    *,
    case: EvalCase,
    answer: str,
    chunks: list[RetrievedChunk],
) -> AnswerQualityScore:
    context = _normalize(" ".join(chunk.content for chunk in chunks))
    answer_body = _answer_body(answer)

    return AnswerQualityScore(
        faithfulness=_score_faithfulness(answer_body=answer_body, context=context),
        answer_relevance=_score_answer_relevance(case=case, answer_body=answer_body),
    )


def _score_faithfulness(*, answer_body: str, context: str) -> float:
    if not answer_body:
        return 0.0
    if "could not find enough relevant documentation" in answer_body.lower():
        return 1.0
    if not context:
        return 0.0

    context_tokens = _keyword_tokens(context)
    claims = [
        claim
        for claim in re.split(r"(?<=[.!?])\s+", answer_body)
        if _keyword_tokens(claim)
    ]
    if not claims:
        return 0.0

    supported = 0
    for claim in claims:
        normalized_claim = _normalize(claim)
        claim_tokens = _keyword_tokens(claim)
        overlap = len(claim_tokens & context_tokens) / len(claim_tokens)
        if normalized_claim in context or overlap >= 0.9:
            supported += 1

    return round(supported / len(claims), 4)


def _score_answer_relevance(*, case: EvalCase, answer_body: str) -> float:
    answer_tokens = _keyword_tokens(answer_body)
    if not answer_tokens:
        return 0.0

    question_tokens = _keyword_tokens(case.question)
    question_score = (
        len(question_tokens & answer_tokens) / len(question_tokens)
        if question_tokens
        else 0.0
    )

    expected_terms = [term for term in case.expected_terms if term.strip()]
    expected_score = 0.0
    if expected_terms:
        normalized_answer = _normalize(answer_body)
        expected_matches = sum(
            1
            for term in expected_terms
            if _normalize(term) in normalized_answer
            or _keyword_tokens(term).issubset(answer_tokens)
        )
        expected_score = expected_matches / len(expected_terms)

    return round(max(question_score, expected_score), 4)


def _answer_body(answer: str) -> str:
    without_citations = re.sub(r"\[\d+\]", "", answer)
    without_prefix = re.sub(
        r"^based on the retrieved documentation for ['\"].+?['\"],\s*",
        "",
        without_citations.strip(),
        flags=re.IGNORECASE,
    )
    return _normalize(without_prefix)


def _keyword_tokens(value: str) -> set[str]:
    return {
        _stem(token)
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in STOP_WORDS
    }


def _stem(token: str) -> str:
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _metric_value(result: object) -> float:
    value = getattr(result, "value", result)
    if value is None:
        return 0.0
    return float(value)


def _bounded_score(value: float) -> float:
    return round(min(max(value, 0.0), 1.0), 4)
