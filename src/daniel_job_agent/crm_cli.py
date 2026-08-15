"""CLI local para consultar e editar o CRM armazenado em SQLite."""

import argparse
from datetime import date

from .crm import CRMRecordNotFound, CRMValidationError, LocalCRM, records_to_table
from .models import ApplicationStatus
from .repository import DEFAULT_DATABASE_PATH, JobRepository
from .rules import RetentionDecision


def _date_argument(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected date in YYYY-MM-DD format") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the local job CRM")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List stored opportunities")
    list_parser.add_argument("--db", default=str(DEFAULT_DATABASE_PATH))
    list_parser.add_argument("--status", choices=[item.value for item in ApplicationStatus])
    list_parser.add_argument("--decision", choices=[item.value for item in RetentionDecision])
    list_parser.add_argument("--source")
    list_parser.add_argument("--minimum-score", type=int)
    list_parser.add_argument("--still-open", choices=("true", "false"))
    list_parser.add_argument("--order", choices=("default", "newest"), default="default")

    update_parser = subparsers.add_parser("update", help="Update manual CRM fields")
    update_parser.add_argument("internal_id", type=int)
    update_parser.add_argument("--db", default=str(DEFAULT_DATABASE_PATH))
    update_parser.add_argument("--status", choices=[item.value for item in ApplicationStatus])
    update_parser.add_argument("--notes")
    update_parser.add_argument("--recruiter-name")
    update_parser.add_argument("--recruiter-email")
    update_parser.add_argument("--applied-date", type=_date_argument)
    update_parser.add_argument("--next-step")
    update_parser.add_argument("--next-step-date", type=_date_argument)

    preview = subparsers.add_parser("export-preview", help="Preview tabular CRM data")
    preview.add_argument("--db", default=str(DEFAULT_DATABASE_PATH))
    preview.add_argument("--limit", type=int, default=5)
    return parser


def _print_list(crm: LocalCRM, args: argparse.Namespace) -> None:
    still_open = None
    if args.still_open is not None:
        still_open = args.still_open == "true"
    records = crm.list_records(
        application_status=args.status,
        retention_decision=args.decision,
        still_open=still_open,
        source=args.source,
        minimum_score=args.minimum_score,
        order=args.order,
    )
    print("ID | Company | Role | Score | Decision | Application Status")
    for item in records:
        print(
            f"{item.internal_id} | {item.company} | {item.role} | "
            f"{item.match_score} | {item.retention_decision.value} | "
            f"{item.application_status.value}"
        )


def _update(crm: LocalCRM, args: argparse.Namespace) -> None:
    option_to_field = {
        "status": "application_status",
        "notes": "notes",
        "recruiter_name": "recruiter_name",
        "recruiter_email": "recruiter_email",
        "applied_date": "applied_date",
        "next_step": "next_step",
        "next_step_date": "next_step_date",
    }
    changes = {
        field: getattr(args, option)
        for option, field in option_to_field.items()
        if getattr(args, option) is not None
    }
    if not changes:
        raise CRMValidationError("Provide at least one manual field to update")
    record = crm.update_manual_fields(args.internal_id, **changes)
    print(f"Updated CRM record {record.internal_id}: {record.application_status.value}")


def _preview(crm: LocalCRM, limit: int) -> None:
    if limit < 0:
        raise CRMValidationError("limit cannot be negative")
    table = records_to_table(crm.list_records()[:limit])
    print("Headers:")
    print(" | ".join(table.headers))
    print("Rows:")
    for row in table.rows:
        print(" | ".join("" if value is None else str(value) for value in row))


def main() -> None:
    args = build_parser().parse_args()
    try:
        with JobRepository(args.db) as repository:
            crm = LocalCRM(repository)
            if args.command == "list":
                _print_list(crm, args)
            elif args.command == "update":
                _update(crm, args)
            else:
                _preview(crm, args.limit)
    except (CRMValidationError, CRMRecordNotFound) as exc:
        raise SystemExit(f"Error: {exc}") from exc


if __name__ == "__main__":
    main()
