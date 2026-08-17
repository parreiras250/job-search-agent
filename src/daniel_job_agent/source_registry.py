"""Identidade, capabilities e registry em memória das fontes de vagas."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from types import MappingProxyType
from typing import Callable, Mapping

from .ingestion import (
    BaseJobAdapter,
    GreenhouseJobAdapter,
    JobicyJobAdapter,
    RemotiveJobAdapter,
    WeWorkRemotelyJobAdapter,
)
from .sources import (
    GreenhouseJobSource,
    JobSource,
    JobicyJobSource,
    RemotiveJobSource,
    WWR_SALES_MARKETING_RSS_URL,
    WeWorkRemotelyJobSource,
)


MAX_GREENHOUSE_PILOT_TENANTS = 5


class SourceType(str, Enum):
    GLOBAL_BOARD = "GLOBAL_BOARD"
    TENANT_BOARD = "TENANT_BOARD"
    FEED = "FEED"
    AGGREGATOR = "AGGREGATOR"


class LifecycleAuthority(str, Enum):
    NONE = "NONE"
    OBSERVATIONAL = "OBSERVATIONAL"
    AUTHORITATIVE = "AUTHORITATIVE"


@dataclass(frozen=True, slots=True)
class GreenhouseTenantConfig:
    """Configuração manual e temporária de um tenant do piloto Greenhouse."""

    company_key: str
    company_name: str
    board_token: str
    enabled: bool = True
    priority: int = 100

    def __post_init__(self) -> None:
        if (
            not self.company_key
            or self.company_key != self.company_key.strip().casefold()
            or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for character in self.company_key)
        ):
            raise ValueError("company_key must be a lowercase slug")
        if not self.company_name.strip():
            raise ValueError("company_name cannot be empty")
        if not self.board_token.strip():
            raise ValueError("board_token cannot be empty")
        if self.priority < 0:
            raise ValueError("priority cannot be negative")


@dataclass(frozen=True, slots=True)
class SourceCapabilities:
    global_search: bool = False
    tenant_scoped: bool = False
    supports_query: bool = False
    supports_location_filter: bool = False
    supports_category_filter: bool = False
    supports_pagination: bool = False
    provides_description: bool = False
    provides_salary: bool = False
    provides_posted_date: bool = False
    provides_external_id: bool = False
    provides_direct_url: bool = False
    lifecycle_authority: LifecycleAuthority = LifecycleAuthority.NONE
    requires_auth: bool = False
    requires_attribution: bool = False

    def __post_init__(self) -> None:
        if self.global_search and self.tenant_scoped:
            raise ValueError("a source cannot be global_search and tenant_scoped")


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    source_id: str
    display_name: str
    source_type: SourceType
    source_family: str
    source_instance: str
    capabilities: SourceCapabilities
    source_factory: Callable[[], JobSource]
    adapter_factory: Callable[[], BaseJobAdapter]
    default_config: Mapping[str, object]
    query_source_factory: Callable[[Mapping[str, object]], JobSource] | None = None
    enabled: bool = True
    priority: int = 100
    request_budget: int = 1

    def __post_init__(self) -> None:
        for name, value in (
            ("source_id", self.source_id),
            ("display_name", self.display_name),
            ("source_family", self.source_family),
            ("source_instance", self.source_instance),
        ):
            if not value.strip():
                raise ValueError(f"{name} cannot be empty")
        if self.source_id != self.source_id.strip().casefold():
            raise ValueError("source_id must be a lowercase stable identifier")
        if self.source_family != self.source_family.strip().casefold():
            raise ValueError("source_family must be a lowercase stable identifier")
        if not self.source_instance.startswith(f"{self.source_family}:"):
            raise ValueError("source_instance must start with source_family plus ':'")
        if self.priority < 0:
            raise ValueError("priority cannot be negative")
        if self.request_budget < 1:
            raise ValueError("request_budget must be positive")
        object.__setattr__(self, "default_config", MappingProxyType(dict(self.default_config)))


class SourceRegistry:
    """Registry ordenado, validado e mutável somente por enable/disable."""

    def __init__(self, definitions: list[SourceDefinition] | None = None) -> None:
        self._definitions: dict[str, SourceDefinition] = {}
        for definition in definitions or []:
            self.register(definition)

    def register(self, definition: SourceDefinition) -> None:
        if definition.source_id in self._definitions:
            raise ValueError(f"duplicate source_id: {definition.source_id}")
        self._definitions[definition.source_id] = definition

    def get(self, source_id: str) -> SourceDefinition:
        try:
            return self._definitions[source_id]
        except KeyError as exc:
            raise KeyError(f"unknown source_id: {source_id}") from exc

    def list_all(self) -> list[SourceDefinition]:
        return list(self._definitions.values())

    def enabled_sources(self) -> list[SourceDefinition]:
        return [item for item in self._definitions.values() if item.enabled]

    def enable(self, source_id: str) -> None:
        self._definitions[source_id] = replace(self.get(source_id), enabled=True)

    def disable(self, source_id: str) -> None:
        self._definitions[source_id] = replace(self.get(source_id), enabled=False)


def create_greenhouse_pilot_definitions(
    tenants: list[GreenhouseTenantConfig] | tuple[GreenhouseTenantConfig, ...],
    *,
    source_overrides: Mapping[str, JobSource] | None = None,
    max_tenants: int = MAX_GREENHOUSE_PILOT_TENANTS,
) -> list[SourceDefinition]:
    """Cria definições tenant-scoped; o piloto manual mantém limite cinco."""

    if len(tenants) > max_tenants:
        raise ValueError(f"Greenhouse configuration supports at most {max_tenants} tenants")
    overrides = dict(source_overrides or {})
    definitions: list[SourceDefinition] = []
    for tenant in tenants:
        source_id = f"greenhouse:{tenant.company_key}"

        def source_factory(
            config: GreenhouseTenantConfig = tenant,
            definition_id: str = source_id,
        ) -> JobSource:
            override = overrides.get(definition_id)
            if override is not None:
                return override
            return GreenhouseJobSource(config.board_token, config.company_name)

        definitions.append(
            SourceDefinition(
                source_id=source_id,
                display_name=f"Greenhouse — {tenant.company_name.strip()}",
                source_type=SourceType.TENANT_BOARD,
                source_family="greenhouse",
                source_instance=source_id,
                capabilities=SourceCapabilities(
                    tenant_scoped=True,
                    supports_query=False,
                    provides_description=True,
                    provides_posted_date=False,
                    provides_external_id=True,
                    provides_direct_url=True,
                    lifecycle_authority=LifecycleAuthority.AUTHORITATIVE,
                    requires_auth=False,
                    requires_attribution=False,
                ),
                source_factory=source_factory,
                adapter_factory=lambda company=tenant.company_name: GreenhouseJobAdapter(company),
                default_config={
                    "company_key": tenant.company_key,
                    "company_name": tenant.company_name.strip(),
                    "board_token": tenant.board_token.strip(),
                },
                enabled=tenant.enabled,
                priority=tenant.priority,
                request_budget=1,
            )
        )
    return definitions


def create_default_source_registry(
    *,
    jobicy_config: Mapping[str, object] | None = None,
    remotive_config: Mapping[str, object] | None = None,
    jobicy_source: JobSource | None = None,
    remotive_source: JobSource | None = None,
    wwr_source: JobSource | None = None,
    greenhouse_tenants: tuple[GreenhouseTenantConfig, ...] = (),
    greenhouse_sources: Mapping[str, JobSource] | None = None,
) -> SourceRegistry:
    """Registra as três fontes operacionais na ordem determinística."""

    jobicy_values = {
        "geo": "latam", "industry": "seller", "count": 100, "tag": None,
        **dict(jobicy_config or {}),
    }
    remotive_values = {
        "category": "sales", "company_name": None, "search": None, "limit": None,
        **dict(remotive_config or {}),
    }
    definitions = [
        SourceDefinition(
            source_id="jobicy", display_name="Jobicy",
            source_type=SourceType.GLOBAL_BOARD, source_family="jobicy",
            source_instance="jobicy:global",
            capabilities=SourceCapabilities(
                global_search=True, supports_query=True,
                supports_location_filter=True, supports_category_filter=True,
                provides_description=True, provides_salary=True,
                provides_posted_date=True, provides_external_id=True,
                provides_direct_url=True,
                lifecycle_authority=LifecycleAuthority.OBSERVATIONAL,
                requires_attribution=True,
            ),
            source_factory=(lambda: jobicy_source) if jobicy_source else (
                lambda: JobicyJobSource(**jobicy_values)
            ),
            adapter_factory=JobicyJobAdapter,
            query_source_factory=lambda parameters: JobicyJobSource(**parameters),
            default_config=jobicy_values,
            request_budget=4,
        ),
        SourceDefinition(
            source_id="remotive", display_name="Remotive",
            source_type=SourceType.AGGREGATOR, source_family="remotive",
            source_instance="remotive:global",
            capabilities=SourceCapabilities(
                global_search=True, supports_query=True,
                supports_category_filter=True, provides_description=True,
                provides_salary=True, provides_posted_date=True,
                provides_external_id=True, provides_direct_url=True,
                lifecycle_authority=LifecycleAuthority.OBSERVATIONAL,
                requires_attribution=True,
            ),
            source_factory=(lambda: remotive_source) if remotive_source else (
                lambda: RemotiveJobSource(**remotive_values)
            ),
            adapter_factory=RemotiveJobAdapter,
            query_source_factory=lambda parameters: RemotiveJobSource(**parameters),
            default_config=remotive_values,
            request_budget=4,
        ),
        SourceDefinition(
            source_id="weworkremotely", display_name="We Work Remotely",
            source_type=SourceType.FEED, source_family="weworkremotely",
            source_instance="weworkremotely:sales-marketing",
            capabilities=SourceCapabilities(
                global_search=True, supports_query=False,
                provides_description=True, provides_posted_date=True,
                provides_external_id=True, provides_direct_url=True,
                lifecycle_authority=LifecycleAuthority.OBSERVATIONAL,
                requires_attribution=True,
            ),
            source_factory=(lambda: wwr_source) if wwr_source else WeWorkRemotelyJobSource,
            adapter_factory=WeWorkRemotelyJobAdapter,
            default_config={"feed_url": WWR_SALES_MARKETING_RSS_URL},
            request_budget=1,
        ),
    ]
    definitions.extend(
        create_greenhouse_pilot_definitions(
            greenhouse_tenants, source_overrides=greenhouse_sources
        )
    )
    return SourceRegistry(definitions)
