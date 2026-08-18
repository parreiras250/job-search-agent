"""Consulta manual do tenant LatamCent pela API pública do Ashby."""

from collections import Counter

from .enrichment import enrich_opportunities
from .ingestion import AshbyJobAdapter, ingest_batch
from .pipeline import process_opportunities
from .profiles import create_daniel_profile
from .source_registry import AshbyTenantConfig, create_ashby_definitions
from .sources import AshbyJobSource


def main() -> None:
    config = AshbyTenantConfig(
        tenant_key="latamcent",
        publisher_name="LatamCent",
        board_name="latamcent",
    )
    definition = create_ashby_definitions([config])[0]
    source_result = AshbyJobSource(config.board_name).fetch()
    if not source_result.success:
        print(f"Source error: {source_result.message}")
        return

    ingestion = ingest_batch(
        source_result.records,
        AshbyJobAdapter(config.publisher_name, employer_name=config.employer_name),
    )
    for job in ingestion.opportunities:
        job.source_id = definition.source_id
        job.source_family = definition.source_family
        job.source_instance = definition.source_instance
        job.source_type = definition.source_type.value
        job.lifecycle_authority = definition.capabilities.lifecycle_authority.value
    pipeline = process_opportunities(
        enrich_opportunities(ingestion.opportunities), create_daniel_profile()
    )
    workplaces = {
        record.get("jobUrl"): record.get("workplaceType")
        for record in source_result.records
    }

    print("LatamCent via Ashby Public Job Posting API")
    print(f"Jobs received: {len(source_result.records)}")
    print(f"Jobs converted: {ingestion.converted_count}")
    print(f"Warnings: {ingestion.warning_count}")
    if ingestion.warnings:
        print("Warning summary:")
        for (field, message), count in sorted(Counter(
            (item.field, item.message) for item in ingestion.warnings
        ).items()):
            print(f"- {field}: {message}: {count}")
    print(f"Ingestion errors: {ingestion.error_count}")
    print(f"Unique jobs: {pipeline.unique_opportunities}")
    print(f"Duplicates: {pipeline.duplicates_detected}")
    print(f"KEEP: {pipeline.keep_count}")
    print(f"REVIEW: {pipeline.review_count}")
    print(f"REJECT: {pipeline.reject_count}")
    print("\nTop opportunities:")
    for item in pipeline.ranked_opportunities[:10]:
        job = item.normalized_job
        workplace = workplaces.get(job.job_url) or "Unknown"
        print(
            f"{item.rank}. {job.role} — {job.company} "
            f"| Career Fit {item.match_score} | Eligibility {item.eligibility.value} "
            f"| {item.retention_decision.value}"
        )
        print(
            f"   Publisher/source: LatamCent / Ashby | Location: {job.location} "
            f"| Remote: {job.remote} | Workplace: {workplace}"
        )


if __name__ == "__main__":
    main()
