"""Testes offline da automação semanal; launchctl e rede nunca são chamados."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest

from daniel_job_agent.repository import JobRepository, SCHEMA_VERSION
from daniel_job_agent.scheduler import (
    LAUNCH_AGENT_LABEL, LaunchAgentController, SchedulerConfig,
    WeeklySchedule, generate_plist, validate_config,
)
from daniel_job_agent.scheduler_cli import build_parser, format_status
from daniel_job_agent.weekly_run import (
    AlreadyRunningError, RunLock, SUCCESS, PARTIAL_FAILURE, run_weekly,
)


class FakeRunner:
    def __init__(self, *, loaded: bool = True) -> None:
        self.commands: list[list[str]] = []
        self.loaded = loaded

    def __call__(self, command):
        command = list(command)
        self.commands.append(command)
        code = 0
        if command[1] == "print" and not self.loaded:
            code = 1
        return subprocess.CompletedProcess(command, code, "", "")


class SchedulerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".venv/bin").mkdir(parents=True)
        self.python = self.root / ".venv/bin/python"
        self.python.write_text("python", encoding="utf-8")
        self.python.chmod(0o700)
        (self.root / "data").mkdir()
        self.home = self.root / "home"
        (self.home / "Library/LaunchAgents").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def config(self, schedule=WeeklySchedule()) -> SchedulerConfig:
        return SchedulerConfig(
            project_dir=self.root, python_path=self.python,
            database_path=self.root / "data/jobs.db", logs_dir=self.root / "logs",
            plist_path=self.home / "Library/LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist",
            lock_path=self.root / "data/run.lock", schedule=schedule,
        )


class PlistAndConfigTests(SchedulerTestCase):
    def test_default_plist_is_monday_0800_with_direct_venv_python(self) -> None:
        config = self.config()
        payload = plistlib.loads(generate_plist(config))
        self.assertEqual(payload["StartCalendarInterval"], {"Weekday": 2, "Hour": 8, "Minute": 0})
        self.assertEqual(payload["ProgramArguments"][0], str(self.python))
        self.assertEqual(payload["WorkingDirectory"], str(self.root))
        self.assertEqual(payload["StandardOutPath"], str(config.out_log))
        self.assertEqual(payload["StandardErrorPath"], str(config.err_log))
        self.assertNotIn("spreadsheet", generate_plist(config).decode().casefold())

    def test_custom_schedule_is_deterministic(self) -> None:
        config = self.config(WeeklySchedule("Friday", 17, 45))
        first = generate_plist(config)
        self.assertEqual(first, generate_plist(config))
        self.assertEqual(plistlib.loads(first)["StartCalendarInterval"], {"Weekday": 6, "Hour": 17, "Minute": 45})

    def test_from_project_reads_env_without_putting_sheet_id_in_plist(self) -> None:
        (self.root / ".env").write_text(
            "JOB_AGENT_WEEKDAY=Tuesday\nJOB_AGENT_HOUR=9\nJOB_AGENT_MINUTE=30\nGOOGLE_SPREADSHEET_ID=sheet-123\n",
            encoding="utf-8",
        )
        config = SchedulerConfig.from_project(self.root, environment={}, home=self.home)
        self.assertEqual(config.schedule, WeeklySchedule("Tuesday", 9, 30))
        self.assertEqual(config.spreadsheet_id, "sheet-123")
        self.assertNotIn(b"sheet-123", generate_plist(config))

    def test_validation_reports_paths_and_sheets_prerequisites(self) -> None:
        config = self.config()
        self.assertEqual(validate_config(config), [])
        broken = SchedulerConfig(
            project_dir=config.project_dir, python_path=self.root / "missing-python",
            database_path=config.database_path, logs_dir=config.logs_dir,
            plist_path=config.plist_path, lock_path=config.lock_path,
            spreadsheet_id="configured", credentials_path=self.root / "missing-credentials",
            token_path=self.root / "missing-token",
        )
        errors = "\n".join(validate_config(broken))
        self.assertIn("Virtualenv Python not found", errors)
        self.assertIn("credentials file not found", errors)
        self.assertIn("token file not found", errors)


class LaunchAgentControllerTests(SchedulerTestCase):
    def test_install_writes_plist_and_simulates_bootstrap(self) -> None:
        config, runner = self.config(), FakeRunner()
        LaunchAgentController(config, runner).install()
        self.assertTrue(config.plist_path.is_file())
        self.assertEqual(runner.commands[0][1], "enable")
        self.assertEqual(runner.commands[1][:3], ["launchctl", "bootstrap", f"gui/{__import__('os').getuid()}"])

    def test_start_stop_status_and_uninstall_are_simulated(self) -> None:
        config, runner = self.config(), FakeRunner()
        config.plist_path.write_bytes(generate_plist(config))
        controller = LaunchAgentController(config, runner)
        controller.start()
        controller.stop()
        self.assertTrue(controller.is_loaded())
        controller.uninstall()
        self.assertFalse(config.plist_path.exists())
        verbs = [command[1] for command in runner.commands]
        self.assertEqual(verbs, ["enable", "bootstrap", "disable", "bootout", "print", "bootout"])

    def test_all_cli_commands_have_help(self) -> None:
        help_text = build_parser().format_help()
        for command in ("install", "status", "start", "stop", "run-now", "uninstall"):
            self.assertIn(command, help_text)


class LockTests(SchedulerTestCase):
    def test_lock_blocks_active_process_and_cleans_after_error(self) -> None:
        config = self.config()
        with RunLock(config.lock_path):
            with self.assertRaises(AlreadyRunningError):
                with RunLock(config.lock_path):
                    pass
        self.assertFalse(config.lock_path.exists())

    def test_stale_lock_is_replaced_safely(self) -> None:
        config = self.config()
        config.lock_path.write_text("99999999", encoding="utf-8")
        with RunLock(config.lock_path):
            self.assertTrue(config.lock_path.exists())
        self.assertFalse(config.lock_path.exists())


class FakeAgentResult:
    def __init__(self, failed=None) -> None:
        self.sources_succeeded = ["Jobicy", "Remotive"]
        self.sources_failed = failed or []
        if failed:
            self.sources_succeeded = [name for name in self.sources_succeeded if name not in failed]
        self.persistence_errors = 0
        self.discovery = type("Discovery", (), {"errors_by_source": {"Jobicy": 0, "Remotive": 0}})()
        self.jobs_received = 4
        self.new = 2
        self.existing = 1
        self.updated = 1
        self.lifecycle = type("Lifecycle", (), {
            "misses_recorded": 3, "possibly_closed": 2,
            "newly_closed": 1, "reopened": 1,
        })()


class FakeAgent:
    def __init__(self, result) -> None:
        self.result = result

    def run(self):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class WeeklyWorkflowTests(SchedulerTestCase):
    def clock(self):
        current = datetime(2026, 8, 17, 11, tzinfo=timezone.utc)
        def next_time():
            nonlocal current
            value, current = current, current + timedelta(seconds=5)
            return value
        return next_time

    def execute_workflow(self, result, sheets=(None, None)):
        config = self.config()
        outcome = run_weekly(
            config, agent_factory=lambda repository: FakeAgent(result),
            sheets_sync=lambda repository, cfg: sheets, clock=self.clock(),
            report_writer=lambda repository, history, agent, rows, directory: directory / "fake.md",
        )
        with JobRepository(config.database_path) as repository:
            history = repository.latest_agent_run()
        return config, outcome, history

    def test_success_and_run_history(self) -> None:
        config, outcome, history = self.execute_workflow(FakeAgentResult(), (True, None))
        self.assertEqual((outcome.exit_code, outcome.status), (SUCCESS, "SUCCESS"))
        self.assertIsNotNone(history)
        self.assertEqual((history.jobs_received, history.new_count, history.lifecycle_misses), (4, 2, 3))
        self.assertEqual(history.sheets_sync_success, True)
        self.assertFalse(config.lock_path.exists())

    def test_each_source_failure_is_partial_and_persisted(self) -> None:
        for source in ("Jobicy", "Remotive"):
            with self.subTest(source=source):
                _, outcome, history = self.execute_workflow(FakeAgentResult([source]))
                self.assertEqual(outcome.exit_code, PARTIAL_FAILURE)
                self.assertEqual(history.sources_failed, [source])

    def test_sheets_failure_after_persistence_is_partial(self) -> None:
        _, outcome, history = self.execute_workflow(FakeAgentResult(), (False, "API unavailable"))
        self.assertEqual(outcome.status, "PARTIAL_FAILURE")
        self.assertEqual(history.new_count, 2)
        self.assertIn("Sheets: API unavailable", history.error_summary)

    def test_agent_failure_is_recorded_without_jobs(self) -> None:
        _, outcome, history = self.execute_workflow(RuntimeError("offline failure"))
        self.assertEqual(outcome.status, "FAILURE")
        self.assertEqual(history.jobs_received, 0)
        self.assertIn("offline failure", history.error_summary)

    def test_report_failure_does_not_rollback_completed_run(self) -> None:
        config = self.config()
        outcome = run_weekly(
            config,
            agent_factory=lambda repository: FakeAgent(FakeAgentResult()),
            sheets_sync=lambda repository, cfg: (True, None, 4),
            report_writer=lambda *args: (_ for _ in ()).throw(OSError("disk full")),
            clock=self.clock(),
        )
        with JobRepository(config.database_path) as repository:
            history = repository.latest_agent_run()
        self.assertEqual((outcome.status, outcome.exit_code), ("PARTIAL_FAILURE", PARTIAL_FAILURE))
        self.assertEqual(history.new_count, 2)
        self.assertIn("Report: disk full", history.error_summary)

    def test_status_shows_latest_run(self) -> None:
        config, _, _ = self.execute_workflow(FakeAgentResult())
        text = format_status(config, loaded=False)
        self.assertIn("Loaded/enabled: no", text)
        self.assertIn("Status: SUCCESS", text)
        self.assertIn("New jobs: 2", text)

    def test_schema_migration_preserves_existing_crm_table(self) -> None:
        config = self.config()
        with JobRepository(config.database_path) as repository:
            original_count = repository.count()
            self.assertIsNone(repository.latest_agent_run())
            version = repository.connection.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(original_count, 0)
        self.assertEqual(version, SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
