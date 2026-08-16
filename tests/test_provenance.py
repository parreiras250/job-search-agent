"""Testes offline de provenance persistente e lifecycle multi-source."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from daniel_job_agent import (
    ApplicationStatus,
    JobLifecycleStatus,
    JobOpportunity,
    JobRepository,
    LifecyclePolicy,
    LocalCRM,
    create_daniel_profile,
    process_opportunities,
    reconcile_lifecycle,
    sync_opportunities,
)


START = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)


def job(
    source_id: str,
    *,
    url: str | None = None,
    external_id: str | None = None,
    authority: str = "OBSERVATIONAL",
) -> JobOpportunity:
    labels = {
        "jobicy": "Jobicy public Remote Jobs API",
        "remotive": "Remotive",
        "weworkremotely": "We Work Remotely",
        "greenhouse-example": "Future Greenhouse Example",
    }
    families = {"greenhouse-example": "greenhouse"}
    instances = {
        "jobicy": "jobicy:global",
        "remotive": "remotive:global",
        "weworkremotely": "weworkremotely:sales-marketing",
        "greenhouse-example": "greenhouse:example",
    }
    types = {
        "jobicy": "GLOBAL_BOARD",
        "remotive": "AGGREGATOR",
        "weworkremotely": "FEED",
        "greenhouse-example": "TENANT_BOARD",
    }
    return JobOpportunity(
        company="Same SaaS",
        role="Account Executive",
        job_url=url or f"https://{source_id}.example/jobs/ae",
        source=labels[source_id],
        location="LATAM",
        remote=True,
        brazil_eligible=True,
        external_id=external_id or f"{source_id}-ae",
        source_id=source_id,
        source_family=families.get(source_id, source_id),
        source_instance=instances[source_id],
        source_type=types[source_id],
        lifecycle_authority=authority,
    )


def pipeline(*jobs: JobOpportunity):
    return process_opportunities(jobs, create_daniel_profile())


class ObservationPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = JobRepository(":memory:")

    def tearDown(self) -> None:
        self.repository.close()

    def test_one_logical_opportunity_persists_three_observations(self) -> None:
        output = sync_opportunities(
            pipeline(job("jobicy"), job("remotive"), job("weworkremotely")),
            self.repository,
            now=START,
        )
        self.assertEqual(self.repository.count(), 1)
        self.assertEqual(output.observations_created, 3)
        self.assertEqual(output.cross_source_observations_added, 2)
        observations = self.repository.get_observations(output.new_jobs[0].internal_id)
        self.assertEqual(
            [item.source_id for item in observations],
            ["jobicy", "remotive", "weworkremotely"],
        )
        self.assertEqual(len(output.seen_observation_ids), 3)

    def test_existing_observation_updates_without_losing_first_seen(self) -> None:
        first = sync_opportunities(pipeline(job("jobicy")), self.repository, now=START)
        internal_id = first.new_jobs[0].internal_id
        original = self.repository.get_observations(internal_id)[0]
        later = START + timedelta(days=1)
        second = sync_opportunities(pipeline(job("jobicy")), self.repository, now=later)
        updated = self.repository.get_observations(internal_id)[0]
        self.assertEqual(second.observations_updated, 1)
        self.assertEqual(updated.first_seen_at, original.first_seen_at)
        self.assertEqual(updated.last_seen_at, later)
        self.assertTrue(updated.active)
        self.assertEqual(updated.consecutive_misses, 0)

    def test_cross_source_sync_preserves_original_primary_source_and_crm(self) -> None:
        first = sync_opportunities(pipeline(job("jobicy")), self.repository, now=START)
        internal_id = first.new_jobs[0].internal_id
        LocalCRM(self.repository).update_manual_fields(
            internal_id,
            application_status=ApplicationStatus.APPLIED,
            notes="keep this manual note",
        )
        sync_opportunities(
            pipeline(job("weworkremotely")),
            self.repository,
            now=START + timedelta(days=1),
        )
        stored = self.repository.get(internal_id)
        assert stored is not None
        self.assertEqual(stored.opportunity.source_id, "jobicy")
        self.assertEqual(stored.opportunity.tracking.application_status, ApplicationStatus.APPLIED)
        self.assertEqual(stored.opportunity.tracking.notes, "keep this manual note")
        self.assertEqual(
            LocalCRM(self.repository).get(internal_id).observed_sources,  # type: ignore[union-attr]
            "jobicy | weworkremotely",
        )


class ObservationLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = JobRepository(":memory:")
        initial = sync_opportunities(
            pipeline(job("jobicy"), job("weworkremotely")),
            self.repository,
            now=START,
        )
        self.internal_id = initial.new_jobs[0].internal_id

    def tearDown(self) -> None:
        self.repository.close()

    def reconcile(self, identities, seen=frozenset(), day=1):
        return reconcile_lifecycle(
            self.repository,
            seen_internal_ids={self.internal_id} if seen else set(),
            successful_sources=set(),
            successful_source_identities=set(identities),
            seen_observation_ids=set(seen),
            policy=LifecyclePolicy(),
            now=START + timedelta(days=day),
        )

    def test_one_observation_missing_but_another_seen_keeps_open(self) -> None:
        jobicy_observation = next(
            item for item in self.repository.get_observations(self.internal_id)
            if item.source_id == "jobicy"
        )
        output = self.reconcile(
            {("jobicy", "jobicy:global"), ("weworkremotely", "weworkremotely:sales-marketing")},
            {jobicy_observation.observation_id},
        )
        stored = self.repository.get(self.internal_id)
        assert stored is not None
        wwr = next(
            item for item in self.repository.get_observations(self.internal_id)
            if item.source_id == "weworkremotely"
        )
        self.assertEqual(output.misses_recorded, 0)
        self.assertEqual(wwr.consecutive_misses, 1)
        self.assertEqual(stored.opportunity.lifecycle_status, JobLifecycleStatus.OPEN)

    def test_source_failure_does_not_increment_its_observation_or_global_miss(self) -> None:
        before = {
            item.source_id: item.consecutive_misses
            for item in self.repository.get_observations(self.internal_id)
        }
        output = self.reconcile({("jobicy", "jobicy:global")})
        after = {
            item.source_id: item.consecutive_misses
            for item in self.repository.get_observations(self.internal_id)
        }
        self.assertEqual(after["weworkremotely"], before["weworkremotely"])
        self.assertEqual(after["jobicy"], before["jobicy"] + 1)
        self.assertEqual(output.misses_recorded, 0)

    def test_all_missing_progresses_then_any_source_reopens(self) -> None:
        identities = {
            ("jobicy", "jobicy:global"),
            ("weworkremotely", "weworkremotely:sales-marketing"),
        }
        first = self.reconcile(identities, day=1)
        second = self.reconcile(identities, day=2)
        third = self.reconcile(identities, day=3)
        self.assertEqual(first.misses_recorded, 1)
        self.assertEqual(second.possibly_closed, 1)
        self.assertEqual(third.newly_closed, 1)
        seen = sync_opportunities(
            pipeline(job("weworkremotely")),
            self.repository,
            now=START + timedelta(days=4),
        )
        reopened = reconcile_lifecycle(
            self.repository,
            seen_internal_ids={self.internal_id},
            successful_sources=set(),
            successful_source_identities={
                ("weworkremotely", "weworkremotely:sales-marketing")
            },
            seen_observation_ids=seen.seen_observation_ids,
            now=START + timedelta(days=4),
        )
        self.assertEqual(reopened.reopened, 1)
        stored = self.repository.get(self.internal_id)
        assert stored is not None
        self.assertEqual(stored.opportunity.lifecycle_status, JobLifecycleStatus.OPEN)

    def test_fake_authoritative_present_overrides_missing_wwr(self) -> None:
        sync = sync_opportunities(
            pipeline(
                job("greenhouse-example", authority="AUTHORITATIVE")
            ),
            self.repository,
            now=START + timedelta(hours=1),
        )
        greenhouse_id = next(
            observation_id
            for observation_id in sync.seen_observation_ids
        )
        output = self.reconcile(
            {
                ("greenhouse", "greenhouse:example"),
                ("weworkremotely", "weworkremotely:sales-marketing"),
            },
            {greenhouse_id},
        )
        stored = self.repository.get(self.internal_id)
        assert stored is not None
        self.assertEqual(output.misses_recorded, 0)
        self.assertEqual(stored.opportunity.lifecycle_status, JobLifecycleStatus.OPEN)
        authority = next(
            item for item in self.repository.get_observations(self.internal_id)
            if item.source_family == "greenhouse"
        )
        self.assertEqual(authority.lifecycle_authority, "AUTHORITATIVE")


class ObservationMigrationTests(unittest.TestCase):
    def test_33_existing_rows_gain_observations_idempotently_and_keep_crm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "existing.db"
            with JobRepository(path) as repository:
                for index in range(33):
                    item = job("jobicy", url=f"https://jobicy.example/jobs/{index}", external_id=str(index))
                    item.company = f"Company {index}"
                    sync = sync_opportunities(pipeline(item), repository, now=START)
                    if index == 0:
                        LocalCRM(repository).update_manual_fields(
                            sync.new_jobs[0].internal_id,
                            application_status=ApplicationStatus.APPLIED,
                            notes="migration note",
                        )
                repository.connection.execute("DROP TABLE source_observations")
                repository.connection.execute("PRAGMA user_version = 4")
                repository.connection.commit()
            with JobRepository(path) as migrated:
                self.assertEqual(migrated.count(), 33)
                self.assertEqual(migrated.observation_count(), 33)
                self.assertEqual(
                    migrated.connection.execute("PRAGMA user_version").fetchone()[0], 5
                )
                first = LocalCRM(migrated).list_records(application_status="APPLIED")[0]
                self.assertEqual(first.notes, "migration note")
            with JobRepository(path) as reopened:
                self.assertEqual(reopened.observation_count(), 33)


if __name__ == "__main__":
    unittest.main()
