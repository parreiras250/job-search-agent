"""Componentes públicos do Daniel Job Agent."""

from .models import (
    ApplicationStatus,
    ApplicationTracking,
    CandidateProfile,
    JobOpportunity,
)
from .pipeline import (
    DuplicateRecord,
    PipelineResult,
    ProcessedOpportunity,
    process_opportunities,
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
    "DuplicateRecord",
    "GeographicEligibility",
    "JobOpportunity",
    "MatchEvaluation",
    "PipelineResult",
    "ProcessedOpportunity",
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
    "process_opportunities",
]
