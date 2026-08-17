"""Consulta manual e controlada do JSON feed público do RemoteOK."""

from .enrichment import enrich_opportunities
from .ingestion import RemoteOKJobAdapter, ingest_batch
from .pipeline import process_opportunities
from .profiles import create_daniel_profile
from .reporting import format_counts, format_warning_summary
from .sources import RemoteOKJobSource


def main() -> None:
    source_result = RemoteOKJobSource().fetch()
    if not source_result.success:
        raise SystemExit(
            source_result.message or f"RemoteOK failed: {source_result.status.value}"
        )
    ingestion = ingest_batch(source_result.records, RemoteOKJobAdapter())
    pipeline = process_opportunities(
        enrich_opportunities(ingestion.opportunities), create_daniel_profile()
    )
    print("RemoteOK JSON feed")
    print(format_counts(len(source_result.records), ingestion, pipeline))
    if ingestion.warnings:
        print("\n" + format_warning_summary(ingestion))
    print("\nTop opportunities:")
    for item in pipeline.ranked_opportunities[:10]:
        print(
            f"- {item.normalized_job.company} | {item.normalized_job.role} "
            f"| {item.normalized_job.location} | Score {item.match_score} "
            f"| {item.retention_decision.value}"
        )


if __name__ == "__main__":
    main()
