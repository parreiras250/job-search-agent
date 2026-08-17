"""Snapshots executivos, Markdown e armazenamento local por execução."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re

from .agent import AgentRunResult
from .crm import LocalCRM
from .models import ApplicationStatus
from .repository import AgentRunHistory, JobRepository
from .source_contribution import HimalayasDelta, SourceContribution


_SECRET_PATTERN = re.compile(
    r"(?i)(access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|token)"
    r"(\s*[:=]\s*|=)[^\s&]+"
)


def _safe_text(value: str, *, limit: int = 200) -> str:
    """Redige padrões de secret e limita mensagens externas no relatório."""

    redacted = _SECRET_PATTERN.sub(r"\1=[REDACTED]", value)
    return redacted if len(redacted) <= limit else redacted[:limit] + "…"


@dataclass(frozen=True, slots=True)
class SourceReport:
    name: str
    succeeded: bool
    received: int
    converted: int
    warnings: int
    errors: int
    failure_message: str | None = None


@dataclass(frozen=True, slots=True)
class ReportOpportunity:
    company: str
    role: str
    score: int
    decision: str
    role_family: str
    seniority: str
    location: str
    source: str
    job_url: str
    salary: str | None = None


@dataclass(frozen=True, slots=True)
class WeeklyReport:
    run_id: int
    started_at: datetime
    finished_at: datetime
    status: str
    sources: list[SourceReport]
    jobs_received: int = 0
    unique_opportunities: int = 0
    duplicates: int = 0
    opportunities_with_one_source: int = 0
    opportunities_with_multiple_sources: int = 0
    keep: int = 0
    review: int = 0
    reject: int = 0
    new: int = 0
    existing: int = 0
    updated: int = 0
    persistence_errors: int = 0
    total_stored: int = 0
    seen_open: int = 0
    misses_recorded: int = 0
    possibly_closed: int = 0
    newly_closed: int = 0
    reopened: int = 0
    sheets_success: bool | None = None
    sheets_rows_written: int | None = None
    crm_status_counts: dict[ApplicationStatus, int] = field(default_factory=dict)
    best_new: list[ReportOpportunity] = field(default_factory=list)
    important_updates: list[ReportOpportunity] = field(default_factory=list)
    possibly_closed_jobs: list[ReportOpportunity] = field(default_factory=list)
    newly_closed_jobs: list[ReportOpportunity] = field(default_factory=list)
    reopened_jobs: list[ReportOpportunity] = field(default_factory=list)
    failure_summary: str | None = None
    companies_tracked: int = 0
    companies_enabled: int = 0
    companies_executed: int = 0
    companies_succeeded: int = 0
    companies_failed: int = 0
    companies_unsupported: int = 0
    companies_limited: int = 0
    company_top_failures: list[str] = field(default_factory=list)
    source_contributions: list[SourceContribution] = field(default_factory=list)
    himalayas_delta: HimalayasDelta | None = None

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()


def _salary(job: object) -> str | None:
    text = getattr(job, "salary_text", None)
    if text:
        return str(text)
    minimum = getattr(job, "salary_min", None)
    maximum = getattr(job, "salary_max", None)
    currency = getattr(job, "salary_currency", None) or ""
    period = getattr(job, "salary_period", None)
    if minimum is None and maximum is None:
        return None
    values = (
        f"{minimum:g}–{maximum:g}" if minimum is not None and maximum is not None
        else f"{minimum if minimum is not None else maximum:g}"
    )
    suffix = f"/{period}" if period else ""
    return " ".join(part for part in (currency, values + suffix) if part)


def _opportunity_from_processed(item: object) -> ReportOpportunity:
    job = getattr(item, "normalized_job")
    return ReportOpportunity(
        company=job.company, role=job.role, score=int(getattr(item, "match_score")),
        decision=getattr(item, "retention_decision").value,
        role_family=getattr(item, "role_family").value,
        seniority=getattr(item, "seniority").value,
        location=job.location, source=job.source, job_url=job.job_url,
        salary=_salary(job),
    )


def _opportunity_from_stored(stored: object) -> ReportOpportunity:
    job = getattr(stored, "opportunity")
    return ReportOpportunity(
        company=job.company, role=job.role, score=int(getattr(stored, "match_score")),
        decision=getattr(stored, "retention_decision").value,
        role_family=getattr(stored, "role_family").value,
        seniority=getattr(stored, "seniority").value,
        location=job.location, source=job.source, job_url=job.job_url,
        salary=_salary(job),
    )


def _safe_failure_summary(result: AgentRunResult | None, sheets_success: bool | None) -> str | None:
    causes: list[str] = []
    if result is None:
        causes.append("The agent failed before a complete result was available.")
    else:
        causes.extend(
            f"{name} failed; results may be incomplete."
            for name in result.sources_failed
        )
        ingestion_errors = sum(result.discovery.errors_by_source.values())
        if ingestion_errors:
            causes.append(f"{ingestion_errors} ingestion error(s) reduced the result set.")
        if result.persistence_errors:
            causes.append(f"{result.persistence_errors} persistence error(s) occurred.")
    if sheets_success is False:
        causes.append("Google Sheets synchronization failed after local processing.")
    return " ".join(causes) or None


def build_weekly_report(
    repository: JobRepository,
    history: AgentRunHistory,
    agent_result: AgentRunResult | None,
    *,
    sheets_rows_written: int | None = None,
) -> WeeklyReport:
    records = LocalCRM(repository).list_records()
    counts = Counter(record.application_status for record in records)
    crm_snapshot = {status: counts[status] for status in ApplicationStatus}
    if agent_result is None:
        return WeeklyReport(
            run_id=history.run_id, started_at=history.started_at,
            finished_at=history.finished_at, status=history.status, sources=[],
            sheets_success=history.sheets_sync_success,
            sheets_rows_written=sheets_rows_written,
            crm_status_counts=crm_snapshot,
            failure_summary=_safe_failure_summary(None, history.sheets_sync_success),
        )

    summaries = agent_result.discovery.source_summaries
    sources = [
        SourceReport(
            name=name, succeeded=summary.succeeded, received=summary.received,
            converted=summary.converted, warnings=summary.warnings,
            errors=summary.errors,
            failure_message=(
                _safe_text(summary.failure_message or "Source request failed")
                if not summary.succeeded else None
            ),
        )
        for name, summary in summaries.items()
    ]
    new_ids = {item.internal_id for item in agent_result.persistence.new_jobs}
    updated_ids = [item.internal_id for item in agent_result.persistence.updated_jobs]
    processed_by_id = {
        synced.internal_id: processed
        for processed in agent_result.discovery.ranking
        for synced in (
            agent_result.persistence.new_jobs
            + agent_result.persistence.existing_jobs
            + agent_result.persistence.updated_jobs
        )
        if processed.original_job is synced.opportunity
    }
    decision_order = {"KEEP": 0, "REVIEW": 1, "REJECT": 2}
    best_new = sorted(
        (
            _opportunity_from_processed(processed_by_id[internal_id])
            for internal_id in new_ids
            if internal_id in processed_by_id
            and processed_by_id[internal_id].retention_decision.value != "REJECT"
        ),
        key=lambda item: (decision_order[item.decision], -item.score, item.company.casefold()),
    )[:10]
    updates = [
        _opportunity_from_processed(processed_by_id[internal_id])
        for internal_id in updated_ids if internal_id in processed_by_id
    ][:10]

    def lifecycle_jobs(ids: list[int]) -> list[ReportOpportunity]:
        return [
            _opportunity_from_stored(stored)
            for internal_id in ids
            if (stored := repository.get(internal_id)) is not None
        ]

    lifecycle = agent_result.lifecycle
    companies = agent_result.company_monitoring
    one_source, multiple_sources = repository.observation_overlap_counts()
    return WeeklyReport(
        run_id=history.run_id, started_at=history.started_at,
        finished_at=history.finished_at, status=history.status, sources=sources,
        jobs_received=agent_result.jobs_received,
        unique_opportunities=agent_result.unique_opportunities,
        duplicates=agent_result.discovery_duplicates, keep=agent_result.keep,
        opportunities_with_one_source=one_source,
        opportunities_with_multiple_sources=multiple_sources,
        review=agent_result.review, reject=agent_result.reject,
        new=agent_result.new, existing=agent_result.existing,
        updated=agent_result.updated, persistence_errors=agent_result.persistence_errors,
        total_stored=agent_result.total_stored, seen_open=lifecycle.open_seen,
        misses_recorded=lifecycle.misses_recorded,
        possibly_closed=lifecycle.possibly_closed,
        newly_closed=lifecycle.newly_closed, reopened=lifecycle.reopened,
        sheets_success=history.sheets_sync_success,
        sheets_rows_written=sheets_rows_written,
        crm_status_counts=crm_snapshot, best_new=best_new,
        important_updates=updates,
        possibly_closed_jobs=lifecycle_jobs(lifecycle.possibly_closed_ids),
        newly_closed_jobs=lifecycle_jobs(lifecycle.newly_closed_ids),
        reopened_jobs=lifecycle_jobs(lifecycle.reopened_ids),
        failure_summary=_safe_failure_summary(agent_result, history.sheets_sync_success),
        companies_tracked=companies.tracked,
        companies_enabled=companies.enabled,
        companies_executed=companies.executed,
        companies_succeeded=companies.succeeded,
        companies_failed=companies.failed,
        companies_unsupported=companies.unsupported,
        companies_limited=companies.limited,
        company_top_failures=companies.top_failures,
        source_contributions=[
            agent_result.discovery.source_contributions.contributions[source_id]
            for source_id in agent_result.discovery.source_contributions.operational_order
        ],
        himalayas_delta=agent_result.discovery.source_contributions.himalayas_delta,
    )


def _opportunity_lines(item: ReportOpportunity) -> list[str]:
    lines = [
        f"- **{item.company} — {item.role}**",
        f"  - Score: {item.score} | Decision: {item.decision}",
        f"  - Role family: {item.role_family} | Seniority: {item.seniority}",
        f"  - Location: {item.location} | Source: {item.source}",
    ]
    if item.salary:
        lines.append(f"  - Salary: {item.salary}")
    lines.append(f"  - URL: {_safe_text(item.job_url, limit=500)}")
    return lines


def format_weekly_report(report: WeeklyReport) -> str:
    sheets = "disabled" if report.sheets_success is None else (
        "success" if report.sheets_success else "failed"
    )
    lines = [
        "# Daniel Job Agent — Weekly Report", "",
        f"Run: {report.started_at.astimezone().strftime('%Y-%m-%d %H:%M %Z')}",
        f"Run ID: {report.run_id}", f"Status: **{report.status}**",
        f"Duration: {report.duration_seconds:.1f} seconds", "",
        "## Executive summary", "",
        f"- {report.jobs_received} jobs discovered",
        f"- {report.new} new opportunities",
        f"- {sum(item.decision == 'KEEP' for item in report.best_new)} strong new match(es)",
        f"- {report.updated} updated job(s)",
        f"- {report.misses_recorded} lifecycle miss(es) recorded",
        f"- {report.newly_closed} newly closed",
        f"- Google Sheets: {sheets}",
    ]
    if report.failure_summary:
        lines.extend(["", f"> {_safe_text(report.failure_summary, limit=500)}"])
    lines.extend(["", "## Source health", ""])
    if not report.sources:
        lines.append("Source details were not available.")
    for source in report.sources:
        state = "SUCCESS" if source.succeeded else "FAILED"
        detail = f" — {source.failure_message}" if source.failure_message else ""
        lines.extend([
            f"- **{source.name}: {state}**{detail}",
            f"  - Received: {source.received} | Converted: {source.converted} | Warnings: {source.warnings} | Errors: {source.errors}",
        ])
    lines.extend(["", "## Source contribution", ""])
    if not report.source_contributions:
        lines.append("Contribution details were not available.")
    for contribution in report.source_contributions:
        label = {
            "jobicy": "Jobicy",
            "remotive": "Remotive",
            "weworkremotely": "We Work Remotely",
            "himalayas": "Himalayas",
            "remoteok": "RemoteOK",
        }.get(contribution.source_id, contribution.source_id)
        if contribution.status != "SUCCESS":
            lines.append(f"- **{label}: contribution unavailable (FAILED)**")
            continue
        lines.append(
            f"- **{label}:** +{contribution.incremental_unique} unique | "
            f"+{contribution.incremental_keep} KEEP | "
            f"+{contribution.incremental_relevant} relevant"
        )
    if report.himalayas_delta is not None:
        delta = report.himalayas_delta
        lines.append(
            "- Himalayas delta: "
            f"{delta.baseline_unique} → {delta.expanded_unique} unique | "
            f"+{delta.incremental_keep} KEEP | +{delta.incremental_relevant} relevant"
        )
    lines.extend([
        "", "## Company monitoring", "",
        f"- Tracked companies: {report.companies_tracked}",
        f"- Enabled: {report.companies_enabled} | Executed: {report.companies_executed}",
        f"- Succeeded: {report.companies_succeeded} | Failed: {report.companies_failed} | Unsupported: {report.companies_unsupported}",
    ])
    if report.companies_limited:
        lines.append(f"- Limited by safety cap: {report.companies_limited}")
    if report.company_top_failures:
        lines.append("- Top failures: " + ", ".join(report.company_top_failures))
    lines.extend([
        "", "## Discovery", "",
        f"- Received: {report.jobs_received}",
        f"- Unique opportunities: {report.unique_opportunities}",
        f"- Duplicates: {report.duplicates}",
        f"- Source overlap: {report.opportunities_with_one_source} observed by 1 source | {report.opportunities_with_multiple_sources} observed by 2+ sources",
        f"- KEEP: {report.keep} | REVIEW: {report.review} | REJECT: {report.reject}",
        "", "## Persistence", "",
        f"- NEW: {report.new} | EXISTING: {report.existing} | UPDATED: {report.updated}",
        f"- Errors: {report.persistence_errors} | Total stored: {report.total_stored}",
        "", "## Best new opportunities", "",
    ])
    if not report.best_new:
        lines.append("No new KEEP or REVIEW opportunities found in this run.")
    for item in report.best_new:
        lines.extend(_opportunity_lines(item))
    lines.extend(["", "## Important updates", ""])
    if not report.important_updates:
        lines.append("No relevant opportunities were updated in this run.")
    for item in report.important_updates:
        lines.extend(_opportunity_lines(item))
    lines.extend([
        "", "## Lifecycle changes", "",
        f"Seen open: {report.seen_open} | Misses: {report.misses_recorded}", "",
    ])
    for title, jobs in (
        ("Possibly closed", report.possibly_closed_jobs),
        ("Closed", report.newly_closed_jobs),
        ("Reopened", report.reopened_jobs),
    ):
        lines.append(f"### {title}")
        lines.extend(
            (f"- {item.company} — {item.role}" for item in jobs)
            if jobs else ["None in this run."]
        )
        lines.append("")
    lines.extend(["## Google Sheets", "", f"Sync: {sheets}"])
    if report.sheets_rows_written is not None:
        lines.append(f"Rows written: {report.sheets_rows_written}")
    lines.extend(["", "## CRM snapshot", ""])
    lines.extend(
        f"- {status.value}: {report.crm_status_counts.get(status, 0)}"
        for status in ApplicationStatus
    )
    return "\n".join(lines).rstrip() + "\n"


def report_filename(report: WeeklyReport) -> str:
    return f"{report.started_at.strftime('%Y-%m-%d_%H%M%S')}_{report.run_id}.md"


def save_weekly_report(report: WeeklyReport, reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    markdown = format_weekly_report(report)
    historical = reports_dir / report_filename(report)
    with historical.open("x", encoding="utf-8") as output:
        output.write(markdown)
    temporary = reports_dir / ".latest.md.tmp"
    temporary.write_text(markdown, encoding="utf-8")
    temporary.replace(reports_dir / "latest.md")
    return historical


def find_report_for_run(reports_dir: Path, run_id: int) -> Path | None:
    suffix = re.compile(rf"_{run_id}\.md$")
    return next(
        (path for path in sorted(reports_dir.glob("*.md")) if suffix.search(path.name)),
        None,
    )
