"""Formatação compartilhada das contagens das demonstrações reais."""

from collections import Counter

from .ingestion import BatchIngestionResult
from .pipeline import PipelineResult


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


def format_warning_summary(ingestion: BatchIngestionResult) -> str:
    """Agrupa warnings equivalentes sem exibir registros ou valores grandes."""

    if not ingestion.warnings:
        return ""
    counts = Counter(
        (warning.field, warning.message) for warning in ingestion.warnings
    )
    lines = ["Warning summary:"]
    lines.extend(
        f"- {field}: {message}: {count}"
        for (field, message), count in sorted(counts.items())
    )
    return "\n".join(lines)
