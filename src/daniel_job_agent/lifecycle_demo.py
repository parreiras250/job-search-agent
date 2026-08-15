"""Demonstra offline misses conservadores, fechamento e reaparecimento."""

from datetime import datetime, timedelta, timezone
from tempfile import TemporaryDirectory

from .lifecycle import reconcile_lifecycle
from .models import JobOpportunity
from .pipeline import process_opportunities
from .profiles import create_daniel_profile
from .repository import JobRepository, sync_opportunities


def _job(identifier: str) -> JobOpportunity:
    return JobOpportunity(
        company=f"Demo {identifier}",
        role="Account Executive",
        job_url=f"https://demo.invalid/{identifier}",
        source="Jobicy public Remote Jobs API",
        location="LATAM",
        remote=True,
        brazil_eligible=True,
        external_id=identifier,
    )


def _print_state(run: int, repository: JobRepository) -> None:
    print(f"Run {run}")
    for stored in repository.list_all():
        job = stored.opportunity
        suffix = " REOPENED" if job.reopened_at and run == 5 else ""
        print(
            f"{job.company}: {job.lifecycle_status.value} "
            f"misses={job.consecutive_misses}{suffix}"
        )
    print()


def main() -> None:
    profile = create_daniel_profile()
    start = datetime(2026, 8, 15, 12, tzinfo=timezone.utc)
    with TemporaryDirectory() as directory:
        with JobRepository(f"{directory}/lifecycle-demo.db") as repository:
            first = sync_opportunities(
                process_opportunities([_job("A"), _job("B")], profile),
                repository,
                now=start,
            )
            seen = {item.internal_id for item in first.new_jobs}
            reconcile_lifecycle(
                repository,
                seen_internal_ids=seen,
                successful_sources={"Jobicy"},
                now=start,
            )
            _print_state(1, repository)

            a_id = next(
                item.internal_id
                for item in first.new_jobs
                if item.opportunity.external_id == "A"
            )
            for run in (2, 3, 4):
                reconcile_lifecycle(
                    repository,
                    seen_internal_ids={a_id},
                    successful_sources={"Jobicy"},
                    now=start + timedelta(days=run - 1),
                )
                _print_state(run, repository)

            fifth = sync_opportunities(
                process_opportunities([_job("B")], profile),
                repository,
                now=start + timedelta(days=4),
            )
            b_id = (
                fifth.existing_jobs + fifth.updated_jobs
            )[0].internal_id
            reconcile_lifecycle(
                repository,
                seen_internal_ids={b_id},
                successful_sources={"Jobicy"},
                now=start + timedelta(days=4),
            )
            _print_state(5, repository)


if __name__ == "__main__":
    main()
