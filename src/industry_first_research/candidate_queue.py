"""Build a conservative, source-traceable company candidate queue."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


class CandidateQueueError(ValueError):
    """Raised when a company screen report cannot be queued."""


QUEUE_SCHEMA_VERSION = "company-candidate-queue.v1"
RULE_VERSION = "company-candidate-queue-rules.v1"
_HARD_REJECTION_BLOCKERS = {"IDENTITY_INCOMPLETE", "INDUSTRY_MISMATCH"}
_VALID_SCREEN_STATES = {"PASS", "REVIEW", "INSUFFICIENT"}
_VALID_QUEUE_STATES = {"WATCH", "REVIEW", "CANDIDATE", "INSUFFICIENT", "REJECTED"}


def build_candidate_queue(
    screen_report: Mapping[str, Any],
    *,
    as_of: str = "",
    source: str = "",
    snapshot_id: str = "",
    rule_version: str = RULE_VERSION,
) -> dict[str, Any]:
    """Convert a LIGHT screen into a review queue without making an investment call."""

    if not isinstance(screen_report, Mapping):
        raise CandidateQueueError("input must be a JSON object")
    if screen_report.get("schema_version") != "company-light-screen.v1":
        raise CandidateQueueError(
            "input must be a company-light-screen.v1 report"
        )
    raw_items = screen_report.get("items")
    if not isinstance(raw_items, list):
        raise CandidateQueueError("screen report has no items list")
    if not rule_version.strip():
        raise CandidateQueueError("rule_version must not be empty")

    resolved_as_of = as_of or _report_as_of(screen_report)
    input_source = (
        screen_report.get("input_source")
        or screen_report.get("source")
        or source
        or ""
    )
    resolved_source = source or _source_label(input_source)
    queue_items = [
        _queue_one(
            item,
            fallback_as_of=resolved_as_of,
            fallback_source=resolved_source,
            rule_version=rule_version,
        )
        for item in raw_items
    ]
    counts = Counter(item["candidate_state"] for item in queue_items)
    input_snapshot_id = str(
        screen_report.get("input_snapshot_id")
        or screen_report.get("snapshot_id")
        or snapshot_id
        or ""
    )
    queue_id = snapshot_id or input_snapshot_id
    if not queue_id:
        queue_id = "company-light-screen-input"

    return {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "queue_id": f"company-candidate-queue-{queue_id}",
        "input_schema_version": screen_report["schema_version"],
        "input_snapshot_id": input_snapshot_id,
        "rule_version": rule_version,
        "as_of": resolved_as_of,
        "source": resolved_source,
        "source_metadata": input_source,
        "candidate_count": len(queue_items),
        "status_counts": dict(counts),
        "allowed_candidate_states": sorted(_VALID_QUEUE_STATES),
        "policy": {
            "light_data_can_be_candidate": False,
            "price_or_volume_can_upgrade": False,
            "read_only": True,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
        },
        "items": queue_items,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _queue_one(
    item: Any,
    *,
    fallback_as_of: str,
    fallback_source: str,
    rule_version: str,
) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise CandidateQueueError("each screen item must be an object")
    screen_state = str(item.get("screen_state") or "").upper()
    if screen_state not in _VALID_SCREEN_STATES:
        raise CandidateQueueError(f"unsupported screen_state: {screen_state or '<empty>'}")

    reasons = _string_list(item.get("reasons"))
    blockers = _string_list(item.get("blockers"))
    evidence_gaps = _evidence_gaps(item, reasons, blockers)
    if any(blocker in _HARD_REJECTION_BLOCKERS for blocker in blockers):
        candidate_state = "REJECTED"
        queue_reason = "HARD_SCREEN_BLOCKER"
    elif screen_state == "PASS":
        candidate_state = "WATCH"
        queue_reason = "LIGHT_SCREEN_PASS_REQUIRES_FURTHER_REVIEW"
    elif screen_state == "REVIEW":
        candidate_state = "REVIEW"
        queue_reason = "LIGHT_SCREEN_REVIEW_REQUIRED"
    else:
        candidate_state = "INSUFFICIENT"
        queue_reason = "EVIDENCE_INSUFFICIENT_FOR_REVIEW"

    source = str(item.get("source") or fallback_source or "")
    item_as_of = str(item.get("as_of") or fallback_as_of or "")
    if not source and "SOURCE_MISSING" not in evidence_gaps:
        evidence_gaps.append("SOURCE_MISSING")
    if not item_as_of:
        evidence_gaps.append("AS_OF_MISSING")

    return {
        "company_id": str(item.get("company_id") or ""),
        "display_name": str(item.get("display_name") or ""),
        "industry_id": str(item.get("industry_id") or ""),
        "source": source,
        "as_of": item_as_of,
        "field_sources": _field_sources(item.get("field_sources")),
        "additional_sources": _string_list(item.get("additional_sources")),
        "rule_version": rule_version,
        "screen_state": screen_state,
        "candidate_state": candidate_state,
        "reasons": _unique([queue_reason, *reasons]),
        "blockers": blockers,
        "evidence_gaps": _unique(evidence_gaps),
        "review_only": True,
        "investment_conclusion": False,
    }


def _evidence_gaps(
    item: Mapping[str, Any], reasons: Sequence[str], blockers: Sequence[str]
) -> list[str]:
    gaps: list[str] = []
    gaps.extend(_string_list(item.get("evidence_gaps")))
    for code in (*reasons, *blockers):
        if code in {
            "LIGHT_PROFILE_INCOMPLETE",
            "MAIN_BUSINESS_MISSING",
            "REPORTED_INDUSTRY_MISSING",
            "LEGAL_NAME_MISSING",
            "LISTING_MARKET_MISSING",
            "LIGHT_DATA_UNAVAILABLE",
            "SOURCE_MISSING",
        }:
            gaps.append(code)
    if not item.get("source"):
        gaps.append("SOURCE_MISSING")
    if not item.get("as_of"):
        gaps.append("AS_OF_MISSING")
    available_fields = item.get("available_fields")
    if isinstance(available_fields, list) and not available_fields:
        gaps.append("LIGHT_FIELDS_UNAVAILABLE")
    return _unique(gaps)


def _report_as_of(report: Mapping[str, Any]) -> str:
    value = report.get("as_of") or report.get("input_as_of") or ""
    if isinstance(value, str):
        return value
    return ""


def _source_label(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        provider = value.get("provider")
        return str(provider or "")
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise CandidateQueueError("reasons, blockers, and evidence fields must be lists")
    return [str(item) for item in value if str(item)]


def _field_sources(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise CandidateQueueError("field_sources must be a string mapping")
    return {
        str(field): str(source).strip()
        for field, source in value.items()
        if str(field).strip() and str(source).strip()
    }


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
