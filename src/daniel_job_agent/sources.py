"""Fontes externas responsáveis somente por obter registros brutos de vagas."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
import json
import re
import socket
from typing import Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .ingestion import RawJobRecord

GREENHOUSE_API_BASE_URL = "https://boards-api.greenhouse.io/v1/boards"
LEVER_API_BASE_URLS = {
    "global": "https://api.lever.co/v0/postings",
    "eu": "https://api.eu.lever.co/v0/postings",
}
DEFAULT_HTTP_TIMEOUT_SECONDS = 10.0
DEFAULT_USER_AGENT = "DanielJobAgent/1.0 (public-job-board-reader)"


class SourceStatus(str, Enum):
    SUCCESS = "SUCCESS"
    NO_JOBS = "NO_JOBS"
    HTTP_ERROR = "HTTP_ERROR"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    TIMEOUT = "TIMEOUT"
    INVALID_PAYLOAD = "INVALID_PAYLOAD"


@dataclass(frozen=True, slots=True)
class SourceResult:
    """Resultado controlado de uma consulta a uma fonte externa."""

    status: SourceStatus
    records: list[RawJobRecord]
    message: str | None = None
    http_status: int | None = None

    @property
    def success(self) -> bool:
        return self.status in (SourceStatus.SUCCESS, SourceStatus.NO_JOBS)


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Resposta HTTP mínima usada para desacoplar testes da rede."""

    status: int
    body: bytes


class HttpTransport(Protocol):
    def get(
        self, url: str, timeout: float, headers: Mapping[str, str]
    ) -> HttpResponse:
        """Executa um único HTTP GET."""


class UrllibHttpTransport:
    """Transporte padrão baseado somente na biblioteca padrão do Python."""

    def get(
        self, url: str, timeout: float, headers: Mapping[str, str]
    ) -> HttpResponse:
        request = Request(url, headers=dict(headers), method="GET")
        with urlopen(request, timeout=timeout) as response:
            return HttpResponse(status=response.status, body=response.read())


class JobSource(ABC):
    """Contrato simples: uma fonte externa devolve registros brutos."""

    @abstractmethod
    def fetch(self) -> SourceResult:
        """Obtém registros sem executar ingestão, scoring ou ranking."""


def build_greenhouse_jobs_url(board_token: str) -> str:
    """Valida o token público e monta a única URL utilizada pela integração."""

    normalized = board_token.strip()
    if not normalized or re.fullmatch(r"[A-Za-z0-9_-]+", normalized) is None:
        raise ValueError(
            "board_token must contain only letters, numbers, hyphens, or underscores"
        )
    return f"{GREENHOUSE_API_BASE_URL}/{normalized}/jobs?content=true"


def build_lever_postings_url(company_slug: str, region: str = "global") -> str:
    """Valida site e região antes de montar o endpoint público do Lever."""

    normalized_slug = company_slug.strip()
    normalized_region = region.strip().casefold()
    if not normalized_slug or re.fullmatch(r"[A-Za-z0-9_-]+", normalized_slug) is None:
        raise ValueError(
            "company_slug must contain only letters, numbers, hyphens, or underscores"
        )
    if normalized_region not in LEVER_API_BASE_URLS:
        raise ValueError("region must be 'global' or 'eu'")
    return f"{LEVER_API_BASE_URLS[normalized_region]}/{normalized_slug}?mode=json"


def _fetch_json(
    *,
    source_name: str,
    url: str,
    timeout: float,
    transport: HttpTransport,
) -> tuple[object | None, SourceResult | None]:
    """Compartilha um único GET e tratamento de transporte entre as sources."""

    try:
        response = transport.get(
            url,
            timeout=timeout,
            headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"},
        )
    except HTTPError as error:
        return None, SourceResult(
            status=SourceStatus.HTTP_ERROR,
            records=[],
            message=f"{source_name} returned HTTP {error.code}",
            http_status=error.code,
        )
    except (TimeoutError, socket.timeout):
        return None, SourceResult(
            status=SourceStatus.TIMEOUT,
            records=[],
            message=f"{source_name} request timed out",
        )
    except URLError as error:
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            return None, SourceResult(
                status=SourceStatus.TIMEOUT,
                records=[],
                message=f"{source_name} request timed out",
            )
        return None, SourceResult(
            status=SourceStatus.CONNECTION_ERROR,
            records=[],
            message=f"Could not connect to {source_name}: {error.reason}",
        )
    except OSError as error:
        return None, SourceResult(
            status=SourceStatus.CONNECTION_ERROR,
            records=[],
            message=f"Could not connect to {source_name}: {error}",
        )

    if not 200 <= response.status < 300:
        return None, SourceResult(
            status=SourceStatus.HTTP_ERROR,
            records=[],
            message=f"{source_name} returned HTTP {response.status}",
            http_status=response.status,
        )
    try:
        return json.loads(response.body.decode("utf-8")), None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, SourceResult(
            status=SourceStatus.INVALID_PAYLOAD,
            records=[],
            message=f"{source_name} returned invalid JSON",
        )


class GreenhouseJobSource(JobSource):
    """Lê uma única listagem pública do Greenhouse Job Board API."""

    def __init__(
        self,
        board_token: str,
        company_name: str,
        *,
        timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
        transport: HttpTransport | None = None,
    ) -> None:
        if not company_name.strip():
            raise ValueError("company_name cannot be empty")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        self.board_token = board_token.strip()
        self.company_name = company_name.strip()
        self.timeout = timeout
        self.transport = transport or UrllibHttpTransport()
        self.url = build_greenhouse_jobs_url(self.board_token)

    def fetch(self) -> SourceResult:
        payload, error = _fetch_json(
            source_name="Greenhouse",
            url=self.url,
            timeout=self.timeout,
            transport=self.transport,
        )
        if error is not None:
            return error

        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            return SourceResult(
                status=SourceStatus.INVALID_PAYLOAD,
                records=[],
                message="Greenhouse payload must contain a jobs list",
            )

        records = [job for job in payload["jobs"] if isinstance(job, dict)]
        # Non-object entries cannot represent jobs. Keeping valid objects lets the
        # adapter report individual field errors without losing the whole board.
        if not records:
            return SourceResult(status=SourceStatus.NO_JOBS, records=[])
        return SourceResult(status=SourceStatus.SUCCESS, records=records)


class LeverJobSource(JobSource):
    """Lê postings públicos de um único site Lever global ou EU."""

    def __init__(
        self,
        company_slug: str,
        company_name: str,
        *,
        region: str = "global",
        timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
        transport: HttpTransport | None = None,
    ) -> None:
        if not company_name.strip():
            raise ValueError("company_name cannot be empty")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        self.company_slug = company_slug.strip()
        self.company_name = company_name.strip()
        self.region = region.strip().casefold()
        self.timeout = timeout
        self.transport = transport or UrllibHttpTransport()
        self.url = build_lever_postings_url(self.company_slug, self.region)

    def fetch(self) -> SourceResult:
        payload, error = _fetch_json(
            source_name="Lever",
            url=self.url,
            timeout=self.timeout,
            transport=self.transport,
        )
        if error is not None:
            return error
        if not isinstance(payload, list):
            return SourceResult(
                status=SourceStatus.INVALID_PAYLOAD,
                records=[],
                message="Lever payload must be a list of postings",
            )
        records = [posting for posting in payload if isinstance(posting, dict)]
        if not records:
            return SourceResult(status=SourceStatus.NO_JOBS, records=[])
        return SourceResult(status=SourceStatus.SUCCESS, records=records)
