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


class EligibilityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    LIKELY_ELIGIBLE = "LIKELY_ELIGIBLE"
    UNCERTAIN = "UNCERTAIN"
    LIKELY_INELIGIBLE = "LIKELY_INELIGIBLE"
    INELIGIBLE = "INELIGIBLE"


class TitleGeographyCategory(str, Enum):
    """Tipo de sinal geográfico encontrado no título da oportunidade."""

    COMPATIBLE_REGION = "COMPATIBLE_REGION"
    INCOMPATIBLE_REGION = "INCOMPATIBLE_REGION"
    US_LOCAL_TERRITORY = "US_LOCAL_TERRITORY"
    UNKNOWN_MARKET_REFERENCE = "UNKNOWN_MARKET_REFERENCE"


@dataclass(frozen=True, slots=True)
class TitleGeographySignal:
    category: TitleGeographyCategory
    label: str
    explicit_worker_restriction: bool = False


class TimezoneCompatibility(str, Enum):
    HIGH = "HIGH"
    REASONABLE = "REASONABLE"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class OpportunityRisk(str, Enum):
    COMMISSION_ONLY = "COMMISSION_ONLY"
    NO_BASE_SALARY = "NO_BASE_SALARY"
    UNPAID = "UNPAID"


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
    eligibility: EligibilityStatus
    timezone_compatibility: TimezoneCompatibility
    opportunity_risks: tuple[OpportunityRisk, ...]
    decision_reasons: list[str]
    retention_decision: RetentionDecision


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
    "maintenance planner",
    "facilities planner",
    "estimator",
    "artificial intelligence specialist",
    "customer service representative",
    "customer service agent",
    "customer support representative",
    "graphic designer",
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
        for phrase in (
            "pre-sales",
            "presales",
            "pre sales",
            "technical sales specialist",
        )
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
        (RoleFamily.WRITING_CONTENT, ("copywriter", "content writer", "technical writer", "writer", "editor")),
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
    "must reside in the us",
    "must reside in us",
    "authorized to work in the us",
    "authorized to work in us",
    "canada only",
    "europe only",
    "eu only",
    "uk only",
    "apac only",
    "remote - united states",
    "remote - usa",
    "remote, united states",
)
_ELIGIBLE_LOCATIONS = (
    "remote - brazil",
    "remote - latam",
    "latin america",
    "worldwide remote",
    "worldwide",
    "anywhere",
    "global",
    "south america",
    "americas",
    "latam",
    "brazil",
    "brasil",
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
    if any(phrase in normalized for phrase in _ELIGIBLE_LOCATIONS):
        return GeographicEligibility.ELIGIBLE
    if any(phrase in normalized for phrase in _NOT_ELIGIBLE_LOCATIONS):
        return GeographicEligibility.NOT_ELIGIBLE
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


_INCOMPATIBLE_REGIONS = {
    "united states", "usa", "us", "canada", "europe", "eu", "emea",
    "united kingdom", "uk", "apac", "india", "morocco", "australia",
    "new zealand", "japan", "china", "singapore",
}

_BROAD_LOCATION_SIGNALS = {"worldwide", "anywhere", "global", "remote"}
_TITLE_COMPATIBLE_REGIONS = (
    ("latin america", "Latin America"),
    ("latam", "LATAM"),
    ("brazil", "Brazil"),
    ("brasil", "Brasil"),
    ("americas", "Americas"),
)
_TITLE_INCOMPATIBLE_REGION_ALIASES = (
    (("uki", "uk&i", "uk & ireland"), "UK & Ireland"),
    (("dach",), "DACH"),
    (("emea",), "EMEA"),
    (("apac",), "APAC"),
    (("anz", "australia & new zealand"), "Australia & New Zealand"),
    (("benelux",), "Benelux"),
    (("nordics",), "Nordics"),
    (("eastern saudi arabia", "saudi arabia"), "Eastern Saudi Arabia"),
    (("united kingdom", "uk"), "United Kingdom"),
    (("germany",), "Germany"),
    (("france",), "France"),
    (("australia",), "Australia"),
    (("japan",), "Japan"),
    (("india",), "India"),
)
_TITLE_US_LOCAL_TERRITORIES = (
    ("sf/bay area", "SF/Bay Area"),
    ("bay area", "Bay Area"),
    ("new york", "New York"),
)


def analyze_title_geography(role: str) -> TitleGeographySignal | None:
    """Extrai sinais territoriais pequenos e explícitos sem inferir residência."""

    title = _comparable(role)
    market_match = re.search(
        r"(?<!\w)(us|u\.s\.|united states)\s+(market|customers?)(?!\w)",
        title,
    )
    if market_match:
        return TitleGeographySignal(
            TitleGeographyCategory.UNKNOWN_MARKET_REFERENCE,
            market_match.group(0),
        )

    worker_language = bool(re.search(
        r"(?<!\w)(?:in[- ]territory|based in|located in|resident of|must reside|remote in)(?!\w)",
        title,
    )) or bool(re.search(r"(?<!\w)[\w./ -]+[- ]based(?!\w)", title))

    for signal, label in _TITLE_COMPATIBLE_REGIONS:
        if _contains_phrase(title, signal):
            return TitleGeographySignal(
                TitleGeographyCategory.COMPATIBLE_REGION, label, worker_language
            )
    for signal, label in _TITLE_US_LOCAL_TERRITORIES:
        if _contains_phrase(title, signal):
            return TitleGeographySignal(
                TitleGeographyCategory.US_LOCAL_TERRITORY,
                label,
                worker_language or "in-territory" in title,
            )
    for aliases, label in _TITLE_INCOMPATIBLE_REGION_ALIASES:
        if any(_contains_phrase(title, alias) for alias in aliases):
            return TitleGeographySignal(
                TitleGeographyCategory.INCOMPATIBLE_REGION,
                label,
                worker_language,
            )
    return None


def _structured_locations_are_broad(names: list[str]) -> bool:
    return not names or all(
        any(_contains_phrase(name, signal) for signal in _BROAD_LOCATION_SIGNALS)
        for name in names
    )


def evaluate_eligibility(job: JobOpportunity) -> EligibilityStatus:
    """Avalia geografia com precedência para restrições estruturadas."""

    restrictions = job.location_restrictions
    if restrictions is not None:
        names = [_comparable(item.name) for item in restrictions]
        title_signal = analyze_title_geography(job.role)
        if _structured_locations_are_broad(names):
            if title_signal is None:
                return EligibilityStatus.ELIGIBLE
            if title_signal.category is TitleGeographyCategory.COMPATIBLE_REGION:
                return EligibilityStatus.ELIGIBLE
            if title_signal.category is TitleGeographyCategory.UNKNOWN_MARKET_REFERENCE:
                return EligibilityStatus.UNCERTAIN
            if title_signal.explicit_worker_restriction:
                return EligibilityStatus.INELIGIBLE
            return EligibilityStatus.LIKELY_INELIGIBLE
        if any(
            any(signal in name for signal in _ELIGIBLE_LOCATIONS)
            or name in {"brazil", "brasil", "latam", "latin america"}
            for name in names
        ):
            return EligibilityStatus.ELIGIBLE
        # A coleção estruturada representa o conjunto permitido. Países ou
        # regiões específicos sem sinal LATAM/Brazil são incompatíveis.
        if all(name and name != "remote" for name in names):
            return EligibilityStatus.INELIGIBLE
        return EligibilityStatus.UNCERTAIN

    legacy = evaluate_geographic_eligibility(job.location, job.role)
    if legacy is GeographicEligibility.ELIGIBLE:
        title_signal = analyze_title_geography(job.role)
        if title_signal is not None and any(
            signal in _comparable(job.location)
            for signal in _BROAD_LOCATION_SIGNALS
        ):
            if title_signal.category is TitleGeographyCategory.UNKNOWN_MARKET_REFERENCE:
                return EligibilityStatus.UNCERTAIN
            if title_signal.category in {
                TitleGeographyCategory.INCOMPATIBLE_REGION,
                TitleGeographyCategory.US_LOCAL_TERRITORY,
            }:
                if title_signal.explicit_worker_restriction:
                    return EligibilityStatus.INELIGIBLE
                return EligibilityStatus.LIKELY_INELIGIBLE
        return EligibilityStatus.ELIGIBLE
    if legacy is GeographicEligibility.NOT_ELIGIBLE:
        return EligibilityStatus.INELIGIBLE

    location = _comparable(job.location)
    if location in _INCOMPATIBLE_REGIONS:
        return EligibilityStatus.INELIGIBLE
    if job.brazil_eligible is True:
        return EligibilityStatus.LIKELY_ELIGIBLE
    if job.brazil_eligible is False:
        return EligibilityStatus.LIKELY_INELIGIBLE
    return EligibilityStatus.UNCERTAIN


def evaluate_timezone_compatibility(job: JobOpportunity) -> TimezoneCompatibility:
    """Avalia somente compatibilidade de horário, nunca geografia."""

    values = job.timezone_restrictions
    if values is not None:
        if not values:
            return TimezoneCompatibility.HIGH
        numeric = [
            float(value) for value in values
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        if len(numeric) >= 10 and min(numeric) <= -10 and max(numeric) >= 12:
            return TimezoneCompatibility.HIGH
        if any(-10 <= value <= -3 for value in numeric):
            return TimezoneCompatibility.HIGH
        if numeric and all(-1 <= value <= 3 for value in numeric):
            return TimezoneCompatibility.LOW
        if numeric and all(value >= 4 or value <= -11 for value in numeric):
            return TimezoneCompatibility.LOW

    timezone_text = " ".join(
        str(value) for value in (values or []) if isinstance(value, str)
    )
    text = _comparable(
        " ".join((job.location, job.description or "", timezone_text))
    )
    if any(
        phrase in text
        for phrase in (
            "eastern time", "central time", "mountain time", "pacific time",
            "est hours", "cst hours", "mst hours", "pst hours",
            "us business hours", "u.s. business hours", "latam business hours",
            "brazil business hours",
        )
    ):
        return TimezoneCompatibility.HIGH
    if any(
        phrase in text
        for phrase in (
            "european business hours", "europe business hours", "cet hours",
            "india business hours", "ist hours", "asia business hours",
            "australia business hours", "new zealand business hours",
        )
    ):
        return TimezoneCompatibility.LOW
    if values:
        return TimezoneCompatibility.REASONABLE
    return TimezoneCompatibility.UNKNOWN


def evaluate_opportunity_risks(job: JobOpportunity) -> tuple[OpportunityRisk, ...]:
    """Detecta somente riscos de remuneração com evidência textual forte."""

    text = _comparable(
        " ".join(
            value for value in (
                job.description, job.salary_text, job.employment_type
            ) if value
        )
    )
    risks: list[OpportunityRisk] = []
    if re.search(
        r"(?<!\w)(?:commission[- ]only|full commission|100% commission|commission[- ]based[- ]only)(?!\w)",
        text,
    ):
        risks.append(OpportunityRisk.COMMISSION_ONLY)
    if re.search(r"(?<!\w)no base (?:salary|pay)(?!\w)", text):
        risks.append(OpportunityRisk.NO_BASE_SALARY)
    if re.search(r"(?<!\w)(?:unpaid|volunteer)(?!\w)", text):
        risks.append(OpportunityRisk.UNPAID)
    return tuple(risks)


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
    primary_family: int = 90
    relevant_family: int = 65
    stretch_family: int = 45
    unknown_family: int = 15
    out_of_focus_family: int = 0
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
    eligibility = evaluate_eligibility(job)
    timezone_compatibility = evaluate_timezone_compatibility(job)
    opportunity_risks = evaluate_opportunity_risks(job)
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

    if eligibility in {EligibilityStatus.ELIGIBLE, EligibilityStatus.LIKELY_ELIGIBLE}:
        positive_reasons.append("Brazil/LATAM eligible")
    elif eligibility in {EligibilityStatus.INELIGIBLE, EligibilityStatus.LIKELY_INELIGIBLE}:
        potential_gaps.append("Location is explicitly incompatible with Brazil/LATAM")
    else:
        unknowns.append("Brazil/LATAM eligibility is not clear")

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

    if timezone_compatibility is TimezoneCompatibility.HIGH:
        positive_reasons.append("Timezone is highly compatible")
    elif timezone_compatibility is TimezoneCompatibility.LOW:
        potential_gaps.append("Timezone has low compatibility with Brazil/US hours")
    elif timezone_compatibility is TimezoneCompatibility.UNKNOWN:
        unknowns.append("Timezone compatibility is not disclosed")
    for risk in opportunity_risks:
        potential_gaps.append(
            f"Opportunity quality risk: {risk.value.replace('_', ' ').title()}"
        )

    score = (
        role_points
        + seniority_points
        + experience_points
        + tool_points
        + industry_points
        + experience_signal_points
    )
    career_fit_score = max(0, min(100, score))
    decision, decision_reasons = _final_decision(
        job=job,
        profile=profile,
        career_fit_score=career_fit_score,
        family=family,
        seniority=seniority,
        eligibility=eligibility,
        timezone_compatibility=timezone_compatibility,
        opportunity_risks=opportunity_risks,
    )
    return MatchEvaluation(
        score=career_fit_score,
        positive_reasons=positive_reasons,
        potential_gaps=potential_gaps,
        unknowns=unknowns,
        role_family=family,
        seniority=seniority,
        eligibility=eligibility,
        timezone_compatibility=timezone_compatibility,
        opportunity_risks=opportunity_risks,
        decision_reasons=decision_reasons,
        retention_decision=decision,
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


def _final_decision(
    *,
    job: JobOpportunity,
    profile: CandidateProfile,
    career_fit_score: int,
    family: RoleFamily,
    seniority: Seniority,
    eligibility: EligibilityStatus,
    timezone_compatibility: TimezoneCompatibility,
    opportunity_risks: tuple[OpportunityRisk, ...],
) -> tuple[RetentionDecision, list[str]]:
    title_signal = analyze_title_geography(job.role)
    hard_compensation_risks = {
        OpportunityRisk.COMMISSION_ONLY,
        OpportunityRisk.NO_BASE_SALARY,
        OpportunityRisk.UNPAID,
    }
    if family in profile.out_of_focus_role_families or is_clearly_irrelevant_role(job.role):
        return RetentionDecision.REJECT, ["Role family is outside target profile"]
    if eligibility is EligibilityStatus.INELIGIBLE:
        if title_signal is not None and title_signal.explicit_worker_restriction:
            return RetentionDecision.REJECT, [
                f"Role explicitly limited to {title_signal.label} territory"
            ]
        return RetentionDecision.REJECT, ["Geographic restriction excludes Brazil/LATAM"]
    if hard_compensation_risks.intersection(opportunity_risks):
        labels = ", ".join(risk.value for risk in opportunity_risks)
        return RetentionDecision.REJECT, [f"Hard compensation risk: {labels}"]
    if profile.remote_only and job.remote is False:
        return RetentionDecision.REJECT, ["Role is explicitly non-remote"]
    if eligibility is EligibilityStatus.LIKELY_INELIGIBLE:
        if title_signal is not None:
            return RetentionDecision.REVIEW, [
                f"Title indicates {title_signal.label} sales territory; "
                "Brazil eligibility is not supported"
            ]
        return RetentionDecision.REVIEW, ["Brazil/LATAM eligibility is likely incompatible"]
    if family is RoleFamily.OTHER:
        return RetentionDecision.REVIEW, ["Role title needs manual career-fit review"]
    if (
        family in profile.stretch_role_families
        and seniority in {Seniority.DIRECTOR, Seniority.VP_EXECUTIVE}
    ):
        return RetentionDecision.REVIEW, ["Relevant title, but seniority is a career stretch"]
    if eligibility is EligibilityStatus.UNCERTAIN:
        if (
            title_signal is not None
            and title_signal.category is TitleGeographyCategory.UNKNOWN_MARKET_REFERENCE
        ):
            return RetentionDecision.REVIEW, [
                f"Title references {title_signal.label} as a market, not a residence requirement"
            ]
        return RetentionDecision.REVIEW, ["Strong career fit, but geographic eligibility is unclear"]
    if profile.remote_only and job.remote is None:
        return RetentionDecision.REVIEW, ["Remote work arrangement is not confirmed"]
    if timezone_compatibility is TimezoneCompatibility.LOW:
        return RetentionDecision.REVIEW, ["Eligible role with low timezone compatibility"]
    if career_fit_score >= 60:
        geography_reason = "Brazil/LATAM eligibility supported"
        if (
            title_signal is not None
            and title_signal.category is TitleGeographyCategory.COMPATIBLE_REGION
        ):
            geography_reason = (
                f"{title_signal.label} title aligns with Brazil/LATAM eligibility"
            )
        return RetentionDecision.KEEP, [
            "Career fit meets target",
            geography_reason,
            "No hard opportunity-quality risk detected",
        ]
    return RetentionDecision.REVIEW, ["Relevant role requires manual career-fit review"]


def decide_retention(
    job: JobOpportunity,
    profile: CandidateProfile | None = None,
    weights: ScoreWeights = DEFAULT_SCORE_WEIGHTS,
) -> RetentionDecision:
    """Combina fit, eligibility, timezone e hard risks sem os ocultar no score."""

    if profile is not None:
        return evaluate_match(job, profile, weights).retention_decision

    eligibility = evaluate_eligibility(job)
    risks = evaluate_opportunity_risks(job)
    if (
        eligibility is EligibilityStatus.INELIGIBLE
        or is_clearly_irrelevant_role(job.role)
        or risks
    ):
        return RetentionDecision.REJECT
    priority = classify_role(job.role)
    if priority is RolePriority.IRRELEVANT or eligibility is EligibilityStatus.UNCERTAIN:
        return RetentionDecision.REVIEW
    score = calculate_match_score(job, weights)
    if eligibility in {EligibilityStatus.ELIGIBLE, EligibilityStatus.LIKELY_ELIGIBLE} and score >= 70:
        return RetentionDecision.KEEP
    return RetentionDecision.REVIEW
