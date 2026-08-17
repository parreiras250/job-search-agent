"""Persistência SQLite local para oportunidades já processadas pelo pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timezone
from enum import Enum
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from .models import (
    ApplicationStatus,
    ApplicationTracking,
    CompanyRecord,
    JobLifecycleStatus,
    JobOpportunity,
    LocationRestriction,
    RoleFamily,
    Seniority,
)
from .pipeline import PipelineResult, ProcessedOpportunity
from .rules import (
    EligibilityStatus,
    OpportunityRisk,
    RetentionDecision,
    TimezoneCompatibility,
    normalize_company,
    normalize_job_url,
    normalize_role,
)


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
    eligibility: EligibilityStatus
    timezone_compatibility: TimezoneCompatibility
    opportunity_risks: tuple[OpportunityRisk, ...]
    decision_reasons: list[str]


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
    observations_created: int = 0
    observations_updated: int = 0
    cross_source_observations_added: int = 0
    seen_observation_ids: set[int] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class SourceObservation:
    """Evidência persistente de uma opportunity em uma source específica."""

    observation_id: int
    opportunity_id: int
    source_id: str
    source_family: str
    source_instance: str
    source_type: str
    external_id: str | None
    observed_url: str
    first_seen_at: datetime
    last_seen_at: datetime
    last_checked_at: datetime
    lifecycle_authority: str
    active: bool
    consecutive_misses: int
    first_missing_at: datetime | None
    last_missing_at: datetime | None


_AUTOMATIC_COLUMNS = (
    "external_id", "company", "role", "job_url", "source", "location",
    "remote", "brazil_eligible", "employment_type", "description",
    "requirements", "responsibilities", "preferred_qualifications",
    "tools_mentioned", "industries_mentioned", "years_experience_required",
    "full_cycle_sales_required", "outbound_sales_required",
    "inbound_sales_mentioned", "b2b_experience_required",
    "saas_experience_required", "base_salary", "ote", "salary_min",
    "salary_max", "salary_currency", "salary_period", "salary_text",
    "job_level", "source_id", "source_family", "source_instance",
    "location_restrictions", "timezone_restrictions",
    "date_posted", "match_score", "retention_decision",
    "role_family", "seniority", "positive_reasons", "potential_gaps",
    "unknowns", "eligibility", "timezone_compatibility",
    "opportunity_risks", "decision_reasons",
)

SCHEMA_VERSION = 8


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


def _location_restrictions_from_db(value: str | None) -> list[LocationRestriction] | None:
    """Lê tanto o formato estruturado atual quanto listas de nomes do schema v7."""

    if not value:
        return None
    decoded = json.loads(value)
    if decoded is None:
        return None
    return [
        LocationRestriction(**item)
        if isinstance(item, dict)
        else LocationRestriction(alpha2=None, name=item, slug=None)
        for item in decoded
    ]


class JobRepository:
    """Centraliza schema, consultas e gravações do histórico SQLite."""

    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
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
                source_id TEXT,
                source_family TEXT,
                source_instance TEXT,
                location_restrictions TEXT,
                timezone_restrictions TEXT,
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
                eligibility TEXT NOT NULL DEFAULT 'UNCERTAIN',
                timezone_compatibility TEXT NOT NULL DEFAULT 'UNKNOWN',
                opportunity_risks TEXT NOT NULL DEFAULT '[]',
                decision_reasons TEXT NOT NULL DEFAULT '[]',
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
            CREATE TABLE IF NOT EXISTS source_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id INTEGER NOT NULL,
                observation_key TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_family TEXT NOT NULL,
                source_instance TEXT NOT NULL,
                source_type TEXT NOT NULL,
                external_id TEXT,
                observed_url TEXT NOT NULL,
                observed_url_normalized TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                last_checked_at TEXT NOT NULL,
                lifecycle_authority TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                consecutive_misses INTEGER NOT NULL DEFAULT 0,
                first_missing_at TEXT,
                last_missing_at TEXT,
                FOREIGN KEY(opportunity_id) REFERENCES opportunities(id),
                UNIQUE(opportunity_id, observation_key)
            )
            """
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_observation_opportunity "
            "ON source_observations(opportunity_id)"
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_observation_source_instance "
            "ON source_observations(source_instance)"
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
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tracked_companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_key TEXT NOT NULL UNIQUE,
                company_name TEXT NOT NULL,
                careers_url TEXT,
                ats_family TEXT NOT NULL,
                ats_identifier TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                priority INTEGER NOT NULL DEFAULT 100,
                remote_policy TEXT,
                latam_evidence TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_checked_at TEXT,
                last_success_at TEXT,
                failure_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_tracked_companies_enabled_priority "
            "ON tracked_companies(enabled, priority DESC, company_key)"
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
            "source_id": "TEXT",
            "source_family": "TEXT",
            "source_instance": "TEXT",
            "location_restrictions": "TEXT",
            "timezone_restrictions": "TEXT",
            "eligibility": "TEXT NOT NULL DEFAULT 'UNCERTAIN'",
            "timezone_compatibility": "TEXT NOT NULL DEFAULT 'UNKNOWN'",
            "opportunity_risks": "TEXT NOT NULL DEFAULT '[]'",
            "decision_reasons": "TEXT NOT NULL DEFAULT '[]'",
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
        # Migração explícita dos rótulos históricos conhecidos. A lógica de
        # lifecycle não interpreta mais substrings de texto.
        self.connection.execute(
            """UPDATE opportunities SET
               source_id = CASE source
                   WHEN 'Jobicy public Remote Jobs API' THEN 'jobicy'
                   WHEN 'Remotive' THEN 'remotive'
                   ELSE source_id END,
               source_family = CASE source
                   WHEN 'Jobicy public Remote Jobs API' THEN 'jobicy'
                   WHEN 'Remotive' THEN 'remotive'
                   ELSE source_family END,
               source_instance = CASE source
                   WHEN 'Jobicy public Remote Jobs API' THEN 'jobicy:global'
                   WHEN 'Remotive' THEN 'remotive:global'
                   ELSE source_instance END
               WHERE source_id IS NULL"""
        )
        # Cada registro histórico ganha exatamente uma observação inicial. A
        # chave determinística e UNIQUE tornam a migração idempotente.
        migrated_columns = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(opportunities)")
        }
        observation_migration_columns = {
            "id", "source", "source_id", "source_family", "source_instance",
            "external_id", "job_url", "job_url_normalized", "first_seen_at",
            "last_seen_at", "last_checked", "lifecycle_status",
            "consecutive_misses", "first_missing_at", "last_missing_at",
        }
        if observation_migration_columns <= migrated_columns:
            self.connection.execute(
                """INSERT OR IGNORE INTO source_observations (
               opportunity_id, observation_key, source_id, source_family,
               source_instance, source_type, external_id, observed_url,
               observed_url_normalized, first_seen_at, last_seen_at,
               last_checked_at, lifecycle_authority, active,
               consecutive_misses, first_missing_at, last_missing_at
               )
               SELECT id,
                      COALESCE(source_instance, 'legacy:' || id) || '|' ||
                      CASE WHEN external_id IS NOT NULL AND external_id != ''
                           THEN 'external:' || external_id
                           ELSE 'url:' || job_url_normalized END,
                      COALESCE(source_id, 'legacy-' || id),
                      COALESCE(source_family, 'legacy'),
                      COALESCE(source_instance, 'legacy:' || id),
                      CASE source_id
                          WHEN 'jobicy' THEN 'GLOBAL_BOARD'
                          WHEN 'remotive' THEN 'AGGREGATOR'
                          WHEN 'weworkremotely' THEN 'FEED'
                          ELSE 'UNKNOWN' END,
                      external_id, job_url, job_url_normalized,
                      first_seen_at, last_seen_at, last_checked,
                      'OBSERVATIONAL',
                      CASE WHEN lifecycle_status = 'CLOSED' THEN 0 ELSE 1 END,
                      consecutive_misses, first_missing_at, last_missing_at
                   FROM opportunities"""
            )
        current_version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if current_version < SCHEMA_VERSION:
            self.connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) AS count FROM opportunities").fetchone()
        return int(row["count"])

    def observation_count(self) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM source_observations"
        ).fetchone()
        return int(row["count"])

    @staticmethod
    def _company_from_row(row: sqlite3.Row) -> CompanyRecord:
        return CompanyRecord(
            id=int(row["id"]),
            company_key=row["company_key"],
            company_name=row["company_name"],
            careers_url=row["careers_url"],
            ats_family=row["ats_family"],
            ats_identifier=row["ats_identifier"],
            enabled=bool(row["enabled"]),
            priority=int(row["priority"]),
            remote_policy=row["remote_policy"],
            latam_evidence=row["latam_evidence"],
            notes=row["notes"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            last_checked_at=(
                datetime.fromisoformat(row["last_checked_at"])
                if row["last_checked_at"] else None
            ),
            last_success_at=(
                datetime.fromisoformat(row["last_success_at"])
                if row["last_success_at"] else None
            ),
            failure_count=int(row["failure_count"]),
        )

    def add_company(
        self,
        company_key: str,
        company_name: str,
        ats_family: str,
        ats_identifier: str,
        *,
        enabled: bool = True,
        priority: int = 100,
        careers_url: str | None = None,
        remote_policy: str | None = None,
        latam_evidence: str | None = None,
        notes: str | None = None,
        now: datetime | None = None,
    ) -> CompanyRecord:
        timestamp = _as_utc(now or _utc_now())
        company = CompanyRecord(
            id=None,
            company_key=company_key.strip().casefold(),
            company_name=company_name.strip(),
            ats_family=ats_family.strip().casefold(),
            ats_identifier=ats_identifier.strip(),
            enabled=enabled,
            priority=priority,
            careers_url=careers_url,
            remote_policy=remote_policy,
            latam_evidence=latam_evidence,
            notes=notes,
            created_at=timestamp,
            updated_at=timestamp,
        )
        try:
            cursor = self.connection.execute(
                """INSERT INTO tracked_companies (
                   company_key, company_name, careers_url, ats_family,
                   ats_identifier, enabled, priority, remote_policy,
                   latam_evidence, notes, created_at, updated_at,
                   failure_count
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (
                    company.company_key, company.company_name, company.careers_url,
                    company.ats_family, company.ats_identifier,
                    int(company.enabled), company.priority, company.remote_policy,
                    company.latam_evidence, company.notes,
                    timestamp.isoformat(), timestamp.isoformat(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"duplicate company_key: {company.company_key}") from exc
        self.connection.commit()
        stored = self.get_company(company.company_key)
        assert stored is not None
        return stored

    def get_company(self, company_key: str) -> CompanyRecord | None:
        row = self.connection.execute(
            "SELECT * FROM tracked_companies WHERE company_key = ?",
            (company_key.strip().casefold(),),
        ).fetchone()
        return self._company_from_row(row) if row else None

    def list_companies(self, *, enabled_only: bool = False) -> list[CompanyRecord]:
        where = "WHERE enabled = 1" if enabled_only else ""
        rows = self.connection.execute(
            f"SELECT * FROM tracked_companies {where} "
            "ORDER BY priority DESC, company_key ASC"
        ).fetchall()
        return [self._company_from_row(row) for row in rows]

    def update_company(
        self,
        company_key: str,
        *,
        company_name: str | None = None,
        ats_family: str | None = None,
        ats_identifier: str | None = None,
        priority: int | None = None,
        careers_url: str | None = None,
        remote_policy: str | None = None,
        latam_evidence: str | None = None,
        notes: str | None = None,
        now: datetime | None = None,
    ) -> CompanyRecord:
        current = self.get_company(company_key)
        if current is None:
            raise KeyError(f"unknown company_key: {company_key}")
        timestamp = _as_utc(now or _utc_now())
        updated = CompanyRecord(
            id=current.id,
            company_key=current.company_key,
            company_name=(company_name if company_name is not None else current.company_name).strip(),
            ats_family=(ats_family if ats_family is not None else current.ats_family).strip().casefold(),
            ats_identifier=(ats_identifier if ats_identifier is not None else current.ats_identifier).strip(),
            enabled=current.enabled,
            priority=priority if priority is not None else current.priority,
            careers_url=careers_url if careers_url is not None else current.careers_url,
            remote_policy=remote_policy if remote_policy is not None else current.remote_policy,
            latam_evidence=latam_evidence if latam_evidence is not None else current.latam_evidence,
            notes=notes if notes is not None else current.notes,
            created_at=current.created_at,
            updated_at=timestamp,
            last_checked_at=current.last_checked_at,
            last_success_at=current.last_success_at,
            failure_count=current.failure_count,
        )
        self.connection.execute(
            """UPDATE tracked_companies SET
               company_name = ?, careers_url = ?, ats_family = ?,
               ats_identifier = ?, priority = ?, remote_policy = ?,
               latam_evidence = ?, notes = ?, updated_at = ?
               WHERE company_key = ?""",
            (
                updated.company_name, updated.careers_url, updated.ats_family,
                updated.ats_identifier, updated.priority, updated.remote_policy,
                updated.latam_evidence, updated.notes, timestamp.isoformat(),
                updated.company_key,
            ),
        )
        self.connection.commit()
        return self.get_company(updated.company_key)  # type: ignore[return-value]

    def _set_company_enabled(
        self, company_key: str, enabled: bool, *, now: datetime | None = None
    ) -> CompanyRecord:
        if self.get_company(company_key) is None:
            raise KeyError(f"unknown company_key: {company_key}")
        timestamp = _as_utc(now or _utc_now()).isoformat()
        self.connection.execute(
            "UPDATE tracked_companies SET enabled = ?, updated_at = ? "
            "WHERE company_key = ?",
            (int(enabled), timestamp, company_key.strip().casefold()),
        )
        self.connection.commit()
        return self.get_company(company_key)  # type: ignore[return-value]

    def enable_company(self, company_key: str, *, now: datetime | None = None) -> CompanyRecord:
        return self._set_company_enabled(company_key, True, now=now)

    def disable_company(self, company_key: str, *, now: datetime | None = None) -> CompanyRecord:
        return self._set_company_enabled(company_key, False, now=now)

    def record_company_check(
        self, company_key: str, *, succeeded: bool, now: datetime | None = None
    ) -> CompanyRecord:
        if self.get_company(company_key) is None:
            raise KeyError(f"unknown company_key: {company_key}")
        timestamp = _as_utc(now or _utc_now()).isoformat()
        if succeeded:
            self.connection.execute(
                """UPDATE tracked_companies SET last_checked_at = ?,
                   last_success_at = ?, failure_count = 0, updated_at = ?
                   WHERE company_key = ?""",
                (timestamp, timestamp, timestamp, company_key.strip().casefold()),
            )
        else:
            self.connection.execute(
                """UPDATE tracked_companies SET last_checked_at = ?,
                   failure_count = failure_count + 1, updated_at = ?
                   WHERE company_key = ?""",
                (timestamp, timestamp, company_key.strip().casefold()),
            )
        self.connection.commit()
        return self.get_company(company_key)  # type: ignore[return-value]

    @staticmethod
    def _observation_from_row(row: sqlite3.Row) -> SourceObservation:
        return SourceObservation(
            observation_id=int(row["id"]),
            opportunity_id=int(row["opportunity_id"]),
            source_id=row["source_id"],
            source_family=row["source_family"],
            source_instance=row["source_instance"],
            source_type=row["source_type"],
            external_id=row["external_id"],
            observed_url=row["observed_url"],
            first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
            last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
            last_checked_at=datetime.fromisoformat(row["last_checked_at"]),
            lifecycle_authority=row["lifecycle_authority"],
            active=bool(row["active"]),
            consecutive_misses=int(row["consecutive_misses"]),
            first_missing_at=(
                datetime.fromisoformat(row["first_missing_at"])
                if row["first_missing_at"] else None
            ),
            last_missing_at=(
                datetime.fromisoformat(row["last_missing_at"])
                if row["last_missing_at"] else None
            ),
        )

    def get_observations(self, opportunity_id: int) -> list[SourceObservation]:
        rows = self.connection.execute(
            "SELECT * FROM source_observations WHERE opportunity_id = ? ORDER BY id",
            (opportunity_id,),
        ).fetchall()
        return [self._observation_from_row(row) for row in rows]

    def list_opportunity_sources(self, opportunity_id: int) -> list[str]:
        return sorted(
            {item.source_id for item in self.get_observations(opportunity_id)},
            key=str.casefold,
        )

    def observation_overlap_counts(self) -> tuple[int, int]:
        rows = self.connection.execute(
            """SELECT opportunity_id, COUNT(DISTINCT source_instance) AS count
               FROM source_observations GROUP BY opportunity_id"""
        ).fetchall()
        return (
            sum(int(row["count"]) == 1 for row in rows),
            sum(int(row["count"]) >= 2 for row in rows),
        )

    @staticmethod
    def _observation_key(job: JobOpportunity) -> str:
        instance = job.source_instance or f"legacy:{job.source_id or job.source}"
        if job.external_id:
            return f"{instance}|external:{job.external_id}"
        return f"{instance}|url:{normalize_job_url(job.job_url)}"

    def _upsert_observation(
        self, opportunity_id: int, job: JobOpportunity, now: datetime
    ) -> tuple[int, bool]:
        key = self._observation_key(job)
        existing = self.connection.execute(
            """SELECT * FROM source_observations
               WHERE opportunity_id = ? AND observation_key = ?""",
            (opportunity_id, key),
        ).fetchone()
        timestamp = now.isoformat()
        if existing is not None:
            self.connection.execute(
                """UPDATE source_observations SET
                   observed_url = ?, observed_url_normalized = ?,
                   last_seen_at = ?, last_checked_at = ?, active = 1,
                   consecutive_misses = 0, first_missing_at = NULL,
                   last_missing_at = NULL
                   WHERE id = ?""",
                (
                    job.job_url, normalize_job_url(job.job_url), timestamp,
                    timestamp, existing["id"],
                ),
            )
            return int(existing["id"]), False
        cursor = self.connection.execute(
            """INSERT INTO source_observations (
               opportunity_id, observation_key, source_id, source_family,
               source_instance, source_type, external_id, observed_url,
               observed_url_normalized, first_seen_at, last_seen_at,
               last_checked_at, lifecycle_authority, active,
               consecutive_misses
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0)""",
            (
                opportunity_id, key, job.source_id or "legacy",
                job.source_family or "legacy",
                job.source_instance or f"legacy:{job.source_id or job.source}",
                job.source_type or "UNKNOWN", job.external_id, job.job_url,
                normalize_job_url(job.job_url), timestamp, timestamp, timestamp,
                job.lifecycle_authority or "OBSERVATIONAL",
            ),
        )
        return int(cursor.lastrowid), True

    def mark_observation_missing(
        self, observation_id: int, *, now: datetime
    ) -> SourceObservation:
        timestamp = _as_utc(now).isoformat()
        self.connection.execute(
            """UPDATE source_observations SET
               active = 0, consecutive_misses = consecutive_misses + 1,
               first_missing_at = COALESCE(first_missing_at, ?),
               last_missing_at = ?, last_checked_at = ?
               WHERE id = ?""",
            (timestamp, timestamp, timestamp, observation_id),
        )
        row = self.connection.execute(
            "SELECT * FROM source_observations WHERE id = ?", (observation_id,)
        ).fetchone()
        assert row is not None
        return self._observation_from_row(row)

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
            "source_id": job.source_id,
            "source_family": job.source_family,
            "source_instance": job.source_instance,
            "location_restrictions": _dump(
                [asdict(item) for item in job.location_restrictions]
                if job.location_restrictions is not None else None
            ),
            "timezone_restrictions": _dump(job.timezone_restrictions),
            "date_posted": job.date_posted.isoformat() if job.date_posted else None,
            "match_score": item.match_score,
            "retention_decision": item.retention_decision.value,
            "role_family": item.role_family.value,
            "seniority": item.seniority.value,
            "positive_reasons": _dump(item.positive_reasons),
            "potential_gaps": _dump(item.potential_gaps),
            "unknowns": _dump(item.unknowns),
            "eligibility": item.eligibility.value,
            "timezone_compatibility": item.timezone_compatibility.value,
            "opportunity_risks": _dump(
                [risk.value for risk in item.opportunity_risks]
            ),
            "decision_reasons": _dump(item.decision_reasons),
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
        primary_observation = next(
            (
                observation
                for observation in self.get_observations(int(existing["id"]))
                if observation.source_instance == existing["source_instance"]
            ),
            None,
        )
        promote_authoritative = (
            job.lifecycle_authority == "AUTHORITATIVE"
            and (
                primary_observation is None
                or primary_observation.lifecycle_authority != "AUTHORITATIVE"
            )
        )
        same_primary_source = (
            not existing["source_instance"]
            or existing["source_instance"] == job.source_instance
        )
        changed = (same_primary_source or promote_authoritative) and any(
            existing[column] != automatic[column] for column in _AUTOMATIC_COLUMNS
        )
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
        opportunities: Iterable[ProcessedOpportunity] | PipelineResult,
        *,
        now: datetime | None = None,
    ) -> SyncResult:
        pipeline = opportunities if isinstance(opportunities, PipelineResult) else None
        items = list(
            pipeline.ranked_opportunities if pipeline is not None else opportunities
        )
        timestamp = _as_utc(now or _utc_now())
        grouped: dict[SyncStatus, list[SyncedOpportunity]] = {
            status: [] for status in SyncStatus
        }
        errors: list[SyncError] = []
        observations_created = observations_updated = cross_source_added = 0
        seen_observation_ids: set[int] = set()
        primary_ids: dict[int, int] = {}
        primary_items: dict[int, ProcessedOpportunity] = {}
        for index, item in enumerate(items):
            savepoint = f"opportunity_{index}"
            self.connection.execute(f"SAVEPOINT {savepoint}")
            try:
                synced = self._sync_one(item, timestamp)
                previous_observations = self.get_observations(synced.internal_id)
                observation_id, created = self._upsert_observation(
                    synced.internal_id, item.original_job, timestamp
                )
                seen_observation_ids.add(observation_id)
                observations_created += int(created)
                observations_updated += int(not created)
                if created and previous_observations:
                    cross_source_added += int(
                        all(
                            observation.source_instance
                            != item.original_job.source_instance
                            for observation in previous_observations
                        )
                    )
                primary_ids[id(item.original_job)] = synced.internal_id
                primary_items[id(item.original_job)] = item
                self.connection.execute(f"RELEASE SAVEPOINT {savepoint}")
                grouped[synced.status].append(synced)
            except (sqlite3.Error, TypeError, ValueError) as exc:
                self.connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                self.connection.execute(f"RELEASE SAVEPOINT {savepoint}")
                errors.append(SyncError(item, str(exc)))
        if pipeline is not None:
            for index, duplicate in enumerate(pipeline.duplicate_records):
                opportunity_id = primary_ids.get(id(duplicate.primary))
                if opportunity_id is None:
                    continue
                savepoint = f"observation_{index}"
                self.connection.execute(f"SAVEPOINT {savepoint}")
                try:
                    previous = self.get_observations(opportunity_id)
                    primary_item = primary_items.get(id(duplicate.primary))
                    if primary_item is not None:
                        self._sync_one(
                            replace(
                                primary_item,
                                original_job=duplicate.duplicate,
                                normalized_job=duplicate.duplicate,
                            ),
                            timestamp,
                        )
                    observation_id, created = self._upsert_observation(
                        opportunity_id, duplicate.duplicate, timestamp
                    )
                    seen_observation_ids.add(observation_id)
                    observations_created += int(created)
                    observations_updated += int(not created)
                    if created and previous:
                        cross_source_added += int(
                            all(
                                item.source_instance
                                != duplicate.duplicate.source_instance
                                for item in previous
                            )
                        )
                    self.connection.execute(f"RELEASE SAVEPOINT {savepoint}")
                except (sqlite3.Error, TypeError, ValueError) as exc:
                    self.connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                    self.connection.execute(f"RELEASE SAVEPOINT {savepoint}")
                    primary_item = primary_items.get(id(duplicate.primary))
                    if primary_item is not None:
                        errors.append(SyncError(primary_item, str(exc)))
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
            observations_created=observations_created,
            observations_updated=observations_updated,
            cross_source_observations_added=cross_source_added,
            seen_observation_ids=seen_observation_ids,
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
        opportunity_risks = tuple(
            OpportunityRisk(value) for value in json.loads(row["opportunity_risks"])
        )
        decision_reasons = json.loads(row["decision_reasons"])
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
            source_id=row["source_id"], source_family=row["source_family"],
            source_instance=row["source_instance"],
            location_restrictions=_location_restrictions_from_db(
                row["location_restrictions"]
            ),
            timezone_restrictions=(
                json.loads(row["timezone_restrictions"])
                if row["timezone_restrictions"] else None
            ),
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
            eligibility=EligibilityStatus(row["eligibility"]),
            timezone_compatibility=TimezoneCompatibility(
                row["timezone_compatibility"]
            ),
            opportunity_risks=opportunity_risks,
            decision_reasons=decision_reasons,
        )


def sync_opportunities(
    processed: Iterable[ProcessedOpportunity] | PipelineResult,
    repository: JobRepository,
    *,
    now: datetime | None = None,
) -> SyncResult:
    """Sincroniza a saída do pipeline sem executar discovery."""

    return repository.sync(processed, now=now)
