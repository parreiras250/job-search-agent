"""Testes offline da camada explícita de CRM local."""

import unittest
from contextlib import redirect_stderr
from datetime import date, datetime, timedelta, timezone
from io import StringIO

from daniel_job_agent import (
    AUTOMATIC_FIELDS,
    CRM_COLUMNS,
    MANUAL_FIELDS,
    ApplicationStatus,
    CRMRecordNotFound,
    CRMValidationError,
    JobOpportunity,
    JobRepository,
    LocalCRM,
    RetentionDecision,
    create_daniel_profile,
    process_opportunities,
    records_to_table,
    sync_opportunities,
)
from daniel_job_agent.crm_cli import build_parser


def make_job(identifier: str, **changes: object) -> JobOpportunity:
    values: dict[str, object] = {
        "company": f"Company {identifier}",
        "role": "Account Executive",
        "job_url": f"https://example.test/jobs/{identifier}",
        "source": "Fixture Source",
        "location": "Remote - LATAM",
        "remote": True,
        "brazil_eligible": True,
        "external_id": identifier,
        "date_found": date(2026, 8, 15),
        "date_posted": date(2026, 8, 14),
        "still_open": True,
        "salary_min": 70_000,
        "salary_max": 100_000,
        "salary_currency": "USD",
        "salary_period": "year",
        "salary_text": "$70k-$100k",
    }
    values.update(changes)
    return JobOpportunity(**values)  # type: ignore[arg-type]


class LocalCRMTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = JobRepository(":memory:")
        self.crm = LocalCRM(self.repository)
        self.time = datetime(2026, 8, 15, 12, tzinfo=timezone.utc)
        jobs = [
            make_job("keep", company="Zulu Keep"),
            make_job(
                "review",
                company="Alpha Review",
                role="Revenue Enablement Specialist",
                location="Remote",
                still_open=None,
                source="Other Source",
            ),
            make_job("reject", company="Beta Reject", role="Software Engineer", still_open=False),
        ]
        self.first_sync = sync_opportunities(
            process_opportunities(jobs, create_daniel_profile()),
            self.repository,
            now=self.time,
        )
        self.ids = {
            item.opportunity.external_id: item.internal_id
            for item in self.first_sync.new_jobs
        }

    def tearDown(self) -> None:
        self.repository.close()

    def test_crm_record_contains_automatic_and_manual_fields(self) -> None:
        record = self.crm.get(self.ids["keep"])
        assert record is not None
        self.assertEqual(record.company, "Zulu Keep")
        self.assertEqual(record.retention_decision, RetentionDecision.KEEP)
        self.assertEqual(record.salary_min, 70_000)
        self.assertTrue(record.positive_reasons)
        self.assertEqual(record.application_status, ApplicationStatus.NOT_APPLIED)
        self.assertIsNone(record.notes)

    def test_column_contract_and_field_groups_are_explicit_and_disjoint(self) -> None:
        self.assertEqual(CRM_COLUMNS[0:5], (
            "internal_id", "company", "role", "match_score", "retention_decision"
        ))
        self.assertEqual(CRM_COLUMNS[-3:], ("first_seen_at", "last_seen_at", "last_checked"))
        self.assertEqual(set(AUTOMATIC_FIELDS) & set(MANUAL_FIELDS), set())
        self.assertEqual(set(CRM_COLUMNS), set(AUTOMATIC_FIELDS) | set(MANUAL_FIELDS))

    def test_updates_all_supported_manual_field_types_without_clearing_others(self) -> None:
        updated = self.crm.update_manual_fields(
            self.ids["keep"],
            application_status="APPLIED",
            applied_date="2026-08-15",
            recruiter_name="Ana",
            recruiter_email="ana@example.com",
            next_step="Recruiter screen",
            next_step_date=date(2026, 8, 20),
            notes="Applied through the company site",
        )
        self.assertEqual(updated.application_status, ApplicationStatus.APPLIED)
        self.assertEqual(updated.applied_date, date(2026, 8, 15))
        self.assertEqual(updated.recruiter_name, "Ana")
        self.assertEqual(updated.recruiter_email, "ana@example.com")
        self.assertEqual(updated.next_step, "Recruiter screen")
        self.assertEqual(updated.next_step_date, date(2026, 8, 20))
        self.assertEqual(updated.notes, "Applied through the company site")

        changed_status = self.crm.update_manual_fields(
            self.ids["keep"], application_status=ApplicationStatus.INTERVIEW
        )
        self.assertEqual(changed_status.application_status, ApplicationStatus.INTERVIEW)
        self.assertEqual(changed_status.notes, "Applied through the company site")

    def test_empty_notes_are_allowed(self) -> None:
        updated = self.crm.update_manual_fields(self.ids["keep"], notes="")
        self.assertEqual(updated.notes, "")

    def test_automatic_or_unknown_field_update_is_rejected_without_change(self) -> None:
        before = self.crm.get(self.ids["keep"])
        with self.assertRaisesRegex(CRMValidationError, "Cannot edit"):
            self.crm.update_manual_fields(
                self.ids["keep"], match_score=0, company="Changed"
            )
        self.assertEqual(self.crm.get(self.ids["keep"]), before)

    def test_invalid_status_is_rejected_without_change(self) -> None:
        with self.assertRaisesRegex(CRMValidationError, "Invalid application status"):
            self.crm.update_manual_fields(self.ids["keep"], application_status="UNKNOWN")
        self.assertEqual(
            self.crm.get(self.ids["keep"]).application_status,  # type: ignore[union-attr]
            ApplicationStatus.NOT_APPLIED,
        )

    def test_invalid_date_is_rejected_without_change(self) -> None:
        with self.assertRaisesRegex(CRMValidationError, "YYYY-MM-DD"):
            self.crm.update_manual_fields(self.ids["keep"], applied_date="15/08/2026")
        self.assertIsNone(self.crm.get(self.ids["keep"]).applied_date)  # type: ignore[union-attr]

    def test_get_by_internal_id_and_missing_record_are_safe(self) -> None:
        self.assertEqual(self.crm.get(self.ids["keep"]).internal_id, self.ids["keep"])  # type: ignore[union-attr]
        self.assertIsNone(self.crm.get(999_999))
        with self.assertRaises(CRMRecordNotFound):
            self.crm.update_manual_fields(999_999, notes="No record")

    def test_filters_by_manual_and_automatic_fields(self) -> None:
        self.crm.update_manual_fields(self.ids["keep"], application_status="APPLIED")
        self.assertEqual(len(self.crm.list_records(application_status="APPLIED")), 1)
        self.assertEqual(len(self.crm.list_records(retention_decision="REVIEW")), 1)
        self.assertEqual(len(self.crm.list_records(still_open=True)), 1)
        self.assertEqual(len(self.crm.list_records(still_open=False)), 1)
        self.assertEqual(len(self.crm.list_records(source="other source")), 1)
        self.assertEqual(len(self.crm.list_records(minimum_score=90)), 1)

    def test_default_order_is_decision_score_then_company_role(self) -> None:
        records = self.crm.list_records()
        self.assertEqual(
            [record.retention_decision for record in records],
            [RetentionDecision.KEEP, RetentionDecision.REVIEW, RetentionDecision.REJECT],
        )

    def test_newest_order_uses_last_seen(self) -> None:
        later = self.time + timedelta(days=1)
        sync_opportunities(
            process_opportunities([make_job("review", company="Alpha Review", role="Revenue Enablement Specialist", location="Remote", still_open=None, source="Other Source")], create_daniel_profile()),
            self.repository,
            now=later,
        )
        newest = self.crm.list_records(order="newest")
        self.assertEqual(newest[0].internal_id, self.ids["review"])

    def test_tabular_representation_has_stable_headers_and_simple_rows(self) -> None:
        records = self.crm.list_records()
        table = records_to_table(records)
        self.assertEqual(table.headers, list(CRM_COLUMNS))
        self.assertEqual(len(table.rows), 3)
        self.assertTrue(all(not isinstance(value, list) for row in table.rows for value in row))
        url_index = table.headers.index("job_url")
        self.assertEqual(table.rows[0][url_index], records[0].job_url)

    def test_list_formatting_is_deterministic(self) -> None:
        record = self.crm.get(self.ids["keep"])
        assert record is not None
        first = records_to_table([record])
        second = records_to_table([record])
        reasons = first.rows[0][first.headers.index("positive_reasons")]
        self.assertEqual(first, second)
        self.assertEqual(reasons, " | ".join(record.positive_reasons))

    def test_manual_fields_survive_later_automatic_sync(self) -> None:
        self.crm.update_manual_fields(
            self.ids["keep"],
            application_status="APPLIED",
            notes="Preserve after agent sync",
        )
        changed = make_job("keep", company="Zulu Keep", salary_min=80_000)
        sync_opportunities(
            process_opportunities([changed], create_daniel_profile()),
            self.repository,
            now=self.time + timedelta(days=1),
        )
        record = self.crm.get(self.ids["keep"])
        assert record is not None
        self.assertEqual(record.application_status, ApplicationStatus.APPLIED)
        self.assertEqual(record.notes, "Preserve after agent sync")
        self.assertEqual(record.salary_min, 80_000)


class CRMCLIParserTests(unittest.TestCase):
    def test_update_accepts_iso_manual_dates(self) -> None:
        args = build_parser().parse_args(
            [
                "update",
                "12",
                "--status",
                "APPLIED",
                "--applied-date",
                "2026-08-15",
                "--next-step-date",
                "2026-08-20",
            ]
        )
        self.assertEqual(args.internal_id, 12)
        self.assertEqual(args.applied_date, date(2026, 8, 15))
        self.assertEqual(args.next_step_date, date(2026, 8, 20))

    def test_update_rejects_non_iso_date_before_opening_repository(self) -> None:
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                build_parser().parse_args(
                    ["update", "12", "--applied-date", "15/08/2026"]
                )


if __name__ == "__main__":
    unittest.main()
