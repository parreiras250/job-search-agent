"""Testes offline da Etapa 13F — Company Registry persistente."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from daniel_job_agent import (
    AgentRunHistory,
    ApplicationStatus,
    CompanyRegistry,
    DanielJobAgent,
    JobOpportunity,
    JobRepository,
    LifecycleAuthority,
    LocalCRM,
    MultiSourceDiscovery,
    SourceRegistry,
    SourceResult,
    SourceStatus,
    build_weekly_report,
    create_daniel_profile,
    format_weekly_report,
    process_opportunities,
    reconcile_lifecycle,
    sync_opportunities,
)
from daniel_job_agent.repository import SCHEMA_VERSION


NOW = datetime(2026, 8, 17, 12, tzinfo=timezone.utc)


class StubSource:
    def __init__(self, result: SourceResult):
        self.result = result
        self.calls = 0

    def fetch(self) -> SourceResult:
        self.calls += 1
        return self.result


def success() -> SourceResult:
    return SourceResult(SourceStatus.NO_JOBS, [])


def failure() -> SourceResult:
    return SourceResult(SourceStatus.CONNECTION_ERROR, [], "offline")


def manual_pilot_job() -> JobOpportunity:
    return JobOpportunity(
        company="ScaleOps", role="Account Executive",
        job_url="https://boards.greenhouse.io/scaleops/jobs/1",
        source="Greenhouse public Job Board", location="Remote",
        remote=None, brazil_eligible=None, external_id="1",
        source_id="greenhouse:manual-pilot", source_family="greenhouse",
        source_instance="greenhouse:manual-pilot", source_type="TENANT_BOARD",
        lifecycle_authority="AUTHORITATIVE",
    )


class CompanyPersistenceTests(unittest.TestCase):
    def test_schema_migration_is_idempotent_and_preserves_existing_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.db"
            with JobRepository(path) as repository:
                synced = sync_opportunities(
                    process_opportunities([manual_pilot_job()], create_daniel_profile()),
                    repository, now=NOW,
                )
                internal_id = synced.new_jobs[0].internal_id
                LocalCRM(repository).update_manual_fields(
                    internal_id, application_status=ApplicationStatus.APPLIED,
                    notes="preserve",
                )
                repository.connection.execute("PRAGMA user_version = 5")
                repository.connection.commit()
            with JobRepository(path) as migrated:
                self.assertEqual(
                    migrated.connection.execute("PRAGMA user_version").fetchone()[0],
                    SCHEMA_VERSION,
                )
                migrated.add_company("scaleops", "ScaleOps", "greenhouse", "scaleops")
                self.assertEqual(migrated.count(), 1)
                observation = migrated.get_observations(internal_id)[0]
                self.assertEqual(observation.source_instance, "greenhouse:manual-pilot")
                self.assertEqual(
                    migrated.get(internal_id).opportunity.tracking.notes, "preserve"  # type: ignore[union-attr]
                )
            with JobRepository(path) as reopened:
                self.assertEqual(len(reopened.list_companies()), 1)
                self.assertEqual(reopened.observation_count(), 1)

    def test_add_get_duplicate_list_enable_disable_and_update(self) -> None:
        with JobRepository(":memory:") as repository:
            low = repository.add_company(
                "low", "Low", "ashby", "low-board", priority=10, now=NOW
            )
            high = repository.add_company(
                "high", "High", "greenhouse", "high-board", priority=200,
                notes="initial", now=NOW,
            )
            self.assertEqual(repository.get_company("HIGH"), high)
            self.assertEqual(
                [item.company_key for item in repository.list_companies()],
                ["high", "low"],
            )
            with self.assertRaisesRegex(ValueError, "duplicate company_key"):
                repository.add_company("high", "Again", "greenhouse", "again")
            repository.disable_company("high", now=NOW + timedelta(minutes=1))
            self.assertEqual(
                [item.company_key for item in repository.list_companies(enabled_only=True)],
                ["low"],
            )
            repository.enable_company("high", now=NOW + timedelta(minutes=2))
            updated = repository.update_company(
                "high", company_name="High Updated", priority=300,
                notes="changed", now=NOW + timedelta(minutes=3),
            )
            self.assertTrue(updated.enabled)
            self.assertEqual(updated.company_name, "High Updated")
            self.assertEqual(updated.priority, 300)
            self.assertEqual(low.failure_count, 0)

    def test_validation_rejects_invalid_fields_priority_and_naive_time(self) -> None:
        with JobRepository(":memory:") as repository:
            for values in (
                ("bad key", "Name", "greenhouse", "id", 100),
                ("key", "", "greenhouse", "id", 100),
                ("key", "Name", "", "id", 100),
                ("key", "Name", "greenhouse", "", 100),
                ("key", "Name", "greenhouse", "id", 1001),
            ):
                with self.subTest(values=values), self.assertRaises(ValueError):
                    repository.add_company(*values[:4], priority=values[4])


class CompanyRegistryGenerationTests(unittest.TestCase):
    def test_empty_registry_keeps_seven_operational_sources(self) -> None:
        with JobRepository(":memory:") as repository:
            registry, snapshot = CompanyRegistry(repository).build_source_registry()
            self.assertEqual(
                [item.source_id for item in registry.list_all()],
            ["jobicy", "remotive", "weworkremotely", "himalayas", "remoteok", "getonboard", "latamcent"],
            )
            self.assertEqual(snapshot.tracked, 0)

    def test_greenhouse_definition_is_authoritative_and_company_scoped(self) -> None:
        with JobRepository(":memory:") as repository:
            repository.add_company("scaleops", "ScaleOps", "greenhouse", "board-token")
            definitions, snapshot = CompanyRegistry(repository).source_definitions()
            definition = definitions[0]
            self.assertEqual(definition.source_id, "greenhouse:scaleops")
            self.assertEqual(definition.source_instance, "greenhouse:scaleops")
            self.assertEqual(definition.default_config["board_token"], "board-token")
            self.assertEqual(definition.request_budget, 1)
            self.assertEqual(
                definition.capabilities.lifecycle_authority,
                LifecycleAuthority.AUTHORITATIVE,
            )
            self.assertEqual(len(snapshot.executable), 1)

    def test_disabled_and_unsupported_are_never_generated_or_requested(self) -> None:
        with JobRepository(":memory:") as repository:
            repository.add_company("disabled", "Disabled", "greenhouse", "disabled")
            repository.disable_company("disabled")
            repository.add_company("future", "Future", "ashby", "future")
            disabled_source = StubSource(success())
            future_source = StubSource(success())
            definitions, snapshot = CompanyRegistry(repository).source_definitions(
                source_overrides={
                    "greenhouse:disabled": disabled_source,
                    "ashby:future": future_source,
                }
            )
            self.assertEqual(definitions, [])
            self.assertEqual([item.company_key for item in snapshot.unsupported], ["future"])
            self.assertEqual([disabled_source.calls, future_source.calls], [0, 0])

    def test_safety_limit_selects_top_25_deterministically(self) -> None:
        with JobRepository(":memory:") as repository:
            for index in range(27):
                repository.add_company(
                    f"company-{index:02d}", f"Company {index:02d}",
                    "greenhouse", f"board-{index:02d}", priority=index,
                )
            definitions, snapshot = CompanyRegistry(repository).source_definitions()
            self.assertEqual(len(definitions), 25)
            self.assertEqual(definitions[0].source_id, "greenhouse:company-26")
            self.assertEqual(definitions[-1].source_id, "greenhouse:company-02")
            self.assertEqual(
                [item.company_key for item in snapshot.limited],
                ["company-01", "company-00"],
            )


class CompanyHealthAndIntegrationTests(unittest.TestCase):
    def test_health_success_failure_increment_reset_and_no_auto_disable(self) -> None:
        with JobRepository(":memory:") as repository:
            repository.add_company("tenant", "Tenant", "greenhouse", "tenant", now=NOW)
            first = repository.record_company_check("tenant", succeeded=False, now=NOW)
            second = repository.record_company_check(
                "tenant", succeeded=False, now=NOW + timedelta(hours=1)
            )
            self.assertEqual([first.failure_count, second.failure_count], [1, 2])
            self.assertTrue(second.enabled)
            successful = repository.record_company_check(
                "tenant", succeeded=True, now=NOW + timedelta(hours=2)
            )
            self.assertEqual(successful.failure_count, 0)
            self.assertEqual(successful.last_checked_at, NOW + timedelta(hours=2))
            self.assertEqual(successful.last_success_at, NOW + timedelta(hours=2))

    def test_one_request_health_failure_isolation_and_report_summary(self) -> None:
        with JobRepository(":memory:") as repository:
            repository.add_company("ok", "OK Co", "greenhouse", "ok")
            repository.add_company("bad", "Bad Co", "greenhouse", "bad")
            repository.add_company("future", "Future Co", "ashby", "future")
            ok = StubSource(success())
            bad = StubSource(failure())
            service = CompanyRegistry(repository)
            definitions, _ = service.source_definitions(
                source_overrides={"greenhouse:ok": ok, "greenhouse:bad": bad}
            )
            result = DanielJobAgent(
                repository,
                discovery=MultiSourceDiscovery(registry=SourceRegistry(definitions)),
                company_registry=service,
                clock=lambda: NOW,
            ).run()
            self.assertEqual([ok.calls, bad.calls], [1, 1])
            self.assertEqual(result.company_monitoring.executed, 2)
            self.assertEqual(result.company_monitoring.succeeded, 1)
            self.assertEqual(result.company_monitoring.failed, 1)
            self.assertEqual(result.company_monitoring.unsupported, 1)
            self.assertEqual(repository.get_company("bad").failure_count, 1)  # type: ignore[union-attr]
            history = AgentRunHistory(
                1, NOW, NOW, "PARTIAL_SUCCESS", result.sources_succeeded,
                result.sources_failed, 0, 0, 0, 0, 0, 0, 0, 0, None, None,
            )
            rendered = format_weekly_report(
                build_weekly_report(repository, history, result)
            )
            self.assertIn("## Company monitoring", rendered)
            self.assertIn("Tracked companies: 3", rendered)
            self.assertIn("Succeeded: 1 | Failed: 1 | Unsupported: 1", rendered)

    def test_failed_or_disabled_tenant_does_not_create_lifecycle_miss(self) -> None:
        with JobRepository(":memory:") as repository:
            initial = sync_opportunities(
                process_opportunities([manual_pilot_job()], create_daniel_profile()),
                repository, now=NOW,
            )
            internal_id = initial.new_jobs[0].internal_id
            before = repository.get_observations(internal_id)[0]
            repository.add_company("scaleops", "ScaleOps", "greenhouse", "scaleops")
            repository.disable_company("scaleops")
            lifecycle = reconcile_lifecycle(
                repository, seen_internal_ids=set(), successful_sources=set(),
                successful_source_identities=set(), seen_observation_ids=set(),
                now=NOW + timedelta(days=1),
            )
            after = repository.get_observations(internal_id)[0]
            self.assertEqual(lifecycle.misses_recorded, 0)
            self.assertEqual(after.consecutive_misses, before.consecutive_misses)
            self.assertEqual(after.source_instance, "greenhouse:manual-pilot")


if __name__ == "__main__":
    unittest.main()
