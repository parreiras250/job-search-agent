"""CLI não interativa para administrar o Company Registry local."""

from __future__ import annotations

import argparse

from .repository import DEFAULT_DATABASE_PATH, JobRepository


def _add_db_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default=str(DEFAULT_DATABASE_PATH))


def _print_company(company: object) -> None:
    last_success = getattr(company, "last_success_at")
    print(f"Key: {getattr(company, 'company_key')}")
    print(f"Company: {getattr(company, 'company_name')}")
    print(f"ATS: {getattr(company, 'ats_family')}")
    print(f"Identifier: {getattr(company, 'ats_identifier')}")
    print(f"Enabled: {getattr(company, 'enabled')}")
    print(f"Priority: {getattr(company, 'priority')}")
    print(f"Last success: {last_success.isoformat() if last_success else '-'}")
    print(f"Failures: {getattr(company, 'failure_count')}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage tracked ATS companies")
    commands = parser.add_subparsers(dest="command", required=True)

    listing = commands.add_parser("list")
    _add_db_argument(listing)

    add = commands.add_parser("add")
    _add_db_argument(add)
    add.add_argument("--key", required=True)
    add.add_argument("--name", required=True)
    add.add_argument("--ats", required=True)
    add.add_argument("--identifier", required=True)
    add.add_argument("--priority", type=int, default=100)
    add.add_argument("--careers-url")
    add.add_argument("--notes")

    show = commands.add_parser("show")
    show.add_argument("key")
    _add_db_argument(show)

    for name in ("enable", "disable"):
        command = commands.add_parser(name)
        command.add_argument("key")
        _add_db_argument(command)

    update = commands.add_parser("update")
    update.add_argument("key")
    _add_db_argument(update)
    update.add_argument("--name")
    update.add_argument("--ats")
    update.add_argument("--identifier")
    update.add_argument("--priority", type=int)
    update.add_argument("--careers-url")
    update.add_argument("--notes")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    with JobRepository(args.db) as repository:
        if args.command == "list":
            print("Key | Company | ATS | Identifier | Enabled | Priority | Last Success | Failures")
            for company in repository.list_companies():
                success = company.last_success_at.isoformat() if company.last_success_at else "-"
                print(
                    f"{company.company_key} | {company.company_name} | "
                    f"{company.ats_family} | {company.ats_identifier} | "
                    f"{company.enabled} | {company.priority} | {success} | "
                    f"{company.failure_count}"
                )
            return
        if args.command == "add":
            company = repository.add_company(
                args.key, args.name, args.ats, args.identifier,
                priority=args.priority, careers_url=args.careers_url,
                notes=args.notes,
            )
        elif args.command == "show":
            company = repository.get_company(args.key)
            if company is None:
                raise SystemExit(f"Unknown company: {args.key}")
        elif args.command == "enable":
            company = repository.enable_company(args.key)
        elif args.command == "disable":
            company = repository.disable_company(args.key)
        else:
            company = repository.update_company(
                args.key, company_name=args.name, ats_family=args.ats,
                ats_identifier=args.identifier, priority=args.priority,
                careers_url=args.careers_url, notes=args.notes,
            )
        _print_company(company)


if __name__ == "__main__":
    main()
