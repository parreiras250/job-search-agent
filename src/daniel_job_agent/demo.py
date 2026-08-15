"""Demonstração de ingestão local seguida pelo pipeline."""

from .demo_data import create_ingestion_demo_records
from .ingestion import (
    BatchIngestionResult,
    GenericJobAdapter,
    MockGreenhouseAdapter,
    MockLeverAdapter,
    combine_ingestion_batches,
    ingest_batch,
)
from .pipeline import PipelineResult, process_opportunities
from .profiles import create_daniel_profile


def format_demo(
    ingestion: BatchIngestionResult, pipeline: PipelineResult
) -> str:
    """Gera uma saída curta e legível, sem dependências externas."""

    lines = [
        "Daniel Job Agent — Local Demo",
        "",
        "Ingestion:",
        f"Raw records received: {ingestion.total_received}",
        f"Converted successfully: {ingestion.converted_count}",
        f"Warnings: {ingestion.warning_count}",
        f"Failed validation: {ingestion.error_count}",
        "",
    ]
    if ingestion.errors:
        lines.append("Conversion errors:")
        for error in ingestion.errors:
            lines.append(f"- Record {error.record_index}: {error.message}")
        lines.append("")
    if ingestion.warnings:
        lines.append("Conversion warnings:")
        for warning in ingestion.warnings:
            lines.append(
                f"- Record {warning.record_index}, {warning.field}: {warning.message}"
            )
        lines.append("")
    lines.extend(
        [
            "Pipeline:",
            f"Unique opportunities: {pipeline.unique_opportunities}",
            f"Duplicates detected: {pipeline.duplicates_detected}",
            f"KEEP: {pipeline.keep_count}",
            f"REVIEW: {pipeline.review_count}",
            f"REJECT: {pipeline.reject_count}",
            "",
            "Ranking:",
        ]
    )
    for item in pipeline.ranked_opportunities:
        job = item.normalized_job
        lines.extend(
            [
                f"{item.rank}. {job.role} — {job.company}",
                f"   Score: {item.match_score} | Decision: {item.retention_decision.value}",
            ]
        )
        if item.positive_reasons:
            lines.append(f"   Reason: {item.positive_reasons[0]}")
        if item.potential_gaps:
            lines.append(f"   Gap: {item.potential_gaps[0]}")
    return "\n".join(lines)


def main() -> None:
    records = create_ingestion_demo_records()
    ingestion = combine_ingestion_batches(
        [
            ingest_batch(records["generic"], GenericJobAdapter()),
            ingest_batch(records["greenhouse"], MockGreenhouseAdapter()),
            ingest_batch(records["lever"], MockLeverAdapter()),
        ]
    )
    pipeline = process_opportunities(
        ingestion.opportunities, create_daniel_profile()
    )
    print(format_demo(ingestion, pipeline))


if __name__ == "__main__":
    main()
