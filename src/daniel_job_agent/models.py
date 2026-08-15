"""Modelos de dados usados pelo Daniel Job Agent."""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum


class ApplicationStatus(str, Enum):
    """Etapas que Daniel pode registrar manualmente no processo seletivo."""

    NOT_APPLIED = "NOT_APPLIED"
    APPLIED = "APPLIED"
    RECRUITER_SCREEN = "RECRUITER_SCREEN"
    HIRING_MANAGER = "HIRING_MANAGER"
    INTERVIEW = "INTERVIEW"
    FINAL_INTERVIEW = "FINAL_INTERVIEW"
    OFFER = "OFFER"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


@dataclass(slots=True)
class ApplicationTracking:
    """Dados manuais do CRM, separados das informações publicadas da vaga.

    Regras automáticas recebem este objeto apenas como parte da oportunidade e
    nunca o modificam. Assim, futuras atualizações de anúncios podem preservar
    todo o acompanhamento feito pelo usuário.
    """

    application_status: ApplicationStatus = ApplicationStatus.NOT_APPLIED
    applied_date: date | None = None
    recruiter_name: str | None = None
    recruiter_email: str | None = None
    next_step: str | None = None
    next_step_date: date | None = None
    notes: str | None = None


@dataclass(slots=True)
class CandidateProfile:
    """Informações profissionais usadas para comparar o candidato com vagas."""

    name: str
    years_experience: float | None
    target_roles: list[str] = field(default_factory=list)
    secondary_roles: list[str] = field(default_factory=list)
    preferred_markets: list[str] = field(default_factory=list)
    remote_only: bool = True
    brazil_based: bool = True
    contractor_ok: bool = True
    us_market_experience: bool | None = None
    b2b_experience: bool | None = None
    saas_experience: bool | None = None
    full_cycle_sales: bool | None = None
    outbound_experience: bool | None = None
    customer_success_experience: bool | None = None
    account_management_experience: bool | None = None
    enterprise_sales_experience: bool | None = None
    tools: list[str] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    minimum_base_salary: float | None = None
    preferred_base_salary: float | None = None
    preferred_ote: float | None = None
    preferred_currency: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("name cannot be empty")
        if self.years_experience is not None and self.years_experience < 0:
            raise ValueError("years_experience cannot be negative")
        salary_fields = (
            self.minimum_base_salary,
            self.preferred_base_salary,
            self.preferred_ote,
        )
        if any(value is not None and value < 0 for value in salary_fields):
            raise ValueError("salary preferences cannot be negative")


@dataclass(slots=True)
class JobOpportunity:
    """Representa os dados encontrados em um anúncio de vaga.

    Os campos essenciais para identificar a vaga não têm valor padrão. Os
    campos que podem estar ausentes no anúncio usam ``None``. Isso permite
    distinguir um dado desconhecido de um valor igual a zero.
    """

    # Identificação e origem da oportunidade.
    company: str
    role: str
    job_url: str
    source: str

    # Localização e regras básicas de elegibilidade.
    location: str
    # None significa que a fonte não informou ou não permitiu confirmar.
    remote: bool | None
    brazil_eligible: bool | None
    employment_type: str | None = None

    # Conteúdo estruturado fornecido pela origem da vaga. Nesta etapa nenhum
    # texto livre é interpretado automaticamente.
    description: str | None = None
    requirements: list[str] | None = None
    responsibilities: list[str] | None = None
    preferred_qualifications: list[str] | None = None
    tools_mentioned: list[str] | None = None
    industries_mentioned: list[str] | None = None
    years_experience_required: float | None = None
    full_cycle_sales_required: bool | None = None
    outbound_sales_required: bool | None = None
    inbound_sales_mentioned: bool | None = None
    b2b_experience_required: bool | None = None
    saas_experience_required: bool | None = None

    # Remuneração. Float mantém o modelo simples nesta etapa; a moeda será
    # modelada separadamente quando existirem fontes reais de vagas.
    base_salary: float | None = None
    ote: float | None = None  # OTE: ganho total esperado ao atingir a meta.
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None

    # Metadados opcionais preservados quando uma fonte os fornece.
    external_id: str | None = None
    job_level: str | None = None

    # Datas do anúncio e do acompanhamento interno.
    date_found: date = field(default_factory=date.today)
    date_posted: date | None = None

    # Resultado da comparação futura com o perfil profissional.
    match_score: float | None = None
    why_match: list[str] = field(default_factory=list)
    potential_gaps: list[str] = field(default_factory=list)

    # Estado da vaga. None significa que ainda não foi possível confirmar.
    still_open: bool | None = None
    last_checked: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # Informações preenchidas pelo usuário. Elas ficam agrupadas para não serem
    # confundidas nem sobrescritas por futuras atualizações automáticas da vaga.
    tracking: ApplicationTracking = field(default_factory=ApplicationTracking)

    def __post_init__(self) -> None:
        """Impede a criação de registros com valores claramente inválidos."""

        # Strings vazias dificultariam identificar e deduplicar oportunidades.
        required_text = {
            "company": self.company,
            "role": self.role,
            "job_url": self.job_url,
            "source": self.source,
            "location": self.location,
        }
        empty_fields = [name for name, value in required_text.items() if not value.strip()]
        if empty_fields:
            fields = ", ".join(empty_fields)
            raise ValueError(f"Required text fields cannot be empty: {fields}")

        # O Match Score, quando conhecido, deve ficar entre 0 e 100.
        if self.match_score is not None and not 0 <= self.match_score <= 100:
            raise ValueError("match_score must be between 0 and 100")

        # Salários negativos representam erro de entrada.
        if self.base_salary is not None and self.base_salary < 0:
            raise ValueError("base_salary cannot be negative")
        if self.ote is not None and self.ote < 0:
            raise ValueError("ote cannot be negative")
        if self.salary_min is not None and self.salary_min < 0:
            raise ValueError("salary_min cannot be negative")
        if self.salary_max is not None and self.salary_max < 0:
            raise ValueError("salary_max cannot be negative")
        if (
            self.years_experience_required is not None
            and self.years_experience_required < 0
        ):
            raise ValueError("years_experience_required cannot be negative")
