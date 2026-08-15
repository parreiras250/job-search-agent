"""Testes das regras determinísticas do Daniel Job Agent."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from daniel_job_agent import (  # noqa: E402
    GeographicEligibility,
    JobOpportunity,
    RetentionDecision,
    RolePriority,
    ScoreWeights,
    are_probably_duplicates,
    calculate_match_score,
    classify_role,
    decide_retention,
    evaluate_geographic_eligibility,
    normalize_company,
    normalize_location,
    normalize_role,
)


def make_job(**changes: object) -> JobOpportunity:
    values = {
        "company": "Example Inc.",
        "role": "Account Executive",
        "job_url": "https://example.com/jobs/123",
        "source": "Company careers page",
        "location": "Remote - LATAM",
        "remote": True,
        "brazil_eligible": True,
    }
    values.update(changes)
    return JobOpportunity(**values)  # type: ignore[arg-type]


class NormalizationTests(unittest.TestCase):
    def test_normalizes_spaces_without_changing_company_name(self) -> None:
        self.assertEqual(normalize_company("  ACME   do Brasil  "), "ACME do Brasil")
        self.assertEqual(normalize_role("  Account Executive  "), "Account Executive")
        self.assertEqual(normalize_location(" Remote -   Brazil "), "Remote - Brazil")


class RoleClassificationTests(unittest.TestCase):
    def test_classifies_high_priority_role_with_small_variation(self) -> None:
        self.assertEqual(
            classify_role("Senior Enterprise Account Executive - SaaS"),
            RolePriority.HIGH,
        )

    def test_classifies_medium_role_before_generic_business_development(self) -> None:
        self.assertEqual(
            classify_role("Business Development Representative (BDR)"),
            RolePriority.MEDIUM,
        )

    def test_classifies_clearly_irrelevant_role(self) -> None:
        self.assertEqual(classify_role("Senior Software Engineer"), RolePriority.IRRELEVANT)

    def test_rejects_clearly_technical_and_non_sales_families(self) -> None:
        roles = (
            "AI Engineer",
            "Machine Learning Engineer",
            "Backend Engineer",
            "Product Manager",
            "Legal Counsel",
            "Talent Acquisition Specialist",
            "Senior Researcher",
        )
        for role in roles:
            with self.subTest(role=role):
                self.assertEqual(
                    decide_retention(make_job(role=role)),
                    RetentionDecision.REJECT,
                )

    def test_protects_technical_commercial_roles_from_false_rejection(self) -> None:
        roles = ("Sales Engineer", "Solutions Engineer", "Technical Account Manager")
        for role in roles:
            with self.subTest(role=role):
                self.assertNotEqual(
                    decide_retention(
                        make_job(role=role, location="Location not disclosed")
                    ),
                    RetentionDecision.REJECT,
                )


class GeographicEligibilityTests(unittest.TestCase):
    def test_recognizes_supported_eligible_locations(self) -> None:
        for location in ("Remote - Brazil", "Remote - LATAM", "Latin America", "Worldwide Remote"):
            with self.subTest(location=location):
                self.assertEqual(
                    evaluate_geographic_eligibility(location),
                    GeographicEligibility.ELIGIBLE,
                )

    def test_recognizes_us_only_as_not_eligible(self) -> None:
        for location in ("Remote - US only", "United States only"):
            with self.subTest(location=location):
                self.assertEqual(
                    evaluate_geographic_eligibility(location),
                    GeographicEligibility.NOT_ELIGIBLE,
                )

    def test_returns_unknown_when_information_is_insufficient(self) -> None:
        self.assertEqual(
            evaluate_geographic_eligibility("Remote"),
            GeographicEligibility.UNKNOWN,
        )

    def test_uses_explicit_eligible_signals_from_title(self) -> None:
        roles = (
            "Account Executive - LATAM",
            "Sales Executive Latin America",
            "BDR Brazil",
        )
        for role in roles:
            with self.subTest(role=role):
                self.assertEqual(
                    evaluate_geographic_eligibility("Location not disclosed", role),
                    GeographicEligibility.ELIGIBLE,
                )

    def test_uses_explicit_us_signal_from_title_conservatively(self) -> None:
        for role in ("Account Executive USA", "Sales Executive United States"):
            with self.subTest(role=role):
                self.assertEqual(
                    evaluate_geographic_eligibility("Location not disclosed", role),
                    GeographicEligibility.NOT_ELIGIBLE,
                )


class DeduplicationTests(unittest.TestCase):
    def test_matches_normalized_url_ignoring_tracking_and_trailing_slash(self) -> None:
        first = make_job(job_url="https://EXAMPLE.com/jobs/123/?utm_source=board")
        second = make_job(company="Other", role="Other", job_url="https://example.com/jobs/123")
        self.assertTrue(are_probably_duplicates(first, second))

    def test_matches_normalized_company_and_role(self) -> None:
        first = make_job(company=" Example Inc. ", role="Account  Executive")
        second = make_job(
            company="example inc.",
            role="account executive",
            job_url="https://other.example/job/9",
        )
        self.assertTrue(are_probably_duplicates(first, second))

    def test_keeps_distinct_jobs_distinct(self) -> None:
        self.assertFalse(
            are_probably_duplicates(
                make_job(),
                make_job(role="SDR", job_url="https://example.com/jobs/456"),
            )
        )


class ScoringAndRetentionTests(unittest.TestCase):
    def test_scores_strong_eligible_remote_match(self) -> None:
        self.assertEqual(calculate_match_score(make_job()), 95)

    def test_penalizes_explicitly_ineligible_location(self) -> None:
        job = make_job(location="Remote - US only", brazil_eligible=False)
        self.assertEqual(calculate_match_score(job), 5)

    def test_accepts_configurable_weights_and_caps_score(self) -> None:
        weights = ScoreWeights(high_role=95, eligible_location=40, remote=20)
        self.assertEqual(calculate_match_score(make_job(), weights), 100)

    def test_decides_keep_review_and_reject(self) -> None:
        self.assertEqual(decide_retention(make_job()), RetentionDecision.KEEP)
        self.assertEqual(
            decide_retention(make_job(location="Remote", brazil_eligible=False)),
            RetentionDecision.REVIEW,
        )
        self.assertEqual(
            decide_retention(make_job(role="Product Designer")),
            RetentionDecision.REJECT,
        )
        self.assertEqual(
            decide_retention(make_job(location="United States only", brazil_eligible=False)),
            RetentionDecision.REJECT,
        )


if __name__ == "__main__":
    unittest.main()
