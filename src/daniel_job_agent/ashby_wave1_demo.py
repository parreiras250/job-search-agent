"""Validação manual e limitada dos company boards Ashby da Wave 1."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Mapping

from .enrichment import enrich_opportunities
from .ingestion import ingest_batch
from .pipeline import PipelineResult, process_opportunities
from .profiles import create_daniel_profile
from .source_registry import AshbyTenantConfig, create_ashby_definitions
from .sources import AshbyJobSource, SourceResult, SourceStatus


WAVE1_TENANTS = (
    AshbyTenantConfig(
        "elevenlabs", "ElevenLabs", "elevenlabs", employer_name="ElevenLabs"
    ),
    AshbyTenantConfig("replit", "Replit", "replit", employer_name="Replit"),
)


def _offline_records(tenant_key: str) -> list[Mapping[str, object]]:
    fixture = (
        Path(__file__).parents[2]
        / "tests"
        / "fixtures"
        / f"ashby_{tenant_key}_jobs.json"
    )
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    return payload["jobs"]


def _format_tenant(
    config: AshbyTenantConfig,
    source_result: SourceResult,
) -> str:
    lines = [f"Company: {config.employer_name}"]
    if not source_result.success:
        lines.extend(["Status: FAILED", f"Source error: {source_result.message}"])
        return "\n".join(lines)

    definition = create_ashby_definitions([config])[0]
    ingestion = ingest_batch(source_result.records, definition.adapter_factory())
    for job in ingestion.opportunities:
        job.source_id = definition.source_id
        job.source_family = definition.source_family
        job.source_instance = definition.source_instance
        job.source_type = definition.source_type.value
        job.lifecycle_authority = definition.capabilities.lifecycle_authority.value
    pipeline: PipelineResult = process_opportunities(
        enrich_opportunities(ingestion.opportunities), create_daniel_profile()
    )
    lines.extend([
        f"Jobs received: {len(source_result.records)}",
        f"Jobs converted: {ingestion.converted_count}",
        f"Warnings: {ingestion.warning_count}",
        f"Errors: {ingestion.error_count}",
        f"Unique jobs: {pipeline.unique_opportunities}",
        f"KEEP: {pipeline.keep_count}",
        f"REVIEW: {pipeline.review_count}",
        f"REJECT: {pipeline.reject_count}",
    ])
    if ingestion.warnings:
        lines.append("Warning summary:")
        for (field, message), count in sorted(Counter(
            (warning.field, warning.message) for warning in ingestion.warnings
        ).items()):
            lines.append(f"- {field}: {message}: {count}")
    lines.append("Top relevant opportunities:")
    relevant = [
        item for item in pipeline.ranked_opportunities
        if item.retention_decision.value in {"KEEP", "REVIEW"}
    ][:5]
    if not relevant:
        lines.append("- None")
    for item in relevant:
        job = item.normalized_job
        lines.extend([
            f"- {job.role} — {job.company}",
            f"  Location: {job.location} | Remote: {job.remote}",
            f"  Career Fit: {item.match_score} | Eligibility: {item.eligibility.value}",
            f"  Timezone Fit: {item.timezone_compatibility.value} | Decision: {item.retention_decision.value}",
        ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate ElevenLabs and Replit through the generic Ashby adapter."
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="Use the small local fixtures and make no network requests.",
    )
    args = parser.parse_args()

    print("Ashby Wave 1 — ElevenLabs + Replit")
    for config in WAVE1_TENANTS:
        if args.offline:
            result = SourceResult(
                SourceStatus.SUCCESS, list(_offline_records(config.tenant_key))
            )
        else:
            result = AshbyJobSource(config.board_name).fetch()
        print()
        print(_format_tenant(config, result))


if __name__ == "__main__":
    main()
