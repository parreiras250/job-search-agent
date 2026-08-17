"""Discovery genérico sobre as fontes habilitadas em um SourceRegistry."""

from dataclasses import dataclass

from .enrichment import enrich_opportunities
from .ingestion import BatchIngestionResult, ingest_batch
from .pipeline import PipelineResult, ProcessedOpportunity, process_opportunities
from .models import CandidateProfile
from .source_registry import SourceRegistry, create_default_source_registry
from .source_contribution import (
    SourceContributionResult,
    measure_source_contributions,
)
from .sources import JobSource, SourceResult


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
    source_id: str = ""
    source_family: str = ""
    source_instance: str = ""

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
    source_executions_by_id: dict[str, SourceDiscoverySummary]
    source_contributions: SourceContributionResult


class MultiSourceDiscovery:
    """Executa N definições habilitadas, com falhas isoladas por source_id."""

    def __init__(
        self,
        *,
        jobicy_config: JobicyDiscoveryConfig | None = None,
        remotive_config: RemotiveDiscoveryConfig | None = None,
        jobicy_source: JobSource | None = None,
        remotive_source: JobSource | None = None,
        wwr_source: JobSource | None = None,
        himalayas_source: JobSource | None = None,
        registry: SourceRegistry | None = None,
    ) -> None:
        self.jobicy_config = jobicy_config or JobicyDiscoveryConfig()
        self.remotive_config = remotive_config or RemotiveDiscoveryConfig()
        self.registry = registry or create_default_source_registry(
            jobicy_config={
                "geo": self.jobicy_config.geo,
                "industry": self.jobicy_config.industry,
                "count": self.jobicy_config.count,
                "tag": self.jobicy_config.tag,
            },
            remotive_config={
                "category": self.remotive_config.category,
                "company_name": self.remotive_config.company_name,
                "search": self.remotive_config.search,
                "limit": self.remotive_config.limit,
            },
            jobicy_source=jobicy_source,
            remotive_source=remotive_source,
            wwr_source=wwr_source,
            himalayas_source=himalayas_source,
        )
        # Compatibilidade de inspeção para código/testes anteriores.
        self._source_instances = {
            definition.source_id: definition.source_factory()
            for definition in self.registry.enabled_sources()
        }
        self.jobicy_source = self._source_instances.get("jobicy")
        self.remotive_source = self._source_instances.get("remotive")
        self.wwr_source = self._source_instances.get("weworkremotely")
        self.himalayas_source = self._source_instances.get("himalayas")

    def run(self, profile: CandidateProfile) -> MultiSourceDiscoveryResult:
        """Consulta N fontes habilitadas e processa juntas somente vagas válidas."""

        summaries: dict[str, SourceDiscoverySummary] = {}
        executions_by_id: dict[str, SourceDiscoverySummary] = {}
        combined_jobs = []

        for definition in self.registry.enabled_sources():
            name = definition.display_name
            source = self._source_instances[definition.source_id]
            adapter = definition.adapter_factory()
            source_result = source.fetch()
            ingestion = (
                ingest_batch(source_result.records, adapter)
                if source_result.success
                else None
            )
            if ingestion is not None:
                for opportunity in ingestion.opportunities:
                    opportunity.source_id = definition.source_id
                    opportunity.source_family = definition.source_family
                    opportunity.source_instance = definition.source_instance
                    opportunity.source_type = definition.source_type.value
                    opportunity.lifecycle_authority = (
                        definition.capabilities.lifecycle_authority.value
                    )
                combined_jobs.extend(ingestion.opportunities)
            summary = SourceDiscoverySummary(
                source=name,
                source_result=source_result,
                ingestion=ingestion,
                received=len(source_result.records),
                converted=ingestion.converted_count if ingestion else 0,
                warnings=ingestion.warning_count if ingestion else 0,
                errors=ingestion.error_count if ingestion else 0,
                failure_message=(None if source_result.success else source_result.message),
                source_id=definition.source_id,
                source_family=definition.source_family,
                source_instance=definition.source_instance,
            )
            summaries[name] = summary
            executions_by_id[definition.source_id] = summary

        enriched_jobs = enrich_opportunities(combined_jobs)
        pipeline = process_opportunities(enriched_jobs, profile)
        source_contributions = measure_source_contributions(
            pipeline, executions_by_id
        )
        attempted = list(summaries)
        succeeded = [name for name, item in summaries.items() if item.succeeded]
        failed = [name for name, item in summaries.items() if not item.succeeded]
        cross_source_duplicates = sum(
            (
                record.duplicate.source_instance or record.duplicate.source
            ) != (
                record.primary.source_instance or record.primary.source
            )
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
            source_executions_by_id=executions_by_id,
            source_contributions=source_contributions,
        )
