"""Perfis profissionais locais usados pelo Daniel Job Agent."""

from .models import CandidateProfile


def create_daniel_profile() -> CandidateProfile:
    """Cria o perfil padrão somente com informações fornecidas pelo Daniel."""

    return CandidateProfile(
        name="Daniel Pedrosa",
        years_experience=5,
        target_roles=[
            "Account Executive",
            "Enterprise Account Executive",
            "Sales Executive",
            "Inside Sales",
            "Full Cycle Sales",
            "Business Development Executive",
        ],
        secondary_roles=[
            "SDR",
            "BDR",
            "Sales Development Representative",
            "Business Development Representative",
        ],
        preferred_markets=["United States", "U.S. market"],
        remote_only=True,
        brazil_based=True,
        contractor_ok=True,
        us_market_experience=True,
        b2b_experience=True,
        saas_experience=True,
        full_cycle_sales=True,
        outbound_experience=True,
        customer_success_experience=True,
        account_management_experience=True,
        enterprise_sales_experience=True,
        tools=[
            "HubSpot",
            "Salesforce",
            "SalesLoft",
            "Apollo",
            "RollWorks",
            "LinkedIn",
            "ZoomInfo",
            "6sense",
            "Aircall",
            "Gong",
            "Slack",
            "Asana",
            "Confluence",
            "Fathom",
            "Google Workspace",
        ],
        industries=[
            "B2B SaaS",
            "Technology",
            "Healthtech",
            "Software Development Services",
        ],
        minimum_base_salary=None,
        preferred_base_salary=None,
        preferred_ote=None,
        preferred_currency="USD",
    )
