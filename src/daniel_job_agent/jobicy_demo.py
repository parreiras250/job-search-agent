"""Consulta manual e explícita da API pública de vagas remotas do Jobicy."""

import argparse

from .enrichment import enrich_opportunities
from .ingestion import JobicyJobAdapter, ingest_batch
from .pipeline import process_opportunities
from .profiles import create_daniel_profile
from .reporting import format_counts, format_warning_summary
from .sources import JobicyJobSource


def main() -> None:
    parser = argparse.ArgumentParser(description="Read and rank one Jobicy query.")
    parser.add_argument("--geo", default="latam", help="Jobicy geo filter")
    parser.add_argument("--industry", default="seller", help="Jobicy industry filter")
    parser.add_argument("--count", type=int, default=100, help="Number of jobs (1-100)")
    parser.add_argument("--tag", help="Optional Jobicy tag filter")
    args = parser.parse_args()

    source = JobicyJobSource(
        count=args.count, geo=args.geo, industry=args.industry, tag=args.tag
    )
    print(
        "Jobicy query: "
        f"count={args.count}, geo={args.geo}, industry={args.industry}, "
        f"tag={args.tag or '(none)'}"
    )
    source_result = source.fetch()
    if not source_result.success:
        print(f"Source error: {source_result.message}")
        return

    ingestion = ingest_batch(source_result.records, JobicyJobAdapter())
    pipeline = process_opportunities(
        enrich_opportunities(ingestion.opportunities), create_daniel_profile()
    )
    print(format_counts(len(source_result.records), ingestion, pipeline))
    warning_summary = format_warning_summary(ingestion)
    if warning_summary:
        print(f"\n{warning_summary}")
    print("\nTop opportunities:")
    for item in pipeline.ranked_opportunities[:10]:
        job = item.normalized_job
        print(
            f"{item.rank}. {job.role} — {job.company} | {job.location} "
            f"| Score {item.match_score} | {item.retention_decision.value} "
            f"| {job.job_url}"
        )


if __name__ == "__main__":
    main()
