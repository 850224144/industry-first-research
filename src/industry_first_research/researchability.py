"""Derive a conservative researchability gate from supplemental evidence."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


class ResearchabilityError(ValueError):
    """Raised when a supplemental report cannot drive a researchability gate."""


RESEARCHABILITY_SCHEMA_VERSION = "company-researchability.v1"
RULE_VERSION = "company-researchability-rules.v1"
_QUEUE_STATES = {"WATCH", "REVIEW", "CANDIDATE", "INSUFFICIENT", "REJECTED"}
_SUPPLEMENTAL_STATES = {"READY", "PARTIAL", "INSUFFICIENT", "BLOCKED"}


def build_researchability_report(
    supplemental_report: Mapping[str, Any],
    *,
    rule_version: str = RULE_VERSION,
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Convert evidence coverage into a hard research-depth gate."""

    if not isinstance(supplemental_report, Mapping):
        raise ResearchabilityError("input supplemental report must be a JSON object")
    if supplemental_report.get("schema_version") != (
        "company-supplemental-evidence.v1"
    ):
        raise ResearchabilityError(
            "input must be a company-supplemental-evidence.v1 report"
        )
    raw_items = supplemental_report.get("items")
    if not isinstance(raw_items, list):
        raise ResearchabilityError("supplemental report has no items list")
    if not rule_version.strip():
        raise ResearchabilityError("rule_version must not be empty")

    items = [_build_item(item, rule_version=rule_version) for item in raw_items]
    counts = Counter(item["research_readiness"] for item in items)
    input_report_id = str(supplemental_report.get("report_id") or "")
    report_id = snapshot_id or input_report_id or "supplemental-input"
    return {
        "schema_version": RESEARCHABILITY_SCHEMA_VERSION,
        "report_id": f"company-researchability-{report_id}",
        "input_report_id": input_report_id,
        "input_queue_id": str(supplemental_report.get("input_queue_id") or ""),
        "input_snapshot_id": str(
            supplemental_report.get("input_snapshot_id") or ""
        ),
        "rule_version": rule_version,
        "as_of": str(supplemental_report.get("as_of") or ""),
        "source": str(supplemental_report.get("source") or ""),
        "source_metadata": supplemental_report.get("source_metadata") or {},
        "candidate_count": len(items),
        "readiness_counts": dict(counts),
        "items": items,
        "policy": {
            "researchability_only": True,
            "candidate_state_preserved": True,
            "standard_research_requires_ready": True,
            "partial_research_requires_degradation": True,
            "insufficient_is_screen_only": True,
            "blocked_stops_deep_research": True,
            "read_only": True,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _build_item(item: Any, *, rule_version: str) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise ResearchabilityError("each supplemental item must be an object")
    company_id = str(item.get("company_id") or "").strip()
    candidate_state = str(item.get("candidate_state") or "").upper()
    supplemental_state = str(item.get("supplemental_state") or "").upper()
    if not company_id:
        raise ResearchabilityError("supplemental item company_id is required")
    if candidate_state not in _QUEUE_STATES:
        raise ResearchabilityError(
            f"unsupported candidate_state: {candidate_state or '<empty>'}"
        )
    if supplemental_state not in _SUPPLEMENTAL_STATES:
        raise ResearchabilityError(
            f"unsupported supplemental_state: {supplemental_state or '<empty>'}"
        )

    candidate_reasons = _string_list(item.get("candidate_reasons"))
    candidate_blockers = _string_list(item.get("candidate_blockers"))
    candidate_gaps = _string_list(item.get("candidate_evidence_gaps"))
    supplemental_blockers = _string_list(item.get("blockers"))
    supplemental_gaps = _string_list(item.get("evidence_gaps"))
    reasons: list[str] = []
    blockers: list[str] = list(candidate_blockers)
    evidence_gaps = _unique([*candidate_gaps, *supplemental_gaps])

    if candidate_state == "REJECTED":
        readiness, depth = "BLOCKED", "NONE"
        blockers.append("QUEUE_ITEM_REJECTED")
        reasons.append("REJECTED_QUEUE_ITEM_CANNOT_ENTER_RESEARCH")
    elif candidate_state == "INSUFFICIENT":
        readiness, depth = "INSUFFICIENT", "SCREEN_ONLY"
        blockers.append("QUEUE_ITEM_INSUFFICIENT")
        reasons.append("QUEUE_EVIDENCE_SUPPORTS_SCREENING_ONLY")
    elif supplemental_state == "BLOCKED":
        readiness, depth = "BLOCKED", "NONE"
        blockers.extend(supplemental_blockers or ["SUPPLEMENTAL_EVIDENCE_BLOCKED"])
        reasons.append("SUPPLEMENTAL_EVIDENCE_BLOCKED")
    elif supplemental_state == "INSUFFICIENT":
        readiness, depth = "INSUFFICIENT", "SCREEN_ONLY"
        blockers.extend(supplemental_blockers or ["SUPPLEMENTAL_EVIDENCE_INSUFFICIENT"])
        reasons.append("SUPPLEMENTAL_EVIDENCE_SUPPORTS_SCREENING_ONLY")
    elif supplemental_state == "PARTIAL":
        readiness, depth = "PARTIAL", "QUICK"
        reasons.append("SUPPLEMENTAL_EVIDENCE_REQUIRES_DEGRADED_RESEARCH")
    elif candidate_state == "REVIEW" or evidence_gaps:
        readiness, depth = "PARTIAL", "QUICK"
        reasons.append("CANDIDATE_REVIEW_GAPS_REQUIRE_DEGRADED_RESEARCH")
    else:
        readiness, depth = "READY", "STANDARD"
        reasons.append("KEY_SUPPLEMENTAL_FIELDS_COVERED")

    if candidate_state == "REVIEW" and "CANDIDATE_REVIEW_GAPS_REQUIRE_DEGRADED_RESEARCH" not in reasons:
        reasons.append("CANDIDATE_REMAINS_REVIEW_ONLY")
    if supplemental_blockers and supplemental_state not in {"BLOCKED", "INSUFFICIENT"}:
        blockers.extend(supplemental_blockers)

    return {
        "company_id": company_id,
        "display_name": str(item.get("display_name") or ""),
        "industry_id": str(item.get("industry_id") or ""),
        "candidate_state": candidate_state,
        "candidate_state_changed": False,
        "candidate_rule_version": str(item.get("candidate_rule_version") or ""),
        "candidate_reasons": candidate_reasons,
        "candidate_blockers": candidate_blockers,
        "candidate_evidence_gaps": candidate_gaps,
        "candidate_field_sources": _field_sources(
            item.get("candidate_field_sources")
        ),
        "candidate_additional_sources": _string_list(
            item.get("candidate_additional_sources")
        ),
        "supplemental_state": supplemental_state,
        "research_readiness": readiness,
        "research_depth": depth,
        "rule_version": rule_version,
        "reasons": _unique(reasons),
        "blockers": _unique(blockers),
        "evidence_gaps": evidence_gaps,
        "allowed_actions": _allowed_actions(readiness),
        "prohibited_actions": [
            "investment_conclusion",
            "automatic_candidate_promotion",
            "execution",
        ],
        "review_only": True,
        "investment_conclusion": False,
    }


def _allowed_actions(readiness: str) -> list[str]:
    return {
        "READY": ["standard_research", "evidence_refresh"],
        "PARTIAL": ["quick_research", "gap_review", "evidence_refresh"],
        "INSUFFICIENT": ["screen_only", "gap_collection", "evidence_refresh"],
        "BLOCKED": ["identity_or_conflict_resolution"],
    }[readiness]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise ResearchabilityError("researchability fields must be string lists")
    return [str(item) for item in value if str(item)]


def _field_sources(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ResearchabilityError("field_sources must be a string mapping")
    return {
        str(field): str(source).strip()
        for field, source in value.items()
        if str(field).strip() and str(source).strip()
    }


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
