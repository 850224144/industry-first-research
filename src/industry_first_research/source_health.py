"""Immutable data-source health snapshots and capability-aware route plans."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from .data_sources import DataSourceRouter


SOURCE_HEALTH_SCHEMA_VERSION = "data-source-health.v1"
SOURCE_HEALTH_RULE_VERSION = "data-source-health-rules.v1"
_DEFAULT_SUBJECT_TYPES = (
    "listed_company",
    "industry",
    "futures_contract",
    "announcement",
)


class SourceHealthError(ValueError):
    """Raised when a source-health snapshot is invalid."""


def build_source_health_snapshot(
    router: DataSourceRouter,
    *,
    subject_types: Sequence[str] = _DEFAULT_SUBJECT_TYPES,
    source_names: Sequence[str] = (),
    required_capabilities: Mapping[str, Sequence[str]] | None = None,
    checked_at: str = "",
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Check adapter readiness without fetching research data.

    ``available`` means the adapter and its optional dependency are ready. It does
    not prove that a remote endpoint is reachable; actual fetch attempts remain
    part of the evidence lineage.
    """

    if not isinstance(router, DataSourceRouter):
        raise SourceHealthError("router must be a DataSourceRouter")
    normalized_subjects = _string_list(subject_types, "subject_types")
    if not normalized_subjects:
        raise SourceHealthError("subject_types must not be empty")
    normalized_sources = _string_list(source_names, "source_names")
    normalized_capabilities = _capability_map(required_capabilities)
    checked = str(checked_at or "").strip() or datetime.now(timezone.utc).isoformat()
    _parse_datetime(checked, "checked_at")

    health_items = [item.to_dict() for item in router.health(normalized_sources or None)]
    by_name = {str(item["name"]): item for item in health_items}
    routes: dict[str, dict[str, Any]] = {}
    for subject_type in normalized_subjects:
        configured = list(router.policy.sources_for(subject_type))
        eligible: list[str] = []
        rejected: list[dict[str, Any]] = []
        required = set(normalized_capabilities.get(subject_type, ()))
        for name in configured:
            item = by_name.get(name)
            if item is None:
                rejected.append({"source": name, "reason": "not_checked"})
                continue
            capabilities = set(item.get("capabilities") or ())
            if not item.get("available"):
                rejected.append({"source": name, "reason": item.get("reason") or "unavailable"})
            elif required and not required.issubset(capabilities):
                rejected.append(
                    {
                        "source": name,
                        "reason": "missing_capability",
                        "required": sorted(required),
                        "available": sorted(capabilities),
                    }
                )
            else:
                eligible.append(name)
        routes[subject_type] = {
            "configured_sources": configured,
            "eligible_sources": eligible,
            "primary_source": eligible[0] if eligible else None,
            "fallback_sources": eligible[1:],
            "rejected_sources": rejected,
            "required_capabilities": sorted(required),
            "status": "READY" if eligible else "INSUFFICIENT",
        }

    normalized = {
        "schema_version": SOURCE_HEALTH_SCHEMA_VERSION,
        "snapshot_id": str(snapshot_id or "").strip(),
        "checked_at": checked,
        "subject_types": normalized_subjects,
        "source_names": normalized_sources or sorted(by_name),
        "sources": health_items,
        "routes": routes,
        "policy": {
            "health_check_is_adapter_readiness_only": True,
            "endpoint_reachability_requires_fetch_attempt": True,
            "fallback_order_preserved": True,
            "qmt_dependency": False,
            "read_only": True,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
        },
        "rule_version": SOURCE_HEALTH_RULE_VERSION,
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }
    normalized["snapshot_id"] = normalized["snapshot_id"] or (
        "source-health-" + _hash_payload(normalized)[:20]
    )
    normalized["content_hash"] = _hash_payload(normalized)
    return normalized


def validate_source_health_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Validate schema, immutability and content hash without rechecking sources."""

    if not isinstance(snapshot, Mapping):
        raise SourceHealthError("source health snapshot must be an object")
    if snapshot.get("schema_version") != SOURCE_HEALTH_SCHEMA_VERSION:
        raise SourceHealthError(f"input must be {SOURCE_HEALTH_SCHEMA_VERSION}")
    for field in ("snapshot_id", "checked_at", "content_hash", "rule_version"):
        if not str(snapshot.get(field) or "").strip():
            raise SourceHealthError(f"source health {field} is required")
    if snapshot.get("immutable") is not True:
        raise SourceHealthError("source health snapshot must be immutable")
    if not isinstance(snapshot.get("sources"), list) or not isinstance(snapshot.get("routes"), Mapping):
        raise SourceHealthError("source health snapshot has invalid sources or routes")
    _parse_datetime(str(snapshot["checked_at"]), "checked_at")
    expected = _hash_payload(
        {key: value for key, value in snapshot.items() if key != "content_hash"}
    )
    if str(snapshot["content_hash"]) != expected:
        raise SourceHealthError("content_hash does not match source health snapshot")
    return dict(snapshot)


def _capability_map(value: Mapping[str, Sequence[str]] | None) -> dict[str, list[str]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise SourceHealthError("required_capabilities must be an object")
    return {
        str(subject): _string_list(capabilities, f"required_capabilities.{subject}")
        for subject, capabilities in value.items()
    }


def _string_list(value: Sequence[str], field: str) -> list[str]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise SourceHealthError(f"{field} must be a string list")
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _parse_datetime(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise SourceHealthError(f"{field} must be an ISO datetime") from error


def _hash_payload(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
