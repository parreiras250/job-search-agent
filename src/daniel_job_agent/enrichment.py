"""Enriquecimento determinístico e conservador de descrições de vagas."""

from dataclasses import replace
from html import unescape
import re
from typing import Iterable

from .models import JobOpportunity


def _plain_search_text(description: str) -> str:
    """Prepara HTML já recebido para buscas literais, sem interpretar conteúdo."""

    without_tags = re.sub(r"<[^>]+>", " ", unescape(description))
    return " ".join(without_tags.casefold().split())


def extract_years_experience(description: str) -> float | None:
    """Extrai mínimos explícitos; em ranges, usa o menor número informado."""

    text = _plain_search_text(description)
    patterns = (
        r"(?<!\d)(\d+(?:\.\d+)?)\s*\+\s*years?\b(?:\s+of\s+experience)?",
        r"(?<!\d)(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*\d+(?:\.\d+)?\s+years?\b(?:\s+of\s+experience)?",
        r"(?<!\d)(\d+(?:\.\d+)?)\s+years?\s+of\s+experience",
    )
    values = [
        float(match.group(1))
        for pattern in patterns
        for match in re.finditer(pattern, text)
    ]
    return min(values) if values else None


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def enrich_job(job: JobOpportunity) -> JobOpportunity:
    """Cria uma cópia com sinais explícitos; ausência permanece desconhecida."""

    if not job.description:
        return replace(job)

    text = _plain_search_text(job.description)
    full_cycle = _contains_any(
        text,
        (
            "entire sales process",
            "full sales cycle",
            "complete sales cycle",
            "end-to-end sales cycle",
            "qualification to closing",
        ),
    )
    outbound = _contains_any(
        text,
        ("outbound", "direct prospecting", "cold outreach", "prospecting"),
    ) and not _contains_any(
        text,
        ("no outbound", "without outbound", "outbound is not required"),
    )
    inbound = "inbound" in text
    b2b = re.search(r"(?<!\w)b2b(?!\w)", text) is not None
    saas = re.search(r"(?<!\w)saas(?!\w)", text) is not None

    return replace(
        job,
        years_experience_required=(
            job.years_experience_required
            if job.years_experience_required is not None
            else extract_years_experience(job.description)
        ),
        full_cycle_sales_required=(
            job.full_cycle_sales_required
            if job.full_cycle_sales_required is not None
            else (True if full_cycle else None)
        ),
        outbound_sales_required=(
            job.outbound_sales_required
            if job.outbound_sales_required is not None
            else (True if outbound else None)
        ),
        inbound_sales_mentioned=(
            job.inbound_sales_mentioned
            if job.inbound_sales_mentioned is not None
            else (True if inbound else None)
        ),
        b2b_experience_required=(
            job.b2b_experience_required
            if job.b2b_experience_required is not None
            else (True if b2b else None)
        ),
        saas_experience_required=(
            job.saas_experience_required
            if job.saas_experience_required is not None
            else (True if saas else None)
        ),
    )


def enrich_opportunities(
    jobs: Iterable[JobOpportunity],
) -> list[JobOpportunity]:
    """Enriquece um lote localmente sem alterar as oportunidades recebidas."""

    return [enrich_job(job) for job in jobs]
