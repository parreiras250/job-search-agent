"""Calibração determinística de fit, eligibility, timezone e riscos."""

import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from daniel_job_agent import (
    ApplicationStatus,
    EligibilityStatus,
    JobOpportunity,
    JobRepository,
    LocalCRM,
    LocationRestriction,
    OpportunityRisk,
    RetentionDecision,
    TimezoneCompatibility,
    create_daniel_profile,
    evaluate_match,
    process_opportunities,
    sync_opportunities,
)
from daniel_job_agent.repository import SCHEMA_VERSION
from daniel_job_agent.ranking_calibration_demo import format_calibration


def job(role="Account Executive", location="LATAM", **changes):
    values = {
        "company": "Example SaaS",
        "role": role,
        "job_url": f"https://example.com/{role.lower().replace(' ', '-')}",
        "source": "Fixture",
        "location": location,
        "remote": True,
        "brazil_eligible": None,
    }
    values.update(changes)
    return JobOpportunity(**values)


class RankingCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.profile = create_daniel_profile()

    def evaluate(self, item):
        return evaluate_match(item, self.profile)

    def test_strong_ae_latam_and_worldwide_are_keep(self):
        for location in ("LATAM", "Worldwide"):
            with self.subTest(location=location):
                result = self.evaluate(job(location=location))
                self.assertGreaterEqual(result.score, 90)
                self.assertEqual(result.eligibility, EligibilityStatus.ELIGIBLE)
                self.assertEqual(result.retention_decision, RetentionDecision.KEEP)

    def test_ae_us_only_and_europe_only_reject_for_geography_not_fit(self):
        for location in ("United States only", "Remote - United States", "Europe only"):
            with self.subTest(location=location):
                result = self.evaluate(job(location=location))
                self.assertGreaterEqual(result.score, 90)
                self.assertEqual(result.eligibility, EligibilityStatus.INELIGIBLE)
                self.assertEqual(result.retention_decision, RetentionDecision.REJECT)
                self.assertIn("Geographic restriction", result.decision_reasons[0])

    def test_explicit_latam_opening_overrides_us_location_signal(self):
        result = self.evaluate(
            job(location="Remote - United States; open to LATAM candidates")
        )
        self.assertEqual(result.eligibility, EligibilityStatus.ELIGIBLE)
        self.assertEqual(result.retention_decision, RetentionDecision.KEEP)

    def test_strong_ae_unknown_geography_is_review_not_ineligible(self):
        result = self.evaluate(job(location="Remote"))
        self.assertEqual(result.eligibility, EligibilityStatus.UNCERTAIN)
        self.assertEqual(result.retention_decision, RetentionDecision.REVIEW)

    def test_commission_only_and_no_base_are_hard_negative(self):
        cases = (
            "This is a 100% commission position.",
            "Compensation is commission-only with no base salary.",
        )
        for description in cases:
            with self.subTest(description=description):
                result = self.evaluate(job(description=description))
                self.assertEqual(result.retention_decision, RetentionDecision.REJECT)
                self.assertTrue(result.opportunity_risks)

    def test_base_plus_commission_is_not_commission_only(self):
        for description in (
            "$60k base + commission",
            "Competitive base salary plus uncapped commission",
        ):
            result = self.evaluate(job(description=description))
            self.assertNotIn(OpportunityRisk.COMMISSION_ONLY, result.opportunity_risks)
            self.assertEqual(result.retention_decision, RetentionDecision.KEEP)

    def test_clear_non_target_titles_reject_even_when_description_mentions_sales(self):
        roles = (
            "Maintenance Planner",
            "Facilities Planner",
            "Customer Service Representative",
            "Artificial Intelligence Specialist",
            "Estimator",
            "Software Engineer",
        )
        for role in roles:
            with self.subTest(role=role):
                result = self.evaluate(
                    job(role, description="sales customer account business sales sales")
                )
                self.assertEqual(result.retention_decision, RetentionDecision.REJECT)
                self.assertEqual(result.decision_reasons, ["Role family is outside target profile"])

    def test_latam_sdr_remains_relevant(self):
        result = self.evaluate(job("Sales Development Representative"))
        self.assertGreaterEqual(result.score, 60)
        self.assertEqual(result.retention_decision, RetentionDecision.KEEP)

    def test_worldwide_with_europe_timezone_is_review_not_geo_reject(self):
        result = self.evaluate(
            job(location="Worldwide", description="Work European business hours")
        )
        self.assertEqual(result.eligibility, EligibilityStatus.ELIGIBLE)
        self.assertEqual(result.timezone_compatibility, TimezoneCompatibility.LOW)
        self.assertEqual(result.retention_decision, RetentionDecision.REVIEW)

    def test_full_timezone_span_is_high_compatibility(self):
        result = self.evaluate(
            job(timezone_restrictions=list(range(-11, 15)), location="Worldwide")
        )
        self.assertEqual(result.timezone_compatibility, TimezoneCompatibility.HIGH)
        self.assertEqual(result.retention_decision, RetentionDecision.KEEP)

    def test_us_timezone_and_latam_location_are_high_compatibility(self):
        result = self.evaluate(
            job(description="Must overlap with US Eastern Time business hours")
        )
        self.assertEqual(result.timezone_compatibility, TimezoneCompatibility.HIGH)
        self.assertEqual(result.retention_decision, RetentionDecision.KEEP)

    def test_structured_location_precedes_generic_remote_text(self):
        item = job(
            location="Remote",
            description="Global remote culture",
            location_restrictions=[
                LocationRestriction("US", "United States", "united-states")
            ],
        )
        result = self.evaluate(item)
        self.assertEqual(result.eligibility, EligibilityStatus.INELIGIBLE)
        self.assertEqual(result.retention_decision, RetentionDecision.REJECT)

    def test_broad_metadata_is_qualified_by_explicit_title_geography(self):
        cases = (
            ("Account Executive - LATAM", EligibilityStatus.ELIGIBLE, RetentionDecision.KEEP),
            ("Account Executive – Eastern Saudi Arabia", EligibilityStatus.LIKELY_INELIGIBLE, RetentionDecision.REVIEW),
            ("Account Executive - UK", EligibilityStatus.LIKELY_INELIGIBLE, RetentionDecision.REVIEW),
            ("Account Executive - DACH", EligibilityStatus.LIKELY_INELIGIBLE, RetentionDecision.REVIEW),
            ("Account Executive - APAC", EligibilityStatus.LIKELY_INELIGIBLE, RetentionDecision.REVIEW),
            ("Account Executive - Brazil", EligibilityStatus.ELIGIBLE, RetentionDecision.KEEP),
        )
        for role, eligibility, decision in cases:
            with self.subTest(role=role):
                result = self.evaluate(job(
                    role,
                    location="Worldwide",
                    location_restrictions=[
                        LocationRestriction(None, "Worldwide", None)
                    ],
                ))
                self.assertEqual(result.eligibility, eligibility)
                self.assertEqual(result.retention_decision, decision)

    def test_common_sales_region_aliases_do_not_receive_keep(self):
        aliases = (
            "UKI",
            "UK&I",
            "UK & Ireland",
            "DACH",
            "EMEA",
            "APAC",
            "ANZ",
            "Australia & New Zealand",
            "Benelux",
            "Nordics",
        )
        for alias in aliases:
            with self.subTest(alias=alias):
                result = self.evaluate(job(
                    f"Account Executive {alias}",
                    location="Worldwide",
                ))
                self.assertEqual(
                    result.eligibility, EligibilityStatus.LIKELY_INELIGIBLE
                )
                self.assertEqual(
                    result.retention_decision, RetentionDecision.REVIEW
                )
                self.assertIn("sales territory", result.decision_reasons[0])

    def test_non_geographic_commercial_segments_are_not_territory_signals(self):
        roles = (
            "Corporate Account Executive - East",
            "Corporate Account Executive - West",
            "Enterprise Account Executive, SLED",
        )
        for role in roles:
            with self.subTest(role=role):
                result = self.evaluate(job(role, location="Worldwide"))
                self.assertEqual(result.eligibility, EligibilityStatus.ELIGIBLE)
                self.assertEqual(result.retention_decision, RetentionDecision.KEEP)

    def test_in_territory_us_title_is_a_hard_geographic_restriction(self):
        result = self.evaluate(job(
            "Account Executive - In-Territory (SF/Bay Area, CA)",
            location="Anywhere",
            location_restrictions=[],
        ))
        self.assertEqual(result.eligibility, EligibilityStatus.INELIGIBLE)
        self.assertEqual(result.retention_decision, RetentionDecision.REJECT)
        self.assertIn("SF/Bay Area", result.decision_reasons[0])

    def test_us_market_title_is_ambiguous_not_hard_rejected(self):
        result = self.evaluate(job(
            "Account Executive, US Market",
            location="Worldwide",
            location_restrictions=[],
        ))
        self.assertEqual(result.eligibility, EligibilityStatus.UNCERTAIN)
        self.assertEqual(result.retention_decision, RetentionDecision.REVIEW)

    def test_explicit_latam_structured_restriction_wins_over_us_customers(self):
        result = self.evaluate(job(
            "Account Executive for US customers",
            location="LATAM",
            location_restrictions=[LocationRestriction(None, "LATAM", None)],
        ))
        self.assertEqual(result.eligibility, EligibilityStatus.ELIGIBLE)
        self.assertEqual(result.retention_decision, RetentionDecision.KEEP)

    def test_explanations_keep_axes_visible(self):
        result = self.evaluate(job(location="United States only"))
        self.assertGreaterEqual(result.score, 90)
        self.assertEqual(result.eligibility.value, "INELIGIBLE")
        self.assertEqual(result.opportunity_risks, ())
        self.assertTrue(result.decision_reasons)

    def test_offline_calibration_demo_covers_expected_cases(self):
        output = format_calibration()
        self.assertIn("Career Fit | Eligibility | TZ Fit | Risk | Decision", output)
        self.assertIn("Commission-only Account Executive", output)
        self.assertIn("Maintenance Planner", output)
        self.assertEqual(len(output.splitlines()), 21)


class RankingMigrationCompatibilityTests(unittest.TestCase):
    def test_schema_migration_and_reranking_preserve_manual_crm_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.db"
            original = job(description="Base salary plus commission")
            original.source_id = "jobicy"
            original.source_family = "jobicy"
            original.source_instance = "jobicy:global"
            original.source_type = "GLOBAL_BOARD"
            original.lifecycle_authority = "OBSERVATIONAL"
            with JobRepository(path) as repository:
                synced = sync_opportunities(
                    process_opportunities([original], create_daniel_profile()), repository
                )
                internal_id = synced.new_jobs[0].internal_id
                LocalCRM(repository).update_manual_fields(
                    internal_id,
                    application_status=ApplicationStatus.APPLIED,
                    applied_date=date(2026, 8, 17),
                    notes="manual note survives",
                )
                self.assertEqual(repository.observation_count(), 1)
            with sqlite3.connect(path) as legacy:
                for column in (
                    "eligibility", "timezone_compatibility",
                    "opportunity_risks", "decision_reasons",
                ):
                    legacy.execute(f"ALTER TABLE opportunities DROP COLUMN {column}")
                legacy.execute("PRAGMA user_version = 7")
            with JobRepository(path) as repository:
                self.assertEqual(
                    repository.connection.execute("PRAGMA user_version").fetchone()[0],
                    SCHEMA_VERSION,
                )
                sync_opportunities(
                    process_opportunities([original], create_daniel_profile()), repository
                )
                record = LocalCRM(repository).get(internal_id)
                assert record is not None
                self.assertEqual(record.application_status, ApplicationStatus.APPLIED)
                self.assertEqual(record.notes, "manual note survives")
                self.assertEqual(repository.observation_count(), 1)
                self.assertEqual(record.eligibility, EligibilityStatus.ELIGIBLE)


if __name__ == "__main__":
    unittest.main()
