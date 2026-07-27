"""Normalize company boundaries before product, financial, or valuation work.

The scope object is intentionally small and evidence-oriented.  It prevents a
subsidiary, associate, or related party from being silently treated as the
listed entity, while still allowing a caller to keep facts that do not
transmit to the listed subject.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from hashlib import sha256
import json
from typing import Any


class CompanyScopeError(ValueError):
    """Raised when a company boundary package is unsafe or incomplete."""


COMPANY_SCOPE_SCHEMA_VERSION = "company-scope.v1"
RULE_VERSION = "company-scope-rules.v1"
OBJECT_TYPES = {
    "ListedEntity",
    "ConsolidatedGroup",
    "Subsidiary",
    "Associate",
    "Unconsolidated",
    "RelatedParty",
}
CONSOLIDATION_METHODS = {"CONSOLIDATED", "EQUITY_METHOD", "NONE", "UNKNOWN"}
TRANSMISSION_STATES = {
    "DIRECT",
    "CONSOLIDATED",
    "EQUITY_METHOD",
    "NO_TRANSMISSION",
    "UNKNOWN",
}
BOUNDARY_FIELDS = (
    "product_ownership",
    "order_ownership",
    "capacity_attribution",
    "revenue_attribution",
    "profit_attribution",
    "cash_attribution",
    "debt_attribution",
    "transmission_to_listed",
)
RESEARCHABILITY_STATES = {"READY", "PARTIAL", "INSUFFICIENT", "BLOCKED"}


def build_company_scope_report(
    payload: Mapping[str, Any],
    *,
    required_fields: Sequence[str] = BOUNDARY_FIELDS,
    rule_version: str = RULE_VERSION,
    scope_id: str = "",
) -> dict[str, Any]:
    """Build a versioned company boundary and researchability report."""

    if not isinstance(payload, Mapping):
        raise CompanyScopeError("company scope input must be an object")
    if payload.get("schema_version") not in {"company-scope-input.v1", COMPANY_SCOPE_SCHEMA_VERSION}:
        raise CompanyScopeError("input must be company-scope-input.v1 or company-scope.v1")
    as_of = _parse_day(payload.get("as_of") or payload.get("research_as_of"), "as_of")
    fields = _normalise_fields(required_fields)
    objects = _normalise_objects(payload.get("objects"), as_of)
    object_by_id = {item["object_id"]: item for item in objects}
    listed = [item for item in objects if item["object_type"] == "ListedEntity"]
    group = [item for item in objects if item["object_type"] == "ConsolidatedGroup"]
    if len(listed) > 1:
        raise CompanyScopeError("company scope cannot contain multiple ListedEntity objects")
    if len(group) > 1:
        raise CompanyScopeError("company scope cannot contain multiple ConsolidatedGroup objects")

    facts = _normalise_facts(payload.get("facts") or [], object_by_id, as_of)
    field_status = {
        field: _field_status(
            field,
            facts,
            listed[0]["object_id"] if listed else "",
            object_by_id,
        )
        for field in fields
    }
    blockers: list[str] = []
    unknowns: list[str] = []
    if not listed:
        blockers.append("LISTED_ENTITY_MISSING")
    if not group:
        blockers.append("CONSOLIDATED_GROUP_MISSING")
    if listed and group and group[0].get("parent_entity_id") not in {None, listed[0]["object_id"]}:
        blockers.append("CONSOLIDATED_GROUP_PARENT_MISMATCH")
    for field, status in field_status.items():
        if status == "MISSING":
            unknowns.append(field)
        elif status == "CONFLICTING":
            blockers.append(f"CONFLICTING_{field.upper()}")

    if blockers:
        state = "BLOCKED"
    elif not facts or len(unknowns) == len(fields):
        state = "INSUFFICIENT"
    elif unknowns or any(status in {"UNVERIFIED", "PARTIAL"} for status in field_status.values()):
        state = "PARTIAL"
    else:
        state = "READY"
    report_key = str(scope_id or payload.get("scope_id") or payload.get("company_id") or "scope").strip()
    evidence_ids = sorted({evidence_id for fact in facts for evidence_id in fact["evidence_ids"]})
    report = {
        "schema_version": COMPANY_SCOPE_SCHEMA_VERSION,
        "scope_id": f"company-scope-{report_key}",
        "company_id": str(payload.get("company_id") or (listed[0]["object_id"] if listed else "")).strip(),
        "display_name": str(payload.get("display_name") or "").strip(),
        "as_of": as_of.isoformat(),
        "research_as_of": as_of.isoformat(),
        "rule_version": rule_version,
        "objects": objects,
        "facts": facts,
        "field_status": field_status,
        "evidence_ids": evidence_ids,
        "researchability_state": state,
        "blockers": sorted(set(blockers)),
        "unknowns": sorted(set(unknowns)),
        "object_counts": dict(Counter(item["object_type"] for item in objects)),
        "policy": {
            "scope_before_deep_research": True,
            "economic_facts_bound_to_object": True,
            "unconsolidated_facts_not_auto_attributed": True,
            "related_party_not_operating_entity": True,
            "read_only": True,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
        },
        "content_hash": _hash_payload({
            "company_id": str(payload.get("company_id") or (listed[0]["object_id"] if listed else "")).strip(),
            "as_of": as_of.isoformat(),
            "objects": objects,
            "facts": facts,
        }),
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }
    return report


def validate_company_scope_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a stored scope report and return a read-only validation result."""

    if not isinstance(report, Mapping) or report.get("schema_version") != COMPANY_SCOPE_SCHEMA_VERSION:
        raise CompanyScopeError("input must be company-scope.v1")
    rebuilt = build_company_scope_report({**report, "schema_version": COMPANY_SCOPE_SCHEMA_VERSION})
    errors: list[str] = []
    for field in ("scope_id", "company_id", "as_of", "content_hash"):
        if not str(report.get(field) or "").strip():
            errors.append(f"missing {field}")
    if report.get("content_hash") != rebuilt["content_hash"]:
        errors.append("content_hash does not match normalized objects and facts")
    if report.get("researchability_state") not in RESEARCHABILITY_STATES:
        errors.append("unsupported researchability_state")
    return {
        "schema_version": "company-scope-validation.v1",
        "scope_id": str(report.get("scope_id") or ""),
        "as_of": str(report.get("as_of") or ""),
        "status": "VALID" if not errors else "INVALID",
        "error_count": len(errors),
        "errors": errors,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def scope_item_for_company(report: Mapping[str, Any], company_id: str) -> dict[str, Any] | None:
    """Return a compact scope projection for a company-stage report."""

    if not isinstance(report, Mapping) or report.get("schema_version") != COMPANY_SCOPE_SCHEMA_VERSION:
        raise CompanyScopeError("scope report must be company-scope.v1")
    target = str(company_id or "").strip()
    report_company = str(report.get("company_id") or "").strip()
    if target and report_company and target != report_company:
        return None
    return {
        "scope_id": str(report.get("scope_id") or ""),
        "company_id": report_company,
        "researchability_state": str(report.get("researchability_state") or "INSUFFICIENT").upper(),
        "field_status": dict(report.get("field_status") or {}),
        "evidence_ids": list(report.get("evidence_ids") or []),
        "blockers": list(report.get("blockers") or []),
        "unknowns": list(report.get("unknowns") or []),
        "scope_content_hash": str(report.get("content_hash") or ""),
        "scope_as_of": str(report.get("as_of") or ""),
    }


def normalize_scope_reports(
    reports: Mapping[str, Any] | None,
) -> dict[str, Mapping[str, Any]]:
    """Accept either one scope report or a company-id keyed report map."""

    if reports is None:
        return {}
    if not isinstance(reports, Mapping):
        raise CompanyScopeError("company scope reports must be an object")
    if reports.get("schema_version") == COMPANY_SCOPE_SCHEMA_VERSION:
        company_id = str(reports.get("company_id") or "").strip()
        if not company_id:
            raise CompanyScopeError("single company scope report requires company_id")
        return {company_id: reports}
    normalized: dict[str, Mapping[str, Any]] = {}
    for key, value in reports.items():
        if not isinstance(value, Mapping):
            raise CompanyScopeError(f"company scope report must be an object: {key}")
        if value.get("schema_version") != COMPANY_SCOPE_SCHEMA_VERSION:
            raise CompanyScopeError(f"company scope report must be company-scope.v1: {key}")
        company_id = str(value.get("company_id") or key or "").strip()
        if not company_id:
            raise CompanyScopeError("company scope report company_id is required")
        if company_id in normalized:
            raise CompanyScopeError(f"duplicate company scope report: {company_id}")
        normalized[company_id] = value
    return normalized


def _normalise_objects(raw: Any, as_of: date) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise CompanyScopeError("objects must be a non-empty list")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            raise CompanyScopeError("each scope object must be an object")
        object_id = str(item.get("object_id") or item.get("entity_id") or "").strip()
        object_type = str(item.get("object_type") or "").strip()
        if not object_id or not object_type:
            raise CompanyScopeError("scope object requires object_id and object_type")
        if object_id in seen:
            raise CompanyScopeError(f"duplicate scope object_id: {object_id}")
        if object_type not in OBJECT_TYPES:
            raise CompanyScopeError(f"unsupported scope object_type: {object_type}")
        parent = str(item.get("parent_entity_id") or "").strip() or None
        ownership = item.get("ownership_percent")
        if ownership is not None:
            try:
                ownership = float(ownership)
            except (TypeError, ValueError) as error:
                raise CompanyScopeError(f"ownership_percent must be numeric: {object_id}") from error
            if ownership < 0 or ownership > 100:
                raise CompanyScopeError(f"ownership_percent out of range: {object_id}")
        method = str(item.get("consolidation_method") or "UNKNOWN").upper()
        if method not in CONSOLIDATION_METHODS:
            raise CompanyScopeError(f"unsupported consolidation_method: {method}")
        if object_type == "ListedEntity" and method not in {"CONSOLIDATED", "UNKNOWN"}:
            raise CompanyScopeError("ListedEntity consolidation_method must be CONSOLIDATED or UNKNOWN")
        seen.add(object_id)
        result.append({
            "object_id": object_id,
            "object_type": object_type,
            "legal_name": str(item.get("legal_name") or ""),
            "display_name": str(item.get("display_name") or ""),
            "parent_entity_id": parent,
            "ownership_percent": ownership,
            "consolidation_method": method,
            "listed_subject_id": str(item.get("listed_subject_id") or ""),
            "as_of": str(item.get("as_of") or as_of.isoformat()),
            "source_evidence_ids": _string_list(item.get("source_evidence_ids")),
        })
    for item in result:
        if item["parent_entity_id"] and item["parent_entity_id"] not in seen:
            raise CompanyScopeError(f"parent_entity_id is unknown: {item['object_id']}")
    return result


def _normalise_facts(raw: Any, objects: Mapping[str, Mapping[str, Any]], as_of: date) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise CompanyScopeError("facts must be a list")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise CompanyScopeError("each scope fact must be an object")
        fact_id = str(item.get("fact_id") or f"scope-fact-{index + 1}").strip()
        object_id = str(item.get("object_id") or item.get("entity_id") or "").strip()
        field = str(item.get("field") or "").strip()
        if not fact_id or not object_id or not field:
            raise CompanyScopeError("scope fact requires fact_id, object_id, and field")
        if fact_id in seen:
            raise CompanyScopeError(f"duplicate fact_id: {fact_id}")
        if object_id not in objects:
            raise CompanyScopeError(f"scope fact references unknown object: {object_id}")
        transmission = str(item.get("transmission_to_listed") or "UNKNOWN").upper()
        if transmission not in TRANSMISSION_STATES:
            raise CompanyScopeError(f"unsupported transmission_to_listed: {transmission}")
        object_type = objects[object_id]["object_type"]
        if object_type in {"Associate", "Unconsolidated", "RelatedParty"} and transmission in {"DIRECT", "CONSOLIDATED"}:
            raise CompanyScopeError(
                f"{object_type} fact cannot use {transmission} transmission without an explicit bridge: {fact_id}"
            )
        fact_as_of = _parse_day(item.get("as_of") or as_of.isoformat(), f"fact {fact_id}.as_of")
        if fact_as_of > as_of:
            raise CompanyScopeError(f"scope fact is after as_of: {fact_id}")
        evidence_ids = _string_list(item.get("evidence_ids") or item.get("source_evidence_ids"))
        if not evidence_ids:
            raise CompanyScopeError(f"scope fact requires evidence_ids: {fact_id}")
        seen.add(fact_id)
        result.append({
            "fact_id": fact_id,
            "object_id": object_id,
            "field": field,
            "value": item.get("value"),
            "unit": str(item.get("unit") or ""),
            "period": str(item.get("period") or ""),
            "accounting_basis": str(item.get("accounting_basis") or objects[object_id]["consolidation_method"]),
            "transmission_to_listed": transmission,
            "evidence_ids": evidence_ids,
            "as_of": fact_as_of.isoformat(),
            "verification_status": str(item.get("verification_status") or "UNVERIFIED").upper(),
            "note": str(item.get("note") or ""),
        })
    return result


def _field_status(
    field: str,
    facts: Sequence[Mapping[str, Any]],
    listed_id: str,
    objects: Mapping[str, Mapping[str, Any]],
) -> str:
    matches = [item for item in facts if item["field"] == field]
    if not matches:
        return "MISSING"
    values_by_object: dict[str, set[str]] = {}
    for item in matches:
        values_by_object.setdefault(str(item["object_id"]), set()).add(
            json.dumps(item.get("value"), ensure_ascii=False, sort_keys=True, default=str)
        )
    if any(len(values) > 1 for values in values_by_object.values()):
        return "CONFLICTING"
    if any(str(item.get("verification_status") or "").upper() == "CONFLICTING" for item in matches):
        return "CONFLICTING"
    if any(
        item["object_id"] == listed_id
        and item["transmission_to_listed"] == "DIRECT"
        for item in matches
    ):
        return "VERIFIED"
    if any(
        item["transmission_to_listed"] == "CONSOLIDATED"
        and objects.get(item["object_id"], {}).get("object_type") == "ConsolidatedGroup"
        for item in matches
    ):
        return "VERIFIED"
    if any(item["transmission_to_listed"] == "EQUITY_METHOD" for item in matches):
        return "PARTIAL"
    return "UNVERIFIED"


def _normalise_fields(fields: Sequence[str]) -> tuple[str, ...]:
    if isinstance(fields, (str, bytes, bytearray)):
        raise CompanyScopeError("required_fields must be a string list")
    values = tuple(dict.fromkeys(str(item).strip() for item in fields))
    if not values or any(not item for item in values):
        raise CompanyScopeError("required_fields must contain non-empty names")
    return values


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise CompanyScopeError("evidence_ids must be a string list")
    return [str(item).strip() for item in value if str(item).strip()]


def _parse_day(value: Any, field: str) -> date:
    text = str(value or "").strip()
    if not text:
        raise CompanyScopeError(f"{field} is required")
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError as error:
            raise CompanyScopeError(f"{field} must be an ISO date or datetime") from error


def _hash_payload(payload: Mapping[str, Any]) -> str:
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
