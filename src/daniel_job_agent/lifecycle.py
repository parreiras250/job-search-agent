"""Reconciliação conservadora do ciclo de vida das vagas armazenadas."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping

from .models import JobLifecycleStatus
from .repository import JobRepository


class VerificationStatus(str, Enum):
    """Sinal explícito futuro, sem inferir fechamento por HTTP status."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class LifecyclePolicy:
    possibly_closed_after: int = 2
    closed_after: int = 3

    def __post_init__(self) -> None:
        if self.possibly_closed_after < 1:
            raise ValueError("possibly_closed_after must be positive")
        if self.closed_after <= self.possibly_closed_after:
            raise ValueError("closed_after must be greater than possibly_closed_after")


@dataclass(frozen=True, slots=True)
class LifecycleResult:
    open_seen: int
    misses_recorded: int
    possibly_closed: int
    newly_closed: int
    reopened: int
    unchanged_lifecycle: int


def _source_family(source: str) -> str | None:
    normalized = source.casefold()
    if "jobicy" in normalized:
        return "Jobicy"
    if "remotive" in normalized:
        return "Remotive"
    if "greenhouse" in normalized:
        return "Greenhouse"
    if "lever" in normalized:
        return "Lever"
    return None


def reconcile_lifecycle(
    repository: JobRepository,
    *,
    seen_internal_ids: set[int],
    successful_sources: set[str],
    policy: LifecyclePolicy = LifecyclePolicy(),
    verifications: Mapping[int, VerificationStatus] | None = None,
    now: datetime | None = None,
) -> LifecycleResult:
    """Atualiza presença/ausência somente para fontes consultadas com sucesso."""

    timestamp = now or datetime.now(timezone.utc)
    verification_map = verifications or {}
    open_seen = misses = possible = closed = reopened = unchanged = 0

    for stored in repository.list_all():
        job = stored.opportunity
        verification = verification_map.get(stored.internal_id, VerificationStatus.UNKNOWN)
        if stored.internal_id in seen_internal_ids or verification is VerificationStatus.OPEN:
            was_reopened = job.lifecycle_status in {
                JobLifecycleStatus.POSSIBLY_CLOSED,
                JobLifecycleStatus.CLOSED,
            }
            repository.update_lifecycle_seen(
                stored.internal_id,
                now=timestamp,
                reopened=was_reopened,
                explicitly_verified=verification is VerificationStatus.OPEN,
            )
            open_seen += 1
            if was_reopened:
                reopened += 1
            else:
                unchanged += 1
            continue

        if verification is VerificationStatus.CLOSED:
            if job.lifecycle_status is not JobLifecycleStatus.CLOSED:
                closed += 1
            else:
                unchanged += 1
            repository.update_lifecycle_missing(
                stored.internal_id,
                status=JobLifecycleStatus.CLOSED,
                misses=job.consecutive_misses,
                now=timestamp,
                explicitly_verified=True,
            )
            continue

        family = _source_family(job.source)
        if family not in successful_sources:
            continue
        new_misses = job.consecutive_misses + 1
        if new_misses >= policy.closed_after:
            status = JobLifecycleStatus.CLOSED
        elif new_misses >= policy.possibly_closed_after:
            status = JobLifecycleStatus.POSSIBLY_CLOSED
        else:
            status = job.lifecycle_status
            if status in {
                JobLifecycleStatus.POSSIBLY_CLOSED,
                JobLifecycleStatus.CLOSED,
            }:
                status = JobLifecycleStatus.OPEN
        repository.update_lifecycle_missing(
            stored.internal_id,
            status=status,
            misses=new_misses,
            now=timestamp,
            explicitly_verified=False,
        )
        misses += 1
        if status is JobLifecycleStatus.POSSIBLY_CLOSED and job.lifecycle_status is not status:
            possible += 1
        elif status is JobLifecycleStatus.CLOSED and job.lifecycle_status is not status:
            closed += 1
        else:
            unchanged += 1

    return LifecycleResult(open_seen, misses, possible, closed, reopened, unchanged)
