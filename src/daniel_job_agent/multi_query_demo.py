"""Executa manualmente a estratégia controlada de múltiplas queries."""

import argparse

from .profiles import create_daniel_profile
from .search_strategy import (
    MultiQueryDiscovery,
    create_search_strategy,
    format_query_efficiency_report,
    recommend_search_strategy,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the controlled Jobicy + Remotive multi-query strategy."
    )
    parser.add_argument(
        "--mode",
        choices=("broad", "full"),
        default="broad",
        help="broad uses 2 requests; full uses up to 8 (default: broad)",
    )
    args = parser.parse_args()

    strategy = create_search_strategy(args.mode)
    print("Strategy")
    print(f"Name: {strategy.name}")
    print(f"Jobicy queries: {len(strategy.jobicy_queries)}")
    print(f"Remotive queries: {len(strategy.remotive_queries)}")
    print(f"Planned requests: {strategy.expected_requests}")

    result = MultiQueryDiscovery(strategy).run(create_daniel_profile())
    print("\nQuery summary")
    for summary in result.query_summaries:
        print(
            f"{summary.source} | {summary.query_name} | received={summary.received} "
            f"| converted={summary.converted} | warnings={summary.warnings} "
            f"| errors={summary.errors}"
        )
        if summary.failure_message:
            print(f"  query error={summary.failure_message}")

    print("\nGlobal")
    print(f"Raw jobs across queries: {result.total_raw_results}")
    print(f"Converted before dedup: {result.total_jobs_before_dedup}")
    print(f"Unique jobs: {result.unique_jobs}")
    print(f"Intra-source duplicates: {result.intra_source_duplicates}")
    print(f"Cross-source duplicates: {result.cross_source_duplicates}")
    print(f"Duplication rate: {result.duplication_rate:.1%}")
    print(
        f"KEEP: {result.keep_count} | REVIEW: {result.review_count} "
        f"| REJECT: {result.reject_count} | KEEP rate: {result.keep_rate:.1%}"
    )

    print("\nCoverage")
    print(f"Unique from Jobicy primary records: {result.unique_jobs_by_source['Jobicy']}")
    print(f"Unique from Remotive primary records: {result.unique_jobs_by_source['Remotive']}")
    print(f"Found by multiple queries: {result.jobs_found_by_multiple_queries}")
    print(f"Broad baseline unique: {result.broad_unique_jobs}")
    print(f"Broad baseline KEEP: {result.broad_keep_count}")
    print(f"Incremental unique gain: {result.incremental_unique_gain:+d}")
    print(f"Incremental KEEP gain: {result.incremental_keep_gain:+d}")
    print(f"Useful queries: {result.useful_query_count}")
    print(f"Wasted queries: {result.wasted_query_count}")
    print(
        "Requests per unique job: "
        f"{result.requests_per_unique_job:.2f}"
        if result.requests_per_unique_job is not None
        else "Requests per unique job: n/a"
    )
    print(
        f"Requests per KEEP: {result.requests_per_keep:.2f}"
        if result.requests_per_keep is not None
        else "Requests per KEEP: n/a"
    )

    print("\nEfficiency")
    print(format_query_efficiency_report(result.query_efficiencies))

    recommendation = recommend_search_strategy(result)
    print("\nRecommended next-run strategy")
    print("Keep:")
    for key in recommendation.keep_query_keys:
        print(f"- {key}")
    print("Drop:")
    if recommendation.drop_query_keys:
        for key in recommendation.drop_query_keys:
            print(f"- {key}: {recommendation.reasons[key]}")
    else:
        print("- none")

    print("\nTop global opportunities")
    for item in result.ranking[:20]:
        job = item.normalized_job
        print(
            f"{item.rank}. {job.role} — {job.company} | {job.location} "
            f"| Score {item.match_score} | {item.retention_decision.value} "
            f"| {item.role_family.value} | {item.seniority.value} "
            f"| {job.source} | {job.job_url}"
        )


if __name__ == "__main__":
    main()
