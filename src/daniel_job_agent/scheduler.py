"""Configuração e controle testável de um LaunchAgent do usuário no macOS."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import plistlib
import subprocess
from typing import Callable, Mapping, Sequence


LAUNCH_AGENT_LABEL = "com.daniel.job-agent"
WEEKDAYS = {
    "sunday": 1, "monday": 2, "tuesday": 3, "wednesday": 4,
    "thursday": 5, "friday": 6, "saturday": 7,
}


def load_env_file(path: Path) -> dict[str, str]:
    """Lê somente pares KEY=VALUE simples, suficientes para configuração local."""

    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


@dataclass(frozen=True, slots=True)
class WeeklySchedule:
    weekday: str = "Monday"
    hour: int = 8
    minute: int = 0

    def __post_init__(self) -> None:
        normalized = self.weekday.casefold()
        if normalized not in WEEKDAYS:
            raise ValueError("weekday must be an English weekday name")
        if not 0 <= self.hour <= 23 or not 0 <= self.minute <= 59:
            raise ValueError("hour must be 0-23 and minute must be 0-59")

    @property
    def launchd_weekday(self) -> int:
        return WEEKDAYS[self.weekday.casefold()]

    def display(self) -> str:
        return f"{self.weekday} {self.hour:02d}:{self.minute:02d}"


@dataclass(frozen=True, slots=True)
class SchedulerConfig:
    project_dir: Path
    python_path: Path
    database_path: Path
    logs_dir: Path
    plist_path: Path
    lock_path: Path
    schedule: WeeklySchedule = WeeklySchedule()
    spreadsheet_id: str | None = None
    sheet_name: str = "Job CRM"
    credentials_path: Path = Path("credentials.json")
    token_path: Path = Path("token.json")

    @property
    def sheets_enabled(self) -> bool:
        return bool(self.spreadsheet_id)

    @property
    def out_log(self) -> Path:
        return self.logs_dir / "job_agent.out.log"

    @property
    def err_log(self) -> Path:
        return self.logs_dir / "job_agent.err.log"

    @property
    def reports_dir(self) -> Path:
        return self.project_dir / "reports"

    @classmethod
    def from_project(
        cls, project_dir: Path, *, environment: Mapping[str, str] | None = None,
        home: Path | None = None,
    ) -> "SchedulerConfig":
        project = project_dir.resolve()
        values = load_env_file(project / ".env")
        values.update(os.environ if environment is None else environment)

        def local_path(key: str, default: str) -> Path:
            value = Path(values.get(key, default)).expanduser()
            return value if value.is_absolute() else project / value

        user_home = (home or Path.home()).expanduser()
        return cls(
            project_dir=project,
            python_path=project / ".venv/bin/python",
            database_path=local_path("JOB_AGENT_DB", "data/job_agent.db"),
            logs_dir=project / "logs",
            plist_path=user_home / "Library/LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist",
            lock_path=project / "data/weekly_run.lock",
            schedule=WeeklySchedule(
                values.get("JOB_AGENT_WEEKDAY", "Monday"),
                int(values.get("JOB_AGENT_HOUR", "8")),
                int(values.get("JOB_AGENT_MINUTE", "0")),
            ),
            spreadsheet_id=values.get("GOOGLE_SPREADSHEET_ID") or None,
            sheet_name=values.get("GOOGLE_SHEET_NAME", "Job CRM"),
            credentials_path=local_path("GOOGLE_CREDENTIALS_PATH", "credentials.json"),
            token_path=local_path("GOOGLE_TOKEN_PATH", "token.json"),
        )


def validate_config(config: SchedulerConfig, *, for_install: bool = True) -> list[str]:
    errors: list[str] = []
    if not config.project_dir.is_dir():
        errors.append(f"Project directory not found: {config.project_dir}")
    if not config.python_path.is_file():
        errors.append(f"Virtualenv Python not found: {config.python_path}")
    elif not os.access(config.python_path, os.X_OK):
        errors.append(f"Virtualenv Python is not executable: {config.python_path}")
    data_dir = config.database_path.parent
    if not data_dir.exists() or not os.access(data_dir, os.W_OK):
        errors.append(f"Database directory is unavailable: {data_dir}")
    if config.sheets_enabled:
        if not config.credentials_path.is_file():
            errors.append(f"Google credentials file not found: {config.credentials_path}")
        if not config.token_path.is_file():
            errors.append(f"Google token file not found: {config.token_path}")
    if for_install and config.plist_path.parent.exists() and not os.access(
        config.plist_path.parent, os.W_OK
    ):
        errors.append(f"LaunchAgents directory is not writable: {config.plist_path.parent}")
    return errors


def generate_plist(config: SchedulerConfig) -> bytes:
    payload = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [
            str(config.python_path), "-m", "daniel_job_agent.weekly_run",
        ],
        "WorkingDirectory": str(config.project_dir),
        "EnvironmentVariables": {"PYTHONPATH": str(config.project_dir / "src")},
        "StartCalendarInterval": {
            "Weekday": config.schedule.launchd_weekday,
            "Hour": config.schedule.hour,
            "Minute": config.schedule.minute,
        },
        "RunAtLoad": False,
        "StandardOutPath": str(config.out_log),
        "StandardErrorPath": str(config.err_log),
    }
    return plistlib.dumps(payload, sort_keys=True)


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


class LaunchAgentController:
    def __init__(self, config: SchedulerConfig, runner: Runner = default_runner) -> None:
        self.config = config
        self.runner = runner
        self.domain = f"gui/{os.getuid()}"
        self.service = f"{self.domain}/{LAUNCH_AGENT_LABEL}"

    def install(self) -> None:
        errors = validate_config(self.config)
        if errors:
            raise ValueError("\n".join(errors))
        self.config.logs_dir.mkdir(parents=True, exist_ok=True)
        self.config.plist_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.plist_path.write_bytes(generate_plist(self.config))
        enabled = self.runner(["launchctl", "enable", self.service])
        if enabled.returncode:
            raise RuntimeError(enabled.stderr.strip() or "launchctl enable failed")
        result = self.runner(["launchctl", "bootstrap", self.domain, str(self.config.plist_path)])
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "launchctl bootstrap failed")

    def start(self) -> None:
        if not self.config.plist_path.is_file():
            raise ValueError("Scheduler is not installed")
        enabled = self.runner(["launchctl", "enable", self.service])
        if enabled.returncode:
            raise RuntimeError(enabled.stderr.strip() or "launchctl enable failed")
        result = self.runner(["launchctl", "bootstrap", self.domain, str(self.config.plist_path)])
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "launchctl bootstrap failed")

    def stop(self) -> None:
        if not self.config.plist_path.is_file():
            raise ValueError("Scheduler is not installed")
        disabled = self.runner(["launchctl", "disable", self.service])
        if disabled.returncode:
            raise RuntimeError(disabled.stderr.strip() or "launchctl disable failed")
        result = self.runner(["launchctl", "bootout", self.service])
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "launchctl bootout failed")

    def uninstall(self) -> None:
        if not self.config.plist_path.exists():
            return
        self.runner(["launchctl", "bootout", self.service])
        self.config.plist_path.unlink()

    def is_loaded(self) -> bool:
        return self.runner(["launchctl", "print", self.service]).returncode == 0
