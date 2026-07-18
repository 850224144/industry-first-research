"""Cross-platform free-data source adapters.

The core does not require a broker terminal.  AKShare is the primary public
market-data entry point; BaoStock is an optional A-share fallback.  Both are
treated as collection sources, not as authoritative facts.  Official exchange
and company announcements remain the preferred verification layer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import importlib
from typing import Any


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
class FreeDataSourcePolicy:
    """Default source order with no broker-terminal dependency."""

    listed_company_sources: tuple[str, ...] = ("akshare", "baostock")
    industry_sources: tuple[str, ...] = ("akshare",)
    futures_sources: tuple[str, ...] = ("official_exchange", "akshare")
    announcement_sources: tuple[str, ...] = (
        "official_exchange",
        "company_disclosure",
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


def default_free_data_adapters() -> tuple[Any, ...]:
    return (AkshareDataSourceAdapter(), BaoStockDataSourceAdapter())


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
