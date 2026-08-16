"""Consulta simples dos relatórios Markdown e do histórico SQLite."""

from __future__ import annotations

import argparse
from pathlib import Path

from .repository import JobRepository
from .reports import find_report_for_run
from .scheduler import SchedulerConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read Daniel Job Agent weekly reports")
    parser.add_argument(
        "--project-dir", type=Path, default=Path.cwd(),
        help="Project directory (default: current directory)",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("latest", help="Print reports/latest.md")
    history = commands.add_parser("history", help="List run metadata from SQLite")
    history.add_argument("--limit", type=int, default=10)
    show = commands.add_parser("show", help="Print the report for one run ID")
    show.add_argument("run_id", type=int)
    return parser


def format_history(repository: JobRepository, *, limit: int) -> str:
    runs = repository.list_agent_runs(limit=limit)
    if not runs:
        return "No agent run history is available."
    lines = ["Run history"]
    for run in runs:
        sheets = "disabled" if run.sheets_sync_success is None else (
            "success" if run.sheets_sync_success else "failed"
        )
        lines.append(
            f"{run.started_at.astimezone().strftime('%Y-%m-%d %H:%M')} | "
            f"Run {run.run_id} | {run.status} | New: {run.new_count} | "
            f"Updated: {run.updated_count} | Possibly closed: "
            f"{run.possibly_closed} | Closed: {run.newly_closed} | Sheets: {sheets}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = SchedulerConfig.from_project(args.project_dir)
    if args.command == "latest":
        path = config.reports_dir / "latest.md"
        if not path.is_file():
            print("No weekly report is available yet.")
            return 1
        print(path.read_text(encoding="utf-8"), end="")
        return 0
    if args.command == "show":
        path = find_report_for_run(config.reports_dir, args.run_id)
        if path is None:
            print(f"No report was found for run {args.run_id}.")
            return 1
        print(path.read_text(encoding="utf-8"), end="")
        return 0
    if not config.database_path.is_file():
        print("No agent run history is available.")
        return 1
    try:
        with JobRepository(config.database_path) as repository:
            print(format_history(repository, limit=args.limit))
    except ValueError as exc:
        print(f"Cannot show history: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
