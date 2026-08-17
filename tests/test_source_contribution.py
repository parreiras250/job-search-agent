"""Testes offline das métricas incrementais das quatro fontes globais."""

from dataclasses import dataclass
from datetime import datetime, timezone
import unittest

from daniel_job_agent import (
    GLOBAL_SOURCE_ORDER,
    JobOpportunity,
    create_daniel_profile,
    measure_source_contributions,
    process_opportunities,
    format_weekly_report,
    WeeklyReport,
)
from daniel_job_agent.source_efficiency_demo import format_source_efficiency


@dataclass(frozen=True)
class Summary:
    received: int
    converted: int
    succeeded: bool = True


def job(source_id: str, key: str, role: str) -> JobOpportunity:
    url_source = source_id.replace(":", "-")
    return JobOpportunity(
        company=f"Company {key}",
        role=role,
        job_url=f"https://{url_source}.example/{key}",
        source=source_id,
        source_id=source_id,
        location="LATAM",
        remote=True,
        brazil_eligible=True,
        description="B2B SaaS outbound sales",
    )


def fixture_jobs() -> list[JobOpportunity]:
    """A–G, incluindo overlaps duplo e triplo, na ordem operacional."""

    return [
        job("jobicy", "A", "Account Executive"),
        job("jobicy", "B", "Sales Development Representative"),
        job("remotive", "B", "Sales Development Representative"),
        job("weworkremotely", "C", "Account Executive"),
        job("weworkremotely", "D", "Sales Development Representative"),
        job("himalayas", "B", "Sales Development Representative"),
        job("himalayas", "D", "Sales Development Representative"),
        job("himalayas", "E", "Account Executive"),
        job("himalayas", "F", "Sales Engineer"),
        job("himalayas", "G", "Software Engineer"),
    ]


def successful_summaries() -> dict[str, Summary]:
    return {
        "jobicy": Summary(2, 2),
        "remotive": Summary(1, 1),
        "weworkremotely": Summary(2, 2),
        "himalayas": Summary(5, 5),
    }


class SourceContributionTests(unittest.TestCase):
    def result(self):
        pipeline = process_opportunities(fixture_jobs(), create_daniel_profile())
        return measure_source_contributions(pipeline, successful_summaries())

    def test_structure_order_and_exact_marginal_counts(self) -> None:
        result = self.result()
        self.assertEqual(result.operational_order, GLOBAL_SOURCE_ORDER)
        self.assertEqual(list(result.contributions), list(GLOBAL_SOURCE_ORDER))
        self.assertEqual(
            [result.contributions[item].incremental_unique for item in GLOBAL_SOURCE_ORDER],
            [2, 0, 2, 3],
        )
        himalayas = result.contributions["himalayas"]
        self.assertEqual(himalayas.unique_contributed, 5)
        self.assertEqual(himalayas.incremental_keep, 1)
        self.assertEqual(himalayas.incremental_review, 1)
        self.assertEqual(himalayas.incremental_reject, 1)
        self.assertEqual(himalayas.incremental_relevant, 2)
        self.assertEqual(himalayas.keep, 3)
        self.assertEqual(himalayas.review, 1)
        self.assertEqual(himalayas.reject, 1)

    def test_provenance_overlap_matrix_includes_double_and_triple_groups(self) -> None:
        result = self.result()
        self.assertEqual(result.overlap_matrix[("jobicy", "remotive")], 1)
        self.assertEqual(result.overlap_matrix[("jobicy", "himalayas")], 1)
        self.assertEqual(result.overlap_matrix[("remotive", "himalayas")], 1)
        self.assertEqual(result.overlap_matrix[("weworkremotely", "himalayas")], 1)
        self.assertEqual(result.contributions["himalayas"].overlap_count, 2)
        self.assertEqual(result.contributions["himalayas"].cross_source_duplicates, 2)

    def test_efficiency_ratios_and_zero_incremental_are_safe(self) -> None:
        result = self.result()
        himalayas = result.contributions["himalayas"]
        remotive = result.contributions["remotive"]
        self.assertEqual(himalayas.requests_per_incremental_unique, 1 / 3)
        self.assertEqual(himalayas.requests_per_incremental_relevant, 1 / 2)
        self.assertIsNone(remotive.requests_per_incremental_unique)
        self.assertIsNone(remotive.requests_per_incremental_relevant)

    def test_himalayas_baseline_and_expanded_delta(self) -> None:
        delta = self.result().himalayas_delta
        assert delta is not None
        self.assertEqual((delta.baseline_unique, delta.expanded_unique), (4, 7))
        self.assertEqual(delta.incremental_unique, 3)
        self.assertEqual(delta.incremental_keep, 1)
        self.assertEqual(delta.incremental_relevant, 2)
        self.assertEqual(delta.cross_source_duplicates, 2)

    def test_failed_source_is_unavailable_not_false_zero(self) -> None:
        summaries = successful_summaries()
        summaries["remotive"] = Summary(0, 0, succeeded=False)
        pipeline = process_opportunities(
            [item for item in fixture_jobs() if item.source_id != "remotive"],
            create_daniel_profile(),
        )
        result = measure_source_contributions(pipeline, summaries)
        failed = result.contributions["remotive"]
        self.assertEqual(failed.status, "FAILED")
        self.assertIsNone(failed.incremental_unique)
        self.assertIsNone(failed.incremental_relevant)
        self.assertEqual(result.contributions["himalayas"].status, "SUCCESS")

    def test_himalayas_failure_makes_delta_unavailable(self) -> None:
        summaries = successful_summaries()
        summaries["himalayas"] = Summary(0, 0, succeeded=False)
        pipeline = process_opportunities(
            [item for item in fixture_jobs() if item.source_id != "himalayas"],
            create_daniel_profile(),
        )
        result = measure_source_contributions(pipeline, summaries)
        self.assertIsNone(result.himalayas_delta)

    def test_demo_formatter_is_compact_and_handles_unavailable(self) -> None:
        result = self.result()
        output = format_source_efficiency(result)
        self.assertIn("Himalayas: SUCCESS", output)
        self.assertIn("Incremental unique: +3", output)
        self.assertIn("Unique: 4 → 7 (+3)", output)
        self.assertNotIn("https://", output)

    def test_weekly_report_has_compact_contribution_section(self) -> None:
        result = self.result()
        now = datetime(2026, 8, 17, tzinfo=timezone.utc)
        report = WeeklyReport(
            run_id=1,
            started_at=now,
            finished_at=now,
            status="SUCCESS",
            sources=[],
            source_contributions=list(result.contributions.values()),
            himalayas_delta=result.himalayas_delta,
        )
        output = format_weekly_report(report)
        self.assertIn("## Source contribution", output)
        self.assertIn("**Himalayas:** +3 unique | +1 KEEP | +2 relevant", output)

    def test_tenant_sources_are_excluded_from_global_measurement(self) -> None:
        jobs = [
            job("jobicy", "A", "Account Executive"),
            job("greenhouse:tenant", "A", "Account Executive"),
            job("greenhouse:tenant", "T", "Account Executive"),
        ]
        result = measure_source_contributions(
            process_opportunities(jobs, create_daniel_profile()),
            successful_summaries(),
        )
        self.assertEqual(result.contributions["jobicy"].unique_contributed, 1)
        self.assertEqual(result.contributions["jobicy"].cross_source_duplicates, 0)
        assert result.himalayas_delta is not None
        self.assertEqual(result.himalayas_delta.expanded_unique, 1)


if __name__ == "__main__":
    unittest.main()
