"""Registry persistente de empresas e geração segura de tenant sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping, TYPE_CHECKING

from .models import (
    CompanyRecord,
    DIRECT_EMPLOYER,
    RECRUITING_PUBLISHER,
)
from .repository import JobRepository
from .source_registry import (
    AshbyTenantConfig,
    GreenhouseTenantConfig,
    SourceDefinition,
    SourceRegistry,
    create_ashby_definitions,
    create_default_source_registry,
    create_greenhouse_pilot_definitions,
)
from .sources import JobSource

if TYPE_CHECKING:
    from .discovery import MultiSourceDiscoveryResult


DEFAULT_MAX_ENABLED_TENANTS = 25
SUPPORTED_ATS_FAMILIES = frozenset({"greenhouse", "ashby"})

ASHBY_WAVE1_SEED = (
    ("latamcent", "LatamCent", "latamcent", RECRUITING_PUBLISHER),
    ("elevenlabs", "ElevenLabs", "elevenlabs", DIRECT_EMPLOYER),
    ("replit", "Replit", "replit", DIRECT_EMPLOYER),
)


@dataclass(frozen=True, slots=True)
class CompanyRegistrySnapshot:
    tracked: int
    enabled: int
    executable: list[CompanyRecord]
    unsupported: list[CompanyRecord]
    limited: list[CompanyRecord]


@dataclass(frozen=True, slots=True)
class CompanyMonitoringSummary:
    tracked: int = 0
    enabled: int = 0
    executed: int = 0
    succeeded: int = 0
    failed: int = 0
    unsupported: int = 0
    limited: int = 0
    top_failures: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CompanySeedResult:
    created: list[str]
    preserved: list[str]


def seed_ashby_wave1(repository: JobRepository) -> CompanySeedResult:
    """Insere somente tenants ausentes; nunca sobrescreve configuração local."""

    created: list[str] = []
    preserved: list[str] = []
    for company_key, company_name, identifier, publisher_model in ASHBY_WAVE1_SEED:
        if repository.get_company(company_key) is not None:
            preserved.append(company_key)
            continue
        repository.add_company(
            company_key,
            company_name,
            "ashby",
            identifier,
            publisher_model=publisher_model,
        )
        created.append(company_key)
    return CompanySeedResult(created=created, preserved=preserved)


class CompanyRegistry:
    """Carrega companies do SQLite e converte apenas tenants suportados."""

    def __init__(
        self,
        repository: JobRepository,
        *,
        max_enabled_tenants: int = DEFAULT_MAX_ENABLED_TENANTS,
    ) -> None:
        if max_enabled_tenants < 1:
            raise ValueError("max_enabled_tenants must be positive")
        self.repository = repository
        self.max_enabled_tenants = max_enabled_tenants

    def snapshot(self) -> CompanyRegistrySnapshot:
        companies = self.repository.list_companies()
        enabled = [company for company in companies if company.enabled]
        supported = [
            company for company in enabled
            if company.ats_family in SUPPORTED_ATS_FAMILIES
        ]
        return CompanyRegistrySnapshot(
            tracked=len(companies),
            enabled=len(enabled),
            executable=supported[: self.max_enabled_tenants],
            unsupported=[
                company for company in enabled
                if company.ats_family not in SUPPORTED_ATS_FAMILIES
            ],
            limited=supported[self.max_enabled_tenants :],
        )

    def source_definitions(
        self,
        *,
        source_overrides: Mapping[str, JobSource] | None = None,
    ) -> tuple[list[SourceDefinition], CompanyRegistrySnapshot]:
        snapshot = self.snapshot()
        definitions: list[SourceDefinition] = []
        for company in snapshot.executable:
            if company.ats_family == "greenhouse":
                definitions.extend(create_greenhouse_pilot_definitions(
                    (GreenhouseTenantConfig(
                        company_key=company.company_key,
                        company_name=company.company_name,
                        board_token=company.ats_identifier,
                        priority=company.priority,
                    ),),
                    source_overrides=source_overrides,
                    max_tenants=self.max_enabled_tenants,
                ))
            elif company.ats_family == "ashby":
                employer_name = (
                    company.company_name
                    if company.publisher_model == DIRECT_EMPLOYER else None
                )
                definitions.extend(create_ashby_definitions(
                    (AshbyTenantConfig(
                        tenant_key=company.company_key,
                        publisher_name=company.company_name,
                        board_name=company.ats_identifier,
                        employer_name=employer_name,
                        priority=company.priority,
                    ),),
                    source_overrides=source_overrides,
                ))
        return definitions, snapshot

    def build_source_registry(
        self,
        *,
        base_registry: SourceRegistry | None = None,
        source_overrides: Mapping[str, JobSource] | None = None,
    ) -> tuple[SourceRegistry, CompanyRegistrySnapshot]:
        base = base_registry or create_default_source_registry()
        definitions, snapshot = self.source_definitions(
            source_overrides=source_overrides
        )
        return SourceRegistry(base.list_all() + definitions), snapshot

    def record_discovery(
        self,
        discovery: MultiSourceDiscoveryResult,
        *,
        snapshot: CompanyRegistrySnapshot | None = None,
        now: datetime | None = None,
    ) -> CompanyMonitoringSummary:
        state = snapshot or self.snapshot()
        timestamp = now or datetime.now(timezone.utc)
        succeeded = failed = 0
        failures: list[str] = []
        for company in state.executable:
            source_id = (
                company.company_key
                if company.ats_family == "ashby"
                else f"{company.ats_family}:{company.company_key}"
            )
            execution = discovery.source_executions_by_id.get(source_id)
            if execution is None:
                continue
            success = execution.succeeded
            self.repository.record_company_check(
                company.company_key, succeeded=success, now=timestamp
            )
            if success:
                succeeded += 1
            else:
                failed += 1
                failures.append(company.company_name)
        return CompanyMonitoringSummary(
            tracked=state.tracked,
            enabled=state.enabled,
            executed=succeeded + failed,
            succeeded=succeeded,
            failed=failed,
            unsupported=len(state.unsupported),
            limited=len(state.limited),
            top_failures=failures[:5],
        )
