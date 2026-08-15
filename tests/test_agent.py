"""Testes end-to-end offline do orquestrador principal."""

import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from daniel_job_agent import (
    ApplicationStatus,
    ApplicationTracking,
    DanielJobAgent,
    JobRepository,
    MultiSourceDiscovery,
    RetentionDecision,
    SourceResult,
    SourceStatus,
    create_broad_discovery,
    create_default_search_strategy,
)
from daniel_job_agent.reporting import format_agent_run


class FakeSource:
    def __init__(self, result: SourceResult) -> None:
        self.result = result
        self.calls = 0

    def fetch(self) -> SourceResult:
        self.calls += 1
        return self.result


class StepClock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def __call__(self) -> datetime:
        value = self.current
        self.current += timedelta(seconds=1)
        return value


def success(records: list[dict[str, object]]) -> SourceResult:
    return SourceResult(
        status=SourceStatus.SUCCESS if records else SourceStatus.NO_JOBS,
        records=records,
    )


def failure(message: str) -> SourceResult:
    return SourceResult(
        status=SourceStatus.CONNECTION_ERROR,
        records=[],
        message=message,
    )


def jobicy_record(identifier: int, **changes: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": identifier,
        "url": f"https://jobicy.test/jobs/{identifier}",
        "jobTitle": "Account Executive",
        "companyName": f"Jobicy Company {identifier}",
        "jobGeo": "LATAM",
        "jobDescription": "Own the sales cycle.",
        "pubDate": "2026-08-15 10:00:00",
    }
    record.update(changes)
    return record


def remotive_record(identifier: int, **changes: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": identifier,
        "url": f"https://remotive.test/jobs/{identifier}",
        "title": "Revenue Enablement Specialist",
        "company_name": f"Remotive Company {identifier}",
        "candidate_required_location": "Remote",
        "description": "Support commercial teams.",
        "publication_date": "2026-08-15T10:00:00Z",
    }
    record.update(changes)
    return record


class AgentEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = JobRepository(":memory:")
        self.jobicy = FakeSource(
            success(
                [
                    jobicy_record(1),
                    jobicy_record(
                        2,
                        jobTitle="Software Engineer",
                        companyName="Rejected Company",
                    ),
                ]
            )
        )
        self.remotive = FakeSource(success([remotive_record(3)]))
        self.discovery = MultiSourceDiscovery(
            jobicy_source=self.jobicy,
            remotive_source=self.remotive,
        )

    def tearDown(self) -> None:
        self.repository.close()

    def make_agent(self, *, clock=None) -> DanielJobAgent:
        return DanielJobAgent(
            self.repository,
            discovery=self.discovery,
            clock=clock or StepClock(datetime(2026, 8, 15, tzinfo=timezone.utc)),
        )

    def test_complete_run_persists_keep_review_and_reject_as_new(self) -> None:
        result = self.make_agent().run()
        decisions = {item.retention_decision for item in result.discovery.ranking}
        self.assertEqual(result.sources_succeeded, ["Jobicy", "Remotive"])
        self.assertEqual((result.jobs_received, result.jobs_converted), (3, 3))
        self.assertEqual((result.unique_opportunities, result.discovery_duplicates), (3, 0))
        self.assertEqual(decisions, set(RetentionDecision))
        self.assertEqual((result.keep, result.review, result.reject), (1, 1, 1))
        self.assertEqual((result.new, result.existing, result.updated), (3, 0, 0))
        self.assertEqual(result.total_stored, 3)
        self.assertEqual(result.lifecycle.open_seen, 3)
        self.assertEqual(result.lifecycle.misses_recorded, 0)

    def test_second_run_is_existing_and_third_changed_run_is_updated(self) -> None:
        first = self.make_agent().run()
        second = self.make_agent().run()
        self.remotive.result = success(
            [remotive_record(3, description="Updated automatic description")]
        )
        third = self.make_agent().run()
        self.assertEqual((first.new, first.existing), (3, 0))
        self.assertEqual((second.new, second.existing, second.updated), (0, 3, 0))
        self.assertEqual((third.new, third.existing, third.updated), (0, 2, 1))
        self.assertEqual(third.total_stored, 3)

    def test_automatic_run_preserves_manual_crm(self) -> None:
        first = self.make_agent().run()
        job_id = next(
            item.internal_id
            for item in first.persistence.new_jobs
            if item.opportunity.external_id == "1"
        )
        tracking = ApplicationTracking(
            application_status=ApplicationStatus.APPLIED,
            applied_date=date(2026, 8, 15),
            recruiter_name="Ana",
            recruiter_email="ana@example.com",
            next_step="Interview",
            next_step_date=date(2026, 8, 20),
            notes="Manual note",
        )
        self.repository.update_tracking(job_id, tracking)
        self.jobicy.result = success(
            [
                jobicy_record(1, jobDescription="Changed"),
                jobicy_record(2, jobTitle="Software Engineer", companyName="Rejected Company"),
            ]
        )
        self.make_agent().run()
        stored = self.repository.get(job_id)
        assert stored is not None
        self.assertEqual(stored.opportunity.tracking, tracking)

    def test_top_new_prioritizes_keep_then_review_and_excludes_reject(self) -> None:
        result = self.make_agent().run()
        self.assertEqual(
            [item.retention_decision for item in result.top_new_opportunities],
            [RetentionDecision.KEEP, RetentionDecision.REVIEW],
        )
        report = format_agent_run(result)
        self.assertIn("Account Executive — Jobicy Company 1", report)
        self.assertIn("Revenue Enablement Specialist — Remotive Company 3", report)
        self.assertNotIn("Software Engineer — Rejected Company", report)

    def test_timestamps_duration_and_database_path_are_reported(self) -> None:
        start = datetime(2026, 8, 15, 12, tzinfo=timezone.utc)
        result = self.make_agent(clock=StepClock(start)).run()
        self.assertEqual(result.started_at, start)
        self.assertEqual(result.finished_at, start + timedelta(seconds=2))
        self.assertEqual(result.duration_seconds, 2)
        self.assertEqual(result.database_path, ":memory:")
        self.assertTrue(all(item.last_seen_at == start + timedelta(seconds=1) for item in self.repository.list_all()))

    def test_no_missing_job_is_automatically_closed(self) -> None:
        first = self.make_agent().run()
        stored_id = first.persistence.new_jobs[0].internal_id
        self.jobicy.result = success([])
        self.remotive.result = success([])
        self.make_agent().run()
        stored = self.repository.get(stored_id)
        assert stored is not None
        self.assertIs(stored.opportunity.still_open, True)
        self.assertEqual(self.repository.count(), 3)

    def test_custom_database_path_uses_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent-test.db"
            with JobRepository(path) as repository:
                result = DanielJobAgent(repository, discovery=self.discovery).run()
            self.assertEqual(result.database_path, str(path))
            self.assertTrue(path.exists())


class AgentFailureIsolationTests(unittest.TestCase):
    def run_with(self, jobicy: SourceResult, remotive: SourceResult, repository: JobRepository):
        discovery = MultiSourceDiscovery(
            jobicy_source=FakeSource(jobicy),
            remotive_source=FakeSource(remotive),
        )
        return DanielJobAgent(repository, discovery=discovery).run()

    def test_jobicy_failure_still_persists_remotive(self) -> None:
        with JobRepository(":memory:") as repository:
            result = self.run_with(failure("Jobicy unavailable"), success([remotive_record(1)]), repository)
            self.assertEqual(result.sources_failed, ["Jobicy"])
            self.assertEqual((result.new, result.total_stored), (1, 1))

    def test_remotive_failure_still_persists_jobicy(self) -> None:
        with JobRepository(":memory:") as repository:
            result = self.run_with(success([jobicy_record(1)]), failure("Remotive unavailable"), repository)
            self.assertEqual(result.sources_failed, ["Remotive"])
            self.assertEqual((result.new, result.total_stored), (1, 1))

    def test_both_fail_without_changing_existing_database(self) -> None:
        with JobRepository(":memory:") as repository:
            self.run_with(success([jobicy_record(1)]), success([]), repository)
            before = repository.list_all()[0]
            result = self.run_with(failure("one"), failure("two"), repository)
            after = repository.list_all()[0]
            self.assertEqual(result.sources_failed, ["Jobicy", "Remotive"])
            self.assertEqual((result.jobs_received, result.new, result.total_stored), (0, 0, 1))
            self.assertEqual(after.last_seen_at, before.last_seen_at)
            self.assertIs(after.opportunity.still_open, True)
            self.assertEqual(result.lifecycle.misses_recorded, 0)


class BroadStrategyIntegrationTests(unittest.TestCase):
    def test_default_discovery_reuses_calibrated_broad_strategy(self) -> None:
        strategy = create_default_search_strategy()
        discovery = create_broad_discovery(strategy)
        jobicy = strategy.jobicy_queries[0]
        remotive = strategy.remotive_queries[0]
        self.assertEqual(discovery.jobicy_config.geo, jobicy.geo)
        self.assertEqual(discovery.jobicy_config.industry, jobicy.industry)
        self.assertEqual(discovery.jobicy_config.count, jobicy.count)
        self.assertEqual(discovery.remotive_config.category, remotive.category)


if __name__ == "__main__":
    unittest.main()
