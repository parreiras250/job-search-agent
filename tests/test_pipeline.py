"""Testes end-to-end do pipeline local de oportunidades."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from daniel_job_agent import (  # noqa: E402
    ApplicationStatus,
    JobOpportunity,
    RetentionDecision,
    create_daniel_profile,
    process_opportunities,
)
from daniel_job_agent.demo_data import create_demo_jobs  # noqa: E402


def make_job(identifier: str = "1", **changes: object) -> JobOpportunity:
    values = {
        "company": f"Company {identifier}",
        "role": "Account Executive",
        "job_url": f"https://example.com/jobs/{identifier}",
        "source": "Local test",
        "location": "Remote - LATAM",
        "remote": True,
        "brazil_eligible": True,
        "years_experience_required": 5,
    }
    values.update(changes)
    return JobOpportunity(**values)  # type: ignore[arg-type]


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = create_daniel_profile()

    def test_processes_empty_collection(self) -> None:
        result = process_opportunities([], self.profile)

        self.assertEqual(result.total_received, 0)
        self.assertEqual(result.unique_opportunities, 0)
        self.assertEqual(result.ranked_opportunities, [])
        self.assertEqual(result.keep_count + result.review_count + result.reject_count, 0)

    def test_processes_single_opportunity_and_preserves_original(self) -> None:
        job = make_job(company="  Example Company  ", role="Account  Executive")
        result = process_opportunities([job], self.profile)
        item = result.ranked_opportunities[0]

        self.assertIs(item.original_job, job)
        self.assertEqual(item.original_job.company, "  Example Company  ")
        self.assertEqual(item.normalized_job.company, "Example Company")
        self.assertEqual(item.rank, 1)

    def test_processes_multiple_opportunities_and_counts_decisions(self) -> None:
        jobs = [
            make_job("keep"),
            make_job("review", location="Remote", brazil_eligible=False),
            make_job("reject", role="Software Engineer"),
        ]
        result = process_opportunities(jobs, self.profile)

        self.assertEqual(result.total_received, 3)
        self.assertEqual(result.unique_opportunities, 3)
        self.assertEqual(result.keep_count, 1)
        self.assertEqual(result.review_count, 1)
        self.assertEqual(result.reject_count, 1)
        self.assertEqual(len(result.keep), 1)
        self.assertEqual(len(result.review), 1)
        self.assertEqual(len(result.reject), 1)

    def test_deduplicates_and_records_primary_without_merging(self) -> None:
        primary = make_job("one", company=" Example Inc. ")
        duplicate = make_job(
            "two",
            company="example inc.",
            role="account executive",
            tools_mentioned=["Salesforce"],
        )
        result = process_opportunities([primary, duplicate], self.profile)

        self.assertEqual(result.unique_opportunities, 1)
        self.assertEqual(result.duplicates_detected, 1)
        self.assertIs(result.duplicate_records[0].primary, primary)
        self.assertIs(result.duplicate_records[0].duplicate, duplicate)
        self.assertIsNone(primary.tools_mentioned)

    def test_ranks_by_score_from_highest_to_lowest(self) -> None:
        strong = make_job(
            "strong",
            tools_mentioned=["Salesforce", "HubSpot"],
            industries_mentioned=["B2B SaaS"],
        )
        secondary = make_job("secondary", role="SDR")
        result = process_opportunities([secondary, strong], self.profile)

        scores = [item.match_score for item in result.ranked_opportunities]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertIs(result.ranked_opportunities[0].original_job, strong)

    def test_ranking_is_stable_for_equal_score_and_decision(self) -> None:
        zebra = make_job("zebra", company="Zebra Co")
        alpha = make_job("alpha", company="Alpha Co")
        result = process_opportunities([zebra, alpha], self.profile)

        self.assertEqual(
            [item.normalized_job.company for item in result.ranked_opportunities],
            ["Alpha Co", "Zebra Co"],
        )

    def test_rejected_jobs_remain_in_ranked_result(self) -> None:
        rejected = make_job("rejected", location="Remote - US only")
        result = process_opportunities([rejected], self.profile)

        self.assertEqual(result.reject_count, 1)
        self.assertEqual(len(result.ranked_opportunities), 1)
        self.assertIs(result.reject[0].original_job, rejected)

    def test_seven_year_requirement_remains_ranked_and_is_not_rejected(self) -> None:
        job = make_job("seven", years_experience_required=7)
        result = process_opportunities([job], self.profile)
        item = result.ranked_opportunities[0]

        self.assertIn(item.retention_decision, (RetentionDecision.KEEP, RetentionDecision.REVIEW))
        self.assertTrue(item.potential_gaps)

    def test_us_only_and_irrelevant_role_are_hard_rejections(self) -> None:
        us_only = make_job("us", location="United States only", brazil_eligible=False)
        irrelevant = make_job("code", role="Software Engineer")
        result = process_opportunities([us_only, irrelevant], self.profile)

        self.assertEqual(result.reject_count, 2)

    def test_unknown_location_is_review(self) -> None:
        job = make_job("unknown", location="Remote", brazil_eligible=False)
        result = process_opportunities([job], self.profile)

        self.assertEqual(result.ranked_opportunities[0].retention_decision, RetentionDecision.REVIEW)

    def test_preserves_application_tracking(self) -> None:
        job = make_job()
        job.tracking.application_status = ApplicationStatus.RECRUITER_SCREEN
        job.tracking.notes = "Manual CRM note"

        result = process_opportunities([job], self.profile)

        self.assertIs(result.ranked_opportunities[0].original_job.tracking, job.tracking)
        self.assertEqual(job.tracking.application_status, ApplicationStatus.RECRUITER_SCREEN)
        self.assertEqual(job.tracking.notes, "Manual CRM note")

    def test_demo_dataset_processes_end_to_end(self) -> None:
        jobs = create_demo_jobs()
        result = process_opportunities(jobs, self.profile)

        self.assertEqual(result.total_received, 13)
        self.assertEqual(result.unique_opportunities, 12)
        self.assertEqual(result.duplicates_detected, 1)
        self.assertEqual(len(result.ranked_opportunities), 12)
        self.assertEqual(
            result.keep_count + result.review_count + result.reject_count,
            result.unique_opportunities,
        )


if __name__ == "__main__":
    unittest.main()
