"""Read-only Tonghuashun industry table adapter."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from html.parser import HTMLParser
import html
import json
from typing import Any
from urllib.request import Request, urlopen
from urllib.parse import urljoin

from .models import IndustryRadarSnapshot, IndustrySignal, IndustryState


DEFAULT_ENDPOINT = "https://q.10jqka.com.cn/thshy/"
DEFAULT_USER_AGENT = "industry-first-research/0.1"


class TonghuashunAPIError(RuntimeError):
    """Raised when the public Tonghuashun page cannot form a radar snapshot."""


FetchBytes = Callable[[str], bytes]


class TonghuashunIndustryRadar:
    """Fetch the bounded industry table from Tonghuashun's public quote page."""

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
        self._last_fetched_at = ""
        self._last_row_count = 0

    def snapshots(self, as_of: str) -> Iterable[IndustryRadarSnapshot]:
        self._last_fetched_at = datetime.now(timezone.utc).isoformat()
        try:
            raw = self._fetch(self.endpoint)
            parser = _IndustryTableParser()
            parser.feed(raw.decode("gbk", errors="strict"))
            parser.close()
        except (OSError, TimeoutError, UnicodeDecodeError) as error:
            raise TonghuashunAPIError(
                f"unable to read Tonghuashun response: {error}"
            ) from error

        rows = parser.rows[: self.page_size]
        self._last_row_count = len(rows)
        result = [self._to_snapshot(row, as_of) for row in rows]
        result = [item for item in result if item is not None]
        if not result:
            raise TonghuashunAPIError(
                "Tonghuashun response contained no usable industry rows"
            )
        return result

    def metadata(self, as_of: str) -> dict[str, Any]:
        return {
            "provider": "tonghuashun",
            "endpoint": self.endpoint,
            "as_of": as_of,
            "fetched_at": self._last_fetched_at,
            "requested_rows": self.page_size,
            "returned_rows": self._last_row_count,
            "read_only": True,
        }

    def _fetch(self, url: str) -> bytes:
        if self._fetcher is not None:
            return self._fetcher(url)
        request = Request(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": self.user_agent,
            },
        )
        with urlopen(request, timeout=self.timeout) as response:
            return response.read()

    def _to_snapshot(
        self, row: "IndustryTableRow", as_of: str
    ) -> IndustryRadarSnapshot | None:
        if not row.code or not row.name:
            return None
        source = urljoin(self.endpoint, row.detail_url or self.endpoint)
        if row.change_pct is None:
            state = IndustryState.INSUFFICIENT
            reason = "Daily change is unavailable; no directional conclusion is made."
        elif row.change_pct < 0:
            state = IndustryState.DETERIORATING
            reason = "Single-source daily quote is negative; this is not a cycle conclusion."
        else:
            state = IndustryState.CLEARING
            reason = "Single-source daily quote is non-negative; this is only a strength clue."

        signals = (
            IndustrySignal("change_pct", row.change_pct, as_of, source, "VERIFIED"),
            IndustrySignal("turnover_volume", row.turnover_volume, as_of, source, "VERIFIED"),
            IndustrySignal("turnover_value", row.turnover_value, as_of, source, "VERIFIED"),
            IndustrySignal("main_net_inflow", row.main_net_inflow, as_of, source, "VERIFIED"),
            IndustrySignal(
                "breadth",
                {"up": row.up_count, "down": row.down_count},
                as_of,
                source,
                "VERIFIED",
            ),
        )
        opportunity_types = ("market_strength_signal",) if state == IndustryState.CLEARING else ()
        return IndustryRadarSnapshot(
            industry_id=row.code,
            display_name=row.name,
            as_of=as_of,
            state=state,
            signals=signals,
            evidence_completeness="SINGLE_SOURCE",
            opportunity_types=opportunity_types,
            reason=reason,
        )


class _IndustryTableParser(HTMLParser):
    """Parse table rows without adding a runtime dependency for HTML parsing."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[IndustryTableRow] = []
        self._in_row = False
        self._in_cell = False
        self._cells: list[str] = []
        self._cell_text: list[str] = []
        self._industry_href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr" and not self._in_row:
            self._in_row = True
            self._cells = []
            self._industry_href = ""
        elif self._in_row and tag in {"td", "th"} and not self._in_cell:
            self._in_cell = True
            self._cell_text = []
        elif self._in_row and self._in_cell and tag == "a" and len(self._cells) == 1:
            href = dict(attrs).get("href")
            if href:
                self._industry_href = html.unescape(href)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._in_cell:
            self._cells.append(_clean_text("".join(self._cell_text)))
            self._cell_text = []
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            self._in_row = False
            row = _row_from_cells(self._cells, self._industry_href)
            if row is not None:
                self.rows.append(row)

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_text.append(data)


class IndustryTableRow:
    def __init__(
        self,
        *,
        code: str,
        name: str,
        detail_url: str,
        change_pct: float | None,
        turnover_volume: float | None,
        turnover_value: float | None,
        main_net_inflow: float | None,
        up_count: int | None,
        down_count: int | None,
    ) -> None:
        self.code = code
        self.name = name
        self.detail_url = detail_url
        self.change_pct = change_pct
        self.turnover_volume = turnover_volume
        self.turnover_value = turnover_value
        self.main_net_inflow = main_net_inflow
        self.up_count = up_count
        self.down_count = down_count


def _row_from_cells(cells: list[str], detail_url: str) -> IndustryTableRow | None:
    if len(cells) < 8 or not cells[0].isdigit() or not cells[1]:
        return None
    code = detail_url.rstrip("/").split("/")[-1] if detail_url else ""
    if not code:
        return None
    return IndustryTableRow(
        code=code,
        name=cells[1],
        detail_url=detail_url,
        change_pct=_as_float(cells[2]),
        turnover_volume=_as_float(cells[3]),
        turnover_value=_as_float(cells[4]),
        main_net_inflow=_as_float(cells[5]),
        up_count=_as_int(cells[6]),
        down_count=_as_int(cells[7]),
    )


def _clean_text(value: str) -> str:
    return " ".join(html.unescape(value).split())


def _as_float(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value.replace(",", "")) if isinstance(value, str) else float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value in (None, "", "-"):
        return None
    try:
        return int(float(value.replace(",", ""))) if isinstance(value, str) else int(value)
    except (TypeError, ValueError):
        return None
