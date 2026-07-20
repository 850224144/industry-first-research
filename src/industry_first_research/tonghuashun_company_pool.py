"""Bounded, read-only company-pool adapter for Tonghuashun industry pages."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from html.parser import HTMLParser
import html
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from .models import CompanyCandidate, IndustryRadarSnapshot


DEFAULT_DETAIL_URL = "https://q.10jqka.com.cn/thshy/detail/code/{industry_code}/"
DEFAULT_USER_AGENT = "industry-first-research/0.1"


class TonghuashunCompanyPoolError(RuntimeError):
    """Raised when a bounded Tonghuashun company table cannot be parsed."""


FetchBytes = Callable[[str], bytes]


class TonghuashunCompanyPool:
    """Load only the visible company table for a selected industry.

    This provider intentionally has no financial-data enrichment behavior. It is a
    candidate list, not a company conclusion.
    """

    def __init__(
        self,
        *,
        page_size: int = 30,
        endpoint_template: str = DEFAULT_DETAIL_URL,
        timeout: float = 15.0,
        user_agent: str = DEFAULT_USER_AGENT,
        fetcher: FetchBytes | None = None,
    ) -> None:
        if page_size < 1:
            raise ValueError("page_size must be positive")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.page_size = page_size
        self.endpoint_template = endpoint_template
        self.timeout = timeout
        self.user_agent = user_agent
        self._fetcher = fetcher
        self._metadata: dict[str, Any] = {}

    def candidates(
        self, industry: IndustryRadarSnapshot, limit: int
    ) -> Sequence[CompanyCandidate]:
        if limit < 1:
            raise ValueError("limit must be positive")
        industry_code = industry.source_ids.get("tonghuashun", industry.industry_id)
        url = self.endpoint_template.format(industry_code=industry_code)
        fetched_at = datetime.now(timezone.utc).isoformat()
        try:
            raw = self._fetch(url)
            parser = _CompanyTableParser()
            parser.feed(raw.decode("gbk", errors="strict"))
            parser.close()
        except (OSError, TimeoutError, UnicodeDecodeError) as error:
            raise TonghuashunCompanyPoolError(
                f"unable to read Tonghuashun company table: {error}"
            ) from error

        requested_limit = min(limit, self.page_size)
        rows = parser.rows[:requested_limit]
        self._metadata = {
            "provider": "tonghuashun_company_pool",
            "endpoint": url,
            "requested_industry_id": industry.industry_id,
            "resolved_tonghuashun_industry_id": industry_code,
            "fetched_at": fetched_at,
            "requested_limit": limit,
            "adapter_limit": self.page_size,
            "returned_rows": len(rows),
            "visible_table_only": True,
            "full_industry_membership_loaded": False,
            "read_only": True,
        }
        if not rows:
            raise TonghuashunCompanyPoolError(
                "Tonghuashun company table contained no usable rows"
            )
        return [
            CompanyCandidate(
                company_id=row.code,
                display_name=row.name,
                industry_id=industry.industry_id,
                source=urljoin(url, row.company_url or url),
                inclusion_reason="Visible company row from selected industry; requires company-level verification.",
            )
            for row in rows
        ]

    def metadata(self) -> dict[str, Any]:
        return dict(self._metadata)

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


class _CompanyTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[_CompanyTableRow] = []
        self._in_row = False
        self._in_cell = False
        self._cells: list[str] = []
        self._cell_text: list[str] = []
        self._code_url = ""
        self._name_url = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr" and not self._in_row:
            self._in_row = True
            self._cells = []
            self._code_url = ""
            self._name_url = ""
        elif self._in_row and tag in {"td", "th"} and not self._in_cell:
            self._in_cell = True
            self._cell_text = []
        elif self._in_row and self._in_cell and tag == "a":
            href = dict(attrs).get("href")
            if href and len(self._cells) == 1:
                self._code_url = html.unescape(href)
            elif href and len(self._cells) == 2:
                self._name_url = html.unescape(href)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._in_cell:
            self._cells.append(_clean_text("".join(self._cell_text)))
            self._cell_text = []
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            self._in_row = False
            row = _row_from_cells(self._cells, self._code_url, self._name_url)
            if row is not None:
                self.rows.append(row)

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_text.append(data)


class _CompanyTableRow:
    def __init__(self, code: str, name: str, company_url: str) -> None:
        self.code = code
        self.name = name
        self.company_url = company_url


def _row_from_cells(
    cells: list[str], code_url: str, name_url: str
) -> _CompanyTableRow | None:
    if len(cells) < 3 or not cells[0].isdigit() or not cells[1].isdigit() or not cells[2]:
        return None
    return _CompanyTableRow(cells[1], cells[2], name_url or code_url)


def _clean_text(value: str) -> str:
    return " ".join(html.unescape(value).split())
