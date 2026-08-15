"""Consulta manual e explícita da API pública de vagas remotas da Remotive."""

import argparse

from .enrichment import enrich_opportunities
from .ingestion import RemotiveJobAdapter, ingest_batch
from .pipeline import process_opportunities
from .profiles import create_daniel_profile
from .reporting import format_counts, format_warning_summary
from .sources import RemotiveJobSource


def main() -> None:
    parser = argparse.ArgumentParser(description="Read and rank one Remotive query.")
    parser.add_argument("--category", help="Remotive category filter")
    parser.add_argument("--company-name", help="Optional company name filter")
    parser.add_argument("--search", help="Optional title and description search")
    parser.add_argument("--limit", type=int, help="Optional positive result limit")
    args = parser.parse_args()

    source = RemotiveJobSource(
        category=args.category,
        company_name=args.company_name,
        search=args.search,
        limit=args.limit,
    )
    print(
        "Remotive query: "
        f"category={args.category or '(none)'}, "
        f"company_name={args.company_name or '(none)'}, "
        f"search={args.search or '(none)'}, limit={args.limit or '(none)'}"
    )
    source_result = source.fetch()
    if not source_result.success:
        print(f"Source error: {source_result.message}")
        return

    ingestion = ingest_batch(source_result.records, RemotiveJobAdapter())
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
            f"| {job.source} | {job.job_url}"
        )


if __name__ == "__main__":
    main()
