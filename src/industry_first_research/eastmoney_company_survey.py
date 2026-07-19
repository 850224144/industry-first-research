"""Read-only Eastmoney company survey facts for missing LIGHT fields."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
import json
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from .models import CompanyCandidate, CompanyDataTier


DEFAULT_SURVEY_URL = (
    "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/"
    "CompanySurveyAjax?code={market_code}{company_id}"
)
DEFAULT_MARKET_CODES = ("SZ", "SH", "BJ")
DEFAULT_USER_AGENT = "industry-first-research/0.1"


class EastmoneyCompanySurveyError(RuntimeError):
    """Raised when a company survey response cannot be used safely."""


FetchBytes = Callable[[str], bytes]


class EastmoneyCompanySurveyData:
    """Fill only missing ``listing_market`` from a source-bound JSON response.

    The adapter probes bounded market-code routes and accepts a response only when
    the returned company code matches the requested candidate. It never derives a
    market value from a stock-code convention.
    """

    def __init__(
        self,
        *,
        endpoint_template: str = DEFAULT_SURVEY_URL,
        market_codes: Sequence[str] = DEFAULT_MARKET_CODES,
        timeout: float = 15.0,
        user_agent: str = DEFAULT_USER_AGENT,
        fetcher: FetchBytes | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        normalised_codes = tuple(dict.fromkeys(str(code).strip().upper() for code in market_codes))
        if not normalised_codes or any(not code for code in normalised_codes):
            raise ValueError("market_codes must contain non-empty values")
        self.endpoint_template = endpoint_template
        self.market_codes = normalised_codes
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
        if str(candidate.light_profile.get("listing_market") or "").strip():
            return candidate

        retrieved_at = datetime.now(timezone.utc).isoformat()
        for market_code in self.market_codes:
            url = self.endpoint_template.format(
                market_code=quote(market_code),
                company_id=quote(candidate.company_id),
            )
            try:
                survey = _parse_survey(self._fetch(url), candidate.company_id)
            except (EastmoneyCompanySurveyError, OSError, TimeoutError):
                continue
            if not survey["listing_market"]:
                continue
            return _merge_listing_market(
                candidate,
                survey["listing_market"],
                source=url,
                retrieved_at=retrieved_at,
            )

        return candidate

    def _fetch(self, url: str) -> bytes:
        if self._fetcher is not None:
            return self._fetcher(url)
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": self.user_agent,
            },
        )
        with urlopen(request, timeout=self.timeout) as response:
            return response.read()


def _parse_survey(raw: bytes, company_id: str) -> dict[str, str]:
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EastmoneyCompanySurveyError(
            f"invalid Eastmoney company survey response: {error}"
        ) from error
    if not isinstance(payload, dict) or not isinstance(payload.get("jbzl"), dict):
        raise EastmoneyCompanySurveyError("Eastmoney company survey has no jbzl object")
    profile = payload["jbzl"]
    returned_company_id = str(profile.get("agdm") or "").strip()
    if returned_company_id != str(company_id).strip():
        raise EastmoneyCompanySurveyError(
            f"Eastmoney company survey code mismatch: expected {company_id}, got {returned_company_id or '<empty>'}"
        )
    return {
        "legal_name": _clean_value(profile.get("gsmc")),
        "listing_market": _clean_value(profile.get("ssjys")),
    }


def _merge_listing_market(
    candidate: CompanyCandidate,
    listing_market: str,
    *,
    source: str,
    retrieved_at: str,
) -> CompanyCandidate:
    profile = dict(candidate.light_profile)
    profile["listing_market"] = listing_market
    available_fields = list(profile.get("available_fields") or ())
    if "listing_market" not in available_fields:
        available_fields.append("listing_market")
    profile["available_fields"] = available_fields
    required_fields = ("legal_name", "main_business", "reported_industry", "listing_market")
    profile["status"] = (
        "VERIFIED"
        if all(str(profile.get(field) or "").strip() for field in required_fields)
        else "PARTIAL"
    )
    field_sources = dict(profile.get("field_sources") or {})
    field_sources["listing_market"] = source
    profile["field_sources"] = field_sources
    additional_sources = list(profile.get("additional_sources") or ())
    if source not in additional_sources:
        additional_sources.append(source)
    profile["additional_sources"] = additional_sources
    profile["listing_market_retrieved_at"] = retrieved_at
    return candidate.with_light_profile(profile)


def _clean_value(value: Any) -> str:
    return " ".join(str(value or "").split())
