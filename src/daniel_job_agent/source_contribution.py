"""Mede a contribuição marginal das fontes globais após o dedup existente."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Mapping, Protocol

from .pipeline import PipelineResult


GLOBAL_SOURCE_ORDER = (
    "jobicy",
    "remotive",
    "weworkremotely",
    "himalayas",
    "remoteok",
    "getonboard",
    "latamcent",
)


class SourceSummary(Protocol):
    """Parte do resumo de discovery necessária para calcular eficiência."""

    received: int
    converted: int

    @property
    def succeeded(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class SourceContribution:
    source_id: str
    status: str
    received: int
    converted: int
    requests: int
    unique_contributed: int | None
    unique_primary: int | None
    incremental_unique: int | None
    keep: int | None
    incremental_keep: int | None
    review: int | None
    incremental_review: int | None
    reject: int | None
    incremental_reject: int | None
    cross_source_duplicates: int | None
    overlap_count: int | None
    incremental_relevant: int | None
    requests_per_incremental_unique: float | None
    requests_per_incremental_relevant: float | None


@dataclass(frozen=True, slots=True)
class HimalayasDelta:
    baseline_unique: int
    expanded_unique: int
    incremental_unique: int
    baseline_keep: int
    expanded_keep: int
    incremental_keep: int
    baseline_relevant: int
    expanded_relevant: int
    incremental_relevant: int
    cross_source_duplicates: int


@dataclass(frozen=True, slots=True)
class SourceContributionResult:
    operational_order: tuple[str, ...]
    contributions: dict[str, SourceContribution]
    overlap_matrix: dict[tuple[str, str], int]
    himalayas_delta: HimalayasDelta | None


def _source_id(job: object) -> str:
    return str(getattr(job, "source_id", "") or getattr(job, "source", ""))


def _unavailable(
    source_id: str, summary: SourceSummary | None
) -> SourceContribution:
    return SourceContribution(
        source_id=source_id,
        status="FAILED",
        received=summary.received if summary else 0,
        converted=summary.converted if summary else 0,
        requests=1 if summary else 0,
        unique_contributed=None,
        unique_primary=None,
        incremental_unique=None,
        keep=None,
        incremental_keep=None,
        review=None,
        incremental_review=None,
        reject=None,
        incremental_reject=None,
        cross_source_duplicates=None,
        overlap_count=None,
        incremental_relevant=None,
        requests_per_incremental_unique=None,
        requests_per_incremental_relevant=None,
    )


def measure_source_contributions(
    pipeline: PipelineResult,
    source_summaries: Mapping[str, SourceSummary],
    *,
    operational_order: tuple[str, ...] = GLOBAL_SOURCE_ORDER,
) -> SourceContributionResult:
    """Atribui cada grupo à primeira fonte global que o observou.

    ``keep``, ``review`` e ``reject`` descrevem todos os grupos observados pela
    fonte. Os campos ``incremental_*`` creditam o grupo somente à primeira
    fonte na ordem operacional fixa. KEEP + REVIEW define ``relevant``.
    """

    rank = {source_id: index for index, source_id in enumerate(operational_order)}
    global_sources = set(operational_order)
    groups: dict[int, tuple[str, set[str]]] = {}
    for item in pipeline.ranked_opportunities:
        source_id = _source_id(item.original_job)
        sources = {source_id} & global_sources
        if sources:
            groups[id(item.original_job)] = (item.retention_decision.value, sources)
    for duplicate in pipeline.duplicate_records:
        group = groups.get(id(duplicate.primary))
        if group is not None:
            group[1].update({_source_id(duplicate.duplicate)} & global_sources)

    overlap_matrix = {
        pair: sum(pair[0] in sources and pair[1] in sources for _, sources in groups.values())
        for pair in combinations(operational_order, 2)
    }
    cross_duplicate_counts = {source_id: 0 for source_id in operational_order}
    for duplicate in pipeline.duplicate_records:
        primary = _source_id(duplicate.primary)
        repeated = _source_id(duplicate.duplicate)
        if (
            primary != repeated
            and primary in global_sources
            and repeated in global_sources
        ):
            if primary in cross_duplicate_counts:
                cross_duplicate_counts[primary] += 1
            if repeated in cross_duplicate_counts:
                cross_duplicate_counts[repeated] += 1

    contributions: dict[str, SourceContribution] = {}
    for source_id in operational_order:
        summary = source_summaries.get(source_id)
        if summary is None or not summary.succeeded:
            contributions[source_id] = _unavailable(source_id, summary)
            continue

        covered = [group for group in groups.values() if source_id in group[1]]
        incremental = [
            group for group in covered
            if min(group[1], key=rank.__getitem__) == source_id
        ]

        def decision_count(values: list[tuple[str, set[str]]], decision: str) -> int:
            return sum(item[0] == decision for item in values)

        incremental_unique = len(incremental)
        incremental_relevant = sum(
            item[0] in {"KEEP", "REVIEW"} for item in incremental
        )
        requests = 1
        contributions[source_id] = SourceContribution(
            source_id=source_id,
            status="SUCCESS",
            received=summary.received,
            converted=summary.converted,
            requests=requests,
            unique_contributed=len(covered),
            unique_primary=sum(
                _source_id(item.original_job) == source_id
                for item in pipeline.ranked_opportunities
            ),
            incremental_unique=incremental_unique,
            keep=decision_count(covered, "KEEP"),
            incremental_keep=decision_count(incremental, "KEEP"),
            review=decision_count(covered, "REVIEW"),
            incremental_review=decision_count(incremental, "REVIEW"),
            reject=decision_count(covered, "REJECT"),
            incremental_reject=decision_count(incremental, "REJECT"),
            cross_source_duplicates=cross_duplicate_counts[source_id],
            overlap_count=sum(len(group[1]) > 1 for group in covered),
            incremental_relevant=incremental_relevant,
            requests_per_incremental_unique=(
                requests / incremental_unique if incremental_unique else None
            ),
            requests_per_incremental_relevant=(
                requests / incremental_relevant if incremental_relevant else None
            ),
        )

    himalayas = contributions.get("himalayas")
    delta = None
    if himalayas is not None and himalayas.status == "SUCCESS":
        himalayas_index = operational_order.index("himalayas")
        baseline_sources = set(operational_order[:himalayas_index])
        baseline = [group for group in groups.values() if group[1] & baseline_sources]
        expanded_sources = baseline_sources | {"himalayas"}
        expanded = [group for group in groups.values() if group[1] & expanded_sources]

        def count(values: list[tuple[str, set[str]]], decision: str) -> int:
            return sum(item[0] == decision for item in values)

        def relevant(values: list[tuple[str, set[str]]]) -> int:
            return sum(item[0] in {"KEEP", "REVIEW"} for item in values)

        delta = HimalayasDelta(
            baseline_unique=len(baseline),
            expanded_unique=len(expanded),
            incremental_unique=len(expanded) - len(baseline),
            baseline_keep=count(baseline, "KEEP"),
            expanded_keep=count(expanded, "KEEP"),
            incremental_keep=count(expanded, "KEEP") - count(baseline, "KEEP"),
            baseline_relevant=relevant(baseline),
            expanded_relevant=relevant(expanded),
            incremental_relevant=relevant(expanded) - relevant(baseline),
            cross_source_duplicates=himalayas.cross_source_duplicates or 0,
        )
    return SourceContributionResult(
        operational_order=operational_order,
        contributions=contributions,
        overlap_matrix=overlap_matrix,
        himalayas_delta=delta,
    )
