"""Formatação compartilhada das contagens das demonstrações reais."""

from collections import Counter
from typing import TYPE_CHECKING

from .ingestion import BatchIngestionResult
from .pipeline import PipelineResult

if TYPE_CHECKING:
    from .agent import AgentRunResult


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


def format_agent_run(result: "AgentRunResult") -> str:
    """Formata uma execução completa sem repetir regras do pipeline."""

    lines = [
        "Daniel Job Agent",
        "",
        "## Discovery",
        (
            f"Sources: {len(result.sources_succeeded)}/"
            f"{len(result.sources_attempted)} succeeded"
        ),
        f"Received: {result.jobs_received}",
        f"Converted: {result.jobs_converted}",
        f"Unique: {result.unique_opportunities}",
        f"Duplicates: {result.discovery_duplicates}",
        f"KEEP: {result.keep}",
        f"REVIEW: {result.review}",
        f"REJECT: {result.reject}",
    ]
    if result.sources_failed:
        lines.append(f"Failed sources: {', '.join(result.sources_failed)}")
    lines.extend(
        [
            "",
            "## Persistence",
            f"NEW: {result.new}",
            f"EXISTING: {result.existing}",
            f"UPDATED: {result.updated}",
            f"Errors: {result.persistence_errors}",
            f"Total stored: {result.total_stored}",
            f"Database: {result.database_path}",
            "",
            "## Lifecycle",
            f"Seen open: {result.lifecycle.open_seen}",
            f"Misses recorded: {result.lifecycle.misses_recorded}",
            f"Possibly closed: {result.lifecycle.possibly_closed}",
            f"Newly closed: {result.lifecycle.newly_closed}",
            f"Reopened: {result.lifecycle.reopened}",
            f"Unchanged lifecycle: {result.lifecycle.unchanged_lifecycle}",
            "",
            "## Top new opportunities",
        ]
    )
    if not result.top_new_opportunities:
        lines.append("No new KEEP or REVIEW opportunities.")
    for position, item in enumerate(result.top_new_opportunities, start=1):
        job = item.normalized_job
        lines.extend(
            [
                f"{position}. {job.role} — {job.company}",
                f"   Score: {item.match_score}",
                f"   {item.retention_decision.value}",
                f"   URL: {job.job_url}",
            ]
        )
    return "\n".join(lines)
