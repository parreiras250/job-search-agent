"""Testes offline do framework genérico de fontes da Etapa 13B."""

import unittest
from datetime import date, datetime, timezone

from daniel_job_agent import (
    GenericJobAdapter,
    AgentRunHistory,
    DanielJobAgent,
    JobOpportunity,
    JobRepository,
    LifecycleAuthority,
    MultiQueryDiscovery,
    MultiSourceDiscovery,
    SearchStrategy,
    SourceCapabilities,
    SourceDefinition,
    SourceQuery,
    SourceRegistry,
    SourceResult,
    SourceStatus,
    SourceType,
    create_daniel_profile,
    create_default_source_registry,
    build_weekly_report,
    reconcile_lifecycle,
    sync_opportunities,
    process_opportunities,
)


class StubSource:
    def __init__(self, result: SourceResult):
        self.result = result
        self.calls = 0

    def fetch(self) -> SourceResult:
        self.calls += 1
        return self.result


def result(*records: dict[str, object], failure: str | None = None) -> SourceResult:
    if failure is not None:
        return SourceResult(SourceStatus.CONNECTION_ERROR, [], failure)
    status = SourceStatus.SUCCESS if records else SourceStatus.NO_JOBS
    return SourceResult(status, list(records))


def record(identifier: str) -> dict[str, object]:
    return {
        "company": f"Company {identifier}",
        "title": "Account Executive",
        "url": f"https://example.test/jobs/{identifier}",
        "location": "LATAM",
        "remote": True,
        "brazil_eligible": True,
    }


def definition(
    source_id: str,
    source_type: SourceType,
    source_result: SourceResult,
    *,
    family: str | None = None,
    instance: str | None = None,
    enabled: bool = True,
) -> tuple[SourceDefinition, StubSource]:
    source = StubSource(source_result)
    source_family = family or source_id
    item = SourceDefinition(
        source_id=source_id,
        display_name=source_id.replace("-", " ").title(),
        source_type=source_type,
        source_family=source_family,
        source_instance=instance or f"{source_family}:global",
        capabilities=SourceCapabilities(
            global_search=source_type is not SourceType.TENANT_BOARD,
            tenant_scoped=source_type is SourceType.TENANT_BOARD,
            supports_query=True,
            provides_direct_url=True,
            lifecycle_authority=LifecycleAuthority.OBSERVATIONAL,
        ),
        source_factory=lambda: source,
        adapter_factory=GenericJobAdapter,
        default_config={},
        enabled=enabled,
    )
    return item, source


class SourceRegistryTests(unittest.TestCase):
    def test_default_registry_contains_current_sources(self) -> None:
        registry = create_default_source_registry()
        self.assertEqual([item.source_id for item in registry.list_all()], ["jobicy", "remotive", "weworkremotely", "himalayas", "remoteok"])
        self.assertEqual(
            [item.default_config for item in registry.list_all()],
            [
                {"geo": "latam", "industry": "seller", "count": 100, "tag": None},
                {"category": "sales", "company_name": None, "search": None, "limit": None},
                {"feed_url": "https://weworkremotely.com/categories/remote-sales-and-marketing-jobs.rss"},
                {"q": "sales", "sort": "recent", "page": 1},
                {"feed_url": "https://remoteok.com/api"},
            ],
        )

    def test_registry_preserves_order_and_supports_enable_disable(self) -> None:
        first, _ = definition("alpha", SourceType.FEED, result())
        second, _ = definition("beta", SourceType.AGGREGATOR, result())
        registry = SourceRegistry([first, second])
        self.assertEqual([item.source_id for item in registry.enabled_sources()], ["alpha", "beta"])
        registry.disable("alpha")
        self.assertEqual([item.source_id for item in registry.enabled_sources()], ["beta"])
        registry.enable("alpha")
        self.assertEqual([item.source_id for item in registry.enabled_sources()], ["alpha", "beta"])
        with self.assertRaisesRegex(ValueError, "duplicate source_id"):
            registry.register(first)

    def test_capabilities_validate_global_tenant_conflict(self) -> None:
        with self.assertRaises(ValueError):
            SourceCapabilities(global_search=True, tenant_scoped=True)


class GenericDiscoveryTests(unittest.TestCase):
    def test_third_feed_and_tenant_sources_need_no_orchestrator_branch(self) -> None:
        alpha, alpha_source = definition("alpha", SourceType.GLOBAL_BOARD, result(record("a")))
        tenant, tenant_source = definition(
            "tenant-acme", SourceType.TENANT_BOARD, result(record("t")),
            family="tenantboard", instance="tenantboard:acme",
        )
        feed, feed_source = definition("partner-feed", SourceType.FEED, result(record("f")))
        discovery = MultiSourceDiscovery(registry=SourceRegistry([alpha, tenant, feed]))
        output = discovery.run(create_daniel_profile())
        self.assertEqual(output.sources_attempted, ["Alpha", "Tenant Acme", "Partner Feed"])
        self.assertEqual(output.global_unique_jobs, 3)
        self.assertEqual(list(output.source_executions_by_id), ["alpha", "tenant-acme", "partner-feed"])
        self.assertEqual([alpha_source.calls, tenant_source.calls, feed_source.calls], [1, 1, 1])
        identities = {
            (item.normalized_job.source_id, item.normalized_job.source_instance)
            for item in output.ranking
        }
        self.assertIn(("tenant-acme", "tenantboard:acme"), identities)

    def test_multiple_failures_are_isolated_across_n_sources(self) -> None:
        definitions = [
            definition(f"source-{index}", SourceType.FEED, result(
                *(record(str(index)),) if index in {1, 4, 5} else (),
                failure=None if index in {1, 4, 5} else f"offline-{index}",
            ))[0]
            for index in range(1, 6)
        ]
        output = MultiSourceDiscovery(registry=SourceRegistry(definitions)).run(
            create_daniel_profile()
        )
        self.assertEqual(output.sources_succeeded, ["Source 1", "Source 4", "Source 5"])
        self.assertEqual(output.sources_failed, ["Source 2", "Source 3"])
        self.assertEqual(output.global_unique_jobs, 3)

    def test_all_registered_sources_can_fail_safely(self) -> None:
        items = [
            definition(f"failed-{index}", SourceType.FEED, result(failure="offline"))[0]
            for index in range(3)
        ]
        output = MultiSourceDiscovery(registry=SourceRegistry(items)).run(create_daniel_profile())
        self.assertEqual(output.sources_succeeded, [])
        self.assertEqual(len(output.sources_failed), 3)
        self.assertEqual(output.global_unique_jobs, 0)

    def test_weekly_report_iterates_generic_source_summary(self) -> None:
        feed, _ = definition("partner-feed", SourceType.FEED, result(record("report")))
        with JobRepository(":memory:") as repository:
            agent_result = DanielJobAgent(
                repository, discovery=MultiSourceDiscovery(registry=SourceRegistry([feed]))
            ).run()
            timestamp = datetime(2026, 8, 16, tzinfo=timezone.utc)
            history = AgentRunHistory(
                1, timestamp, timestamp, "SUCCESS", ["Partner Feed"], [],
                1, 1, 0, 0, 0, 0, 0, 0, None, None,
            )
            report = build_weekly_report(repository, history, agent_result)
        self.assertEqual([item.name for item in report.sources], ["Partner Feed"])
        self.assertEqual(report.sources[0].received, 1)

    def test_disabled_source_is_not_executed(self) -> None:
        enabled, enabled_source = definition("enabled", SourceType.FEED, result())
        disabled, disabled_source = definition("disabled", SourceType.FEED, result(), enabled=False)
        output = MultiSourceDiscovery(registry=SourceRegistry([enabled, disabled])).run(
            create_daniel_profile()
        )
        self.assertEqual(output.sources_attempted, ["Enabled"])
        self.assertEqual([enabled_source.calls, disabled_source.calls], [1, 0])


class GenericQueryAndLifecycleTests(unittest.TestCase):
    def test_generic_query_contributes_under_stable_source_id(self) -> None:
        fake, _ = definition("partner-feed", SourceType.FEED, result())
        strategy = SearchStrategy(
            "fake query", (), (),
            (SourceQuery("partner-feed", "sales", {"page": 1}, broad=True),),
        )
        output = MultiQueryDiscovery(
            strategy,
            registry=SourceRegistry([fake]),
            source_factories={"partner-feed": lambda query: StubSource(result(record("q")))},
        ).run(create_daniel_profile())
        self.assertEqual(output.unique_jobs_by_source, {"partner-feed": 1})
        self.assertEqual(output.query_summaries[0].query_key, "partner-feed:sales")
        self.assertEqual(output.ranking[0].normalized_job.source_id, "partner-feed")

    def test_lifecycle_matches_exact_structured_instance_not_source_text(self) -> None:
        repository = JobRepository(":memory:")
        try:
            opportunity = JobOpportunity(
                company="Acme", role="Account Executive",
                job_url="https://example.test/acme", source="arbitrary human label",
                location="LATAM", remote=True, brazil_eligible=True,
                source_id="tenant-acme", source_family="tenantboard",
                source_instance="tenantboard:acme", date_found=date(2026, 8, 16),
            )
            synced = sync_opportunities(
                process_opportunities([opportunity], create_daniel_profile()), repository
            )
            internal_id = synced.new_jobs[0].internal_id
            other = reconcile_lifecycle(
                repository, seen_internal_ids=set(), successful_sources=set(),
                successful_source_identities={("tenantboard", "tenantboard:other")},
            )
            self.assertEqual(other.misses_recorded, 0)
            exact = reconcile_lifecycle(
                repository, seen_internal_ids=set(), successful_sources=set(),
                successful_source_identities={("tenantboard", "tenantboard:acme")},
            )
            self.assertEqual(exact.misses_recorded, 1)
            self.assertEqual(repository.get(internal_id).opportunity.consecutive_misses, 1)  # type: ignore[union-attr]
        finally:
            repository.close()


if __name__ == "__main__":
    unittest.main()
