"""Testes offline do push do CRM para Google Sheets."""

import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path

from daniel_job_agent import (
    AUTOMATIC_SHEET_HEADERS,
    GOOGLE_SHEET_COLUMNS,
    MANUAL_SHEET_HEADERS,
    ApplicationStatus,
    GoogleSheetsConfig,
    JobOpportunity,
    JobRepository,
    LocalCRM,
    RetentionDecision,
    build_sheet_values,
    create_daniel_profile,
    process_opportunities,
    push_crm_to_google_sheets,
    record_to_sheet_row,
    sync_opportunities,
)
from daniel_job_agent.google_sheets_cli import build_parser


class FakeRequest:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result or {}
        self.error = error

    def execute(self):
        if self.error:
            raise self.error
        return self.result


class FakeValuesResource:
    def __init__(self) -> None:
        self.clear_calls: list[dict[str, object]] = []
        self.update_calls: list[dict[str, object]] = []

    def clear(self, **kwargs):
        self.clear_calls.append(kwargs)
        return FakeRequest()

    def update(self, **kwargs):
        self.update_calls.append(kwargs)
        return FakeRequest({"updatedRows": len(kwargs["body"]["values"])})


class FakeSpreadsheetsResource:
    def __init__(self, sheet_name: str | None = None, *, fail: bool = False) -> None:
        self.sheets = [] if sheet_name is None else [
            {"properties": {"title": sheet_name, "sheetId": 42}}
        ]
        self.fail = fail
        self.values_resource = FakeValuesResource()
        self.add_calls: list[dict[str, object]] = []
        self.format_calls: list[dict[str, object]] = []

    def get(self, **kwargs):
        if self.fail:
            return FakeRequest(error=RuntimeError("simulated API failure"))
        return FakeRequest({"sheets": list(self.sheets)})

    def batchUpdate(self, **kwargs):
        requests = kwargs["body"]["requests"]
        if requests and "addSheet" in requests[0]:
            self.add_calls.append(kwargs)
            title = requests[0]["addSheet"]["properties"]["title"]
            self.sheets.append({"properties": {"title": title, "sheetId": 99}})
            return FakeRequest(
                {"replies": [{"addSheet": {"properties": {"sheetId": 99}}}]}
            )
        self.format_calls.append(kwargs)
        return FakeRequest()

    def values(self):
        return self.values_resource


class FakeService:
    def __init__(self, sheet_name: str | None = None, *, fail: bool = False) -> None:
        self.resource = FakeSpreadsheetsResource(sheet_name, fail=fail)

    def spreadsheets(self):
        return self.resource


def make_job(identifier: str, **changes: object) -> JobOpportunity:
    values: dict[str, object] = {
        "company": f"Company {identifier}",
        "role": "Account Executive",
        "job_url": f"https://example.test/{identifier}",
        "source": "Offline fixture",
        "location": "Remote - LATAM",
        "remote": True,
        "brazil_eligible": True,
        "external_id": identifier,
        "still_open": True,
        "date_found": date(2026, 8, 15),
    }
    values.update(changes)
    return JobOpportunity(**values)  # type: ignore[arg-type]


class GoogleSheetsPayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = JobRepository(":memory:")
        jobs = [
            make_job(
                "keep",
                company="Zulu Keep",
                requirements=["One", "Two"],
                salary_min=80_000,
            ),
            make_job(
                "review",
                company="Alpha Review",
                role="Revenue Enablement Specialist",
                location="Remote",
                still_open=None,
            ),
            make_job("reject", role="Software Engineer", still_open=False),
        ]
        result = sync_opportunities(
            process_opportunities(jobs, create_daniel_profile()), self.repository
        )
        self.crm = LocalCRM(self.repository)
        self.crm.update_manual_fields(
            result.new_jobs[0].internal_id,
            application_status=ApplicationStatus.APPLIED,
            notes="Manual note",
            next_step="Interview",
        )

    def tearDown(self) -> None:
        self.repository.close()

    def test_visual_contract_has_31_friendly_columns_and_id_last(self) -> None:
        headers = [column.header for column in GOOGLE_SHEET_COLUMNS]
        self.assertEqual(len(headers), 31)
        self.assertEqual(headers[:5], [
            "Company", "Role", "Match Score", "Decision", "Application Status"
        ])
        self.assertEqual(headers[-1], "Internal ID")
        self.assertNotIn("match_score", headers)

    def test_manual_and_automatic_header_groups_cover_contract(self) -> None:
        headers = {column.header for column in GOOGLE_SHEET_COLUMNS}
        self.assertEqual(set(MANUAL_SHEET_HEADERS) | set(AUTOMATIC_SHEET_HEADERS), headers)
        self.assertEqual(set(MANUAL_SHEET_HEADERS) & set(AUTOMATIC_SHEET_HEADERS), set())
        self.assertIn("Notes", MANUAL_SHEET_HEADERS)
        self.assertIn("Match Score", AUTOMATIC_SHEET_HEADERS)

    def test_record_conversion_handles_none_lists_booleans_and_manual_fields(self) -> None:
        record = next(
            item for item in self.crm.list_records()
            if item.retention_decision is RetentionDecision.REVIEW
        )
        row = record_to_sheet_row(record)
        fields = [column.field for column in GOOGLE_SHEET_COLUMNS]
        self.assertEqual(row[fields.index("still_open")], "")
        self.assertIsInstance(
            record_to_sheet_row(self.crm.list_records()[0])[fields.index("still_open")],
            bool,
        )
        self.assertEqual(row[-1], record.internal_id)
        self.assertIsInstance(row[fields.index("positive_reasons")], str)
        self.assertEqual(len(row), 31)

    def test_sheet_values_preserve_crm_default_order_and_headers(self) -> None:
        records = self.crm.list_records()
        values = build_sheet_values(records)
        self.assertEqual(values[0], [column.header for column in GOOGLE_SHEET_COLUMNS])
        self.assertEqual(
            [row[3] for row in values[1:]],
            ["KEEP", "REVIEW", "REJECT"],
        )
        self.assertEqual(values[1][7], "Manual note")


class GoogleSheetsPushTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = JobRepository(":memory:")
        sync_opportunities(
            process_opportunities([make_job("1")], create_daniel_profile()),
            self.repository,
        )
        self.config = GoogleSheetsConfig(spreadsheet_id="test-sheet-id")

    def tearDown(self) -> None:
        self.repository.close()

    def test_missing_tab_is_created_then_headers_and_data_are_written(self) -> None:
        service = FakeService()
        result = push_crm_to_google_sheets(self.repository, self.config, service=service)
        self.assertEqual(len(service.resource.add_calls), 1)
        self.assertEqual(len(service.resource.values_resource.clear_calls), 1)
        self.assertEqual(len(service.resource.values_resource.update_calls), 1)
        payload = service.resource.values_resource.update_calls[0]["body"]["values"]
        self.assertEqual(payload[0][0], "Company")
        self.assertEqual(len(payload), 2)
        self.assertTrue(result.success)
        self.assertEqual((result.rows_written, result.columns_written), (1, 31))
        self.assertIsNone(result.error)

    def test_existing_tab_is_not_created_again_and_formatting_is_batched(self) -> None:
        service = FakeService("Job CRM")
        push_crm_to_google_sheets(self.repository, self.config, service=service)
        self.assertEqual(service.resource.add_calls, [])
        self.assertEqual(len(service.resource.format_calls), 1)
        requests = service.resource.format_calls[0]["body"]["requests"]
        self.assertTrue(any("setBasicFilter" in request for request in requests))
        self.assertTrue(any("autoResizeDimensions" in request for request in requests))

    def test_api_error_returns_structured_failure(self) -> None:
        result = push_crm_to_google_sheets(
            self.repository,
            self.config,
            service=FakeService(fail=True),
            now=datetime(2026, 8, 15, tzinfo=timezone.utc),
        )
        self.assertFalse(result.success)
        self.assertEqual(result.rows_written, 0)
        self.assertIn("simulated API failure", result.error or "")
        self.assertEqual(result.synced_at, datetime(2026, 8, 15, tzinfo=timezone.utc))


class GoogleSheetsConfigurationTests(unittest.TestCase):
    def test_paths_and_sheet_name_are_configurable_without_real_credentials(self) -> None:
        config = GoogleSheetsConfig(
            spreadsheet_id="configured-id",
            sheet_name="My CRM",
            credentials_path=Path("private/client.json"),
            token_path=Path("private/oauth-token.json"),
        )
        self.assertEqual(config.credentials_path, Path("private/client.json"))
        self.assertEqual(config.token_path, Path("private/oauth-token.json"))
        self.assertEqual(config.sheet_name, "My CRM")

    def test_spreadsheet_id_is_required_in_config_and_cli(self) -> None:
        with self.assertRaisesRegex(ValueError, "required"):
            GoogleSheetsConfig(spreadsheet_id=" ")
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                build_parser().parse_args(["push"])

    def test_cli_accepts_all_configurable_paths(self) -> None:
        args = build_parser().parse_args(
            [
                "push",
                "--spreadsheet-id", "sheet-123",
                "--sheet-name", "Applications",
                "--credentials", "/tmp/fake-credentials.json",
                "--token", "/tmp/fake-token.json",
                "--db", "/tmp/fake.db",
            ]
        )
        self.assertEqual(args.spreadsheet_id, "sheet-123")
        self.assertEqual(args.credentials, Path("/tmp/fake-credentials.json"))
        self.assertEqual(args.token, Path("/tmp/fake-token.json"))


if __name__ == "__main__":
    unittest.main()
