"""Demonstração real e compacta da contribuição das fontes globais."""

from __future__ import annotations

from .discovery import MultiSourceDiscovery
from .profiles import create_daniel_profile
from .source_contribution import SourceContributionResult


_LABELS = {
    "jobicy": "Jobicy",
    "remotive": "Remotive",
    "weworkremotely": "We Work Remotely",
    "himalayas": "Himalayas",
    "remoteok": "RemoteOK",
    "getonboard": "Get on Board",
    "latamcent": "LatamCent (Ashby)",
}


def _ratio(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}"


def format_source_efficiency(result: SourceContributionResult) -> str:
    """Formata métricas sem imprimir vagas ou payloads completos."""

    lines = ["Source contribution", ""]
    for source_id in result.operational_order:
        item = result.contributions[source_id]
        label = _LABELS.get(source_id, source_id)
        if item.status != "SUCCESS":
            lines.extend([f"{label}: FAILED", "Contribution: unavailable", ""])
            continue
        lines.extend(
            [
                f"{label}: SUCCESS",
                f"Received: {item.received} | Converted: {item.converted} | Requests: {item.requests}",
                f"Observed unique: {item.unique_contributed} | Incremental unique: +{item.incremental_unique}",
                f"Incremental KEEP: +{item.incremental_keep} | REVIEW: +{item.incremental_review} | REJECT: +{item.incremental_reject}",
                f"Incremental relevant: +{item.incremental_relevant} | Overlap: {item.overlap_count}",
                "Requests/incremental unique: "
                f"{_ratio(item.requests_per_incremental_unique)} | "
                "Requests/incremental relevant: "
                f"{_ratio(item.requests_per_incremental_relevant)}",
                "",
            ]
        )

    lines.append("Overlap matrix")
    for (left, right), count in result.overlap_matrix.items():
        lines.append(
            f"{_LABELS.get(left, left)} ↔ {_LABELS.get(right, right)}: {count}"
        )
    lines.extend(["", "Himalayas delta"])
    delta = result.himalayas_delta
    if delta is None:
        lines.append("Contribution: unavailable")
    else:
        lines.extend(
            [
                f"Unique: {delta.baseline_unique} → {delta.expanded_unique} (+{delta.incremental_unique})",
                f"KEEP: {delta.baseline_keep} → {delta.expanded_keep} (+{delta.incremental_keep})",
                f"Relevant: {delta.baseline_relevant} → {delta.expanded_relevant} (+{delta.incremental_relevant})",
                f"Cross-source duplicates involving Himalayas: {delta.cross_source_duplicates}",
            ]
        )
    return "\n".join(lines)


def main() -> None:
    """Executa as fontes globais; uso manual, fora dos testes."""

    discovery = MultiSourceDiscovery().run(create_daniel_profile())
    print(format_source_efficiency(discovery.source_contributions))


if __name__ == "__main__":
    main()
