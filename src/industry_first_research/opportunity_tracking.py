"""Track opportunity-candidate snapshots without inventing new evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
from typing import Any


OPPORTUNITY_TRACKING_SCHEMA_VERSION = "opportunity-candidate-tracking.v1"
RULE_VERSION = "opportunity-candidate-tracking-rules.v1"


class OpportunityTrackingError(ValueError):
    """Raised when opportunity tracking inputs are invalid."""


def build_opportunity_tracking_report(
    current_scan: Mapping[str, Any] | None,
    *,
    previous_scan: Mapping[str, Any] | None = None,
    trend_report: Mapping[str, Any] | None = None,
    candidate_delta: Mapping[str, Any] | None = None,
    as_of: str = "",
    tracking_id: str = "",
) -> dict[str, Any]:
    """Compare candidate states and expose only observed changes.

    A trend or queue summary can mark an item for review, but cannot change its
    candidate state without a new four-dimensional evidence snapshot.
    """

    _validate_scan(current_scan, "current_scan", allow_none=True)
    _validate_scan(previous_scan, "previous_scan", allow_none=True)
    if trend_report is not None and not isinstance(trend_report, Mapping):
        raise OpportunityTrackingError("trend_report must be an object")
    if candidate_delta is not None and not isinstance(candidate_delta, Mapping):
        raise OpportunityTrackingError("candidate_delta must be an object")

    current_items = _items_by_id(current_scan)
    previous_items = _items_by_id(previous_scan)
    delta_items = _delta_ids(candidate_delta)
    changes = []
    for candidate_id in sorted(set(current_items) | set(previous_items)):
        current = current_items.get(candidate_id)
        previous = previous_items.get(candidate_id)
        state_changed = bool(
            current
            and previous
            and current.get("status") != previous.get("status")
        )
        current_dimensions = _dimension_statuses(current)
        previous_dimensions = _dimension_statuses(previous)
        changed_dimensions = [
            name
            for name in sorted(set(current_dimensions) | set(previous_dimensions))
            if current_dimensions.get(name) != previous_dimensions.get(name)
        ]
        if current is None:
            change_type = "REMOVED_FROM_CURRENT_SCAN"
        elif previous is None:
            change_type = "NEW_TO_CURRENT_SCAN"
        elif state_changed or changed_dimensions:
            change_type = "STATE_OR_DIMENSION_CHANGED"
        elif candidate_id in delta_items or str((current or previous or {}).get("company_id") or "") in delta_items:
            change_type = "QUEUE_DELTA_REVIEW"
        else:
            change_type = "UNCHANGED"
        changes.append(
            {
                "candidate_id": candidate_id,
                "company_id": str((current or previous or {}).get("company_id") or ""),
                "display_name": str((current or previous or {}).get("display_name") or ""),
                "previous_status": previous.get("status") if previous else None,
                "current_status": current.get("status") if current else None,
                "state_changed": state_changed,
                "changed_dimensions": changed_dimensions,
                "change_type": change_type,
                "review_required": change_type != "UNCHANGED",
                "affected_modules": _affected_modules(changed_dimensions, trend_report),
                "previous_hash": _hash(previous) if previous else None,
                "current_hash": _hash(current) if current else None,
            }
        )

    changed_count = sum(item["change_type"] != "UNCHANGED" for item in changes)
    key = tracking_id.strip() or f"{as_of or (current_scan or {}).get('as_of') or 'unknown'}"
    return {
        "schema_version": OPPORTUNITY_TRACKING_SCHEMA_VERSION,
        "tracking_id": f"opportunity-tracking-{key}",
        "as_of": as_of or str((current_scan or {}).get("as_of") or ""),
        "current_scan_id": str((current_scan or {}).get("scan_id") or ""),
        "previous_scan_id": str((previous_scan or {}).get("scan_id") or ""),
        "current_scan_status": "AVAILABLE" if current_scan else "NO_SNAPSHOT",
        "previous_scan_status": "AVAILABLE" if previous_scan else "NO_SNAPSHOT",
        "changed_count": changed_count,
        "changes": changes,
        "trend_observed": bool(trend_report),
        "candidate_delta_observed": bool(candidate_delta),
        "state_transition_requires_new_evidence": True,
        "rule_version": RULE_VERSION,
        "policy": {
            "no_state_inference_from_trend_only": True,
            "no_state_inference_from_queue_only": True,
            "missing_snapshot_is_explicit": True,
            "old_snapshot_preserved": True,
            "not_investment_conclusion": True,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _validate_scan(value: Mapping[str, Any] | None, name: str, *, allow_none: bool) -> None:
    if value is None and allow_none:
        return
    if not isinstance(value, Mapping):
        raise OpportunityTrackingError(f"{name} must be an object")
    schema = str(value.get("schema_version") or "")
    if schema not in {"opportunity-scan.v1", "industry-discovery.v1"}:
        raise OpportunityTrackingError(f"{name} must be an opportunity scan snapshot")
    if not isinstance(value.get("items") or value.get("opportunity_candidates"), list):
        raise OpportunityTrackingError(f"{name} has no candidate items")


def _items_by_id(value: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if value is None:
        return {}
    items = value.get("items")
    if not isinstance(items, list):
        items = value.get("opportunity_candidates")
    result = {}
    for item in items or []:
        if not isinstance(item, Mapping):
            raise OpportunityTrackingError("candidate items must be objects")
        candidate_id = str(item.get("candidate_id") or "").strip()
        if not candidate_id:
            raise OpportunityTrackingError("candidate item has no candidate_id")
        if candidate_id in result:
            raise OpportunityTrackingError(f"duplicate candidate_id: {candidate_id}")
        result[candidate_id] = item
    return result


def _dimension_statuses(item: Mapping[str, Any] | None) -> dict[str, str]:
    if not item or not isinstance(item.get("dimensions"), Mapping):
        return {}
    return {
        str(name): str(value.get("status") or "NOT_EVALUABLE")
        for name, value in item["dimensions"].items()
        if isinstance(value, Mapping)
    }


def _delta_ids(delta: Mapping[str, Any] | None) -> set[str]:
    if not delta:
        return set()
    raw_items = delta.get("items") or []
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes, bytearray)):
        return set()
    return {
        identifier
        for item in raw_items
        if isinstance(item, Mapping)
        for identifier in (
            str(item.get("candidate_id") or "").strip(),
            str(item.get("company_id") or "").strip(),
        )
        if identifier
    }


def _affected_modules(
    dimensions: Sequence[str], trend_report: Mapping[str, Any] | None
) -> list[str]:
    modules = []
    for dimension in dimensions:
        modules.extend(
            {
                "downside_protection": ("survival_analysis",),
                "inflection_evidence": ("industry_situation", "cycle_reversal"),
                "profit_convexity": ("competitive_position", "valuation_scenarios"),
                "expectation_gap": ("valuation_scenarios", "market_structure"),
            }.get(dimension, ("research_report",))
        )
    if trend_report:
        modules.append("industry_situation")
    return list(dict.fromkeys(modules))


def _hash(value: Mapping[str, Any] | None) -> str | None:
    if value is None:
        return None
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()
