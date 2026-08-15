"""Discovery amplo combinando uma consulta Jobicy e uma Remotive."""

from dataclasses import dataclass

from .enrichment import enrich_opportunities
from .ingestion import (
    BatchIngestionResult,
    JobicyJobAdapter,
    RemotiveJobAdapter,
    ingest_batch,
)
from .pipeline import PipelineResult, ProcessedOpportunity, process_opportunities
from .models import CandidateProfile
from .sources import (
    JobSource,
    JobicyJobSource,
    RemotiveJobSource,
    SourceResult,
)


@dataclass(frozen=True, slots=True)
class JobicyDiscoveryConfig:
    """Parâmetros da única consulta Jobicy desta etapa."""

    geo: str = "latam"
    industry: str = "seller"
    count: int = 100
    tag: str | None = None


@dataclass(frozen=True, slots=True)
class RemotiveDiscoveryConfig:
    """Parâmetros da única consulta Remotive desta etapa."""

    category: str = "sales"
    company_name: str | None = None
    search: str | None = None
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class SourceDiscoverySummary:
    """Resultado auditável de uma fonte antes da combinação global."""

    source: str
    source_result: SourceResult
    ingestion: BatchIngestionResult | None
    received: int
    converted: int
    warnings: int
    errors: int
    failure_message: str | None

    @property
    def succeeded(self) -> bool:
        return self.source_result.success


@dataclass(frozen=True, slots=True)
class MultiSourceDiscoveryResult:
    """Contagens por fonte e resultado único do pipeline global."""

    source_summaries: dict[str, SourceDiscoverySummary]
    sources_attempted: list[str]
    sources_succeeded: list[str]
    sources_failed: list[str]
    source_failure_messages: dict[str, str]
    jobs_received_by_source: dict[str, int]
    jobs_converted_by_source: dict[str, int]
    warnings_by_source: dict[str, int]
    errors_by_source: dict[str, int]
    total_jobs_before_global_dedup: int
    global_unique_jobs: int
    global_duplicates: int
    cross_source_duplicates: int
    keep_count: int
    review_count: int
    reject_count: int
    ranking: list[ProcessedOpportunity]
    pipeline: PipelineResult


class MultiSourceDiscovery:
    """Executa uma Jobicy e uma Remotive, com falhas isoladas por fonte."""

    def __init__(
        self,
        *,
        jobicy_config: JobicyDiscoveryConfig | None = None,
        remotive_config: RemotiveDiscoveryConfig | None = None,
        jobicy_source: JobSource | None = None,
        remotive_source: JobSource | None = None,
    ) -> None:
        self.jobicy_config = jobicy_config or JobicyDiscoveryConfig()
        self.remotive_config = remotive_config or RemotiveDiscoveryConfig()
        self.jobicy_source = jobicy_source or JobicyJobSource(
            geo=self.jobicy_config.geo,
            industry=self.jobicy_config.industry,
            count=self.jobicy_config.count,
            tag=self.jobicy_config.tag,
        )
        self.remotive_source = remotive_source or RemotiveJobSource(
            category=self.remotive_config.category,
            company_name=self.remotive_config.company_name,
            search=self.remotive_config.search,
            limit=self.remotive_config.limit,
        )

    def run(self, profile: CandidateProfile) -> MultiSourceDiscoveryResult:
        """Consulta as duas fontes e processa juntas somente as vagas válidas."""

        definitions = (
            ("Jobicy", self.jobicy_source, JobicyJobAdapter()),
            ("Remotive", self.remotive_source, RemotiveJobAdapter()),
        )
        summaries: dict[str, SourceDiscoverySummary] = {}
        combined_jobs = []

        for name, source, adapter in definitions:
            source_result = source.fetch()
            ingestion = (
                ingest_batch(source_result.records, adapter)
                if source_result.success
                else None
            )
            if ingestion is not None:
                combined_jobs.extend(ingestion.opportunities)
            summaries[name] = SourceDiscoverySummary(
                source=name,
                source_result=source_result,
                ingestion=ingestion,
                received=len(source_result.records),
                converted=ingestion.converted_count if ingestion else 0,
                warnings=ingestion.warning_count if ingestion else 0,
                errors=ingestion.error_count if ingestion else 0,
                failure_message=(None if source_result.success else source_result.message),
            )

        enriched_jobs = enrich_opportunities(combined_jobs)
        pipeline = process_opportunities(enriched_jobs, profile)
        attempted = list(summaries)
        succeeded = [name for name, item in summaries.items() if item.succeeded]
        failed = [name for name, item in summaries.items() if not item.succeeded]
        cross_source_duplicates = sum(
            record.duplicate.source != record.primary.source
            for record in pipeline.duplicate_records
        )
        return MultiSourceDiscoveryResult(
            source_summaries=summaries,
            sources_attempted=attempted,
            sources_succeeded=succeeded,
            sources_failed=failed,
            source_failure_messages={
                name: item.failure_message or "Unknown source error"
                for name, item in summaries.items()
                if not item.succeeded
            },
            jobs_received_by_source={
                name: item.received for name, item in summaries.items()
            },
            jobs_converted_by_source={
                name: item.converted for name, item in summaries.items()
            },
            warnings_by_source={
                name: item.warnings for name, item in summaries.items()
            },
            errors_by_source={name: item.errors for name, item in summaries.items()},
            total_jobs_before_global_dedup=pipeline.total_received,
            global_unique_jobs=pipeline.unique_opportunities,
            global_duplicates=pipeline.duplicates_detected,
            cross_source_duplicates=cross_source_duplicates,
            keep_count=pipeline.keep_count,
            review_count=pipeline.review_count,
            reject_count=pipeline.reject_count,
            ranking=pipeline.ranked_opportunities,
            pipeline=pipeline,
        )
