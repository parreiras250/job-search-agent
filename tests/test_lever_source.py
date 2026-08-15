"""Testes da fonte pública Lever sem realizar requests reais."""

import json
import socket
import sys
import unittest
from pathlib import Path
from urllib.error import URLError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from daniel_job_agent import (  # noqa: E402
    ApplicationStatus,
    LeverJobAdapter,
    create_daniel_profile,
    enrich_opportunities,
    ingest_batch,
    process_opportunities,
)
from daniel_job_agent.reporting import format_counts  # noqa: E402
from daniel_job_agent.sources import (  # noqa: E402
    DEFAULT_USER_AGENT,
    HttpResponse,
    LeverJobSource,
    SourceStatus,
    build_lever_postings_url,
)


def lever_posting(**changes: object) -> dict[str, object]:
    posting: dict[str, object] = {
        "id": "posting-123",
        "text": "Account Executive - LATAM",
        "categories": {
            "location": "Remote - LATAM",
            "commitment": "Full-time",
            "team": "Sales",
        },
        "descriptionPlain": "Own customer relationships for a B2B SaaS product.",
        "lists": [
            {
                "text": "What you will do",
                "content": "Own the full sales cycle and outbound prospecting.",
            }
        ],
        "additionalPlain": "Requires 4+ years of experience.",
        "hostedUrl": "https://jobs.lever.co/example/posting-123",
        "applyUrl": "https://jobs.lever.co/example/posting-123/apply",
    }
    posting.update(changes)
    return posting


class FakeTransport:
    def __init__(
        self,
        *,
        response: HttpResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple[str, float, dict[str, str]]] = []

    def get(self, url: str, timeout: float, headers: dict[str, str]) -> HttpResponse:
        self.calls.append((url, timeout, headers))
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise AssertionError("Fake transport has no configured response")
        return self.response


def json_response(payload: object, status: int = 200) -> HttpResponse:
    return HttpResponse(status=status, body=json.dumps(payload).encode("utf-8"))


class LeverSourceTests(unittest.TestCase):
    def test_builds_global_and_eu_urls_safely(self) -> None:
        self.assertEqual(
            build_lever_postings_url("example"),
            "https://api.lever.co/v0/postings/example?mode=json",
        )
        self.assertEqual(
            build_lever_postings_url("example", "eu"),
            "https://api.eu.lever.co/v0/postings/example?mode=json",
        )
        for slug in ("", "../secret", "company/site", "company?mode=html"):
            with self.subTest(slug=slug):
                with self.assertRaises(ValueError):
                    build_lever_postings_url(slug)
        with self.assertRaises(ValueError):
            build_lever_postings_url("example", "unknown")

    def test_valid_response_returns_multiple_postings_with_one_get(self) -> None:
        transport = FakeTransport(
            response=json_response([lever_posting(), lever_posting(id="posting-456")])
        )
        source = LeverJobSource(
            "example", "Example Company", timeout=3, transport=transport
        )

        result = source.fetch()

        self.assertEqual(result.status, SourceStatus.SUCCESS)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0][1], 3)
        self.assertEqual(transport.calls[0][2]["User-Agent"], DEFAULT_USER_AGENT)

    def test_zero_postings_is_successful(self) -> None:
        source = LeverJobSource(
            "example",
            "Example Company",
            transport=FakeTransport(response=json_response([])),
        )
        result = source.fetch()

        self.assertTrue(result.success)
        self.assertEqual(result.status, SourceStatus.NO_JOBS)

    def test_timeout_and_connection_errors_are_structured(self) -> None:
        cases = (
            (socket.timeout("timed out"), SourceStatus.TIMEOUT),
            (URLError("offline"), SourceStatus.CONNECTION_ERROR),
        )
        for error, status in cases:
            with self.subTest(status=status):
                source = LeverJobSource(
                    "example",
                    "Example Company",
                    transport=FakeTransport(error=error),
                )
                self.assertEqual(source.fetch().status, status)

    def test_http_404_and_500_are_structured(self) -> None:
        for status in (404, 500):
            with self.subTest(status=status):
                source = LeverJobSource(
                    "example",
                    "Example Company",
                    transport=FakeTransport(
                        response=HttpResponse(status=status, body=b"error")
                    ),
                )
                result = source.fetch()
                self.assertEqual(result.status, SourceStatus.HTTP_ERROR)
                self.assertEqual(result.http_status, status)

    def test_invalid_json_and_unexpected_payload_are_structured(self) -> None:
        responses = (
            HttpResponse(status=200, body=b"not json"),
            json_response({"postings": []}),
        )
        for response in responses:
            with self.subTest(body=response.body):
                source = LeverJobSource(
                    "example",
                    "Example Company",
                    transport=FakeTransport(response=response),
                )
                self.assertEqual(source.fetch().status, SourceStatus.INVALID_PAYLOAD)


class LeverAdapterIntegrationTests(unittest.TestCase):
    def test_adapter_maps_real_fields_and_preserves_unknowns(self) -> None:
        result = LeverJobAdapter("Example Company").adapt(lever_posting())
        job = result.opportunity

        self.assertTrue(result.success)
        self.assertEqual(job.company, "Example Company")  # type: ignore[union-attr]
        self.assertEqual(job.role, "Account Executive - LATAM")  # type: ignore[union-attr]
        self.assertEqual(job.location, "Remote - LATAM")  # type: ignore[union-attr]
        self.assertEqual(job.job_url, "https://jobs.lever.co/example/posting-123")  # type: ignore[union-attr]
        self.assertEqual(job.source, "Lever public postings")  # type: ignore[union-attr]
        self.assertEqual(job.employment_type, "Full-time")  # type: ignore[union-attr]
        self.assertIn("B2B SaaS", job.description)  # type: ignore[operator,union-attr]
        self.assertIn("full sales cycle", job.description)  # type: ignore[operator,union-attr]
        self.assertIsNone(job.remote)  # type: ignore[union-attr]
        self.assertIsNone(job.brazil_eligible)  # type: ignore[union-attr]
        self.assertIsNone(job.base_salary)  # type: ignore[union-attr]
        self.assertIsNone(job.years_experience_required)  # type: ignore[union-attr]
        self.assertIsNone(job.saas_experience_required)  # type: ignore[union-attr]

    def test_invalid_posting_does_not_interrupt_valid_posting(self) -> None:
        batch = ingest_batch(
            [lever_posting(), lever_posting(id="bad", text="")],
            LeverJobAdapter("Example Company"),
        )

        self.assertEqual(batch.converted_count, 1)
        self.assertEqual(batch.error_count, 1)

    def test_adapter_reuses_deterministic_enrichment(self) -> None:
        ingestion = ingest_batch(
            [lever_posting()],
            LeverJobAdapter("Example Company"),
        )
        enriched = enrich_opportunities(ingestion.opportunities)[0]

        self.assertEqual(enriched.years_experience_required, 4)
        self.assertIs(enriched.full_cycle_sales_required, True)
        self.assertIs(enriched.outbound_sales_required, True)
        self.assertIs(enriched.b2b_experience_required, True)
        self.assertIs(enriched.saas_experience_required, True)

    def test_source_adapter_enrichment_pipeline_preserves_tracking(self) -> None:
        source = LeverJobSource(
            "example",
            "Example Company",
            transport=FakeTransport(response=json_response([lever_posting()])),
        )
        source_result = source.fetch()
        ingestion = ingest_batch(
            source_result.records,
            LeverJobAdapter("Example Company"),
        )
        original_tracking = ingestion.opportunities[0].tracking
        original_tracking.application_status = ApplicationStatus.APPLIED
        original_tracking.notes = "Manual Lever note"
        enriched = enrich_opportunities(ingestion.opportunities)
        pipeline = process_opportunities(enriched, create_daniel_profile())

        self.assertEqual(pipeline.total_received, 1)
        self.assertIs(pipeline.ranked_opportunities[0].original_job.tracking, original_tracking)
        self.assertEqual(original_tracking.application_status, ApplicationStatus.APPLIED)
        self.assertEqual(original_tracking.notes, "Manual Lever note")
        summary = format_counts(len(source_result.records), ingestion, pipeline)
        self.assertIn("Jobs received: 1", summary)
        self.assertIn("Unique jobs: 1", summary)


if __name__ == "__main__":
    unittest.main()
