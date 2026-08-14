"""Testes do modelo JobOpportunity usando apenas a biblioteca padrão."""

import sys
import unittest
from datetime import date
from pathlib import Path

# Permite importar o pacote diretamente da pasta src sem instalar o projeto.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from daniel_job_agent import JobOpportunity  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
