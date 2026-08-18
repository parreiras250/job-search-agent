"""Testes offline do componente Ashby e dos três tenants configurados."""

import json
import socket
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError

from daniel_job_agent import (
    ASHBY_API_BASE_URL,
    AshbyJobAdapter,
    AshbyJobSource,
    AshbyTenantConfig,
    GLOBAL_SOURCE_ORDER,
    JobOpportunity,
    JobLifecycleStatus,
    JobRepository,
    LifecycleAuthority,
    MultiSourceDiscovery,
    SourceRegistry,
    SourceStatus,
    SourceType,
    build_ashby_jobs_url,
    create_ashby_definitions,
    create_daniel_profile,
    create_default_source_registry,
    ingest_batch,
    process_opportunities,
    reconcile_lifecycle,
    sync_opportunities,
)
from daniel_job_agent.sources import HttpResponse, SourceResult


FIXTURE = Path(__file__).parent / "fixtures" / "ashby_latamcent_jobs.json"
ELEVENLABS_FIXTURE = Path(__file__).parent / "fixtures" / "ashby_elevenlabs_jobs.json"
REPLIT_FIXTURE = Path(__file__).parent / "fixtures" / "ashby_replit_jobs.json"


def fixture_payload():
    return json.loads(FIXTURE.read_text())


def tenant_payload(path):
    return json.loads(path.read_text())


class FakeTransport:
    def __init__(self, payload=None, *, status=200, error=None):
        self.payload, self.status, self.error = payload, status, error
        self.calls = []

    def get(self, url, timeout, headers):
        self.calls.append((url, timeout, headers))
        if self.error is not None:
            raise self.error
        body = self.payload if isinstance(self.payload, bytes) else json.dumps(self.payload).encode()
        return HttpResponse(self.status, body)


class AshbySourceTests(unittest.TestCase):
    def test_url_uses_official_public_board_endpoint(self) -> None:
        self.assertEqual(
            build_ashby_jobs_url("latamcent"),
            ASHBY_API_BASE_URL + "/latamcent?includeCompensation=true",
        )
        self.assertTrue(build_ashby_jobs_url("board", include_compensation=False).endswith("false"))
        for invalid in ("", "../tenant", "a/b", "a?b"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                build_ashby_jobs_url(invalid)

    def test_one_get_returns_all_fixture_jobs_without_auth(self) -> None:
        transport = FakeTransport(fixture_payload())
        result = AshbyJobSource("latamcent", transport=transport).fetch()
        self.assertEqual(result.status, SourceStatus.SUCCESS)
        self.assertEqual(len(result.records), 10)
        self.assertEqual(len(transport.calls), 1)
        self.assertNotIn("Authorization", transport.calls[0][2])

    def test_empty_and_unexpected_payloads_are_controlled(self) -> None:
        self.assertEqual(
            AshbyJobSource("x", transport=FakeTransport({"apiVersion": "1", "jobs": []})).fetch().status,
            SourceStatus.NO_JOBS,
        )
        for payload in (b"not json", {}, {"jobs": "bad"}):
            with self.subTest(payload=payload):
                result = AshbyJobSource("x", transport=FakeTransport(payload)).fetch()
                self.assertEqual(result.status, SourceStatus.INVALID_PAYLOAD)
        self.assertEqual(
            AshbyJobSource("x", transport=FakeTransport({"apiVersion": "1", "jobs": [None]})).fetch().status,
            SourceStatus.NO_JOBS,
        )
        mixed = AshbyJobSource("x", transport=FakeTransport({
            "apiVersion": "1", "jobs": [None, fixture_payload()["jobs"][0]],
        })).fetch()
        self.assertEqual((mixed.status, len(mixed.records)), (SourceStatus.SUCCESS, 1))

    def test_transport_failures_are_isolated(self) -> None:
        url = build_ashby_jobs_url("x")
        cases = (
            (FakeTransport(status=500), SourceStatus.HTTP_ERROR),
            (FakeTransport(error=HTTPError(url, 429, "rate", {}, None)), SourceStatus.HTTP_ERROR),
            (FakeTransport(error=socket.timeout()), SourceStatus.TIMEOUT),
            (FakeTransport(error=URLError("offline")), SourceStatus.CONNECTION_ERROR),
        )
        for transport, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(AshbyJobSource("x", transport=transport).fetch().status, expected)


class AshbyAdapterTests(unittest.TestCase):
    def test_official_fields_compensation_and_unknowns_are_mapped(self) -> None:
        result = AshbyJobAdapter("LatamCent").adapt(fixture_payload()["jobs"][0])
        job = result.opportunity
        self.assertTrue(result.success)
        self.assertEqual(result.warnings, [])
        self.assertEqual(job.company, "Employer not disclosed (published by LatamCent)")
        self.assertEqual(job.source, "LatamCent")
        self.assertEqual(job.salary_min, 81000)
        self.assertEqual(job.salary_max, 87000)
        self.assertEqual(job.salary_currency, "USD")
        self.assertEqual(job.salary_period, "1 YEAR")
        self.assertTrue(job.remote)
        self.assertIsNone(job.brazil_eligible)
        self.assertEqual(job.job_url, "https://jobs.ashbyhq.com/latamcent/ae-latam")

    def test_optional_absence_and_unknown_fields_do_not_warn(self) -> None:
        records = fixture_payload()["jobs"]
        batch = ingest_batch(records[:-1], AshbyJobAdapter("LatamCent"))
        self.assertEqual(batch.converted_count, 9)
        self.assertEqual(batch.warning_count, 0)
        self.assertEqual(batch.opportunities[4].location, "Location not specified")
        self.assertTrue(batch.opportunities[5].remote)
        self.assertIsNone(batch.opportunities[6].salary_min)
        self.assertIsNone(batch.opportunities[7].description)

    def test_malformed_job_does_not_remove_valid_siblings(self) -> None:
        batch = ingest_batch(fixture_payload()["jobs"], AshbyJobAdapter("LatamCent"))
        self.assertEqual((batch.converted_count, batch.error_count), (9, 1))
        self.assertIn("job_url", batch.errors[0].message)

    def test_invalid_optional_values_warn_without_losing_job(self) -> None:
        record = dict(fixture_payload()["jobs"][0])
        record.update(publishedAt="not-a-date", isRemote="sometimes", compensation={"summaryComponents": "bad"})
        result = AshbyJobAdapter("LatamCent").adapt(record)
        self.assertTrue(result.success)
        self.assertEqual({item.field for item in result.warnings}, {"date_posted", "remote", "compensation"})

    def test_known_direct_employer_can_be_configured_without_using_publisher(self) -> None:
        result = AshbyJobAdapter("Example Careers", employer_name="Example SaaS").adapt(
            fixture_payload()["jobs"][1]
        )
        self.assertEqual(result.opportunity.company, "Example SaaS")
        self.assertEqual(result.opportunity.source, "Example Careers")


class LatamCentRegistryTests(unittest.TestCase):
    def test_default_registry_has_latamcent_ashby_identity_and_one_request_budget(self) -> None:
        registry = create_default_source_registry()
        definition = registry.get("latamcent")
        self.assertEqual(len(registry.enabled_sources()), 9)
        self.assertEqual(definition.source_family, "ashby")
        self.assertEqual(definition.source_instance, "ashby:latamcent")
        self.assertEqual(definition.source_type, SourceType.TENANT_BOARD)
        self.assertEqual(definition.request_budget, 1)
        self.assertEqual(definition.capabilities.lifecycle_authority, LifecycleAuthority.OBSERVATIONAL)
        self.assertEqual(definition.default_config["board_name"], "latamcent")
        self.assertIsNone(definition.default_config["employer_name"])
        self.assertEqual(GLOBAL_SOURCE_ORDER[-1], "latamcent")

    def test_wave1_company_boards_have_independent_observational_identities(self) -> None:
        registry = create_default_source_registry()
        elevenlabs = registry.get("elevenlabs")
        replit = registry.get("replit")
        self.assertEqual(
            (elevenlabs.source_family, elevenlabs.source_instance),
            ("ashby", "ashby:elevenlabs"),
        )
        self.assertEqual(
            (replit.source_family, replit.source_instance),
            ("ashby", "ashby:replit"),
        )
        for definition, company in ((elevenlabs, "ElevenLabs"), (replit, "Replit")):
            with self.subTest(company=company):
                self.assertEqual(definition.request_budget, 1)
                self.assertEqual(
                    definition.capabilities.lifecycle_authority,
                    LifecycleAuthority.OBSERVATIONAL,
                )
                self.assertEqual(definition.default_config["employer_name"], company)
                self.assertIs(type(definition.adapter_factory()), AshbyJobAdapter)
        self.assertNotIn("elevenlabs", GLOBAL_SOURCE_ORDER)
        self.assertNotIn("replit", GLOBAL_SOURCE_ORDER)

    def test_wave1_real_contract_fixtures_convert_without_warnings(self) -> None:
        for path, company in (
            (ELEVENLABS_FIXTURE, "ElevenLabs"),
            (REPLIT_FIXTURE, "Replit"),
        ):
            with self.subTest(company=company):
                batch = ingest_batch(
                    tenant_payload(path)["jobs"],
                    AshbyJobAdapter(company, employer_name=company),
                )
                self.assertEqual((batch.converted_count, batch.warning_count), (2, 0))
                self.assertEqual({job.company for job in batch.opportunities}, {company})

    def test_tenant_does_not_infer_brazil_eligibility_or_worldwide(self) -> None:
        record = dict(tenant_payload(ELEVENLABS_FIXTURE)["jobs"][0])
        record.update(title="Account Executive", location="United States")
        result = AshbyJobAdapter("ElevenLabs", employer_name="ElevenLabs").adapt(record)
        self.assertIsNone(result.opportunity.brazil_eligible)
        pipeline = process_opportunities([result.opportunity], create_daniel_profile())
        self.assertNotEqual(pipeline.ranked_opportunities[0].retention_decision.value, "KEEP")

        record.update(location="Remote")
        remote = AshbyJobAdapter("ElevenLabs", employer_name="ElevenLabs").adapt(record)
        self.assertIsNone(remote.opportunity.brazil_eligible)
        remote_pipeline = process_opportunities([remote.opportunity], create_daniel_profile())
        self.assertNotEqual(remote_pipeline.ranked_opportunities[0].eligibility.value, "ELIGIBLE")

    def test_generic_factory_supports_another_tenant(self) -> None:
        definitions = create_ashby_definitions([
            AshbyTenantConfig("example", "Example Careers", "example", "Example Inc")
        ])
        self.assertEqual(definitions[0].source_instance, "ashby:example")
        self.assertEqual(definitions[0].adapter_factory().employer_name, "Example Inc")

    def test_tenant_failure_does_not_stop_another_source(self) -> None:
        class StubSource:
            def __init__(self, result): self.result = result
            def fetch(self): return self.result

        failed = create_ashby_definitions(
            [AshbyTenantConfig("failed", "Failed", "failed")],
            source_overrides={"failed": StubSource(SourceResult(SourceStatus.TIMEOUT, [], "timeout"))},
        )[0]
        good = create_ashby_definitions(
            [AshbyTenantConfig("latamcent", "LatamCent", "latamcent")],
            source_overrides={"latamcent": StubSource(SourceResult(SourceStatus.SUCCESS, [fixture_payload()["jobs"][0]]))},
        )[0]
        result = MultiSourceDiscovery(registry=SourceRegistry([failed, good])).run(create_daniel_profile())
        self.assertEqual(result.sources_failed, ["Failed"])
        self.assertEqual(result.jobs_converted_by_source["LatamCent"], 1)

    def test_wave1_tenant_failures_are_isolated_in_both_directions(self) -> None:
        class StubSource:
            def __init__(self, result): self.result = result
            def fetch(self): return self.result

        configs = {
            "elevenlabs": AshbyTenantConfig(
                "elevenlabs", "ElevenLabs", "elevenlabs", "ElevenLabs"
            ),
            "replit": AshbyTenantConfig("replit", "Replit", "replit", "Replit"),
        }
        fixtures = {
            "elevenlabs": tenant_payload(ELEVENLABS_FIXTURE)["jobs"][0],
            "replit": tenant_payload(REPLIT_FIXTURE)["jobs"][0],
        }
        for good_key, failed_key in (
            ("elevenlabs", "replit"), ("replit", "elevenlabs")
        ):
            with self.subTest(good=good_key):
                definitions = create_ashby_definitions(
                    [configs[good_key], configs[failed_key]],
                    source_overrides={
                        good_key: StubSource(SourceResult(
                            SourceStatus.SUCCESS, [fixtures[good_key]]
                        )),
                        failed_key: StubSource(SourceResult(
                            SourceStatus.TIMEOUT, [], "timeout"
                        )),
                    },
                )
                result = MultiSourceDiscovery(registry=SourceRegistry(definitions)).run(
                    create_daniel_profile()
                )
                self.assertEqual(
                    result.sources_succeeded, [configs[good_key].publisher_name]
                )
                self.assertEqual(
                    result.sources_failed, [configs[failed_key].publisher_name]
                )
                self.assertEqual(result.source_executions_by_id[good_key].converted, 1)

    def test_failed_wave1_tenant_does_not_record_lifecycle_miss(self) -> None:
        definition = create_ashby_definitions([
            AshbyTenantConfig("replit", "Replit", "replit", "Replit")
        ])[0]
        job = definition.adapter_factory().adapt(
            tenant_payload(REPLIT_FIXTURE)["jobs"][0]
        ).opportunity
        job.source_id = definition.source_id
        job.source_family = definition.source_family
        job.source_instance = definition.source_instance
        job.source_type = definition.source_type.value
        job.lifecycle_authority = definition.capabilities.lifecycle_authority.value
        pipeline = process_opportunities([job], create_daniel_profile())
        with JobRepository(":memory:") as repository:
            sync_opportunities(pipeline, repository)
            lifecycle = reconcile_lifecycle(
                repository,
                seen_internal_ids=set(),
                successful_sources=set(),
                successful_source_identities={
                    ("ashby", "ashby:elevenlabs"),
                },
                now=datetime(2026, 8, 18, tzinfo=timezone.utc),
            )
            self.assertEqual(lifecycle.misses_recorded, 0)

    def test_pipeline_uses_existing_decisions_without_scoring_changes(self) -> None:
        batch = ingest_batch(fixture_payload()["jobs"], AshbyJobAdapter("LatamCent"))
        pipeline = process_opportunities(batch.opportunities, create_daniel_profile())
        self.assertEqual(pipeline.total_received, 9)
        self.assertEqual(pipeline.keep_count + pipeline.review_count + pipeline.reject_count, 9)

    def test_cross_source_duplicate_keeps_true_employer_and_two_observations(self) -> None:
        url = "https://example.com/jobs/ae"
        authoritative = JobOpportunity(
            company="Example SaaS", role="Account Executive - LATAM", job_url=url,
            source="Himalayas", location="LATAM", remote=True, brazil_eligible=True,
            source_id="himalayas", source_family="himalayas", source_instance="himalayas:global",
            source_type="GLOBAL_BOARD", lifecycle_authority="OBSERVATIONAL",
        )
        ashby = AshbyJobAdapter("LatamCent").adapt({
            **fixture_payload()["jobs"][0], "jobUrl": url,
        }).opportunity
        ashby.source_id, ashby.source_family = "latamcent", "ashby"
        ashby.source_instance, ashby.source_type = "ashby:latamcent", "TENANT_BOARD"
        ashby.lifecycle_authority = "OBSERVATIONAL"
        pipeline = process_opportunities([authoritative, ashby], create_daniel_profile())
        self.assertEqual((pipeline.unique_opportunities, pipeline.duplicates_detected), (1, 1))
        with JobRepository(":memory:") as repository:
            sync_opportunities(pipeline, repository)
            stored = repository.list_all()[0]
            self.assertEqual(stored.opportunity.company, "Example SaaS")
            self.assertEqual(repository.observation_count(), 2)
            self.assertEqual(
                {item.source_instance for item in repository.get_observations(stored.internal_id)},
                {"himalayas:global", "ashby:latamcent"},
            )

            observations = repository.get_observations(stored.internal_id)
            himalayas_observation = next(
                item for item in observations
                if item.source_instance == "himalayas:global"
            )
            lifecycle = reconcile_lifecycle(
                repository,
                seen_internal_ids={stored.internal_id},
                seen_observation_ids={himalayas_observation.observation_id},
                successful_sources=set(),
                successful_source_identities={
                    ("himalayas", "himalayas:global"),
                    ("ashby", "ashby:latamcent"),
                },
                now=datetime(2026, 8, 18, tzinfo=timezone.utc),
            )
            self.assertEqual(lifecycle.misses_recorded, 0)
            self.assertEqual(
                repository.get(stored.internal_id).opportunity.lifecycle_status,
                JobLifecycleStatus.OPEN,
            )

    def test_wwr_and_elevenlabs_duplicate_preserve_two_observations(self) -> None:
        url = "https://example.com/jobs/strategic-ae-brazil"
        elevenlabs = AshbyJobAdapter("ElevenLabs", employer_name="ElevenLabs").adapt({
            **tenant_payload(ELEVENLABS_FIXTURE)["jobs"][0], "jobUrl": url,
        }).opportunity
        elevenlabs.source_id, elevenlabs.source_family = "elevenlabs", "ashby"
        elevenlabs.source_instance = "ashby:elevenlabs"
        elevenlabs.source_type = "TENANT_BOARD"
        elevenlabs.lifecycle_authority = "OBSERVATIONAL"
        wwr = JobOpportunity(
            company="ElevenLabs", role=elevenlabs.role, job_url=url,
            source="We Work Remotely", location="Brazil", remote=True,
            brazil_eligible=None,
            source_id="weworkremotely", source_family="weworkremotely",
            source_instance="weworkremotely:sales-marketing", source_type="FEED",
            lifecycle_authority="OBSERVATIONAL",
        )
        pipeline = process_opportunities([wwr, elevenlabs], create_daniel_profile())
        self.assertEqual(
            (pipeline.unique_opportunities, pipeline.duplicates_detected), (1, 1)
        )
        with JobRepository(":memory:") as repository:
            sync_opportunities(pipeline, repository)
            stored = repository.list_all()[0]
            self.assertEqual(repository.observation_count(), 2)
            self.assertEqual(
                {item.source_instance for item in repository.get_observations(stored.internal_id)},
                {"weworkremotely:sales-marketing", "ashby:elevenlabs"},
            )


if __name__ == "__main__":
    unittest.main()
