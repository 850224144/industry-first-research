"""Auditable reuse decisions for existing components and capability gaps."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
from typing import Any


CAPABILITY_MATRIX_SCHEMA_VERSION = "capability-matrix.v1"
CAPABILITY_DECISIONS = {
    "DIRECT_REUSE",
    "ADAPTER_REUSE",
    "REFERENCE_ONLY",
    "NEW_DEVELOPMENT",
}
RULE_VERSION = "capability-matrix-rules.v1"


class CapabilityMatrixError(ValueError):
    """Raised when a capability reuse decision is incomplete."""


def build_capability_matrix(
    payload: Mapping[str, Any], *, matrix_id: str = ""
) -> dict[str, Any]:
    """Validate and normalize a capability inventory.

    A new implementation is allowed only when its record names the concrete
    gap that existing components cannot satisfy.
    """

    if not isinstance(payload, Mapping):
        raise CapabilityMatrixError("capability matrix must be a JSON object")
    raw_items = payload.get("items") or payload.get("capabilities")
    if not isinstance(raw_items, list):
        raise CapabilityMatrixError("capability matrix has no items list")
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            raise CapabilityMatrixError("each capability item must be an object")
        item = _item(raw)
        if item["capability_id"] in seen:
            raise CapabilityMatrixError(f"duplicate capability_id: {item['capability_id']}")
        seen.add(item["capability_id"])
        items.append(item)
    counts = Counter(item["decision"] for item in items)
    identifier = str(payload.get("matrix_id") or matrix_id).strip() or f"capability-matrix-{_hash(items)[:20]}"
    return {
        "schema_version": CAPABILITY_MATRIX_SCHEMA_VERSION,
        "matrix_id": identifier,
        "as_of": str(payload.get("as_of") or ""),
        "items": items,
        "item_count": len(items),
        "decision_counts": dict(counts),
        "matrix_hash": _hash(items),
        "rule_version": RULE_VERSION,
        "policy": {
            "reuse_before_new_development": True,
            "new_development_requires_capability_gap": True,
            "adapter_preferred_for_protocol_or_schema_gap": True,
            "license_and_safety_boundary_required": True,
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


def build_capability_gap(
    payload: Mapping[str, Any], *, gap_id: str = ""
) -> dict[str, Any]:
    """Create a bounded new-development request tied to an explicit gap."""

    if not isinstance(payload, Mapping):
        raise CapabilityMatrixError("capability gap must be a JSON object")
    name = str(payload.get("capability_name") or "").strip()
    gap = str(payload.get("capability_gap") or payload.get("gap") or "").strip()
    if not name:
        raise CapabilityMatrixError("capability_name is required")
    if not gap:
        raise CapabilityMatrixError("capability_gap is required for new development")
    identifier = str(payload.get("gap_id") or gap_id).strip() or f"gap-{_hash(payload)[:20]}"
    return {
        "schema_version": "capability-gap.v1",
        "gap_id": identifier,
        "capability_name": name,
        "capability_gap": gap,
        "existing_components_checked": _string_list(payload.get("existing_components_checked")),
        "rejected_reuse_reasons": _string_list(payload.get("rejected_reuse_reasons")),
        "proposed_scope": str(payload.get("proposed_scope") or ""),
        "owner_module": str(payload.get("owner_module") or ""),
        "created_as_of": str(payload.get("created_as_of") or payload.get("as_of") or ""),
        "rule_version": RULE_VERSION,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _item(raw: Mapping[str, Any]) -> dict[str, Any]:
    identifier = str(raw.get("capability_id") or "").strip()
    name = str(raw.get("capability_name") or "").strip()
    component = str(raw.get("component") or "").strip()
    decision = str(raw.get("decision") or "").strip().upper()
    if not identifier:
        raise CapabilityMatrixError("capability_id is required")
    if not name:
        raise CapabilityMatrixError(f"{identifier}: capability_name is required")
    if not component:
        raise CapabilityMatrixError(f"{identifier}: component is required")
    if decision not in CAPABILITY_DECISIONS:
        raise CapabilityMatrixError(f"{identifier}: unsupported decision {decision or '<empty>'}")
    interfaces = _string_list(raw.get("interfaces"))
    if not interfaces:
        raise CapabilityMatrixError(f"{identifier}: interfaces are required")
    license_status = str(raw.get("license_status") or "").strip()
    temporal = str(raw.get("temporal_cutoff_support") or "").strip()
    safety = str(raw.get("safety_boundary") or "").strip()
    if not license_status:
        raise CapabilityMatrixError(f"{identifier}: license_status is required")
    if not temporal:
        raise CapabilityMatrixError(f"{identifier}: temporal_cutoff_support is required")
    if not safety:
        raise CapabilityMatrixError(f"{identifier}: safety_boundary is required")
    gap = str(raw.get("capability_gap") or "").strip()
    if decision == "NEW_DEVELOPMENT" and not gap:
        raise CapabilityMatrixError(f"{identifier}: NEW_DEVELOPMENT requires capability_gap")
    if decision != "NEW_DEVELOPMENT" and gap:
        raise CapabilityMatrixError(f"{identifier}: capability_gap is only for NEW_DEVELOPMENT")
    return {
        "capability_id": identifier,
        "capability_name": name,
        "component": component,
        "component_version": str(raw.get("component_version") or "unknown"),
        "interfaces": interfaces,
        "output_quality": str(raw.get("output_quality") or "UNKNOWN"),
        "license_status": license_status,
        "temporal_cutoff_support": temporal,
        "safety_boundary": safety,
        "decision": decision,
        "reuse_reason": str(raw.get("reuse_reason") or ""),
        "capability_gap": gap or None,
        "evidence_refs": _string_list(raw.get("evidence_refs")),
        "validated_at": str(raw.get("validated_at") or raw.get("as_of") or ""),
        "field_lineage": dict(raw.get("field_lineage") or {}),
    }


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise CapabilityMatrixError("expected a string list")
    return [str(item).strip() for item in value if str(item).strip()]


def _hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()
