"""Componentes públicos do Daniel Job Agent."""

from .models import (
    ApplicationStatus,
    ApplicationTracking,
    CandidateProfile,
    JobOpportunity,
)
from .profiles import create_daniel_profile
from .rules import (
    GeographicEligibility,
    MatchEvaluation,
    RetentionDecision,
    RolePriority,
    ScoreWeights,
    are_probably_duplicates,
    calculate_match_score,
    classify_role,
    decide_retention,
    evaluate_match,
    evaluate_geographic_eligibility,
    normalize_company,
    normalize_job_url,
    normalize_location,
    normalize_role,
)

__all__ = [
    "ApplicationStatus",
    "ApplicationTracking",
    "CandidateProfile",
    "GeographicEligibility",
    "JobOpportunity",
    "MatchEvaluation",
    "RetentionDecision",
    "RolePriority",
    "ScoreWeights",
    "are_probably_duplicates",
    "calculate_match_score",
    "classify_role",
    "create_daniel_profile",
    "decide_retention",
    "evaluate_match",
    "evaluate_geographic_eligibility",
    "normalize_company",
    "normalize_job_url",
    "normalize_location",
    "normalize_role",
]
