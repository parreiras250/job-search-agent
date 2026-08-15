"""Demonstra duas sincronizações SQLite sem consultar a internet."""

from datetime import date
from tempfile import TemporaryDirectory

from .models import ApplicationStatus, ApplicationTracking, JobOpportunity
from .pipeline import process_opportunities
from .profiles import create_daniel_profile
from .repository import JobRepository, SyncResult, sync_opportunities


def _job(identifier: str, **changes: object) -> JobOpportunity:
    values: dict[str, object] = {
        "company": f"Demo Company {identifier}",
        "role": "Account Executive",
        "job_url": f"https://demo.invalid/jobs/{identifier}",
        "source": "Offline persistence demo",
        "location": "Remote - LATAM",
        "remote": True,
        "brazil_eligible": True,
        "external_id": identifier,
    }
    values.update(changes)
    return JobOpportunity(**values)  # type: ignore[arg-type]


def _print_run(number: int, result: SyncResult) -> None:
    print(f"Run {number}:")
    print(f"NEW: {result.new}")
    print(f"EXISTING: {result.existing}")
    print(f"UPDATED: {result.updated}")
    print(f"Errors: {result.errors}")
    print(f"Total stored: {result.total_stored}")


def main() -> None:
    profile = create_daniel_profile()
    first_jobs = [_job("1"), _job("2"), _job("3")]
    with TemporaryDirectory() as temporary_directory:
        database_path = f"{temporary_directory}/persistence_demo.db"
        with JobRepository(database_path) as repository:
            first = sync_opportunities(process_opportunities(first_jobs, profile), repository)
            _print_run(1, first)

            first_id = first.new_jobs[0].internal_id
            repository.update_tracking(
                first_id,
                ApplicationTracking(
                    application_status=ApplicationStatus.APPLIED,
                    applied_date=date(2026, 8, 15),
                    recruiter_name="Demo Recruiter",
                    notes="Manual note preserved between syncs.",
                ),
            )
            second_jobs = [
                _job("1"),
                _job("2", salary_min=75_000, salary_currency="USD"),
                _job("4"),
            ]
            second = sync_opportunities(process_opportunities(second_jobs, profile), repository)
            print()
            _print_run(2, second)
            stored = repository.get(first_id)
            assert stored is not None
            print()
            print("Manual CRM preserved:")
            print(f"Application status: {stored.opportunity.tracking.application_status.value}")
            print(f"Recruiter: {stored.opportunity.tracking.recruiter_name}")
            print(f"Notes: {stored.opportunity.tracking.notes}")


if __name__ == "__main__":
    main()
