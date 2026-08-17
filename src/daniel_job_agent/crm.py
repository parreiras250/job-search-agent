"""Camada local de CRM sobre o histórico mantido pelo JobRepository."""

from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import Enum
from typing import TypeAlias

from .models import ApplicationStatus, JobLifecycleStatus, RoleFamily, Seniority
from .repository import JobRepository, StoredOpportunity
from .rules import (
    EligibilityStatus,
    OpportunityRisk,
    RetentionDecision,
    TimezoneCompatibility,
)


AUTOMATIC_FIELDS = (
    "internal_id",
    "company",
    "role",
    "job_url",
    "source",
    "location",
    "match_score",
    "retention_decision",
    "role_family",
    "seniority",
    "still_open",
    "lifecycle_status",
    "consecutive_misses",
    "first_missing_at",
    "last_missing_at",
    "closed_at",
    "reopened_at",
    "last_verified_at",
    "date_found",
    "date_posted",
    "first_seen_at",
    "last_seen_at",
    "last_checked",
    "positive_reasons",
    "potential_gaps",
    "unknowns",
    "eligibility",
    "timezone_compatibility",
    "opportunity_risks",
    "decision_reasons",
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_period",
    "salary_text",
    "observed_sources",
)

MANUAL_FIELDS = (
    "application_status",
    "applied_date",
    "recruiter_name",
    "recruiter_email",
    "next_step",
    "next_step_date",
    "notes",
)

# Contrato estável para uma futura interface tabular, como Google Sheets.
CRM_COLUMNS = (
    "internal_id",
    "company",
    "role",
    "match_score",
    "retention_decision",
    "location",
    "source",
    "job_url",
    "date_found",
    "date_posted",
    "still_open",
    "lifecycle_status",
    "consecutive_misses",
    "first_missing_at",
    "last_missing_at",
    "closed_at",
    "reopened_at",
    "last_verified_at",
    "application_status",
    "applied_date",
    "recruiter_name",
    "recruiter_email",
    "next_step",
    "next_step_date",
    "notes",
    "positive_reasons",
    "potential_gaps",
    "unknowns",
    "role_family",
    "seniority",
    "eligibility",
    "timezone_compatibility",
    "opportunity_risks",
    "decision_reasons",
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_period",
    "salary_text",
    "observed_sources",
    "first_seen_at",
    "last_seen_at",
    "last_checked",
)

SimpleValue: TypeAlias = str | int | float | bool | None


class CRMValidationError(ValueError):
    """Entrada manual inválida ou tentativa de editar campo automático."""


class CRMRecordNotFound(LookupError):
    """ID interno não encontrado no histórico local."""


@dataclass(frozen=True, slots=True)
class CRMRecord:
    internal_id: int
    company: str
    role: str
    job_url: str
    source: str
    location: str
    match_score: int
    retention_decision: RetentionDecision
    role_family: RoleFamily
    seniority: Seniority
    still_open: bool | None
    lifecycle_status: JobLifecycleStatus
    consecutive_misses: int
    first_missing_at: datetime | None
    last_missing_at: datetime | None
    closed_at: datetime | None
    reopened_at: datetime | None
    last_verified_at: datetime | None
    date_found: date
    date_posted: date | None
    first_seen_at: datetime
    last_seen_at: datetime
    last_checked: datetime
    positive_reasons: list[str]
    potential_gaps: list[str]
    unknowns: list[str]
    eligibility: EligibilityStatus
    timezone_compatibility: TimezoneCompatibility
    opportunity_risks: tuple[OpportunityRisk, ...]
    decision_reasons: list[str]
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    salary_period: str | None
    salary_text: str | None
    observed_sources: str
    application_status: ApplicationStatus
    applied_date: date | None
    recruiter_name: str | None
    recruiter_email: str | None
    next_step: str | None
    next_step_date: date | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class CRMTable:
    headers: list[str]
    rows: list[list[SimpleValue]]


def _record_from_stored(
    stored: StoredOpportunity, observed_sources: list[str]
) -> CRMRecord:
    job = stored.opportunity
    tracking = job.tracking
    return CRMRecord(
        internal_id=stored.internal_id,
        company=job.company,
        role=job.role,
        job_url=job.job_url,
        source=job.source,
        location=job.location,
        match_score=stored.match_score,
        retention_decision=stored.retention_decision,
        role_family=stored.role_family,
        seniority=stored.seniority,
        still_open=job.still_open,
        lifecycle_status=job.lifecycle_status,
        consecutive_misses=job.consecutive_misses,
        first_missing_at=job.first_missing_at,
        last_missing_at=job.last_missing_at,
        closed_at=job.closed_at,
        reopened_at=job.reopened_at,
        last_verified_at=job.last_verified_at,
        date_found=job.date_found,
        date_posted=job.date_posted,
        first_seen_at=stored.first_seen_at,
        last_seen_at=stored.last_seen_at,
        last_checked=job.last_checked,
        positive_reasons=list(stored.positive_reasons),
        potential_gaps=list(stored.potential_gaps),
        unknowns=list(stored.unknowns),
        eligibility=stored.eligibility,
        timezone_compatibility=stored.timezone_compatibility,
        opportunity_risks=stored.opportunity_risks,
        decision_reasons=list(stored.decision_reasons),
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        salary_period=job.salary_period,
        salary_text=job.salary_text,
        observed_sources=" | ".join(observed_sources),
        application_status=tracking.application_status,
        applied_date=tracking.applied_date,
        recruiter_name=tracking.recruiter_name,
        recruiter_email=tracking.recruiter_email,
        next_step=tracking.next_step,
        next_step_date=tracking.next_step_date,
        notes=tracking.notes,
    )


def _parse_status(value: object) -> ApplicationStatus:
    if isinstance(value, ApplicationStatus):
        return value
    if isinstance(value, str):
        try:
            return ApplicationStatus(value.strip().upper())
        except ValueError as exc:
            raise CRMValidationError(f"Invalid application status: {value}") from exc
    raise CRMValidationError("application_status must be an ApplicationStatus or text")


def _parse_date(value: object, field_name: str) -> date | None:
    if value is None or isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise CRMValidationError(
                f"Invalid {field_name}; expected YYYY-MM-DD"
            ) from exc
    raise CRMValidationError(f"{field_name} must be a date, YYYY-MM-DD, or None")


class LocalCRM:
    """Oferece leitura e atualização segura dos campos manuais."""

    def __init__(self, repository: JobRepository) -> None:
        self.repository = repository

    def get(self, internal_id: int) -> CRMRecord | None:
        stored = self.repository.get(internal_id)
        return (
            _record_from_stored(
                stored, self.repository.list_opportunity_sources(internal_id)
            )
            if stored else None
        )

    def list_records(
        self,
        *,
        application_status: ApplicationStatus | str | None = None,
        retention_decision: RetentionDecision | str | None = None,
        still_open: bool | None = None,
        lifecycle_status: JobLifecycleStatus | str | None = None,
        source: str | None = None,
        minimum_score: int | None = None,
        order: str = "default",
    ) -> list[CRMRecord]:
        records = [
            _record_from_stored(
                item, self.repository.list_opportunity_sources(item.internal_id)
            )
            for item in self.repository.list_all()
        ]
        if application_status is not None:
            status = _parse_status(application_status)
            records = [item for item in records if item.application_status is status]
        if retention_decision is not None:
            try:
                decision = (
                    retention_decision
                    if isinstance(retention_decision, RetentionDecision)
                    else RetentionDecision(retention_decision.strip().upper())
                )
            except (AttributeError, ValueError) as exc:
                raise CRMValidationError(
                    f"Invalid retention decision: {retention_decision}"
                ) from exc
            records = [item for item in records if item.retention_decision is decision]
        if still_open is not None:
            records = [item for item in records if item.still_open is still_open]
        if lifecycle_status is not None:
            try:
                status = (
                    lifecycle_status
                    if isinstance(lifecycle_status, JobLifecycleStatus)
                    else JobLifecycleStatus(lifecycle_status.strip().upper())
                )
            except (AttributeError, ValueError) as exc:
                raise CRMValidationError(
                    f"Invalid lifecycle status: {lifecycle_status}"
                ) from exc
            records = [item for item in records if item.lifecycle_status is status]
        if source is not None:
            records = [item for item in records if item.source.casefold() == source.casefold()]
        if minimum_score is not None:
            records = [item for item in records if item.match_score >= minimum_score]

        if order == "newest":
            return sorted(
                records,
                key=lambda item: (item.last_seen_at, item.internal_id),
                reverse=True,
            )
        if order != "default":
            raise CRMValidationError("order must be 'default' or 'newest'")
        decision_order = {
            RetentionDecision.KEEP: 0,
            RetentionDecision.REVIEW: 1,
            RetentionDecision.REJECT: 2,
        }
        return sorted(
            records,
            key=lambda item: (
                decision_order[item.retention_decision],
                -item.match_score,
                item.company.casefold(),
                item.role.casefold(),
            ),
        )

    def update_manual_fields(self, internal_id: int, **changes: object) -> CRMRecord:
        invalid_fields = sorted(set(changes) - set(MANUAL_FIELDS))
        if invalid_fields:
            raise CRMValidationError(
                "Cannot edit automatic or unknown fields: " + ", ".join(invalid_fields)
            )
        stored = self.repository.get(internal_id)
        if stored is None:
            raise CRMRecordNotFound(f"CRM record {internal_id} was not found")
        tracking = stored.opportunity.tracking
        normalized = dict(changes)
        if "application_status" in normalized:
            normalized["application_status"] = _parse_status(
                normalized["application_status"]
            )
        for field_name in ("applied_date", "next_step_date"):
            if field_name in normalized:
                normalized[field_name] = _parse_date(normalized[field_name], field_name)
        for field_name in (
            "recruiter_name",
            "recruiter_email",
            "next_step",
            "notes",
        ):
            if field_name in normalized and normalized[field_name] is not None:
                if not isinstance(normalized[field_name], str):
                    raise CRMValidationError(f"{field_name} must be text or None")
        self.repository.update_tracking(internal_id, replace(tracking, **normalized))
        updated = self.get(internal_id)
        assert updated is not None
        return updated


def records_to_table(records: list[CRMRecord]) -> CRMTable:
    """Converte registros em tipos simples e colunas de ordem estável."""

    rows: list[list[SimpleValue]] = []
    for record in records:
        row: list[SimpleValue] = []
        for column in CRM_COLUMNS:
            value = getattr(record, column)
            if isinstance(value, Enum):
                value = value.value
            elif isinstance(value, (date, datetime)):
                value = value.isoformat()
            elif isinstance(value, list):
                value = " | ".join(value)
            row.append(value)
        rows.append(row)
    return CRMTable(headers=list(CRM_COLUMNS), rows=rows)
