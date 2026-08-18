import unittest

from daniel_job_agent import (
    MultiSourceDiscovery,
    SourceResult,
    SourceStatus,
    create_daniel_profile,
)


class StubSource:
    def __init__(self, result: SourceResult):
        self.result = result
        self.calls = 0

    def fetch(self) -> SourceResult:
        self.calls += 1
        return self.result


def jobicy_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": 1,
        "url": "https://jobicy.com/jobs/1",
        "jobTitle": "Account Executive",
        "companyName": "Alpha SaaS",
        "jobIndustry": ["Sales"],
        "jobType": ["full-time"],
        "jobGeo": "LATAM",
        "jobDescription": "Own the full sales cycle for B2B SaaS customers.",
        "pubDate": "2026-08-14 10:30:00",
    }
    record.update(overrides)
    return record


def remotive_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": 2,
        "url": "https://remotive.com/remote-jobs/sales/account-executive-2",
        "title": "Account Executive",
        "company_name": "Beta SaaS",
        "category": "Sales",
        "job_type": "full_time",
        "publication_date": "2026-08-14T10:30:00Z",
        "candidate_required_location": "LATAM",
        "salary": "$40,000 - $50,000",
        "description": "Own the full sales cycle for B2B SaaS customers.",
    }
    record.update(overrides)
    return record


def success(records: list[dict[str, object]]) -> SourceResult:
    status = SourceStatus.SUCCESS if records else SourceStatus.NO_JOBS
    return SourceResult(status=status, records=records)


def failure(message: str) -> SourceResult:
    return SourceResult(
        status=SourceStatus.CONNECTION_ERROR,
        records=[],
        message=message,
    )


class MultiSourceDiscoveryTests(unittest.TestCase):
    def run_discovery(self, jobicy: SourceResult, remotive: SourceResult):
        jobicy_source = StubSource(jobicy)
        remotive_source = StubSource(remotive)
        wwr_source = StubSource(success([]))
        himalayas_source = StubSource(success([]))
        remoteok_source = StubSource(success([]))
        getonboard_source = StubSource(success([]))
        result = MultiSourceDiscovery(
            jobicy_source=jobicy_source,
            remotive_source=remotive_source,
            wwr_source=wwr_source,
            himalayas_source=himalayas_source,
            remoteok_source=remoteok_source,
            getonboard_source=getonboard_source,
        ).run(create_daniel_profile())
        self.assertEqual(jobicy_source.calls, 1)
        self.assertEqual(remotive_source.calls, 1)
        self.assertEqual(wwr_source.calls, 1)
        self.assertEqual(himalayas_source.calls, 1)
        self.assertEqual(remoteok_source.calls, 1)
        return result

    def test_both_sources_succeed_with_global_counts_and_ranking(self):
        result = self.run_discovery(
            success([jobicy_record()]), success([remotive_record()])
        )
        self.assertEqual(result.sources_attempted, ["Jobicy", "Remotive", "We Work Remotely", "Himalayas", "RemoteOK", "Get on Board"])
        self.assertEqual(result.sources_succeeded, ["Jobicy", "Remotive", "We Work Remotely", "Himalayas", "RemoteOK", "Get on Board"])
        self.assertEqual(result.sources_failed, [])
        self.assertEqual(result.jobs_received_by_source, {"Jobicy": 1, "Remotive": 1, "We Work Remotely": 0, "Himalayas": 0, "RemoteOK": 0, "Get on Board": 0})
        self.assertEqual(result.jobs_converted_by_source, {"Jobicy": 1, "Remotive": 1, "We Work Remotely": 0, "Himalayas": 0, "RemoteOK": 0, "Get on Board": 0})
        self.assertEqual(result.total_jobs_before_global_dedup, 2)
        self.assertEqual(result.global_unique_jobs, 2)
        self.assertEqual([item.rank for item in result.ranking], [1, 2])
        self.assertEqual(result.global_unique_jobs, result.keep_count + result.review_count + result.reject_count)
        self.assertTrue(all(item.retention_decision.value == "KEEP" for item in result.ranking))

    def test_jobicy_failure_does_not_stop_remotive(self):
        result = self.run_discovery(failure("Jobicy offline"), success([remotive_record()]))
        self.assertEqual(result.sources_succeeded, ["Remotive", "We Work Remotely", "Himalayas", "RemoteOK", "Get on Board"])
        self.assertEqual(result.sources_failed, ["Jobicy"])
        self.assertEqual(result.source_failure_messages, {"Jobicy": "Jobicy offline"})
        self.assertEqual(result.global_unique_jobs, 1)
        self.assertEqual(result.ranking[0].normalized_job.source, "Remotive")

    def test_remotive_failure_does_not_stop_jobicy(self):
        result = self.run_discovery(success([jobicy_record()]), failure("Remotive offline"))
        self.assertEqual(result.sources_succeeded, ["Jobicy", "We Work Remotely", "Himalayas", "RemoteOK", "Get on Board"])
        self.assertEqual(result.sources_failed, ["Remotive"])
        self.assertEqual(result.source_failure_messages, {"Remotive": "Remotive offline"})
        self.assertEqual(result.global_unique_jobs, 1)

    def test_both_sources_can_fail_without_crashing(self):
        result = self.run_discovery(failure("one"), failure("two"))
        self.assertEqual(result.sources_succeeded, ["We Work Remotely", "Himalayas", "RemoteOK", "Get on Board"])
        self.assertEqual(result.sources_failed, ["Jobicy", "Remotive"])
        self.assertEqual(result.total_jobs_before_global_dedup, 0)
        self.assertEqual(result.ranking, [])

    def test_zero_jobs_is_success_and_both_zero_produce_empty_ranking(self):
        one_zero = self.run_discovery(success([]), success([remotive_record()]))
        self.assertEqual(one_zero.sources_succeeded, ["Jobicy", "Remotive", "We Work Remotely", "Himalayas", "RemoteOK", "Get on Board"])
        self.assertEqual(one_zero.jobs_received_by_source["Jobicy"], 0)
        both_zero = self.run_discovery(success([]), success([]))
        self.assertEqual(both_zero.sources_failed, [])
        self.assertEqual(both_zero.global_unique_jobs, 0)

    def test_warnings_and_ingestion_errors_remain_isolated_by_source(self):
        result = self.run_discovery(
            success([
                jobicy_record(id=1, pubDate="not-a-date"),
                jobicy_record(id=2, companyName=""),
            ]),
            success([remotive_record()]),
        )
        self.assertEqual(result.warnings_by_source, {"Jobicy": 1, "Remotive": 0, "We Work Remotely": 0, "Himalayas": 0, "RemoteOK": 0, "Get on Board": 0})
        self.assertEqual(result.errors_by_source, {"Jobicy": 1, "Remotive": 0, "We Work Remotely": 0, "Himalayas": 0, "RemoteOK": 0, "Get on Board": 0})
        self.assertEqual(result.jobs_converted_by_source, {"Jobicy": 1, "Remotive": 1, "We Work Remotely": 0, "Himalayas": 0, "RemoteOK": 0, "Get on Board": 0})
        self.assertEqual(result.global_unique_jobs, 2)

    def test_cross_source_duplicate_keeps_primary_source_and_records_duplicate(self):
        result = self.run_discovery(
            success([jobicy_record(companyName="Same Company")]),
            success([remotive_record(company_name="Same Company")]),
        )
        self.assertEqual(result.total_jobs_before_global_dedup, 2)
        self.assertEqual(result.global_unique_jobs, 1)
        self.assertEqual(result.global_duplicates, 1)
        self.assertEqual(result.cross_source_duplicates, 1)
        self.assertEqual(result.ranking[0].normalized_job.source, "Jobicy public Remote Jobs API")

    def test_remotive_attribution_url_rejects_and_tracking_are_preserved(self):
        result = self.run_discovery(
            success([jobicy_record()]),
            success([
                remotive_record(
                    id=9,
                    title="Software Engineer",
                    company_name="Gamma",
                    candidate_required_location="USA",
                    url="https://remotive.com/remote-jobs/software-dev/engineer-9",
                )
            ]),
        )
        remotive_summary = result.source_summaries["Remotive"]
        assert remotive_summary.ingestion is not None
        tracking = remotive_summary.ingestion.opportunities[0].tracking
        ranked = next(
            item for item in result.ranking
            if item.normalized_job.source == "Remotive"
        )
        self.assertEqual(ranked.retention_decision.value, "REJECT")
        self.assertEqual(
            ranked.normalized_job.job_url,
            "https://remotive.com/remote-jobs/software-dev/engineer-9",
        )
        self.assertIs(ranked.normalized_job.tracking, tracking)

    def test_result_is_deterministic_for_same_inputs(self):
        first = self.run_discovery(
            success([jobicy_record()]), success([remotive_record()])
        )
        second = self.run_discovery(
            success([jobicy_record()]), success([remotive_record()])
        )
        first_order = [item.normalized_job.job_url for item in first.ranking]
        second_order = [item.normalized_job.job_url for item in second.ranking]
        self.assertEqual(first_order, second_order)


if __name__ == "__main__":
    unittest.main()
