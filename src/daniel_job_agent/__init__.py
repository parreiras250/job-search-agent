"""Componentes públicos do Daniel Job Agent."""

from .models import ApplicationStatus, ApplicationTracking, JobOpportunity
from .rules import (
    GeographicEligibility,
    RetentionDecision,
    RolePriority,
    ScoreWeights,
    are_probably_duplicates,
    calculate_match_score,
    classify_role,
    decide_retention,
    evaluate_geographic_eligibility,
    normalize_company,
    normalize_job_url,
    normalize_location,
    normalize_role,
)

__all__ = [
    "ApplicationStatus",
    "ApplicationTracking",
    "GeographicEligibility",
    "JobOpportunity",
    "RetentionDecision",
    "RolePriority",
    "ScoreWeights",
    "are_probably_duplicates",
    "calculate_match_score",
    "classify_role",
    "decide_retention",
    "evaluate_geographic_eligibility",
    "normalize_company",
    "normalize_job_url",
    "normalize_location",
    "normalize_role",
]
