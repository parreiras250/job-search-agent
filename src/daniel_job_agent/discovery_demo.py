"""Executa manualmente o discovery global Jobicy + Remotive."""

import argparse

from .discovery import MultiSourceDiscovery
from .profiles import create_daniel_profile


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one Jobicy and one Remotive query and rank them globally."
    )
    parser.parse_args()

    discovery = MultiSourceDiscovery()
    print("Multi-source discovery query")
    print("Jobicy: geo=latam, industry=seller, count=100, tag=(none)")
    print("Remotive: category=sales, company_name=(none), search=(none), limit=(none)")

    result = discovery.run(create_daniel_profile())
    print("\nSource summary:")
    for name in result.sources_attempted:
        summary = result.source_summaries[name]
        print(name)
        print(
            f"  received={summary.received} | converted={summary.converted} "
            f"| warnings={summary.warnings} | errors={summary.errors}"
        )
        if summary.failure_message:
            print(f"  source error={summary.failure_message}")

    classified = result.keep_count + result.review_count + result.reject_count
    print("\nGlobal summary:")
    print(f"Sources attempted: {len(result.sources_attempted)}")
    print(f"Sources succeeded: {len(result.sources_succeeded)}")
    print(f"Sources failed: {len(result.sources_failed)}")
    print(f"Jobs before global dedup: {result.total_jobs_before_global_dedup}")
    print(f"Unique jobs: {result.global_unique_jobs}")
    print(f"Global duplicates: {result.global_duplicates}")
    print(f"Cross-source duplicates: {result.cross_source_duplicates}")
    print(
        f"KEEP: {result.keep_count} | REVIEW: {result.review_count} "
        f"| REJECT: {result.reject_count}"
    )
    print(f"Check: unique jobs = KEEP + REVIEW + REJECT = {classified}")

    print("\nTop global opportunities:")
    for item in result.ranking[:15]:
        job = item.normalized_job
        print(
            f"{item.rank}. {job.role} — {job.company} | {job.location} "
            f"| Score {item.match_score} | {item.retention_decision.value} "
            f"| {item.role_family.value} | {item.seniority.value} "
            f"| {job.source} | {job.job_url}"
        )


if __name__ == "__main__":
    main()
