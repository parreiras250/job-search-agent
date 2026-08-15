"""Exportação push-only do CRM SQLite para uma tab do Google Sheets."""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .crm import CRMRecord, LocalCRM
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
    SheetColumn("match_score", "Match Score"),
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
    SheetColumn("positive_reasons", "Positive Reasons"),
    SheetColumn("potential_gaps", "Potential Gaps"),
    SheetColumn("unknowns", "Unknowns"),
    SheetColumn("role_family", "Role Family"),
    SheetColumn("seniority", "Seniority"),
    SheetColumn("salary_min", "Salary Min"),
    SheetColumn("salary_max", "Salary Max"),
    SheetColumn("salary_currency", "Salary Currency"),
    SheetColumn("salary_period", "Salary Period"),
    SheetColumn("salary_text", "Salary Text"),
    SheetColumn("first_seen_at", "First Seen"),
    SheetColumn("last_seen_at", "Last Seen"),
    SheetColumn("last_checked", "Last Checked"),
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
        elif isinstance(value, list):
            value = " | ".join(value)
        row.append(value)
    return row


def build_sheet_values(records: list[CRMRecord]) -> list[list[object]]:
    """Monta um payload único com headers amigáveis e todas as linhas."""

    headers = [column.header for column in GOOGLE_SHEET_COLUMNS]
    return [headers, *(record_to_sheet_row(record) for record in records)]


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


def create_sheets_service(credentials: Any) -> Any:
    """Cria o cliente oficial somente após a autenticação explícita."""

    try:
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover - depende do ambiente do usuário
        raise RuntimeError(
            "Google dependencies are not installed; run pip install -r requirements.txt"
        ) from exc
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def ensure_sheet_tab(service: Any, config: GoogleSheetsConfig) -> int:
    """Retorna o ID da tab configurada, criando-a uma única vez se necessário."""

    metadata = (
        service.spreadsheets()
        .get(spreadsheetId=config.spreadsheet_id, fields="sheets.properties")
        .execute()
    )
    for sheet in metadata.get("sheets", []):
        properties = sheet.get("properties", {})
        if properties.get("title") == config.sheet_name:
            return int(properties["sheetId"])
    response = (
        service.spreadsheets()
        .batchUpdate(
            spreadsheetId=config.spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": config.sheet_name}}}]},
        )
        .execute()
    )
    return int(response["replies"][0]["addSheet"]["properties"]["sheetId"])


def _format_requests(sheet_id: int, row_count: int) -> list[dict[str, object]]:
    wrap_columns = (7, 17, 18, 19)  # Notes, reasons, gaps and unknowns (zero-based).
    requests: list[dict[str, object]] = [
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
    ]
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
    return requests


def write_sheet(service: Any, config: GoogleSheetsConfig, sheet_id: int, records: list[CRMRecord]) -> None:
    """Reescreve a tab usando chamadas por lote, nunca uma chamada por célula."""

    values = build_sheet_values(records)
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
        body={"requests": _format_requests(sheet_id, len(records))},
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
        sheet_id = ensure_sheet_tab(sheets_service, config)
        write_sheet(sheets_service, config, sheet_id, records)
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
