"""Regras locais e determinísticas para avaliar oportunidades de trabalho."""

from dataclasses import dataclass
from enum import Enum
import re
from urllib.parse import urlsplit, urlunsplit

from .models import JobOpportunity


class RolePriority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    IRRELEVANT = "IRRELEVANT"


class GeographicEligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    UNKNOWN = "UNKNOWN"


class RetentionDecision(str, Enum):
    KEEP = "KEEP"
    REVIEW = "REVIEW"
    REJECT = "REJECT"


def _normalize_whitespace(value: str) -> str:
    """Remove espaços externos e transforma espaços repetidos em um só."""

    return " ".join(value.split())


def normalize_company(company: str) -> str:
    """Normaliza somente espaços, preservando grafia e capitalização."""

    return _normalize_whitespace(company)


def normalize_role(role: str) -> str:
    """Normaliza espaços do título sem eliminar pequenas variações úteis."""

    return _normalize_whitespace(role)


def normalize_location(location: str) -> str:
    """Normaliza espaços da localização anunciada."""

    return _normalize_whitespace(location)


def _comparable(value: str) -> str:
    """Cria texto comparável sem alterar o valor exibido ao usuário."""

    return _normalize_whitespace(value).casefold()


# Frases específicas vêm antes das genéricas para evitar que, por exemplo,
# "Business Development Representative" seja confundido com prioridade alta.
_MEDIUM_ROLES = (
    "sales development representative",
    "business development representative",
    "sdr",
    "bdr",
)
_HIGH_ROLES = (
    "enterprise account executive",
    "account executive",
    "sales executive",
    "inside sales",
    "account manager",
    "business development executive",
    "business development",
    "sales representative",
    "full cycle sales",
)
_IRRELEVANT_ROLES = (
    "software engineer",
    "data engineer",
    "product designer",
    "accountant",
)


def _contains_phrase(title: str, phrase: str) -> bool:
    """Encontra uma frase como palavras completas, aceitando pontuação."""

    pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"
    return re.search(pattern, title) is not None


def classify_role(role: str) -> RolePriority:
    """Classifica títulos comerciais; desconhecidos seguem para revisão."""

    title = _comparable(role)
    if any(_contains_phrase(title, item) for item in _IRRELEVANT_ROLES):
        return RolePriority.IRRELEVANT
    if any(_contains_phrase(title, item) for item in _MEDIUM_ROLES):
        return RolePriority.MEDIUM
    if any(_contains_phrase(title, item) for item in _HIGH_ROLES):
        return RolePriority.HIGH
    # O enum é pequeno por solicitação. Títulos desconhecidos não são rejeitados:
    # IRRELEVANT aqui significa "sem aderência confirmada" e a retenção os revisa.
    return RolePriority.IRRELEVANT


_NOT_ELIGIBLE_LOCATIONS = (
    "remote - us only",
    "united states only",
    "us only",
    "u.s. only",
)
_ELIGIBLE_LOCATIONS = (
    "remote - brazil",
    "remote - latam",
    "latin america",
    "worldwide remote",
)


def evaluate_geographic_eligibility(location: str) -> GeographicEligibility:
    """Interpreta apenas padrões geográficos explícitos desta primeira etapa."""

    normalized = _comparable(location)
    if any(phrase in normalized for phrase in _NOT_ELIGIBLE_LOCATIONS):
        return GeographicEligibility.NOT_ELIGIBLE
    if any(phrase in normalized for phrase in _ELIGIBLE_LOCATIONS):
        return GeographicEligibility.ELIGIBLE
    return GeographicEligibility.UNKNOWN


def normalize_job_url(url: str) -> str:
    """Remove diferenças comuns de URL que não identificam outra vaga."""

    parts = urlsplit(url.strip())
    scheme = parts.scheme.casefold()
    hostname = (parts.hostname or "").casefold()
    port = parts.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        hostname = f"{hostname}:{port}"
    path = parts.path.rstrip("/") or "/"
    # Query strings normalmente contêm parâmetros de rastreamento. Fragmentos
    # apontam para uma parte da mesma página, não para outra oportunidade.
    return urlunsplit((scheme, hostname, path, "", ""))


def are_probably_duplicates(first: JobOpportunity, second: JobOpportunity) -> bool:
    """Compara URL ou, como alternativa, empresa e cargo normalizados."""

    same_url = normalize_job_url(first.job_url) == normalize_job_url(second.job_url)
    same_company_and_role = (
        _comparable(first.company) == _comparable(second.company)
        and _comparable(first.role) == _comparable(second.role)
    )
    return same_url or same_company_and_role


@dataclass(frozen=True, slots=True)
class ScoreWeights:
    """Pesos explícitos para facilitar ajustes futuros sem reescrever regras."""

    high_role: int = 65
    medium_role: int = 45
    unknown_or_irrelevant_role: int = 5
    eligible_location: int = 20
    unknown_location: int = 0
    not_eligible_location: int = -70
    remote: int = 10


DEFAULT_SCORE_WEIGHTS = ScoreWeights()


def calculate_match_score(
    job: JobOpportunity, weights: ScoreWeights = DEFAULT_SCORE_WEIGHTS
) -> int:
    """Calcula score de 0 a 100 sem modificar a oportunidade recebida."""

    priority = classify_role(job.role)
    eligibility = evaluate_geographic_eligibility(job.location)
    role_points = {
        RolePriority.HIGH: weights.high_role,
        RolePriority.MEDIUM: weights.medium_role,
        RolePriority.IRRELEVANT: weights.unknown_or_irrelevant_role,
    }[priority]
    location_points = {
        GeographicEligibility.ELIGIBLE: weights.eligible_location,
        GeographicEligibility.UNKNOWN: weights.unknown_location,
        GeographicEligibility.NOT_ELIGIBLE: weights.not_eligible_location,
    }[eligibility]
    score = role_points + location_points + (weights.remote if job.remote else 0)
    return max(0, min(100, score))


def decide_retention(job: JobOpportunity) -> RetentionDecision:
    """Decide sem rejeitar uma vaga apenas por localização desconhecida."""

    priority = classify_role(job.role)
    eligibility = evaluate_geographic_eligibility(job.location)

    if eligibility is GeographicEligibility.NOT_ELIGIBLE:
        return RetentionDecision.REJECT
    if priority is RolePriority.IRRELEVANT:
        # Títulos explicitamente fora do objetivo e títulos ainda não conhecidos
        # compartilham o enum, por isso só os exemplos claros são rejeitados.
        title = _comparable(job.role)
        if any(_contains_phrase(title, item) for item in _IRRELEVANT_ROLES):
            return RetentionDecision.REJECT
        return RetentionDecision.REVIEW
    if eligibility is GeographicEligibility.ELIGIBLE and calculate_match_score(job) >= 70:
        return RetentionDecision.KEEP
    return RetentionDecision.REVIEW
