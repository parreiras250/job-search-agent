"""CLI amigável para instalar, pausar e inspecionar a automação semanal."""

from __future__ import annotations

import argparse
from pathlib import Path

from .repository import JobRepository
from .scheduler import LaunchAgentController, SchedulerConfig
from .weekly_run import AlreadyRunningError, format_weekly_outcome, run_weekly


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage the Daniel Job Agent weekly macOS LaunchAgent"
    )
    parser.add_argument(
        "--project-dir", type=Path, default=Path.cwd(),
        help="Project directory (default: current directory)",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("install", help="Create and load the weekly LaunchAgent")
    commands.add_parser("status", help="Show installation, schedule and last run")
    commands.add_parser("start", help="Resume an installed weekly LaunchAgent")
    commands.add_parser("stop", help="Pause without deleting data or the plist")
    commands.add_parser("run-now", help="Run the same weekly workflow immediately")
    commands.add_parser("uninstall", help="Unload and remove only the generated plist")
    return parser


def format_status(config: SchedulerConfig, loaded: bool) -> str:
    lines = [
        f"Installed: {'yes' if config.plist_path.is_file() else 'no'}",
        f"Loaded/enabled: {'yes' if loaded else 'no'}",
        f"Schedule: {config.schedule.display()}",
        f"Project path: {config.project_dir}",
        f"Python path: {config.python_path}",
        f"Output log: {config.out_log}",
        f"Error log: {config.err_log}",
    ]
    if config.database_path.is_file():
        with JobRepository(config.database_path) as repository:
            last = repository.latest_agent_run()
        if last:
            sheets = "disabled" if last.sheets_sync_success is None else (
                "success" if last.sheets_sync_success else "failed"
            )
            lines.extend([
                "", "Last run:",
                last.started_at.astimezone().strftime("%Y-%m-%d %H:%M"),
                f"Status: {last.status}",
                f"New jobs: {last.new_count}",
                f"Updated: {last.updated_count}",
                f"Possibly closed: {last.possibly_closed}",
                f"Sheets sync: {sheets}",
            ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = SchedulerConfig.from_project(args.project_dir)
    controller = LaunchAgentController(config)
    try:
        if args.command == "install":
            controller.install()
            print(f"Installed: {config.plist_path}")
        elif args.command == "status":
            print(format_status(config, controller.is_loaded()))
        elif args.command == "start":
            controller.start()
            print("Weekly automation resumed; history and data were preserved.")
        elif args.command == "stop":
            controller.stop()
            print("Weekly automation paused; history and data were preserved.")
        elif args.command == "uninstall":
            controller.uninstall()
            print("LaunchAgent removed; database, tokens and logs were preserved.")
        else:
            outcome = run_weekly(config)
            print(format_weekly_outcome(outcome))
            return outcome.exit_code
    except (AlreadyRunningError, OSError, RuntimeError, ValueError) as exc:
        print(f"Scheduler command failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
