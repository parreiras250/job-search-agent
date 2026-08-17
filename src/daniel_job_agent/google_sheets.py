"""Exportação push-only do CRM SQLite para uma tab do Google Sheets."""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .crm import (
    MANUAL_FIELDS,
    CRMRecord,
    CRMRecordNotFound,
    CRMValidationError,
    LocalCRM,
)
from .models import ApplicationStatus
from .repository import JobRepository


SHEETS_SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)


@dataclass(frozen=True, slots=True)
class SheetColumn:
    field: str
    header: str


# Ordem visual estável. O ID interno fica no final para não poluir o uso diário.
GOOGLE_SHEET_COLUMNS = (
    SheetColumn("company", "Company"),
    SheetColumn("role", "Role"),
    SheetColumn("match_score", "Career Fit"),
    SheetColumn("retention_decision", "Decision"),
    SheetColumn("application_status", "Application Status"),
    SheetColumn("next_step", "Next Step"),
    SheetColumn("next_step_date", "Next Step Date"),
    SheetColumn("notes", "Notes"),
    SheetColumn("location", "Location"),
    SheetColumn("source", "Source"),
    SheetColumn("job_url", "Job URL"),
    SheetColumn("applied_date", "Applied Date"),
    SheetColumn("recruiter_name", "Recruiter Name"),
    SheetColumn("recruiter_email", "Recruiter Email"),
    SheetColumn("date_found", "Date Found"),
    SheetColumn("date_posted", "Date Posted"),
    SheetColumn("still_open", "Still Open"),
    SheetColumn("lifecycle_status", "Lifecycle Status"),
    SheetColumn("closed_at", "Closed At"),
    SheetColumn("positive_reasons", "Positive Reasons"),
    SheetColumn("potential_gaps", "Potential Gaps"),
    SheetColumn("unknowns", "Unknowns"),
    SheetColumn("role_family", "Role Family"),
    SheetColumn("seniority", "Seniority"),
    SheetColumn("eligibility", "Eligibility"),
    SheetColumn("timezone_compatibility", "Timezone Fit"),
    SheetColumn("opportunity_risks", "Opportunity Risk"),
    SheetColumn("decision_reasons", "Decision Reason"),
    SheetColumn("salary_min", "Salary Min"),
    SheetColumn("salary_max", "Salary Max"),
    SheetColumn("salary_currency", "Salary Currency"),
    SheetColumn("salary_period", "Salary Period"),
    SheetColumn("salary_text", "Salary Text"),
    SheetColumn("first_seen_at", "First Seen"),
    SheetColumn("last_seen_at", "Last Seen"),
    SheetColumn("last_checked", "Last Checked"),
    SheetColumn("observed_sources", "Observed Sources"),
    SheetColumn("internal_id", "Internal ID"),
)

MANUAL_SHEET_HEADERS = (
    "Application Status",
    "Applied Date",
    "Recruiter Name",
    "Recruiter Email",
    "Next Step",
    "Next Step Date",
    "Notes",
)
AUTOMATIC_SHEET_HEADERS = tuple(
    column.header
    for column in GOOGLE_SHEET_COLUMNS
    if column.header not in MANUAL_SHEET_HEADERS
)


@dataclass(frozen=True, slots=True)
class GoogleSheetsConfig:
    spreadsheet_id: str
    sheet_name: str = "Job CRM"
    credentials_path: Path = Path("credentials.json")
    token_path: Path = Path("token.json")

    def __post_init__(self) -> None:
        if not self.spreadsheet_id.strip():
            raise ValueError("spreadsheet_id is required")
        if not self.sheet_name.strip():
            raise ValueError("sheet_name cannot be empty")


@dataclass(frozen=True, slots=True)
class SheetSyncResult:
    spreadsheet_id: str
    sheet_name: str
    rows_written: int
    columns_written: int
    success: bool
    error: str | None
    synced_at: datetime


@dataclass(frozen=True, slots=True)
class SheetPullIssue:
    row_number: int | None
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class SheetPullResult:
    spreadsheet_id: str
    sheet_name: str
    rows_read: int
    rows_valid: int
    rows_unchanged: int
    rows_updated: int
    rows_skipped: int
    rows_errored: int
    success: bool
    error: str | None
    issues: list[SheetPullIssue]
    synced_at: datetime


FRIENDLY_HEADER_TO_FIELD = {
    column.header: column.field for column in GOOGLE_SHEET_COLUMNS
}
MANUAL_HEADER_TO_FIELD = {
    column.header: column.field
    for column in GOOGLE_SHEET_COLUMNS
    if column.field in MANUAL_FIELDS
}


def record_to_sheet_row(record: CRMRecord) -> list[object]:
    """Converte uma linha do CRM em valores seguros para a Sheets API."""

    row: list[object] = []
    for column in GOOGLE_SHEET_COLUMNS:
        value = getattr(record, column.field)
        if value is None:
            value = ""
        elif isinstance(value, Enum):
            value = value.value
        elif isinstance(value, (date, datetime)):
            value = value.isoformat()
        elif isinstance(value, (list, tuple)):
            value = " | ".join(
                item.value if isinstance(item, Enum) else str(item)
                for item in value
            )
        row.append(value)
    return row


def build_sheet_values(records: list[CRMRecord]) -> list[list[object]]:
    """Monta um payload único com headers amigáveis e todas as linhas."""

    headers = [column.header for column in GOOGLE_SHEET_COLUMNS]
    return [headers, *(record_to_sheet_row(record) for record in records)]


def _header_map(values: list[list[object]]) -> dict[str, int]:
    """Valida e mapeia headers sem depender da posição visual das colunas."""

    if not values:
        raise ValueError("Sheet is empty and has no headers")
    headers = [str(value).strip() for value in values[0]]
    duplicates = sorted({header for header in headers if header and headers.count(header) > 1})
    if duplicates:
        raise ValueError("Duplicate headers: " + ", ".join(duplicates))
    required = {"Internal ID", *MANUAL_HEADER_TO_FIELD}
    missing = sorted(required - set(headers))
    if missing:
        raise ValueError("Missing required headers: " + ", ".join(missing))
    return {header: index for index, header in enumerate(headers) if header}


def _cell(row: list[object], index: int) -> object:
    # A values API omite células vazias no fim da linha. Como o header já foi
    # validado, ausência no array da linha representa uma célula presente vazia.
    return row[index] if index < len(row) else ""


def _internal_id(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("Internal ID must be a positive integer")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, float) and value.is_integer():
        parsed = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
    else:
        raise ValueError("Internal ID must be a positive integer")
    if parsed <= 0:
        raise ValueError("Internal ID must be a positive integer")
    return parsed


def _manual_sheet_changes(
    row: list[object], header_map: dict[str, int]
) -> dict[str, object]:
    changes: dict[str, object] = {}
    for header, field in MANUAL_HEADER_TO_FIELD.items():
        value = _cell(row, header_map[header])
        if value == "":
            # Status is required by the domain. All other manual fields are
            # optional and an empty cell intentionally clears their value.
            changes[field] = "" if field == "application_status" else None
        else:
            changes[field] = str(value) if not isinstance(value, str) else value
    return changes


def _manual_values_equal(record: CRMRecord, changes: dict[str, object]) -> bool:
    for field, incoming in changes.items():
        current = getattr(record, field)
        if isinstance(current, Enum):
            current = current.value
        elif isinstance(current, date):
            current = current.isoformat()
        if current != incoming:
            return False
    return True


def merge_manual_sheet_values(
    generated_values: list[list[object]], existing_values: list[list[object]]
) -> list[list[object]]:
    """Preserva edições manuais do Sheet por Internal ID durante o push."""

    if not existing_values or not any(existing_values[0]):
        return generated_values
    existing_headers = _header_map(existing_values)
    generated_headers = _header_map(generated_values)
    existing_by_id: dict[int, list[object]] = {}
    for row_number, row in enumerate(existing_values[1:], start=2):
        if not any(value != "" for value in row):
            continue
        internal_id = _internal_id(_cell(row, existing_headers["Internal ID"]))
        if internal_id in existing_by_id:
            raise ValueError(f"Duplicate Internal ID in Sheet at row {row_number}")
        existing_by_id[internal_id] = row
    for generated_row in generated_values[1:]:
        internal_id = _internal_id(
            _cell(generated_row, generated_headers["Internal ID"])
        )
        existing_row = existing_by_id.get(internal_id)
        if existing_row is None:
            continue
        for header in MANUAL_HEADER_TO_FIELD:
            generated_row[generated_headers[header]] = _cell(
                existing_row, existing_headers[header]
            )
    return generated_values


def authenticate_google(config: GoogleSheetsConfig) -> Any:
    """Executa/reutiliza OAuth desktop sem imprimir tokens ou credentials."""

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:  # pragma: no cover - depende do ambiente do usuário
        raise RuntimeError(
            "Google dependencies are not installed; run pip install -r requirements.txt"
        ) from exc

    credentials = None
    if config.token_path.exists():
        credentials = Credentials.from_authorized_user_file(
            str(config.token_path), SHEETS_SCOPES
        )
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(config.credentials_path), SHEETS_SCOPES
        )
        credentials = flow.run_local_server(port=0)
    config.token_path.parent.mkdir(parents=True, exist_ok=True)
    config.token_path.write_text(credentials.to_json(), encoding="utf-8")
    config.token_path.chmod(0o600)
    return credentials


def authenticate_google_noninteractive(config: GoogleSheetsConfig) -> Any:
    """Carrega/atualiza OAuth existente sem jamais abrir navegador."""

    if not config.credentials_path.is_file():
        raise RuntimeError(f"Google credentials file not found: {config.credentials_path}")
    if not config.token_path.is_file():
        raise RuntimeError(
            f"Google token file not found: {config.token_path}; run a manual Sheets command first"
        )
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Google dependencies are not installed; run pip install -r requirements.txt"
        ) from exc
    credentials = Credentials.from_authorized_user_file(
        str(config.token_path), SHEETS_SCOPES
    )
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        config.token_path.write_text(credentials.to_json(), encoding="utf-8")
        config.token_path.chmod(0o600)
    if not credentials.valid:
        raise RuntimeError("Stored Google token is invalid; renew it manually")
    return credentials


def create_sheets_service(credentials: Any) -> Any:
    """Cria o cliente oficial somente após a autenticação explícita."""

    try:
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover - depende do ambiente do usuário
        raise RuntimeError(
            "Google dependencies are not installed; run pip install -r requirements.txt"
        ) from exc
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def _ensure_sheet_tab_state(
    service: Any, config: GoogleSheetsConfig
) -> tuple[int, int]:
    """Retorna sheet ID e quantidade atual de regras condicionais."""

    metadata = (
        service.spreadsheets()
        .get(
            spreadsheetId=config.spreadsheet_id,
            fields="sheets(properties,conditionalFormats)",
        )
        .execute()
    )
    for sheet in metadata.get("sheets", []):
        properties = sheet.get("properties", {})
        if properties.get("title") == config.sheet_name:
            return int(properties["sheetId"]), len(sheet.get("conditionalFormats", []))
    response = (
        service.spreadsheets()
        .batchUpdate(
            spreadsheetId=config.spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": config.sheet_name}}}]},
        )
        .execute()
    )
    return int(response["replies"][0]["addSheet"]["properties"]["sheetId"]), 0


def ensure_sheet_tab(service: Any, config: GoogleSheetsConfig) -> int:
    """Retorna o ID da tab configurada, criando-a uma única vez se necessário."""

    sheet_id, _ = _ensure_sheet_tab_state(service, config)
    return sheet_id


def _format_requests(
    sheet_id: int, row_count: int, conditional_rule_count: int = 0
) -> list[dict[str, object]]:
    wrap_fields = {
        "notes", "positive_reasons", "potential_gaps", "unknowns",
        "decision_reasons",
    }
    wrap_columns = tuple(
        index for index, column in enumerate(GOOGLE_SHEET_COLUMNS)
        if column.field in wrap_fields
    )
    requests: list[dict[str, object]] = [
        {
            "deleteConditionalFormatRule": {
                "sheetId": sheet_id,
                "index": index,
            }
        }
        for index in reversed(range(conditional_rule_count))
    ]
    requests.extend([
        {
            "updateSheetProperties": {
                "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                "fields": "userEnteredFormat.textFormat.bold",
            }
        },
        {
            "setBasicFilter": {
                "filter": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": max(1, row_count + 1),
                        "startColumnIndex": 0,
                        "endColumnIndex": len(GOOGLE_SHEET_COLUMNS),
                    }
                }
            }
        },
        {
            "autoResizeDimensions": {
                "dimensions": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": len(GOOGLE_SHEET_COLUMNS),
                }
            }
        },
    ])
    requests.extend(
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startColumnIndex": column,
                    "endColumnIndex": column + 1,
                },
                "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP"}},
                "fields": "userEnteredFormat.wrapStrategy",
            }
        }
        for column in wrap_columns
    )
    requests.extend(
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": column,
                    "endIndex": column + 1,
                },
                "properties": {"pixelSize": 280},
                "fields": "pixelSize",
            }
        }
        for column in wrap_columns
    )
    manual_color = {"red": 0.93, "green": 0.96, "blue": 1.0}
    for column in GOOGLE_SHEET_COLUMNS:
        if column.field in MANUAL_FIELDS:
            column_index = GOOGLE_SHEET_COLUMNS.index(column)
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "startColumnIndex": column_index,
                            "endColumnIndex": column_index + 1,
                        },
                        "cell": {
                            "userEnteredFormat": {"backgroundColor": manual_color}
                        },
                        "fields": "userEnteredFormat.backgroundColor",
                    }
                }
            )

    status_values = [{"userEnteredValue": status.value} for status in ApplicationStatus]
    requests.append(
        {
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": max(1000, row_count + 1),
                    "startColumnIndex": 4,
                    "endColumnIndex": 5,
                },
                "rule": {
                    "condition": {"type": "ONE_OF_LIST", "values": status_values},
                    "strict": True,
                    "showCustomUi": True,
                },
            }
        }
    )

    def conditional_rule(
        column_index: int,
        condition: dict[str, object],
        color: dict[str, float],
    ) -> dict[str, object]:
        return {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [
                        {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "startColumnIndex": column_index,
                            "endColumnIndex": column_index + 1,
                        }
                    ],
                    "booleanRule": {
                        "condition": condition,
                        "format": {"backgroundColor": color},
                    },
                },
                "index": 0,
            }
        }

    score_ranges = (
        (90, 100, {"red": 0.72, "green": 0.88, "blue": 0.70}),
        (75, 89, {"red": 0.84, "green": 0.93, "blue": 0.82}),
        (60, 74, {"red": 1.0, "green": 0.95, "blue": 0.65}),
        (40, 59, {"red": 0.98, "green": 0.80, "blue": 0.60}),
        (0, 39, {"red": 0.95, "green": 0.72, "blue": 0.72}),
    )
    for minimum, maximum, color in score_ranges:
        requests.append(
            conditional_rule(
                2,
                {
                    "type": "NUMBER_BETWEEN",
                    "values": [
                        {"userEnteredValue": str(minimum)},
                        {"userEnteredValue": str(maximum)},
                    ],
                },
                color,
            )
        )

    decision_colors = {
        "KEEP": {"red": 0.78, "green": 0.91, "blue": 0.76},
        "REVIEW": {"red": 1.0, "green": 0.94, "blue": 0.65},
        "REJECT": {"red": 0.93, "green": 0.76, "blue": 0.76},
    }
    for value, color in decision_colors.items():
        requests.append(
            conditional_rule(
                3,
                {"type": "TEXT_EQ", "values": [{"userEnteredValue": value}]},
                color,
            )
        )

    status_colors = {
        ApplicationStatus.NOT_APPLIED: {"red": 0.90, "green": 0.90, "blue": 0.90},
        ApplicationStatus.APPLIED: {"red": 0.72, "green": 0.84, "blue": 0.96},
        ApplicationStatus.RECRUITER_SCREEN: {"red": 1.0, "green": 0.92, "blue": 0.65},
        ApplicationStatus.HIRING_MANAGER: {"red": 1.0, "green": 0.87, "blue": 0.58},
        ApplicationStatus.INTERVIEW: {"red": 1.0, "green": 0.82, "blue": 0.50},
        ApplicationStatus.FINAL_INTERVIEW: {"red": 0.95, "green": 0.76, "blue": 0.43},
        ApplicationStatus.OFFER: {"red": 0.70, "green": 0.90, "blue": 0.68},
        ApplicationStatus.REJECTED: {"red": 0.91, "green": 0.72, "blue": 0.72},
        ApplicationStatus.WITHDRAWN: {"red": 0.82, "green": 0.82, "blue": 0.82},
    }
    for status, color in status_colors.items():
        requests.append(
            conditional_rule(
                4,
                {
                    "type": "TEXT_EQ",
                    "values": [{"userEnteredValue": status.value}],
                },
                color,
            )
        )
    lifecycle_colors = {
        "OPEN": {"red": 0.88, "green": 0.95, "blue": 0.86},
        "POSSIBLY_CLOSED": {"red": 1.0, "green": 0.88, "blue": 0.62},
        "CLOSED": {"red": 0.88, "green": 0.80, "blue": 0.80},
        "UNKNOWN": {"red": 0.90, "green": 0.90, "blue": 0.90},
    }
    for value, color in lifecycle_colors.items():
        requests.append(
            conditional_rule(
                17,
                {"type": "TEXT_EQ", "values": [{"userEnteredValue": value}]},
                color,
            )
        )
    return requests


def read_sheet_values(service: Any, config: GoogleSheetsConfig) -> list[list[object]]:
    """Lê a região usada da tab em uma única chamada."""

    escaped_name = config.sheet_name.replace("'", "''")
    response = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=config.spreadsheet_id,
            range=f"'{escaped_name}'!A:ZZ",
            majorDimension="ROWS",
        )
        .execute()
    )
    return response.get("values", [])


def write_sheet(
    service: Any,
    config: GoogleSheetsConfig,
    sheet_id: int,
    records: list[CRMRecord],
    *,
    existing_values: list[list[object]] | None = None,
    conditional_rule_count: int = 0,
) -> None:
    """Reescreve a tab usando chamadas por lote, nunca uma chamada por célula."""

    values = build_sheet_values(records)
    if existing_values:
        values = merge_manual_sheet_values(values, existing_values)
    escaped_name = config.sheet_name.replace("'", "''")
    sheet_range = f"'{escaped_name}'"
    service.spreadsheets().values().clear(
        spreadsheetId=config.spreadsheet_id,
        range=sheet_range,
        body={},
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=config.spreadsheet_id,
        range=f"{sheet_range}!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()
    service.spreadsheets().batchUpdate(
        spreadsheetId=config.spreadsheet_id,
        body={
            "requests": _format_requests(
                sheet_id, len(records), conditional_rule_count
            )
        },
    ).execute()


def push_crm_to_google_sheets(
    repository: JobRepository,
    config: GoogleSheetsConfig,
    *,
    service: Any | None = None,
    now: datetime | None = None,
) -> SheetSyncResult:
    """Envia todo o CRM ordenado para Sheets; nunca lê mudanças de volta."""

    synced_at = now or datetime.now(timezone.utc)
    try:
        sheets_service = service or create_sheets_service(authenticate_google(config))
        records = LocalCRM(repository).list_records()
        sheet_id, conditional_rule_count = _ensure_sheet_tab_state(
            sheets_service, config
        )
        existing_values = read_sheet_values(sheets_service, config)
        write_sheet(
            sheets_service,
            config,
            sheet_id,
            records,
            existing_values=existing_values,
            conditional_rule_count=conditional_rule_count,
        )
        return SheetSyncResult(
            spreadsheet_id=config.spreadsheet_id,
            sheet_name=config.sheet_name,
            rows_written=len(records),
            columns_written=len(GOOGLE_SHEET_COLUMNS),
            success=True,
            error=None,
            synced_at=synced_at,
        )
    except Exception as exc:  # API errors are returned without aborting the CLI.
        return SheetSyncResult(
            spreadsheet_id=config.spreadsheet_id,
            sheet_name=config.sheet_name,
            rows_written=0,
            columns_written=len(GOOGLE_SHEET_COLUMNS),
            success=False,
            error=str(exc),
            synced_at=synced_at,
        )


def pull_manual_fields_from_google_sheets(
    repository: JobRepository,
    config: GoogleSheetsConfig,
    *,
    service: Any | None = None,
    now: datetime | None = None,
) -> SheetPullResult:
    """Importa somente MANUAL_FIELDS, reconciliados pelo Internal ID."""

    synced_at = now or datetime.now(timezone.utc)
    try:
        sheets_service = service or create_sheets_service(authenticate_google(config))
        values = read_sheet_values(sheets_service, config)
        rows_read = max(0, len(values) - 1)
        try:
            header_map = _header_map(values)
        except ValueError as exc:
            issue = SheetPullIssue(None, "invalid_structure", str(exc))
            return SheetPullResult(
                config.spreadsheet_id,
                config.sheet_name,
                rows_read,
                0,
                0,
                0,
                0,
                0,
                False,
                str(exc),
                [issue],
                synced_at,
            )

        crm = LocalCRM(repository)
        unchanged = updated = skipped = errored = 0
        issues: list[SheetPullIssue] = []
        seen_ids: set[int] = set()
        for row_number, row in enumerate(values[1:], start=2):
            if not any(value != "" for value in row):
                skipped += 1
                continue
            try:
                internal_id = _internal_id(_cell(row, header_map["Internal ID"]))
                if internal_id in seen_ids:
                    raise ValueError("Internal ID appears more than once in the Sheet")
                seen_ids.add(internal_id)
                current = crm.get(internal_id)
                if current is None:
                    raise CRMRecordNotFound(f"CRM record {internal_id} was not found")
                changes = _manual_sheet_changes(row, header_map)
                if _manual_values_equal(current, changes):
                    unchanged += 1
                    continue
                crm.update_manual_fields(internal_id, **changes)
                updated += 1
            except (CRMValidationError, CRMRecordNotFound, ValueError) as exc:
                errored += 1
                issues.append(
                    SheetPullIssue(row_number, "invalid_row", str(exc))
                )
        valid = unchanged + updated
        return SheetPullResult(
            spreadsheet_id=config.spreadsheet_id,
            sheet_name=config.sheet_name,
            rows_read=rows_read,
            rows_valid=valid,
            rows_unchanged=unchanged,
            rows_updated=updated,
            rows_skipped=skipped,
            rows_errored=errored,
            success=errored == 0,
            error=None,
            issues=issues,
            synced_at=synced_at,
        )
    except Exception as exc:
        return SheetPullResult(
            config.spreadsheet_id,
            config.sheet_name,
            0,
            0,
            0,
            0,
            0,
            0,
            False,
            str(exc),
            [SheetPullIssue(None, "api_error", str(exc))],
            synced_at,
        )
