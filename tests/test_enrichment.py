"""Testes do enriquecimento determinístico de descrições."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from daniel_job_agent import (  # noqa: E402
    JobOpportunity,
    RetentionDecision,
    create_daniel_profile,
    decide_retention,
    enrich_job,
    evaluate_match,
    extract_years_experience,
)


def make_job(**changes: object) -> JobOpportunity:
    values = {
        "company": "Example Company",
        "role": "Account Executive - LATAM",
        "job_url": "https://example.com/jobs/ae-latam",
        "source": "Local fixture",
        "location": "Location not disclosed",
        "remote": None,
        "brazil_eligible": None,
    }
    values.update(changes)
    return JobOpportunity(**values)  # type: ignore[arg-type]


class DeterministicEnrichmentTests(unittest.TestCase):
    def test_extracts_plus_years_and_range_minimum(self) -> None:
        self.assertEqual(extract_years_experience("Requires 4+ years."), 4)
        self.assertEqual(
            extract_years_experience("Requires 6-8 years of experience."),
            6,
        )

    def test_extracts_explicit_sales_signals(self) -> None:
        job = enrich_job(
            make_job(
                description=(
                    "Own the full sales cycle from qualification to closing. "
                    "Build inbound and outbound pipeline through direct prospecting. "
                    "Sell a B2B SaaS product. Requires approximately 4+ years."
                )
            )
        )

        self.assertEqual(job.years_experience_required, 4)
        self.assertIs(job.full_cycle_sales_required, True)
        self.assertIs(job.outbound_sales_required, True)
        self.assertIs(job.inbound_sales_mentioned, True)
        self.assertIs(job.b2b_experience_required, True)
        self.assertIs(job.saas_experience_required, True)

    def test_absent_signals_remain_unknown(self) -> None:
        job = enrich_job(make_job(description="Lead customer conversations."))

        self.assertIsNone(job.years_experience_required)
        self.assertIsNone(job.full_cycle_sales_required)
        self.assertIsNone(job.outbound_sales_required)
        self.assertIsNone(job.inbound_sales_mentioned)
        self.assertIsNone(job.b2b_experience_required)
        self.assertIsNone(job.saas_experience_required)

    def test_enrichment_does_not_override_existing_structured_value(self) -> None:
        job = enrich_job(
            make_job(
                years_experience_required=7,
                description="Requires 4+ years of experience.",
            )
        )
        self.assertEqual(job.years_experience_required, 7)

    def test_ae_latam_fixture_scores_above_unenriched_equivalent(self) -> None:
        description = (
            "Requires approximately 4+ years. Own the full sales cycle. "
            "Develop inbound and outbound pipeline with direct prospecting. "
            "This is a B2B SaaS sales role."
        )
        original = make_job(description=description)
        enriched = enrich_job(original)
        profile = create_daniel_profile()

        original_evaluation = evaluate_match(original, profile)
        enriched_evaluation = evaluate_match(enriched, profile)

        self.assertGreater(enriched_evaluation.score, original_evaluation.score)
        self.assertIn(
            decide_retention(enriched, profile),
            (RetentionDecision.KEEP, RetentionDecision.REVIEW),
        )
        self.assertIsNone(original.years_experience_required)

    def test_additional_years_remain_soft_signal_after_enrichment(self) -> None:
        job = enrich_job(make_job(description="Requires 7+ years of experience."))

        self.assertEqual(job.years_experience_required, 7)
        self.assertNotEqual(
            decide_retention(job, create_daniel_profile()),
            RetentionDecision.REJECT,
        )


if __name__ == "__main__":
    unittest.main()
