import unittest

from daniel_job_agent import (
    JobicySearchQuery,
    MultiQueryDiscovery,
    QueryUsefulnessRule,
    RemotiveSearchQuery,
    SearchStrategy,
    SourceResult,
    SourceStatus,
    create_daniel_profile,
    create_default_search_strategy,
    create_full_search_strategy,
    create_search_strategy,
    recommend_search_strategy,
)


class StubSource:
    def __init__(self, result: SourceResult):
        self.result = result
        self.calls = 0

    def fetch(self) -> SourceResult:
        self.calls += 1
        return self.result


def success(records):
    return SourceResult(
        status=SourceStatus.SUCCESS if records else SourceStatus.NO_JOBS,
        records=records,
    )


def failure(message="offline"):
    return SourceResult(
        status=SourceStatus.CONNECTION_ERROR, records=[], message=message
    )


def jobicy_record(identifier=1, **changes):
    record = {
        "id": identifier,
        "url": f"https://jobicy.com/jobs/{identifier}",
        "jobTitle": "Account Executive",
        "companyName": f"Jobicy Company {identifier}",
        "jobIndustry": ["Sales"],
        "jobType": ["full-time"],
        "jobGeo": "LATAM",
        "jobDescription": "Own the full sales cycle for B2B SaaS customers.",
        "pubDate": "2026-08-15 10:30:00",
    }
    record.update(changes)
    return record


def remotive_record(identifier=1, **changes):
    record = {
        "id": identifier,
        "url": f"https://remotive.com/remote-jobs/sales/job-{identifier}",
        "title": "Account Executive",
        "company_name": f"Remotive Company {identifier}",
        "category": "Sales",
        "job_type": "full_time",
        "publication_date": "2026-08-15T10:30:00Z",
        "candidate_required_location": "LATAM",
        "salary": "$40,000 - $50,000",
        "description": "Own the full sales cycle for B2B SaaS customers.",
    }
    record.update(changes)
    return record


class Factory:
    def __init__(self, results):
        self.results = results
        self.sources = []

    def __call__(self, query):
        source = StubSource(self.results.get(query.name, success([])))
        self.sources.append(source)
        return source


class SearchStrategyConfigurationTests(unittest.TestCase):
    def test_default_strategy_is_broad_only(self):
        strategy = create_default_search_strategy()
        self.assertEqual(strategy.name, "Daniel broad sales baseline")
        self.assertEqual(len(strategy.jobicy_queries), 1)
        self.assertEqual(len(strategy.remotive_queries), 1)
        self.assertEqual(strategy.expected_requests, 4)
        self.assertTrue(strategy.jobicy_queries[0].broad)
        self.assertTrue(strategy.remotive_queries[0].broad)

    def test_full_strategy_keeps_broad_and_three_targeted_per_source(self):
        strategy = create_full_search_strategy()
        self.assertEqual(strategy.expected_requests, 8)
        self.assertEqual(
            [query.tag for query in strategy.jobicy_queries[1:]],
            ["account executive", "business development", "sales development"],
        )

    def test_smaller_limits_keep_broad_query_first(self):
        strategy = create_full_search_strategy(jobicy_limit=2, remotive_limit=1)
        self.assertEqual(strategy.expected_requests, 3)
        self.assertTrue(strategy.jobicy_queries[0].broad)
        self.assertTrue(strategy.remotive_queries[0].broad)

    def test_strategy_rejects_more_than_four_queries_per_source(self):
        queries = tuple(
            JobicySearchQuery(f"query_{index}", broad=index == 0)
            for index in range(5)
        )
        with self.assertRaises(ValueError):
            SearchStrategy("too many", queries, ())
        remotive_queries = tuple(
            RemotiveSearchQuery(f"query_{index}", broad=index == 0)
            for index in range(5)
        )
        with self.assertRaises(ValueError):
            SearchStrategy("too many", (), remotive_queries)

    def test_public_modes_select_broad_or_full_and_preserve_limits(self):
        self.assertEqual(create_search_strategy("broad").expected_requests, 4)
        self.assertEqual(create_search_strategy("full").expected_requests, 8)
        with self.assertRaises(ValueError):
            create_search_strategy("aggressive")


class MultiQueryDiscoveryTests(unittest.TestCase):
    def run_strategy(self, strategy, jobicy_results, remotive_results):
        jobicy_factory = Factory(jobicy_results)
        remotive_factory = Factory(remotive_results)
        result = MultiQueryDiscovery(
            strategy,
            jobicy_source_factory=jobicy_factory,
            remotive_source_factory=remotive_factory,
            source_factories={
                "weworkremotely": lambda query: StubSource(success([])),
                "himalayas": lambda query: StubSource(success([])),
            },
        ).run(create_daniel_profile())
        self.assertTrue(all(source.calls == 1 for source in jobicy_factory.sources))
        self.assertTrue(all(source.calls == 1 for source in remotive_factory.sources))
        return result

    def test_query_success_failure_and_counts_are_isolated(self):
        strategy = create_full_search_strategy(jobicy_limit=2, remotive_limit=1)
        result = self.run_strategy(
            strategy,
            {
                "broad_latam_sales": success([jobicy_record(1)]),
                "account_executive": failure("targeted timeout"),
            },
            {"broad_sales": success([remotive_record(1)])},
        )
        self.assertEqual(len(result.query_summaries), 3)
        failed = next(item for item in result.query_summaries if item.failure_message)
        self.assertEqual(failed.query_key, "jobicy:account_executive")
        self.assertEqual(failed.failure_message, "targeted timeout")
        self.assertEqual(result.unique_jobs, 2)

    def test_all_jobicy_queries_can_fail_while_remotive_continues(self):
        strategy = create_full_search_strategy(jobicy_limit=2, remotive_limit=1)
        result = self.run_strategy(
            strategy,
            {"broad_latam_sales": failure(), "account_executive": failure()},
            {"broad_sales": success([remotive_record(1)])},
        )
        self.assertEqual(result.unique_jobs, 1)
        self.assertEqual(result.unique_jobs_by_source, {"jobicy": 0, "remotive": 1})

    def test_intra_and_cross_source_dedup_preserve_provenance(self):
        strategy = create_full_search_strategy(jobicy_limit=2, remotive_limit=1)
        jobicy = jobicy_record(1, companyName="Same Company")
        remotive = remotive_record(1, company_name="Same Company")
        result = self.run_strategy(
            strategy,
            {
                "broad_latam_sales": success([jobicy]),
                "account_executive": success([jobicy]),
            },
            {"broad_sales": success([remotive])},
        )
        self.assertEqual(result.total_jobs_before_dedup, 3)
        self.assertEqual(result.unique_jobs, 1)
        self.assertEqual(result.intra_source_duplicates, 1)
        self.assertEqual(result.cross_source_duplicates, 1)
        self.assertAlmostEqual(result.duplication_rate, 2 / 3)
        self.assertEqual(result.jobs_found_by_multiple_queries, 1)
        self.assertEqual(
            result.provenance_by_job_url["https://jobicy.com/jobs/1"],
            [
                "jobicy:account_executive",
                "jobicy:broad_latam_sales",
                "remotive:broad_sales",
            ],
        )

    def test_same_job_in_three_queries_appears_once_without_score_bonus(self):
        three = create_full_search_strategy(jobicy_limit=3, remotive_limit=0)
        record = jobicy_record(1)
        multi = self.run_strategy(
            three,
            {
                "broad_latam_sales": success([record]),
                "account_executive": success([record]),
                "business_development": success([record]),
            },
            {},
        )
        single = self.run_strategy(
            create_full_search_strategy(jobicy_limit=1, remotive_limit=0),
            {"broad_latam_sales": success([record])},
            {},
        )
        self.assertEqual(multi.unique_jobs, 1)
        self.assertEqual(multi.jobs_found_by_multiple_queries, 1)
        self.assertEqual(multi.ranking[0].match_score, single.ranking[0].match_score)

    def test_metrics_baseline_and_incremental_gain(self):
        strategy = create_full_search_strategy(jobicy_limit=2, remotive_limit=1)
        result = self.run_strategy(
            strategy,
            {
                "broad_latam_sales": success([jobicy_record(1)]),
                "account_executive": success([jobicy_record(2)]),
            },
            {"broad_sales": success([remotive_record(1)])},
        )
        self.assertEqual(result.total_raw_results, 3)
        self.assertEqual(result.unique_jobs, 3)
        self.assertEqual(result.duplication_rate, 0.0)
        self.assertEqual(result.broad_unique_jobs, 2)
        self.assertEqual(result.incremental_unique_gain, 1)
        self.assertEqual(result.incremental_keep_gain, 1)
        self.assertEqual(result.keep_rate, 1.0)

    def test_warnings_errors_rejects_and_tracking_remain_available(self):
        strategy = create_full_search_strategy(jobicy_limit=1, remotive_limit=1)
        result = self.run_strategy(
            strategy,
            {"broad_latam_sales": success([
                jobicy_record(1, pubDate="bad-date"),
                jobicy_record(2, companyName=""),
            ])},
            {"broad_sales": success([
                remotive_record(1, title="Software Engineer")
            ])},
        )
        jobicy_summary = result.query_summaries[0]
        self.assertEqual((jobicy_summary.warnings, jobicy_summary.errors), (1, 1))
        self.assertEqual(result.reject_count, 1)
        assert jobicy_summary.ingestion is not None
        tracking = jobicy_summary.ingestion.opportunities[0].tracking
        ranked_jobicy = next(
            item for item in result.ranking
            if item.normalized_job.source != "Remotive"
        )
        self.assertIs(ranked_jobicy.normalized_job.tracking, tracking)

    def test_ranking_is_deterministic(self):
        strategy = create_full_search_strategy(jobicy_limit=1, remotive_limit=1)
        inputs = (
            {"broad_latam_sales": success([jobicy_record(1)])},
            {"broad_sales": success([remotive_record(1)])},
        )
        first = self.run_strategy(strategy, *inputs)
        second = self.run_strategy(strategy, *inputs)
        self.assertEqual(
            [item.normalized_job.job_url for item in first.ranking],
            [item.normalized_job.job_url for item in second.ranking],
        )


class QueryEfficiencyTests(unittest.TestCase):
    def run_strategy(self, strategy, jobicy_results, remotive_results):
        return MultiQueryDiscovery(
            strategy,
            jobicy_source_factory=Factory(jobicy_results),
            remotive_source_factory=Factory(remotive_results),
            source_factories={"weworkremotely": lambda query: StubSource(success([]))},
        ).run(create_daniel_profile())

    def test_query_with_incremental_keep_is_useful(self):
        strategy = create_full_search_strategy(jobicy_limit=2, remotive_limit=0)
        result = self.run_strategy(
            strategy,
            {
                "broad_latam_sales": success([]),
                "account_executive": success([jobicy_record(1)]),
            },
            {},
        )
        targeted = result.query_efficiencies[1]
        self.assertEqual(targeted.incremental_unique_gain, 1)
        self.assertEqual(targeted.incremental_keep_gain, 1)
        self.assertEqual(targeted.keep_contributed, 1)
        self.assertTrue(targeted.useful)

    def test_query_adding_only_review_is_still_useful_unique_gain(self):
        strategy = create_full_search_strategy(jobicy_limit=2, remotive_limit=0)
        result = self.run_strategy(
            strategy,
            {
                "broad_latam_sales": success([]),
                "account_executive": success([
                    jobicy_record(1, jobTitle="Sales Engineer")
                ]),
            },
            {},
        )
        targeted = result.query_efficiencies[1]
        self.assertEqual(targeted.review_contributed, 1)
        self.assertEqual(targeted.incremental_keep_gain, 0)
        self.assertTrue(targeted.useful)

    def test_fully_duplicate_query_and_empty_query_are_wasted(self):
        strategy = create_full_search_strategy(jobicy_limit=3, remotive_limit=0)
        record = jobicy_record(1)
        result = self.run_strategy(
            strategy,
            {
                "broad_latam_sales": success([record]),
                "account_executive": success([record]),
                "business_development": success([]),
            },
            {},
        )
        duplicate = result.query_efficiencies[1]
        empty = result.query_efficiencies[2]
        self.assertEqual(duplicate.duplicate_jobs, 1)
        self.assertEqual(duplicate.duplication_rate, 1.0)
        self.assertFalse(duplicate.useful)
        self.assertEqual(empty.jobs_received, 0)
        self.assertFalse(empty.useful)
        self.assertEqual(result.useful_query_count, 1)
        self.assertEqual(result.wasted_query_count, 2)

    def test_requests_per_unique_and_keep_are_safe(self):
        strategy = create_default_search_strategy()
        populated = self.run_strategy(
            strategy,
            {"broad_latam_sales": success([jobicy_record(1)])},
            {"broad_sales": success([remotive_record(1)])},
        )
        self.assertEqual(populated.requests_per_unique_job, 2.0)
        self.assertEqual(populated.requests_per_keep, 2.0)
        empty = self.run_strategy(
            strategy,
            {"broad_latam_sales": success([])},
            {"broad_sales": success([])},
        )
        self.assertIsNone(empty.requests_per_unique_job)
        self.assertIsNone(empty.requests_per_keep)

    def test_marginal_gain_depends_on_query_order(self):
        record = jobicy_record(1)
        first_strategy = SearchStrategy(
            "first order",
            (
                JobicySearchQuery("broad", broad=True),
                JobicySearchQuery("target_one", broad=False),
                JobicySearchQuery("target_two", broad=False),
            ),
            (),
        )
        first = self.run_strategy(
            first_strategy,
            {
                "broad": success([]),
                "target_one": success([record]),
                "target_two": success([record]),
            },
            {},
        )
        self.assertTrue(first.query_efficiencies[1].useful)
        self.assertFalse(first.query_efficiencies[2].useful)

    def test_configurable_usefulness_rule(self):
        rule = QueryUsefulnessRule(minimum_unique_gain=2, minimum_keep_gain=2)
        strategy = create_full_search_strategy(jobicy_limit=1, remotive_limit=0)
        factory = Factory({"broad_latam_sales": success([jobicy_record(1)])})
        result = MultiQueryDiscovery(
            strategy,
            jobicy_source_factory=factory,
            remotive_source_factory=Factory({}),
            usefulness_rule=rule,
        ).run(create_daniel_profile())
        self.assertFalse(result.query_efficiencies[0].useful)

    def test_recommendation_keeps_broad_drops_zero_gain_and_does_not_mutate(self):
        strategy = create_full_search_strategy(jobicy_limit=2, remotive_limit=1)
        original_keys = [
            query.key
            for query in (*strategy.jobicy_queries, *strategy.remotive_queries)
        ]
        record = jobicy_record(1)
        result = self.run_strategy(
            strategy,
            {
                "broad_latam_sales": success([record]),
                "account_executive": success([record]),
            },
            {"broad_sales": success([])},
        )
        recommendation = recommend_search_strategy(result)
        self.assertEqual(
            recommendation.keep_query_keys,
            ["jobicy:broad_latam_sales", "remotive:broad_sales"],
        )
        self.assertEqual(
            recommendation.drop_query_keys, ["jobicy:account_executive"]
        )
        self.assertEqual(recommendation.recommended_strategy.expected_requests, 2)
        self.assertEqual(
            [
                query.key
                for query in (*strategy.jobicy_queries, *strategy.remotive_queries)
            ],
            original_keys,
        )


if __name__ == "__main__":
    unittest.main()
