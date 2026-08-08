"""Read-only Eastmoney industry quote adapter for the first radar snapshot."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone
import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import IndustryRadarSnapshot, IndustrySignal, IndustryState


DEFAULT_ENDPOINT = "https://push2.eastmoney.com/api/qt/clist/get"
DEFAULT_FIELDS = "f12,f14,f2,f3,f5,f6,f62,f104,f105,f106"
DEFAULT_USER_AGENT = "industry-first-research/0.1"


class EastmoneyAPIError(RuntimeError):
    """Raised when the public quote response cannot form a radar snapshot."""


FetchBytes = Callable[[str], bytes]


class EastmoneyIndustryRadar:
    """Fetch a bounded, read-only list of Eastmoney industry quote rows.

    The adapter deliberately maps one-day quote observations to ``CLEARING`` or
    ``DETERIORATING`` only. A single quote snapshot cannot confirm a cycle reversal.
    """

    def __init__(
        self,
        *,
        page_size: int = 50,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: float = 15.0,
        user_agent: str = DEFAULT_USER_AGENT,
        fetcher: FetchBytes | None = None,
    ) -> None:
        if page_size < 1:
            raise ValueError("page_size must be positive")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.page_size = page_size
        self.endpoint = endpoint
        self.timeout = timeout
        self.user_agent = user_agent
        self._fetcher = fetcher
        self._last_url = ""
        self._last_fetched_at = ""
        self._last_total: int | None = None

    def snapshots(self, as_of: str) -> Iterable[IndustryRadarSnapshot]:
        url = self.build_url()
        self._last_url = url
        self._last_fetched_at = datetime.now(timezone.utc).isoformat()
        try:
            raw = self._fetch(url)
            payload = json.loads(raw.decode("utf-8-sig"))
        except (OSError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EastmoneyAPIError(f"unable to read Eastmoney response: {error}") from error

        if not isinstance(payload, dict) or payload.get("rc") not in (0, None):
            raise EastmoneyAPIError("Eastmoney returned an unsuccessful response")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise EastmoneyAPIError("Eastmoney response has no data object")
        rows = data.get("diff")
        if not isinstance(rows, list):
            raise EastmoneyAPIError("Eastmoney response has no industry rows")
        self._last_total = _as_int(data.get("total"))

        result = [self._to_snapshot(row, as_of, url) for row in rows if isinstance(row, dict)]
        result = [item for item in result if item is not None]
        if not result:
            raise EastmoneyAPIError("Eastmoney response contained no usable industry rows")
        return result

    def build_url(self) -> str:
        params = {
            "pn": 1,
            "pz": self.page_size,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:90+t:2",
            "fields": DEFAULT_FIELDS,
        }
        # Eastmoney's public endpoint expects the market filter and field list
        # in their query-native form instead of percent-encoded separators.
        return f"{self.endpoint}?{urlencode(params, safe=',+:')}"

    def metadata(self, as_of: str) -> dict[str, Any]:
        return {
            "provider": "eastmoney",
            "endpoint": self._last_url or self.endpoint,
            "as_of": as_of,
            "fetched_at": self._last_fetched_at,
            "requested_rows": self.page_size,
            "market_total_rows": self._last_total,
            "read_only": True,
        }

    def _fetch(self, url: str) -> bytes:
        if self._fetcher is not None:
            return self._fetcher(url)
        request = Request(url, headers={"User-Agent": self.user_agent})
        with urlopen(request, timeout=self.timeout) as response:
            return response.read()

    @staticmethod
    def _to_snapshot(
        row: dict[str, Any], as_of: str, url: str
    ) -> IndustryRadarSnapshot | None:
        industry_id = row.get("f12")
        display_name = row.get("f14")
        if not industry_id or not display_name:
            return None

        change_pct = _as_float(row.get("f3"))
        current_price = _as_float(row.get("f2"))
        turnover = _as_float(row.get("f6"))
        main_net_inflow = _as_float(row.get("f62"))
        breadth = {
            "up": _as_int(row.get("f104")),
            "down": _as_int(row.get("f105")),
            "flat": _as_int(row.get("f106")),
        }
        if change_pct is None:
            state = IndustryState.INSUFFICIENT
            reason = "Daily change is unavailable; no directional conclusion is made."
        elif change_pct < 0:
            state = IndustryState.DETERIORATING
            reason = "Single-source daily quote is negative; this is not a cycle conclusion."
        else:
            state = IndustryState.CLEARING
            reason = "Single-source daily quote is non-negative; this is only a strength clue."

        source = url
        signals = (
            IndustrySignal("change_pct", change_pct, as_of, source, "VERIFIED"),
            IndustrySignal("current_price", current_price, as_of, source, "VERIFIED"),
            IndustrySignal("turnover_value", turnover, as_of, source, "VERIFIED"),
            IndustrySignal("main_net_inflow", main_net_inflow, as_of, source, "VERIFIED"),
            IndustrySignal("breadth", breadth, as_of, source, "VERIFIED"),
        )
        opportunity_types = ("market_strength_signal",) if state == IndustryState.CLEARING else ()
        return IndustryRadarSnapshot(
            industry_id=str(industry_id),
            display_name=str(display_name),
            as_of=as_of,
            state=state,
            signals=signals,
            evidence_completeness="SINGLE_SOURCE",
            opportunity_types=opportunity_types,
            reason=reason,
            source_ids={"eastmoney": str(industry_id)},
        )


def _as_float(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value in (None, "", "-"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
