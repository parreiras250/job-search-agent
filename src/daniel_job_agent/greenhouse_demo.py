"""Consulta manual e explícita de um único board público do Greenhouse."""

import argparse

from .enrichment import enrich_opportunities
from .discovery import MultiSourceDiscovery
from .ingestion import GreenhouseJobAdapter, ingest_batch
from .pipeline import process_opportunities
from .profiles import create_daniel_profile
from .reporting import format_counts
from .sources import GreenhouseJobSource
from .repository import JobRepository, sync_opportunities
from .source_registry import (
    GreenhouseTenantConfig,
    SourceRegistry,
    create_greenhouse_pilot_definitions,
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

    config = GreenhouseTenantConfig(
        company_key="manual-pilot",
        company_name=args.company_name,
        board_token=args.board_token,
    )
    definition = create_greenhouse_pilot_definitions([config])[0]
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
    print(f"Source ID: {definition.source_id}")
    print(f"Source family: {definition.source_family}")
    print(f"Source instance: {definition.source_instance}")
    print(
        "Lifecycle authority: "
        f"{definition.capabilities.lifecycle_authority.value}"
    )
    print(format_counts(len(source_result.records), ingestion, pipeline))
    print("\nTop opportunities:")
    for item in pipeline.ranked_opportunities[:10]:
        job = item.normalized_job
        print(
            f"{item.rank}. {job.role} — {job.company} "
            f"| Score {item.match_score} | {item.retention_decision.value}"
        )

    # A mesma resposta já obtida é reutilizada; esta integração não faz um
    # segundo request e demonstra a criação das observations em memória.
    class FetchedSource:
        def fetch(self):
            return source_result

    registry_definition = create_greenhouse_pilot_definitions(
        [config], source_overrides={definition.source_id: FetchedSource()}
    )[0]
    discovery = MultiSourceDiscovery(
        registry=SourceRegistry([registry_definition])
    ).run(create_daniel_profile())
    with JobRepository(":memory:") as repository:
        sync = sync_opportunities(discovery.pipeline, repository)
        print(
            f"Persisted opportunities: {repository.count()} | "
            f"Source observations: {repository.observation_count()} | "
            f"Observations created: {sync.observations_created}"
        )


if __name__ == "__main__":
    main()
