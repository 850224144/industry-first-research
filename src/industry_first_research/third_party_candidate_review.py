"""Append-only review lifecycle for external project capability slices.

Candidate reviews describe whether a bounded capability is safe to pilot. They
are deliberately separate from the runtime component registry: registering a
candidate never installs a package, accesses a remote service, or enables an
adapter.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from hashlib import sha256
import json
from typing import Any


CANDIDATE_REVIEW_INPUT_SCHEMA_VERSION = "third-party-candidate-review-input.v1"
CANDIDATE_REVIEW_SCHEMA_VERSION = "third-party-candidate-review.v1"
CANDIDATE_REVIEW_EVENT_SCHEMA_VERSION = "third-party-candidate-review-event.v1"
CANDIDATE_REVIEW_PROJECTION_SCHEMA_VERSION = "third-party-candidate-review-projection.v1"
CANDIDATE_REVIEW_RULE_VERSION = "third-party-candidate-review-rules.v1"

REVIEW_STATES = {
    "DISCOVERED",
    "CAPABILITY_SCOPED",
    "LICENSE_AND_SECURITY_REVIEWED",
    "FIXTURE_VALIDATED",
    "ADAPTER_PILOTED",
    "ACCEPTED",
    "CONDITIONAL",
    "REFERENCE_ONLY",
    "REJECTED",
}

_TRANSITIONS = {
    "DISCOVERED": {"CAPABILITY_SCOPED"},
    "CAPABILITY_SCOPED": {"LICENSE_AND_SECURITY_REVIEWED", "REFERENCE_ONLY", "REJECTED"},
    "LICENSE_AND_SECURITY_REVIEWED": {"FIXTURE_VALIDATED", "REFERENCE_ONLY", "REJECTED"},
    "FIXTURE_VALIDATED": {"ADAPTER_PILOTED", "REFERENCE_ONLY", "REJECTED"},
    "ADAPTER_PILOTED": {"ACCEPTED", "CONDITIONAL", "REFERENCE_ONLY", "REJECTED"},
    "CONDITIONAL": {"ACCEPTED", "REJECTED"},
    "ACCEPTED": set(),
    "REFERENCE_ONLY": set(),
    "REJECTED": set(),
}

_TERMINAL_STATES = {"ACCEPTED", "CONDITIONAL", "REFERENCE_ONLY", "REJECTED"}
_BLOCKED_LICENSE_STATUSES = {
    "",
    "UNKNOWN",
    "REVIEW_REQUIRED",
    "LICENSE_REVIEW_REQUIRED",
    "UNREVIEWED",
}
_BLOCKED_SECURITY_STATUSES = {"", "UNKNOWN", "REVIEW_REQUIRED", "UNREVIEWED", "FAILED"}
_UPDATABLE_FIELDS = {
    "license_status",
    "security_status",
    "temporal_cutoff_support",
    "future_function_risk",
    "reproducibility_status",
    "fixture_ids",
    "baseline_id",
    "adapter_id",
    "fallback_id",
    "regression_status",
    "enable_conditions",
    "rejection_or_exit_reason",
    "reviewed_at",
    "next_review_at",
    "owner",
    "capability_matrix_refs",
}


class ThirdPartyCandidateReviewError(ValueError):
    """Raised when a candidate review or event is unsafe."""


def build_candidate_review(
    payload: Mapping[str, Any],
    *,
    review_id: str = "",
) -> dict[str, Any]:
    """Create one immutable candidate review in its initial or declared state."""

    if not isinstance(payload, Mapping):
        raise ThirdPartyCandidateReviewError("candidate review must be an object")
    schema = str(payload.get("schema_version") or "").strip()
    if schema not in {CANDIDATE_REVIEW_INPUT_SCHEMA_VERSION, CANDIDATE_REVIEW_SCHEMA_VERSION}:
        raise ThirdPartyCandidateReviewError(
            f"input must be {CANDIDATE_REVIEW_INPUT_SCHEMA_VERSION}"
        )

    normalized = _normalize_review(payload, review_id=review_id)
    _validate_state_requirements(normalized, normalized["state"])
    normalized["schema_version"] = CANDIDATE_REVIEW_SCHEMA_VERSION
    normalized["rule_version"] = CANDIDATE_REVIEW_RULE_VERSION
    normalized["policy"] = _policy()
    normalized["immutable"] = True
    normalized["read_only"] = True
    normalized["review_only"] = True
    normalized["investment_conclusion"] = False
    normalized["execution_enabled"] = False
    normalized["content_hash"] = _content_hash(normalized)
    return normalized


def validate_candidate_review(review: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one immutable candidate review and its content hash."""

    if not isinstance(review, Mapping) or review.get("schema_version") != CANDIDATE_REVIEW_SCHEMA_VERSION:
        raise ThirdPartyCandidateReviewError(
            f"input must be {CANDIDATE_REVIEW_SCHEMA_VERSION}"
        )
    if review.get("immutable") is not True:
        raise ThirdPartyCandidateReviewError("candidate review must be immutable")
    rebuilt = build_candidate_review(review, review_id=str(review.get("review_id") or ""))
    if review.get("content_hash") != rebuilt["content_hash"]:
        raise ThirdPartyCandidateReviewError("content_hash does not match candidate review")
    return dict(review)


def build_candidate_review_event(
    review: Mapping[str, Any],
    *,
    to_state: str,
    changed_at: str,
    trigger: str,
    actor: str,
    evidence_refs: Sequence[str] = (),
    field_updates: Mapping[str, Any] | None = None,
    previous_events: Sequence[Mapping[str, Any]] = (),
    event_id: str = "",
) -> dict[str, Any]:
    """Create one append-only state event with a bounded metadata patch."""

    base = validate_candidate_review(review)
    current, projected = _project_fields(base, previous_events, validate_events=True)
    target = str(to_state or "").strip().upper()
    if target not in REVIEW_STATES:
        raise ThirdPartyCandidateReviewError(f"unsupported review state: {target or '<empty>'}")
    if target not in _TRANSITIONS[current]:
        raise ThirdPartyCandidateReviewError(f"invalid review transition: {current} -> {target}")
    changed = _parse_datetime(changed_at, "changed_at")
    trigger_text = str(trigger or "").strip()
    actor_text = str(actor or "").strip()
    if not trigger_text:
        raise ThirdPartyCandidateReviewError("event trigger is required")
    if not actor_text:
        raise ThirdPartyCandidateReviewError("event actor is required")
    updates = _normalize_updates(field_updates or {})
    next_fields = dict(projected)
    next_fields.update(updates)
    next_fields["state"] = target
    _validate_state_requirements(next_fields, target)
    references = _string_list(evidence_refs, "evidence_refs")
    identifier = event_id.strip() or f"candidate-review-{base['review_id']}-{target.lower()}-{changed.isoformat()}"
    seen = {str(item.get("event_id") or "") for item in previous_events if isinstance(item, Mapping)}
    if identifier in seen:
        raise ThirdPartyCandidateReviewError(f"duplicate event_id: {identifier}")
    event = {
        "schema_version": CANDIDATE_REVIEW_EVENT_SCHEMA_VERSION,
        "event_id": identifier,
        "review_id": base["review_id"],
        "from_state": current,
        "to_state": target,
        "changed_at": changed_at,
        "trigger": trigger_text,
        "actor": actor_text,
        "evidence_refs": references,
        "field_updates": updates,
        "rule_version": CANDIDATE_REVIEW_RULE_VERSION,
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }
    event["content_hash"] = _content_hash(event)
    return event


def build_candidate_review_projection(
    review: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]] = (),
    *,
    projection_id: str = "",
) -> dict[str, Any]:
    """Replay and validate an append-only candidate review event stream."""

    base = validate_candidate_review(review)
    current, projected = _project_fields(base, events, validate_events=True)
    identifier = projection_id.strip() or f"candidate-review-projection-{base['review_id']}"
    normalized_events = [dict(item) for item in events]
    projection = {
        "schema_version": CANDIDATE_REVIEW_PROJECTION_SCHEMA_VERSION,
        "projection_id": identifier,
        "review_id": base["review_id"],
        "base_review_content_hash": base["content_hash"],
        "initial_state": str(base["state"]),
        "current_state": current,
        "review": {
            **projected,
            "schema_version": CANDIDATE_REVIEW_SCHEMA_VERSION,
            "state": current,
            "decision": current if current in _TERMINAL_STATES else "",
            "rule_version": CANDIDATE_REVIEW_RULE_VERSION,
            "policy": _policy(),
            "immutable": True,
            "read_only": True,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
        },
        "event_count": len(normalized_events),
        "events": normalized_events,
        "last_event_id": normalized_events[-1]["event_id"] if normalized_events else None,
        "rule_version": CANDIDATE_REVIEW_RULE_VERSION,
        "policy": {
            **_policy(),
            "review_record_unchanged": True,
            "append_only_events": True,
            "runtime_registry_separate": True,
        },
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }
    projection["review"]["content_hash"] = _content_hash(projection["review"])
    projection["content_hash"] = _content_hash(projection)
    return projection


def validate_candidate_review_projection(
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate an immutable projection and its nested event stream."""

    if not isinstance(projection, Mapping) or projection.get("schema_version") != CANDIDATE_REVIEW_PROJECTION_SCHEMA_VERSION:
        raise ThirdPartyCandidateReviewError(
            f"input must be {CANDIDATE_REVIEW_PROJECTION_SCHEMA_VERSION}"
        )
    if projection.get("immutable") is not True:
        raise ThirdPartyCandidateReviewError("candidate review projection must be immutable")
    supplied_hash = str(projection.get("content_hash") or "")
    if not supplied_hash or supplied_hash != _content_hash(projection):
        raise ThirdPartyCandidateReviewError(
            "content_hash does not match candidate review projection"
        )
    review = projection.get("review")
    if not isinstance(review, Mapping):
        raise ThirdPartyCandidateReviewError("projection review is required")
    nested_hash = str(review.get("content_hash") or "")
    if not nested_hash or nested_hash != _content_hash(review):
        raise ThirdPartyCandidateReviewError(
            "content_hash does not match projected candidate review"
        )
    review_id = str(projection.get("review_id") or "").strip()
    if not review_id or review_id != str(review.get("review_id") or "").strip():
        raise ThirdPartyCandidateReviewError("projection review_id does not match review")
    current_state = str(projection.get("current_state") or "").upper()
    if current_state != str(review.get("state") or "").upper():
        raise ThirdPartyCandidateReviewError("projection current_state does not match review")
    events = projection.get("events") or []
    if not isinstance(events, list):
        raise ThirdPartyCandidateReviewError("projection events must be a list")
    for event in events:
        validate_candidate_review_event(event)
    if str(projection.get("initial_state") or "").upper() not in REVIEW_STATES:
        raise ThirdPartyCandidateReviewError("projection initial_state is invalid")
    if str(projection.get("base_review_content_hash") or "") == "":
        raise ThirdPartyCandidateReviewError("projection base_review_content_hash is required")
    state = str(projection.get("initial_state") or "").upper()
    for event in events:
        if str(event.get("from_state") or "").upper() != state:
            raise ThirdPartyCandidateReviewError("projection event chain does not start from initial_state")
        target = str(event.get("to_state") or "").upper()
        if target not in _TRANSITIONS[state]:
            raise ThirdPartyCandidateReviewError("projection event chain has invalid transition")
        state = target
    if state != current_state:
        raise ThirdPartyCandidateReviewError("projection event chain does not reach current_state")
    if int(projection.get("event_count", -1)) != len(events):
        raise ThirdPartyCandidateReviewError("projection event_count does not match events")
    last_event_id = events[-1].get("event_id") if events else None
    if projection.get("last_event_id") != last_event_id:
        raise ThirdPartyCandidateReviewError("projection last_event_id does not match events")
    if str(projection.get("rule_version") or "") != CANDIDATE_REVIEW_RULE_VERSION:
        raise ThirdPartyCandidateReviewError("unsupported candidate review rule version")
    return dict(projection)


def validate_candidate_review_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an immutable candidate review event independently."""

    if not isinstance(event, Mapping) or event.get("schema_version") != CANDIDATE_REVIEW_EVENT_SCHEMA_VERSION:
        raise ThirdPartyCandidateReviewError(
            f"input must be {CANDIDATE_REVIEW_EVENT_SCHEMA_VERSION}"
        )
    if event.get("immutable") is not True:
        raise ThirdPartyCandidateReviewError("candidate review event must be immutable")
    rebuilt = dict(event)
    supplied_hash = rebuilt.pop("content_hash", None)
    if supplied_hash != _content_hash(rebuilt):
        raise ThirdPartyCandidateReviewError("content_hash does not match candidate review event")
    _parse_datetime(str(event.get("changed_at") or ""), "changed_at")
    if not str(event.get("event_id") or "").strip():
        raise ThirdPartyCandidateReviewError("event_id is required")
    if not str(event.get("review_id") or "").strip():
        raise ThirdPartyCandidateReviewError("review_id is required")
    if not str(event.get("trigger") or "").strip():
        raise ThirdPartyCandidateReviewError("event trigger is required")
    if not str(event.get("actor") or "").strip():
        raise ThirdPartyCandidateReviewError("event actor is required")
    return dict(event)


def _normalize_review(payload: Mapping[str, Any], *, review_id: str) -> dict[str, Any]:
    identifier = str(payload.get("review_id") or review_id).strip()
    if not identifier:
        identifier = f"candidate-review-{_hash_payload(payload)[:20]}"
    project_url = str(payload.get("project_url") or "").strip()
    package_name = str(payload.get("package_name") or "").strip()
    capability_slice = str(payload.get("capability_slice") or "").strip()
    capability_gap = str(payload.get("capability_gap") or "").strip()
    requested = str(payload.get("requested_capability") or "").strip()
    source_kind = str(payload.get("source_kind") or "").strip().lower()
    if not project_url:
        raise ThirdPartyCandidateReviewError("project_url is required")
    if not capability_slice:
        raise ThirdPartyCandidateReviewError("capability_slice is required")
    if not capability_gap:
        raise ThirdPartyCandidateReviewError("capability_gap is required")
    if not requested:
        raise ThirdPartyCandidateReviewError("requested_capability is required")
    if source_kind not in {"github", "pypi", "vendor", "system_package", "local_code"}:
        raise ThirdPartyCandidateReviewError(
            "source_kind must be github, pypi, vendor, system_package, or local_code"
        )
    discovered_at = str(payload.get("discovered_at") or "").strip()
    _parse_datetime(discovered_at, "discovered_at")
    version = str(payload.get("version_or_commit") or "").strip()
    if not version:
        raise ThirdPartyCandidateReviewError("version_or_commit is required")
    execution_surface = str(payload.get("execution_surface") or "").strip()
    temporal = str(payload.get("temporal_cutoff_support") or "").strip()
    future_risk = str(payload.get("future_function_risk") or "").strip()
    reproducibility = str(payload.get("reproducibility_status") or "").strip()
    license_status = str(payload.get("license_status") or "").strip().upper()
    security_status = str(payload.get("security_status") or "").strip().upper()
    for value, field in (
        (execution_surface, "execution_surface"),
        (temporal, "temporal_cutoff_support"),
        (future_risk, "future_function_risk"),
        (reproducibility, "reproducibility_status"),
        (license_status, "license_status"),
        (security_status, "security_status"),
    ):
        if not value:
            raise ThirdPartyCandidateReviewError(f"{field} is required")
    state = str(payload.get("state") or "DISCOVERED").strip().upper()
    if state not in REVIEW_STATES:
        raise ThirdPartyCandidateReviewError(f"unsupported review state: {state}")
    decision = str(payload.get("decision") or "").strip().upper()
    if decision and decision not in _TERMINAL_STATES:
        raise ThirdPartyCandidateReviewError(f"unsupported decision: {decision}")
    if decision and decision != state:
        raise ThirdPartyCandidateReviewError("decision must match terminal state")
    if state in _TERMINAL_STATES:
        decision = state
    return {
        "review_id": identifier,
        "capability_slice": capability_slice,
        "project_url": project_url,
        "package_name": package_name,
        "source_kind": source_kind,
        "discovered_at": discovered_at,
        "version_or_commit": version,
        "license_snapshot": str(payload.get("license_snapshot") or "").strip(),
        "license_status": license_status,
        "security_status": security_status,
        "capability_gap": capability_gap,
        "requested_capability": requested,
        "used_modules": _string_list(payload.get("used_modules"), "used_modules"),
        "excluded_modules": _string_list(payload.get("excluded_modules"), "excluded_modules"),
        "dependency_manifest": _json_value(payload.get("dependency_manifest") or {}, "dependency_manifest"),
        "network_required": bool(payload.get("network_required", False)),
        "token_required": bool(payload.get("token_required", False)),
        "account_required": bool(payload.get("account_required", False)),
        "execution_surface": execution_surface,
        "temporal_cutoff_support": temporal,
        "future_function_risk": future_risk,
        "reproducibility_status": reproducibility,
        "fixture_ids": _string_list(payload.get("fixture_ids"), "fixture_ids"),
        "baseline_id": str(payload.get("baseline_id") or "").strip(),
        "adapter_id": str(payload.get("adapter_id") or "").strip(),
        "fallback_id": str(payload.get("fallback_id") or "").strip(),
        "regression_status": str(payload.get("regression_status") or "NOT_RUN").strip().upper(),
        "enable_conditions": _json_value(payload.get("enable_conditions") or {}, "enable_conditions"),
        "capability_matrix_refs": _string_list(
            payload.get("capability_matrix_refs"), "capability_matrix_refs"
        ),
        "state": state,
        "decision": decision,
        "rejection_or_exit_reason": str(payload.get("rejection_or_exit_reason") or "").strip(),
        "reviewed_at": str(payload.get("reviewed_at") or "").strip(),
        "next_review_at": str(payload.get("next_review_at") or "").strip(),
        "owner": str(payload.get("owner") or "").strip(),
    }


def _project_fields(
    review: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    *,
    validate_events: bool = False,
) -> tuple[str, dict[str, Any]]:
    current = str(review.get("state") or "DISCOVERED").upper()
    fields = {key: value for key, value in review.items() if key not in {
        "schema_version", "rule_version", "policy", "immutable", "read_only",
        "review_only", "investment_conclusion", "execution_enabled", "content_hash",
    }}
    seen: set[str] = set()
    previous_changed: datetime | None = None
    for raw in events:
        if not isinstance(raw, Mapping):
            raise ThirdPartyCandidateReviewError("each event must be an object")
        event = validate_candidate_review_event(raw) if validate_events else dict(raw)
        event_id = str(event.get("event_id") or "").strip()
        if not event_id or event_id in seen:
            raise ThirdPartyCandidateReviewError(f"duplicate or empty event_id: {event_id}")
        if str(event.get("review_id") or "") != str(review.get("review_id") or ""):
            raise ThirdPartyCandidateReviewError("event review_id does not match review")
        if str(event.get("from_state") or "").upper() != current:
            raise ThirdPartyCandidateReviewError(
                f"event from_state does not match current state: {current}"
            )
        target = str(event.get("to_state") or "").upper()
        if target not in _TRANSITIONS[current]:
            raise ThirdPartyCandidateReviewError(f"invalid review transition: {current} -> {target}")
        changed = _parse_datetime(str(event.get("changed_at") or ""), "event.changed_at")
        if previous_changed and changed < previous_changed:
            raise ThirdPartyCandidateReviewError("event changed_at must be non-decreasing")
        updates = _normalize_updates(event.get("field_updates") or {})
        fields.update(updates)
        fields["state"] = target
        _validate_state_requirements(fields, target)
        seen.add(event_id)
        previous_changed = changed
        current = target
    return current, fields


def _normalize_updates(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ThirdPartyCandidateReviewError("field_updates must be an object")
    unknown = set(value) - _UPDATABLE_FIELDS
    if unknown:
        raise ThirdPartyCandidateReviewError(
            "field_updates contains immutable or unsupported fields: " + ", ".join(sorted(unknown))
        )
    updates: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"fixture_ids", "capability_matrix_refs"}:
            updates[key] = _string_list(item, key)
        elif key == "enable_conditions":
            updates[key] = _json_value(item or {}, key)
        elif key in {"license_status", "security_status", "regression_status"}:
            updates[key] = str(item or "").strip().upper()
        else:
            updates[key] = str(item or "").strip()
    return updates


def _validate_state_requirements(fields: Mapping[str, Any], state: str) -> None:
    if state not in REVIEW_STATES:
        raise ThirdPartyCandidateReviewError(f"unsupported review state: {state}")
    if state in {"LICENSE_AND_SECURITY_REVIEWED", "FIXTURE_VALIDATED", "ADAPTER_PILOTED", "ACCEPTED", "CONDITIONAL"}:
        if str(fields.get("license_status") or "").upper() in _BLOCKED_LICENSE_STATUSES:
            raise ThirdPartyCandidateReviewError("license review is incomplete")
        if str(fields.get("security_status") or "").upper() in _BLOCKED_SECURITY_STATUSES:
            raise ThirdPartyCandidateReviewError("security review is incomplete")
    if state in {"FIXTURE_VALIDATED", "ADAPTER_PILOTED", "ACCEPTED", "CONDITIONAL"}:
        if not _string_list(fields.get("fixture_ids"), "fixture_ids"):
            raise ThirdPartyCandidateReviewError(f"{state} requires fixture_ids")
        if not str(fields.get("baseline_id") or "").strip():
            raise ThirdPartyCandidateReviewError(f"{state} requires baseline_id")
        if str(fields.get("regression_status") or "").upper() not in {"PASS", "PASSED"}:
            raise ThirdPartyCandidateReviewError(f"{state} requires regression_status PASS")
    if state in {"ADAPTER_PILOTED", "ACCEPTED", "CONDITIONAL"}:
        if not str(fields.get("adapter_id") or "").strip():
            raise ThirdPartyCandidateReviewError(f"{state} requires adapter_id")
        if not str(fields.get("fallback_id") or "").strip():
            raise ThirdPartyCandidateReviewError(f"{state} requires fallback_id")
    if state == "CONDITIONAL" and not _json_value(fields.get("enable_conditions") or {}, "enable_conditions"):
        raise ThirdPartyCandidateReviewError("CONDITIONAL requires enable_conditions")
    if state in {"REFERENCE_ONLY", "REJECTED"} and not str(fields.get("rejection_or_exit_reason") or "").strip():
        raise ThirdPartyCandidateReviewError(f"{state} requires rejection_or_exit_reason")


def _json_value(value: Any, field: str) -> Any:
    if not isinstance(value, (Mapping, list, tuple)):
        raise ThirdPartyCandidateReviewError(f"{field} must be an object or list")
    return dict(value) if isinstance(value, Mapping) else list(value)


def _string_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise ThirdPartyCandidateReviewError(f"{field} must be a string list")
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _parse_datetime(value: str, field: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ThirdPartyCandidateReviewError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.combine(date.fromisoformat(text[:10]), datetime.min.time())
        except ValueError as error:
            raise ThirdPartyCandidateReviewError(f"{field} must be an ISO date or datetime") from error
    return parsed


def _content_hash(value: Mapping[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "content_hash"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()


def _hash_payload(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()


def _policy() -> dict[str, Any]:
    return {
        "candidate_review_only": True,
        "runtime_registry_separate": True,
        "no_automatic_install": True,
        "no_remote_fetch": True,
        "no_account_access": True,
        "no_investment_conclusion": True,
        "read_only": True,
        "review_only": True,
        "execution_enabled": False,
    }
