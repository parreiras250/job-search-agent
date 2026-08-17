"""Consulta manual e controlada da API pública Himalayas."""

import argparse
import json
from collections.abc import Mapping

from .enrichment import enrich_opportunities
from .ingestion import HimalayasJobAdapter, ingest_batch
from .pipeline import process_opportunities
from .profiles import create_daniel_profile
from .reporting import format_counts, format_warning_summary
from .sources import HimalayasJobSource


def _truncated_json(value: object, *, limit: int = 240) -> str:
    try:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        rendered = repr(value)
    return rendered if len(rendered) <= limit else rendered[: limit - 1] + "…"


def format_payload_shape(
    records: list[Mapping[str, object]], *, max_jobs: int = 3
) -> str:
    """Resume somente a estrutura dos campos geográficos, nunca o payload inteiro."""

    lines = ["Payload shape debug (maximum 3 jobs)"]
    for index, record in enumerate(records[: min(max_jobs, 3)], start=1):
        lines.extend(["", f"Job {index}"])
        for field in ("locationRestrictions", "timezoneRestrictions"):
            value = record.get(field)
            lines.append(f"{field} type: {type(value).__name__}")
            lines.append(f"{field} sample: {_truncated_json(value)}")
            if isinstance(value, list) and value:
                first = value[0]
                lines.append(f"{field} first item type: {type(first).__name__}")
                if isinstance(first, dict):
                    lines.append(
                        f"{field} first item keys: {sorted(map(str, first.keys()))}"
                    )
                lines.append(
                    f"{field} first item sample: {_truncated_json(first, limit=160)}"
                )
    return "\n".join(lines)


def format_timezone_restriction(value: int | float | str) -> str:
    """Apresenta offsets numéricos sem alterar o valor persistido."""

    if isinstance(value, str):
        return value
    total_minutes = round(abs(float(value)) * 60)
    hours, minutes = divmod(total_minutes, 60)
    sign = "+" if value >= 0 else "-"
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run one Himalayas sales search")
    parser.add_argument(
        "--debug-payload-shape",
        action="store_true",
        help="print a safe structural sample for at most three jobs",
    )
    args = parser.parse_args(argv)
    source = HimalayasJobSource(q="sales", sort="recent", page=1)
    result = source.fetch()
    if not result.success:
        raise SystemExit(result.message or f"Himalayas failed: {result.status.value}")
    if args.debug_payload_shape:
        print(format_payload_shape(result.records))
        print()
    ingestion = ingest_batch(result.records, HimalayasJobAdapter())
    pipeline = process_opportunities(
        enrich_opportunities(ingestion.opportunities), create_daniel_profile()
    )
    print("Himalayas Remote Jobs API")
    print("Query: sales | Sort: recent | Page: 1")
    print(format_counts(len(result.records), ingestion, pipeline))
    if ingestion.warnings:
        print("\n" + format_warning_summary(ingestion))
    print("\nTop opportunities:")
    for item in pipeline.ranked_opportunities[:10]:
        location_text = " | ".join(
            restriction.name
            for restriction in (item.normalized_job.location_restrictions or [])
        ) or "Worldwide"
        timezone_text = " | ".join(
            format_timezone_restriction(value)
            for value in (item.normalized_job.timezone_restrictions or [])
        ) or "All timezones"
        print(
            f"- {item.normalized_job.company} | {item.normalized_job.role} "
            f"| Location restrictions: {location_text} "
            f"| Timezones: {timezone_text} "
            f"| Score {item.match_score} | {item.retention_decision.value}"
        )


if __name__ == "__main__":
    main()
