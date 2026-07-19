"""Conservative, read-only screening of company LIGHT profiles."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from .cross_validation import normalize_industry_name
from .models import CompanyCandidate


_LIGHT_FIELDS = ("legal_name", "main_business", "reported_industry", "listing_market")
_LIGHT_FIELD_REASONS = {
    "legal_name": "LEGAL_NAME_MISSING",
    "main_business": "MAIN_BUSINESS_MISSING",
    "reported_industry": "REPORTED_INDUSTRY_MISSING",
    "listing_market": "LISTING_MARKET_MISSING",
}


class CompanyScreenError(ValueError):
    """Raised when screen configuration is invalid."""


def screen_company_candidates(
    candidates: Sequence[CompanyCandidate],
    *,
    expected_industry: str = "",
    require_main_business: bool = True,
    require_source: bool = True,
    input_snapshot_id: str = "",
    input_as_of: str = "",
    input_source: Any = "",
) -> dict[str, Any]:
    """Classify LIGHT data quality without estimating value or investment merit."""

    results = [
        _screen_one(
            candidate,
            expected_industry=expected_industry,
            require_main_business=require_main_business,
            require_source=require_source,
        )
        for candidate in candidates
    ]
    counts = Counter(item["screen_state"] for item in results)
    return {
        "schema_version": "company-light-screen.v1",
        "candidate_count": len(results),
        "expected_industry": expected_industry,
        "input_snapshot_id": input_snapshot_id,
        "input_as_of": input_as_of,
        "input_source": input_source,
        "rules": {
            "require_main_business": require_main_business,
            "require_source": require_source,
            "read_only": True,
            "investment_conclusion": False,
        },
        "status_counts": dict(counts),
        "items": results,
        "data_quality": {
            "status": "OK" if results else "INSUFFICIENT_DATA",
            "reason": (
                "Screen classifies source-bound LIGHT completeness only; it does not assess valuation or survivability."
                if results
                else "No company candidates were supplied."
            ),
        },
    }


def _screen_one(
    candidate: CompanyCandidate,
    *,
    expected_industry: str,
    require_main_business: bool,
    require_source: bool,
) -> dict[str, Any]:
    profile = candidate.light_profile
    reasons: list[str] = []
    blockers: list[str] = []
    status = str(profile.get("status", "NOT_REQUESTED"))
    if status == "UNAVAILABLE":
        blockers.append("LIGHT_DATA_UNAVAILABLE")
    elif status in {"PARTIAL", "NOT_REQUESTED"}:
        reasons.append("LIGHT_PROFILE_INCOMPLETE")
    if not candidate.company_id or not candidate.display_name:
        blockers.append("IDENTITY_INCOMPLETE")
    if require_source and not profile.get("source") and not candidate.source:
        blockers.append("SOURCE_MISSING")
    if require_main_business and not str(profile.get("main_business") or "").strip():
        reasons.append("MAIN_BUSINESS_MISSING")
    for field in _missing_light_fields(profile):
        reason = _LIGHT_FIELD_REASONS[field]
        if field == "main_business" and not require_main_business:
            continue
        if reason not in reasons:
            reasons.append(reason)
    reported_industry = str(profile.get("reported_industry") or "").strip()
    if expected_industry and reported_industry:
        if normalize_industry_name(expected_industry) != normalize_industry_name(reported_industry):
            blockers.append("INDUSTRY_MISMATCH")
    elif expected_industry and not reported_industry:
        reasons.append("REPORTED_INDUSTRY_MISSING")

    if blockers:
        screen_state = "INSUFFICIENT"
    elif reasons:
        screen_state = "REVIEW"
    else:
        screen_state = "PASS"
    return {
        "company_id": candidate.company_id,
        "display_name": candidate.display_name,
        "industry_id": candidate.industry_id,
        "source": str(profile.get("source") or candidate.source or ""),
        "as_of": str(profile.get("as_of") or ""),
        "available_fields": list(profile.get("available_fields") or ()),
        "field_sources": _field_sources(profile.get("field_sources")),
        "additional_sources": _string_list(profile.get("additional_sources")),
        "data_tier": candidate.data_tier.value,
        "light_status": status,
        "screen_state": screen_state,
        "reasons": list(dict.fromkeys(reasons)),
        "blockers": blockers,
        "evidence_gaps": list(dict.fromkeys([*reasons, *blockers])),
        "review_only": True,
        "investment_conclusion": False,
    }


def _missing_light_fields(profile: dict[str, Any]) -> list[str]:
    available = profile.get("available_fields")
    if isinstance(available, list):
        available_fields = {str(field) for field in available}
    else:
        available_fields = {
            field for field in _LIGHT_FIELDS if str(profile.get(field) or "").strip()
        }
    return [field for field in _LIGHT_FIELDS if field not in available_fields]


def _field_sources(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise CompanyScreenError("field_sources must be a string mapping")
    return {
        str(field): str(source).strip()
        for field, source in value.items()
        if str(field).strip() and str(source).strip()
    }


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise CompanyScreenError("source fields must be string lists")
    return [str(item) for item in value if str(item)]
