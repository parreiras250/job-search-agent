"""CLI principal para executar discovery broad e persistir o resultado."""

import argparse

from .agent import DanielJobAgent
from .reporting import format_agent_run
from .repository import DEFAULT_DATABASE_PATH, JobRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Daniel Job Agent")
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DATABASE_PATH),
        help="SQLite database path (default: data/job_agent.db)",
    )
    parser.add_argument(
        "--mode",
        choices=("broad",),
        default="broad",
        help="Discovery mode; broad is the calibrated operational default",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    with JobRepository(args.db) as repository:
        result = DanielJobAgent(repository).run()
    print(format_agent_run(result))


if __name__ == "__main__":
    main()
