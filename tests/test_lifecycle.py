"""Testes offline da reconciliação conservadora do lifecycle das vagas."""

import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from daniel_job_agent import (
    ApplicationStatus,
    ApplicationTracking,
    JobLifecycleStatus,
    JobOpportunity,
    JobRepository,
    LifecyclePolicy,
    LocalCRM,
    VerificationStatus,
    create_daniel_profile,
    process_opportunities,
    reconcile_lifecycle,
    sync_opportunities,
)
from daniel_job_agent.repository import SCHEMA_VERSION


def make_job(identifier: str, **changes: object) -> JobOpportunity:
    values: dict[str, object] = {
        "company": f"Company {identifier}",
        "role": "Account Executive",
        "job_url": f"https://example.test/{identifier}",
        "source": "Jobicy public Remote Jobs API",
        "source_id": "jobicy",
        "source_family": "jobicy",
        "source_instance": "jobicy:global",
        "location": "LATAM",
        "remote": True,
        "brazil_eligible": True,
        "external_id": identifier,
        "date_found": date(2026, 8, 15),
    }
    values.update(changes)
    return JobOpportunity(**values)  # type: ignore[arg-type]


class LifecycleStateMachineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = JobRepository(":memory:")
        self.profile = create_daniel_profile()
        self.start = datetime(2026, 8, 15, 12, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self.repository.close()

    def sync_jobs(self, jobs: list[JobOpportunity], now: datetime):
        return sync_opportunities(
            process_opportunities(jobs, self.profile), self.repository, now=now
        )

    def test_run_sequence_open_misses_closed_and_reopened(self) -> None:
        first = self.sync_jobs(
            [make_job("A"), make_job("B"), make_job("C")], self.start
        )
        ids = {
            item.opportunity.external_id: item.internal_id for item in first.new_jobs
        }
        run1 = reconcile_lifecycle(
            self.repository,
            seen_internal_ids=set(ids.values()),
            successful_sources={"Jobicy"},
            now=self.start,
        )
        self.assertEqual(run1.open_seen, 3)
        self.assertTrue(
            all(
                item.opportunity.lifecycle_status is JobLifecycleStatus.OPEN
                for item in self.repository.list_all()
            )
        )

        for run, expected_status, expected_open in (
            (2, JobLifecycleStatus.OPEN, True),
            (3, JobLifecycleStatus.POSSIBLY_CLOSED, None),
            (4, JobLifecycleStatus.CLOSED, False),
        ):
            result = reconcile_lifecycle(
                self.repository,
                seen_internal_ids={ids["A"], ids["B"]},
                successful_sources={"Jobicy"},
                now=self.start + timedelta(days=run - 1),
            )
            c = self.repository.get(ids["C"])
            assert c is not None
            self.assertEqual(c.opportunity.consecutive_misses, run - 1)
            self.assertEqual(c.opportunity.lifecycle_status, expected_status)
            self.assertIs(c.opportunity.still_open, expected_open)
            self.assertEqual(result.misses_recorded, 1)
            if run == 3:
                self.assertEqual(result.possibly_closed_ids, [ids["C"]])
            if run == 4:
                self.assertEqual(result.newly_closed_ids, [ids["C"]])

        closed = self.repository.get(ids["C"])
        assert closed is not None
        self.assertIsNotNone(closed.opportunity.closed_at)
        original_first_seen = closed.first_seen_at

        fifth_sync = self.sync_jobs(
            [make_job("C")], self.start + timedelta(days=4)
        )
        c_seen_id = (fifth_sync.existing_jobs + fifth_sync.updated_jobs)[0].internal_id
        run5 = reconcile_lifecycle(
            self.repository,
            seen_internal_ids={c_seen_id},
            successful_sources={"Jobicy"},
            now=self.start + timedelta(days=4),
        )
        reopened = self.repository.get(ids["C"])
        assert reopened is not None
        self.assertEqual(run5.reopened, 1)
        self.assertEqual(run5.reopened_ids, [ids["C"]])
        self.assertEqual(reopened.opportunity.lifecycle_status, JobLifecycleStatus.OPEN)
        self.assertEqual(reopened.opportunity.consecutive_misses, 0)
        self.assertIs(reopened.opportunity.still_open, True)
        self.assertIsNotNone(reopened.opportunity.reopened_at)
        self.assertIsNone(reopened.opportunity.closed_at)
        self.assertEqual(reopened.first_seen_at, original_first_seen)

    def test_failed_source_does_not_count_but_successful_zero_results_does(self) -> None:
        first = self.sync_jobs([make_job("A")], self.start)
        internal_id = first.new_jobs[0].internal_id
        failed = reconcile_lifecycle(
            self.repository,
            seen_internal_ids=set(),
            successful_sources={"Remotive"},
            now=self.start + timedelta(days=1),
        )
        self.assertEqual(failed.misses_recorded, 0)
        self.assertEqual(
            self.repository.get(internal_id).opportunity.consecutive_misses, 0  # type: ignore[union-attr]
        )
        zero_results = reconcile_lifecycle(
            self.repository,
            seen_internal_ids=set(),
            successful_sources={"Jobicy"},
            now=self.start + timedelta(days=2),
        )
        self.assertEqual(zero_results.misses_recorded, 1)
        self.assertEqual(
            self.repository.get(internal_id).opportunity.consecutive_misses, 1  # type: ignore[union-attr]
        )

    def test_other_unexecuted_sources_are_never_changed(self) -> None:
        greenhouse = make_job(
            "G",
            source="Greenhouse: Example",
            source_id="greenhouse-example",
            source_family="greenhouse",
            source_instance="greenhouse:example",
        )
        first = self.sync_jobs([greenhouse], self.start)
        internal_id = first.new_jobs[0].internal_id
        reconcile_lifecycle(
            self.repository,
            seen_internal_ids=set(),
            successful_sources={"Jobicy", "Remotive"},
            now=self.start + timedelta(days=1),
        )
        stored = self.repository.get(internal_id)
        assert stored is not None
        self.assertEqual(stored.opportunity.consecutive_misses, 0)
        self.assertEqual(stored.opportunity.lifecycle_status, JobLifecycleStatus.OPEN)

    def test_keep_review_reject_all_receive_lifecycle(self) -> None:
        jobs = [
            make_job("keep"),
            make_job("review", role="Revenue Enablement Specialist", location="Remote"),
            make_job("reject", role="Software Engineer"),
        ]
        first = self.sync_jobs(jobs, self.start)
        reconcile_lifecycle(
            self.repository,
            seen_internal_ids={item.internal_id for item in first.new_jobs},
            successful_sources={"Jobicy"},
            now=self.start,
        )
        result = reconcile_lifecycle(
            self.repository,
            seen_internal_ids=set(),
            successful_sources={"Jobicy"},
            policy=LifecyclePolicy(possibly_closed_after=1, closed_after=2),
            now=self.start + timedelta(days=1),
        )
        self.assertEqual((result.misses_recorded, result.possibly_closed), (3, 3))

    def test_crm_manual_fields_survive_closure_and_reopening(self) -> None:
        first = self.sync_jobs([make_job("A")], self.start)
        internal_id = first.new_jobs[0].internal_id
        tracking = ApplicationTracking(
            application_status=ApplicationStatus.INTERVIEW,
            notes="Do not overwrite",
            recruiter_name="Ana",
        )
        self.repository.update_tracking(internal_id, tracking)
        for day in (1, 2, 3):
            reconcile_lifecycle(
                self.repository,
                seen_internal_ids=set(),
                successful_sources={"Jobicy"},
                now=self.start + timedelta(days=day),
            )
        reconcile_lifecycle(
            self.repository,
            seen_internal_ids={internal_id},
            successful_sources={"Jobicy"},
            now=self.start + timedelta(days=4),
        )
        self.assertEqual(
            self.repository.get(internal_id).opportunity.tracking, tracking  # type: ignore[union-attr]
        )

    def test_explicit_verification_can_close_without_http_inference(self) -> None:
        first = self.sync_jobs([make_job("A")], self.start)
        internal_id = first.new_jobs[0].internal_id
        result = reconcile_lifecycle(
            self.repository,
            seen_internal_ids=set(),
            successful_sources=set(),
            verifications={internal_id: VerificationStatus.CLOSED},
            now=self.start + timedelta(days=1),
        )
        stored = self.repository.get(internal_id)
        assert stored is not None
        self.assertEqual(result.newly_closed, 1)
        self.assertEqual(stored.opportunity.lifecycle_status, JobLifecycleStatus.CLOSED)
        self.assertIsNotNone(stored.opportunity.last_verified_at)

    def test_crm_filter_supports_lifecycle_status(self) -> None:
        first = self.sync_jobs([make_job("A"), make_job("B")], self.start)
        ids = {item.opportunity.external_id: item.internal_id for item in first.new_jobs}
        reconcile_lifecycle(
            self.repository,
            seen_internal_ids={ids["A"]},
            successful_sources={"Jobicy"},
            policy=LifecyclePolicy(possibly_closed_after=1, closed_after=2),
            now=self.start + timedelta(days=1),
        )
        crm = LocalCRM(self.repository)
        self.assertEqual(len(crm.list_records(lifecycle_status="OPEN")), 1)
        self.assertEqual(
            len(crm.list_records(lifecycle_status="POSSIBLY_CLOSED")), 1
        )


class LifecycleSchemaMigrationTests(unittest.TestCase):
    def test_old_database_is_migrated_idempotently_without_losing_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.db"
            connection = sqlite3.connect(path)
            connection.execute(
                """CREATE TABLE opportunities (
                    id INTEGER PRIMARY KEY,
                    job_url_normalized TEXT,
                    source TEXT,
                    external_id TEXT,
                    company_normalized TEXT,
                    role_normalized TEXT,
                    still_open INTEGER,
                    closed_at TEXT
                )"""
            )
            connection.execute(
                """INSERT INTO opportunities
                   (id, job_url_normalized, source, external_id,
                    company_normalized, role_normalized, still_open)
                   VALUES (1, 'https://example.test/1', 'Jobicy', '1',
                           'company', 'role', 1)"""
            )
            connection.commit()
            connection.close()

            repository = JobRepository(path)
            columns = {
                row[1]
                for row in repository.connection.execute(
                    "PRAGMA table_info(opportunities)"
                )
            }
            version = repository.connection.execute("PRAGMA user_version").fetchone()[0]
            self.assertEqual(repository.count(), 1)
            self.assertIn("lifecycle_status", columns)
            self.assertIn("consecutive_misses", columns)
            self.assertEqual(version, SCHEMA_VERSION)
            repository.close()

            reopened = JobRepository(path)
            self.assertEqual(reopened.count(), 1)
            self.assertEqual(
                reopened.connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )
            reopened.close()

            future = sqlite3.connect(path)
            future.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            future.close()
            compatible = JobRepository(path)
            self.assertEqual(
                compatible.connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )
            compatible.close()


if __name__ == "__main__":
    unittest.main()
