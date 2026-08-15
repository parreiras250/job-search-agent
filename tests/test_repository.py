"""Testes offline da persistência SQLite."""

import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from daniel_job_agent import (
    ApplicationStatus,
    ApplicationTracking,
    JobOpportunity,
    JobRepository,
    RetentionDecision,
    RoleFamily,
    Seniority,
    SyncStatus,
    create_daniel_profile,
    process_opportunities,
    sync_opportunities,
)


def make_job(identifier: str = "1", **changes: object) -> JobOpportunity:
    values: dict[str, object] = {
        "company": f"Company {identifier}",
        "role": "Account Executive",
        "job_url": f"https://example.com/jobs/{identifier}",
        "source": "Local fixture",
        "location": "Remote - LATAM",
        "remote": True,
        "brazil_eligible": True,
        "external_id": identifier,
        "date_found": date(2026, 8, 10),
        "date_posted": date(2026, 8, 9),
    }
    values.update(changes)
    return JobOpportunity(**values)  # type: ignore[arg-type]


def processed(*jobs: JobOpportunity):
    return process_opportunities(jobs, create_daniel_profile())


class RepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = JobRepository(":memory:")
        self.first_time = datetime(2026, 8, 15, 12, tzinfo=timezone.utc)
        self.second_time = self.first_time + timedelta(hours=2)

    def tearDown(self) -> None:
        self.repository.close()

    def test_creates_schema_without_erasing_existing_database(self) -> None:
        first = sync_opportunities(processed(make_job()), self.repository, now=self.first_time)
        self.repository._create_schema()
        self.assertEqual(first.total_stored, 1)
        self.assertEqual(self.repository.count(), 1)

    def test_insert_is_new_and_second_identical_sync_is_existing(self) -> None:
        first = sync_opportunities(processed(make_job()), self.repository, now=self.first_time)
        second = sync_opportunities(processed(make_job()), self.repository, now=self.second_time)
        self.assertEqual((first.new, first.existing, first.updated), (1, 0, 0))
        self.assertEqual((second.new, second.existing, second.updated), (0, 1, 0))
        self.assertEqual(second.existing_jobs[0].status, SyncStatus.EXISTING)

    def test_automatic_change_is_updated_and_timestamps_are_correct(self) -> None:
        first = sync_opportunities(processed(make_job()), self.repository, now=self.first_time)
        changed = make_job(location="Worldwide", description="Updated description")
        second = sync_opportunities(processed(changed), self.repository, now=self.second_time)
        stored = self.repository.get(first.new_jobs[0].internal_id)
        assert stored is not None
        self.assertEqual(second.updated, 1)
        self.assertEqual(stored.first_seen_at, self.first_time)
        self.assertEqual(stored.last_seen_at, self.second_time)
        self.assertEqual(stored.opportunity.last_checked, self.second_time)
        self.assertEqual(stored.opportunity.location, "Worldwide")

    def test_external_id_identifies_job_when_url_changes(self) -> None:
        sync_opportunities(processed(make_job()), self.repository)
        changed_url = make_job(job_url="https://example.com/new-url")
        result = sync_opportunities(processed(changed_url), self.repository)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.total_stored, 1)

    def test_normalized_url_has_identity_priority(self) -> None:
        sync_opportunities(processed(make_job(job_url="https://EXAMPLE.com/jobs/1/?utm=x")), self.repository)
        result = sync_opportunities(
            processed(make_job(external_id="different", job_url="https://example.com/jobs/1")),
            self.repository,
        )
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.total_stored, 1)

    def test_company_and_role_are_fallback_identity(self) -> None:
        first = make_job(external_id=None, company=" Example Inc ", role="Account  Executive")
        second = make_job(external_id=None, company="example inc", role="account executive", job_url="https://other.test/job")
        sync_opportunities(processed(first), self.repository)
        result = sync_opportunities(processed(second), self.repository)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.total_stored, 1)

    def test_round_trip_preserves_json_booleans_dates_salary_and_evaluation(self) -> None:
        job = make_job(
            remote=None, brazil_eligible=False, requirements=["Five years"],
            responsibilities=["Own pipeline"], preferred_qualifications=["SaaS"],
            tools_mentioned=["Salesforce"], industries_mentioned=["B2B SaaS"],
            salary_min=80_000, salary_max=120_000, salary_currency="USD",
            salary_period="year", salary_text="$80k-$120k", job_level="Senior",
        )
        result = sync_opportunities(processed(job), self.repository, now=self.first_time)
        stored = self.repository.get(result.new_jobs[0].internal_id)
        assert stored is not None
        self.assertIsNone(stored.opportunity.remote)
        self.assertIs(stored.opportunity.brazil_eligible, False)
        self.assertEqual(stored.opportunity.requirements, ["Five years"])
        self.assertEqual(stored.opportunity.tools_mentioned, ["Salesforce"])
        self.assertEqual(stored.opportunity.salary_min, 80_000)
        self.assertEqual(stored.opportunity.date_posted, date(2026, 8, 9))
        self.assertIsInstance(stored.retention_decision, RetentionDecision)
        self.assertIsInstance(stored.role_family, RoleFamily)
        self.assertIsInstance(stored.seniority, Seniority)
        self.assertTrue(stored.positive_reasons)
        self.assertEqual(stored.opportunity.why_match, stored.positive_reasons)
        self.assertEqual(stored.opportunity.potential_gaps, stored.potential_gaps)

    def test_new_job_starts_with_manual_crm_defaults(self) -> None:
        incoming = make_job(
            tracking=ApplicationTracking(
                application_status=ApplicationStatus.APPLIED,
                notes="Automatic input must not initialize manual CRM",
            )
        )
        result = sync_opportunities(processed(incoming), self.repository)
        stored = self.repository.get(result.new_jobs[0].internal_id)
        assert stored is not None
        self.assertEqual(
            stored.opportunity.tracking.application_status,
            ApplicationStatus.NOT_APPLIED,
        )
        self.assertIsNone(stored.opportunity.tracking.notes)

    def test_sync_never_infers_reopening(self) -> None:
        sync_opportunities(processed(make_job(still_open=False)), self.repository)
        result = sync_opportunities(processed(make_job(still_open=False)), self.repository)
        stored = self.repository.list_all()[0]
        self.assertEqual(result.existing, 1)
        self.assertIs(stored.opportunity.still_open, False)

    def test_automatic_sync_preserves_all_manual_crm_fields(self) -> None:
        first = sync_opportunities(processed(make_job()), self.repository)
        tracking = ApplicationTracking(
            application_status=ApplicationStatus.RECRUITER_SCREEN,
            applied_date=date(2026, 8, 11), recruiter_name="Ana",
            recruiter_email="ana@example.com", next_step="Interview",
            next_step_date=date(2026, 8, 20), notes="Keep this note",
        )
        internal_id = first.new_jobs[0].internal_id
        self.repository.update_tracking(internal_id, tracking)
        incoming = make_job(description="Changed", tracking=ApplicationTracking())
        result = sync_opportunities(processed(incoming), self.repository)
        stored = self.repository.get(internal_id)
        assert stored is not None
        self.assertEqual(result.updated, 1)
        self.assertEqual(stored.opportunity.tracking, tracking)

    def test_batch_counts_multiple_jobs(self) -> None:
        first = sync_opportunities(processed(make_job("1"), make_job("2"), make_job("3")), self.repository)
        second = sync_opportunities(
            processed(make_job("1"), make_job("2", salary_min=50_000), make_job("4")),
            self.repository,
        )
        self.assertEqual((first.received, first.new, first.total_stored), (3, 3, 3))
        self.assertEqual((second.received, second.new, second.existing, second.updated, second.errors), (3, 1, 1, 1, 0))
        self.assertEqual(second.total_stored, 4)

    def test_one_save_error_does_not_stop_batch(self) -> None:
        original = self.repository._sync_one

        def fail_one(item, now):
            if item.original_job.company == "Company bad":
                raise ValueError("simulated save failure")
            return original(item, now)

        self.repository._sync_one = fail_one  # type: ignore[method-assign]
        result = sync_opportunities(
            processed(make_job("bad"), make_job("good")), self.repository
        )
        self.assertEqual((result.received, result.new, result.errors, result.total_stored), (2, 1, 1, 1))
        self.assertIn("simulated", result.error_details[0].message)

    def test_file_database_can_use_temporary_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            with JobRepository(path) as repository:
                sync_opportunities(processed(make_job()), repository)
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
