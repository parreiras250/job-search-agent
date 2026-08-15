"""Testes do modelo JobOpportunity usando apenas a biblioteca padrão."""

import sys
import unittest
from datetime import date
from pathlib import Path

# Permite importar o pacote diretamente da pasta src sem instalar o projeto.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from daniel_job_agent import (  # noqa: E402
    ApplicationStatus,
    ApplicationTracking,
    JobOpportunity,
    calculate_match_score,
    decide_retention,
)


class JobOpportunityTests(unittest.TestCase):
    """Confirma os comportamentos essenciais do modelo."""

    def make_job(self, **changes: object) -> JobOpportunity:
        """Cria uma vaga válida e permite alterar campos em cada teste."""

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

    def test_creates_opportunity_with_safe_defaults(self) -> None:
        job = self.make_job()

        self.assertEqual(job.company, "Example Inc.")
        self.assertEqual(job.date_found, date.today())
        self.assertIsNone(job.match_score)
        self.assertEqual(job.why_match, [])
        self.assertEqual(job.potential_gaps, [])

    def test_rejects_match_score_outside_zero_to_one_hundred(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 100"):
            self.make_job(match_score=101)

    def test_rejects_empty_required_text(self) -> None:
        with self.assertRaisesRegex(ValueError, "company"):
            self.make_job(company="   ")

    def test_lists_are_not_shared_between_opportunities(self) -> None:
        first = self.make_job()
        second = self.make_job()

        first.why_match.append("Relevant sales experience")

        self.assertEqual(second.why_match, [])

    def test_manual_tracking_has_safe_independent_defaults(self) -> None:
        first = self.make_job()
        second = self.make_job()

        first.tracking.notes = "Recruiter asked for availability."
        first.tracking.application_status = ApplicationStatus.RECRUITER_SCREEN

        self.assertEqual(second.tracking.application_status, ApplicationStatus.NOT_APPLIED)
        self.assertIsNone(second.tracking.notes)

    def test_rules_do_not_overwrite_manual_tracking_data(self) -> None:
        tracking = ApplicationTracking(
            application_status=ApplicationStatus.APPLIED,
            applied_date=date(2026, 8, 14),
            recruiter_name="Ana",
            recruiter_email="ana@example.com",
            next_step="Recruiter screen",
            next_step_date=date(2026, 8, 20),
            notes="Application sent directly.",
        )
        job = self.make_job(tracking=tracking)

        calculate_match_score(job)
        decide_retention(job)

        self.assertIs(job.tracking, tracking)
        self.assertEqual(job.tracking.application_status, ApplicationStatus.APPLIED)
        self.assertEqual(job.tracking.notes, "Application sent directly.")


if __name__ == "__main__":
    unittest.main()
