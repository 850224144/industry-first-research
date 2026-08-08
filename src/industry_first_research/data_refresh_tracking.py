"""Deterministic before/after tracking for bounded data refresh snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
import hashlib
import json
from typing import Any

from .data_refresh import DataRefreshError, validate_data_source_refresh


DATA_REFRESH_TRACKING_SCHEMA_VERSION = "data-source-refresh-tracking.v1"
DATA_REFRESH_TRACKING_RULE_VERSION = "data-source-refresh-tracking-rules.v1"


class DataRefreshTrackingError(ValueError):
    """Raised when two refresh snapshots cannot be compared safely."""


def build_data_refresh_tracking_report(
    current_report: Mapping[str, Any],
    previous_report: Mapping[str, Any] | None = None,
    *,
    as_of: str = "",
    tracking_id: str = "",
) -> dict[str, Any]:
    """Compare explicit refresh results without creating facts or conclusions."""

    try:
        current = validate_data_source_refresh(current_report)
        previous = (
            validate_data_source_refresh(previous_report)
            if previous_report is not None
            else None
        )
    except DataRefreshError as error:
        raise DataRefreshTrackingError(str(error)) from error

    current_date = _parse_date(current["as_of"], "current_report.as_of")
    cutoff = _parse_date(as_of, "as_of") if str(as_of).strip() else current_date
    if current_date > cutoff:
        raise DataRefreshTrackingError("current refresh exceeds tracking as_of")
    previous_date: date | None = None
    if previous is not None:
        previous_date = _parse_date(previous["as_of"], "previous_report.as_of")
        if previous_date > current_date:
            raise DataRefreshTrackingError("previous refresh is newer than current refresh")

    changes: list[dict[str, Any]] = []
    if previous is not None:
        changes.extend(_compare_rows(previous, current))
        if previous.get("status") != current.get("status"):
            changes.append(_change("refresh_status", "status", previous.get("status"), current.get("status")))
        if previous.get("source_health_snapshot_id") != current.get("source_health_snapshot_id"):
            changes.append(
                _change(
                    "source_health",
                    "source_health_snapshot_id",
                    previous.get("source_health_snapshot_id"),
                    current.get("source_health_snapshot_id"),
                )
            )

    current_status = str(current.get("status") or "INSUFFICIENT").upper()
    if current_status == "BLOCKED":
        tracking_status = "BLOCKED"
    elif current_status != "SUCCESS":
        tracking_status = "PARTIAL"
    elif previous is None:
        tracking_status = "INITIALIZED"
    elif changes:
        tracking_status = "UPDATED"
    else:
        tracking_status = "NO_CHANGE"

    review_required = bool(previous is None or changes or current_status != "SUCCESS")
    affected_modules = _affected_modules(changes, current=current)

    identifier = str(tracking_id or "").strip() or "data-refresh-tracking-" + _hash_payload(
        {
            "current": current["refresh_id"],
            "previous": previous["refresh_id"] if previous else "",
            "as_of": cutoff.isoformat(),
        }
    )[:20]
    return {
        "schema_version": DATA_REFRESH_TRACKING_SCHEMA_VERSION,
        "tracking_id": identifier,
        "rule_version": DATA_REFRESH_TRACKING_RULE_VERSION,
        "as_of": cutoff.isoformat(),
        "current_refresh_id": current["refresh_id"],
        "previous_refresh_id": previous["refresh_id"] if previous else "",
        "current_refresh_as_of": current_date.isoformat(),
        "previous_refresh_as_of": previous_date.isoformat() if previous_date else "",
        "current_status": current_status,
        "tracking_status": tracking_status,
        "changed": bool(changes),
        "change_count": len(changes),
        "changed_query_ids": sorted(
            {
                str(change.get("query_id") or "")
                for change in changes
                if str(change.get("query_id") or "")
            }
        ),
        "changes": changes,
        "affected_modules": affected_modules,
        "decision_review": {
            "status": "REVIEW_REQUIRED" if review_required else "NO_CHANGE",
            "affected_modules": affected_modules,
            "actions": ["review_refresh_evidence", "review_affected_research"]
            if review_required
            else [],
            "user_confirmation_required": review_required,
            "automatic_snapshot_update": False,
        },
        "review_required": review_required,
        "policy": {
            "current_refresh_unchanged": True,
            "previous_refresh_unchanged": True,
            "historical_versions_preserved": True,
            "data_fetched": False,
            "fact_promotion": False,
            "directional_conclusion": False,
            "investment_conclusion": False,
            "decision_snapshot_created": False,
            "read_only": True,
            "execution_enabled": False,
        },
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def validate_data_refresh_tracking_report(
    report: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(report, Mapping):
        raise DataRefreshTrackingError("tracking report must be an object")
    if report.get("schema_version") != DATA_REFRESH_TRACKING_SCHEMA_VERSION:
        raise DataRefreshTrackingError(
            f"input must be {DATA_REFRESH_TRACKING_SCHEMA_VERSION}"
        )
    for field in (
        "tracking_id",
        "as_of",
        "current_refresh_id",
        "tracking_status",
    ):
        if not str(report.get(field) or "").strip():
            raise DataRefreshTrackingError(f"{field} is required")
    _parse_date(report["as_of"], "as_of")
    if report.get("immutable") is not True:
        raise DataRefreshTrackingError("tracking report must be immutable")
    policy = report.get("policy")
    if not isinstance(policy, Mapping) or policy.get("fact_promotion") is not False:
        raise DataRefreshTrackingError("tracking report cannot promote facts")
    if report.get("execution_enabled") is not False:
        raise DataRefreshTrackingError("tracking report must be execution-disabled")
    if not isinstance(report.get("changes"), list):
        raise DataRefreshTrackingError("changes must be a list")
    return dict(report)


def _compare_rows(
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
) -> list[dict[str, Any]]:
    old_rows = {
        str(row.get("query_id") or ""): row
        for row in previous.get("queries") or []
        if isinstance(row, Mapping) and str(row.get("query_id") or "")
    }
    new_rows = {
        str(row.get("query_id") or ""): row
        for row in current.get("queries") or []
        if isinstance(row, Mapping) and str(row.get("query_id") or "")
    }
    changes: list[dict[str, Any]] = []
    for query_id in sorted(set(old_rows) | set(new_rows)):
        old = old_rows.get(query_id)
        new = new_rows.get(query_id)
        if old is None:
            changes.append(_change("query", "added", None, new, query_id=query_id))
            continue
        if new is None:
            changes.append(_change("query", "removed", old, None, query_id=query_id))
            continue
        for key in (
            "subject_type",
            "subject_id",
            "status",
            "source",
            "data_hash",
            "truncated",
            "requested_sources",
        ):
            if not _same(old.get(key), new.get(key)):
                changes.append(
                    _change(
                        "query",
                        key,
                        old.get(key),
                        new.get(key),
                        query_id=query_id,
                    )
                )
        old_attempts = [
            str(item.get("status") or "")
            for item in old.get("attempts") or []
            if isinstance(item, Mapping)
        ]
        new_attempts = [
            str(item.get("status") or "")
            for item in new.get("attempts") or []
            if isinstance(item, Mapping)
        ]
        if old_attempts != new_attempts:
            changes.append(
                _change(
                    "query",
                    "attempt_statuses",
                    old_attempts,
                    new_attempts,
                    query_id=query_id,
                )
            )
    return changes


def _affected_modules(
    changes: list[Mapping[str, Any]], *, current: Mapping[str, Any]
) -> list[str]:
    modules = {"evidence_freshness"}
    subject_types = {
        str(row.get("subject_type") or "")
        for row in current.get("queries") or []
        if isinstance(row, Mapping)
    }
    if "listed_company" in subject_types:
        modules.add("company_research")
    if "industry" in subject_types:
        modules.add("industry_research")
    if subject_types.intersection({"futures_variety", "futures_contract"}):
        modules.add("futures_fundamentals")
    if changes:
        modules.add("research_version_review")
    return sorted(modules)


def _change(
    area: str,
    key: str,
    previous: Any,
    current: Any,
    *,
    query_id: str = "",
) -> dict[str, Any]:
    return {
        "area": area,
        "key": key,
        "query_id": query_id,
        "previous": previous,
        "current": current,
    }


def _same(left: Any, right: Any) -> bool:
    return _canonical(left) == _canonical(right)


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )


def _parse_date(value: Any, name: str) -> date:
    text = str(value or "").strip()
    if not text:
        raise DataRefreshTrackingError(f"{name} is required")
    try:
        return date.fromisoformat(text[:10])
    except ValueError as error:
        raise DataRefreshTrackingError(f"{name} must be an ISO date") from error


def _hash_payload(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()
