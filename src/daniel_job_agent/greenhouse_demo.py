"""Consulta manual e explícita de um único board público do Greenhouse."""

import argparse

from .enrichment import enrich_opportunities
from .ingestion import BatchIngestionResult, GreenhouseJobAdapter, ingest_batch
from .pipeline import PipelineResult, process_opportunities
from .profiles import create_daniel_profile
from .sources import GreenhouseJobSource


def format_counts(
    jobs_received: int,
    ingestion: BatchIngestionResult,
    pipeline: PipelineResult,
) -> str:
    """Mostra de forma auditável como os totais se relacionam."""

    classified = pipeline.keep_count + pipeline.review_count + pipeline.reject_count
    return "\n".join(
        [
            f"Jobs received: {jobs_received}",
            f"Jobs converted: {ingestion.converted_count}",
            f"Warnings: {ingestion.warning_count}",
            f"Ingestion errors: {ingestion.error_count}",
            f"Unique jobs: {pipeline.unique_opportunities}",
            f"Duplicates detected: {pipeline.duplicates_detected}",
            (
                f"KEEP: {pipeline.keep_count} | REVIEW: {pipeline.review_count} "
                f"| REJECT: {pipeline.reject_count}"
            ),
            f"Check: unique jobs = KEEP + REVIEW + REJECT = {classified}",
        ]
    )


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
        enrich_opportunities(ingestion.opportunities),
        create_daniel_profile(),
    )

    print("Greenhouse public board")
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
