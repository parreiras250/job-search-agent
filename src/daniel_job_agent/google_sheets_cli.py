"""CLI push-only do CRM SQLite para uma spreadsheet existente."""

import argparse
from pathlib import Path

from .google_sheets import (
    GoogleSheetsConfig,
    pull_manual_fields_from_google_sheets,
    push_crm_to_google_sheets,
)
from .repository import DEFAULT_DATABASE_PATH, JobRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Push and pull manual CRM data with Google Sheets"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    def add_shared_arguments(command: argparse.ArgumentParser) -> None:
        command.add_argument("--db", default=str(DEFAULT_DATABASE_PATH))
        command.add_argument("--spreadsheet-id", required=True)
        command.add_argument("--sheet-name", default="Job CRM")
        command.add_argument(
            "--credentials", type=Path, default=Path("credentials.json")
        )
        command.add_argument("--token", type=Path, default=Path("token.json"))

    push = subparsers.add_parser(
        "push", help="Export SQLite CRM while preserving Sheet manual fields"
    )
    add_shared_arguments(push)
    pull = subparsers.add_parser(
        "pull", help="Import only manual CRM fields from Google Sheets"
    )
    add_shared_arguments(pull)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = GoogleSheetsConfig(
        spreadsheet_id=args.spreadsheet_id,
        sheet_name=args.sheet_name,
        credentials_path=args.credentials,
        token_path=args.token,
    )
    with JobRepository(args.db) as repository:
        if args.command == "push":
            result = push_crm_to_google_sheets(repository, config)
            if not result.success:
                raise SystemExit(f"Google Sheets push failed: {result.error}")
            print(
                f"Google Sheets push completed: {result.rows_written} rows x "
                f"{result.columns_written} columns in '{result.sheet_name}'."
            )
        else:
            pull_result = pull_manual_fields_from_google_sheets(repository, config)
            print("Google Sheets pull completed")
            print(f"Rows read: {pull_result.rows_read}")
            print(f"Valid: {pull_result.rows_valid}")
            print(f"Updated: {pull_result.rows_updated}")
            print(f"Unchanged: {pull_result.rows_unchanged}")
            print(f"Skipped: {pull_result.rows_skipped}")
            print(f"Errors: {pull_result.rows_errored}")
            for issue in pull_result.issues[:10]:
                location = f"row {issue.row_number}" if issue.row_number else "sheet"
                print(f"- {location}: {issue.message}")
            if not pull_result.success:
                raise SystemExit("Google Sheets pull completed with errors")


if __name__ == "__main__":
    main()
