"""Read-only LIGHT company facts from Tonghuashun public company pages."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from html.parser import HTMLParser
import html
import re
from typing import Any
from urllib.request import Request, urlopen

from .models import CompanyCandidate, CompanyDataTier


DEFAULT_BASIC_URL = "https://basic.10jqka.com.cn/{company_id}/"
DEFAULT_USER_AGENT = "industry-first-research/0.1"


class TonghuashunLightDataError(RuntimeError):
    """Raised when a company LIGHT page cannot be fetched or decoded."""


FetchBytes = Callable[[str], bytes]


class TonghuashunLightCompanyData:
    """Enrich selected candidates with bounded, source-bound LIGHT fields."""

    def __init__(
        self,
        *,
        endpoint_template: str = DEFAULT_BASIC_URL,
        timeout: float = 15.0,
        user_agent: str = DEFAULT_USER_AGENT,
        fetcher: FetchBytes | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.endpoint_template = endpoint_template
        self.timeout = timeout
        self.user_agent = user_agent
        self._fetcher = fetcher

    def enrich(
        self, candidates: Sequence[CompanyCandidate], tier: CompanyDataTier
    ) -> Sequence[CompanyCandidate]:
        if tier != CompanyDataTier.LIGHT:
            return list(candidates)
        return [self._enrich_one(candidate) for candidate in candidates]

    def _enrich_one(self, candidate: CompanyCandidate) -> CompanyCandidate:
        url = self.endpoint_template.format(company_id=candidate.company_id)
        retrieved_at = datetime.now(timezone.utc).isoformat()
        try:
            raw = self._fetch(url)
            profile = _parse_profile(raw.decode("gbk", errors="strict"))
        except (OSError, TimeoutError, UnicodeDecodeError) as error:
            return candidate.with_light_profile(
                {
                    "status": "UNAVAILABLE",
                    "company_id": candidate.company_id,
                    "as_of": retrieved_at[:10],
                    "retrieved_at": retrieved_at,
                    "source": url,
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "read_only": True,
                }
            )

        profile.update(
            {
                "company_id": candidate.company_id,
                "as_of": retrieved_at[:10],
                "retrieved_at": retrieved_at,
                "source": url,
                "read_only": True,
            }
        )
        return candidate.with_light_profile(profile)

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


def _parse_profile(document: str) -> dict[str, Any]:
    parser = _ProfileParser()
    parser.feed(document)
    parser.close()
    fields = {
        "legal_name": parser.company_name,
        "main_business": parser.main_business,
        "reported_industry": parser.reported_industry,
        "listing_market": parser.listing_market,
    }
    available = [name for name, value in fields.items() if value]
    fields["status"] = "VERIFIED" if len(available) == len(fields) else "PARTIAL"
    fields["available_fields"] = available
    return fields


class _ProfileParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.company_name = ""
        self.main_business = ""
        self.reported_industry = ""
        self.listing_market = ""
        self._title_parts: list[str] = []
        self._capture: str | None = None
        self._capture_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag.lower() == "title":
            self._in_title = True
        if tag.lower() in {"span", "a"}:
            element_id = attrs_dict.get("id", "")
            class_names = set((attrs_dict.get("class") or "").split())
            if "main-bussiness-text" in class_names:
                self._start_capture("main_business")
            elif element_id == "companyInfoName":
                self._start_capture("company_name")
            elif element_id == "companyInfoIndustry":
                self._start_capture("reported_industry")
            elif element_id == "companyInfoMarket":
                self._start_capture("listing_market")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False
        if self._capture is not None and tag.lower() in {"span", "a"}:
            self._finish_capture()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        if self._capture is not None:
            self._capture_parts.append(data)

    def close(self) -> None:
        super().close()
        if self._capture is not None:
            self._finish_capture()
        if not self.company_name:
            self.company_name = _company_name_from_title("".join(self._title_parts))

    def _start_capture(self, field: str) -> None:
        if self._capture is None:
            self._capture = field
            self._capture_parts = []

    def _finish_capture(self) -> None:
        value = _clean_text("".join(self._capture_parts))
        if value:
            setattr(self, self._capture, value)
        self._capture = None
        self._capture_parts = []


def _company_name_from_title(title: str) -> str:
    match = re.match(r"(.+?)\(\d{6}\)", _clean_text(title))
    return match.group(1).strip() if match else ""


def _clean_text(value: str) -> str:
    return " ".join(html.unescape(value).split())
