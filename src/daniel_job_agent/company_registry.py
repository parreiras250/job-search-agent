"""Registry persistente de empresas e geração segura de tenant sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping, TYPE_CHECKING

from .models import CompanyRecord
from .repository import JobRepository
from .source_registry import (
    GreenhouseTenantConfig,
    SourceDefinition,
    SourceRegistry,
    create_default_source_registry,
    create_greenhouse_pilot_definitions,
)
from .sources import JobSource

if TYPE_CHECKING:
    from .discovery import MultiSourceDiscoveryResult


DEFAULT_MAX_ENABLED_TENANTS = 25
SUPPORTED_ATS_FAMILIES = frozenset({"greenhouse"})


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
        configs = tuple(
            GreenhouseTenantConfig(
                company_key=company.company_key,
                company_name=company.company_name,
                board_token=company.ats_identifier,
                priority=company.priority,
            )
            for company in snapshot.executable
        )
        definitions = create_greenhouse_pilot_definitions(
            configs,
            source_overrides=source_overrides,
            max_tenants=self.max_enabled_tenants,
        )
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
            source_id = f"{company.ats_family}:{company.company_key}"
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
