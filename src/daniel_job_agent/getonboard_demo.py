"""Consulta manual de uma página da busca pública do Get on Board."""

import argparse
import json
from collections.abc import Mapping, Sequence

from .enrichment import enrich_opportunities
from .ingestion import GetOnBoardJobAdapter, IngestionResult, ingest_batch
from .pipeline import process_opportunities
from .profiles import create_daniel_profile
from .reporting import format_counts, format_warning_summary
from .sources import GetOnBoardJobSource


_MAX_SAMPLE_CHARACTERS = 180


def _safe_sample(value: object) -> str:
    """Resume estruturas sem despejar textos ou payloads extensos."""

    if isinstance(value, str):
        rendered = repr(value)
    else:
        try:
            rendered = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            rendered = repr(value)
    if len(rendered) > _MAX_SAMPLE_CHARACTERS:
        return rendered[: _MAX_SAMPLE_CHARACTERS - 1] + "…"
    return rendered


def _record_fields(record: Mapping[str, object]) -> dict[str, object]:
    """Expõe paths seguros do envelope JSON:API sem normalizar seu shape."""

    fields = {key: value for key, value in record.items() if key != "description"}
    attributes = record.get("attributes")
    if isinstance(attributes, Mapping):
        fields.update(
            {
                f"attributes.{key}": value
                for key, value in attributes.items()
                if key != "description"
            }
        )
    relationships = record.get("relationships")
    if isinstance(relationships, Mapping):
        for key in ("company", "tags"):
            if key in relationships:
                fields[f"relationships.{key}"] = relationships[key]
    return fields


def _matching_fields(
    fields: Mapping[str, object], names: Sequence[str], fragments: Sequence[str] = ()
) -> list[tuple[str, object]]:
    exact = {name.casefold() for name in names}
    matches = []
    for path, value in fields.items():
        key = path.rsplit(".", 1)[-1].casefold()
        if key in exact or any(fragment in key for fragment in fragments):
            matches.append((path, value))
    return matches


def _format_values(label: str, values: list[tuple[str, object]]) -> list[str]:
    if not values:
        return [f"{label}: not present"]
    lines = [f"{label}:"]
    for path, value in values:
        lines.append(
            f"  - {path}: type={type(value).__name__}; sample={_safe_sample(value)}"
        )
    return lines


def format_getonboard_payload_shape_debug(
    records: Sequence[Mapping[str, object]],
    results: Sequence[IngestionResult],
    *,
    max_successes: int = 3,
    max_failures: int = 3,
) -> str:
    """Formata uma amostra estrutural limitada, sem descrição ou payload inteiro."""

    selected: list[tuple[int, Mapping[str, object], IngestionResult]] = []
    success_count = failure_count = 0
    for index, (record, result) in enumerate(zip(records, results), start=1):
        if result.success and success_count < max_successes:
            selected.append((index, record, result))
            success_count += 1
        elif not result.success and failure_count < max_failures:
            selected.append((index, record, result))
            failure_count += 1
        if success_count >= max_successes and failure_count >= max_failures:
            break

    lines = [
        "Get on Board payload shape debug",
        f"Selected: {success_count} converted | {failure_count} ingestion failures",
    ]
    for index, record, result in selected:
        fields = _record_fields(record)
        title_values = _matching_fields(fields, ("title", "headline", "name"))
        identifier = record.get("id")
        title = title_values[0][1] if title_values else None
        lines.extend(
            [
                "",
                f"Job {index} ({'CONVERTED' if result.success else 'FAILED'})",
                f"top-level keys: {sorted(record.keys())}",
                f"id: type={type(identifier).__name__}; sample={_safe_sample(identifier)}",
                f"identifier/title: {_safe_sample(identifier)} | {_safe_sample(title)}",
            ]
        )
        lines.extend(_format_values("title/headline fields", title_values))
        lines.extend(
            _format_values(
                "company fields",
                _matching_fields(fields, ("company", "company_name", "organization")),
            )
        )
        lines.extend(
            _format_values(
                "date fields",
                _matching_fields(
                    fields,
                    ("published_at", "created_at", "date_posted", "published", "created"),
                    ("date", "publish", "created"),
                ),
            )
        )
        lines.extend(
            _format_values(
                "employment type fields",
                _matching_fields(fields, ("employment_type", "modality", "job_type")),
            )
        )
        lines.extend(
            _format_values(
                "seniority/job level fields",
                _matching_fields(fields, ("seniority", "job_level", "level")),
            )
        )
        lines.extend(
            _format_values(
                "remote/location fields",
                _matching_fields(
                    fields,
                    ("remote", "remote_modality", "location", "allowed_locations"),
                    ("remote", "location"),
                ),
            )
        )
        lines.extend(
            _format_values(
                "salary fields",
                _matching_fields(fields, (), ("salary", "compensation")),
            )
        )
        lines.extend(
            _format_values("tags fields", _matching_fields(fields, ("tags", "tag")))
        )
        if result.error is not None:
            lines.append(f"ingestion error: {result.error.message}")
            lines.append(
                "failure field: "
                + (
                    result.error.message.split(":", 1)[-1].strip()
                    if ":" in result.error.message
                    else "see adapter validation error above"
                )
            )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--debug-payload-shape",
        action="store_true",
        help="show a small structural sample of records and ingestion failures",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = build_parser().parse_args(argv)
    source = GetOnBoardJobSource()
    source_result = source.fetch()
    if not source_result.success:
        raise SystemExit(
            source_result.message
            or f"Get on Board failed: {source_result.status.value}"
        )
    ingestion = ingest_batch(source_result.records, GetOnBoardJobAdapter())
    if arguments.debug_payload_shape:
        print(
            format_getonboard_payload_shape_debug(
                source_result.records, ingestion.results
            )
        )
        return
    pipeline = process_opportunities(
        enrich_opportunities(ingestion.opportunities), create_daniel_profile()
    )
    print("Get on Board public API")
    print(f"Query: {source.query} | Page: {source.page} | Per page: {source.per_page}")
    print(format_counts(len(source_result.records), ingestion, pipeline))
    if ingestion.warnings:
        print("\n" + format_warning_summary(ingestion))
    raw_attributes_by_id = {
        str(record.get("id")): record.get("attributes")
        for record in source_result.records
        if isinstance(record, dict) and isinstance(record.get("attributes"), dict)
    }
    print("\nTop opportunities:")
    for item in pipeline.ranked_opportunities[:10]:
        attributes = raw_attributes_by_id.get(
            item.normalized_job.external_id or "", {}
        )
        attributes = attributes if isinstance(attributes, dict) else {}
        salary = "Unknown"
        if attributes.get("min_salary") is not None or attributes.get("max_salary") is not None:
            salary = (
                f"{attributes.get('salary_currency') or ''} "
                f"{attributes.get('min_salary') or '?'}–{attributes.get('max_salary') or '?'} "
                f"{attributes.get('salary_period') or ''}"
            ).strip()
        print(
            f"- {item.normalized_job.company} | {item.normalized_job.role} "
            f"| {item.normalized_job.location} | Remote modality: "
            f"{attributes.get('remote_modality') or 'Unknown'} | Salary: {salary} "
            f"| Score {item.match_score} | {item.retention_decision.value}"
        )


if __name__ == "__main__":
    main()
