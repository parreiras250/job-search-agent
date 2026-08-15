"""Consulta manual e explícita de um único site público do Lever."""

import argparse

from .enrichment import enrich_opportunities
from .ingestion import LeverJobAdapter, ingest_batch
from .pipeline import process_opportunities
from .profiles import create_daniel_profile
from .reporting import format_counts
from .sources import LeverJobSource


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read one public Lever postings site and rank its jobs."
    )
    parser.add_argument("company_slug", help="Public site slug from the Lever jobs URL")
    parser.add_argument("company_name", help="Company display name")
    parser.add_argument(
        "--region",
        choices=("global", "eu"),
        default="global",
        help="Lever instance region (default: global)",
    )
    args = parser.parse_args()

    source = LeverJobSource(
        args.company_slug,
        args.company_name,
        region=args.region,
    )
    source_result = source.fetch()
    if not source_result.success:
        print(f"Source error: {source_result.message}")
        return

    ingestion = ingest_batch(
        source_result.records,
        LeverJobAdapter(args.company_name),
    )
    enriched_jobs = enrich_opportunities(ingestion.opportunities)
    pipeline = process_opportunities(enriched_jobs, create_daniel_profile())

    print("Lever public postings")
    print(format_counts(len(source_result.records), ingestion, pipeline))
    print("\nTop opportunities:")
    for item in pipeline.ranked_opportunities[:10]:
        job = item.normalized_job
        print(
            f"{item.rank}. {job.role} — {job.company} "
            f"| Score {item.match_score} | {item.retention_decision.value}"
        )


if __name__ == "__main__":
    main()
