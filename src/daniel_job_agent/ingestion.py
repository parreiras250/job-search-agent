"""Conversão local de registros brutos em oportunidades padronizadas."""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, Mapping

from .models import JobOpportunity
from .rules import normalize_company, normalize_location, normalize_role

RawJobRecord = Mapping[str, object]


class IngestionErrorType(str, Enum):
    """Tipos de falha esperados durante uma ingestão."""

    MISSING_REQUIRED_FIELDS = "MISSING_REQUIRED_FIELDS"
    VALIDATION_ERROR = "VALIDATION_ERROR"


@dataclass(frozen=True, slots=True)
class IngestionError:
    """Erro controlado associado a somente um registro bruto."""

    error_type: IngestionErrorType
    message: str
    raw_record: RawJobRecord
    record_index: int | None = None


@dataclass(frozen=True, slots=True)
class IngestionWarning:
    """Perda controlada em campo opcional que não impede a oportunidade."""

    field: str
    message: str
    raw_value: object
    record_index: int | None = None


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Resultado da tentativa de converter um único registro."""

    opportunity: JobOpportunity | None
    error: IngestionError | None
    optional_fields_missing: list[str]
    warnings: list[IngestionWarning]

    @property
    def success(self) -> bool:
        return self.opportunity is not None and self.error is None


@dataclass(frozen=True, slots=True)
class BatchIngestionResult:
    """Resumo de um lote, mantendo oportunidades e erros separadamente."""

    total_received: int
    converted_count: int
    error_count: int
    warning_count: int
    opportunities: list[JobOpportunity]
    errors: list[IngestionError]
    warnings: list[IngestionWarning]
    results: list[IngestionResult]


def _required_text(record: RawJobRecord, field_name: str) -> str | None:
    value = record.get(field_name)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _optional_text(record: RawJobRecord, field_name: str) -> str | None:
    value = record.get(field_name)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text")
    normalized = value.strip()
    return normalized or None


def _optional_boolean(
    record: RawJobRecord, field_name: str
) -> bool | None:
    value = record.get(field_name)
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise ValueError(f"{field_name} must be true or false")


def _optional_number(record: RawJobRecord, field_name: str) -> float | None:
    value = record.get(field_name)
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a simple number")
    if isinstance(value, (int, float)):
        number = float(value)
        if number < 0:
            raise ValueError(f"{field_name} cannot be negative")
        return number
    if isinstance(value, str):
        try:
            number = float(value.strip())
            if number < 0:
                raise ValueError(f"{field_name} cannot be negative")
            return number
        except ValueError as error:
            raise ValueError(f"{field_name} must be a simple number") from error
    raise ValueError(f"{field_name} must be a simple number")


def _optional_list(record: RawJobRecord, field_name: str) -> list[str] | None:
    value = record.get(field_name)
    if value is None or value == "":
        return None
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list of text values")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of text values")
    normalized = [" ".join(item.split()) for item in value if item.strip()]
    return normalized or None


class BaseJobAdapter:
    """Adapter pequeno configurado pelos nomes de campos de uma fonte."""

    source_name = "Unknown local source"
    company_field = "company"
    role_field = "role"
    url_field = "job_url"
    location_field = "location"
    remote_field = "remote"
    brazil_eligible_field = "brazil_eligible"
    description_field = "description"
    employment_type_field = "employment_type"
    salary_field = "base_salary"
    ote_field = "ote"
    currency_field = "salary_currency"
    tools_field = "tools_mentioned"
    industries_field = "industries_mentioned"
    years_field = "years_experience_required"

    def adapt(self, record: RawJobRecord) -> IngestionResult:
        """Converte um registro sem usar exceção como resultado esperado."""

        required_mapping = {
            "company": self.company_field,
            "role": self.role_field,
            "job_url": self.url_field,
            "location": self.location_field,
        }
        required_values = {
            target: _required_text(record, source)
            for target, source in required_mapping.items()
        }
        missing = [name for name, value in required_values.items() if value is None]
        if missing:
            return IngestionResult(
                opportunity=None,
                error=IngestionError(
                    error_type=IngestionErrorType.MISSING_REQUIRED_FIELDS,
                    message=f"Missing required fields: {', '.join(missing)}",
                    raw_record=record,
                ),
                optional_fields_missing=[],
                warnings=[],
            )

        optional_mapping = {
            "description": self.description_field,
            "employment_type": self.employment_type_field,
            "base_salary": self.salary_field,
            "ote": self.ote_field,
            "salary_currency": self.currency_field,
            "tools_mentioned": self.tools_field,
            "industries_mentioned": self.industries_field,
            "years_experience_required": self.years_field,
            "remote": self.remote_field,
            "brazil_eligible": self.brazil_eligible_field,
        }
        optional_missing = [
            target
            for target, source in optional_mapping.items()
            if record.get(source) is None or record.get(source) == ""
        ]

        try:
            warnings: list[IngestionWarning] = []

            def optional_value(
                target_name: str,
                source_name: str,
                converter: Callable[[RawJobRecord, str], object],
            ) -> object:
                """Converte um opcional ou registra warning e devolve None."""

                try:
                    return converter(record, source_name)
                except ValueError as error:
                    warnings.append(
                        IngestionWarning(
                            field=target_name,
                            message=str(error),
                            raw_value=record.get(source_name),
                        )
                    )
                    return None

            opportunity = JobOpportunity(
                company=normalize_company(required_values["company"] or ""),
                role=normalize_role(required_values["role"] or ""),
                job_url=(required_values["job_url"] or "").strip(),
                source=self.source_name,
                location=normalize_location(required_values["location"] or ""),
                remote=optional_value(
                    "remote", self.remote_field, _optional_boolean
                ),  # type: ignore[arg-type]
                brazil_eligible=optional_value(
                    "brazil_eligible",
                    self.brazil_eligible_field,
                    _optional_boolean,
                ),  # type: ignore[arg-type]
                employment_type=optional_value(
                    "employment_type", self.employment_type_field, _optional_text
                ),  # type: ignore[arg-type]
                description=optional_value(
                    "description", self.description_field, _optional_text
                ),  # type: ignore[arg-type]
                tools_mentioned=optional_value(
                    "tools_mentioned", self.tools_field, _optional_list
                ),  # type: ignore[arg-type]
                industries_mentioned=optional_value(
                    "industries_mentioned", self.industries_field, _optional_list
                ),  # type: ignore[arg-type]
                years_experience_required=optional_value(
                    "years_experience_required", self.years_field, _optional_number
                ),  # type: ignore[arg-type]
                base_salary=optional_value(
                    "base_salary", self.salary_field, _optional_number
                ),  # type: ignore[arg-type]
                ote=optional_value(
                    "ote", self.ote_field, _optional_number
                ),  # type: ignore[arg-type]
                salary_currency=optional_value(
                    "salary_currency", self.currency_field, _optional_text
                ),  # type: ignore[arg-type]
            )
        except ValueError as error:
            return IngestionResult(
                opportunity=None,
                error=IngestionError(
                    error_type=IngestionErrorType.VALIDATION_ERROR,
                    message=str(error),
                    raw_record=record,
                ),
                optional_fields_missing=optional_missing,
                warnings=[],
            )

        return IngestionResult(
            opportunity=opportunity,
            error=None,
            optional_fields_missing=optional_missing,
            warnings=warnings,
        )


class GenericJobAdapter(BaseJobAdapter):
    """Adapter do formato genérico fictício."""

    source_name = "Generic local source"
    role_field = "title"
    url_field = "url"


class MockGreenhouseAdapter(BaseJobAdapter):
    """Simula localmente um formato diferente, sem acessar Greenhouse."""

    source_name = "Mock Greenhouse"
    company_field = "organization_name"
    role_field = "position_name"
    url_field = "absolute_url"
    location_field = "workplace"
    salary_field = "salary"
    tools_field = "tools"
    industries_field = "industries"
    years_field = "experience_years"


class MockLeverAdapter(BaseJobAdapter):
    """Simula localmente um formato diferente, sem acessar Lever."""

    source_name = "Mock Lever"
    company_field = "employer"
    role_field = "job_title"
    url_field = "apply_url"
    location_field = "region"
    employment_type_field = "commitment"
    salary_field = "compensation"
    currency_field = "currency"
    tools_field = "stack"
    industries_field = "business_contexts"
    years_field = "minimum_years"


class GreenhouseJobAdapter(BaseJobAdapter):
    """Converte o formato real da listagem pública do Greenhouse."""

    source_name = "Greenhouse public Job Board"

    def __init__(self, company_name: str) -> None:
        if not company_name.strip():
            raise ValueError("company_name cannot be empty")
        self.company_name = company_name.strip()

    def adapt(self, record: RawJobRecord) -> IngestionResult:
        location_value = record.get("location")
        location = (
            location_value.get("name")
            if isinstance(location_value, Mapping)
            else None
        )
        mapped: dict[str, object] = {
            "company": self.company_name,
            "role": record.get("title"),
            "job_url": record.get("absolute_url"),
            "location": location,
            "description": record.get("content"),
            # These values are not structured in the list-jobs response.
            "remote": None,
            "brazil_eligible": None,
        }
        return super().adapt(mapped)


class LeverJobAdapter(BaseJobAdapter):
    """Converte o formato real da Postings API pública do Lever."""

    source_name = "Lever public postings"

    def __init__(self, company_name: str) -> None:
        if not company_name.strip():
            raise ValueError("company_name cannot be empty")
        self.company_name = company_name.strip()

    def adapt(self, record: RawJobRecord) -> IngestionResult:
        categories = record.get("categories")
        category_values = categories if isinstance(categories, Mapping) else {}
        description_parts: list[str] = []
        introduction = record.get("descriptionPlain") or record.get("description")
        if isinstance(introduction, str) and introduction.strip():
            description_parts.append(introduction.strip())
        lists = record.get("lists")
        if isinstance(lists, list):
            for section in lists:
                if not isinstance(section, Mapping):
                    continue
                heading = section.get("text")
                content = section.get("content")
                if isinstance(heading, str) and heading.strip():
                    description_parts.append(heading.strip())
                if isinstance(content, str) and content.strip():
                    description_parts.append(content.strip())
        additional = record.get("additionalPlain") or record.get("additional")
        if isinstance(additional, str) and additional.strip():
            description_parts.append(additional.strip())
        description = "\n\n".join(description_parts) or None
        mapped: dict[str, object] = {
            "company": self.company_name,
            "role": record.get("text"),
            "job_url": record.get("hostedUrl") or record.get("applyUrl"),
            "location": category_values.get("location"),
            "description": description,
            "employment_type": category_values.get("commitment"),
            "remote": None,
            "brazil_eligible": None,
        }
        return super().adapt(mapped)


def ingest_batch(
    records: Iterable[RawJobRecord], adapter: BaseJobAdapter
) -> BatchIngestionResult:
    """Converte um lote e continua após qualquer registro inválido."""

    received = list(records)
    results: list[IngestionResult] = []
    for index, record in enumerate(received, start=1):
        result = adapter.adapt(record)
        if result.error is not None:
            result = IngestionResult(
                opportunity=None,
                error=IngestionError(
                    error_type=result.error.error_type,
                    message=f"{adapter.source_name}: {result.error.message}",
                    raw_record=result.error.raw_record,
                    record_index=index,
                ),
                optional_fields_missing=result.optional_fields_missing,
                warnings=result.warnings,
            )
        results.append(result)

    opportunities = [
        result.opportunity
        for result in results
        if result.opportunity is not None
    ]
    errors = [result.error for result in results if result.error is not None]
    warnings = [warning for result in results for warning in result.warnings]
    indexed_warnings = [
        IngestionWarning(
            field=warning.field,
            message=warning.message,
            raw_value=warning.raw_value,
            record_index=index,
        )
        for index, result in enumerate(results, start=1)
        for warning in result.warnings
    ]
    return BatchIngestionResult(
        total_received=len(received),
        converted_count=len(opportunities),
        error_count=len(errors),
        warning_count=len(warnings),
        opportunities=opportunities,
        errors=errors,
        warnings=indexed_warnings,
        results=results,
    )


def combine_ingestion_batches(
    batches: Iterable[BatchIngestionResult],
) -> BatchIngestionResult:
    """Combina lotes de adapters diferentes para alimentar um único pipeline."""

    batch_list = list(batches)
    results = [result for batch in batch_list for result in batch.results]
    opportunities = [job for batch in batch_list for job in batch.opportunities]
    errors = [error for batch in batch_list for error in batch.errors]
    warnings = [warning for batch in batch_list for warning in batch.warnings]
    return BatchIngestionResult(
        total_received=sum(batch.total_received for batch in batch_list),
        converted_count=len(opportunities),
        error_count=len(errors),
        warning_count=len(warnings),
        opportunities=opportunities,
        errors=errors,
        warnings=warnings,
        results=results,
    )
