"""Persistência SQLite local para oportunidades já processadas pelo pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from .models import (
    ApplicationStatus,
    ApplicationTracking,
    JobLifecycleStatus,
    JobOpportunity,
    RoleFamily,
    Seniority,
)
from .pipeline import PipelineResult, ProcessedOpportunity
from .rules import RetentionDecision, normalize_company, normalize_job_url, normalize_role


DEFAULT_DATABASE_PATH = Path("data/job_agent.db")


class SyncStatus(str, Enum):
    """Resultado da comparação de uma oportunidade com o histórico local."""

    NEW = "NEW"
    EXISTING = "EXISTING"
    UPDATED = "UPDATED"


@dataclass(frozen=True, slots=True)
class StoredOpportunity:
    """Registro reconstruído do SQLite, incluindo histórico e avaliação."""

    internal_id: int
    opportunity: JobOpportunity
    first_seen_at: datetime
    last_seen_at: datetime
    match_score: int
    retention_decision: RetentionDecision
    role_family: RoleFamily
    seniority: Seniority
    positive_reasons: list[str]
    potential_gaps: list[str]
    unknowns: list[str]


@dataclass(frozen=True, slots=True)
class SyncedOpportunity:
    internal_id: int
    status: SyncStatus
    opportunity: JobOpportunity


@dataclass(frozen=True, slots=True)
class SyncError:
    opportunity: ProcessedOpportunity
    message: str


@dataclass(frozen=True, slots=True)
class SyncResult:
    received: int
    new: int
    existing: int
    updated: int
    errors: int
    total_stored: int
    new_jobs: list[SyncedOpportunity]
    existing_jobs: list[SyncedOpportunity]
    updated_jobs: list[SyncedOpportunity]
    error_details: list[SyncError]


_AUTOMATIC_COLUMNS = (
    "external_id", "company", "role", "job_url", "source", "location",
    "remote", "brazil_eligible", "employment_type", "description",
    "requirements", "responsibilities", "preferred_qualifications",
    "tools_mentioned", "industries_mentioned", "years_experience_required",
    "full_cycle_sales_required", "outbound_sales_required",
    "inbound_sales_mentioned", "b2b_experience_required",
    "saas_experience_required", "base_salary", "ote", "salary_min",
    "salary_max", "salary_currency", "salary_period", "salary_text",
    "job_level", "date_posted", "match_score", "retention_decision",
    "role_family", "seniority", "positive_reasons", "potential_gaps",
    "unknowns",
)

SCHEMA_VERSION = 3


@dataclass(frozen=True, slots=True)
class AgentRunHistory:
    """Metadados operacionais leves; nunca contém payloads ou secrets."""

    run_id: int
    started_at: datetime
    finished_at: datetime
    status: str
    sources_succeeded: list[str]
    sources_failed: list[str]
    jobs_received: int
    new_count: int
    existing_count: int
    updated_count: int
    lifecycle_misses: int
    possibly_closed: int
    newly_closed: int
    reopened: int
    sheets_sync_success: bool | None
    error_summary: str | None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _bool_to_db(value: bool | None) -> int | None:
    return None if value is None else int(value)


def _bool_from_db(value: int | None) -> bool | None:
    return None if value is None else bool(value)


class JobRepository:
    """Centraliza schema, consultas e gravações do histórico SQLite."""

    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self._create_schema()

    def __enter__(self) -> JobRepository:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def _create_schema(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS opportunities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT,
                company TEXT NOT NULL,
                company_normalized TEXT NOT NULL,
                role TEXT NOT NULL,
                role_normalized TEXT NOT NULL,
                job_url TEXT NOT NULL,
                job_url_normalized TEXT NOT NULL,
                source TEXT NOT NULL,
                location TEXT NOT NULL,
                remote INTEGER,
                brazil_eligible INTEGER,
                employment_type TEXT,
                description TEXT,
                requirements TEXT,
                responsibilities TEXT,
                preferred_qualifications TEXT,
                tools_mentioned TEXT,
                industries_mentioned TEXT,
                years_experience_required REAL,
                full_cycle_sales_required INTEGER,
                outbound_sales_required INTEGER,
                inbound_sales_mentioned INTEGER,
                b2b_experience_required INTEGER,
                saas_experience_required INTEGER,
                base_salary REAL,
                ote REAL,
                salary_min REAL,
                salary_max REAL,
                salary_currency TEXT,
                salary_period TEXT,
                salary_text TEXT,
                job_level TEXT,
                date_found TEXT NOT NULL,
                date_posted TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                last_checked TEXT NOT NULL,
                closed_at TEXT,
                lifecycle_status TEXT NOT NULL DEFAULT 'UNKNOWN',
                consecutive_misses INTEGER NOT NULL DEFAULT 0,
                first_missing_at TEXT,
                last_missing_at TEXT,
                reopened_at TEXT,
                last_verified_at TEXT,
                match_score INTEGER NOT NULL,
                retention_decision TEXT NOT NULL,
                role_family TEXT NOT NULL,
                seniority TEXT NOT NULL,
                positive_reasons TEXT NOT NULL,
                potential_gaps TEXT NOT NULL,
                unknowns TEXT NOT NULL,
                still_open INTEGER,
                application_status TEXT NOT NULL,
                applied_date TEXT,
                recruiter_name TEXT,
                recruiter_email TEXT,
                next_step TEXT,
                next_step_date TEXT,
                notes TEXT
            )
            """
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_opportunity_url ON opportunities(job_url_normalized)"
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_opportunity_external ON opportunities(source, external_id)"
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_opportunity_company_role ON opportunities(company_normalized, role_normalized)"
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                status TEXT NOT NULL,
                sources_succeeded TEXT NOT NULL,
                sources_failed TEXT NOT NULL,
                jobs_received INTEGER NOT NULL,
                new_count INTEGER NOT NULL,
                existing_count INTEGER NOT NULL,
                updated_count INTEGER NOT NULL,
                lifecycle_misses INTEGER NOT NULL,
                possibly_closed INTEGER NOT NULL,
                newly_closed INTEGER NOT NULL,
                reopened INTEGER NOT NULL,
                sheets_sync_success INTEGER,
                error_summary TEXT
            )
            """
        )
        self._migrate_schema()
        self.connection.commit()

    def _migrate_schema(self) -> None:
        """Adiciona colunas lifecycle sem apagar bancos ou registros existentes."""

        columns = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(opportunities)")
        }
        additions = {
            "lifecycle_status": "TEXT NOT NULL DEFAULT 'UNKNOWN'",
            "consecutive_misses": "INTEGER NOT NULL DEFAULT 0",
            "first_missing_at": "TEXT",
            "last_missing_at": "TEXT",
            "reopened_at": "TEXT",
            "last_verified_at": "TEXT",
        }
        for name, definition in additions.items():
            if name not in columns:
                self.connection.execute(
                    f"ALTER TABLE opportunities ADD COLUMN {name} {definition}"
                )
        self.connection.execute(
            """UPDATE opportunities
               SET lifecycle_status = CASE
                   WHEN still_open = 1 THEN 'OPEN'
                   WHEN still_open = 0 THEN 'CLOSED'
                   ELSE lifecycle_status
               END
               WHERE lifecycle_status = 'UNKNOWN'"""
        )
        current_version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if current_version < SCHEMA_VERSION:
            self.connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) AS count FROM opportunities").fetchone()
        return int(row["count"])

    def record_agent_run(
        self,
        *,
        started_at: datetime,
        finished_at: datetime,
        status: str,
        sources_succeeded: list[str],
        sources_failed: list[str],
        jobs_received: int,
        new_count: int,
        existing_count: int,
        updated_count: int,
        lifecycle_misses: int,
        possibly_closed: int,
        newly_closed: int,
        reopened: int,
        sheets_sync_success: bool | None,
        error_summary: str | None,
    ) -> int:
        cursor = self.connection.execute(
            """INSERT INTO agent_runs (
               started_at, finished_at, status, sources_succeeded, sources_failed,
               jobs_received, new_count, existing_count, updated_count,
               lifecycle_misses, possibly_closed, newly_closed, reopened,
               sheets_sync_success, error_summary
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _as_utc(started_at).isoformat(), _as_utc(finished_at).isoformat(),
                status, _dump(sources_succeeded), _dump(sources_failed), jobs_received,
                new_count, existing_count, updated_count, lifecycle_misses,
                possibly_closed, newly_closed, reopened,
                _bool_to_db(sheets_sync_success), error_summary,
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def latest_agent_run(self) -> AgentRunHistory | None:
        row = self.connection.execute(
            "SELECT * FROM agent_runs ORDER BY run_id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return AgentRunHistory(
            run_id=int(row["run_id"]),
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=datetime.fromisoformat(row["finished_at"]),
            status=row["status"],
            sources_succeeded=json.loads(row["sources_succeeded"]),
            sources_failed=json.loads(row["sources_failed"]),
            jobs_received=int(row["jobs_received"]),
            new_count=int(row["new_count"]),
            existing_count=int(row["existing_count"]),
            updated_count=int(row["updated_count"]),
            lifecycle_misses=int(row["lifecycle_misses"]),
            possibly_closed=int(row["possibly_closed"]),
            newly_closed=int(row["newly_closed"]),
            reopened=int(row["reopened"]),
            sheets_sync_success=_bool_from_db(row["sheets_sync_success"]),
            error_summary=row["error_summary"],
        )

    def list_agent_runs(self, *, limit: int = 10) -> list[AgentRunHistory]:
        if limit < 1:
            raise ValueError("limit must be positive")
        rows = self.connection.execute(
            "SELECT * FROM agent_runs ORDER BY run_id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._agent_run_from_row(row) for row in rows]

    def get_agent_run(self, run_id: int) -> AgentRunHistory | None:
        row = self.connection.execute(
            "SELECT * FROM agent_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return self._agent_run_from_row(row) if row else None

    def update_agent_run_result(
        self, run_id: int, *, status: str, error_summary: str | None
    ) -> None:
        self.connection.execute(
            "UPDATE agent_runs SET status = ?, error_summary = ? WHERE run_id = ?",
            (status, error_summary, run_id),
        )
        self.connection.commit()

    @staticmethod
    def _agent_run_from_row(row: sqlite3.Row) -> AgentRunHistory:
        return AgentRunHistory(
            run_id=int(row["run_id"]),
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=datetime.fromisoformat(row["finished_at"]),
            status=row["status"],
            sources_succeeded=json.loads(row["sources_succeeded"]),
            sources_failed=json.loads(row["sources_failed"]),
            jobs_received=int(row["jobs_received"]),
            new_count=int(row["new_count"]),
            existing_count=int(row["existing_count"]),
            updated_count=int(row["updated_count"]),
            lifecycle_misses=int(row["lifecycle_misses"]),
            possibly_closed=int(row["possibly_closed"]),
            newly_closed=int(row["newly_closed"]),
            reopened=int(row["reopened"]),
            sheets_sync_success=_bool_from_db(row["sheets_sync_success"]),
            error_summary=row["error_summary"],
        )

    def _find_existing(self, job: JobOpportunity) -> sqlite3.Row | None:
        row = self.connection.execute(
            "SELECT * FROM opportunities WHERE job_url_normalized = ? ORDER BY id LIMIT 1",
            (normalize_job_url(job.job_url),),
        ).fetchone()
        if row is not None:
            return row
        if job.external_id:
            row = self.connection.execute(
                "SELECT * FROM opportunities WHERE source = ? AND external_id = ? ORDER BY id LIMIT 1",
                (job.source, job.external_id),
            ).fetchone()
            if row is not None:
                return row
        return self.connection.execute(
            """SELECT * FROM opportunities
               WHERE company_normalized = ? AND role_normalized = ?
               ORDER BY id LIMIT 1""",
            (normalize_company(job.company).casefold(), normalize_role(job.role).casefold()),
        ).fetchone()

    @staticmethod
    def _automatic_values(item: ProcessedOpportunity) -> dict[str, object]:
        job = item.original_job
        return {
            "external_id": job.external_id,
            "company": job.company,
            "role": job.role,
            "job_url": job.job_url,
            "source": job.source,
            "location": job.location,
            "remote": _bool_to_db(job.remote),
            "brazil_eligible": _bool_to_db(job.brazil_eligible),
            "employment_type": job.employment_type,
            "description": job.description,
            "requirements": _dump(job.requirements),
            "responsibilities": _dump(job.responsibilities),
            "preferred_qualifications": _dump(job.preferred_qualifications),
            "tools_mentioned": _dump(job.tools_mentioned),
            "industries_mentioned": _dump(job.industries_mentioned),
            "years_experience_required": job.years_experience_required,
            "full_cycle_sales_required": _bool_to_db(job.full_cycle_sales_required),
            "outbound_sales_required": _bool_to_db(job.outbound_sales_required),
            "inbound_sales_mentioned": _bool_to_db(job.inbound_sales_mentioned),
            "b2b_experience_required": _bool_to_db(job.b2b_experience_required),
            "saas_experience_required": _bool_to_db(job.saas_experience_required),
            "base_salary": job.base_salary,
            "ote": job.ote,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "salary_currency": job.salary_currency,
            "salary_period": job.salary_period,
            "salary_text": job.salary_text,
            "job_level": job.job_level,
            "date_posted": job.date_posted.isoformat() if job.date_posted else None,
            "match_score": item.match_score,
            "retention_decision": item.retention_decision.value,
            "role_family": item.role_family.value,
            "seniority": item.seniority.value,
            "positive_reasons": _dump(item.positive_reasons),
            "potential_gaps": _dump(item.potential_gaps),
            "unknowns": _dump(item.unknowns),
        }

    def _insert(self, item: ProcessedOpportunity, now: datetime) -> int:
        job = item.original_job
        automatic = self._automatic_values(item)
        explicitly_closed = (
            job.lifecycle_status is JobLifecycleStatus.CLOSED
            or job.still_open is False
        )
        initial_status = (
            JobLifecycleStatus.CLOSED if explicitly_closed else JobLifecycleStatus.OPEN
        )
        # Dados manuais não vêm da automação: um registro novo começa com os
        # defaults do CRM e só muda por update_tracking().
        tracking = ApplicationTracking()
        values = {
            **automatic,
            "company_normalized": normalize_company(job.company).casefold(),
            "role_normalized": normalize_role(job.role).casefold(),
            "job_url_normalized": normalize_job_url(job.job_url),
            "date_found": job.date_found.isoformat(),
            "first_seen_at": now.isoformat(),
            "last_seen_at": now.isoformat(),
            "last_checked": now.isoformat(),
            "closed_at": now.isoformat() if explicitly_closed else None,
            "lifecycle_status": initial_status.value,
            "consecutive_misses": 0,
            "first_missing_at": None,
            "last_missing_at": None,
            "reopened_at": None,
            "last_verified_at": now.isoformat() if explicitly_closed else None,
            "still_open": 0 if explicitly_closed else 1,
            "application_status": tracking.application_status.value,
            "applied_date": tracking.applied_date.isoformat() if tracking.applied_date else None,
            "recruiter_name": tracking.recruiter_name,
            "recruiter_email": tracking.recruiter_email,
            "next_step": tracking.next_step,
            "next_step_date": tracking.next_step_date.isoformat() if tracking.next_step_date else None,
            "notes": tracking.notes,
        }
        columns = list(values)
        cursor = self.connection.execute(
            f"INSERT INTO opportunities ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            tuple(values[column] for column in columns),
        )
        return int(cursor.lastrowid)

    def _sync_one(self, item: ProcessedOpportunity, now: datetime) -> SyncedOpportunity:
        job = item.original_job
        existing = self._find_existing(job)
        if existing is None:
            internal_id = self._insert(item, now)
            return SyncedOpportunity(internal_id, SyncStatus.NEW, job)

        automatic = self._automatic_values(item)
        changed = any(existing[column] != automatic[column] for column in _AUTOMATIC_COLUMNS)
        updates: dict[str, object] = {
            "last_seen_at": now.isoformat(),
            "last_checked": now.isoformat(),
        }
        if changed:
            updates.update(automatic)
            updates.update(
                company_normalized=normalize_company(job.company).casefold(),
                role_normalized=normalize_role(job.role).casefold(),
                job_url_normalized=normalize_job_url(job.job_url),
            )
        assignments = ", ".join(f"{column} = ?" for column in updates)
        self.connection.execute(
            f"UPDATE opportunities SET {assignments} WHERE id = ?",
            (*updates.values(), existing["id"]),
        )
        status = SyncStatus.UPDATED if changed else SyncStatus.EXISTING
        return SyncedOpportunity(int(existing["id"]), status, job)

    def sync(
        self,
        opportunities: Iterable[ProcessedOpportunity],
        *,
        now: datetime | None = None,
    ) -> SyncResult:
        items = list(opportunities)
        timestamp = _as_utc(now or _utc_now())
        grouped: dict[SyncStatus, list[SyncedOpportunity]] = {
            status: [] for status in SyncStatus
        }
        errors: list[SyncError] = []
        for index, item in enumerate(items):
            savepoint = f"opportunity_{index}"
            self.connection.execute(f"SAVEPOINT {savepoint}")
            try:
                synced = self._sync_one(item, timestamp)
                self.connection.execute(f"RELEASE SAVEPOINT {savepoint}")
                grouped[synced.status].append(synced)
            except (sqlite3.Error, TypeError, ValueError) as exc:
                self.connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                self.connection.execute(f"RELEASE SAVEPOINT {savepoint}")
                errors.append(SyncError(item, str(exc)))
        self.connection.commit()
        return SyncResult(
            received=len(items),
            new=len(grouped[SyncStatus.NEW]),
            existing=len(grouped[SyncStatus.EXISTING]),
            updated=len(grouped[SyncStatus.UPDATED]),
            errors=len(errors),
            total_stored=self.count(),
            new_jobs=grouped[SyncStatus.NEW],
            existing_jobs=grouped[SyncStatus.EXISTING],
            updated_jobs=grouped[SyncStatus.UPDATED],
            error_details=errors,
        )

    def update_tracking(self, internal_id: int, tracking: ApplicationTracking) -> None:
        """Atualiza somente os campos manuais do CRM."""

        self.connection.execute(
            """UPDATE opportunities SET
               application_status = ?, applied_date = ?, recruiter_name = ?,
               recruiter_email = ?, next_step = ?, next_step_date = ?, notes = ?
               WHERE id = ?""",
            (
                tracking.application_status.value,
                tracking.applied_date.isoformat() if tracking.applied_date else None,
                tracking.recruiter_name,
                tracking.recruiter_email,
                tracking.next_step,
                tracking.next_step_date.isoformat() if tracking.next_step_date else None,
                tracking.notes,
                internal_id,
            ),
        )
        self.connection.commit()

    def update_lifecycle_seen(
        self,
        internal_id: int,
        *,
        now: datetime,
        reopened: bool,
        explicitly_verified: bool,
    ) -> None:
        """Marca uma vaga encontrada sem tocar nos campos manuais do CRM."""

        timestamp = _as_utc(now).isoformat()
        self.connection.execute(
            """UPDATE opportunities SET
               lifecycle_status = ?, consecutive_misses = 0,
               first_missing_at = NULL, last_missing_at = NULL,
               closed_at = NULL, still_open = 1,
               reopened_at = CASE WHEN ? THEN ? ELSE reopened_at END,
               last_verified_at = CASE WHEN ? THEN ? ELSE last_verified_at END
               WHERE id = ?""",
            (
                JobLifecycleStatus.OPEN.value,
                int(reopened),
                timestamp,
                int(explicitly_verified),
                timestamp,
                internal_id,
            ),
        )
        self.connection.commit()

    def update_lifecycle_missing(
        self,
        internal_id: int,
        *,
        status: JobLifecycleStatus,
        misses: int,
        now: datetime,
        explicitly_verified: bool,
    ) -> None:
        """Registra um miss ou fechamento explícito, preservando o CRM manual."""

        timestamp = _as_utc(now).isoformat()
        still_open = {
            JobLifecycleStatus.OPEN: 1,
            JobLifecycleStatus.POSSIBLY_CLOSED: None,
            JobLifecycleStatus.CLOSED: 0,
            JobLifecycleStatus.UNKNOWN: None,
        }[status]
        self.connection.execute(
            """UPDATE opportunities SET
               lifecycle_status = ?, consecutive_misses = ?,
               first_missing_at = COALESCE(first_missing_at, ?),
               last_missing_at = ?, still_open = ?,
               closed_at = CASE WHEN ? = 'CLOSED' THEN COALESCE(closed_at, ?) ELSE closed_at END,
               last_verified_at = CASE WHEN ? THEN ? ELSE last_verified_at END
               WHERE id = ?""",
            (
                status.value,
                misses,
                timestamp,
                timestamp,
                still_open,
                status.value,
                timestamp,
                int(explicitly_verified),
                timestamp,
                internal_id,
            ),
        )
        self.connection.commit()

    def get(self, internal_id: int) -> StoredOpportunity | None:
        row = self.connection.execute(
            "SELECT * FROM opportunities WHERE id = ?", (internal_id,)
        ).fetchone()
        return self._from_row(row) if row else None

    def list_all(self) -> list[StoredOpportunity]:
        rows = self.connection.execute("SELECT * FROM opportunities ORDER BY id").fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> StoredOpportunity:
        positive_reasons = json.loads(row["positive_reasons"])
        potential_gaps = json.loads(row["potential_gaps"])
        unknowns = json.loads(row["unknowns"])
        tracking = ApplicationTracking(
            application_status=ApplicationStatus(row["application_status"]),
            applied_date=date.fromisoformat(row["applied_date"]) if row["applied_date"] else None,
            recruiter_name=row["recruiter_name"],
            recruiter_email=row["recruiter_email"],
            next_step=row["next_step"],
            next_step_date=date.fromisoformat(row["next_step_date"]) if row["next_step_date"] else None,
            notes=row["notes"],
        )
        job = JobOpportunity(
            company=row["company"], role=row["role"], job_url=row["job_url"],
            source=row["source"], location=row["location"],
            remote=_bool_from_db(row["remote"]), brazil_eligible=_bool_from_db(row["brazil_eligible"]),
            employment_type=row["employment_type"], description=row["description"],
            requirements=json.loads(row["requirements"]), responsibilities=json.loads(row["responsibilities"]),
            preferred_qualifications=json.loads(row["preferred_qualifications"]),
            tools_mentioned=json.loads(row["tools_mentioned"]), industries_mentioned=json.loads(row["industries_mentioned"]),
            years_experience_required=row["years_experience_required"],
            full_cycle_sales_required=_bool_from_db(row["full_cycle_sales_required"]),
            outbound_sales_required=_bool_from_db(row["outbound_sales_required"]),
            inbound_sales_mentioned=_bool_from_db(row["inbound_sales_mentioned"]),
            b2b_experience_required=_bool_from_db(row["b2b_experience_required"]),
            saas_experience_required=_bool_from_db(row["saas_experience_required"]),
            base_salary=row["base_salary"], ote=row["ote"], salary_min=row["salary_min"],
            salary_max=row["salary_max"], salary_currency=row["salary_currency"],
            salary_period=row["salary_period"], salary_text=row["salary_text"],
            external_id=row["external_id"], job_level=row["job_level"],
            date_found=date.fromisoformat(row["date_found"]),
            date_posted=date.fromisoformat(row["date_posted"]) if row["date_posted"] else None,
            match_score=row["match_score"], why_match=positive_reasons,
            potential_gaps=potential_gaps, still_open=_bool_from_db(row["still_open"]),
            lifecycle_status=JobLifecycleStatus(row["lifecycle_status"]),
            consecutive_misses=int(row["consecutive_misses"]),
            first_missing_at=datetime.fromisoformat(row["first_missing_at"]) if row["first_missing_at"] else None,
            last_missing_at=datetime.fromisoformat(row["last_missing_at"]) if row["last_missing_at"] else None,
            closed_at=datetime.fromisoformat(row["closed_at"]) if row["closed_at"] else None,
            reopened_at=datetime.fromisoformat(row["reopened_at"]) if row["reopened_at"] else None,
            last_verified_at=datetime.fromisoformat(row["last_verified_at"]) if row["last_verified_at"] else None,
            last_checked=datetime.fromisoformat(row["last_checked"]), tracking=tracking,
        )
        return StoredOpportunity(
            internal_id=int(row["id"]), opportunity=job,
            first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
            last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
            match_score=int(row["match_score"]),
            retention_decision=RetentionDecision(row["retention_decision"]),
            role_family=RoleFamily(row["role_family"]), seniority=Seniority(row["seniority"]),
            positive_reasons=positive_reasons,
            potential_gaps=potential_gaps, unknowns=unknowns,
        )


def sync_opportunities(
    processed: Iterable[ProcessedOpportunity] | PipelineResult,
    repository: JobRepository,
    *,
    now: datetime | None = None,
) -> SyncResult:
    """Sincroniza a saída do pipeline sem executar discovery."""

    items = processed.ranked_opportunities if isinstance(processed, PipelineResult) else processed
    return repository.sync(items, now=now)
