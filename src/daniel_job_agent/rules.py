"""Regras locais e determinísticas para avaliar oportunidades de trabalho."""

from dataclasses import dataclass
from enum import Enum
import re
from urllib.parse import urlsplit, urlunsplit

from .models import CandidateProfile, JobOpportunity, RoleFamily, Seniority


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


@dataclass(frozen=True, slots=True)
class MatchEvaluation:
    """Resultado explicável da comparação entre uma vaga e um perfil."""

    score: int
    positive_reasons: list[str]
    potential_gaps: list[str]
    unknowns: list[str]
    role_family: RoleFamily
    seniority: Seniority


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
    "backend engineer",
    "frontend engineer",
    "ai engineer",
    "machine learning engineer",
    "devops engineer",
    "infrastructure engineer",
    "product designer",
    "product manager",
    "accountant",
    "legal counsel",
    "talent acquisition",
    "researcher",
)
_PROTECTED_TECHNICAL_SALES_ROLES = (
    "sales engineer",
    "solutions engineer",
    "technical account manager",
)


def _contains_phrase(title: str, phrase: str) -> bool:
    """Encontra uma frase como palavras completas, aceitando pontuação."""

    pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"
    return re.search(pattern, title) is not None


def is_clearly_irrelevant_role(role: str) -> bool:
    """Reconhece famílias fora de vendas e protege cargos comerciais técnicos."""

    title = _comparable(role)
    if any(
        _contains_phrase(title, protected)
        for protected in _PROTECTED_TECHNICAL_SALES_ROLES
    ):
        return False
    if any(_contains_phrase(title, item) for item in _IRRELEVANT_ROLES):
        return True
    family = classify_role_family(role)
    if family in {
        RoleFamily.MARKETING,
        RoleFamily.ENGINEERING,
        RoleFamily.PRODUCT,
        RoleFamily.OPERATIONS,
        RoleFamily.WRITING_CONTENT,
        RoleFamily.FINANCE,
        RoleFamily.LEGAL,
        RoleFamily.HR_RECRUITING,
    }:
        return True
    return (
        _contains_phrase(title, "engineer")
        or _contains_phrase(title, "hr")
    )


def classify_role(role: str) -> RolePriority:
    """Classifica títulos comerciais; desconhecidos seguem para revisão."""

    title = _comparable(role)
    if is_clearly_irrelevant_role(role):
        return RolePriority.IRRELEVANT
    if any(_contains_phrase(title, item) for item in _MEDIUM_ROLES):
        return RolePriority.MEDIUM
    if any(_contains_phrase(title, item) for item in _HIGH_ROLES):
        return RolePriority.HIGH
    # O enum é pequeno por solicitação. Títulos desconhecidos não são rejeitados:
    # IRRELEVANT aqui significa "sem aderência confirmada" e a retenção os revisa.
    return RolePriority.IRRELEVANT


def classify_role_family(role: str) -> RoleFamily:
    """Classifica a função por precedência, protegendo cargos comerciais técnicos."""

    title = _comparable(role)
    if any(
        _contains_phrase(title, phrase)
        for phrase in ("pre-sales", "presales", "pre sales")
    ):
        return RoleFamily.PRE_SALES
    if any(
        _contains_phrase(title, phrase)
        for phrase in ("sales engineer", "solutions engineer", "solution engineer")
    ):
        return RoleFamily.PRE_SALES
    if _contains_phrase(title, "technical account manager"):
        return RoleFamily.ACCOUNT_MANAGEMENT
    if any(
        _contains_phrase(title, phrase)
        for phrase in ("partner sales", "partnership", "alliances", "channel manager")
    ):
        return RoleFamily.PARTNERSHIPS
    if (
        any(_contains_phrase(title, phrase) for phrase in ("sales", "sdr", "bdr"))
        and any(
            _contains_phrase(title, phrase)
            for phrase in ("manager", "director", "vp", "vice president", "head of")
        )
    ):
        return RoleFamily.SALES_LEADERSHIP
    precedence = (
        (RoleFamily.PRE_SALES, ("sales engineer", "solutions engineer", "solution engineer")),
        (RoleFamily.ACCOUNT_MANAGEMENT, ("technical account manager", "account manager")),
        (RoleFamily.CUSTOMER_SUCCESS, ("customer success", "client success")),
        (RoleFamily.SALES_DEVELOPMENT, ("sales development representative", "business development representative", "sdr", "bdr")),
        (RoleFamily.SALES_LEADERSHIP, ("sales manager", "sales director", "director of sales", "vp sales", "vp of sales", "sales vp", "vice president of sales", "head of sales", "sdr director")),
        (RoleFamily.CLOSING_SALES, ("account executive", "sales executive", "inside sales", "sales representative", "full cycle sales", "business development executive")),
        (RoleFamily.WRITING_CONTENT, ("copywriter", "content writer", "technical writer", "editor")),
        (RoleFamily.MARKETING, ("marketing", "growth marketer", "demand generation")),
        (RoleFamily.PRODUCT, ("product manager", "product designer", "product owner")),
        (RoleFamily.ENGINEERING, ("software engineer", "data engineer", "backend engineer", "frontend engineer", "ai engineer", "machine learning engineer", "devops engineer", "engineer")),
        (RoleFamily.HR_RECRUITING, ("recruiter", "talent acquisition", "human resources", "people operations")),
        (RoleFamily.LEGAL, ("legal counsel", "lawyer", "attorney", "paralegal")),
        (RoleFamily.FINANCE, ("accountant", "finance", "financial analyst", "controller")),
        (RoleFamily.OPERATIONS, ("office assistant", "administrative assistant", "operations", "chief of staff")),
    )
    for family, phrases in precedence:
        if any(_contains_phrase(title, phrase) for phrase in phrases):
            return family
    return RoleFamily.OTHER


def classify_seniority(role: str) -> Seniority:
    """Usa somente o título e não interpreta descrição, salário ou responsabilidades."""

    title = _comparable(role)
    if any(_contains_phrase(title, phrase) for phrase in ("vp", "vice president", "head of", "chief revenue officer", "cro")):
        return Seniority.VP_EXECUTIVE
    if _contains_phrase(title, "director"):
        return Seniority.DIRECTOR
    if any(_contains_phrase(title, phrase) for phrase in ("graduate", "junior", "entry level", "entry-level")):
        return Seniority.ENTRY
    if any(_contains_phrase(title, phrase) for phrase in ("senior", "sr", "principal", "enterprise account executive")):
        return Seniority.SENIOR_IC
    family = classify_role_family(role)
    protected_ic = family in {
        RoleFamily.ACCOUNT_MANAGEMENT,
        RoleFamily.CUSTOMER_SUCCESS,
        RoleFamily.PARTNERSHIPS,
    }
    if _contains_phrase(title, "manager") and not protected_ic:
        return Seniority.MANAGER
    if family in {
        RoleFamily.CLOSING_SALES,
        RoleFamily.SALES_DEVELOPMENT,
        RoleFamily.ACCOUNT_MANAGEMENT,
        RoleFamily.PRE_SALES,
        RoleFamily.CUSTOMER_SUCCESS,
        RoleFamily.PARTNERSHIPS,
    }:
        return Seniority.INDIVIDUAL_CONTRIBUTOR
    return Seniority.UNKNOWN


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
_JOBICY_ELIGIBLE_LOCATIONS = {
    "brazil",
    "latam",
    "latin america",
    "anywhere",
    "worldwide",
    "americas",
}
_JOBICY_NOT_ELIGIBLE_LOCATIONS = {
    "usa",
    "united states",
    "europe",
    "emea",
}


def evaluate_geographic_eligibility(
    location: str, role: str | None = None
) -> GeographicEligibility:
    """Interpreta sinais explícitos de localização e, opcionalmente, do título."""

    normalized = _comparable(location)
    if normalized in _JOBICY_NOT_ELIGIBLE_LOCATIONS:
        return GeographicEligibility.NOT_ELIGIBLE
    if normalized in _JOBICY_ELIGIBLE_LOCATIONS:
        return GeographicEligibility.ELIGIBLE
    if any(phrase in normalized for phrase in _NOT_ELIGIBLE_LOCATIONS):
        return GeographicEligibility.NOT_ELIGIBLE
    if any(phrase in normalized for phrase in _ELIGIBLE_LOCATIONS):
        return GeographicEligibility.ELIGIBLE
    if role is not None:
        normalized_role = _comparable(role)
        if re.search(
            r"(?<!\w)(?:us-only|usa|united states)(?!\w)", normalized_role
        ):
            return GeographicEligibility.NOT_ELIGIBLE
        if re.search(
            r"(?<!\w)(?:latam|latin america|brazil)(?!\w)", normalized_role
        ):
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
    experience_meets_requirement: int = 3
    experience_small_gap: int = -5
    experience_moderate_gap: int = -10
    experience_large_gap: int = -20
    tool_overlap_each: int = 2
    tool_overlap_limit: int = 6
    industry_overlap_each: int = 5
    industry_overlap_limit: int = 10
    relevant_experience_signal: int = 3
    primary_family: int = 65
    relevant_family: int = 45
    stretch_family: int = 25
    unknown_family: int = 5
    out_of_focus_family: int = -70
    entry_seniority: int = -15
    manager_seniority: int = -3
    director_seniority: int = -10
    vp_executive_seniority: int = -15


DEFAULT_SCORE_WEIGHTS = ScoreWeights()


def _profile_role_priority(job: JobOpportunity, profile: CandidateProfile) -> RolePriority:
    """Compara o cargo com as listas configuradas no perfil."""

    title = _comparable(job.role)
    if any(_contains_phrase(title, _comparable(role)) for role in profile.target_roles):
        return RolePriority.HIGH
    if any(_contains_phrase(title, _comparable(role)) for role in profile.secondary_roles):
        return RolePriority.MEDIUM
    return classify_role(job.role)


def _normalized_overlap(first: list[str], second: list[str] | None) -> list[str]:
    """Retorna itens do perfil também mencionados pela vaga, sem duplicatas."""

    if not second:
        return []
    second_values = {_comparable(item) for item in second}
    return [item for item in first if _comparable(item) in second_values]


def _legacy_score(job: JobOpportunity, weights: ScoreWeights) -> int:
    """Mantém exatamente o cálculo validado antes da introdução do perfil."""

    priority = classify_role(job.role)
    eligibility = evaluate_geographic_eligibility(job.location, job.role)
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


def evaluate_match(
    job: JobOpportunity,
    profile: CandidateProfile,
    weights: ScoreWeights = DEFAULT_SCORE_WEIGHTS,
) -> MatchEvaluation:
    """Compara vaga e perfil usando somente dados estruturados e regras claras."""

    family = classify_role_family(job.role)
    seniority = classify_seniority(job.role)
    eligibility = evaluate_geographic_eligibility(job.location, job.role)
    positive_reasons: list[str] = []
    potential_gaps: list[str] = []
    unknowns: list[str] = []

    family_label = family.value.replace("_", " ").title()
    configured_families = (
        profile.primary_role_families
        + profile.relevant_role_families
        + profile.stretch_role_families
        + profile.out_of_focus_role_families
    )
    if not configured_families:
        priority = _profile_role_priority(job, profile)
        role_points = {
            RolePriority.HIGH: weights.high_role,
            RolePriority.MEDIUM: weights.medium_role,
            RolePriority.IRRELEVANT: weights.unknown_or_irrelevant_role,
        }[priority]
        if priority is RolePriority.HIGH:
            positive_reasons.append(
                f"High-priority role match: {normalize_role(job.role)}"
            )
        elif priority is RolePriority.MEDIUM:
            positive_reasons.append(
                f"Secondary role match: {normalize_role(job.role)}"
            )
    elif family in profile.primary_role_families:
        role_points = weights.primary_family
        positive_reasons.append(
            f"Role family matches primary target: {family_label}"
        )
    elif family in profile.relevant_role_families:
        role_points = weights.relevant_family
        positive_reasons.append(f"Role family is relevant: {family_label}")
    elif family in profile.stretch_role_families:
        role_points = weights.stretch_family
        potential_gaps.append(f"Role family is a career stretch: {family_label}")
    elif family in profile.out_of_focus_role_families:
        role_points = weights.out_of_focus_family
        potential_gaps.append(f"Role family is outside the current career focus: {family_label}")
    else:
        role_points = weights.unknown_family
        unknowns.append("Role family is not recognized as a configured career target")

    seniority_points = 0
    if seniority is Seniority.ENTRY:
        seniority_points = weights.entry_seniority
        potential_gaps.append("Entry-level role may be below current career level")
    elif seniority is Seniority.INDIVIDUAL_CONTRIBUTOR:
        positive_reasons.append("Individual contributor level aligns with target")
    elif seniority is Seniority.SENIOR_IC:
        positive_reasons.append("Senior individual contributor level aligns with target")
    elif seniority is Seniority.MANAGER:
        seniority_points = weights.manager_seniority
        potential_gaps.append("Manager-level role is a mild stretch relative to current profile")
    elif seniority is Seniority.DIRECTOR:
        seniority_points = weights.director_seniority
        potential_gaps.append("Director-level role is a stretch relative to current profile")
    elif seniority is Seniority.VP_EXECUTIVE:
        seniority_points = weights.vp_executive_seniority
        potential_gaps.append("VP/Executive-level role is a significant career stretch")
    else:
        unknowns.append("Seniority could not be determined from title")

    location_points = {
        GeographicEligibility.ELIGIBLE: weights.eligible_location,
        GeographicEligibility.UNKNOWN: weights.unknown_location,
        GeographicEligibility.NOT_ELIGIBLE: weights.not_eligible_location,
    }[eligibility]
    if eligibility is GeographicEligibility.ELIGIBLE:
        positive_reasons.append("Brazil/LATAM eligible")
    elif eligibility is GeographicEligibility.NOT_ELIGIBLE:
        potential_gaps.append("Location is explicitly incompatible with Brazil/LATAM")
    else:
        unknowns.append("Brazil/LATAM eligibility is not clear")

    remote_points = weights.remote if job.remote else 0
    if job.remote is True:
        positive_reasons.append("Remote opportunity")
    elif job.remote is False and profile.remote_only:
        potential_gaps.append("Profile requires remote work, but the role is not remote")
    elif job.remote is None:
        unknowns.append("Remote work arrangement is not disclosed")

    experience_points = 0
    required = job.years_experience_required
    available = profile.years_experience
    if required is None:
        unknowns.append("Years of experience required are not disclosed")
    elif available is None:
        unknowns.append("Candidate years of experience are unknown")
    else:
        difference = required - available
        if difference <= 0:
            experience_points = weights.experience_meets_requirement
            positive_reasons.append("Experience meets the stated years requirement")
        elif difference <= 2:
            experience_points = weights.experience_small_gap
            potential_gaps.append(
                f"Role requests {required:g} years; profile has approximately {available:g}"
            )
        elif difference <= 4:
            experience_points = weights.experience_moderate_gap
            potential_gaps.append(
                f"Moderate experience gap: {required:g} years requested versus {available:g}"
            )
        else:
            experience_points = weights.experience_large_gap
            potential_gaps.append(
                f"Large experience gap: {required:g} years requested versus {available:g}"
            )

    common_tools = _normalized_overlap(profile.tools, job.tools_mentioned)
    tool_points = min(
        len(common_tools) * weights.tool_overlap_each,
        weights.tool_overlap_limit,
    )
    if common_tools:
        positive_reasons.append(f"Tools in common: {', '.join(common_tools)}")
    elif job.tools_mentioned is None:
        unknowns.append("Tools used by the role are not disclosed")
    elif job.tools_mentioned:
        potential_gaps.append("No overlap found among the tools explicitly mentioned")

    common_industries = _normalized_overlap(profile.industries, job.industries_mentioned)
    industry_points = min(
        len(common_industries) * weights.industry_overlap_each,
        weights.industry_overlap_limit,
    )
    if common_industries:
        positive_reasons.append(f"Industry experience match: {', '.join(common_industries)}")
    elif job.industries_mentioned is None:
        unknowns.append("Industry or business context is not disclosed")
    elif job.industries_mentioned:
        potential_gaps.append("No overlap found among the industries explicitly mentioned")

    experience_signal_points = 0
    role_text = _comparable(job.role)
    role_signals = (
        ("full cycle", profile.full_cycle_sales, "Full-cycle sales experience is relevant"),
        ("account manager", profile.account_management_experience, "Account Management experience is relevant"),
        ("enterprise", profile.enterprise_sales_experience, "Enterprise Sales experience is relevant"),
        ("customer success", profile.customer_success_experience, "Customer Success experience is relevant"),
    )
    for phrase, has_experience, reason in role_signals:
        if phrase in role_text and has_experience:
            experience_signal_points += weights.relevant_experience_signal
            positive_reasons.append(reason)

    structured_signals = (
        (
            job.full_cycle_sales_required,
            profile.full_cycle_sales,
            "Full-cycle sales experience matches an explicit requirement",
            "Full-cycle sales requirement is not disclosed",
        ),
        (
            job.outbound_sales_required,
            profile.outbound_experience,
            "Outbound sales experience matches an explicit requirement",
            "Outbound sales requirement is not disclosed",
        ),
        (
            job.b2b_experience_required,
            profile.b2b_experience,
            "B2B experience matches an explicit requirement",
            "B2B experience requirement is not disclosed",
        ),
        (
            job.saas_experience_required,
            profile.saas_experience,
            "SaaS experience matches an explicit requirement",
            "SaaS experience requirement is not disclosed",
        ),
    )
    for required_signal, profile_signal, reason, unknown in structured_signals:
        if required_signal is True and profile_signal is True:
            experience_signal_points += weights.relevant_experience_signal
            positive_reasons.append(reason)
        elif required_signal is None:
            unknowns.append(unknown)
    if job.inbound_sales_mentioned is None:
        unknowns.append("Inbound sales motion is not disclosed")
    elif job.inbound_sales_mentioned is True:
        positive_reasons.append("Inbound sales motion is explicitly mentioned")

    if job.base_salary is None and job.ote is None:
        unknowns.append("Compensation is not disclosed")

    score = (
        role_points
        + seniority_points
        + location_points
        + remote_points
        + experience_points
        + tool_points
        + industry_points
        + experience_signal_points
    )
    return MatchEvaluation(
        score=max(0, min(100, score)),
        positive_reasons=positive_reasons,
        potential_gaps=potential_gaps,
        unknowns=unknowns,
        role_family=family,
        seniority=seniority,
    )


def calculate_match_score(
    job: JobOpportunity,
    weights: ScoreWeights = DEFAULT_SCORE_WEIGHTS,
    profile: CandidateProfile | None = None,
) -> int:
    """Calcula o score sem alterar a vaga; perfil é opcional por compatibilidade."""

    if profile is None:
        return _legacy_score(job, weights)
    return evaluate_match(job, profile, weights).score


def decide_retention(
    job: JobOpportunity,
    profile: CandidateProfile | None = None,
    weights: ScoreWeights = DEFAULT_SCORE_WEIGHTS,
) -> RetentionDecision:
    """Decide sem rejeitar uma vaga apenas por localização desconhecida."""

    priority = classify_role(job.role)
    family = classify_role_family(job.role)
    seniority = classify_seniority(job.role)
    eligibility = evaluate_geographic_eligibility(job.location, job.role)

    if eligibility is GeographicEligibility.NOT_ELIGIBLE:
        return RetentionDecision.REJECT
    if profile is not None and family in profile.out_of_focus_role_families:
        return RetentionDecision.REJECT
    if (
        profile is not None
        and family in profile.stretch_role_families
        and seniority in {Seniority.DIRECTOR, Seniority.VP_EXECUTIVE}
    ):
        return RetentionDecision.REVIEW
    if priority is RolePriority.IRRELEVANT:
        # Títulos explicitamente fora do objetivo e títulos ainda não conhecidos
        # compartilham o enum, por isso só os exemplos claros são rejeitados.
        if is_clearly_irrelevant_role(job.role):
            return RetentionDecision.REJECT
        return RetentionDecision.REVIEW
    score = calculate_match_score(job, weights, profile)
    if eligibility is GeographicEligibility.ELIGIBLE and score >= 70:
        return RetentionDecision.KEEP
    return RetentionDecision.REVIEW
