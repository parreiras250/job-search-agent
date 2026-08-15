"""Testes do perfil profissional e da avaliação explicável."""

import sys
import unittest
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from daniel_job_agent import (  # noqa: E402
    ApplicationStatus,
    CandidateProfile,
    GeographicEligibility,
    JobOpportunity,
    RetentionDecision,
    calculate_match_score,
    create_daniel_profile,
    decide_retention,
    evaluate_geographic_eligibility,
    evaluate_match,
)


def make_job(**changes: object) -> JobOpportunity:
    values = {
        "company": "Example SaaS",
        "role": "Account Executive",
        "job_url": "https://example.com/jobs/123",
        "source": "Company careers page",
        "location": "Remote - LATAM",
        "remote": True,
        "brazil_eligible": True,
    }
    values.update(changes)
    return JobOpportunity(**values)  # type: ignore[arg-type]


class CandidateProfileTests(unittest.TestCase):
    def test_creates_profile_with_simple_types(self) -> None:
        profile = CandidateProfile(
            name="Test Candidate",
            years_experience=None,
            target_roles=["Account Executive"],
            preferred_currency="USD",
        )

        self.assertIsNone(profile.years_experience)
        self.assertEqual(profile.target_roles, ["Account Executive"])

    def test_daniel_profile_contains_only_configured_professional_data(self) -> None:
        profile = create_daniel_profile()

        self.assertEqual(profile.name, "Daniel Pedrosa")
        self.assertEqual(profile.years_experience, 5)
        self.assertIn("Account Executive", profile.target_roles)
        self.assertIn("BDR", profile.secondary_roles)
        self.assertIn("Salesforce", profile.tools)
        self.assertIn("B2B SaaS", profile.industries)
        self.assertTrue(profile.us_market_experience)
        self.assertTrue(profile.contractor_ok)
        self.assertEqual(profile.preferred_currency, "USD")
        self.assertIsNone(profile.minimum_base_salary)

    def test_job_accepts_new_optional_fields_without_breaking_defaults(self) -> None:
        original_style_job = make_job()
        enriched_job = make_job(
            description="A locally supplied description",
            requirements=["5 years of experience"],
            responsibilities=["Own the sales cycle"],
            preferred_qualifications=["SaaS experience"],
            tools_mentioned=["Salesforce"],
            industries_mentioned=["B2B SaaS"],
            years_experience_required=5,
            salary_currency="USD",
        )

        self.assertIsNone(original_style_job.description)
        self.assertEqual(enriched_job.tools_mentioned, ["Salesforce"])
        self.assertEqual(enriched_job.years_experience_required, 5)


class ProfileScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = create_daniel_profile()

    def test_strong_match_has_high_score(self) -> None:
        job = make_job(
            years_experience_required=5,
            tools_mentioned=["Salesforce", "HubSpot"],
            industries_mentioned=["B2B SaaS"],
        )
        self.assertGreaterEqual(calculate_match_score(job, profile=self.profile), 90)

    def test_secondary_role_scores_below_primary_with_same_other_signals(self) -> None:
        common = {
            "years_experience_required": 5,
            "tools_mentioned": ["Salesforce"],
            "industries_mentioned": ["Technology"],
        }
        primary = make_job(role="Account Executive", **common)
        secondary = make_job(role="SDR", job_url="https://example.com/jobs/456", **common)

        self.assertLess(
            calculate_match_score(secondary, profile=self.profile),
            calculate_match_score(primary, profile=self.profile),
        )

    def test_experience_requirement_at_or_below_profile_is_not_penalized(self) -> None:
        less = evaluate_match(make_job(years_experience_required=4), self.profile)
        exact = evaluate_match(make_job(years_experience_required=5), self.profile)

        self.assertEqual(less.score, exact.score)
        self.assertEqual(less.potential_gaps, [])
        self.assertEqual(exact.potential_gaps, [])

    def test_one_or_two_additional_years_is_a_small_gap(self) -> None:
        one_more = evaluate_match(make_job(years_experience_required=6), self.profile)
        two_more = evaluate_match(make_job(years_experience_required=7), self.profile)

        self.assertEqual(one_more.score, two_more.score)
        self.assertTrue(any("approximately 5" in gap for gap in two_more.potential_gaps))

    def test_significantly_higher_requirement_reduces_score_more(self) -> None:
        small_gap = evaluate_match(make_job(years_experience_required=7), self.profile)
        large_gap = evaluate_match(make_job(years_experience_required=12), self.profile)

        self.assertLess(large_gap.score, small_gap.score)
        self.assertTrue(any("Large experience gap" in gap for gap in large_gap.potential_gaps))

    def test_experience_gap_alone_never_rejects(self) -> None:
        job = make_job(years_experience_required=20)
        self.assertNotEqual(decide_retention(job, self.profile), RetentionDecision.REJECT)

    def test_missing_experience_requirement_has_no_score_penalty(self) -> None:
        missing = evaluate_match(make_job(), self.profile)
        matching = evaluate_match(make_job(years_experience_required=5), self.profile)

        self.assertEqual(missing.score + 3, matching.score)
        self.assertTrue(any("Years of experience" in item for item in missing.unknowns))

    def test_tools_and_industries_in_common_raise_score_and_reasons(self) -> None:
        basic = evaluate_match(make_job(), self.profile)
        enriched = evaluate_match(
            make_job(
                tools_mentioned=["Salesforce", "HubSpot"],
                industries_mentioned=["B2B SaaS"],
            ),
            self.profile,
        )

        self.assertGreater(enriched.score, basic.score)
        self.assertTrue(any("Salesforce" in item for item in enriched.positive_reasons))
        self.assertTrue(any("B2B SaaS" in item for item in enriched.positive_reasons))

    def test_evaluation_generates_reasons_gaps_and_unknowns(self) -> None:
        evaluation = evaluate_match(
            make_job(
                years_experience_required=7,
                tools_mentioned=["Unknown CRM"],
            ),
            self.profile,
        )

        self.assertTrue(evaluation.positive_reasons)
        self.assertTrue(evaluation.potential_gaps)
        self.assertTrue(evaluation.unknowns)

    def test_geographic_hard_filter_and_unknown_remain_distinct(self) -> None:
        incompatible = make_job(location="Remote - US only", brazil_eligible=False)
        unknown = make_job(location="Remote", brazil_eligible=False)

        self.assertEqual(
            evaluate_geographic_eligibility(incompatible.location),
            GeographicEligibility.NOT_ELIGIBLE,
        )
        self.assertEqual(decide_retention(incompatible, self.profile), RetentionDecision.REJECT)
        self.assertEqual(
            evaluate_geographic_eligibility(unknown.location),
            GeographicEligibility.UNKNOWN,
        )
        self.assertEqual(decide_retention(unknown, self.profile), RetentionDecision.REVIEW)

    def test_profile_evaluation_preserves_manual_tracking(self) -> None:
        job = make_job()
        job.tracking.application_status = ApplicationStatus.APPLIED
        job.tracking.applied_date = date(2026, 8, 14)
        job.tracking.notes = "Submitted manually"

        evaluate_match(job, self.profile)
        decide_retention(job, self.profile)

        self.assertEqual(job.tracking.application_status, ApplicationStatus.APPLIED)
        self.assertEqual(job.tracking.applied_date, date(2026, 8, 14))
        self.assertEqual(job.tracking.notes, "Submitted manually")


if __name__ == "__main__":
    unittest.main()
