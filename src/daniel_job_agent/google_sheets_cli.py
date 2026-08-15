"""CLI push-only do CRM SQLite para uma spreadsheet existente."""

import argparse
from pathlib import Path

from .google_sheets import GoogleSheetsConfig, push_crm_to_google_sheets
from .repository import DEFAULT_DATABASE_PATH, JobRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Push the local CRM to Google Sheets")
    subparsers = parser.add_subparsers(dest="command", required=True)
    push = subparsers.add_parser("push", help="Overwrite one tab from the SQLite CRM")
    push.add_argument("--db", default=str(DEFAULT_DATABASE_PATH))
    push.add_argument("--spreadsheet-id", required=True)
    push.add_argument("--sheet-name", default="Job CRM")
    push.add_argument("--credentials", type=Path, default=Path("credentials.json"))
    push.add_argument("--token", type=Path, default=Path("token.json"))
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
        result = push_crm_to_google_sheets(repository, config)
    if not result.success:
        raise SystemExit(f"Google Sheets push failed: {result.error}")
    print(
        f"Google Sheets push completed: {result.rows_written} rows x "
        f"{result.columns_written} columns in '{result.sheet_name}'."
    )


if __name__ == "__main__":
    main()
