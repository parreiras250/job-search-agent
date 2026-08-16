"""Demonstração offline de uma opportunity com múltiplas observações."""

from datetime import datetime, timedelta, timezone

from .lifecycle import reconcile_lifecycle
from .models import JobOpportunity
from .pipeline import process_opportunities
from .profiles import create_daniel_profile
from .repository import JobRepository, sync_opportunities


START = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
IDENTITIES = {
    ("jobicy", "jobicy:global"),
    ("weworkremotely", "weworkremotely:sales-marketing"),
}


def opportunity(source_id: str) -> JobOpportunity:
    wwr = source_id == "weworkremotely"
    return JobOpportunity(
        company="Example SaaS",
        role="Account Executive",
        job_url=(
            "https://weworkremotely.com/remote-jobs/example-ae"
            if wwr else "https://jobicy.example/jobs/example-ae"
        ),
        source="We Work Remotely" if wwr else "Jobicy public Remote Jobs API",
        location="LATAM", remote=True, brazil_eligible=True,
        external_id=f"{source_id}-example-ae", source_id=source_id,
        source_family=source_id,
        source_instance=(
            "weworkremotely:sales-marketing" if wwr else "jobicy:global"
        ),
        source_type="FEED" if wwr else "GLOBAL_BOARD",
        lifecycle_authority="OBSERVATIONAL",
    )


def sync(repository: JobRepository, jobs: list[JobOpportunity], now: datetime):
    return sync_opportunities(
        process_opportunities(jobs, create_daniel_profile()), repository, now=now
    )


def main() -> None:
    with JobRepository(":memory:") as repository:
        first = sync(repository, [opportunity("jobicy")], START)
        internal_id = first.new_jobs[0].internal_id
        print("Run 1: 1 opportunity, 1 Jobicy observation")

        second = sync(
            repository,
            [opportunity("jobicy"), opportunity("weworkremotely")],
            START + timedelta(days=1),
        )
        print(
            "Run 2: "
            f"{repository.count()} opportunity, "
            f"{len(repository.get_observations(internal_id))} observations "
            f"({second.cross_source_observations_added} cross-source added)"
        )

        third = sync(
            repository, [opportunity("weworkremotely")], START + timedelta(days=2)
        )
        reconcile_lifecycle(
            repository, seen_internal_ids={internal_id}, successful_sources=set(),
            successful_source_identities=IDENTITIES,
            seen_observation_ids=third.seen_observation_ids,
            now=START + timedelta(days=2),
        )
        status = repository.get(internal_id).opportunity.lifecycle_status.value  # type: ignore[union-attr]
        print(f"Run 3: Jobicy missing, WWR present -> {status}")

        for day in (3, 4, 5):
            result = reconcile_lifecycle(
                repository, seen_internal_ids=set(), successful_sources=set(),
                successful_source_identities=IDENTITIES,
                seen_observation_ids=set(), now=START + timedelta(days=day),
            )
            stored = repository.get(internal_id)
            assert stored is not None
            print(
                f"Run {day + 1}: both missing -> "
                f"{stored.opportunity.lifecycle_status.value} "
                f"(global misses={stored.opportunity.consecutive_misses}, "
                f"newly closed={result.newly_closed})"
            )


if __name__ == "__main__":
    main()
