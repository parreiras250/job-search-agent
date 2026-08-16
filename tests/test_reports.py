"""Relatórios executivos offline, snapshots e CLI de histórico."""

from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from daniel_job_agent import (
    ApplicationStatus, ApplicationTracking, DanielJobAgent, JobRepository,
    MultiSourceDiscovery, SourceResult, SourceStatus,
)
from daniel_job_agent.report_cli import format_history, main as report_main
from daniel_job_agent.reports import (
    ReportOpportunity, SourceReport, WeeklyReport, build_weekly_report,
    find_report_for_run, format_weekly_report, report_filename,
    save_weekly_report,
)
from daniel_job_agent.weekly_run import SUCCESS, run_weekly


class FakeSource:
    def __init__(self, result: SourceResult) -> None:
        self.result = result

    def fetch(self) -> SourceResult:
        return self.result


def success(records):
    return SourceResult(
        SourceStatus.SUCCESS if records else SourceStatus.NO_JOBS, records
    )


def failure(message="timeout"):
    return SourceResult(SourceStatus.CONNECTION_ERROR, [], message)


def jobicy(identifier: int, *, title="Account Executive"):
    return {
        "id": identifier, "url": f"https://example.test/jobicy/{identifier}",
        "jobTitle": title, "companyName": f"Company {identifier}",
        "jobGeo": "LATAM", "jobDescription": "Own the sales cycle.",
        "pubDate": "2026-08-17 08:00:00",
    }


def remotive(identifier: int, *, title="Revenue Enablement Specialist"):
    return {
        "id": identifier, "url": f"https://example.test/remotive/{identifier}",
        "title": title, "company_name": f"Remote Company {identifier}",
        "candidate_required_location": "LATAM", "description": "Enable sales.",
        "publication_date": "2026-08-17T08:00:00Z",
    }


class StepClock:
    def __init__(self):
        self.value = datetime(2026, 8, 17, 11, tzinfo=timezone.utc)

    def __call__(self):
        value = self.value
        self.value += timedelta(seconds=1)
        return value


def run_agent(repository, *, jobicy_result=None, remotive_result=None):
    discovery = MultiSourceDiscovery(
        jobicy_source=FakeSource(jobicy_result or success([jobicy(1)])),
        remotive_source=FakeSource(remotive_result or success([remotive(2)])),
        wwr_source=FakeSource(success([])),
    )
    return DanielJobAgent(repository, discovery=discovery, clock=StepClock()).run()


def record_history(repository, result, *, status="SUCCESS", sheets=True):
    run_id = repository.record_agent_run(
        started_at=result.started_at, finished_at=result.finished_at, status=status,
        sources_succeeded=result.sources_succeeded,
        sources_failed=result.sources_failed, jobs_received=result.jobs_received,
        new_count=result.new, existing_count=result.existing,
        updated_count=result.updated,
        lifecycle_misses=result.lifecycle.misses_recorded,
        possibly_closed=result.lifecycle.possibly_closed,
        newly_closed=result.lifecycle.newly_closed, reopened=result.lifecycle.reopened,
        sheets_sync_success=sheets, error_summary=None,
    )
    return repository.get_agent_run(run_id)


def opportunity(index=1, decision="KEEP", score=90):
    return ReportOpportunity(
        f"Company {index}", f"Role {index}", score, decision,
        "CLOSING_SALES", "SENIOR_IC", "LATAM", "Jobicy",
        f"https://example.test/{index}",
    )


def simple_report(**changes):
    values = dict(
        run_id=7,
        started_at=datetime(2026, 8, 17, 11, tzinfo=timezone.utc),
        finished_at=datetime(2026, 8, 17, 11, 0, 8, tzinfo=timezone.utc),
        status="SUCCESS", sources=[SourceReport("Jobicy", True, 4, 4, 0, 0)],
        jobs_received=4, unique_opportunities=4, keep=2, review=1, reject=1,
        new=2, updated=1, sheets_success=True,
        crm_status_counts={status: 0 for status in ApplicationStatus},
    )
    values.update(changes)
    return WeeklyReport(**values)


class WeeklyReportModelTests(unittest.TestCase):
    def test_successful_report_has_all_sections_and_crm_snapshot(self):
        with JobRepository(":memory:") as repository:
            result = run_agent(repository)
            first_id = result.persistence.new_jobs[0].internal_id
            repository.update_tracking(
                first_id, ApplicationTracking(application_status=ApplicationStatus.APPLIED)
            )
            report = build_weekly_report(repository, record_history(repository, result), result, sheets_rows_written=2)
        markdown = format_weekly_report(report)
        for heading in ("Executive summary", "Source health", "Discovery", "Persistence", "Best new opportunities", "Important updates", "Lifecycle changes", "Google Sheets", "CRM snapshot"):
            self.assertIn(heading, markdown)
        self.assertIn("APPLIED: 1", markdown)
        self.assertIn("Rows written: 2", markdown)

    def test_no_new_jobs_is_clear_and_not_an_error(self):
        report = simple_report(new=0, best_new=[])
        self.assertIn("No new KEEP or REVIEW opportunities", format_weekly_report(report))

    def test_best_new_orders_keep_before_review_excludes_reject_and_caps_ten(self):
        jobs = [opportunity(99, "REVIEW", 100), opportunity(98, "REJECT", 100)]
        jobs += [opportunity(index, "KEEP", 90 - index) for index in range(12)]
        allowed = sorted(
            (job for job in jobs if job.decision != "REJECT"),
            key=lambda job: ({"KEEP": 0, "REVIEW": 1}[job.decision], -job.score),
        )[:10]
        report = simple_report(best_new=allowed)
        self.assertEqual(len(report.best_new), 10)
        self.assertTrue(all(job.decision == "KEEP" for job in report.best_new))
        self.assertNotIn("REJECT", "\n".join(job.decision for job in report.best_new))

    def test_builder_orders_real_keep_before_review_and_excludes_reject(self):
        records = [jobicy(index) for index in range(1, 13)]
        records.append(jobicy(20, title="Software Engineer"))
        with JobRepository(":memory:") as repository:
            result = run_agent(repository, jobicy_result=success(records))
            report = build_weekly_report(repository, record_history(repository, result), result)
        self.assertEqual(len(report.best_new), 10)
        self.assertEqual(report.best_new[0].decision, "KEEP")
        self.assertTrue(all(item.decision != "REJECT" for item in report.best_new))

    def test_builder_lists_a_real_updated_opportunity(self):
        with JobRepository(":memory:") as repository:
            run_agent(repository, jobicy_result=success([jobicy(1)]))
            changed = jobicy(1)
            changed["jobDescription"] = "Updated commercial responsibilities."
            result = run_agent(repository, jobicy_result=success([changed]))
            report = build_weekly_report(repository, record_history(repository, result), result)
        self.assertEqual(report.updated, 1)
        self.assertEqual(len(report.important_updates), 1)
        self.assertEqual(report.important_updates[0].company, "Company 1")

    def test_updated_and_each_lifecycle_event_are_rendered(self):
        item = opportunity()
        markdown = format_weekly_report(simple_report(
            important_updates=[item], possibly_closed_jobs=[item],
            newly_closed_jobs=[item], reopened_jobs=[item],
        ))
        self.assertIn("## Important updates", markdown)
        self.assertIn("### Possibly closed", markdown)
        self.assertIn("### Closed", markdown)
        self.assertIn("### Reopened", markdown)

    def test_partial_and_total_failure_are_human_readable(self):
        partial = simple_report(
            status="PARTIAL_FAILURE",
            sources=[SourceReport("Jobicy", True, 2, 2, 0, 0), SourceReport("Remotive", False, 0, 0, 0, 0, "Source request failed")],
            failure_summary="Remotive failed; results may be incomplete.",
        )
        self.assertIn("Remotive failed; results may be incomplete", format_weekly_report(partial))
        total = simple_report(status="FAILURE", sources=[], failure_summary="The agent failed before a complete result was available.")
        self.assertIn("Source details were not available", format_weekly_report(total))

    def test_sheets_success_and_failure_are_explicit(self):
        self.assertIn("Sync: success", format_weekly_report(simple_report(sheets_success=True)))
        self.assertIn("Sync: failed", format_weekly_report(simple_report(sheets_success=False)))

    def test_report_does_not_include_runtime_error_or_secret_values(self):
        report = simple_report(
            status="PARTIAL_FAILURE",
            failure_summary=(
                "Google Sheets synchronization failed; "
                "access_token=access-token-123 refresh_token=refresh-token-456 "
                "client_secret=client-secret-789"
            ),
        )
        markdown = format_weekly_report(report)
        for secret in ("access-token-123", "refresh-token-456", "client-secret-789"):
            self.assertNotIn(secret, markdown)


class ReportStorageAndCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "data").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def capture_cli(self, args):
        output = StringIO()
        with redirect_stdout(output):
            code = report_main(["--project-dir", str(self.root), *args])
        return code, output.getvalue()

    def test_timestamped_history_and_latest_are_saved(self):
        report = simple_report()
        historical = save_weekly_report(report, self.root / "reports")
        self.assertEqual(historical.name, "2026-08-17_110000_7.md")
        self.assertEqual(report_filename(report), historical.name)
        self.assertTrue((self.root / "reports/latest.md").is_file())
        self.assertEqual(find_report_for_run(self.root / "reports", 7), historical)

    def test_latest_and_show_cli_print_markdown(self):
        save_weekly_report(simple_report(), self.root / "reports")
        self.assertIn("Weekly Report", self.capture_cli(["latest"])[1])
        self.assertIn("Run ID: 7", self.capture_cli(["show", "7"])[1])

    def test_no_reports_behavior_is_clear(self):
        code, output = self.capture_cli(["latest"])
        self.assertEqual(code, 1)
        self.assertIn("No weekly report", output)

    def test_history_uses_agent_runs_not_markdown(self):
        path = self.root / "data/job_agent.db"
        with JobRepository(path) as repository:
            result = run_agent(repository)
            record_history(repository, result)
            text = format_history(repository, limit=10)
        self.assertIn("Run 1", text)
        self.assertIn("New: 2", text)
        self.assertFalse((self.root / "reports").exists())
        self.assertIn("Run 1", self.capture_cli(["history", "--limit", "10"])[1])


class WeeklyReportIntegrationTests(unittest.TestCase):
    def test_weekly_run_creates_report_inside_existing_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            from daniel_job_agent.scheduler import SchedulerConfig
            config = SchedulerConfig(
                project_dir=root, python_path=root / "python",
                database_path=root / "data/jobs.db", logs_dir=root / "logs",
                plist_path=root / "agent.plist", lock_path=root / "data/run.lock",
            )
            discovery = MultiSourceDiscovery(
                jobicy_source=FakeSource(success([jobicy(1)])),
                remotive_source=FakeSource(success([remotive(2)])),
                wwr_source=FakeSource(success([])),
            )
            outcome = run_weekly(
                config,
                agent_factory=lambda repository: DanielJobAgent(repository, discovery=discovery, clock=StepClock()),
                sheets_sync=lambda repository, cfg: (True, None, 2),
                clock=StepClock(),
            )
            self.assertEqual(outcome.exit_code, SUCCESS)
            self.assertTrue(outcome.report_success)
            self.assertTrue(outcome.report_path.is_file())
            self.assertTrue((root / "reports/latest.md").is_file())


if __name__ == "__main__":
    unittest.main()
