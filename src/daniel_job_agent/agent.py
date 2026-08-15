"""Orquestra discovery, pipeline e persistência sem duplicar suas regras."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .discovery import (
    JobicyDiscoveryConfig,
    MultiSourceDiscovery,
    MultiSourceDiscoveryResult,
    RemotiveDiscoveryConfig,
)
from .models import CandidateProfile
from .pipeline import ProcessedOpportunity
from .profiles import create_daniel_profile
from .repository import JobRepository, SyncResult, sync_opportunities
from .rules import RetentionDecision
from .search_strategy import SearchStrategy, create_default_search_strategy


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_broad_discovery(strategy: SearchStrategy | None = None) -> MultiSourceDiscovery:
    """Cria o discovery real a partir da estratégia broad centralizada."""

    selected = strategy or create_default_search_strategy()
    if len(selected.jobicy_queries) != 1 or len(selected.remotive_queries) != 1:
        raise ValueError("Multi-source agent requires one query per source")
    jobicy = selected.jobicy_queries[0]
    remotive = selected.remotive_queries[0]
    return MultiSourceDiscovery(
        jobicy_config=JobicyDiscoveryConfig(
            geo=jobicy.geo,
            industry=jobicy.industry,
            count=jobicy.count,
            tag=jobicy.tag,
        ),
        remotive_config=RemotiveDiscoveryConfig(
            category=remotive.category or "sales",
            search=remotive.search,
            limit=remotive.limit,
        ),
    )


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    """Resumo completo e inspecionável de uma execução do agente."""

    sources_attempted: list[str]
    sources_succeeded: list[str]
    sources_failed: list[str]
    jobs_received: int
    jobs_converted: int
    unique_opportunities: int
    discovery_duplicates: int
    keep: int
    review: int
    reject: int
    new: int
    existing: int
    updated: int
    persistence_errors: int
    total_stored: int
    started_at: datetime
    finished_at: datetime
    database_path: str
    top_new_opportunities: list[ProcessedOpportunity]
    discovery: MultiSourceDiscoveryResult
    persistence: SyncResult

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()


class DanielJobAgent:
    """Coordena uma execução; cada componente mantém sua responsabilidade."""

    def __init__(
        self,
        repository: JobRepository,
        *,
        discovery: MultiSourceDiscovery | None = None,
        profile: CandidateProfile | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.repository = repository
        self.discovery = discovery or create_broad_discovery()
        self.profile = profile or create_daniel_profile()
        self.clock = clock

    def run(self) -> AgentRunResult:
        started_at = self.clock()
        discovery_result = self.discovery.run(self.profile)
        persistence_time = self.clock()
        persistence_result = sync_opportunities(
            discovery_result.pipeline,
            self.repository,
            now=persistence_time,
        )
        finished_at = self.clock()

        new_job_ids = {id(item.opportunity) for item in persistence_result.new_jobs}
        new_processed = [
            item
            for item in discovery_result.ranking
            if id(item.original_job) in new_job_ids
            and item.retention_decision is not RetentionDecision.REJECT
        ]
        decision_order = {
            RetentionDecision.KEEP: 0,
            RetentionDecision.REVIEW: 1,
        }
        top_new = sorted(
            new_processed,
            key=lambda item: (decision_order[item.retention_decision], item.rank or 0),
        )[:10]

        return AgentRunResult(
            sources_attempted=discovery_result.sources_attempted,
            sources_succeeded=discovery_result.sources_succeeded,
            sources_failed=discovery_result.sources_failed,
            jobs_received=sum(discovery_result.jobs_received_by_source.values()),
            jobs_converted=sum(discovery_result.jobs_converted_by_source.values()),
            unique_opportunities=discovery_result.global_unique_jobs,
            discovery_duplicates=discovery_result.global_duplicates,
            keep=discovery_result.keep_count,
            review=discovery_result.review_count,
            reject=discovery_result.reject_count,
            new=persistence_result.new,
            existing=persistence_result.existing,
            updated=persistence_result.updated,
            persistence_errors=persistence_result.errors,
            total_stored=persistence_result.total_stored,
            started_at=started_at,
            finished_at=finished_at,
            database_path=self.repository.database_path,
            top_new_opportunities=top_new,
            discovery=discovery_result,
            persistence=persistence_result,
        )
