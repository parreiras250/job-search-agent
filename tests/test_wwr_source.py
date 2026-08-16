"""Testes totalmente offline do RSS Sales and Marketing do WWR."""

import socket
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError

from daniel_job_agent import (
    GeographicEligibility,
    AgentRunHistory,
    DanielJobAgent,
    JobRepository,
    LifecycleAuthority,
    MultiSourceDiscovery,
    SourceStatus,
    SourceResult,
    SourceType,
    WeWorkRemotelyJobAdapter,
    WeWorkRemotelyJobSource,
    create_daniel_profile,
    create_default_source_registry,
    build_weekly_report,
    enrich_opportunities,
    evaluate_geographic_eligibility,
    ingest_batch,
    process_opportunities,
)
from daniel_job_agent.sources import HttpResponse


FIXTURE = Path(__file__).parent / "fixtures" / "wwr_sales_marketing.xml"


class FakeTransport:
    def __init__(self, body: bytes = b"", *, status: int = 200, error=None):
        self.body = body
        self.status = status
        self.error = error
        self.calls = []

    def get(self, url, timeout, headers):
        self.calls.append((url, timeout, headers))
        if self.error is not None:
            raise self.error
        return HttpResponse(self.status, self.body)


class StubSource:
    def __init__(self, source_result):
        self.source_result = source_result
        self.calls = 0

    def fetch(self):
        self.calls += 1
        return self.source_result


def fixture_source() -> tuple[WeWorkRemotelyJobSource, FakeTransport]:
    transport = FakeTransport(FIXTURE.read_bytes())
    return WeWorkRemotelyJobSource(transport=transport), transport


class WeWorkRemotelySourceTests(unittest.TestCase):
    def test_parses_realistic_rss_with_one_request(self) -> None:
        source, transport = fixture_source()
        output = source.fetch()
        self.assertEqual(output.status, SourceStatus.SUCCESS)
        self.assertEqual(len(output.records), 5)
        self.assertEqual(len(transport.calls), 1)
        first = output.records[0]
        self.assertEqual(first["company"], "Alpha SaaS")
        self.assertEqual(first["role"], "Account Executive")
        self.assertEqual(first["location"], "Anywhere in the World")
        self.assertEqual(first["date_posted"], "2026-08-15T10:30:00+00:00")
        self.assertEqual(
            first["job_url"],
            "https://weworkremotely.com/remote-jobs/alpha-account-executive",
        )

    def test_empty_feed_is_successful_no_jobs(self) -> None:
        body = b"<rss version='2.0'><channel><title>Empty</title></channel></rss>"
        output = WeWorkRemotelyJobSource(transport=FakeTransport(body)).fetch()
        self.assertEqual(output.status, SourceStatus.NO_JOBS)
        self.assertTrue(output.success)

    def test_invalid_unexpected_and_unsafe_xml_are_controlled(self) -> None:
        payloads = (
            b"not xml",
            b"<feed><entry /></feed>",
            b"<!DOCTYPE rss><rss><channel /></rss>",
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                output = WeWorkRemotelyJobSource(
                    transport=FakeTransport(payload)
                ).fetch()
                self.assertEqual(output.status, SourceStatus.INVALID_PAYLOAD)

    def test_http_timeout_and_network_errors_are_structured(self) -> None:
        cases = (
            (FakeTransport(status=500), SourceStatus.HTTP_ERROR),
            (FakeTransport(error=socket.timeout()), SourceStatus.TIMEOUT),
            (FakeTransport(error=URLError("offline")), SourceStatus.CONNECTION_ERROR),
        )
        for transport, expected in cases:
            with self.subTest(expected=expected):
                output = WeWorkRemotelyJobSource(transport=transport).fetch()
                self.assertEqual(output.status, expected)


class WeWorkRemotelyAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        source, _ = fixture_source()
        self.records = source.fetch().records

    def test_adapter_preserves_attribution_url_and_conservative_unknown(self) -> None:
        output = WeWorkRemotelyJobAdapter().adapt(self.records[0])
        self.assertTrue(output.success)
        job = output.opportunity
        assert job is not None
        self.assertEqual(job.source, "We Work Remotely")
        self.assertEqual(
            job.job_url,
            "https://weworkremotely.com/remote-jobs/alpha-account-executive",
        )
        self.assertTrue(job.remote)
        self.assertIsNone(job.brazil_eligible)
        self.assertEqual(job.external_id, job.job_url)
        self.assertEqual(job.employment_type, "Full-Time")
        self.assertIsNone(job.salary_text)

    def test_optional_invalid_date_warns_without_losing_job(self) -> None:
        output = WeWorkRemotelyJobAdapter().adapt(self.records[2])
        self.assertTrue(output.success)
        self.assertIsNone(output.opportunity.date_posted)  # type: ignore[union-attr]
        self.assertEqual([warning.field for warning in output.warnings], ["date_posted"])

    def test_missing_optional_values_do_not_warn(self) -> None:
        record = dict(self.records[0])
        for name in ("description", "date_posted", "external_id", "employment_type"):
            record[name] = None
        output = WeWorkRemotelyJobAdapter().adapt(record)
        self.assertTrue(output.success)
        self.assertEqual(output.warnings, [])

    def test_enrichment_and_pipeline_reuse_existing_rules(self) -> None:
        batch = ingest_batch(self.records, WeWorkRemotelyJobAdapter())
        pipeline = process_opportunities(
            enrich_opportunities(batch.opportunities), create_daniel_profile()
        )
        account = next(
            item for item in pipeline.ranked_opportunities
            if item.normalized_job.role == "Account Executive"
        )
        engineer = next(
            item for item in pipeline.ranked_opportunities
            if item.normalized_job.role == "Software Engineer"
        )
        sdr = next(
            item for item in pipeline.ranked_opportunities
            if item.normalized_job.role == "Sales Development Representative"
        )
        self.assertEqual(sdr.retention_decision.value, "KEEP")
        self.assertEqual(account.retention_decision.value, "REVIEW")
        self.assertEqual(engineer.retention_decision.value, "REJECT")
        self.assertEqual(
            evaluate_geographic_eligibility(account.normalized_job.location),
            GeographicEligibility.UNKNOWN,
        )


class WeWorkRemotelyRegistryIntegrationTests(unittest.TestCase):
    def test_default_definition_is_feed_attributed_observational_and_budgeted(self) -> None:
        definition = create_default_source_registry().get("weworkremotely")
        self.assertEqual(definition.source_type, SourceType.FEED)
        self.assertEqual(definition.source_instance, "weworkremotely:sales-marketing")
        self.assertFalse(definition.capabilities.supports_query)
        self.assertTrue(definition.capabilities.requires_attribution)
        self.assertEqual(
            definition.capabilities.lifecycle_authority,
            LifecycleAuthority.OBSERVATIONAL,
        )
        self.assertEqual(definition.request_budget, 1)

    def test_generic_discovery_runs_three_sources_and_isolates_wwr_failure(self) -> None:
        empty = SourceStatus.NO_JOBS
        jobicy = StubSource(SourceResult(empty, []))
        remotive = StubSource(SourceResult(empty, []))
        wwr = StubSource(SourceResult(SourceStatus.CONNECTION_ERROR, [], "offline"))
        output = MultiSourceDiscovery(
            jobicy_source=jobicy, remotive_source=remotive, wwr_source=wwr
        ).run(create_daniel_profile())
        self.assertEqual(
            output.sources_attempted, ["Jobicy", "Remotive", "We Work Remotely"]
        )
        self.assertEqual(output.sources_succeeded, ["Jobicy", "Remotive"])
        self.assertEqual(output.sources_failed, ["We Work Remotely"])
        self.assertEqual([jobicy.calls, remotive.calls, wwr.calls], [1, 1, 1])

    def test_cross_source_duplicate_uses_existing_global_dedup(self) -> None:
        source, _ = fixture_source()
        wwr_result = source.fetch()
        jobicy_record = {
            "id": 99,
            "url": "https://jobicy.com/jobs/alpha-ae",
            "jobTitle": "Account Executive",
            "companyName": "Alpha SaaS",
            "jobGeo": "LATAM",
            "jobDescription": "Own the full sales cycle for B2B SaaS customers.",
        }
        output = MultiSourceDiscovery(
            jobicy_source=StubSource(SourceResult(SourceStatus.SUCCESS, [jobicy_record])),
            remotive_source=StubSource(SourceResult(SourceStatus.NO_JOBS, [])),
            wwr_source=StubSource(wwr_result),
        ).run(create_daniel_profile())
        self.assertGreaterEqual(output.global_duplicates, 1)
        self.assertGreaterEqual(output.cross_source_duplicates, 1)

    def test_weekly_report_and_lifecycle_use_wwr_structured_identity(self) -> None:
        source, _ = fixture_source()
        wwr_result = source.fetch()
        empty = SourceResult(SourceStatus.NO_JOBS, [])
        with JobRepository(":memory:") as repository:
            first = DanielJobAgent(
                repository,
                discovery=MultiSourceDiscovery(
                    jobicy_source=StubSource(empty), remotive_source=StubSource(empty),
                    wwr_source=StubSource(wwr_result),
                ),
            ).run()
            timestamp = datetime(2026, 8, 16, tzinfo=timezone.utc)
            history = AgentRunHistory(
                1, timestamp, timestamp, "SUCCESS", first.sources_succeeded, [],
                first.jobs_received, first.new, 0, 0, 0, 0, 0, 0, None, None,
            )
            report = build_weekly_report(repository, history, first)
            second = DanielJobAgent(
                repository,
                discovery=MultiSourceDiscovery(
                    jobicy_source=StubSource(empty), remotive_source=StubSource(empty),
                    wwr_source=StubSource(empty),
                ),
            ).run()
        self.assertEqual(
            [item.name for item in report.sources],
            ["Jobicy", "Remotive", "We Work Remotely"],
        )
        self.assertEqual(report.sources[2].received, 5)
        self.assertEqual(second.lifecycle.misses_recorded, 5)
        wwr_job = first.discovery.ranking[0].normalized_job
        self.assertEqual(
            (wwr_job.source_family, wwr_job.source_instance),
            ("weworkremotely", "weworkremotely:sales-marketing"),
        )


if __name__ == "__main__":
    unittest.main()
