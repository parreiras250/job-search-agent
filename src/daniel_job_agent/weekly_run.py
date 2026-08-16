"""Entrypoint semanal: agente, Sheets opcional, histórico e lock local."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Callable

from .agent import AgentRunResult, DanielJobAgent
from .google_sheets import (
    GoogleSheetsConfig, authenticate_google_noninteractive,
    create_sheets_service, push_crm_to_google_sheets,
)
from .reporting import format_agent_run
from .repository import JobRepository
from .scheduler import SchedulerConfig


SUCCESS = 0
FAILURE = 1
PARTIAL_FAILURE = 2
MAX_LOG_BYTES = 5 * 1024 * 1024
KEPT_LOG_BYTES = 1024 * 1024


class AlreadyRunningError(RuntimeError):
    pass


class RunLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.acquired = False

    @staticmethod
    def _pid_running(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def __enter__(self) -> "RunLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as lock_file:
                    lock_file.write(str(os.getpid()))
                self.acquired = True
                return self
            except FileExistsError:
                try:
                    pid = int(self.path.read_text(encoding="utf-8").strip())
                except (OSError, ValueError):
                    pid = -1
                if pid > 0 and self._pid_running(pid):
                    raise AlreadyRunningError(f"Weekly run already active (PID {pid})")
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
        raise AlreadyRunningError("Could not safely acquire weekly run lock")

    def __exit__(self, *_: object) -> None:
        if self.acquired:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass


@dataclass(frozen=True, slots=True)
class WeeklyRunOutcome:
    exit_code: int
    status: str
    agent_result: AgentRunResult | None
    sheets_sync_success: bool | None
    error_summary: str | None


def prune_logs(config: SchedulerConfig) -> None:
    """Mantém apenas o trecho recente quando um log local passa de 5 MiB."""

    for path in (config.out_log, config.err_log):
        try:
            if path.stat().st_size > MAX_LOG_BYTES:
                with path.open("rb") as source:
                    source.seek(-KEPT_LOG_BYTES, os.SEEK_END)
                    recent = source.read()
                path.write_bytes(recent)
        except FileNotFoundError:
            continue


def _sheets_sync(repository: JobRepository, config: SchedulerConfig) -> tuple[bool | None, str | None]:
    if not config.sheets_enabled:
        return None, None
    sheets_config = GoogleSheetsConfig(
        spreadsheet_id=config.spreadsheet_id or "",
        sheet_name=config.sheet_name,
        credentials_path=config.credentials_path,
        token_path=config.token_path,
    )
    try:
        credentials = authenticate_google_noninteractive(sheets_config)
        service = create_sheets_service(credentials)
        result = push_crm_to_google_sheets(repository, sheets_config, service=service)
        return result.success, result.error
    except Exception as exc:
        return False, str(exc)


def run_weekly(
    config: SchedulerConfig,
    *,
    agent_factory: Callable[[JobRepository], DanielJobAgent] = DanielJobAgent,
    sheets_sync: Callable[[JobRepository, SchedulerConfig], tuple[bool | None, str | None]] = _sheets_sync,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> WeeklyRunOutcome:
    prune_logs(config)
    started_at = clock()
    agent_result: AgentRunResult | None = None
    sheets_success: bool | None = None
    errors: list[str] = []
    status = "FAILURE"
    exit_code = FAILURE
    with RunLock(config.lock_path):
        with JobRepository(config.database_path) as repository:
            try:
                agent_result = agent_factory(repository).run()
                if agent_result.sources_failed:
                    errors.append(
                        "Sources failed: " + ", ".join(agent_result.sources_failed)
                    )
                ingestion_errors = sum(
                    agent_result.discovery.errors_by_source.values()
                )
                if ingestion_errors:
                    errors.append(f"Ingestion errors: {ingestion_errors}")
                sheets_success, sheets_error = sheets_sync(repository, config)
                if sheets_error:
                    errors.append(f"Sheets: {sheets_error}")
                if not agent_result.sources_succeeded or agent_result.persistence_errors:
                    status, exit_code = "FAILURE", FAILURE
                elif (
                    agent_result.sources_failed
                    or ingestion_errors
                    or sheets_success is False
                ):
                    status, exit_code = "PARTIAL_FAILURE", PARTIAL_FAILURE
                else:
                    status, exit_code = "SUCCESS", SUCCESS
            except Exception as exc:
                errors.append(f"Agent: {exc}")
            finished_at = clock()
            repository.record_agent_run(
                started_at=started_at, finished_at=finished_at, status=status,
                sources_succeeded=agent_result.sources_succeeded if agent_result else [],
                sources_failed=agent_result.sources_failed if agent_result else [],
                jobs_received=agent_result.jobs_received if agent_result else 0,
                new_count=agent_result.new if agent_result else 0,
                existing_count=agent_result.existing if agent_result else 0,
                updated_count=agent_result.updated if agent_result else 0,
                lifecycle_misses=agent_result.lifecycle.misses_recorded if agent_result else 0,
                possibly_closed=agent_result.lifecycle.possibly_closed if agent_result else 0,
                newly_closed=agent_result.lifecycle.newly_closed if agent_result else 0,
                reopened=agent_result.lifecycle.reopened if agent_result else 0,
                sheets_sync_success=sheets_success,
                error_summary="; ".join(errors) or None,
            )
    return WeeklyRunOutcome(exit_code, status, agent_result, sheets_success, "; ".join(errors) or None)


def format_weekly_outcome(outcome: WeeklyRunOutcome) -> str:
    lines = ["Weekly automation", f"Status: {outcome.status}"]
    if outcome.agent_result:
        lines.extend(["", format_agent_run(outcome.agent_result)])
    sheets = "disabled" if outcome.sheets_sync_success is None else (
        "success" if outcome.sheets_sync_success else "failed"
    )
    lines.append(f"Sheets sync: {sheets}")
    if outcome.error_summary:
        lines.append(f"Errors: {outcome.error_summary}")
    return "\n".join(lines)


def main() -> None:
    config = SchedulerConfig.from_project(Path.cwd())
    try:
        outcome = run_weekly(config)
    except AlreadyRunningError as exc:
        print(str(exc))
        raise SystemExit(PARTIAL_FAILURE) from exc
    print(format_weekly_outcome(outcome))
    raise SystemExit(outcome.exit_code)


if __name__ == "__main__":
    main()
