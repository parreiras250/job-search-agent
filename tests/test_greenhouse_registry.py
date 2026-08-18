"""Testes offline do piloto Greenhouse no registry genérico."""

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from daniel_job_agent import (
    ApplicationStatus,
    GreenhouseTenantConfig,
    JobLifecycleStatus,
    JobOpportunity,
    JobRepository,
    LifecycleAuthority,
    LocalCRM,
    MultiSourceDiscovery,
    SourceRegistry,
    SourceResult,
    SourceStatus,
    SourceType,
    create_daniel_profile,
    create_default_source_registry,
    create_greenhouse_pilot_definitions,
    process_opportunities,
    reconcile_lifecycle,
    sync_opportunities,
)


FIXTURE = Path(__file__).parent / "fixtures" / "greenhouse_pilot.json"
NOW = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)


class StubSource:
    def __init__(self, result: SourceResult):
        self.result = result
        self.calls = 0

    def fetch(self) -> SourceResult:
        self.calls += 1
        return self.result


def greenhouse_result() -> SourceResult:
    records = json.loads(FIXTURE.read_text())["jobs"]
    return SourceResult(SourceStatus.SUCCESS, records)


def empty() -> SourceResult:
    return SourceResult(SourceStatus.NO_JOBS, [])


def failure(name: str) -> SourceResult:
    return SourceResult(SourceStatus.CONNECTION_ERROR, [], f"{name} offline")


def wwr_job() -> JobOpportunity:
    return JobOpportunity(
        company="Pilot SaaS", role="Account Executive",
        job_url="https://weworkremotely.com/remote-jobs/pilot-ae",
        source="We Work Remotely", location="Remote - LATAM",
        remote=True, brazil_eligible=True, external_id="wwr-pilot-ae",
        source_id="weworkremotely", source_family="weworkremotely",
        source_instance="weworkremotely:sales-marketing", source_type="FEED",
        lifecycle_authority="OBSERVATIONAL",
    )


def greenhouse_job() -> JobOpportunity:
    return JobOpportunity(
        company="Pilot SaaS", role="Account Executive",
        job_url="https://boards.greenhouse.io/pilot/jobs/1001",
        source="Greenhouse public Job Board", location="Remote - LATAM",
        remote=None, brazil_eligible=None, external_id="1001",
        source_id="greenhouse:pilot", source_family="greenhouse",
        source_instance="greenhouse:pilot", source_type="TENANT_BOARD",
        lifecycle_authority="AUTHORITATIVE",
    )


class GreenhouseDefinitionTests(unittest.TestCase):
    def test_tenant_definition_has_exact_authoritative_capabilities(self) -> None:
        config = GreenhouseTenantConfig("pilot", "Pilot SaaS", "pilot-board")
        definition = create_greenhouse_pilot_definitions([config])[0]
        self.assertEqual(definition.source_id, "greenhouse:pilot")
        self.assertEqual(definition.display_name, "Greenhouse — Pilot SaaS")
        self.assertEqual(definition.source_type, SourceType.TENANT_BOARD)
        self.assertEqual(definition.source_family, "greenhouse")
        self.assertEqual(definition.source_instance, "greenhouse:pilot")
        self.assertTrue(definition.capabilities.tenant_scoped)
        self.assertFalse(definition.capabilities.global_search)
        self.assertFalse(definition.capabilities.supports_query)
        self.assertFalse(definition.capabilities.provides_posted_date)
        self.assertEqual(
            definition.capabilities.lifecycle_authority,
            LifecycleAuthority.AUTHORITATIVE,
        )
        self.assertFalse(definition.capabilities.requires_auth)
        self.assertFalse(definition.capabilities.requires_attribution)
        self.assertEqual(definition.request_budget, 1)

    def test_pilot_rejects_more_than_five_tenants_and_invalid_keys(self) -> None:
        tenants = [
            GreenhouseTenantConfig(f"company-{index}", f"Company {index}", f"board-{index}")
            for index in range(6)
        ]
        with self.assertRaisesRegex(ValueError, "at most 5"):
            create_greenhouse_pilot_definitions(tenants)
        with self.assertRaises(ValueError):
            GreenhouseTenantConfig("Bad Key", "Company", "board")

    def test_default_registry_adds_only_explicit_manual_tenants(self) -> None:
        base = create_default_source_registry()
        self.assertNotIn("greenhouse:pilot", [item.source_id for item in base.list_all()])
        configured = create_default_source_registry(
            greenhouse_tenants=(GreenhouseTenantConfig("pilot", "Pilot", "board"),),
            greenhouse_sources={"greenhouse:pilot": StubSource(empty())},
        )
        self.assertEqual(
            [item.source_id for item in configured.list_all()][-1], "greenhouse:pilot"
        )


class GreenhouseGenericDiscoveryTests(unittest.TestCase):
    def test_fixture_adapter_identity_external_id_and_pipeline(self) -> None:
        source = StubSource(greenhouse_result())
        definition = create_greenhouse_pilot_definitions(
            [GreenhouseTenantConfig("pilot", "Pilot SaaS", "pilot-board")],
            source_overrides={"greenhouse:pilot": source},
        )[0]
        output = MultiSourceDiscovery(registry=SourceRegistry([definition])).run(
            create_daniel_profile()
        )
        self.assertEqual(source.calls, 1)
        self.assertEqual(output.sources_succeeded, ["Greenhouse — Pilot SaaS"])
        self.assertEqual(output.jobs_converted_by_source["Greenhouse — Pilot SaaS"], 5)
        self.assertEqual(output.errors_by_source["Greenhouse — Pilot SaaS"], 1)
        account = next(
            item.normalized_job for item in output.ranking
            if item.normalized_job.external_id == "1001"
        )
        self.assertEqual(account.source_id, "greenhouse:pilot")
        self.assertEqual(account.source_family, "greenhouse")
        self.assertEqual(account.source_instance, "greenhouse:pilot")
        self.assertEqual(account.lifecycle_authority, "AUTHORITATIVE")
        self.assertIsNone(account.remote)
        self.assertIsNone(account.brazil_eligible)

    def test_multiple_tenants_have_individual_health_and_failure_isolation(self) -> None:
        configs = tuple(
            GreenhouseTenantConfig(f"company-{index}", f"Company {index}", f"board-{index}")
            for index in range(1, 6)
        )
        sources = {
            f"greenhouse:company-{index}": StubSource(
                failure(f"Company {index}") if index == 3 else empty()
            )
            for index in range(1, 6)
        }
        definitions = create_greenhouse_pilot_definitions(
            configs, source_overrides=sources
        )
        output = MultiSourceDiscovery(registry=SourceRegistry(definitions)).run(
            create_daniel_profile()
        )
        self.assertEqual(len(output.sources_attempted), 5)
        self.assertEqual(output.sources_failed, ["Greenhouse — Company 3"])
        self.assertEqual(len(output.sources_succeeded), 4)
        self.assertEqual(
            output.source_failure_messages,
            {"Greenhouse — Company 3": "Company 3 offline"},
        )
        self.assertTrue(all(source.calls == 1 for source in sources.values()))
        self.assertEqual(
            list(output.source_executions_by_id),
            [f"greenhouse:company-{index}" for index in range(1, 6)],
        )

    def test_all_greenhouse_fail_but_three_global_sources_continue(self) -> None:
        globals_ = {
            "jobicy": StubSource(empty()),
            "remotive": StubSource(empty()),
            "weworkremotely": StubSource(empty()),
            "himalayas": StubSource(empty()),
            "remoteok": StubSource(empty()),
        }
        tenants = (
            GreenhouseTenantConfig("one", "One", "one"),
            GreenhouseTenantConfig("two", "Two", "two"),
        )
        greenhouse_sources = {
            "greenhouse:one": StubSource(failure("One")),
            "greenhouse:two": StubSource(failure("Two")),
        }
        registry = create_default_source_registry(
            jobicy_source=globals_["jobicy"], remotive_source=globals_["remotive"],
            wwr_source=globals_["weworkremotely"], greenhouse_tenants=tenants,
            himalayas_source=globals_["himalayas"],
            remoteok_source=globals_["remoteok"],
            getonboard_source=globals_["remoteok"],
            greenhouse_sources=greenhouse_sources,
        )
        output = MultiSourceDiscovery(registry=registry).run(create_daniel_profile())
        self.assertEqual(output.sources_succeeded, ["Jobicy", "Remotive", "We Work Remotely", "Himalayas", "RemoteOK", "Get on Board"])
        self.assertEqual(output.sources_failed, ["Greenhouse — One", "Greenhouse — Two"])


class GreenhousePromotionAndLifecycleTests(unittest.TestCase):
    def test_authoritative_greenhouse_promotes_primary_and_preserves_history_crm(self) -> None:
        with JobRepository(":memory:") as repository:
            first = sync_opportunities(
                process_opportunities([wwr_job()], create_daniel_profile()), repository,
                now=NOW,
            )
            internal_id = first.new_jobs[0].internal_id
            first_seen = repository.get(internal_id).first_seen_at  # type: ignore[union-attr]
            LocalCRM(repository).update_manual_fields(
                internal_id, application_status=ApplicationStatus.APPLIED,
                notes="preserve me",
            )
            second = sync_opportunities(
                process_opportunities([greenhouse_job()], create_daniel_profile()),
                repository, now=NOW + timedelta(days=1),
            )
            stored = repository.get(internal_id)
            assert stored is not None
            self.assertEqual(repository.count(), 1)
            self.assertEqual(repository.observation_count(), 2)
            self.assertEqual(second.updated, 1)
            self.assertEqual(stored.opportunity.source_id, "greenhouse:pilot")
            self.assertEqual(stored.opportunity.job_url, greenhouse_job().job_url)
            self.assertEqual(stored.first_seen_at, first_seen)
            self.assertEqual(stored.opportunity.tracking.application_status, ApplicationStatus.APPLIED)
            self.assertEqual(stored.opportunity.tracking.notes, "preserve me")
            self.assertEqual(
                {item.observed_url for item in repository.get_observations(internal_id)},
                {wwr_job().job_url, greenhouse_job().job_url},
            )

    def test_same_run_cross_source_dedup_also_promotes_greenhouse(self) -> None:
        with JobRepository(":memory:") as repository:
            sync = sync_opportunities(
                process_opportunities(
                    [wwr_job(), greenhouse_job()], create_daniel_profile()
                ),
                repository,
            )
            stored = repository.get(sync.new_jobs[0].internal_id)
            assert stored is not None
            self.assertEqual(repository.count(), 1)
            self.assertEqual(repository.observation_count(), 2)
            self.assertEqual(stored.opportunity.source_family, "greenhouse")

    def test_greenhouse_present_wwr_missing_keeps_open_and_reappears(self) -> None:
        with JobRepository(":memory:") as repository:
            initial = sync_opportunities(
                process_opportunities(
                    [greenhouse_job(), wwr_job()], create_daniel_profile()
                ), repository, now=NOW,
            )
            internal_id = initial.new_jobs[0].internal_id
            observations = repository.get_observations(internal_id)
            greenhouse_observation = next(
                item for item in observations if item.source_family == "greenhouse"
            )
            result = reconcile_lifecycle(
                repository, seen_internal_ids={internal_id}, successful_sources=set(),
                successful_source_identities={
                    ("greenhouse", "greenhouse:pilot"),
                    ("weworkremotely", "weworkremotely:sales-marketing"),
                },
                seen_observation_ids={greenhouse_observation.observation_id},
                now=NOW + timedelta(days=1),
            )
            self.assertEqual(result.misses_recorded, 0)
            self.assertEqual(
                repository.get(internal_id).opportunity.lifecycle_status,  # type: ignore[union-attr]
                JobLifecycleStatus.OPEN,
            )
            seen_again = sync_opportunities(
                process_opportunities([greenhouse_job()], create_daniel_profile()),
                repository, now=NOW + timedelta(days=2),
            )
            greenhouse_after = next(
                item for item in repository.get_observations(internal_id)
                if item.source_family == "greenhouse"
            )
            self.assertIn(greenhouse_after.observation_id, seen_again.seen_observation_ids)
            self.assertEqual(greenhouse_after.consecutive_misses, 0)
            self.assertTrue(greenhouse_after.active)

    def test_greenhouse_missing_wwr_present_then_all_missing_and_reopen(self) -> None:
        identities = {
            ("greenhouse", "greenhouse:pilot"),
            ("weworkremotely", "weworkremotely:sales-marketing"),
        }
        with JobRepository(":memory:") as repository:
            initial = sync_opportunities(
                process_opportunities(
                    [greenhouse_job(), wwr_job()], create_daniel_profile()
                ), repository, now=NOW,
            )
            internal_id = initial.new_jobs[0].internal_id
            wwr_observation = next(
                item for item in repository.get_observations(internal_id)
                if item.source_id == "weworkremotely"
            )
            partial = reconcile_lifecycle(
                repository, seen_internal_ids={internal_id}, successful_sources=set(),
                successful_source_identities=identities,
                seen_observation_ids={wwr_observation.observation_id},
                now=NOW + timedelta(days=1),
            )
            self.assertEqual(partial.misses_recorded, 0)
            self.assertEqual(
                repository.get(internal_id).opportunity.lifecycle_status,  # type: ignore[union-attr]
                JobLifecycleStatus.OPEN,
            )
            for day in (2, 3, 4):
                closed = reconcile_lifecycle(
                    repository, seen_internal_ids=set(), successful_sources=set(),
                    successful_source_identities=identities,
                    seen_observation_ids=set(), now=NOW + timedelta(days=day),
                )
            self.assertEqual(closed.newly_closed, 1)
            greenhouse_seen = sync_opportunities(
                process_opportunities([greenhouse_job()], create_daniel_profile()),
                repository, now=NOW + timedelta(days=5),
            )
            reopened = reconcile_lifecycle(
                repository, seen_internal_ids={internal_id}, successful_sources=set(),
                successful_source_identities={("greenhouse", "greenhouse:pilot")},
                seen_observation_ids=greenhouse_seen.seen_observation_ids,
                now=NOW + timedelta(days=5),
            )
            self.assertEqual(reopened.reopened, 1)
            self.assertEqual(
                repository.get(internal_id).opportunity.lifecycle_status,  # type: ignore[union-attr]
                JobLifecycleStatus.OPEN,
            )

    def test_failed_greenhouse_tenant_does_not_add_observation_miss(self) -> None:
        with JobRepository(":memory:") as repository:
            initial = sync_opportunities(
                process_opportunities([greenhouse_job()], create_daniel_profile()),
                repository, now=NOW,
            )
            internal_id = initial.new_jobs[0].internal_id
            before = repository.get_observations(internal_id)[0]
            result = reconcile_lifecycle(
                repository, seen_internal_ids=set(), successful_sources=set(),
                successful_source_identities=set(), seen_observation_ids=set(),
                now=NOW + timedelta(days=1),
            )
            after = repository.get_observations(internal_id)[0]
            self.assertEqual(result.misses_recorded, 0)
            self.assertEqual(after.consecutive_misses, before.consecutive_misses)


if __name__ == "__main__":
    unittest.main()
