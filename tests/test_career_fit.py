import unittest

from daniel_job_agent import (
    JobOpportunity,
    RetentionDecision,
    RoleFamily,
    Seniority,
    classify_role_family,
    classify_seniority,
    create_daniel_profile,
    decide_retention,
    evaluate_match,
)


def make_job(role: str, identifier: str = "1", **changes: object) -> JobOpportunity:
    values = {
        "company": "Example SaaS",
        "role": role,
        "job_url": f"https://example.com/jobs/{identifier}",
        "source": "Local fixture",
        "location": "Remote - LATAM",
        "remote": True,
        "brazil_eligible": True,
    }
    values.update(changes)
    return JobOpportunity(**values)  # type: ignore[arg-type]


class RoleFamilyClassificationTests(unittest.TestCase):
    def test_classifies_each_configured_family(self):
        cases = {
            "Account Executive": RoleFamily.CLOSING_SALES,
            "Enterprise Account Executive": RoleFamily.CLOSING_SALES,
            "Inside Sales Contractor": RoleFamily.CLOSING_SALES,
            "Sales Development Representative": RoleFamily.SALES_DEVELOPMENT,
            "BDR": RoleFamily.SALES_DEVELOPMENT,
            "Account Manager": RoleFamily.ACCOUNT_MANAGEMENT,
            "Sales Manager": RoleFamily.SALES_LEADERSHIP,
            "Sales Engineer": RoleFamily.PRE_SALES,
            "Customer Success Manager": RoleFamily.CUSTOMER_SUCCESS,
            "Partner Sales Manager": RoleFamily.PARTNERSHIPS,
            "Product Marketing Manager": RoleFamily.MARKETING,
            "Software Engineer": RoleFamily.ENGINEERING,
            "Product Manager": RoleFamily.PRODUCT,
            "Remote Office Assistant": RoleFamily.OPERATIONS,
            "Freelance Copywriter": RoleFamily.WRITING_CONTENT,
            "Financial Analyst": RoleFamily.FINANCE,
            "Legal Counsel": RoleFamily.LEGAL,
            "Recruiter": RoleFamily.HR_RECRUITING,
            "Revenue Enablement Specialist": RoleFamily.OTHER,
        }
        for role, expected in cases.items():
            with self.subTest(role=role):
                self.assertEqual(classify_role_family(role), expected)

    def test_precedence_protects_commercial_technical_roles(self):
        self.assertEqual(classify_role_family("Sales Engineer"), RoleFamily.PRE_SALES)
        self.assertEqual(
            classify_role_family("Technical Account Manager"),
            RoleFamily.ACCOUNT_MANAGEMENT,
        )
        self.assertNotEqual(
            classify_role_family("Product Marketing Manager"),
            RoleFamily.PRODUCT,
        )

    def test_classifies_hyphenated_pre_sales_title(self):
        self.assertEqual(
            classify_role_family("Pre-Sales Solutions Architect"),
            RoleFamily.PRE_SALES,
        )

    def test_classifies_compact_presales_title(self):
        self.assertEqual(
            classify_role_family("Presales Solutions Architect"),
            RoleFamily.PRE_SALES,
        )

    def test_classifies_spaced_pre_sales_title(self):
        self.assertEqual(
            classify_role_family("Pre Sales Consultant"),
            RoleFamily.PRE_SALES,
        )

    def test_sdr_director_is_leadership_not_development(self):
        self.assertEqual(
            classify_role_family("Regional SDR Director"),
            RoleFamily.SALES_LEADERSHIP,
        )


class SeniorityClassificationTests(unittest.TestCase):
    def test_classifies_explicit_title_seniority(self):
        cases = {
            "Graduate Sales Development Representative": Seniority.ENTRY,
            "Junior Account Executive": Seniority.ENTRY,
            "Account Executive": Seniority.INDIVIDUAL_CONTRIBUTOR,
            "Senior Account Executive": Seniority.SENIOR_IC,
            "Enterprise Account Executive": Seniority.SENIOR_IC,
            "Sales Manager": Seniority.MANAGER,
            "Regional Sales Director": Seniority.DIRECTOR,
            "Enterprise Sales VP": Seniority.VP_EXECUTIVE,
            "Head of Sales": Seniority.VP_EXECUTIVE,
            "Freelance Copywriter": Seniority.UNKNOWN,
        }
        for role, expected in cases.items():
            with self.subTest(role=role):
                self.assertEqual(classify_seniority(role), expected)

    def test_account_and_customer_success_manager_are_ic_titles(self):
        for role in ("Account Manager", "Technical Account Manager", "Customer Success Manager"):
            with self.subTest(role=role):
                self.assertEqual(
                    classify_seniority(role), Seniority.INDIVIDUAL_CONTRIBUTOR
                )


class CareerFitEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.profile = create_daniel_profile()

    def test_enterprise_ae_is_strong_keep_with_explanation(self):
        evaluation = evaluate_match(
            make_job("Enterprise Account Executive"), self.profile
        )
        self.assertEqual(evaluation.role_family, RoleFamily.CLOSING_SALES)
        self.assertEqual(evaluation.seniority, Seniority.SENIOR_IC)
        self.assertGreaterEqual(evaluation.score, 90)
        self.assertEqual(
            decide_retention(make_job("Enterprise Account Executive"), self.profile),
            RetentionDecision.KEEP,
        )
        self.assertTrue(
            any("primary target: Closing Sales" in reason for reason in evaluation.positive_reasons)
        )
        self.assertTrue(
            any("Senior individual contributor" in reason for reason in evaluation.positive_reasons)
        )

    def test_inside_sales_is_strong_closing_fit(self):
        evaluation = evaluate_match(make_job("Inside Sales Contractor"), self.profile)
        self.assertEqual(evaluation.role_family, RoleFamily.CLOSING_SALES)
        self.assertGreaterEqual(evaluation.score, 90)

    def test_graduate_sdr_remains_valid_but_ranks_below_ae(self):
        ae = evaluate_match(make_job("Account Executive", "ae"), self.profile)
        graduate = evaluate_match(
            make_job("Graduate Sales Development Representative", "sdr"),
            self.profile,
        )
        self.assertEqual(graduate.role_family, RoleFamily.SALES_DEVELOPMENT)
        self.assertEqual(graduate.seniority, Seniority.ENTRY)
        self.assertLess(graduate.score, ae.score)
        self.assertNotEqual(
            decide_retention(
                make_job("Graduate Sales Development Representative", "sdr"),
                self.profile,
            ),
            RetentionDecision.REJECT,
        )
        self.assertTrue(any("below current career level" in gap for gap in graduate.potential_gaps))

    def test_director_and_vp_are_soft_stretches_and_review(self):
        cases = (
            ("Regional SDR Director", Seniority.DIRECTOR),
            ("Regional Sales Director, Brazil", Seniority.DIRECTOR),
            ("Enterprise Sales VP", Seniority.VP_EXECUTIVE),
        )
        for role, seniority in cases:
            with self.subTest(role=role):
                job = make_job(role)
                evaluation = evaluate_match(job, self.profile)
                self.assertEqual(evaluation.role_family, RoleFamily.SALES_LEADERSHIP)
                self.assertEqual(evaluation.seniority, seniority)
                self.assertEqual(decide_retention(job, self.profile), RetentionDecision.REVIEW)
                self.assertTrue(any("stretch" in gap.casefold() for gap in evaluation.potential_gaps))

    def test_seniority_alone_never_causes_reject(self):
        for role in ("Account Executive Director", "Account Executive VP"):
            with self.subTest(role=role):
                self.assertNotEqual(
                    decide_retention(make_job(role), self.profile),
                    RetentionDecision.REJECT,
                )

    def test_out_of_focus_families_are_rejected(self):
        cases = (
            "Freelance Copywriter",
            "Remote Office Assistant",
            "AI Engineer",
            "Product Marketing Manager",
        )
        for role in cases:
            with self.subTest(role=role):
                self.assertEqual(
                    decide_retention(make_job(role), self.profile),
                    RetentionDecision.REJECT,
                )

    def test_pre_sales_and_technical_account_management_are_not_rejected(self):
        for role in ("Sales Engineer", "Technical Account Manager"):
            with self.subTest(role=role):
                self.assertNotEqual(
                    decide_retention(make_job(role), self.profile),
                    RetentionDecision.REJECT,
                )

    def test_unknown_seniority_is_explained_without_penalty(self):
        evaluation = evaluate_match(
            make_job("Revenue Enablement Specialist"), self.profile
        )
        self.assertEqual(evaluation.seniority, Seniority.UNKNOWN)
        self.assertTrue(
            any("Seniority could not be determined" in item for item in evaluation.unknowns)
        )


if __name__ == "__main__":
    unittest.main()
