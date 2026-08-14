"""Modelos de dados usados pelo Daniel Job Agent."""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone


@dataclass(slots=True)
class JobOpportunity:
    """Representa uma vaga encontrada e seu estado no futuro CRM.

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
    remote: bool
    brazil_eligible: bool
    employment_type: str | None = None

    # Remuneração. Float mantém o modelo simples nesta etapa; a moeda será
    # modelada separadamente quando existirem fontes reais de vagas.
    base_salary: float | None = None
    ote: float | None = None  # OTE: ganho total esperado ao atingir a meta.

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
