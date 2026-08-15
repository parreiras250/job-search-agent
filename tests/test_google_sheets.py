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
    SheetPullResult,
    build_sheet_values,
    create_daniel_profile,
    process_opportunities,
    pull_manual_fields_from_google_sheets,
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
    def __init__(
        self, values: list[list[object]] | None = None, *, fail: bool = False
    ) -> None:
        self.sheet_values = values or []
        self.fail = fail
        self.get_calls: list[dict[str, object]] = []
        self.clear_calls: list[dict[str, object]] = []
        self.update_calls: list[dict[str, object]] = []

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        if self.fail:
            return FakeRequest(error=RuntimeError("simulated API failure"))
        return FakeRequest({"values": self.sheet_values})

    def clear(self, **kwargs):
        self.clear_calls.append(kwargs)
        self.sheet_values = []
        return FakeRequest()

    def update(self, **kwargs):
        self.update_calls.append(kwargs)
        self.sheet_values = kwargs["body"]["values"]
        return FakeRequest({"updatedRows": len(kwargs["body"]["values"])})


class FakeSpreadsheetsResource:
    def __init__(
        self,
        sheet_name: str | None = None,
        *,
        fail: bool = False,
        values: list[list[object]] | None = None,
    ) -> None:
        self.sheets = [] if sheet_name is None else [
            {"properties": {"title": sheet_name, "sheetId": 42}}
        ]
        self.fail = fail
        self.values_resource = FakeValuesResource(values, fail=fail)
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
    def __init__(
        self,
        sheet_name: str | None = None,
        *,
        fail: bool = False,
        values: list[list[object]] | None = None,
    ) -> None:
        self.resource = FakeSpreadsheetsResource(
            sheet_name, fail=fail, values=values
        )

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

    def test_crm_visual_formatting_has_score_decision_status_and_manual_rules(self) -> None:
        service = FakeService("Job CRM")
        service.resource.sheets[0]["conditionalFormats"] = [{}, {}]
        push_crm_to_google_sheets(self.repository, self.config, service=service)
        requests = service.resource.format_calls[0]["body"]["requests"]
        conditional = [request["addConditionalFormatRule"] for request in requests if "addConditionalFormatRule" in request]
        score_rules = [
            rule for rule in conditional
            if rule["rule"]["ranges"][0]["startColumnIndex"] == 2
        ]
        decision_rules = [
            rule for rule in conditional
            if rule["rule"]["ranges"][0]["startColumnIndex"] == 3
        ]
        status_rules = [
            rule for rule in conditional
            if rule["rule"]["ranges"][0]["startColumnIndex"] == 4
        ]
        validations = [request["setDataValidation"] for request in requests if "setDataValidation" in request]
        manual_backgrounds = [
            request["repeatCell"] for request in requests
            if "repeatCell" in request
            and request["repeatCell"]["range"].get("startRowIndex") == 1
            and "backgroundColor" in request["repeatCell"]["cell"].get("userEnteredFormat", {})
        ]
        self.assertEqual(len(score_rules), 5)
        self.assertEqual(len(decision_rules), 3)
        self.assertEqual(len(status_rules), len(ApplicationStatus))
        deleted_rules = [
            request["deleteConditionalFormatRule"]
            for request in requests
            if "deleteConditionalFormatRule" in request
        ]
        self.assertEqual([item["index"] for item in deleted_rules], [1, 0])
        self.assertEqual(len(validations), 1)
        dropdown = validations[0]["rule"]["condition"]["values"]
        self.assertEqual(
            [item["userEnteredValue"] for item in dropdown],
            [status.value for status in ApplicationStatus],
        )
        self.assertEqual(len(manual_backgrounds), 7)

    def test_push_preserves_unsynced_manual_sheet_edits_by_internal_id(self) -> None:
        generated = build_sheet_values(LocalCRM(self.repository).list_records())
        headers = generated[0]
        generated[1][headers.index("Application Status")] = "INTERVIEW"
        generated[1][headers.index("Notes")] = "Edited only in Sheets"
        service = FakeService("Job CRM", values=generated)
        result = push_crm_to_google_sheets(
            self.repository, self.config, service=service
        )
        payload = service.resource.values_resource.update_calls[0]["body"]["values"]
        self.assertTrue(result.success)
        self.assertEqual(payload[1][headers.index("Application Status")], "INTERVIEW")
        self.assertEqual(payload[1][headers.index("Notes")], "Edited only in Sheets")

    def test_push_refuses_incompatible_sheet_before_clearing_it(self) -> None:
        incompatible = [["Company", "Internal ID"], ["Human edit", 1]]
        service = FakeService("Job CRM", values=incompatible)
        result = push_crm_to_google_sheets(
            self.repository, self.config, service=service
        )
        self.assertFalse(result.success)
        self.assertIn("Missing required headers", result.error or "")
        self.assertEqual(service.resource.values_resource.clear_calls, [])
        self.assertEqual(service.resource.values_resource.sheet_values, incompatible)

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

    def test_cli_supports_explicit_pull_with_same_configuration(self) -> None:
        args = build_parser().parse_args(
            ["pull", "--spreadsheet-id", "sheet-123", "--sheet-name", "Job CRM"]
        )
        self.assertEqual(args.command, "pull")
        self.assertEqual(args.spreadsheet_id, "sheet-123")


class GoogleSheetsPullTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = JobRepository(":memory:")
        sync = sync_opportunities(
            process_opportunities(
                [
                    make_job("one", company="Automatic Company"),
                    make_job("two", company="Second Company"),
                ],
                create_daniel_profile(),
            ),
            self.repository,
        )
        self.ids = {
            item.opportunity.external_id: item.internal_id for item in sync.new_jobs
        }
        self.crm = LocalCRM(self.repository)
        self.config = GoogleSheetsConfig(spreadsheet_id="test-sheet-id")

    def tearDown(self) -> None:
        self.repository.close()

    def values(self) -> list[list[object]]:
        return build_sheet_values(self.crm.list_records())

    @staticmethod
    def set_cell(
        values: list[list[object]], row: int, header: str, value: object
    ) -> None:
        values[row][values[0].index(header)] = value

    def pull(self, values: list[list[object]]) -> SheetPullResult:
        return pull_manual_fields_from_google_sheets(
            self.repository,
            self.config,
            service=FakeService("Job CRM", values=values),
        )

    def test_valid_pull_updates_multiple_manual_fields(self) -> None:
        values = self.values()
        self.set_cell(values, 1, "Application Status", "INTERVIEW")
        self.set_cell(values, 1, "Applied Date", "2026-08-10")
        self.set_cell(values, 1, "Recruiter Name", "Ana")
        self.set_cell(values, 1, "Recruiter Email", "ana@example.com")
        self.set_cell(values, 1, "Next Step", "Final interview")
        self.set_cell(values, 1, "Next Step Date", "2026-08-20")
        self.set_cell(values, 1, "Notes", "Updated from Sheets")
        result = self.pull(values)
        record = self.crm.get(int(values[1][-1]))
        assert record is not None
        self.assertEqual((result.rows_read, result.rows_valid, result.rows_updated), (2, 2, 1))
        self.assertEqual(result.rows_unchanged, 1)
        self.assertEqual(record.application_status, ApplicationStatus.INTERVIEW)
        self.assertEqual(record.applied_date, date(2026, 8, 10))
        self.assertEqual(record.recruiter_name, "Ana")
        self.assertEqual(record.next_step, "Final interview")
        self.assertEqual(record.notes, "Updated from Sheets")

    def test_unchanged_rows_are_counted_without_writes(self) -> None:
        result = self.pull(self.values())
        self.assertTrue(result.success)
        self.assertEqual((result.rows_valid, result.rows_unchanged, result.rows_updated), (2, 2, 0))

    def test_automatic_sheet_edits_are_ignored(self) -> None:
        values = self.values()
        internal_id = int(values[1][-1])
        self.set_cell(values, 1, "Company", "Malicious overwrite")
        self.set_cell(values, 1, "Match Score", 0)
        result = self.pull(values)
        record = self.crm.get(internal_id)
        assert record is not None
        self.assertTrue(result.success)
        self.assertEqual(result.rows_unchanged, 2)
        self.assertNotEqual(record.company, "Malicious overwrite")
        self.assertNotEqual(record.match_score, 0)

    def test_invalid_status_and_date_are_isolated_per_row(self) -> None:
        values = self.values()
        self.set_cell(values, 1, "Application Status", "NOT_A_STATUS")
        self.set_cell(values, 2, "Applied Date", "15/08/2026")
        result = self.pull(values)
        self.assertFalse(result.success)
        self.assertEqual((result.rows_errored, result.rows_updated), (2, 0))
        self.assertEqual(len(result.issues), 2)

    def test_empty_required_status_is_an_error_not_an_accidental_clear(self) -> None:
        values = self.values()
        self.set_cell(values, 1, "Application Status", "")
        result = self.pull(values)
        self.assertEqual(result.rows_errored, 1)
        record = self.crm.get(int(values[1][-1]))
        assert record is not None
        self.assertEqual(record.application_status, ApplicationStatus.NOT_APPLIED)

    def test_invalid_and_unknown_internal_ids_do_not_block_valid_row(self) -> None:
        values = self.values()
        self.set_cell(values, 1, "Internal ID", "invalid")
        self.set_cell(values, 2, "Notes", "Valid second row")
        result = self.pull(values)
        self.assertEqual((result.rows_errored, result.rows_updated), (1, 1))
        second = self.crm.get(int(values[2][-1]))
        assert second is not None
        self.assertEqual(second.notes, "Valid second row")

        unknown = self.values()
        self.set_cell(unknown, 1, "Internal ID", 999999)
        unknown_result = self.pull(unknown)
        self.assertGreaterEqual(unknown_result.rows_errored, 1)

    def test_missing_internal_id_or_manual_header_aborts_before_updates(self) -> None:
        for missing in ("Internal ID", "Notes"):
            with self.subTest(missing=missing):
                values = self.values()
                index = values[0].index(missing)
                for row in values:
                    row.pop(index)
                result = self.pull(values)
                self.assertFalse(result.success)
                self.assertEqual(result.rows_updated, 0)
                self.assertIn("Missing required headers", result.error or "")

    def test_duplicate_header_aborts_before_updates(self) -> None:
        values = self.values()
        values[0][0] = "Notes"
        result = self.pull(values)
        self.assertFalse(result.success)
        self.assertEqual(result.rows_updated, 0)
        self.assertIn("Duplicate headers", result.error or "")

    def test_empty_optional_cells_clear_existing_manual_values(self) -> None:
        internal_id = self.ids["one"]
        self.crm.update_manual_fields(
            internal_id,
            application_status="APPLIED",
            applied_date="2026-08-10",
            recruiter_name="Ana",
            recruiter_email="ana@example.com",
            next_step="Interview",
            next_step_date="2026-08-20",
            notes="Remove all optional values",
        )
        values = self.values()
        target_row = next(row for row in values[1:] if int(row[-1]) == internal_id)
        for header in (
            "Applied Date", "Recruiter Name", "Recruiter Email",
            "Next Step", "Next Step Date", "Notes",
        ):
            target_row[values[0].index(header)] = ""
        result = self.pull(values)
        record = self.crm.get(internal_id)
        assert record is not None
        self.assertEqual(result.rows_updated, 1)
        self.assertEqual(record.application_status, ApplicationStatus.APPLIED)
        self.assertIsNone(record.applied_date)
        self.assertIsNone(record.recruiter_name)
        self.assertIsNone(record.next_step_date)
        self.assertIsNone(record.notes)

    def test_pull_api_error_is_structured_without_database_change(self) -> None:
        before = self.crm.list_records()
        result = pull_manual_fields_from_google_sheets(
            self.repository,
            self.config,
            service=FakeService(fail=True),
        )
        self.assertFalse(result.success)
        self.assertEqual(result.issues[0].code, "api_error")
        self.assertEqual(self.crm.list_records(), before)


if __name__ == "__main__":
    unittest.main()
