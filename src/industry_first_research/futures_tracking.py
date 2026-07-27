"""Deterministic, read-only tracking for saved futures fundamentals reports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
import hashlib
import json
from typing import Any


FUTURES_TRACKING_SCHEMA_VERSION = "futures-fundamentals-tracking.v1"
RULE_VERSION = "futures-tracking-rules.v1"
FUTURES_REPORT_SCHEMA_VERSION = "futures-fundamentals-report.v1"


class FuturesTrackingError(ValueError):
    """Raised when two futures fundamentals snapshots cannot be compared safely."""


_TRACKED_DERIVED_METRICS = (
    "spot_latest",
    "contract_settlement_latest",
    "basis_latest",
    "inventory_latest",
    "inventory_change",
    "exchange_inventory_latest",
    "registered_warrants_latest",
    "registered_warrants_change",
    "open_interest_latest",
    "cash_cost",
    "full_cost",
    "spot_minus_cash_cost",
    "spot_minus_full_cost",
    "contract_minus_spot",
    "calendar_spread_latest",
)

_TRACKED_STATES = (
    ("report", "status"),
    ("identity", "identity_status"),
    ("variety_view", "status"),
    ("contract_view", "status"),
    ("simulation_view", "status"),
    ("price_scenarios", "status"),
)
_TRACKING_MODULES = {
    "report": "futures_contract",
    "identity": "futures_contract",
    "state": "futures_fundamentals",
    "derived_metric": "futures_fundamentals",
    "field_status": "evidence_freshness",
    "price_scenario": "valuation_scenarios",
    "price_scenarios": "valuation_scenarios",
}


def build_futures_tracking_report(
    current_report: Mapping[str, Any],
    previous_report: Mapping[str, Any] | None = None,
    *,
    as_of: str = "",
    tracking_id: str = "",
) -> dict[str, Any]:
    """Compare two bounded futures reports without changing either report.

    The result describes changed facts and states only.  It deliberately does
    not infer a direction, create a decision snapshot, or treat a changed
    price as an investment conclusion.
    """

    _validate_report(current_report, "current_report")
    if previous_report is not None:
        _validate_report(previous_report, "previous_report")

    current_as_of = _parse_date(current_report["as_of"], "current_report.as_of")
    cutoff = _parse_date(as_of, "as_of") if str(as_of).strip() else current_as_of
    if current_as_of > cutoff:
        raise FuturesTrackingError("current report exceeds tracking as_of")
    if previous_report is not None:
        previous_as_of = _parse_date(previous_report["as_of"], "previous_report.as_of")
        if previous_as_of > current_as_of:
            raise FuturesTrackingError("previous report is newer than current report")
        _validate_subject_compatibility(current_report, previous_report)
    else:
        previous_as_of = None

    changes: list[dict[str, Any]] = []
    if previous_report is not None:
        changes.extend(_state_changes(previous_report, current_report))
        changes.extend(_metric_changes(previous_report, current_report))
        changes.extend(_field_status_changes(previous_report, current_report))
        changes.extend(_scenario_changes(previous_report, current_report))

    current_status = str(current_report.get("status") or "INSUFFICIENT").upper()
    if current_status == "BLOCKED":
        tracking_status = "BLOCKED"
    elif current_status != "READY":
        tracking_status = "PARTIAL"
    elif previous_report is None:
        tracking_status = "INITIALIZED"
    elif changes:
        tracking_status = "UPDATED"
    else:
        tracking_status = "NO_CHANGE"

    subject = _subject(current_report)
    review_required = bool(previous_report is None or changes or current_status != "READY")
    affected_modules = _affected_modules(changes, current_status=current_status)
    identifier = (
        str(tracking_id).strip()
        or "futures-tracking-"
        + _digest(
            {
                "current": current_report.get("report_id"),
                "previous": previous_report.get("report_id") if previous_report else "",
                "as_of": cutoff.isoformat(),
            }
        )[:16]
    )
    return {
        "schema_version": FUTURES_TRACKING_SCHEMA_VERSION,
        "tracking_id": identifier,
        "rule_version": RULE_VERSION,
        "as_of": cutoff.isoformat(),
        "current_report_id": str(current_report.get("report_id") or ""),
        "previous_report_id": str(previous_report.get("report_id") or "") if previous_report else "",
        "current_report_as_of": current_as_of.isoformat(),
        "previous_report_as_of": previous_as_of.isoformat() if previous_as_of else "",
        "subject": subject,
        "tracking_status": tracking_status,
        "current_status": current_status,
        "changed": bool(changes),
        "change_count": len(changes),
        "changes": changes,
        "current_state": _state_projection(current_report),
        "affected_modules": affected_modules,
        "decision_review": {
            "status": "REVIEW_REQUIRED" if review_required else "NO_CHANGE",
            "affected_modules": affected_modules,
            "actions": (
                ["review_holding_thesis", "review_decision_snapshot"]
                if review_required
                else []
            ),
            "user_confirmation_required": review_required,
            "automatic_snapshot_update": False,
        },
        "review_required": review_required,
        "policy": {
            "current_report_unchanged": True,
            "previous_report_unchanged": True,
            "historical_versions_preserved": True,
            "directional_conclusion": False,
            "investment_conclusion": False,
            "decision_snapshot_created": False,
            "automatic_order_included": False,
            "data_fetched": False,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _validate_report(report: Any, name: str) -> None:
    if not isinstance(report, Mapping):
        raise FuturesTrackingError(f"{name} must be an object")
    if report.get("schema_version") != FUTURES_REPORT_SCHEMA_VERSION:
        raise FuturesTrackingError(
            f"{name} must be {FUTURES_REPORT_SCHEMA_VERSION}"
        )
    if not str(report.get("report_id") or "").strip():
        raise FuturesTrackingError(f"{name}.report_id is required")
    if not str(report.get("as_of") or "").strip():
        raise FuturesTrackingError(f"{name}.as_of is required")
    if not str(report.get("variety_id") or "").strip():
        raise FuturesTrackingError(f"{name}.variety_id is required")
    if not str(report.get("exchange") or "").strip():
        raise FuturesTrackingError(f"{name}.exchange is required")


def _validate_subject_compatibility(
    current: Mapping[str, Any], previous: Mapping[str, Any]
) -> None:
    for field in ("exchange", "variety_id", "object_type"):
        if str(current.get(field) or "") != str(previous.get(field) or ""):
            raise FuturesTrackingError(
                f"current and previous reports have different {field}"
            )


def _subject(report: Mapping[str, Any]) -> dict[str, Any]:
    contract = report.get("contract") or {}
    if not isinstance(contract, Mapping):
        contract = {}
    return {
        "object_type": str(report.get("object_type") or ""),
        "exchange": str(report.get("exchange") or ""),
        "variety_id": str(report.get("variety_id") or ""),
        "variety_name": str(report.get("variety_name") or ""),
        "contract_code": str(contract.get("contract_code") or ""),
    }


def _state_projection(report: Mapping[str, Any]) -> dict[str, Any]:
    projection: dict[str, Any] = {}
    for section, field in _TRACKED_STATES:
        if section == "report":
            value = report.get(field)
        elif section == "identity":
            value = report.get(field)
        else:
            container = report.get(section)
            value = container.get(field) if isinstance(container, Mapping) else None
        projection[f"{section}.{field}"] = value
    contract = report.get("contract") or {}
    projection["contract.contract_code"] = (
        contract.get("contract_code") if isinstance(contract, Mapping) else None
    )
    return projection


def _state_changes(
    previous: Mapping[str, Any], current: Mapping[str, Any]
) -> list[dict[str, Any]]:
    old = _state_projection(previous)
    new = _state_projection(current)
    return [
        _change("state", key, old[key], new[key])
        for key in sorted(set(old) | set(new))
        if not _same(old.get(key), new.get(key))
    ]


def _metric_changes(
    previous: Mapping[str, Any], current: Mapping[str, Any]
) -> list[dict[str, Any]]:
    old_metrics = previous.get("derived_metrics")
    new_metrics = current.get("derived_metrics")
    old_metrics = old_metrics if isinstance(old_metrics, Mapping) else {}
    new_metrics = new_metrics if isinstance(new_metrics, Mapping) else {}
    changes = []
    for key in _TRACKED_DERIVED_METRICS:
        old = old_metrics.get(key)
        new = new_metrics.get(key)
        if not _same(old, new):
            changes.append(_change("derived_metric", key, old, new))
    return changes


def _field_status_changes(
    previous: Mapping[str, Any], current: Mapping[str, Any]
) -> list[dict[str, Any]]:
    old_fields = previous.get("fields")
    new_fields = current.get("fields")
    old_fields = old_fields if isinstance(old_fields, Mapping) else {}
    new_fields = new_fields if isinstance(new_fields, Mapping) else {}
    changes = []
    for key in sorted(set(old_fields) | set(new_fields)):
        old = old_fields.get(key)
        new = new_fields.get(key)
        old_status = old.get("status") if isinstance(old, Mapping) else "MISSING"
        new_status = new.get("status") if isinstance(new, Mapping) else "MISSING"
        if old_status != new_status:
            changes.append(_change("field_status", str(key), old_status, new_status))
    return changes


def _scenario_changes(
    previous: Mapping[str, Any], current: Mapping[str, Any]
) -> list[dict[str, Any]]:
    old = previous.get("price_scenarios")
    new = current.get("price_scenarios")
    old = old if isinstance(old, Mapping) else {}
    new = new if isinstance(new, Mapping) else {}
    changes = []
    for key in ("status", "missing"):
        if not _same(old.get(key), new.get(key)):
            changes.append(_change("price_scenarios", key, old.get(key), new.get(key)))
    old_items = old.get("scenarios") if isinstance(old.get("scenarios"), Mapping) else {}
    new_items = new.get("scenarios") if isinstance(new.get("scenarios"), Mapping) else {}
    for key in sorted(set(old_items) | set(new_items)):
        old_item = old_items.get(key)
        new_item = new_items.get(key)
        if not _same(old_item, new_item):
            changes.append(_change("price_scenario", str(key), old_item, new_item))
    return changes


def _change(area: str, key: str, previous: Any, current: Any) -> dict[str, Any]:
    return {
        "area": area,
        "key": key,
        "previous": previous,
        "current": current,
    }


def _affected_modules(
    changes: Sequence[Mapping[str, Any]], *, current_status: str
) -> list[str]:
    modules = {
        _TRACKING_MODULES.get(str(change.get("area") or ""), "futures_fundamentals")
        for change in changes
        if isinstance(change, Mapping)
    }
    if current_status != "READY" or not modules:
        modules.add("futures_fundamentals")
    return sorted(modules)


def _same(left: Any, right: Any) -> bool:
    return _canonical(left) == _canonical(right)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _parse_date(value: Any, name: str) -> date:
    text = str(value or "").strip()
    if not text:
        raise FuturesTrackingError(f"{name} is required")
    try:
        return date.fromisoformat(text[:10])
    except ValueError as error:
        raise FuturesTrackingError(f"{name} must be an ISO date") from error
