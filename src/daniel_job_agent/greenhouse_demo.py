"""Consulta manual e explícita de um único board público do Greenhouse."""

import argparse

from .ingestion import GreenhouseJobAdapter, ingest_batch
from .pipeline import process_opportunities
from .profiles import create_daniel_profile
from .sources import GreenhouseJobSource


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read one public Greenhouse job board and rank its jobs."
    )
    parser.add_argument("board_token", help="Public token from the Greenhouse board URL")
    parser.add_argument(
        "company_name",
        help="Company display name (the list-jobs response does not provide it)",
    )
    args = parser.parse_args()

    source = GreenhouseJobSource(args.board_token, args.company_name)
    source_result = source.fetch()
    if not source_result.success:
        print(f"Source error: {source_result.message}")
        return

    ingestion = ingest_batch(
        source_result.records,
        GreenhouseJobAdapter(args.company_name),
    )
    pipeline = process_opportunities(
        ingestion.opportunities,
        create_daniel_profile(),
    )

    print("Greenhouse public board")
    print(f"Jobs received: {len(source_result.records)}")
    print(f"Jobs converted: {ingestion.converted_count}")
    print(f"Warnings: {ingestion.warning_count}")
    print(f"Ingestion errors: {ingestion.error_count}")
    print(
        f"KEEP: {pipeline.keep_count} | REVIEW: {pipeline.review_count} "
        f"| REJECT: {pipeline.reject_count}"
    )
    print("\nTop opportunities:")
    for item in pipeline.ranked_opportunities[:10]:
        job = item.normalized_job
        print(
            f"{item.rank}. {job.role} — {job.company} "
            f"| Score {item.match_score} | {item.retention_decision.value}"
        )


if __name__ == "__main__":
    main()
