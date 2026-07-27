"""Cross-platform free-data source adapters.

The core does not require a broker terminal.  AKShare is the primary public
market-data entry point; BaoStock is an optional A-share fallback.  Both are
treated as collection sources, not as authoritative facts.  Official exchange
and company announcements remain the preferred verification layer.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from contextlib import redirect_stderr, redirect_stdout
import importlib
from io import StringIO
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class DataSourceHealth:
    name: str
    source_type: str
    available: bool
    capabilities: tuple[str, ...] = ()
    reason: str = ""
    version: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DataSourceAttempt:
    source: str
    status: str
    reason: str = ""
    started_at: str = ""
    finished_at: str = ""
    diagnostics: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RoutedDataResult:
    source: str
    data: dict[str, Any]
    attempts: tuple[DataSourceAttempt, ...]
    requested_sources: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "data": self.data,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "requested_sources": list(self.requested_sources),
        }


class DataSourceExhaustedError(RuntimeError):
    def __init__(
        self,
        attempts: Sequence[DataSourceAttempt],
        requested_sources: Sequence[str] = (),
    ) -> None:
        self.attempts = tuple(attempts)
        self.requested_sources = tuple(requested_sources)
        detail = "; ".join(
            f"{attempt.source}: {attempt.status} {attempt.reason}".strip()
            for attempt in self.attempts
        )
        super().__init__(f"all configured data sources failed: {detail}")


@dataclass(frozen=True)
class FreeDataSourcePolicy:
    """Default source order; each tuple is tried from left to right."""

    listed_company_sources: tuple[str, ...] = (
        "official_exchange",
        "company_disclosure",
        "eastmoney",
        "akshare",
        "baostock",
    )
    industry_sources: tuple[str, ...] = (
        "official_exchange",
        "eastmoney",
        "akshare",
    )
    futures_sources: tuple[str, ...] = (
        "official_exchange",
        "eastmoney",
        "akshare",
    )
    announcement_sources: tuple[str, ...] = (
        "official_exchange",
        "company_disclosure",
        "eastmoney",
        "akshare",
    )

    def sources_for(self, subject_type: str) -> tuple[str, ...]:
        if subject_type in {"listed_company", "company"}:
            return self.listed_company_sources
        if subject_type in {"industry", "industry_radar"}:
            return self.industry_sources
        if subject_type in {"futures_variety", "futures_contract", "continuous_series"}:
            return self.futures_sources
        if subject_type in {"announcement", "financial_statement"}:
            return self.announcement_sources
        return self.listed_company_sources

    def validate(self) -> None:
        all_sources = (
            *self.listed_company_sources,
            *self.industry_sources,
            *self.futures_sources,
            *self.announcement_sources,
        )
        if "qmt" in {source.lower() for source in all_sources}:
            raise ValueError("the default free-data policy cannot depend on QMT")
        if not self.listed_company_sources:
            raise ValueError("listed company sources must not be empty")


class DataSourceRouter:
    """Try configured sources in order and preserve every failed attempt."""

    def __init__(
        self,
        adapters: Sequence[Any],
        policy: FreeDataSourcePolicy | None = None,
    ) -> None:
        self.policy = policy or FreeDataSourcePolicy()
        self.policy.validate()
        self._adapters = {adapter.name: adapter for adapter in adapters}

    def health(self, source_names: Sequence[str] | None = None) -> list[DataSourceHealth]:
        names = tuple(source_names or self._adapters)
        results: list[DataSourceHealth] = []
        for name in names:
            adapter = self._adapters.get(name)
            if adapter is None:
                results.append(
                    DataSourceHealth(
                        name=name,
                        source_type="unregistered",
                        available=False,
                        reason="adapter is not registered",
                    )
                )
            else:
                try:
                    results.append(adapter.health_check())
                except Exception as error:
                    results.append(
                        DataSourceHealth(
                            name=name,
                            source_type=str(getattr(adapter, "source_type", "unknown")),
                            available=False,
                            reason=f"health check failed: {type(error).__name__}: {error}",
                            version="unknown",
                        )
                    )
        return results

    def fetch(
        self,
        query: Mapping[str, Any],
        as_of: str,
        subject_type: str | None = None,
        source_names: Sequence[str] | None = None,
    ) -> RoutedDataResult:
        names = tuple(source_names or self.policy.sources_for(subject_type or "company"))
        attempts: list[DataSourceAttempt] = []
        source_queries = query.get("source_queries", {})
        for name in names:
            started_at = _now()
            health_diagnostics = ""
            fetch_diagnostics = ""
            normalize_diagnostics = ""
            adapter = self._adapters.get(name)
            if adapter is None:
                attempts.append(
                    DataSourceAttempt(
                        source=name,
                        status="SKIPPED",
                        reason="adapter is not registered",
                        started_at=started_at,
                        finished_at=_now(),
                    )
                )
                continue
            if source_queries and isinstance(source_queries, Mapping) and name not in source_queries:
                attempts.append(
                    DataSourceAttempt(
                        source=name,
                        status="SKIPPED",
                        reason="no query configured for this source",
                        started_at=started_at,
                        finished_at=_now(),
                    )
                )
                continue
            try:
                health, health_diagnostics = _capture_output(adapter.health_check)
                if not health.available:
                    attempts.append(
                        DataSourceAttempt(
                            source=name,
                            status="SKIPPED",
                            reason=health.reason or "source unavailable",
                            started_at=started_at,
                            finished_at=_now(),
                            diagnostics=health_diagnostics,
                        )
                    )
                    continue
                source_query = dict(query)
                if isinstance(source_queries, Mapping) and name in source_queries:
                    override = source_queries[name]
                    if not isinstance(override, Mapping):
                        raise ValueError(f"source query for {name} must be an object")
                    source_query.update(override)
                raw, fetch_diagnostics = _capture_output(
                    adapter.fetch, source_query, as_of
                )
                normalized, normalize_diagnostics = _capture_output(
                    adapter.normalize, raw
                )
                diagnostics = _merge_diagnostics(
                    health_diagnostics,
                    fetch_diagnostics,
                    normalize_diagnostics,
                )
                if not _has_payload(normalized):
                    raise ValueError("source returned an empty payload")
                required_fields = tuple(query.get("required_fields", ()))
                if not _has_required_fields(normalized, required_fields):
                    raise ValueError(
                        "source payload is missing required fields: "
                        + ", ".join(required_fields)
                    )
                attempts.append(
                    DataSourceAttempt(
                        source=name,
                        status="SUCCESS",
                        started_at=started_at,
                        finished_at=_now(),
                        diagnostics=diagnostics,
                    )
                )
                return RoutedDataResult(name, normalized, tuple(attempts), names)
            except Exception as error:
                diagnostics = _merge_diagnostics(
                    locals().get("health_diagnostics", ""),
                    locals().get("fetch_diagnostics", ""),
                    locals().get("normalize_diagnostics", ""),
                    getattr(error, "captured_diagnostics", ""),
                )
                attempts.append(
                    DataSourceAttempt(
                        source=name,
                        status="FAILED",
                        reason=f"{type(error).__name__}: {error}",
                        started_at=started_at,
                        finished_at=_now(),
                        diagnostics=diagnostics,
                    )
                )
        raise DataSourceExhaustedError(attempts, names)


class AkshareDataSourceAdapter:
    """Lazy AKShare adapter so the base package remains dependency-free."""

    name = "akshare"
    source_type = "free_public_market_data"

    def __init__(self, module: Any | None = None) -> None:
        self._module = module

    def _load(self) -> Any:
        if self._module is None:
            self._module = importlib.import_module("akshare")
        return self._module

    def health_check(self) -> DataSourceHealth:
        try:
            module = self._load()
        except (ImportError, ModuleNotFoundError) as error:
            return DataSourceHealth(
                name=self.name,
                source_type=self.source_type,
                available=False,
                capabilities=("cn_stock", "hk_stock", "industry", "futures"),
                reason=f"optional dependency unavailable: {error}",
            )
        return DataSourceHealth(
            name=self.name,
            source_type=self.source_type,
            available=True,
            capabilities=("cn_stock", "hk_stock", "industry", "futures"),
            version=str(getattr(module, "__version__", "unknown")),
        )

    def fetch(self, query: Mapping[str, Any], as_of: str) -> dict[str, Any]:
        """Call an explicitly named AKShare endpoint and preserve query lineage."""

        endpoint = str(query.get("endpoint", ""))
        if not endpoint or endpoint.startswith("_"):
            raise ValueError("an explicit public AKShare endpoint is required")
        module = self._load()
        function = getattr(module, endpoint, None)
        if not callable(function):
            raise ValueError(f"AKShare endpoint is unavailable: {endpoint}")
        raw = function(**dict(query.get("params", {})))
        return {
            "source": self.name,
            "source_type": self.source_type,
            "endpoint": endpoint,
            "as_of": as_of,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "package_version": str(getattr(module, "__version__", "unknown")),
            "data": _to_records(raw),
        }

    def normalize(self, raw_object: Mapping[str, Any]) -> dict[str, Any]:
        return dict(raw_object)


class BaoStockDataSourceAdapter:
    """Optional A-share historical-data fallback for macOS and Linux."""

    name = "baostock"
    source_type = "free_a_share_market_data"

    def __init__(self, module: Any | None = None) -> None:
        self._module = module

    def _load(self) -> Any:
        if self._module is None:
            self._module = importlib.import_module("baostock")
        return self._module

    def health_check(self) -> DataSourceHealth:
        try:
            module = self._load()
        except (ImportError, ModuleNotFoundError) as error:
            return DataSourceHealth(
                name=self.name,
                source_type=self.source_type,
                available=False,
                capabilities=("cn_stock_history",),
                reason=f"optional dependency unavailable: {error}",
            )
        return DataSourceHealth(
            name=self.name,
            source_type=self.source_type,
            available=True,
            capabilities=("cn_stock_history",),
            version=str(getattr(module, "__version__", "unknown")),
        )

    def fetch(self, query: Mapping[str, Any], as_of: str) -> dict[str, Any]:
        """Fetch A-share history; BaoStock is not used for HK or futures data."""

        if query.get("query_type", "history") != "history":
            raise ValueError("BaoStock adapter currently supports history only")
        module = self._load()
        session = module.login()
        if getattr(session, "error_code", "0") != "0":
            raise RuntimeError(f"BaoStock login failed: {getattr(session, 'error_msg', session)}")
        try:
            result = module.query_history_k_data_plus(
                query["code"],
                query.get(
                    "fields",
                    "date,code,open,high,low,close,volume,amount,turn,pctChg",
                ),
                start_date=query.get("start_date"),
                end_date=query.get("end_date", as_of),
                frequency=query.get("frequency", "d"),
                adjustflag=query.get("adjustflag", "3"),
            )
            return {
                "source": self.name,
                "source_type": self.source_type,
                "query_type": "history",
                "as_of": as_of,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "package_version": str(getattr(module, "__version__", "unknown")),
                "data": _to_records(result),
            }
        finally:
            module.logout()

    def normalize(self, raw_object: Mapping[str, Any]) -> dict[str, Any]:
        return dict(raw_object)


class PublicHttpDataSourceAdapter:
    """Generic adapter for an explicitly configured public JSON/text endpoint."""

    def __init__(
        self,
        name: str,
        capabilities: tuple[str, ...],
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.name = name
        self.source_type = "official_public_disclosure"
        self.capabilities = capabilities
        self._opener = opener or urlopen

    def health_check(self) -> DataSourceHealth:
        return DataSourceHealth(
            name=self.name,
            source_type=self.source_type,
            available=True,
            capabilities=self.capabilities,
            version="public-endpoint",
        )

    def fetch(self, query: Mapping[str, Any], as_of: str) -> dict[str, Any]:
        url = str(query.get("url", ""))
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"an explicit {self.name} http(s) url is required")
        url = _with_query(url, query.get("params", {}))
        request = Request(
            url,
            headers={"User-Agent": "industry-first-research/0.1"},
        )
        response = self._opener(request, timeout=float(query.get("timeout", 15)))
        try:
            raw = response.read()
            content_type = _response_content_type(response)
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
        payload = _decode_public_payload(raw)
        return {
            "source": self.name,
            "source_type": self.source_type,
            "url": url,
            "content_type": content_type,
            "as_of": as_of,
            "retrieved_at": _now(),
            "data": payload,
        }

    def normalize(self, raw_object: Mapping[str, Any]) -> dict[str, Any]:
        return dict(raw_object)


class EastmoneyDataSourceAdapter(PublicHttpDataSourceAdapter):
    """Dependency-free adapter for an explicitly configured Eastmoney endpoint."""

    name = "eastmoney"
    source_type = "public_api"

    def __init__(self, opener: Callable[..., Any] | None = None) -> None:
        super().__init__(
            name=self.name,
            capabilities=("cn_stock", "hk_stock", "industry", "futures"),
            opener=opener,
        )


def default_free_data_adapters() -> tuple[Any, ...]:
    return (
        PublicHttpDataSourceAdapter(
            "official_exchange",
            ("exchange_disclosure", "futures_rules", "futures_inventory"),
        ),
        PublicHttpDataSourceAdapter(
            "company_disclosure",
            ("company_disclosure", "financial_statement"),
        ),
        EastmoneyDataSourceAdapter(),
        AkshareDataSourceAdapter(),
        BaoStockDataSourceAdapter(),
    )


def default_data_source_router(
    policy: FreeDataSourcePolicy | None = None,
) -> DataSourceRouter:
    return DataSourceRouter(default_free_data_adapters(), policy)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _capture_output(function: Callable[..., Any], *args: Any, **kwargs: Any) -> tuple[Any, str]:
    """Keep noisy optional data libraries from corrupting machine-readable output."""

    stdout = StringIO()
    stderr = StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = function(*args, **kwargs)
    except Exception as error:
        diagnostics = _clean_diagnostics(stdout.getvalue(), stderr.getvalue())
        setattr(error, "captured_diagnostics", diagnostics)
        raise
    return result, _clean_diagnostics(stdout.getvalue(), stderr.getvalue())


def _merge_diagnostics(*values: str) -> str:
    return _clean_diagnostics("\n".join(value for value in values if value))


def _clean_diagnostics(stdout: str, stderr: str = "") -> str:
    combined = "\n".join(value.strip() for value in (stdout, stderr) if value.strip())
    return combined[:2000]


def _has_payload(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, Mapping):
        if not value:
            return False
        if "data" in value:
            return _has_payload(value["data"])
        return True
    if isinstance(value, (str, bytes)):
        return bool(value)
    try:
        return len(value) > 0
    except TypeError:
        return True


def _has_required_fields(value: Any, fields: Sequence[str]) -> bool:
    if not fields:
        return True
    if isinstance(value, Mapping):
        if all(field in value for field in fields):
            return True
        return any(_has_required_fields(item, fields) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_required_fields(item, fields) for item in value)
    return False


def _with_query(url: str, params: Mapping[str, Any]) -> str:
    if not params:
        return url
    parsed = urlsplit(url)
    existing = dict(parse_qsl(parsed.query))
    existing.update({key: str(value) for key, value in params.items()})
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(existing), parsed.fragment)
    )


def _response_content_type(response: Any) -> str:
    headers = getattr(response, "headers", None)
    if headers is None:
        return "unknown"
    getter = getattr(headers, "get_content_type", None)
    if callable(getter):
        return str(getter())
    getter = getattr(headers, "get", None)
    if callable(getter):
        return str(getter("Content-Type", "unknown"))
    return "unknown"


def _decode_public_payload(raw: Any) -> Any:
    import json

    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return text


def _to_records(value: Any) -> Any:
    if isinstance(value, Mapping):
        return dict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict(orient="records")
        except TypeError:
            return to_dict()
    get_data = getattr(value, "get_data", None)
    if callable(get_data):
        return _to_records(get_data())
    if isinstance(value, (list, tuple)):
        return list(value)
    return value
