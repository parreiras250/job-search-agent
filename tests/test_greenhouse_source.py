"""Testes da fonte pública Greenhouse sem realizar requests reais."""

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
    GreenhouseJobAdapter,
    create_daniel_profile,
    ingest_batch,
    process_opportunities,
)
from daniel_job_agent.greenhouse_demo import format_counts  # noqa: E402
from daniel_job_agent.sources import (  # noqa: E402
    DEFAULT_USER_AGENT,
    GreenhouseJobSource,
    HttpResponse,
    SourceStatus,
    build_greenhouse_jobs_url,
)


def greenhouse_job(**changes: object) -> dict[str, object]:
    job: dict[str, object] = {
        "id": 123,
        "title": "Account Executive",
        "absolute_url": "https://boards.greenhouse.io/example/jobs/123",
        "location": {"name": "Remote - LATAM"},
        "content": "<p>Sell our fictional product.</p>",
    }
    job.update(changes)
    return job


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


class GreenhouseSourceTests(unittest.TestCase):
    def test_builds_safe_public_jobs_url(self) -> None:
        self.assertEqual(
            build_greenhouse_jobs_url("example-board_1"),
            "https://boards-api.greenhouse.io/v1/boards/"
            "example-board_1/jobs?content=true",
        )
        for unsafe in ("", "../secret", "board/token", "board?x=1"):
            with self.subTest(token=unsafe):
                with self.assertRaises(ValueError):
                    build_greenhouse_jobs_url(unsafe)

    def test_valid_response_returns_multiple_raw_jobs_with_one_get(self) -> None:
        transport = FakeTransport(
            response=json_response({"jobs": [greenhouse_job(), greenhouse_job(id=456)]})
        )
        source = GreenhouseJobSource(
            "example", "Example Company", timeout=4, transport=transport
        )

        result = source.fetch()

        self.assertEqual(result.status, SourceStatus.SUCCESS)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0][1], 4)
        self.assertEqual(transport.calls[0][2]["User-Agent"], DEFAULT_USER_AGENT)

    def test_zero_jobs_is_successful_no_jobs_result(self) -> None:
        source = GreenhouseJobSource(
            "example",
            "Example Company",
            transport=FakeTransport(response=json_response({"jobs": []})),
        )
        result = source.fetch()

        self.assertTrue(result.success)
        self.assertEqual(result.status, SourceStatus.NO_JOBS)
        self.assertEqual(result.records, [])

    def test_timeout_is_structured(self) -> None:
        source = GreenhouseJobSource(
            "example",
            "Example Company",
            transport=FakeTransport(error=socket.timeout("timed out")),
        )
        self.assertEqual(source.fetch().status, SourceStatus.TIMEOUT)

    def test_connection_error_is_structured(self) -> None:
        source = GreenhouseJobSource(
            "example",
            "Example Company",
            transport=FakeTransport(error=URLError("offline")),
        )
        self.assertEqual(source.fetch().status, SourceStatus.CONNECTION_ERROR)

    def test_http_404_and_500_are_structured(self) -> None:
        for status in (404, 500):
            with self.subTest(status=status):
                source = GreenhouseJobSource(
                    "example",
                    "Example Company",
                    transport=FakeTransport(
                        response=HttpResponse(status=status, body=b"error")
                    ),
                )
                result = source.fetch()
                self.assertEqual(result.status, SourceStatus.HTTP_ERROR)
                self.assertEqual(result.http_status, status)

    def test_invalid_json_and_invalid_shape_are_structured(self) -> None:
        responses = (
            HttpResponse(status=200, body=b"not json"),
            json_response({"unexpected": []}),
            json_response({"jobs": "not a list"}),
        )
        for response in responses:
            with self.subTest(body=response.body):
                source = GreenhouseJobSource(
                    "example",
                    "Example Company",
                    transport=FakeTransport(response=response),
                )
                self.assertEqual(source.fetch().status, SourceStatus.INVALID_PAYLOAD)


class GreenhouseAdapterIntegrationTests(unittest.TestCase):
    def test_adapter_maps_real_public_fields_and_preserves_unknowns(self) -> None:
        result = GreenhouseJobAdapter("Example Company").adapt(greenhouse_job())
        job = result.opportunity

        self.assertTrue(result.success)
        self.assertEqual(job.company, "Example Company")  # type: ignore[union-attr]
        self.assertEqual(job.role, "Account Executive")  # type: ignore[union-attr]
        self.assertEqual(  # type: ignore[union-attr]
            job.job_url, "https://boards.greenhouse.io/example/jobs/123"
        )
        self.assertEqual(job.source, "Greenhouse public Job Board")  # type: ignore[union-attr]
        self.assertEqual(job.location, "Remote - LATAM")  # type: ignore[union-attr]
        self.assertEqual(job.description, "<p>Sell our fictional product.</p>")  # type: ignore[union-attr]
        self.assertIsNone(job.remote)  # type: ignore[union-attr]
        self.assertIsNone(job.brazil_eligible)  # type: ignore[union-attr]
        self.assertIsNone(job.base_salary)  # type: ignore[union-attr]
        self.assertIsNone(job.years_experience_required)  # type: ignore[union-attr]
        self.assertIsNone(job.tools_mentioned)  # type: ignore[union-attr]
        self.assertIsNone(job.industries_mentioned)  # type: ignore[union-attr]

    def test_invalid_job_does_not_interrupt_other_jobs(self) -> None:
        batch = ingest_batch(
            [greenhouse_job(), greenhouse_job(id=999, title="")],
            GreenhouseJobAdapter("Example Company"),
        )

        self.assertEqual(batch.total_received, 2)
        self.assertEqual(batch.converted_count, 1)
        self.assertEqual(batch.error_count, 1)

    def test_source_adapter_pipeline_integration_preserves_tracking(self) -> None:
        source = GreenhouseJobSource(
            "example",
            "Example Company",
            transport=FakeTransport(
                response=json_response({"jobs": [greenhouse_job()]})
            ),
        )
        source_result = source.fetch()
        ingestion = ingest_batch(
            source_result.records,
            GreenhouseJobAdapter("Example Company"),
        )
        job = ingestion.opportunities[0]
        job.tracking.application_status = ApplicationStatus.APPLIED
        job.tracking.notes = "Manual note"

        pipeline = process_opportunities(
            ingestion.opportunities,
            create_daniel_profile(),
        )

        self.assertEqual(pipeline.total_received, 1)
        self.assertIs(pipeline.ranked_opportunities[0].original_job, job)
        self.assertEqual(job.tracking.application_status, ApplicationStatus.APPLIED)
        self.assertEqual(job.tracking.notes, "Manual note")

        summary = format_counts(len(source_result.records), ingestion, pipeline)
        self.assertIn("Jobs received: 1", summary)
        self.assertIn("Jobs converted: 1", summary)
        self.assertIn("Unique jobs: 1", summary)
        self.assertIn("Duplicates detected: 0", summary)
        self.assertIn("unique jobs = KEEP + REVIEW + REJECT = 1", summary)


if __name__ == "__main__":
    unittest.main()
