"""Consulta manual explícita do RSS público Sales and Marketing do WWR."""

from .enrichment import enrich_opportunities
from .ingestion import WeWorkRemotelyJobAdapter, ingest_batch
from .pipeline import process_opportunities
from .profiles import create_daniel_profile
from .reporting import format_counts, format_warning_summary
from .sources import WeWorkRemotelyJobSource


def main() -> None:
    source_result = WeWorkRemotelyJobSource().fetch()
    if not source_result.success:
        print(f"Source error: {source_result.message}")
        return
    ingestion = ingest_batch(source_result.records, WeWorkRemotelyJobAdapter())
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
