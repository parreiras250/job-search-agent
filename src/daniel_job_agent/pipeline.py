"""Pipeline local para deduplicar, avaliar e ordenar oportunidades."""

from dataclasses import dataclass, replace
from typing import Iterable

from .models import CandidateProfile, JobOpportunity
from .rules import (
    MatchEvaluation,
    RetentionDecision,
    are_probably_duplicates,
    decide_retention,
    evaluate_match,
    normalize_company,
    normalize_location,
    normalize_role,
)


@dataclass(frozen=True, slots=True)
class DuplicateRecord:
    """Registra uma duplicata e a oportunidade principal preservada."""

    duplicate: JobOpportunity
    primary: JobOpportunity


@dataclass(frozen=True, slots=True)
class ProcessedOpportunity:
    """Resultado completo e explicável de uma oportunidade única."""

    original_job: JobOpportunity
    normalized_job: JobOpportunity
    match_score: int
    positive_reasons: list[str]
    potential_gaps: list[str]
    unknowns: list[str]
    retention_decision: RetentionDecision
    rank: int | None = None


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Resumo agregado e resultados inspecionáveis do pipeline."""

    total_received: int
    unique_opportunities: int
    duplicates_detected: int
    keep_count: int
    review_count: int
    reject_count: int
    ranked_opportunities: list[ProcessedOpportunity]
    duplicate_records: list[DuplicateRecord]

    @property
    def keep(self) -> list[ProcessedOpportunity]:
        return self._with_decision(RetentionDecision.KEEP)

    @property
    def review(self) -> list[ProcessedOpportunity]:
        return self._with_decision(RetentionDecision.REVIEW)

    @property
    def reject(self) -> list[ProcessedOpportunity]:
        return self._with_decision(RetentionDecision.REJECT)

    def _with_decision(
        self, decision: RetentionDecision
    ) -> list[ProcessedOpportunity]:
        return [
            item
            for item in self.ranked_opportunities
            if item.retention_decision is decision
        ]


def _normalized_copy(job: JobOpportunity) -> JobOpportunity:
    """Cria uma cópia para processamento sem modificar a vaga recebida."""

    return replace(
        job,
        company=normalize_company(job.company),
        role=normalize_role(job.role),
        location=normalize_location(job.location),
    )


def _find_duplicate(
    candidate: JobOpportunity, unique_jobs: list[JobOpportunity]
) -> JobOpportunity | None:
    """Retorna o primeiro registro principal equivalente, se existir."""

    for primary in unique_jobs:
        if are_probably_duplicates(primary, candidate):
            return primary
    return None


_DECISION_ORDER = {
    RetentionDecision.KEEP: 0,
    RetentionDecision.REVIEW: 1,
    RetentionDecision.REJECT: 2,
}


def _ranking_key(item: ProcessedOpportunity) -> tuple[object, ...]:
    """Ordena por score, decisão e identificadores estáveis da vaga."""

    return (
        -item.match_score,
        _DECISION_ORDER[item.retention_decision],
        item.normalized_job.company.casefold(),
        item.normalized_job.role.casefold(),
        item.normalized_job.job_url.casefold(),
    )


def process_opportunities(
    jobs: Iterable[JobOpportunity], profile: CandidateProfile
) -> PipelineResult:
    """Executa normalização, deduplicação, avaliação, retenção e ranking."""

    received_jobs = list(jobs)
    unique_originals: list[JobOpportunity] = []
    unique_normalized: list[JobOpportunity] = []
    duplicate_records: list[DuplicateRecord] = []

    for original in received_jobs:
        normalized = _normalized_copy(original)
        duplicate_primary = _find_duplicate(normalized, unique_normalized)
        if duplicate_primary is not None:
            primary_index = unique_normalized.index(duplicate_primary)
            duplicate_records.append(
                DuplicateRecord(
                    duplicate=original,
                    primary=unique_originals[primary_index],
                )
            )
            continue
        unique_originals.append(original)
        unique_normalized.append(normalized)

    processed: list[ProcessedOpportunity] = []
    for original, normalized in zip(unique_originals, unique_normalized):
        evaluation: MatchEvaluation = evaluate_match(normalized, profile)
        decision = decide_retention(normalized, profile)
        processed.append(
            ProcessedOpportunity(
                original_job=original,
                normalized_job=normalized,
                match_score=evaluation.score,
                positive_reasons=evaluation.positive_reasons,
                potential_gaps=evaluation.potential_gaps,
                unknowns=evaluation.unknowns,
                retention_decision=decision,
            )
        )

    ranked = [
        replace(item, rank=position)
        for position, item in enumerate(sorted(processed, key=_ranking_key), start=1)
    ]
    counts = {
        decision: sum(item.retention_decision is decision for item in ranked)
        for decision in RetentionDecision
    }
    return PipelineResult(
        total_received=len(received_jobs),
        unique_opportunities=len(unique_originals),
        duplicates_detected=len(duplicate_records),
        keep_count=counts[RetentionDecision.KEEP],
        review_count=counts[RetentionDecision.REVIEW],
        reject_count=counts[RetentionDecision.REJECT],
        ranked_opportunities=ranked,
        duplicate_records=duplicate_records,
    )
