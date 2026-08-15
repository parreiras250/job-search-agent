"""Estratégia controlada de discovery com poucas queries por fonte."""

from collections.abc import Callable
from dataclasses import dataclass

from .enrichment import enrich_opportunities
from .ingestion import (
    BatchIngestionResult,
    JobicyJobAdapter,
    RemotiveJobAdapter,
    ingest_batch,
)
from .models import CandidateProfile, JobOpportunity
from .pipeline import PipelineResult, ProcessedOpportunity, process_opportunities
from .sources import JobSource, JobicyJobSource, RemotiveJobSource, SourceResult

MAX_QUERIES_PER_SOURCE = 4


@dataclass(frozen=True, slots=True)
class JobicySearchQuery:
    name: str
    broad: bool
    geo: str = "latam"
    industry: str = "seller"
    count: int = 100
    tag: str | None = None

    @property
    def key(self) -> str:
        return f"jobicy:{self.name}"


@dataclass(frozen=True, slots=True)
class RemotiveSearchQuery:
    name: str
    broad: bool
    category: str | None = None
    search: str | None = None
    limit: int | None = None

    @property
    def key(self) -> str:
        return f"remotive:{self.name}"


@dataclass(frozen=True, slots=True)
class SearchStrategy:
    """Lista centralizada de queries e orçamento máximo de requests."""

    name: str
    jobicy_queries: tuple[JobicySearchQuery, ...]
    remotive_queries: tuple[RemotiveSearchQuery, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("strategy name cannot be empty")
        if len(self.jobicy_queries) > MAX_QUERIES_PER_SOURCE:
            raise ValueError("Jobicy strategy cannot exceed 4 queries")
        if len(self.remotive_queries) > MAX_QUERIES_PER_SOURCE:
            raise ValueError("Remotive strategy cannot exceed 4 queries")
        keys = [query.key for query in (*self.jobicy_queries, *self.remotive_queries)]
        if len(keys) != len(set(keys)):
            raise ValueError("query names must be unique within each source")

    @property
    def expected_requests(self) -> int:
        return len(self.jobicy_queries) + len(self.remotive_queries)


def create_full_search_strategy(
    *, jobicy_limit: int = 4, remotive_limit: int = 4
) -> SearchStrategy:
    """Cria a estratégia completa; limites menores preservam broad primeiro."""

    for name, limit in (("jobicy_limit", jobicy_limit), ("remotive_limit", remotive_limit)):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= 4:
            raise ValueError(f"{name} must be an integer between 0 and 4")
    jobicy = (
        JobicySearchQuery("broad_latam_sales", broad=True),
        JobicySearchQuery("account_executive", broad=False, tag="account executive"),
        JobicySearchQuery("business_development", broad=False, tag="business development"),
        JobicySearchQuery("sales_development", broad=False, tag="sales development"),
    )
    remotive = (
        RemotiveSearchQuery("broad_sales", broad=True, category="sales"),
        RemotiveSearchQuery("account_executive", broad=False, search="account executive"),
        RemotiveSearchQuery("business_development", broad=False, search="business development"),
        RemotiveSearchQuery("sales_development", broad=False, search="sales development"),
    )
    return SearchStrategy(
        name="Daniel full sales discovery",
        jobicy_queries=jobicy[:jobicy_limit],
        remotive_queries=remotive[:remotive_limit],
    )


def create_default_search_strategy() -> SearchStrategy:
    """Estratégia conservadora calibrada para executar somente as duas broad."""

    full = create_full_search_strategy()
    return SearchStrategy(
        name="Daniel broad sales baseline",
        jobicy_queries=full.jobicy_queries[:1],
        remotive_queries=full.remotive_queries[:1],
    )


def create_search_strategy(mode: str) -> SearchStrategy:
    """Seleciona somente os modos públicos broad e full."""

    normalized = mode.strip().casefold()
    if normalized == "broad":
        return create_default_search_strategy()
    if normalized == "full":
        return create_full_search_strategy()
    raise ValueError("mode must be 'broad' or 'full'")


@dataclass(frozen=True, slots=True)
class QueryDiscoverySummary:
    source: str
    query_name: str
    query_key: str
    broad: bool
    source_result: SourceResult
    ingestion: BatchIngestionResult | None
    received: int
    converted: int
    warnings: int
    errors: int
    failure_message: str | None


@dataclass(frozen=True, slots=True)
class QueryUsefulnessRule:
    """Critério ajustável que ignora volume bruto sem ganho marginal."""

    minimum_unique_gain: int = 1
    minimum_keep_gain: int = 1

    def is_useful(self, unique_gain: int, keep_gain: int) -> bool:
        return (
            unique_gain >= self.minimum_unique_gain
            or keep_gain >= self.minimum_keep_gain
        )


@dataclass(frozen=True, slots=True)
class QueryEfficiency:
    source: str
    query_name: str
    query_key: str
    broad: bool
    jobs_received: int
    jobs_converted: int
    unique_jobs_contributed: int
    duplicate_jobs: int
    keep_contributed: int
    review_contributed: int
    reject_contributed: int
    incremental_unique_gain: int
    incremental_keep_gain: int
    duplication_rate: float
    useful: bool


@dataclass(frozen=True, slots=True)
class StrategyRecommendation:
    """Sugestão em memória; nunca modifica a estratégia que foi executada."""

    current_requests: int
    recommended_strategy: SearchStrategy
    keep_query_keys: list[str]
    drop_query_keys: list[str]
    reasons: dict[str, str]


@dataclass(frozen=True, slots=True)
class MultiQueryDiscoveryResult:
    strategy: SearchStrategy
    query_summaries: list[QueryDiscoverySummary]
    query_efficiencies: list[QueryEfficiency]
    provenance_by_job_url: dict[str, list[str]]
    total_raw_results: int
    total_jobs_before_dedup: int
    unique_jobs: int
    duplicates: int
    intra_source_duplicates: int
    cross_source_duplicates: int
    duplication_rate: float
    keep_count: int
    review_count: int
    reject_count: int
    keep_rate: float
    useful_query_count: int
    wasted_query_count: int
    requests_per_unique_job: float | None
    requests_per_keep: float | None
    unique_jobs_by_source: dict[str, int]
    jobs_found_by_multiple_queries: int
    broad_unique_jobs: int
    broad_keep_count: int
    incremental_unique_gain: int
    incremental_keep_gain: int
    ranking: list[ProcessedOpportunity]
    pipeline: PipelineResult


class MultiQueryDiscovery:
    """Executa a estratégia sequencialmente e tolera falhas por query."""

    def __init__(
        self,
        strategy: SearchStrategy | None = None,
        *,
        jobicy_source_factory: Callable[[JobicySearchQuery], JobSource] | None = None,
        remotive_source_factory: Callable[[RemotiveSearchQuery], JobSource] | None = None,
        usefulness_rule: QueryUsefulnessRule | None = None,
    ) -> None:
        self.strategy = strategy or create_default_search_strategy()
        self.jobicy_source_factory = jobicy_source_factory or self._jobicy_source
        self.remotive_source_factory = remotive_source_factory or self._remotive_source
        self.usefulness_rule = usefulness_rule or QueryUsefulnessRule()

    @staticmethod
    def _jobicy_source(query: JobicySearchQuery) -> JobSource:
        return JobicyJobSource(
            geo=query.geo,
            industry=query.industry,
            count=query.count,
            tag=query.tag,
        )

    @staticmethod
    def _remotive_source(query: RemotiveSearchQuery) -> JobSource:
        return RemotiveJobSource(
            category=query.category,
            search=query.search,
            limit=query.limit,
        )

    def run(self, profile: CandidateProfile) -> MultiQueryDiscoveryResult:
        summaries: list[QueryDiscoverySummary] = []
        jobs_with_query: list[tuple[JobOpportunity, str, bool]] = []
        efficiencies: list[QueryEfficiency] = []
        previous_pipeline = process_opportunities([], profile)
        definitions = [
            ("Jobicy", query, self.jobicy_source_factory(query), JobicyJobAdapter())
            for query in self.strategy.jobicy_queries
        ] + [
            ("Remotive", query, self.remotive_source_factory(query), RemotiveJobAdapter())
            for query in self.strategy.remotive_queries
        ]

        for source_name, query, source, adapter in definitions:
            source_result = source.fetch()
            ingestion = (
                ingest_batch(source_result.records, adapter)
                if source_result.success
                else None
            )
            if ingestion is not None:
                query_jobs = enrich_opportunities(ingestion.opportunities)
                jobs_with_query.extend(
                    (job, query.key, query.broad) for job in query_jobs
                )
            summaries.append(
                QueryDiscoverySummary(
                    source=source_name,
                    query_name=query.name,
                    query_key=query.key,
                    broad=query.broad,
                    source_result=source_result,
                    ingestion=ingestion,
                    received=len(source_result.records),
                    converted=ingestion.converted_count if ingestion else 0,
                    warnings=ingestion.warning_count if ingestion else 0,
                    errors=ingestion.error_count if ingestion else 0,
                    failure_message=None if source_result.success else source_result.message,
                )
            )

            current_pipeline = process_opportunities(
                [item[0] for item in jobs_with_query], profile
            )
            unique_gain = (
                current_pipeline.unique_opportunities
                - previous_pipeline.unique_opportunities
            )
            keep_gain = current_pipeline.keep_count - previous_pipeline.keep_count
            review_gain = current_pipeline.review_count - previous_pipeline.review_count
            reject_gain = current_pipeline.reject_count - previous_pipeline.reject_count
            converted = ingestion.converted_count if ingestion else 0
            duplicate_jobs = max(0, converted - unique_gain)
            efficiencies.append(
                QueryEfficiency(
                    source=source_name,
                    query_name=query.name,
                    query_key=query.key,
                    broad=query.broad,
                    jobs_received=len(source_result.records),
                    jobs_converted=converted,
                    unique_jobs_contributed=unique_gain,
                    duplicate_jobs=duplicate_jobs,
                    keep_contributed=keep_gain,
                    review_contributed=review_gain,
                    reject_contributed=reject_gain,
                    incremental_unique_gain=unique_gain,
                    incremental_keep_gain=keep_gain,
                    duplication_rate=(duplicate_jobs / converted if converted else 0.0),
                    useful=self.usefulness_rule.is_useful(unique_gain, keep_gain),
                )
            )
            previous_pipeline = current_pipeline

        provenance_by_identity = {
            id(job): {query_key}
            for job, query_key, _ in jobs_with_query
        }
        broad_jobs = [
            job
            for job, _, broad in jobs_with_query
            if broad
        ]
        pipeline = previous_pipeline
        broad_pipeline = process_opportunities(broad_jobs, profile)
        for duplicate in pipeline.duplicate_records:
            provenance_by_identity[id(duplicate.primary)].update(
                provenance_by_identity[id(duplicate.duplicate)]
            )
        provenance = {
            item.normalized_job.job_url: sorted(
                provenance_by_identity[id(item.original_job)]
            )
            for item in pipeline.ranked_opportunities
        }
        intra_source = sum(
            duplicate.primary.source == duplicate.duplicate.source
            for duplicate in pipeline.duplicate_records
        )
        cross_source = pipeline.duplicates_detected - intra_source
        unique_by_source: dict[str, int] = {"Jobicy": 0, "Remotive": 0}
        for item in pipeline.ranked_opportunities:
            key = "Remotive" if item.normalized_job.source == "Remotive" else "Jobicy"
            unique_by_source[key] += 1
        total_before = pipeline.total_received
        return MultiQueryDiscoveryResult(
            strategy=self.strategy,
            query_summaries=summaries,
            query_efficiencies=efficiencies,
            provenance_by_job_url=provenance,
            total_raw_results=sum(summary.received for summary in summaries),
            total_jobs_before_dedup=total_before,
            unique_jobs=pipeline.unique_opportunities,
            duplicates=pipeline.duplicates_detected,
            intra_source_duplicates=intra_source,
            cross_source_duplicates=cross_source,
            duplication_rate=(pipeline.duplicates_detected / total_before if total_before else 0.0),
            keep_count=pipeline.keep_count,
            review_count=pipeline.review_count,
            reject_count=pipeline.reject_count,
            keep_rate=(pipeline.keep_count / pipeline.unique_opportunities if pipeline.unique_opportunities else 0.0),
            useful_query_count=sum(item.useful for item in efficiencies),
            wasted_query_count=sum(not item.useful for item in efficiencies),
            requests_per_unique_job=(
                self.strategy.expected_requests / pipeline.unique_opportunities
                if pipeline.unique_opportunities
                else None
            ),
            requests_per_keep=(
                self.strategy.expected_requests / pipeline.keep_count
                if pipeline.keep_count
                else None
            ),
            unique_jobs_by_source=unique_by_source,
            jobs_found_by_multiple_queries=sum(len(keys) > 1 for keys in provenance.values()),
            broad_unique_jobs=broad_pipeline.unique_opportunities,
            broad_keep_count=broad_pipeline.keep_count,
            incremental_unique_gain=pipeline.unique_opportunities - broad_pipeline.unique_opportunities,
            incremental_keep_gain=pipeline.keep_count - broad_pipeline.keep_count,
            ranking=pipeline.ranked_opportunities,
            pipeline=pipeline,
        )


def recommend_search_strategy(
    result: MultiQueryDiscoveryResult,
) -> StrategyRecommendation:
    """Mantém broad e targeted úteis somente como recomendação desta execução."""

    keep = {
        item.query_key
        for item in result.query_efficiencies
        if item.broad or item.useful
    }
    all_keys = [
        query.key
        for query in (
            *result.strategy.jobicy_queries,
            *result.strategy.remotive_queries,
        )
    ]
    keep_keys = [key for key in all_keys if key in keep]
    drop_keys = [key for key in all_keys if key not in keep]
    recommended = SearchStrategy(
        name=f"Recommended from {result.strategy.name}",
        jobicy_queries=tuple(
            query for query in result.strategy.jobicy_queries if query.key in keep
        ),
        remotive_queries=tuple(
            query for query in result.strategy.remotive_queries if query.key in keep
        ),
    )
    return StrategyRecommendation(
        current_requests=result.strategy.expected_requests,
        recommended_strategy=recommended,
        keep_query_keys=keep_keys,
        drop_query_keys=drop_keys,
        reasons={
            key: "zero incremental unique or KEEP gain in this run"
            for key in drop_keys
        },
    )


def format_query_efficiency_report(
    efficiencies: list[QueryEfficiency],
) -> str:
    """Formata ganho marginal sem imprimir vagas ou payloads extensos."""

    lines: list[str] = []
    current_source: str | None = None
    for item in efficiencies:
        if item.source != current_source:
            if lines:
                lines.append("")
            lines.append(item.source)
            current_source = item.source
        lines.extend(
            [
                f"- {item.query_name}",
                f"  received: {item.jobs_received}",
                f"  incremental unique: +{item.incremental_unique_gain}",
                f"  incremental KEEP: +{item.incremental_keep_gain}",
                f"  duplicates: {item.duplicate_jobs}",
                f"  useful: {'YES' if item.useful else 'NO'}",
            ]
        )
    return "\n".join(lines)
