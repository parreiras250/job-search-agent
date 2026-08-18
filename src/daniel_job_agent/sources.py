"""Fontes externas responsáveis somente por obter registros brutos de vagas."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
import json
import re
import socket
from email.utils import parsedate_to_datetime
from typing import Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from .ingestion import RawJobRecord

GREENHOUSE_API_BASE_URL = "https://boards-api.greenhouse.io/v1/boards"
LEVER_API_BASE_URLS = {
    "global": "https://api.lever.co/v0/postings",
    "eu": "https://api.eu.lever.co/v0/postings",
}
DEFAULT_HTTP_TIMEOUT_SECONDS = 10.0
DEFAULT_USER_AGENT = "DanielJobAgent/1.0 (public-job-board-reader)"
JOBICY_API_BASE_URL = "https://jobicy.com/api/v2/remote-jobs"
REMOTIVE_API_BASE_URL = "https://remotive.com/api/remote-jobs"
HIMALAYAS_SEARCH_API_URL = "https://himalayas.app/jobs/api/search"
REMOTEOK_API_URL = "https://remoteok.com/api"
GETONBOARD_API_BASE_URL = "https://www.getonbrd.com/api/v0"
WWR_SALES_MARKETING_RSS_URL = (
    "https://weworkremotely.com/categories/remote-sales-and-marketing-jobs.rss"
)
MAX_RSS_BYTES = 5_000_000


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


def build_jobicy_jobs_url(
    *,
    count: int = 100,
    geo: str | None = None,
    industry: str | None = None,
    tag: str | None = None,
) -> str:
    """Monta uma consulta explícita à API pública do Jobicy."""

    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 100:
        raise ValueError("count must be an integer between 1 and 100")
    parameters: list[tuple[str, str]] = [("count", str(count))]
    for name, value in (("geo", geo), ("industry", industry), ("tag", tag)):
        if value is not None:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text when provided")
            parameters.append((name, value.strip()))
    return f"{JOBICY_API_BASE_URL}?{urlencode(parameters)}"


def build_remotive_jobs_url(
    *,
    category: str | None = None,
    company_name: str | None = None,
    search: str | None = None,
    limit: int | None = None,
) -> str:
    """Monta uma consulta única à API pública da Remotive."""

    parameters: list[tuple[str, str]] = []
    for name, value in (
        ("category", category),
        ("company_name", company_name),
        ("search", search),
    ):
        if value is not None:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text when provided")
            parameters.append((name, value.strip()))
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer when provided")
        parameters.append(("limit", str(limit)))
    query = urlencode(parameters)
    return f"{REMOTIVE_API_BASE_URL}?{query}" if query else REMOTIVE_API_BASE_URL


def build_himalayas_jobs_url(
    *, q: str = "sales", sort: str = "recent", page: int = 1
) -> str:
    """Monta uma única busca oficial, filtrada e deterministicamente paginada."""

    if not isinstance(q, str) or not q.strip():
        raise ValueError("q must be non-empty text")
    allowed_sorts = {
        "relevant", "recent", "salaryAsc", "salaryDesc",
        "nameAToZ", "nameZToA", "jobs",
    }
    if sort not in allowed_sorts:
        raise ValueError("sort is not supported by the Himalayas API")
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("page must be a positive integer")
    return f"{HIMALAYAS_SEARCH_API_URL}?{urlencode({'q': q.strip(), 'sort': sort, 'page': page})}"


def build_getonboard_jobs_url(
    *, query: str = "sales", page: int = 1, per_page: int = 20
) -> str:
    """Monta uma única página da busca pública oficial do Get on Board."""

    if not isinstance(query, str) or len(query.strip()) < 3:
        raise ValueError("query must contain at least three characters")
    if isinstance(page, bool) or not isinstance(page, int) or page != 1:
        raise ValueError("only the first Get on Board page is supported")
    if (
        isinstance(per_page, bool)
        or not isinstance(per_page, int)
        or not 1 <= per_page <= 20
    ):
        raise ValueError("per_page must be an integer between 1 and 20")
    parameters = [
        ("query", query.strip()),
        ("page", str(page)),
        ("per_page", str(per_page)),
        ("expand[]", "company"),
        ("expand[]", "tags"),
    ]
    return f"{GETONBOARD_API_BASE_URL}/search/jobs?{urlencode(parameters)}"


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


class JobicyJobSource(JobSource):
    """Faz uma única consulta controlada à API pública do Jobicy."""

    def __init__(
        self,
        *,
        count: int = 100,
        geo: str | None = None,
        industry: str | None = None,
        tag: str | None = None,
        timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
        transport: HttpTransport | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        self.url = build_jobicy_jobs_url(
            count=count, geo=geo, industry=industry, tag=tag
        )
        self.count = count
        self.geo = geo.strip() if isinstance(geo, str) else None
        self.industry = industry.strip() if isinstance(industry, str) else None
        self.tag = tag.strip() if isinstance(tag, str) else None
        self.timeout = timeout
        self.transport = transport or UrllibHttpTransport()

    def fetch(self) -> SourceResult:
        payload, error = _fetch_json(
            source_name="Jobicy",
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
                message="Jobicy payload must contain a jobs list",
            )
        records = [job for job in payload["jobs"] if isinstance(job, dict)]
        if not records:
            return SourceResult(status=SourceStatus.NO_JOBS, records=[])
        return SourceResult(status=SourceStatus.SUCCESS, records=records)


class RemotiveJobSource(JobSource):
    """Faz uma única consulta controlada à API pública da Remotive."""

    def __init__(
        self,
        *,
        category: str | None = None,
        company_name: str | None = None,
        search: str | None = None,
        limit: int | None = None,
        timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
        transport: HttpTransport | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        self.url = build_remotive_jobs_url(
            category=category,
            company_name=company_name,
            search=search,
            limit=limit,
        )
        self.category = category.strip() if isinstance(category, str) else None
        self.company_name = (
            company_name.strip() if isinstance(company_name, str) else None
        )
        self.search = search.strip() if isinstance(search, str) else None
        self.limit = limit
        self.timeout = timeout
        self.transport = transport or UrllibHttpTransport()

    def fetch(self) -> SourceResult:
        payload, error = _fetch_json(
            source_name="Remotive",
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
                message="Remotive payload must contain a jobs list",
            )
        records = [job for job in payload["jobs"] if isinstance(job, dict)]
        if not records:
            return SourceResult(status=SourceStatus.NO_JOBS, records=[])
        return SourceResult(status=SourceStatus.SUCCESS, records=records)


class HimalayasJobSource(JobSource):
    """Executa uma página da busca pública oficial da Himalayas."""

    def __init__(
        self,
        *,
        q: str = "sales",
        sort: str = "recent",
        page: int = 1,
        timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
        transport: HttpTransport | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        self.q = q.strip()
        self.sort = sort
        self.page = page
        self.url = build_himalayas_jobs_url(q=q, sort=sort, page=page)
        self.timeout = timeout
        self.transport = transport or UrllibHttpTransport()

    def fetch(self) -> SourceResult:
        payload, error = _fetch_json(
            source_name="Himalayas",
            url=self.url,
            timeout=self.timeout,
            transport=self.transport,
        )
        if error is not None:
            return error
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            return SourceResult(
                SourceStatus.INVALID_PAYLOAD, [],
                "Himalayas payload must contain a jobs list",
            )
        metadata = {
            "updatedAt": payload.get("updatedAt"),
            "offset": payload.get("offset"),
            "limit": payload.get("limit"),
            "totalCount": payload.get("totalCount"),
        }
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in metadata.values()
        ) or not (
            metadata["updatedAt"] >= 0
            and metadata["offset"] >= 0
            and 1 <= metadata["limit"] <= 20
            and metadata["totalCount"] >= 0
        ):
            return SourceResult(
                SourceStatus.INVALID_PAYLOAD, [],
                "Himalayas pagination metadata is invalid",
            )
        records = [job for job in payload["jobs"] if isinstance(job, dict)]
        if not records:
            return SourceResult(SourceStatus.NO_JOBS, [])
        return SourceResult(SourceStatus.SUCCESS, records)


class RemoteOKJobSource(JobSource):
    """Lê uma vez o JSON feed público oficial do RemoteOK."""

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
        transport: HttpTransport | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        self.url = REMOTEOK_API_URL
        self.timeout = timeout
        self.transport = transport or UrllibHttpTransport()

    @staticmethod
    def _is_metadata(record: Mapping[str, object]) -> bool:
        """Reconhece a linha legal do feed sem confundi-la com uma vaga."""

        return (
            "last_updated" in record
            and "legal" in record
            and not any(key in record for key in ("id", "company", "position"))
        )

    def fetch(self) -> SourceResult:
        payload, error = _fetch_json(
            source_name="RemoteOK",
            url=self.url,
            timeout=self.timeout,
            transport=self.transport,
        )
        if error is not None:
            return error
        if not isinstance(payload, list):
            return SourceResult(
                SourceStatus.INVALID_PAYLOAD,
                [],
                "RemoteOK payload must be a list",
            )
        if any(not isinstance(item, dict) for item in payload):
            return SourceResult(
                SourceStatus.INVALID_PAYLOAD,
                [],
                "RemoteOK payload entries must be objects",
            )
        records = [item for item in payload if not self._is_metadata(item)]
        if not records:
            return SourceResult(SourceStatus.NO_JOBS, [])
        return SourceResult(SourceStatus.SUCCESS, records)


class GetOnBoardJobSource(JobSource):
    """Executa somente a primeira página da busca pública do Get on Board."""

    def __init__(
        self,
        *,
        query: str = "sales",
        page: int = 1,
        per_page: int = 20,
        timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
        transport: HttpTransport | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        self.query = query.strip()
        self.page = page
        self.per_page = per_page
        self.url = build_getonboard_jobs_url(
            query=query, page=page, per_page=per_page
        )
        self.timeout = timeout
        self.transport = transport or UrllibHttpTransport()

    def fetch(self) -> SourceResult:
        payload, error = _fetch_json(
            source_name="Get on Board",
            url=self.url,
            timeout=self.timeout,
            transport=self.transport,
        )
        if error is not None:
            return error
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            return SourceResult(
                SourceStatus.INVALID_PAYLOAD,
                [],
                "Get on Board payload must contain a data list",
            )
        if any(not isinstance(item, dict) for item in payload["data"]):
            return SourceResult(
                SourceStatus.INVALID_PAYLOAD,
                [],
                "Get on Board data entries must be objects",
            )
        meta = payload.get("meta")
        if meta is not None:
            if not isinstance(meta, dict):
                return SourceResult(
                    SourceStatus.INVALID_PAYLOAD, [],
                    "Get on Board pagination metadata must be an object",
                )
            pagination = meta.get("pagination", meta)
            if not isinstance(pagination, dict):
                return SourceResult(
                    SourceStatus.INVALID_PAYLOAD, [],
                    "Get on Board pagination metadata is invalid",
                )
            for key in ("page", "current_page", "per_page", "total_pages"):
                value = pagination.get(key)
                if value is not None and (
                    isinstance(value, bool) or not isinstance(value, int) or value < 0
                ):
                    return SourceResult(
                        SourceStatus.INVALID_PAYLOAD, [],
                        "Get on Board pagination metadata is invalid",
                    )
        records = list(payload["data"])
        if not records:
            return SourceResult(SourceStatus.NO_JOBS, [])
        return SourceResult(SourceStatus.SUCCESS, records)


class WeWorkRemotelyJobSource(JobSource):
    """Lê uma vez o RSS público oficial de Sales and Marketing do WWR."""

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
        transport: HttpTransport | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        self.url = WWR_SALES_MARKETING_RSS_URL
        self.timeout = timeout
        self.transport = transport or UrllibHttpTransport()

    def fetch(self) -> SourceResult:
        try:
            response = self.transport.get(
                self.url,
                timeout=self.timeout,
                headers={
                    "User-Agent": DEFAULT_USER_AGENT,
                    "Accept": "application/rss+xml, application/xml, text/xml",
                },
            )
        except HTTPError as error:
            return SourceResult(
                SourceStatus.HTTP_ERROR, [],
                f"We Work Remotely returned HTTP {error.code}", error.code,
            )
        except (TimeoutError, socket.timeout):
            return SourceResult(
                SourceStatus.TIMEOUT, [], "We Work Remotely request timed out"
            )
        except URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                return SourceResult(
                    SourceStatus.TIMEOUT, [], "We Work Remotely request timed out"
                )
            return SourceResult(
                SourceStatus.CONNECTION_ERROR, [],
                f"Could not connect to We Work Remotely: {error.reason}",
            )
        except OSError as error:
            return SourceResult(
                SourceStatus.CONNECTION_ERROR, [],
                f"Could not connect to We Work Remotely: {error}",
            )

        if not 200 <= response.status < 300:
            return SourceResult(
                SourceStatus.HTTP_ERROR, [],
                f"We Work Remotely returned HTTP {response.status}", response.status,
            )
        body = response.body
        if len(body) > MAX_RSS_BYTES or b"<!DOCTYPE" in body.upper():
            return SourceResult(
                SourceStatus.INVALID_PAYLOAD, [],
                "We Work Remotely returned an unsafe or oversized RSS payload",
            )
        try:
            root = ElementTree.fromstring(body)
        except (ElementTree.ParseError, ValueError):
            return SourceResult(
                SourceStatus.INVALID_PAYLOAD, [],
                "We Work Remotely returned invalid RSS XML",
            )
        channel = root.find("channel") if root.tag == "rss" else None
        if channel is None:
            return SourceResult(
                SourceStatus.INVALID_PAYLOAD, [],
                "We Work Remotely RSS must contain an rss/channel structure",
            )

        records = [self._item_record(item) for item in channel.findall("item")]
        if not records:
            return SourceResult(SourceStatus.NO_JOBS, [])
        return SourceResult(SourceStatus.SUCCESS, records)

    @staticmethod
    def _item_record(item: ElementTree.Element) -> RawJobRecord:
        def text(name: str) -> str | None:
            value = item.findtext(name)
            return value.strip() if value and value.strip() else None

        combined_title = text("title") or ""
        company, separator, role = combined_title.partition(":")
        raw_date = text("pubDate")
        date_posted: str | None = None
        if raw_date is not None:
            try:
                date_posted = parsedate_to_datetime(raw_date).isoformat()
            except (TypeError, ValueError, OverflowError):
                # O adapter transformará este opcional presente em warning.
                date_posted = raw_date
        return {
            "company": company.strip() if separator else "",
            "role": role.strip() if separator else combined_title,
            "job_url": text("link"),
            "location": text("region"),
            "description": text("description"),
            "date_posted": date_posted,
            "external_id": text("guid"),
            "employment_type": text("category"),
            "remote": True,
            "brazil_eligible": None,
        }
