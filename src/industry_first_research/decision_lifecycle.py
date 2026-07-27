"""Append-only lifecycle events for immutable simulation decision snapshots."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from hashlib import sha256
import json
from typing import Any


DECISION_LIFECYCLE_EVENT_SCHEMA_VERSION = "decision-lifecycle-event.v1"
DECISION_LIFECYCLE_SCHEMA_VERSION = "decision-lifecycle.v1"
RULE_VERSION = "decision-lifecycle-rules.v1"
SNAPSHOT_SCHEMA_VERSION = "decision-snapshot.v1"

_STATUSES = {"DRAFT", "LOCKED", "ACTIVE", "REVIEW_DUE", "CLOSED", "INVALIDATED"}
_TRANSITIONS = {
    "DRAFT": {"LOCKED"},
    "LOCKED": {"ACTIVE", "INVALIDATED"},
    "ACTIVE": {"REVIEW_DUE", "INVALIDATED", "CLOSED"},
    "REVIEW_DUE": {"ACTIVE", "CLOSED", "INVALIDATED"},
    "CLOSED": set(),
    "INVALIDATED": set(),
}


class DecisionLifecycleError(ValueError):
    """Raised when a simulation decision lifecycle event is invalid."""


def build_decision_lifecycle_event(
    snapshot: Mapping[str, Any],
    *,
    to_status: str,
    changed_at: str,
    reason: str,
    evidence_ids: Sequence[str] = (),
    attribution_id: str = "",
    user_confirmed: bool = False,
    previous_events: Sequence[Mapping[str, Any]] = (),
    event_id: str = "",
) -> dict[str, Any]:
    """Create one immutable status transition without editing the snapshot."""

    current_status = _current_status(snapshot, previous_events)
    target = str(to_status or "").strip().upper()
    if target not in _STATUSES:
        raise DecisionLifecycleError(f"unsupported lifecycle status: {target or '<empty>'}")
    if target not in _TRANSITIONS[current_status]:
        raise DecisionLifecycleError(
            f"invalid lifecycle transition: {current_status} -> {target}"
        )
    if not str(reason or "").strip():
        raise DecisionLifecycleError("lifecycle transition reason is required")
    changed = _parse_day(changed_at, "changed_at")
    snapshot_id = _snapshot_id(snapshot)
    if target == "CLOSED" and not attribution_id.strip():
        raise DecisionLifecycleError("CLOSED transition requires attribution_id")
    if target == "INVALIDATED" and not evidence_ids:
        raise DecisionLifecycleError("INVALIDATED transition requires evidence_ids")
    if target == "LOCKED" and not user_confirmed:
        raise DecisionLifecycleError("LOCKED transition requires user_confirmed")
    references = _unique_strings(evidence_ids)
    identifier = event_id.strip() or f"lifecycle-{snapshot_id}-{target.lower()}-{changed.isoformat()}"
    if any(str(item.get("event_id") or "") == identifier for item in previous_events):
        raise DecisionLifecycleError(f"duplicate lifecycle event_id: {identifier}")
    return {
        "schema_version": DECISION_LIFECYCLE_EVENT_SCHEMA_VERSION,
        "event_id": identifier,
        "decision_snapshot_id": snapshot_id,
        "from_status": current_status,
        "to_status": target,
        "changed_at": changed_at,
        "reason": str(reason).strip(),
        "evidence_ids": references,
        "attribution_id": attribution_id.strip(),
        "user_confirmed": bool(user_confirmed),
        "rule_version": RULE_VERSION,
        "content_hash": _hash_payload(
            {
                "event_id": identifier,
                "decision_snapshot_id": snapshot_id,
                "from_status": current_status,
                "to_status": target,
                "changed_at": changed_at,
                "reason": reason.strip(),
                "evidence_ids": references,
                "attribution_id": attribution_id.strip(),
            }
        ),
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "simulation_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "policy": _policy(),
    }


def build_decision_lifecycle(
    snapshot: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]] = (),
    *,
    as_of: str = "",
    lifecycle_id: str = "",
) -> dict[str, Any]:
    """Validate an append-only event stream and project the current lifecycle."""

    snapshot_id = _snapshot_id(snapshot)
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes, bytearray)):
        raise DecisionLifecycleError("events must be a list")
    current = _snapshot_initial_status(snapshot)
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in events:
        if not isinstance(raw, Mapping):
            raise DecisionLifecycleError("each lifecycle event must be an object")
        if raw.get("schema_version") != DECISION_LIFECYCLE_EVENT_SCHEMA_VERSION:
            raise DecisionLifecycleError("events must be decision-lifecycle-event.v1")
        if str(raw.get("decision_snapshot_id") or "") != snapshot_id:
            raise DecisionLifecycleError("lifecycle event snapshot ID does not match input")
        event_id = str(raw.get("event_id") or "").strip()
        if not event_id or event_id in seen_ids:
            raise DecisionLifecycleError(f"duplicate or empty lifecycle event_id: {event_id}")
        if str(raw.get("from_status") or "").upper() != current:
            raise DecisionLifecycleError(
                f"lifecycle event from_status does not match current status: {current}"
            )
        target = str(raw.get("to_status") or "").upper()
        if target not in _TRANSITIONS[current]:
            raise DecisionLifecycleError(f"invalid lifecycle transition: {current} -> {target}")
        if not str(raw.get("reason") or "").strip():
            raise DecisionLifecycleError("lifecycle event reason is required")
        _parse_day(str(raw.get("changed_at") or ""), "event.changed_at")
        if raw.get("immutable") is not True:
            raise DecisionLifecycleError("lifecycle event must be immutable")
        seen_ids.add(event_id)
        normalized.append(dict(raw))
        current = target

    reference_day = _parse_day(as_of, "as_of") if as_of else None
    review_date = _snapshot_review_date(snapshot)
    due = bool(reference_day and review_date and current in {"LOCKED", "ACTIVE"} and reference_day >= review_date)
    projected_status = "REVIEW_DUE" if due else current
    identifier = lifecycle_id.strip() or f"decision-lifecycle-{snapshot_id.removeprefix('decision-snapshot-')}"
    return {
        "schema_version": DECISION_LIFECYCLE_SCHEMA_VERSION,
        "lifecycle_id": identifier,
        "decision_snapshot_id": snapshot_id,
        "snapshot_status": _snapshot_initial_status(snapshot),
        "current_status": projected_status,
        "event_count": len(normalized),
        "events": normalized,
        "as_of": as_of,
        "review_date": _snapshot_review_date_text(snapshot),
        "review_due_projection": due,
        "last_event_id": normalized[-1]["event_id"] if normalized else None,
        "rule_version": RULE_VERSION,
        "policy": {
            **_policy(),
            "snapshot_unchanged": True,
            "lifecycle_is_append_only": True,
            "review_due_is_projection_until_event": True,
        },
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "simulation_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _current_status(snapshot: Mapping[str, Any], events: Sequence[Mapping[str, Any]]) -> str:
    lifecycle = build_decision_lifecycle(snapshot, events) if events else None
    return str(lifecycle["current_status"] if lifecycle else _snapshot_initial_status(snapshot)).upper()


def _snapshot_id(snapshot: Mapping[str, Any]) -> str:
    if not isinstance(snapshot, Mapping) or snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise DecisionLifecycleError("snapshot must be decision-snapshot.v1")
    identifier = str(snapshot.get("snapshot_id") or "").strip()
    if not identifier:
        raise DecisionLifecycleError("snapshot_id is required")
    if snapshot.get("immutable") is not True or snapshot.get("simulation_only") is not True:
        raise DecisionLifecycleError("snapshot must be immutable and simulation-only")
    return identifier


def _snapshot_initial_status(snapshot: Mapping[str, Any]) -> str:
    status = str(snapshot.get("status") or "LOCKED").strip().upper()
    if status not in _STATUSES:
        raise DecisionLifecycleError(f"unsupported snapshot status: {status}")
    return status


def _snapshot_review_date(snapshot: Mapping[str, Any]) -> date | None:
    decision = snapshot.get("decision") or {}
    if not isinstance(decision, Mapping):
        return None
    text = str(decision.get("review_date") or "").strip()
    return _parse_day(text, "review_date") if text else None


def _snapshot_review_date_text(snapshot: Mapping[str, Any]) -> str:
    decision = snapshot.get("decision") or {}
    return str(decision.get("review_date") or "") if isinstance(decision, Mapping) else ""


def _parse_day(value: str, field: str) -> date:
    text = str(value or "").strip()
    if not text:
        raise DecisionLifecycleError(f"{field} is required")
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError as error:
            raise DecisionLifecycleError(f"{field} must be an ISO date or datetime") from error


def _unique_strings(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _hash_payload(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()


def _policy() -> dict[str, Any]:
    return {
        "snapshot_immutable": True,
        "lifecycle_append_only": True,
        "no_automatic_trade": True,
        "no_investment_conclusion": True,
        "read_only": True,
        "review_only": True,
        "simulation_only": True,
        "execution_enabled": False,
    }
