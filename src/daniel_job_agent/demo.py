"""Demonstração de terminal do pipeline local."""

from .demo_data import create_demo_jobs
from .pipeline import PipelineResult, process_opportunities
from .profiles import create_daniel_profile


def format_demo(result: PipelineResult) -> str:
    """Gera uma saída curta e legível, sem dependências externas."""

    lines = [
        "Daniel Job Agent — Local Demo",
        "",
        f"Total received: {result.total_received}",
        f"Unique opportunities: {result.unique_opportunities}",
        f"Duplicates detected: {result.duplicates_detected}",
        "",
        f"KEEP: {result.keep_count}",
        f"REVIEW: {result.review_count}",
        f"REJECT: {result.reject_count}",
        "",
        "Ranking:",
    ]
    for item in result.ranked_opportunities:
        job = item.normalized_job
        lines.extend(
            [
                f"{item.rank}. {job.role} — {job.company}",
                f"   Score: {item.match_score} | Decision: {item.retention_decision.value}",
            ]
        )
        if item.positive_reasons:
            lines.append(f"   Reason: {item.positive_reasons[0]}")
        if item.potential_gaps:
            lines.append(f"   Gap: {item.potential_gaps[0]}")
    return "\n".join(lines)


def main() -> None:
    result = process_opportunities(create_demo_jobs(), create_daniel_profile())
    print(format_demo(result))


if __name__ == "__main__":
    main()
