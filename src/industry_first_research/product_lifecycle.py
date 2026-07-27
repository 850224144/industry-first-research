"""Evidence-only product lifecycle and market-state snapshots.

The lifecycle stage must be explicitly supplied or supported by evidence.  A
price move, theme label, or downstream growth story is never enough for this
module to infer a stage transition.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from typing import Any

from .company_scope import CompanyScopeError, normalize_scope_reports, scope_item_for_company


PRODUCT_LIFECYCLE_INPUT_SCHEMA_VERSION = "product-lifecycle-input.v1"
PRODUCT_LIFECYCLE_SCHEMA_VERSION = "product-lifecycle-snapshot.v1"
RULE_VERSION = "product-lifecycle-rules.v1"

LIFECYCLE_STATES = {
    "INTRODUCTION",
    "RAMP_UP",
    "MATURE",
    "PRICE_DECLINE",
    "REPLACEMENT_RISK",
    "UNKNOWN",
}
MARKET_STATES = {"EXPANDING", "STABLE", "COMMODITIZED", "CONTRACTING", "UNKNOWN"}
MARKET_FIELDS = (
    "price",
    "inventory",
    "supply",
    "demand",
    "utilization",
    "customer_capex",
    "competitor_expansion",
)
FORMAL_EVIDENCE_STATUSES = {"VERIFIED", "CROSS_VALIDATED"}
FIELD_STATUSES = {
    "VERIFIED",
    "CROSS_VALIDATED",
    "COMPANY_CLAIM",
    "MODEL_ASSUMPTION",
    "UNVERIFIED",
    "CONFLICTING",
    "UNKNOWN",
    "MISSING",
}


class ProductLifecycleError(ValueError):
    """Raised when a lifecycle snapshot violates its evidence contract."""


def build_product_lifecycle_report(
    payload: Mapping[str, Any],
    *,
    company_scope_reports: Mapping[str, Mapping[str, Any]] | None = None,
    snapshot_id: str = "",
    rule_version: str = RULE_VERSION,
) -> dict[str, Any]:
    """Normalize explicit lifecycle claims and required market-state fields."""

    if not isinstance(payload, Mapping):
        raise ProductLifecycleError("product lifecycle input must be a JSON object")
    if payload.get("schema_version") != PRODUCT_LIFECYCLE_INPUT_SCHEMA_VERSION:
        raise ProductLifecycleError(
            f"input must be {PRODUCT_LIFECYCLE_INPUT_SCHEMA_VERSION}"
        )
    if not str(rule_version or "").strip():
        raise ProductLifecycleError("rule_version must not be empty")
    try:
        scope_reports = normalize_scope_reports(company_scope_reports)
    except CompanyScopeError as error:
        raise ProductLifecycleError(str(error)) from error
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ProductLifecycleError("input must contain a non-empty items list")

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, Mapping):
            raise ProductLifecycleError("each lifecycle item must be an object")
        item = _build_item(
            raw_item,
            payload=payload,
            scope_reports=scope_reports,
            index=index,
            rule_version=rule_version,
        )
        if item["snapshot_item_id"] in seen:
            raise ProductLifecycleError(
                f"duplicate snapshot_item_id: {item['snapshot_item_id']}"
            )
        seen.add(item["snapshot_item_id"])
        items.append(item)

    state_counts = Counter(item["lifecycle_state"] for item in items)
    market_counts = Counter(item["market_state"] for item in items)
    report_key = str(snapshot_id or payload.get("report_id") or "input").strip()
    return {
        "schema_version": PRODUCT_LIFECYCLE_SCHEMA_VERSION,
        "report_id": f"product-lifecycle-{report_key}",
        "input_product_profile_id": str(payload.get("product_profile_id") or ""),
        "input_application_mapping_id": str(payload.get("application_mapping_id") or ""),
        "as_of": str(payload.get("as_of") or ""),
        "rule_version": rule_version,
        "item_count": len(items),
        "lifecycle_state_counts": dict(state_counts),
        "market_state_counts": dict(market_counts),
        "items": items,
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "policy": {
            "explicit_lifecycle_evidence_only": True,
            "no_stage_inference_from_price": True,
            "market_snapshot_is_evidence_only": True,
            "future_fields_excluded": True,
            "investment_conclusion": False,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
    }


def validate_product_lifecycle_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the envelope and item states of a stored lifecycle snapshot."""

    if not isinstance(report, Mapping) or report.get("schema_version") != PRODUCT_LIFECYCLE_SCHEMA_VERSION:
        raise ProductLifecycleError(f"input must be {PRODUCT_LIFECYCLE_SCHEMA_VERSION}")
    if report.get("immutable") is not True:
        raise ProductLifecycleError("product lifecycle report must be immutable")
    items = report.get("items")
    if not isinstance(items, list):
        raise ProductLifecycleError("product lifecycle report has no items list")
    errors: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            errors.append("item is not an object")
            continue
        identifier = str(item.get("snapshot_item_id") or "")
        if not identifier:
            errors.append("snapshot_item_id is missing")
        elif identifier in seen:
            errors.append(f"duplicate snapshot_item_id: {identifier}")
        seen.add(identifier)
        if str(item.get("lifecycle_state") or "") not in LIFECYCLE_STATES:
            errors.append(f"unsupported lifecycle_state: {identifier}")
        if str(item.get("market_state") or "") not in MARKET_STATES:
            errors.append(f"unsupported market_state: {identifier}")
    return {
        "schema_version": "product-lifecycle-validation.v1",
        "report_id": str(report.get("report_id") or ""),
        "status": "VALID" if not errors else "INVALID",
        "error_count": len(errors),
        "errors": errors,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _build_item(
    raw: Mapping[str, Any],
    *,
    payload: Mapping[str, Any],
    scope_reports: Mapping[str, Mapping[str, Any]],
    index: int,
    rule_version: str,
) -> dict[str, Any]:
    company_id = str(raw.get("company_id") or payload.get("company_id") or "").strip()
    product_id = str(raw.get("product_id") or "").strip()
    product_name = str(raw.get("product_name") or raw.get("product") or "").strip()
    scope_id = str(raw.get("scope_id") or payload.get("scope_id") or "").strip()
    as_of = str(raw.get("as_of") or payload.get("as_of") or "").strip()
    if not company_id:
        raise ProductLifecycleError("company_id is required")
    if not product_id:
        raise ProductLifecycleError("product_id is required")
    if not product_name:
        raise ProductLifecycleError("product_name is required")
    if not scope_id:
        raise ProductLifecycleError("scope_id is required")
    _validate_as_of(as_of)

    scope_projection, scope_status = _scope_status(scope_reports, company_id, scope_id)
    lifecycle_field = _normalise_field(raw.get("lifecycle_state"), "lifecycle_state", as_of)
    lifecycle_state = _normalise_lifecycle_state(lifecycle_field["value"])
    lifecycle_field["value"] = lifecycle_state
    market_state_field = _normalise_field(raw.get("market_state"), "market_state", as_of)
    market_state = _normalise_market_state(market_state_field["value"])
    market_state_field["value"] = market_state

    market_snapshot: dict[str, dict[str, Any]] = {}
    raw_market_snapshot = raw.get("market_snapshot") or {}
    if not isinstance(raw_market_snapshot, Mapping):
        raise ProductLifecycleError("market_snapshot must be an object")
    missing_fields: list[str] = []
    for field in MARKET_FIELDS:
        summary = _normalise_field(raw_market_snapshot.get(field), field, as_of)
        market_snapshot[field] = summary
        if summary["status"] in {"MISSING", "UNKNOWN"}:
            missing_fields.append(field)

    next_conditions = _string_list(raw.get("next_stage_conditions"))
    substitution_factors = _string_list(raw.get("substitution_factors"))
    stage_evidence_ids = _unique(
        [
            *lifecycle_field["evidence_ids"],
            *market_state_field["evidence_ids"],
            *(
                evidence_id
                for field in market_snapshot.values()
                for evidence_id in field["evidence_ids"]
            ),
        ]
    )
    unknowns = list(missing_fields)
    if lifecycle_state == "UNKNOWN":
        unknowns.append("lifecycle_state")
    if market_state == "UNKNOWN":
        unknowns.append("market_state")
    if not next_conditions:
        unknowns.append("next_stage_conditions")
    if not substitution_factors:
        unknowns.append("substitution_factors")

    if scope_status == "CONFLICTING":
        snapshot_state = "BLOCKED"
    elif lifecycle_state == "UNKNOWN":
        snapshot_state = "INSUFFICIENT"
    elif (
        not next_conditions
        or not substitution_factors
        or missing_fields
        or market_state == "UNKNOWN"
    ):
        snapshot_state = "PARTIAL"
    elif lifecycle_field["status"] not in FORMAL_EVIDENCE_STATUSES:
        snapshot_state = "PARTIAL"
    else:
        snapshot_state = "READY"

    warnings: list[str] = []
    if scope_status != "VERIFIED":
        warnings.append("scope is not verified for this company/product snapshot")
    if lifecycle_state != "UNKNOWN" and lifecycle_field["status"] not in FORMAL_EVIDENCE_STATUSES:
        warnings.append("lifecycle state is not supported by formal evidence")
    if market_state == "UNKNOWN":
        warnings.append("market state was not explicitly mapped")
    if not next_conditions:
        warnings.append("next stage conditions are missing; no transition is inferred")
    if not substitution_factors:
        warnings.append("substitution factors are missing; replacement risk is not inferred")

    identifier = str(raw.get("snapshot_item_id") or "").strip() or (
        f"lifecycle-{company_id}-{product_id}-{index + 1}"
    )
    return {
        "snapshot_item_id": identifier,
        "company_id": company_id,
        "scope_id": scope_id,
        "scope_status": scope_status,
        "scope_projection": scope_projection,
        "product_id": product_id,
        "product_name": product_name,
        "as_of": as_of,
        "lifecycle_state": lifecycle_state,
        "lifecycle_field": lifecycle_field,
        "next_stage_options": _next_stage_options(lifecycle_state),
        "next_stage_conditions": next_conditions,
        "substitution_factors": substitution_factors,
        "market_state": market_state,
        "market_state_field": market_state_field,
        "market_snapshot": market_snapshot,
        "unknowns": _unique(unknowns),
        "warnings": warnings,
        "evidence_ids": stage_evidence_ids,
        "evidence_status": _evidence_status(lifecycle_field, market_state_field, market_snapshot, snapshot_state),
        "confidence": _confidence(snapshot_state, scope_status, lifecycle_field, market_snapshot),
        "snapshot_state": snapshot_state,
        "transition_status": "EXPLICIT_STAGE_ONLY",
        "rule_version": rule_version,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _normalise_field(raw: Any, field: str, as_of: str) -> dict[str, Any]:
    if raw in (None, ""):
        return {
            "status": "MISSING",
            "value": None,
            "values": [],
            "evidence_ids": [],
            "sources": [],
            "as_of": "",
        }
    if isinstance(raw, Mapping):
        status = str(raw.get("status") or raw.get("verification_status") or "MODEL_ASSUMPTION").strip().upper()
        if "values" in raw:
            values = raw.get("values")
            if not isinstance(values, list):
                values = [values]
            value = values[0] if len(values) == 1 else values
        else:
            value = raw.get("value")
            values = [] if value is None else [value]
        evidence_ids = _string_list(raw.get("evidence_ids") or raw.get("source_evidence_ids"))
        sources = _string_list(raw.get("sources") or raw.get("source"))
        field_as_of = str(raw.get("as_of") or "").strip()
    else:
        status = "MODEL_ASSUMPTION"
        value = raw
        values = [raw]
        evidence_ids = []
        sources = ["manual_input"]
        field_as_of = ""
    if status not in FIELD_STATUSES:
        raise ProductLifecycleError(f"unsupported field status for {field}: {status}")
    if status in FORMAL_EVIDENCE_STATUSES and not evidence_ids:
        status = "COMPANY_CLAIM"
    if field_as_of:
        _validate_as_of(field_as_of)
        if _as_of_key(field_as_of) > _as_of_key(as_of):
            status = "UNKNOWN"
            values = []
            value = None
            evidence_ids = []
    return {
        "status": status,
        "value": value,
        "values": values,
        "evidence_ids": evidence_ids,
        "sources": sources,
        "as_of": field_as_of,
    }


def _normalise_lifecycle_state(value: Any) -> str:
    text = str(value or "").strip().upper().replace("-", "_")
    aliases = {
        "导入期": "INTRODUCTION",
        "导入": "INTRODUCTION",
        "放量期": "RAMP_UP",
        "放量": "RAMP_UP",
        "成熟期": "MATURE",
        "成熟": "MATURE",
        "降价期": "PRICE_DECLINE",
        "降价": "PRICE_DECLINE",
        "被替代期": "REPLACEMENT_RISK",
        "替代风险": "REPLACEMENT_RISK",
        "UNKNOWN": "UNKNOWN",
    }
    text = aliases.get(text, text)
    if not text:
        return "UNKNOWN"
    if text not in LIFECYCLE_STATES:
        raise ProductLifecycleError(f"unsupported lifecycle_state: {text}")
    return text


def _normalise_market_state(value: Any) -> str:
    text = str(value or "").strip().upper().replace("-", "_")
    aliases = {
        "扩张": "EXPANDING",
        "增长": "EXPANDING",
        "稳定": "STABLE",
        "成熟": "STABLE",
        "商品化": "COMMODITIZED",
        "同质化": "COMMODITIZED",
        "收缩": "CONTRACTING",
        "萎缩": "CONTRACTING",
        "UNKNOWN": "UNKNOWN",
    }
    text = aliases.get(text, text)
    if not text:
        return "UNKNOWN"
    if text not in MARKET_STATES:
        raise ProductLifecycleError(f"unsupported market_state: {text}")
    return text


def _next_stage_options(state: str) -> list[str]:
    return {
        "INTRODUCTION": ["RAMP_UP"],
        "RAMP_UP": ["MATURE", "PRICE_DECLINE"],
        "MATURE": ["PRICE_DECLINE", "REPLACEMENT_RISK"],
        "PRICE_DECLINE": ["REPLACEMENT_RISK"],
        "REPLACEMENT_RISK": [],
        "UNKNOWN": [],
    }[state]


def _scope_status(
    reports: Mapping[str, Mapping[str, Any]], company_id: str, scope_id: str
) -> tuple[dict[str, Any] | None, str]:
    if not reports:
        return None, "UNVERIFIED"
    report = reports.get(company_id)
    if report is None:
        return None, "MISSING"
    try:
        projection = scope_item_for_company(report, company_id)
    except CompanyScopeError as error:
        raise ProductLifecycleError(str(error)) from error
    if projection is None or projection["scope_id"] != scope_id:
        return projection, "CONFLICTING"
    state = str(projection.get("researchability_state") or "INSUFFICIENT").upper()
    return projection, {"READY": "VERIFIED", "PARTIAL": "PARTIAL"}.get(state, state)


def _evidence_status(
    lifecycle_field: Mapping[str, Any],
    market_state_field: Mapping[str, Any],
    market_snapshot: Mapping[str, Mapping[str, Any]],
    snapshot_state: str,
) -> str:
    fields = [lifecycle_field, market_state_field, *market_snapshot.values()]
    statuses = [str(item.get("status") or "MISSING") for item in fields]
    if "CONFLICTING" in statuses:
        return "CONFLICTING"
    if snapshot_state in {"INSUFFICIENT", "BLOCKED"}:
        return "UNKNOWN"
    if snapshot_state == "PARTIAL":
        return "PARTIAL"
    if all(item.get("status") in FORMAL_EVIDENCE_STATUSES and item.get("evidence_ids") for item in fields):
        return "VERIFIED"
    if any(item.get("status") == "MODEL_ASSUMPTION" for item in fields):
        return "MODEL_ASSUMPTION"
    return "PARTIAL"


def _confidence(
    snapshot_state: str,
    scope_status: str,
    lifecycle_field: Mapping[str, Any],
    market_snapshot: Mapping[str, Mapping[str, Any]],
) -> str:
    if snapshot_state != "READY":
        return "LOW"
    if scope_status != "VERIFIED":
        return "MEDIUM"
    fields = [lifecycle_field, *market_snapshot.values()]
    return "HIGH" if all(item.get("status") in FORMAL_EVIDENCE_STATUSES and item.get("evidence_ids") for item in fields) else "MEDIUM"


def _validate_as_of(value: str) -> None:
    if not value:
        raise ProductLifecycleError("as_of is required")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            date.fromisoformat(value)
        except ValueError as error:
            raise ProductLifecycleError("as_of must be an ISO date or datetime") from error


def _as_of_key(value: str) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.combine(date.fromisoformat(text), datetime.min.time())
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise ProductLifecycleError("expected a string list")
    return [str(item).strip() for item in value if str(item).strip()]


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))
