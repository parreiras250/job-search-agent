"""Validação manual da distribuição do ranking nas cinco fontes reais."""

from collections import Counter

from .discovery import MultiSourceDiscovery
from .profiles import create_daniel_profile
from .rules import EligibilityStatus, OpportunityRisk, RetentionDecision


def _reject_category(item: object) -> str:
    risks = set(getattr(item, "opportunity_risks"))
    if risks & {
        OpportunityRisk.COMMISSION_ONLY,
        OpportunityRisk.NO_BASE_SALARY,
        OpportunityRisk.UNPAID,
    }:
        return "compensation risk"
    if getattr(item, "eligibility") is EligibilityStatus.INELIGIBLE:
        return "geography"
    reasons = getattr(item, "decision_reasons")
    if any("outside target" in reason.casefold() for reason in reasons):
        return "role mismatch"
    return "other hard negative"


def main() -> None:
    result = MultiSourceDiscovery().run(create_daniel_profile())
    ranking = result.ranking
    decisions = Counter(item.retention_decision for item in ranking)
    rejects = Counter(
        _reject_category(item)
        for item in ranking
        if item.retention_decision is RetentionDecision.REJECT
    )
    print("Five-source ranking validation")
    print(
        f"KEEP: {decisions[RetentionDecision.KEEP]} | "
        f"REVIEW: {decisions[RetentionDecision.REVIEW]} | "
        f"REJECT: {decisions[RetentionDecision.REJECT]}"
    )
    print("\nReject summary:")
    for category in (
        "role mismatch", "geography", "compensation risk", "other hard negative"
    ):
        print(f"- {category}: {rejects[category]}")
    for decision in (RetentionDecision.KEEP, RetentionDecision.REVIEW):
        print(f"\nTop {decision.value}:")
        selected = [item for item in ranking if item.retention_decision is decision][:10]
        for item in selected:
            print(
                f"- {item.normalized_job.company} | {item.normalized_job.role} "
                f"| Career Fit {item.match_score} | {item.eligibility.value} "
                f"| {item.timezone_compatibility.value}"
            )


if __name__ == "__main__":
    main()
