from __future__ import annotations

from collections.abc import Callable, Iterable
import re

from app.answer_evaluation import AnswerQualityEvaluator, LocalAnswerQualityEvaluator
from app.generation import GeneratedAnswer
from app.schemas import EvalCase, EvalCaseResult, EvalConfig, EvalRunResult, RetrievedChunk

RetrieveFn = Callable[[str, int], list[RetrievedChunk]]
AnswerFn = Callable[[str, list[RetrievedChunk]], GeneratedAnswer]


def evaluate_configs(
    *,
    cases: list[EvalCase],
    configs: list[EvalConfig],
    retrieve_fn: RetrieveFn,
    answer_fn: AnswerFn | None = None,
    answer_quality_evaluator: AnswerQualityEvaluator | None = None,
) -> list[EvalRunResult]:
    return [
        evaluate_config(
            cases=cases,
            config=config,
            retrieve_fn=retrieve_fn,
            answer_fn=answer_fn,
            answer_quality_evaluator=answer_quality_evaluator,
        )
        for config in configs
    ]


def evaluate_config(
    *,
    cases: list[EvalCase],
    config: EvalConfig,
    retrieve_fn: RetrieveFn,
    answer_fn: AnswerFn | None = None,
    answer_quality_evaluator: AnswerQualityEvaluator | None = None,
) -> EvalRunResult:
    case_results = [
        evaluate_case(
            case=case,
            chunks=retrieve_fn(case.question, config.top_k),
            answer_fn=answer_fn,
            answer_quality_evaluator=answer_quality_evaluator,
        )
        for case in cases
    ]

    total = len(case_results) or 1
    return EvalRunResult(
        config=config,
        case_results=case_results,
        recall_at_k=sum(result.recall_at_k for result in case_results) / total,
        mean_reciprocal_rank=sum(result.reciprocal_rank for result in case_results) / total,
        mean_context_precision=sum(result.context_precision for result in case_results) / total,
        mean_faithfulness=_mean_optional(
            result.faithfulness for result in case_results
        ),
        mean_answer_relevance=_mean_optional(
            result.answer_relevance for result in case_results
        ),
    )


def evaluate_case(
    *,
    case: EvalCase,
    chunks: list[RetrievedChunk],
    answer_fn: AnswerFn | None = None,
    answer_quality_evaluator: AnswerQualityEvaluator | None = None,
) -> EvalCaseResult:
    expected_terms = [_normalize(term) for term in case.expected_terms if term.strip()]
    matched_terms: set[str] = set()
    first_match_rank = None
    matching_chunk_count = 0
    answer = None
    faithfulness = None
    answer_relevance = None

    for index, chunk in enumerate(chunks, start=1):
        haystack = _normalize(
            " ".join(
                [
                    chunk.title,
                    chunk.content,
                    chunk.source_uri or "",
                ]
            )
        )
        term_matches = {
            term for term in expected_terms if term and term in haystack
        }
        source_matches = bool(case.expected_source_uri and case.expected_source_uri == chunk.source_uri)

        if term_matches or source_matches:
            matching_chunk_count += 1
            matched_terms.update(term_matches)
            if first_match_rank is None:
                first_match_rank = index

    matched = _is_case_matched(
        case=case,
        expected_terms=expected_terms,
        matched_terms=matched_terms,
        first_match_rank=first_match_rank,
    )
    reciprocal_rank = 0.0 if first_match_rank is None else 1.0 / first_match_rank
    context_precision = 0.0 if not chunks else matching_chunk_count / len(chunks)

    if answer_fn:
        generated = answer_fn(case.question, chunks)
        evaluator = answer_quality_evaluator or LocalAnswerQualityEvaluator()
        quality = evaluator.score(
            case=case,
            answer=generated.answer,
            chunks=chunks,
        )
        answer = generated.answer
        faithfulness = quality.faithfulness
        answer_relevance = quality.answer_relevance

    return EvalCaseResult(
        case_id=case.id,
        question=case.question,
        matched=matched,
        recall_at_k=1.0 if matched else 0.0,
        reciprocal_rank=reciprocal_rank,
        context_precision=context_precision,
        faithfulness=faithfulness,
        answer_relevance=answer_relevance,
        first_match_rank=first_match_rank,
        matched_terms=sorted(matched_terms),
        retrieved_sources=[chunk.source_uri for chunk in chunks],
        answer=answer,
    )


def _is_case_matched(
    *,
    case: EvalCase,
    expected_terms: list[str],
    matched_terms: set[str],
    first_match_rank: int | None,
) -> bool:
    if case.expected_source_uri and first_match_rank is not None:
        return True
    if expected_terms:
        return set(expected_terms).issubset(matched_terms)
    return first_match_rank is not None


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _mean_optional(values: Iterable[float | None]) -> float | None:
    scores = [value for value in values if value is not None]
    if not scores:
        return None
    return sum(scores) / len(scores)
