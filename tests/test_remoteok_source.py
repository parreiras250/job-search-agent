"""Testes totalmente offline do JSON feed público do RemoteOK."""

import json
import socket
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError

from daniel_job_agent import (
    AgentRunHistory,
    DanielJobAgent,
    JobOpportunity,
    JobRepository,
    LifecycleAuthority,
    MultiSourceDiscovery,
    RemoteOKJobAdapter,
    RemoteOKJobSource,
    SourceResult,
    SourceStatus,
    SourceType,
    build_weekly_report,
    create_daniel_profile,
    create_default_source_registry,
    format_weekly_report,
    ingest_batch,
    measure_source_contributions,
    process_opportunities,
    reconcile_lifecycle,
    sync_opportunities,
)
from daniel_job_agent.sources import HttpResponse, REMOTEOK_API_URL


FIXTURE = Path(__file__).parent / "fixtures" / "remoteok_jobs.json"
NOW = datetime(2026, 8, 17, 12, tzinfo=timezone.utc)


def fixture_payload():
    return json.loads(FIXTURE.read_text())


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


class StubSource:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def fetch(self):
        self.calls += 1
        return self.result


class RemoteOKSourceTests(unittest.TestCase):
    def test_official_json_feed_uses_one_request_and_removes_metadata(self) -> None:
        transport = FakeTransport(fixture_payload())
        result = RemoteOKJobSource(transport=transport).fetch()
        self.assertEqual(REMOTEOK_API_URL, "https://remoteok.com/api")
        self.assertEqual(result.status, SourceStatus.SUCCESS)
        self.assertEqual(len(result.records), 8)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(result.records[0]["id"], "201")
        self.assertTrue(all("legal" not in item for item in result.records))

    def test_empty_and_metadata_only_feeds_are_successful_no_jobs(self) -> None:
        for payload in ([], fixture_payload()[:1]):
            with self.subTest(payload=payload):
                result = RemoteOKJobSource(transport=FakeTransport(payload)).fetch()
                self.assertEqual(result.status, SourceStatus.NO_JOBS)
                self.assertTrue(result.success)

    def test_invalid_json_and_payload_shapes_are_controlled(self) -> None:
        for payload in (b"not-json", {}, ["not-an-object"]):
            with self.subTest(payload=payload):
                result = RemoteOKJobSource(transport=FakeTransport(payload)).fetch()
                self.assertEqual(result.status, SourceStatus.INVALID_PAYLOAD)

    def test_http_timeout_and_connection_errors_are_controlled(self) -> None:
        cases = (
            (FakeTransport(status=500), SourceStatus.HTTP_ERROR),
            (FakeTransport(error=HTTPError(REMOTEOK_API_URL, 429, "rate", {}, None)), SourceStatus.HTTP_ERROR),
            (FakeTransport(error=socket.timeout()), SourceStatus.TIMEOUT),
            (FakeTransport(error=URLError("offline")), SourceStatus.CONNECTION_ERROR),
        )
        for transport, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(RemoteOKJobSource(transport=transport).fetch().status, expected)


class RemoteOKAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.records = RemoteOKJobSource(
            transport=FakeTransport(fixture_payload())
        ).fetch().records

    def test_maps_identity_salary_location_tags_date_and_attribution(self) -> None:
        result = RemoteOKJobAdapter().adapt(self.records[0])
        self.assertTrue(result.success)
        self.assertEqual(result.warnings, [])
        job = result.opportunity
        assert job is not None
        self.assertEqual(job.external_id, "201")
        self.assertEqual(job.source, "RemoteOK")
        self.assertEqual(job.job_url, self.records[0]["url"])
        self.assertEqual((job.salary_min, job.salary_max), (80000.0, 120000.0))
        self.assertEqual(job.industries_mentioned, ["sales", "saas", "full time"])
        self.assertEqual(job.employment_type, "full time")
        self.assertEqual(job.location_restrictions[0].name, "Worldwide")
        self.assertEqual(job.date_posted.isoformat(), "2026-08-12")
        self.assertTrue(job.remote)
        self.assertIsNone(job.brazil_eligible)

    def test_zero_salary_is_unknown_and_missing_location_is_not_worldwide(self) -> None:
        no_salary = RemoteOKJobAdapter().adapt(self.records[1]).opportunity
        missing_location = RemoteOKJobAdapter().adapt(self.records[6]).opportunity
        assert no_salary is not None and missing_location is not None
        self.assertIsNone(no_salary.salary_min)
        self.assertIsNone(no_salary.salary_max)
        self.assertEqual(missing_location.location, "Remote")
        self.assertIsNone(missing_location.location_restrictions)
        self.assertIsNone(missing_location.brazil_eligible)

    def test_malformed_optional_fields_warn_without_losing_job(self) -> None:
        result = RemoteOKJobAdapter().adapt(self.records[-1])
        self.assertTrue(result.success)
        self.assertEqual(
            {item.field for item in result.warnings},
            {"industries_mentioned", "date_posted", "salary_min"},
        )
        self.assertIsNone(result.opportunity.salary_min)  # type: ignore[union-attr]

    def test_batch_has_expected_roles_and_required_field_error_is_isolated(self) -> None:
        records = [*self.records, {"position": "Missing required fields"}]
        batch = ingest_batch(records, RemoteOKJobAdapter())
        self.assertEqual(batch.converted_count, 8)
        self.assertEqual(batch.error_count, 1)
        pipeline = process_opportunities(batch.opportunities, create_daniel_profile())
        decisions = {
            item.normalized_job.role: item.retention_decision.value
            for item in pipeline.ranked_opportunities
        }
        self.assertEqual(decisions["Sales Development Representative"], "KEEP")
        self.assertEqual(decisions["Software Engineer"], "REJECT")


class RemoteOKIntegrationTests(unittest.TestCase):
    def test_definition_capabilities_identity_and_budget(self) -> None:
        definition = create_default_source_registry().get("remoteok")
        self.assertEqual(definition.source_type, SourceType.GLOBAL_BOARD)
        self.assertEqual(definition.source_family, "remoteok")
        self.assertEqual(definition.source_instance, "remoteok:global")
        self.assertTrue(definition.capabilities.global_search)
        self.assertFalse(definition.capabilities.supports_query)
        self.assertTrue(definition.capabilities.provides_description)
        self.assertTrue(definition.capabilities.provides_salary)
        self.assertFalse(definition.capabilities.requires_auth)
        self.assertTrue(definition.capabilities.requires_attribution)
        self.assertEqual(definition.capabilities.lifecycle_authority, LifecycleAuthority.OBSERVATIONAL)
        self.assertEqual(definition.request_budget, 1)

    def test_remoteok_and_wwr_create_one_job_with_two_observations(self) -> None:
        remoteok = RemoteOKJobAdapter().adapt(fixture_payload()[1]).opportunity
        assert remoteok is not None
        remoteok.source_id = "remoteok"
        remoteok.source_family = "remoteok"
        remoteok.source_instance = "remoteok:global"
        remoteok.source_type = "GLOBAL_BOARD"
        remoteok.lifecycle_authority = "OBSERVATIONAL"
        wwr = JobOpportunity(
            company=remoteok.company, role=remoteok.role,
            job_url="https://weworkremotely.com/remote-jobs/acme-ae",
            source="We Work Remotely", location="Worldwide", remote=True,
            brazil_eligible=None, source_id="weworkremotely",
            source_family="weworkremotely",
            source_instance="weworkremotely:sales-marketing",
            source_type="FEED", lifecycle_authority="OBSERVATIONAL",
        )
        with JobRepository(":memory:") as repository:
            synced = sync_opportunities(
                process_opportunities([wwr, remoteok], create_daniel_profile()), repository
            )
            self.assertEqual(repository.count(), 1)
            self.assertEqual(repository.observation_count(), 2)
            self.assertEqual(synced.cross_source_observations_added, 1)

    def test_lifecycle_failure_has_no_miss_successful_absence_has_miss(self) -> None:
        job = RemoteOKJobAdapter().adapt(fixture_payload()[1]).opportunity
        assert job is not None
        job.source_id, job.source_family = "remoteok", "remoteok"
        job.source_instance, job.source_type = "remoteok:global", "GLOBAL_BOARD"
        job.lifecycle_authority = "OBSERVATIONAL"
        with JobRepository(":memory:") as repository:
            synced = sync_opportunities(
                process_opportunities([job], create_daniel_profile()), repository, now=NOW
            )
            internal_id = synced.new_jobs[0].internal_id
            failed = reconcile_lifecycle(
                repository, seen_internal_ids=set(), successful_sources=set(),
                successful_source_identities=set(), seen_observation_ids=set(),
                now=NOW + timedelta(days=1),
            )
            self.assertEqual(failed.misses_recorded, 0)
            success = reconcile_lifecycle(
                repository, seen_internal_ids=set(), successful_sources=set(),
                successful_source_identities={("remoteok", "remoteok:global")},
                seen_observation_ids=set(), now=NOW + timedelta(days=2),
            )
            self.assertEqual(success.misses_recorded, 1)
            self.assertEqual(repository.get(internal_id).opportunity.consecutive_misses, 1)  # type: ignore[union-attr]

    def test_failure_isolated_and_reporting_and_contribution_are_generic(self) -> None:
        empty = StubSource(SourceResult(SourceStatus.NO_JOBS, []))
        failed = StubSource(SourceResult(SourceStatus.CONNECTION_ERROR, [], "offline"))
        registry = create_default_source_registry(
            jobicy_source=empty, remotive_source=empty, wwr_source=empty,
            himalayas_source=empty, remoteok_source=failed,
            getonboard_source=empty,
        )
        with JobRepository(":memory:") as repository:
            result = DanielJobAgent(
                repository, discovery=MultiSourceDiscovery(registry=registry), clock=lambda: NOW
            ).run()
            history = AgentRunHistory(
                1, NOW, NOW, "PARTIAL_SUCCESS", result.sources_succeeded,
                result.sources_failed, 0, 0, 0, 0, 0, 0, 0, 0, None, None,
            )
            report = format_weekly_report(build_weekly_report(repository, history, result))
        self.assertEqual(result.sources_failed, ["RemoteOK"])
        contribution = result.discovery.source_contributions.contributions["remoteok"]
        self.assertEqual(contribution.status, "FAILED")
        self.assertIsNone(contribution.incremental_unique)
        self.assertIn("RemoteOK: FAILED", report)
        self.assertIn("RemoteOK: contribution unavailable (FAILED)", report)


@dataclass(frozen=True)
class Summary:
    received: int
    converted: int
    succeeded: bool = True


class RemoteOKContributionTests(unittest.TestCase):
    def test_remoteok_is_fifth_and_gets_only_post_baseline_increment(self) -> None:
        base = JobOpportunity(
            company="Overlap", role="Account Executive", job_url="https://h.example/1",
            source="Himalayas", location="LATAM", remote=True, brazil_eligible=True,
            source_id="himalayas",
        )
        overlap = JobOpportunity(
            company="Overlap", role="Account Executive", job_url="https://r.example/1",
            source="RemoteOK", location="LATAM", remote=True, brazil_eligible=True,
            source_id="remoteok",
        )
        only = JobOpportunity(
            company="Only RemoteOK", role="Sales Engineer", job_url="https://r.example/2",
            source="RemoteOK", location="LATAM", remote=True, brazil_eligible=True,
            source_id="remoteok",
        )
        summaries = {
            source_id: Summary(0, 0)
            for source_id in ("jobicy", "remotive", "weworkremotely")
        }
        summaries.update({"himalayas": Summary(1, 1), "remoteok": Summary(2, 2)})
        result = measure_source_contributions(
            process_opportunities([base, overlap, only], create_daniel_profile()), summaries
        )
        self.assertEqual(result.operational_order[-2:], ("remoteok", "getonboard"))
        remoteok = result.contributions["remoteok"]
        self.assertEqual(remoteok.unique_contributed, 2)
        self.assertEqual(remoteok.incremental_unique, 1)
        self.assertEqual(remoteok.incremental_review, 1)
        self.assertEqual(remoteok.incremental_relevant, 1)
        self.assertEqual(result.overlap_matrix[("himalayas", "remoteok")], 1)


if __name__ == "__main__":
    unittest.main()
