"""Demonstração offline do Markdown executivo, sem discovery ou Sheets."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile

from .models import ApplicationStatus
from .reports import ReportOpportunity, SourceReport, WeeklyReport, save_weekly_report


def main() -> None:
    started = datetime(2026, 8, 17, 11, tzinfo=timezone.utc)
    opportunity = ReportOpportunity(
        company="Example Analytics", role="Enterprise Account Executive",
        score=92, decision="KEEP", role_family="CLOSING_SALES",
        seniority="SENIOR_IC", location="LATAM", source="Jobicy",
        job_url="https://example.test/jobs/weekly-demo",
    )
    report = WeeklyReport(
        run_id=42, started_at=started, finished_at=started + timedelta(seconds=8),
        status="PARTIAL_FAILURE",
        sources=[
            SourceReport("Jobicy", True, 20, 20, 0, 0),
            SourceReport("Remotive", False, 0, 0, 0, 0, "Source request failed"),
        ],
        jobs_received=20, unique_opportunities=18, duplicates=2,
        keep=3, review=12, reject=3, new=2, existing=15, updated=1,
        total_stored=40, seen_open=17, misses_recorded=1,
        possibly_closed=1, sheets_success=True, sheets_rows_written=40,
        crm_status_counts={status: 0 for status in ApplicationStatus},
        best_new=[opportunity], possibly_closed_jobs=[opportunity],
        failure_summary="Remotive failed; results may be incomplete.",
    )
    with tempfile.TemporaryDirectory() as directory:
        path = save_weekly_report(report, Path(directory))
        print(f"Offline report created: {path.name}")
        print("\n".join(path.read_text(encoding="utf-8").splitlines()[:18]))


if __name__ == "__main__":
    main()
