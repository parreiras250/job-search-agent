"""Testes offline da integração com a API pública do Get on Board."""

import json
import socket
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError

from daniel_job_agent import (
    GETONBOARD_API_BASE_URL,
    GetOnBoardJobAdapter,
    GetOnBoardJobSource,
    LifecycleAuthority,
    GLOBAL_SOURCE_ORDER,
    JobOpportunity,
    JobRepository,
    SourceStatus,
    SourceType,
    build_getonboard_jobs_url,
    create_daniel_profile,
    create_default_source_registry,
    ingest_batch,
    process_opportunities,
    sync_opportunities,
)
from daniel_job_agent.sources import HttpResponse
from daniel_job_agent.getonboard_demo import (
    build_parser,
    format_getonboard_payload_shape_debug,
)


FIXTURE = Path(__file__).parent / "fixtures" / "getonboard_jobs.json"
REAL_SHAPES_FIXTURE = Path(__file__).parent / "fixtures" / "getonboard_real_shapes.json"


def fixture_payload():
    return json.loads(FIXTURE.read_text())


def real_shape_records():
    return json.loads(REAL_SHAPES_FIXTURE.read_text())


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


class GetOnBoardSourceTests(unittest.TestCase):
    def test_url_is_official_single_conservative_first_page_query(self) -> None:
        url = build_getonboard_jobs_url()
        self.assertTrue(url.startswith(GETONBOARD_API_BASE_URL + "/search/jobs?"))
        self.assertIn("query=sales", url)
        self.assertIn("page=1", url)
        self.assertIn("per_page=20", url)
        self.assertEqual(url.count("expand%5B%5D="), 2)
        for kwargs in ({"query": "x"}, {"page": 2}, {"per_page": 21}, {"per_page": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                build_getonboard_jobs_url(**kwargs)

    def test_parses_json_api_with_one_request(self) -> None:
        transport = FakeTransport(fixture_payload())
        result = GetOnBoardJobSource(transport=transport).fetch()
        self.assertEqual(result.status, SourceStatus.SUCCESS)
        self.assertEqual(len(result.records), 3)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(result.records[0]["id"], "sales-101")
        self.assertNotIn("Authorization", transport.calls[0][2])

    def test_empty_invalid_schema_and_pagination_are_controlled(self) -> None:
        invalid = [b"not-json", [], {}, {"data": ["bad"]}, {"data": [], "meta": []}, {"data": [], "meta": {"page": True}}]
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assertEqual(GetOnBoardJobSource(transport=FakeTransport(payload)).fetch().status, SourceStatus.INVALID_PAYLOAD)
        self.assertEqual(GetOnBoardJobSource(transport=FakeTransport({"data": []})).fetch().status, SourceStatus.NO_JOBS)

    def test_http_timeout_and_connection_errors_are_controlled(self) -> None:
        url = build_getonboard_jobs_url()
        cases = (
            (FakeTransport(status=500), SourceStatus.HTTP_ERROR),
            (FakeTransport(error=HTTPError(url, 429, "rate", {}, None)), SourceStatus.HTTP_ERROR),
            (FakeTransport(error=socket.timeout()), SourceStatus.TIMEOUT),
            (FakeTransport(error=URLError("offline")), SourceStatus.CONNECTION_ERROR),
        )
        for transport, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(GetOnBoardJobSource(transport=transport).fetch().status, expected)


class GetOnBoardPayloadShapeDebugTests(unittest.TestCase):
    def test_flag_is_optional_and_parsed_offline(self) -> None:
        self.assertFalse(build_parser().parse_args([]).debug_payload_shape)
        self.assertTrue(
            build_parser().parse_args(["--debug-payload-shape"]).debug_payload_shape
        )

    def test_formatter_is_limited_structural_and_omits_descriptions(self) -> None:
        malformed = [
            {
                "id": f"bad-{index}",
                "attributes": {
                    "title": f"Broken {index}",
                    "description": "SECRET DESCRIPTION " * 100,
                    "published_at": 1_723_456_789,
                    "modality": {"id": 2, "name": "Full time"},
                    "seniority": [{"name": "Senior"}],
                    "remote": True,
                    "remote_modality": {"name": "Remote"},
                    "allowed_locations": ["Chile", "Brazil"],
                    "min_salary": 1000,
                    "tags": {"data": [{"attributes": {"name": "Sales"}}]},
                },
                "relationships": {
                    "company": {"data": {"attributes": {"name": "Example"}}}
                },
            }
            for index in range(1, 6)
        ]
        records = [*fixture_payload()["data"], *malformed]
        batch = ingest_batch(records, GetOnBoardJobAdapter())
        output = format_getonboard_payload_shape_debug(records, batch.results)
        self.assertIn("Selected: 3 converted | 3 ingestion failures", output)
        self.assertIn("top-level keys:", output)
        self.assertIn("attributes.published_at: type=int", output)
        self.assertIn("attributes.modality: type=dict", output)
        self.assertIn("attributes.seniority: type=list", output)
        self.assertIn("relationships.company: type=dict", output)
        self.assertIn("ingestion error:", output)
        self.assertNotIn("SECRET DESCRIPTION", output)
        self.assertNotIn("bad-4", output)


class GetOnBoardAdapterTests(unittest.TestCase):
    def test_maps_documented_identity_content_salary_and_attribution(self) -> None:
        result = GetOnBoardJobAdapter().adapt(fixture_payload()["data"][0])
        self.assertTrue(result.success)
        self.assertEqual(result.warnings, [])
        job = result.opportunity
        assert job is not None
        self.assertEqual(job.company, "Acme LATAM")
        self.assertEqual(job.role, "Account Executive LATAM")
        self.assertEqual(job.external_id, "sales-101")
        self.assertEqual(job.source, "Get on Board")
        self.assertTrue(job.job_url.startswith("https://www.getonbrd.com/jobs/"))
        self.assertEqual((job.salary_min, job.salary_max), (3000.0, 5000.0))
        self.assertEqual((job.salary_currency, job.salary_period), ("USD", "monthly"))
        self.assertEqual(job.industries_mentioned, ["SaaS"])
        self.assertEqual(job.job_level, "Senior")
        self.assertTrue(job.remote)
        self.assertIsNone(job.brazil_eligible)

    def test_geography_is_conservative_and_remote_is_not_worldwide(self) -> None:
        chile = GetOnBoardJobAdapter().adapt(fixture_payload()["data"][1]).opportunity
        assert chile is not None
        self.assertEqual(chile.location, "Chile")
        self.assertTrue(chile.remote)
        self.assertIsNone(chile.brazil_eligible)

    def test_optional_malformed_warns_required_invalid_errors_and_batch_continues(self) -> None:
        records = [*fixture_payload()["data"], {"id": "bad", "attributes": {"title": "Missing"}}]
        batch = ingest_batch(records, GetOnBoardJobAdapter())
        self.assertEqual((batch.converted_count, batch.warning_count, batch.error_count), (3, 1, 1))
        self.assertEqual(batch.warnings[0].field, "salary_min")
        self.assertEqual(process_opportunities(batch.opportunities, create_daniel_profile()).total_received, 3)

    def test_sales_and_irrelevant_roles_keep_existing_decision_logic(self) -> None:
        batch = ingest_batch(fixture_payload()["data"], GetOnBoardJobAdapter())
        decisions = {item.normalized_job.role: item.retention_decision.value for item in process_opportunities(batch.opportunities, create_daniel_profile()).ranked_opportunities}
        self.assertNotEqual(decisions["Account Executive LATAM"], "REJECT")
        self.assertEqual(decisions["Software Engineer"], "REJECT")

    def test_real_relationship_shapes_and_unix_dates_convert_without_warnings(self) -> None:
        batch = ingest_batch(real_shape_records(), GetOnBoardJobAdapter())
        self.assertEqual(
            (batch.converted_count, batch.warning_count, batch.error_count),
            (3, 0, 0),
        )
        fully_remote, no_remote, remote_local = batch.opportunities
        self.assertEqual(fully_remote.location, "Remote")
        self.assertTrue(fully_remote.remote)
        self.assertIsNone(fully_remote.employment_type)
        self.assertIsNone(fully_remote.job_level)
        self.assertIsNotNone(fully_remote.date_posted)
        self.assertEqual(no_remote.role, "Ejecutivo/a de Ventas B2B Software")
        self.assertEqual(no_remote.location, "Location unspecified")
        self.assertFalse(no_remote.remote)
        self.assertEqual(
            remote_local.location,
            "Remote — location restricted (unspecified)",
        )
        self.assertTrue(remote_local.remote)

    def test_non_remote_relationship_location_reaches_existing_remote_gate(self) -> None:
        result = GetOnBoardJobAdapter().adapt(real_shape_records()[1])
        self.assertTrue(result.success)
        assert result.opportunity is not None
        ranked = process_opportunities(
            [result.opportunity], create_daniel_profile()
        ).ranked_opportunities[0]
        self.assertEqual(ranked.retention_decision.value, "REJECT")

    def test_invalid_timestamp_warns_without_losing_job(self) -> None:
        record = dict(real_shape_records()[0])
        record["attributes"] = {
            **record["attributes"],
            "published_at": {"unexpected": "date"},
        }
        result = GetOnBoardJobAdapter().adapt(record)
        self.assertTrue(result.success)
        self.assertEqual([warning.field for warning in result.warnings], ["date_posted"])
        self.assertIsNone(result.opportunity.date_posted)  # type: ignore[union-attr]

    def test_malformed_relationships_warn_but_valid_job_survives(self) -> None:
        record = dict(real_shape_records()[0])
        record["attributes"] = {
            **record["attributes"],
            "modality": {"unexpected": {"id": 1}},
            "seniority": {"data": "not-a-resource"},
            "location_cities": {"data": [None]},
        }
        result = GetOnBoardJobAdapter().adapt(record)
        self.assertTrue(result.success)
        self.assertEqual(
            {warning.field for warning in result.warnings},
            {"employment_type", "job_level", "location"},
        )


class GetOnBoardRegistryTests(unittest.TestCase):
    def test_definition_has_public_observational_contract(self) -> None:
        definition = create_default_source_registry().get("getonboard")
        self.assertEqual(definition.source_type, SourceType.GLOBAL_BOARD)
        self.assertEqual((definition.source_family, definition.source_instance), ("getonboard", "getonboard:global"))
        self.assertTrue(definition.capabilities.global_search)
        self.assertTrue(definition.capabilities.supports_query)
        self.assertTrue(definition.capabilities.supports_pagination)
        self.assertFalse(definition.capabilities.requires_auth)
        self.assertTrue(definition.capabilities.requires_attribution)
        self.assertEqual(definition.capabilities.lifecycle_authority, LifecycleAuthority.OBSERVATIONAL)
        self.assertEqual(definition.request_budget, 1)
        self.assertEqual(definition.default_config, {"query": "sales", "page": 1, "per_page": 20})

    def test_contribution_order_places_getonboard_after_remoteok(self) -> None:
        self.assertEqual(GLOBAL_SOURCE_ORDER[-2:], ("remoteok", "getonboard"))

    def test_greenhouse_remains_primary_over_observational_duplicate(self) -> None:
        greenhouse = JobOpportunity(
            company="Acme LATAM", role="Account Executive LATAM",
            job_url="https://boards.greenhouse.io/acme/jobs/101",
            source="Greenhouse public Job Board", location="Latin America",
            remote=True, brazil_eligible=True, source_id="greenhouse:acme",
            source_family="greenhouse", source_instance="greenhouse:acme",
            source_type="TENANT_BOARD", lifecycle_authority="AUTHORITATIVE",
        )
        gob = GetOnBoardJobAdapter().adapt(fixture_payload()["data"][0]).opportunity
        assert gob is not None
        gob.source_id, gob.source_family = "getonboard", "getonboard"
        gob.source_instance, gob.source_type = "getonboard:global", "GLOBAL_BOARD"
        gob.lifecycle_authority = "OBSERVATIONAL"
        with JobRepository(":memory:") as repository:
            sync_opportunities(
                process_opportunities([gob, greenhouse], create_daniel_profile()),
                repository,
            )
            stored = repository.list_all()[0]
            self.assertEqual(stored.opportunity.source_family, "greenhouse")
            self.assertEqual(repository.observation_count(), 2)


if __name__ == "__main__":
    unittest.main()
