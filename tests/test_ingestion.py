"""Testes da conversão de registros brutos em JobOpportunity."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from daniel_job_agent import (  # noqa: E402
    GenericJobAdapter,
    IngestionErrorType,
    MockGreenhouseAdapter,
    MockLeverAdapter,
    combine_ingestion_batches,
    create_daniel_profile,
    ingest_batch,
    process_opportunities,
)
from daniel_job_agent.demo_data import create_ingestion_demo_records  # noqa: E402


def generic_record(**changes: object) -> dict[str, object]:
    record: dict[str, object] = {
        "company": " Example Co ",
        "title": " Account  Executive ",
        "url": " https://example.com/jobs/1 ",
        "location": " Remote - LATAM ",
        "remote": True,
        "brazil_eligible": True,
    }
    record.update(changes)
    return record


class AdapterTests(unittest.TestCase):
    def test_generic_adapter_converts_and_normalizes_valid_record(self) -> None:
        result = GenericJobAdapter().adapt(generic_record())

        self.assertTrue(result.success)
        self.assertEqual(result.opportunity.company, "Example Co")  # type: ignore[union-attr]
        self.assertEqual(result.opportunity.role, "Account Executive")  # type: ignore[union-attr]

    def test_mock_greenhouse_adapter_maps_its_field_names(self) -> None:
        result = MockGreenhouseAdapter().adapt(
            {
                "organization_name": "Green Cloud",
                "position_name": "Enterprise Account Executive",
                "absolute_url": "https://example.com/green/1",
                "workplace": "Remote - Brazil",
                "remote": True,
                "brazil_eligible": True,
            }
        )

        self.assertTrue(result.success)
        self.assertEqual(result.opportunity.source, "Mock Greenhouse")  # type: ignore[union-attr]

    def test_mock_lever_adapter_maps_its_field_names(self) -> None:
        result = MockLeverAdapter().adapt(
            {
                "employer": "Lever Labs",
                "job_title": "SDR",
                "apply_url": "https://example.com/lever/1",
                "region": "Worldwide Remote",
                "remote": "true",
                "brazil_eligible": "true",
                "commitment": "Contractor",
            }
        )

        self.assertTrue(result.success)
        self.assertEqual(result.opportunity.employment_type, "Contractor")  # type: ignore[union-attr]

    def test_missing_or_empty_required_field_returns_structured_error(self) -> None:
        for record in (
            {key: value for key, value in generic_record().items() if key != "company"},
            generic_record(title="   "),
        ):
            with self.subTest(record=record):
                result = GenericJobAdapter().adapt(record)
                self.assertFalse(result.success)
                self.assertEqual(
                    result.error.error_type,  # type: ignore[union-attr]
                    IngestionErrorType.MISSING_REQUIRED_FIELDS,
                )

    def test_missing_optional_fields_are_reported_without_failure(self) -> None:
        result = GenericJobAdapter().adapt(generic_record())

        self.assertTrue(result.success)
        self.assertIn("description", result.optional_fields_missing)
        self.assertIsNone(result.opportunity.description)  # type: ignore[union-attr]

    def test_accepts_explicit_real_and_string_booleans(self) -> None:
        false_values = GenericJobAdapter().adapt(
            generic_record(remote=False, brazil_eligible="false")
        )
        true_values = GenericJobAdapter().adapt(
            generic_record(remote="true", brazil_eligible=True)
        )

        self.assertIs(false_values.opportunity.remote, False)  # type: ignore[union-attr]
        self.assertIs(false_values.opportunity.brazil_eligible, False)  # type: ignore[union-attr]
        self.assertIs(true_values.opportunity.remote, True)  # type: ignore[union-attr]
        self.assertIs(true_values.opportunity.brazil_eligible, True)  # type: ignore[union-attr]

    def test_missing_boolean_fields_remain_unknown(self) -> None:
        record = generic_record()
        del record["remote"]
        del record["brazil_eligible"]

        result = GenericJobAdapter().adapt(record)

        self.assertTrue(result.success)
        self.assertIsNone(result.opportunity.remote)  # type: ignore[union-attr]
        self.assertIsNone(result.opportunity.brazil_eligible)  # type: ignore[union-attr]

    def test_accepts_numeric_and_simple_string_salary(self) -> None:
        numeric = GenericJobAdapter().adapt(generic_record(base_salary=75000))
        text = GenericJobAdapter().adapt(generic_record(base_salary="80000.50"))

        self.assertEqual(numeric.opportunity.base_salary, 75000.0)  # type: ignore[union-attr]
        self.assertEqual(text.opportunity.base_salary, 80000.5)  # type: ignore[union-attr]

    def test_unsupported_optional_salary_returns_warning_and_keeps_job(self) -> None:
        for salary in ("$80k-$120k", "80,000 USD annually"):
            with self.subTest(salary=salary):
                result = GenericJobAdapter().adapt(
                    generic_record(base_salary=salary)
                )

                self.assertTrue(result.success)
                self.assertIsNone(result.opportunity.base_salary)  # type: ignore[union-attr]
                self.assertEqual(len(result.warnings), 1)
                self.assertEqual(result.warnings[0].field, "base_salary")

    def test_unsupported_optional_ote_also_returns_warning(self) -> None:
        result = GenericJobAdapter().adapt(generic_record(ote="$140k OTE"))

        self.assertTrue(result.success)
        self.assertIsNone(result.opportunity.ote)  # type: ignore[union-attr]
        self.assertEqual(result.warnings[0].field, "ote")


class BatchAndPipelineIntegrationTests(unittest.TestCase):
    def test_invalid_record_does_not_abort_batch(self) -> None:
        batch = ingest_batch(
            [generic_record(), generic_record(title="")],
            GenericJobAdapter(),
        )

        self.assertEqual(batch.total_received, 2)
        self.assertEqual(batch.converted_count, 1)
        self.assertEqual(batch.error_count, 1)
        self.assertEqual(batch.warning_count, 0)
        self.assertEqual(len(batch.opportunities), 1)
        self.assertEqual(len(batch.errors), 1)
        self.assertEqual(batch.errors[0].record_index, 2)

    def test_ingested_opportunities_feed_existing_pipeline(self) -> None:
        batch = ingest_batch(
            [generic_record(), generic_record(title="SDR", url="https://example.com/jobs/2")],
            GenericJobAdapter(),
        )
        pipeline = process_opportunities(batch.opportunities, create_daniel_profile())

        self.assertEqual(pipeline.total_received, 2)
        self.assertEqual(pipeline.unique_opportunities, 2)
        self.assertEqual(len(pipeline.ranked_opportunities), 2)

    def test_duplicate_from_different_sources_is_detected(self) -> None:
        generic = ingest_batch([generic_record()], GenericJobAdapter())
        greenhouse = ingest_batch(
            [
                {
                    "organization_name": "example co",
                    "position_name": "account executive",
                    "absolute_url": "https://different.example/jobs/99",
                    "workplace": "Remote - LATAM",
                }
            ],
            MockGreenhouseAdapter(),
        )
        combined = combine_ingestion_batches([generic, greenhouse])
        pipeline = process_opportunities(combined.opportunities, create_daniel_profile())

        self.assertEqual(combined.converted_count, 2)
        self.assertEqual(pipeline.unique_opportunities, 1)
        self.assertEqual(pipeline.duplicates_detected, 1)

    def test_fictional_ingestion_dataset_runs_completely(self) -> None:
        records = create_ingestion_demo_records()
        combined = combine_ingestion_batches(
            [
                ingest_batch(records["generic"], GenericJobAdapter()),
                ingest_batch(records["greenhouse"], MockGreenhouseAdapter()),
                ingest_batch(records["lever"], MockLeverAdapter()),
            ]
        )
        pipeline = process_opportunities(
            combined.opportunities, create_daniel_profile()
        )

        self.assertEqual(combined.total_received, 12)
        self.assertEqual(combined.converted_count, 10)
        self.assertEqual(combined.warning_count, 1)
        self.assertEqual(combined.error_count, 2)
        self.assertEqual(pipeline.unique_opportunities, 9)
        self.assertEqual(pipeline.duplicates_detected, 1)


if __name__ == "__main__":
    unittest.main()
