import json
import socket
import unittest
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

from daniel_job_agent import (
    GeographicEligibility,
    RemotiveJobAdapter,
    RemotiveJobSource,
    SourceStatus,
    build_remotive_jobs_url,
    create_daniel_profile,
    enrich_opportunities,
    evaluate_geographic_eligibility,
    ingest_batch,
    process_opportunities,
)
from daniel_job_agent.sources import HttpResponse


def remotive_job(**overrides: object) -> dict[str, object]:
    job: dict[str, object] = {
        "id": 12345,
        "url": "https://remotive.com/remote-jobs/sales/account-executive-12345",
        "title": "Account Executive",
        "company_name": "Example SaaS",
        "category": "Sales",
        "job_type": "full_time",
        "publication_date": "2026-08-14T10:30:00Z",
        "candidate_required_location": "LATAM",
        "salary": "$40,000 - $50,000",
        "description": "Own the full sales cycle for B2B SaaS customers.",
    }
    job.update(overrides)
    return job


class FakeTransport:
    def __init__(self, payload=None, *, status=200, error=None):
        self.payload = payload
        self.status = status
        self.error = error
        self.calls = []

    def get(self, url, timeout, headers):
        self.calls.append((url, timeout, headers))
        if self.error is not None:
            raise self.error
        body = (
            self.payload
            if isinstance(self.payload, bytes)
            else json.dumps(self.payload).encode()
        )
        return HttpResponse(status=self.status, body=body)


class RemotiveSourceTests(unittest.TestCase):
    def test_url_builder_preserves_endpoint_filters_and_encoding(self):
        url = build_remotive_jobs_url(
            category="sales",
            company_name="Example Company",
            search="account executive",
            limit=100,
        )
        parts = urlsplit(url)
        self.assertEqual(
            f"{parts.scheme}://{parts.netloc}{parts.path}",
            "https://remotive.com/api/remote-jobs",
        )
        self.assertEqual(
            parse_qs(parts.query),
            {
                "category": ["sales"],
                "company_name": ["Example Company"],
                "search": ["account executive"],
                "limit": ["100"],
            },
        )

    def test_limit_must_be_positive_when_provided(self):
        self.assertIn("limit=1", build_remotive_jobs_url(limit=1))
        for limit in (0, -1, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                build_remotive_jobs_url(limit=limit)  # type: ignore[arg-type]

    def test_multiple_jobs_use_one_get(self):
        transport = FakeTransport({"job-count": 2, "jobs": [remotive_job(), remotive_job(id=2)]})
        result = RemotiveJobSource(category="sales", transport=transport).fetch()
        self.assertEqual(result.status, SourceStatus.SUCCESS)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(len(transport.calls), 1)

    def test_zero_jobs_is_success(self):
        result = RemotiveJobSource(transport=FakeTransport({"jobs": []})).fetch()
        self.assertEqual(result.status, SourceStatus.NO_JOBS)
        self.assertTrue(result.success)

    def test_unexpected_payload_and_invalid_json_are_controlled(self):
        for payload in ([], {}, {"jobs": "invalid"}, b"not json"):
            with self.subTest(payload=payload):
                result = RemotiveJobSource(transport=FakeTransport(payload)).fetch()
                self.assertEqual(result.status, SourceStatus.INVALID_PAYLOAD)

    def test_http_timeout_and_connection_failures_are_controlled(self):
        cases = (
            (FakeTransport(status=404), SourceStatus.HTTP_ERROR),
            (FakeTransport(status=500), SourceStatus.HTTP_ERROR),
            (FakeTransport(error=socket.timeout()), SourceStatus.TIMEOUT),
            (FakeTransport(error=URLError("offline")), SourceStatus.CONNECTION_ERROR),
        )
        for transport, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(RemotiveJobSource(transport=transport).fetch().status, expected)


class RemotiveAdapterIntegrationTests(unittest.TestCase):
    def test_adapter_maps_fields_salary_url_and_attribution(self):
        result = RemotiveJobAdapter().adapt(remotive_job())
        self.assertTrue(result.success)
        job = result.opportunity
        assert job is not None
        self.assertEqual(job.external_id, "12345")
        self.assertEqual(job.job_url, "https://remotive.com/remote-jobs/sales/account-executive-12345")
        self.assertEqual(job.role, "Account Executive")
        self.assertEqual(job.company, "Example SaaS")
        self.assertEqual(job.industries_mentioned, ["Sales"])
        self.assertEqual(job.employment_type, "full_time")
        self.assertEqual(job.date_posted.isoformat(), "2026-08-14")
        self.assertEqual(job.location, "LATAM")
        self.assertEqual(job.salary_text, "$40,000 - $50,000")
        self.assertEqual(job.description, "Own the full sales cycle for B2B SaaS customers.")
        self.assertEqual(job.source, "Remotive")
        self.assertTrue(job.remote)
        self.assertIsNone(job.brazil_eligible)

    def test_supported_geographies_reuse_existing_rules(self):
        for location in ("Worldwide", "LATAM", "Brazil"):
            self.assertEqual(evaluate_geographic_eligibility(location), GeographicEligibility.ELIGIBLE)
        self.assertEqual(evaluate_geographic_eligibility("USA"), GeographicEligibility.NOT_ELIGIBLE)

    def test_absent_optional_fields_are_unknown_without_warning(self):
        record = remotive_job()
        for field in ("category", "job_type", "publication_date", "salary", "description"):
            record.pop(field)
        result = RemotiveJobAdapter().adapt(record)
        self.assertTrue(result.success)
        self.assertEqual(result.warnings, [])
        self.assertIsNone(result.opportunity.salary_text)
        self.assertIsNone(result.opportunity.date_posted)
        self.assertIsNone(result.opportunity.employment_type)

    def test_invalid_optional_date_warns_without_losing_job(self):
        result = RemotiveJobAdapter().adapt(remotive_job(publication_date="not-a-date"))
        self.assertTrue(result.success)
        self.assertIsNone(result.opportunity.date_posted)
        self.assertEqual([warning.field for warning in result.warnings], ["date_posted"])

    def test_present_non_text_salary_warns_without_losing_job(self):
        result = RemotiveJobAdapter().adapt(remotive_job(salary={"min": 40000}))
        self.assertTrue(result.success)
        self.assertIsNone(result.opportunity.salary_text)
        self.assertEqual([warning.field for warning in result.warnings], ["salary_text"])

    def test_invalid_job_does_not_interrupt_batch(self):
        batch = ingest_batch(
            [remotive_job(company_name=""), remotive_job(id=2)],
            RemotiveJobAdapter(),
        )
        self.assertEqual((batch.converted_count, batch.error_count), (1, 1))

    def test_source_adapter_enrichment_pipeline_dedup_and_tracking(self):
        payload = {"jobs": [
            remotive_job(),
            remotive_job(id=2, url="https://remotive.com/remote-jobs/sales/account-executive-12345?ref=test"),
            remotive_job(id=3, title="Software Engineer", url="https://remotive.com/remote-jobs/software-dev/engineer-3"),
        ]}
        source_result = RemotiveJobSource(transport=FakeTransport(payload)).fetch()
        ingestion = ingest_batch(source_result.records, RemotiveJobAdapter())
        enriched = enrich_opportunities(ingestion.opportunities)
        enriched[0].tracking.notes = "Preserve this note"
        pipeline = process_opportunities(enriched, create_daniel_profile())
        self.assertEqual(ingestion.converted_count, 3)
        self.assertEqual(pipeline.duplicates_detected, 1)
        self.assertEqual(pipeline.unique_opportunities, 2)
        sales = next(job for job in enriched if job.role == "Account Executive")
        self.assertTrue(sales.full_cycle_sales_required)
        self.assertTrue(sales.b2b_experience_required)
        processed = next(
            item for item in pipeline.ranked_opportunities
            if item.normalized_job.role == "Account Executive"
        )
        self.assertEqual(processed.normalized_job.tracking.notes, "Preserve this note")
        self.assertEqual(processed.normalized_job.source, "Remotive")
        self.assertTrue(processed.normalized_job.job_url.startswith("https://remotive.com/"))


if __name__ == "__main__":
    unittest.main()
