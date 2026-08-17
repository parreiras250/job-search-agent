"""Testes totalmente offline da API pública Himalayas."""

import json
from copy import deepcopy
import socket
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

from daniel_job_agent import (
    AgentRunHistory,
    DanielJobAgent,
    GeographicEligibility,
    HimalayasJobAdapter,
    HimalayasJobSource,
    JobOpportunity,
    JobRepository,
    LifecycleAuthority,
    MultiSourceDiscovery,
    SourceRegistry,
    SourceStatus,
    SourceType,
    build_himalayas_jobs_url,
    build_weekly_report,
    create_daniel_profile,
    create_default_source_registry,
    enrich_opportunities,
    evaluate_geographic_eligibility,
    format_weekly_report,
    ingest_batch,
    process_opportunities,
    reconcile_lifecycle,
    sync_opportunities,
)
from daniel_job_agent.sources import HttpResponse, SourceResult
from daniel_job_agent.himalayas_demo import (
    format_payload_shape,
    format_timezone_restriction,
)


FIXTURE = Path(__file__).parent / "fixtures" / "himalayas_jobs.json"
NOW = datetime(2026, 8, 17, 12, tzinfo=timezone.utc)


def fixture_payload() -> dict[str, object]:
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
    def __init__(self, result: SourceResult):
        self.result = result
        self.calls = 0

    def fetch(self) -> SourceResult:
        self.calls += 1
        return self.result


class HimalayasPayloadShapeDebugTests(unittest.TestCase):
    def test_formatter_is_safe_structural_truncated_and_limited_to_three_jobs(self) -> None:
        records = [
            {
                "description": "SENSITIVE DESCRIPTION " * 100,
                "locationRestrictions": [
                    {"alpha2": "US", "name": "United States", "slug": "united-states"}
                ],
                "timezoneRestrictions": {"unexpected": ["UTC-05:00"]},
            },
            {"locationRestrictions": [], "timezoneRestrictions": ["UTC-03:00"]},
            {"locationRestrictions": "Anywhere", "timezoneRestrictions": None},
            {
                "locationRestrictions": ["MUST NOT APPEAR"],
                "timezoneRestrictions": ["MUST NOT APPEAR"],
            },
        ]

        output = format_payload_shape(records)

        self.assertIn("Job 1", output)
        self.assertIn("Job 3", output)
        self.assertNotIn("Job 4", output)
        self.assertIn("locationRestrictions type: list", output)
        self.assertIn("timezoneRestrictions type: dict", output)
        self.assertIn(
            "locationRestrictions first item keys: ['alpha2', 'name', 'slug']",
            output,
        )
        self.assertIn("timezoneRestrictions first item type: str", output)
        self.assertNotIn("SENSITIVE DESCRIPTION", output)
        self.assertNotIn("MUST NOT APPEAR", output)

    def test_numeric_timezone_formatter_handles_integer_and_half_hours(self) -> None:
        self.assertEqual(format_timezone_restriction(-5), "UTC-05:00")
        self.assertEqual(format_timezone_restriction(5.5), "UTC+05:30")
        self.assertEqual(format_timezone_restriction(-3.5), "UTC-03:30")
        self.assertEqual(format_timezone_restriction("UTC-04:00"), "UTC-04:00")


class HimalayasSourceTests(unittest.TestCase):
    def test_url_uses_one_conservative_sales_page_without_country_filter(self) -> None:
        parts = urlsplit(build_himalayas_jobs_url())
        self.assertEqual(
            f"{parts.scheme}://{parts.netloc}{parts.path}",
            "https://himalayas.app/jobs/api/search",
        )
        self.assertEqual(
            parse_qs(parts.query),
            {"q": ["sales"], "sort": ["recent"], "page": ["1"]},
        )
        self.assertNotIn("country", parse_qs(parts.query))

    def test_valid_payload_parses_with_exactly_one_get(self) -> None:
        transport = FakeTransport(fixture_payload())
        result = HimalayasJobSource(transport=transport).fetch()
        self.assertEqual(result.status, SourceStatus.SUCCESS)
        self.assertEqual(len(result.records), 8)
        self.assertEqual(len(transport.calls), 1)

    def test_empty_response_is_success(self) -> None:
        payload = fixture_payload()
        payload["jobs"] = []
        payload["totalCount"] = 0
        result = HimalayasJobSource(transport=FakeTransport(payload)).fetch()
        self.assertEqual(result.status, SourceStatus.NO_JOBS)
        self.assertTrue(result.success)

    def test_invalid_json_shape_and_pagination_metadata_are_controlled(self) -> None:
        invalid_payloads = [
            b"not-json", [], {}, {"jobs": "invalid"},
            {**fixture_payload(), "offset": -1},
            {**fixture_payload(), "limit": 21},
            {**fixture_payload(), "totalCount": "8"},
            {**fixture_payload(), "updatedAt": None},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                result = HimalayasJobSource(transport=FakeTransport(payload)).fetch()
                self.assertEqual(result.status, SourceStatus.INVALID_PAYLOAD)

    def test_http_timeout_and_connection_failures_are_controlled(self) -> None:
        cases = (
            (FakeTransport(status=400), SourceStatus.HTTP_ERROR),
            (FakeTransport(status=429), SourceStatus.HTTP_ERROR),
            (FakeTransport(error=socket.timeout()), SourceStatus.TIMEOUT),
            (FakeTransport(error=URLError("offline")), SourceStatus.CONNECTION_ERROR),
        )
        for transport, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    HimalayasJobSource(transport=transport).fetch().status, expected
                )


class HimalayasAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.records = fixture_payload()["jobs"]

    def test_adapter_preserves_identity_location_timezone_salary_and_date(self) -> None:
        result = HimalayasJobAdapter().adapt(self.records[0])
        self.assertTrue(result.success)
        job = result.opportunity
        assert job is not None
        self.assertEqual(job.external_id, "latam-ae-1")
        self.assertEqual(job.company, "Latam SaaS")
        self.assertEqual(job.location, "Brazil, Mexico")
        self.assertEqual(
            [(item.alpha2, item.name, item.slug) for item in job.location_restrictions],
            [(None, "Brazil", None), (None, "Mexico", None)],
        )
        self.assertEqual(
            job.timezone_restrictions,
            [-10, -9, -8, -7, -6, -5, 14],
        )
        self.assertEqual((job.salary_min, job.salary_max), (80000.0, 120000.0))
        self.assertEqual((job.salary_currency, job.salary_period), ("USD", "annual"))
        self.assertEqual(job.date_posted.isoformat(), "2026-08-16")
        self.assertEqual(job.job_level, "Mid-level, Senior")
        self.assertEqual(job.source, "Himalayas")
        self.assertTrue(job.remote)
        self.assertTrue(job.brazil_eligible)

    def test_worldwide_and_explicit_incompatible_location_are_conservative(self) -> None:
        worldwide = HimalayasJobAdapter().adapt(self.records[1]).opportunity
        us_only = HimalayasJobAdapter().adapt(self.records[2]).opportunity
        assert worldwide is not None and us_only is not None
        self.assertEqual(worldwide.location, "Worldwide")
        self.assertEqual(worldwide.location_restrictions, [])
        self.assertEqual(worldwide.timezone_restrictions, [])
        self.assertTrue(worldwide.brazil_eligible)
        self.assertFalse(us_only.brazil_eligible)
        self.assertEqual(
            evaluate_geographic_eligibility(worldwide.location),
            GeographicEligibility.ELIGIBLE,
        )
        self.assertEqual(
            evaluate_geographic_eligibility(us_only.location),
            GeographicEligibility.NOT_ELIGIBLE,
        )

    def test_missing_salary_remains_unknown_without_warning(self) -> None:
        result = HimalayasJobAdapter().adapt(self.records[1])
        self.assertTrue(result.success)
        self.assertIsNone(result.opportunity.salary_min)  # type: ignore[union-attr]
        self.assertIsNone(result.opportunity.salary_max)  # type: ignore[union-attr]
        self.assertEqual(result.warnings, [])

    def test_structured_and_mixed_location_formats_are_preserved(self) -> None:
        structured = HimalayasJobAdapter().adapt(self.records[5])
        self.assertEqual(structured.warnings, [])
        restriction = structured.opportunity.location_restrictions[0]  # type: ignore[union-attr]
        self.assertEqual(
            (restriction.alpha2, restriction.name, restriction.slug),
            ("US", "United States", "united-states"),
        )
        mixed_record = dict(self.records[0])
        mixed_record["locationRestrictions"] = [
            "Canada",
            {"alpha2": "US", "name": "United States", "slug": "united-states"},
        ]
        mixed = HimalayasJobAdapter().adapt(mixed_record)
        self.assertEqual(mixed.warnings, [])
        self.assertEqual(
            [item.name for item in mixed.opportunity.location_restrictions],  # type: ignore[union-attr]
            ["Canada", "United States"],
        )

    def test_numeric_timezones_float_and_invalid_bool_are_distinguished(self) -> None:
        india = HimalayasJobAdapter().adapt(self.records[4])
        negative_half = HimalayasJobAdapter().adapt(self.records[6])
        malformed = HimalayasJobAdapter().adapt(self.records[-1])
        self.assertEqual(india.opportunity.timezone_restrictions, [5.5])  # type: ignore[union-attr]
        self.assertEqual(negative_half.opportunity.timezone_restrictions, [-3.5])  # type: ignore[union-attr]
        self.assertIn(
            "timezone_restrictions",
            {warning.field for warning in malformed.warnings},
        )
        self.assertEqual(malformed.opportunity.timezone_restrictions, [-3])  # type: ignore[union-attr]

    def test_malformed_optional_fields_warn_without_losing_job(self) -> None:
        result = HimalayasJobAdapter().adapt(self.records[-1])
        self.assertTrue(result.success)
        fields = {warning.field for warning in result.warnings}
        self.assertEqual(
            fields,
            {"salary_min", "date_posted", "location_restrictions", "timezone_restrictions"},
        )
        self.assertIsNone(result.opportunity.salary_min)  # type: ignore[union-attr]

    def test_real_style_valid_fixture_records_produce_zero_warnings(self) -> None:
        batch = ingest_batch(self.records[:-1], HimalayasJobAdapter())
        self.assertEqual(batch.converted_count, 7)
        self.assertEqual(batch.warning_count, 0)

    def test_pipeline_keeps_sales_candidate_and_rejects_engineering(self) -> None:
        ingestion = ingest_batch(self.records, HimalayasJobAdapter())
        pipeline = process_opportunities(
            enrich_opportunities(ingestion.opportunities), create_daniel_profile()
        )
        sdr = next(item for item in pipeline.ranked_opportunities if item.normalized_job.external_id == "sdr-4")
        engineer = next(item for item in pipeline.ranked_opportunities if item.normalized_job.external_id == "engineering-6")
        self.assertEqual(sdr.retention_decision.value, "KEEP")
        self.assertEqual(engineer.retention_decision.value, "REJECT")

    def test_timezone_fields_survive_sqlite_without_affecting_score(self) -> None:
        job = HimalayasJobAdapter().adapt(self.records[0]).opportunity
        assert job is not None
        without_structured_restrictions = deepcopy(job)
        without_structured_restrictions.location_restrictions = None
        without_structured_restrictions.timezone_restrictions = None
        before = process_opportunities(enrich_opportunities([job]), create_daniel_profile())
        score = before.ranked_opportunities[0].match_score
        comparison = process_opportunities(
            enrich_opportunities([without_structured_restrictions]),
            create_daniel_profile(),
        )
        self.assertEqual(comparison.ranked_opportunities[0].match_score, score)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.db"
            with JobRepository(path) as repository:
                synced = sync_opportunities(before, repository, now=NOW)
                internal_id = synced.new_jobs[0].internal_id
            with JobRepository(path) as repository:
                stored = repository.get(internal_id)
                assert stored is not None
                self.assertEqual(
                    stored.opportunity.timezone_restrictions,
                    [-10, -9, -8, -7, -6, -5, 14],
                )
                self.assertEqual(
                    [
                        (item.alpha2, item.name, item.slug)
                        for item in stored.opportunity.location_restrictions
                    ],
                    [(None, "Brazil", None), (None, "Mexico", None)],
                )
                self.assertEqual(stored.match_score, score)


class HimalayasRegistryProvenanceLifecycleTests(unittest.TestCase):
    def test_default_definition_has_documented_capabilities_and_budget(self) -> None:
        definition = create_default_source_registry().get("himalayas")
        self.assertEqual(definition.source_type, SourceType.GLOBAL_BOARD)
        self.assertEqual(definition.source_instance, "himalayas:global")
        self.assertTrue(definition.capabilities.global_search)
        self.assertTrue(definition.capabilities.supports_query)
        self.assertTrue(definition.capabilities.supports_location_filter)
        self.assertTrue(definition.capabilities.supports_pagination)
        self.assertTrue(definition.capabilities.provides_salary)
        self.assertFalse(definition.capabilities.requires_auth)
        self.assertTrue(definition.capabilities.requires_attribution)
        self.assertEqual(
            definition.capabilities.lifecycle_authority,
            LifecycleAuthority.OBSERVATIONAL,
        )
        self.assertEqual(definition.request_budget, 1)

    def test_himalayas_and_wwr_create_one_opportunity_two_observations(self) -> None:
        himalayas = HimalayasJobAdapter().adapt(self.records()[0]).opportunity
        assert himalayas is not None
        himalayas.source_id = "himalayas"
        himalayas.source_family = "himalayas"
        himalayas.source_instance = "himalayas:global"
        himalayas.source_type = "GLOBAL_BOARD"
        himalayas.lifecycle_authority = "OBSERVATIONAL"
        wwr = JobOpportunity(
            company=himalayas.company, role=himalayas.role,
            job_url="https://weworkremotely.com/remote-jobs/latam-ae-1",
            source="We Work Remotely", location="Brazil", remote=True,
            brazil_eligible=True, external_id="wwr-latam-ae-1",
            source_id="weworkremotely", source_family="weworkremotely",
            source_instance="weworkremotely:sales-marketing", source_type="FEED",
            lifecycle_authority="OBSERVATIONAL",
        )
        with JobRepository(":memory:") as repository:
            result = sync_opportunities(
                process_opportunities([himalayas, wwr], create_daniel_profile()), repository
            )
            self.assertEqual(repository.count(), 1)
            self.assertEqual(repository.observation_count(), 2)
            self.assertEqual(result.cross_source_observations_added, 1)

    @staticmethod
    def records():
        return fixture_payload()["jobs"]

    def test_successful_absence_is_miss_but_failure_is_not(self) -> None:
        job = HimalayasJobAdapter().adapt(self.records()[0]).opportunity
        assert job is not None
        job.source_id = "himalayas"
        job.source_family = "himalayas"
        job.source_instance = "himalayas:global"
        job.source_type = "GLOBAL_BOARD"
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
            succeeded = reconcile_lifecycle(
                repository, seen_internal_ids=set(), successful_sources=set(),
                successful_source_identities={("himalayas", "himalayas:global")},
                seen_observation_ids=set(), now=NOW + timedelta(days=2),
            )
            self.assertEqual(succeeded.misses_recorded, 1)
            self.assertEqual(repository.get(internal_id).opportunity.consecutive_misses, 1)  # type: ignore[union-attr]

    def test_failure_isolated_and_weekly_report_lists_himalayas_generically(self) -> None:
        good = StubSource(SourceResult(SourceStatus.NO_JOBS, []))
        bad = StubSource(SourceResult(SourceStatus.CONNECTION_ERROR, [], "offline"))
        registry = create_default_source_registry(
            jobicy_source=good, remotive_source=good, wwr_source=good,
            himalayas_source=bad,
            remoteok_source=good,
        )
        with JobRepository(":memory:") as repository:
            result = DanielJobAgent(
                repository, discovery=MultiSourceDiscovery(registry=registry),
                clock=lambda: NOW,
            ).run()
            self.assertEqual(result.sources_succeeded, ["Jobicy", "Remotive", "We Work Remotely", "RemoteOK"])
            self.assertEqual(result.sources_failed, ["Himalayas"])
            history = AgentRunHistory(
                1, NOW, NOW, "PARTIAL_SUCCESS", result.sources_succeeded,
                result.sources_failed, 0, 0, 0, 0, 0, 0, 0, 0, None, None,
            )
            report = format_weekly_report(build_weekly_report(repository, history, result))
            self.assertIn("Himalayas: FAILED", report)


if __name__ == "__main__":
    unittest.main()
