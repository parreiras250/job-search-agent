import json
import socket
import unittest
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

from daniel_job_agent import (
    GeographicEligibility,
    JobicyJobAdapter,
    JobicyJobSource,
    SourceStatus,
    build_jobicy_jobs_url,
    create_daniel_profile,
    enrich_opportunities,
    evaluate_geographic_eligibility,
    ingest_batch,
    process_opportunities,
)
from daniel_job_agent.sources import HttpResponse
from daniel_job_agent.reporting import format_warning_summary


def jobicy_job(**overrides: object) -> dict[str, object]:
    job: dict[str, object] = {
        "id": 123, "url": "https://jobicy.com/jobs/123",
        "jobTitle": "Account Executive", "companyName": "Example SaaS",
        "jobIndustry": ["Sales", "SaaS"], "jobType": "Full-time",
        "jobGeo": "LATAM", "jobLevel": "Senior",
        "jobDescription": "Own the full sales cycle using Salesforce.",
        "pubDate": "2026-08-14 10:30:00", "salaryMin": 80000,
        "salaryMax": 120000, "salaryCurrency": "USD", "salaryPeriod": "year",
    }
    job.update(overrides)
    return job


class FakeTransport:
    def __init__(self, payload=None, *, status=200, error=None):
        self.payload, self.status, self.error = payload, status, error
        self.calls = []

    def get(self, url, timeout, headers):
        self.calls.append((url, timeout, headers))
        if self.error is not None:
            raise self.error
        body = self.payload if isinstance(self.payload, bytes) else json.dumps(self.payload).encode()
        return HttpResponse(status=self.status, body=body)


class JobicySourceTests(unittest.TestCase):
    def test_url_builder_encodes_documented_filters(self):
        url = build_jobicy_jobs_url(count=25, geo="latin america", industry="seller", tag="account executive")
        self.assertEqual(urlsplit(url).scheme, "https")
        self.assertEqual(
            f"{urlsplit(url).netloc}{urlsplit(url).path}",
            "jobicy.com/api/v2/remote-jobs",
        )
        self.assertEqual(parse_qs(urlsplit(url).query), {
            "count": ["25"], "geo": ["latin america"],
            "industry": ["seller"], "tag": ["account executive"],
        })

    def test_count_must_be_between_one_and_one_hundred(self):
        self.assertIn("count=1", build_jobicy_jobs_url(count=1))
        self.assertIn("count=100", build_jobicy_jobs_url(count=100))
        for count in (0, 101, True, 1.5):
            with self.subTest(count=count), self.assertRaises(ValueError):
                build_jobicy_jobs_url(count=count)  # type: ignore[arg-type]

    def test_success_and_single_get(self):
        transport = FakeTransport({"apiVersion": "2.0", "jobCount": 2, "jobs": [jobicy_job(), jobicy_job(id=456)]})
        result = JobicyJobSource(count=2, geo="latam", transport=transport).fetch()
        self.assertEqual(result.status, SourceStatus.SUCCESS)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(len(transport.calls), 1)

    def test_zero_jobs_is_success(self):
        result = JobicyJobSource(transport=FakeTransport({"jobs": []})).fetch()
        self.assertEqual(result.status, SourceStatus.NO_JOBS)
        self.assertTrue(result.success)

    def test_invalid_payloads_are_controlled(self):
        for payload in ([], {}, {"jobs": "invalid"}, b"not json"):
            with self.subTest(payload=payload):
                result = JobicyJobSource(transport=FakeTransport(payload)).fetch()
                self.assertEqual(result.status, SourceStatus.INVALID_PAYLOAD)

    def test_transport_failures_are_controlled(self):
        cases = (
            (FakeTransport(status=404), SourceStatus.HTTP_ERROR),
            (FakeTransport(status=500), SourceStatus.HTTP_ERROR),
            (FakeTransport(error=URLError("offline")), SourceStatus.CONNECTION_ERROR),
            (FakeTransport(error=socket.timeout()), SourceStatus.TIMEOUT),
        )
        for transport, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(JobicyJobSource(transport=transport).fetch().status, expected)


class JobicyAdapterAndPipelineTests(unittest.TestCase):
    def test_adapter_preserves_documented_fields_and_salary_range(self):
        result = JobicyJobAdapter().adapt(jobicy_job())
        self.assertTrue(result.success)
        job = result.opportunity
        assert job is not None
        self.assertEqual(job.external_id, "123")
        self.assertEqual(job.role, "Account Executive")
        self.assertEqual(job.company, "Example SaaS")
        self.assertEqual(job.job_url, "https://jobicy.com/jobs/123")
        self.assertEqual(job.location, "LATAM")
        self.assertEqual(job.employment_type, "Full-time")
        self.assertEqual(job.description, "Own the full sales cycle using Salesforce.")
        self.assertEqual(job.industries_mentioned, ["Sales", "SaaS"])
        self.assertEqual(job.job_level, "Senior")
        self.assertEqual((job.salary_min, job.salary_max), (80000.0, 120000.0))
        self.assertEqual((job.salary_currency, job.salary_period), ("USD", "year"))
        self.assertEqual(job.date_posted.isoformat(), "2026-08-14")
        self.assertTrue(job.remote)
        self.assertIsNone(job.brazil_eligible)

    def test_documented_job_type_list_does_not_generate_warning(self):
        result = JobicyJobAdapter().adapt(
            jobicy_job(jobType=["full-time"], jobLevel=["Senior Level"])
        )
        self.assertTrue(result.success)
        self.assertEqual(result.opportunity.employment_type, "full-time")
        self.assertEqual(result.opportunity.job_level, "Senior Level")
        self.assertEqual(result.warnings, [])

    def test_absent_optional_fields_are_unknown_without_warnings(self):
        record = jobicy_job()
        for field in (
            "salaryMin",
            "salaryMax",
            "salaryCurrency",
            "salaryPeriod",
            "jobLevel",
            "pubDate",
        ):
            record.pop(field)
        result = JobicyJobAdapter().adapt(record)
        self.assertTrue(result.success)
        self.assertEqual(result.warnings, [])
        self.assertIsNone(result.opportunity.salary_min)
        self.assertIsNone(result.opportunity.salary_max)
        self.assertIsNone(result.opportunity.salary_currency)
        self.assertIsNone(result.opportunity.salary_period)
        self.assertIsNone(result.opportunity.job_level)
        self.assertIsNone(result.opportunity.date_posted)
        self.assertTrue(
            {"salary_min", "salary_max", "job_level", "date_posted"}
            <= set(result.optional_fields_missing)
        )

    def test_string_industry_is_preserved_as_list(self):
        result = JobicyJobAdapter().adapt(jobicy_job(jobIndustry="Sales"))
        self.assertEqual(result.opportunity.industries_mentioned, ["Sales"])

    def test_invalid_optional_date_warns_without_losing_job(self):
        result = JobicyJobAdapter().adapt(jobicy_job(pubDate="yesterday"))
        self.assertTrue(result.success)
        self.assertIsNone(result.opportunity.date_posted)
        self.assertEqual([warning.field for warning in result.warnings], ["date_posted"])

    def test_invalid_optional_salary_warns_without_losing_job(self):
        result = JobicyJobAdapter().adapt(jobicy_job(salaryMin="$80k-$120k"))
        self.assertTrue(result.success)
        self.assertIsNone(result.opportunity.salary_min)
        self.assertEqual([warning.field for warning in result.warnings], ["salary_min"])

    def test_batch_separates_successes_warnings_and_errors(self):
        batch = ingest_batch(
            [
                jobicy_job(id=1),
                jobicy_job(id=2, pubDate="not-a-date"),
                jobicy_job(id=3, companyName=""),
            ],
            JobicyJobAdapter(),
        )
        self.assertEqual(batch.total_received, 3)
        self.assertEqual(batch.converted_count, 2)
        self.assertEqual(batch.warning_count, 1)
        self.assertEqual(batch.error_count, 1)
        self.assertEqual(
            format_warning_summary(batch),
            "Warning summary:\n"
            "- date_posted: date_posted must be an ISO date or datetime: 1",
        )

    def test_missing_required_field_is_an_individual_error(self):
        batch = ingest_batch([jobicy_job(companyName=""), jobicy_job(id=456)], JobicyJobAdapter())
        self.assertEqual((batch.converted_count, batch.error_count), (1, 1))

    def test_geographies_are_conservative_and_deterministic(self):
        for location in ("Brazil", "LATAM", "Anywhere", "Worldwide", "Americas"):
            self.assertEqual(evaluate_geographic_eligibility(location), GeographicEligibility.ELIGIBLE)
        for location in ("USA", "Europe", "EMEA"):
            self.assertEqual(evaluate_geographic_eligibility(location), GeographicEligibility.NOT_ELIGIBLE)
        self.assertEqual(evaluate_geographic_eligibility("Asia Pacific"), GeographicEligibility.UNKNOWN)

    def test_source_adapter_enrichment_pipeline_and_deduplication(self):
        payload = {"jobs": [
            jobicy_job(),
            jobicy_job(id=456, url="https://jobicy.com/jobs/123?utm_source=test"),
            jobicy_job(id=789, jobTitle="Software Engineer", url="https://jobicy.com/jobs/789"),
        ]}
        source_result = JobicyJobSource(transport=FakeTransport(payload)).fetch()
        ingestion = ingest_batch(source_result.records, JobicyJobAdapter())
        enriched = enrich_opportunities(ingestion.opportunities)
        enriched[0].tracking.notes = "Preserve manual follow-up"
        pipeline = process_opportunities(enriched, create_daniel_profile())
        self.assertEqual(ingestion.converted_count, 3)
        self.assertEqual(pipeline.duplicates_detected, 1)
        self.assertEqual(len(pipeline.ranked_opportunities), 2)
        sales_job = next(job for job in enriched if job.role == "Account Executive")
        self.assertTrue(sales_job.full_cycle_sales_required)
        processed_sales = next(
            item for item in pipeline.ranked_opportunities
            if item.normalized_job.role == "Account Executive"
        )
        self.assertEqual(processed_sales.normalized_job.tracking.notes, "Preserve manual follow-up")


if __name__ == "__main__":
    unittest.main()
