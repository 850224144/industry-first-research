"""Build a conservative, evidence-only product economics profile."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


class ProductProfileError(ValueError):
    """Raised when a product profile cannot be derived safely."""


PRODUCT_PROFILE_SCHEMA_VERSION = "company-product-profile.v1"
RULE_VERSION = "company-product-profile-rules.v1"
DEFAULT_REQUIRED_FIELDS = (
    "product_list",
    "product_application",
    "customer_purchase_reasons",
    "product_system_layer",
    "product_criticality",
    "substitution_risk",
    "competitors",
    "market_state",
    "profit_sources",
    "product_financial_bridge",
    "lifecycle_state",
    "validation_state",
)
_QUEUE_STATES = {"WATCH", "REVIEW", "CANDIDATE", "INSUFFICIENT", "REJECTED"}
_SUPPLEMENTAL_STATES = {"READY", "PARTIAL", "INSUFFICIENT", "BLOCKED"}


def build_product_profile_report(
    supplemental_report: Mapping[str, Any],
    *,
    required_fields: Sequence[str] = DEFAULT_REQUIRED_FIELDS,
    rule_version: str = RULE_VERSION,
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Derive product/profile coverage without inferring business conclusions."""

    if not isinstance(supplemental_report, Mapping):
        raise ProductProfileError("input supplemental report must be a JSON object")
    if supplemental_report.get("schema_version") != (
        "company-supplemental-evidence.v1"
    ):
        raise ProductProfileError(
            "input must be a company-supplemental-evidence.v1 report"
        )
    if not isinstance(supplemental_report.get("items"), list):
        raise ProductProfileError("supplemental report has no items list")
    fields = _normalise_fields(required_fields)
    if not rule_version.strip():
        raise ProductProfileError("rule_version must not be empty")

    records = _normalise_records(supplemental_report.get("records") or [])
    items = []
    for raw_item in supplemental_report["items"]:
        if not isinstance(raw_item, Mapping):
            raise ProductProfileError("each supplemental item must be an object")
        company_id = str(raw_item.get("company_id") or "").strip()
        if not company_id:
            raise ProductProfileError("supplemental item company_id is required")
        candidate_state = str(raw_item.get("candidate_state") or "").upper()
        supplemental_state = str(raw_item.get("supplemental_state") or "").upper()
        if candidate_state not in _QUEUE_STATES:
            raise ProductProfileError(
                f"unsupported candidate_state: {candidate_state or '<empty>'}"
            )
        if supplemental_state not in _SUPPLEMENTAL_STATES:
            raise ProductProfileError(
                f"unsupported supplemental_state: {supplemental_state or '<empty>'}"
            )
        company_records = [
            record for record in records if record["company_id"] == company_id
        ]
        items.append(
            _build_item(
                raw_item,
                company_records,
                required_fields=fields,
                rule_version=rule_version,
            )
        )

    counts = Counter(item["product_profile_state"] for item in items)
    input_report_id = str(supplemental_report.get("report_id") or "")
    report_id = snapshot_id or input_report_id or "supplemental-input"
    return {
        "schema_version": PRODUCT_PROFILE_SCHEMA_VERSION,
        "report_id": f"company-product-profile-{report_id}",
        "input_supplemental_id": input_report_id,
        "input_queue_id": str(supplemental_report.get("input_queue_id") or ""),
        "input_snapshot_id": str(
            supplemental_report.get("input_snapshot_id") or ""
        ),
        "rule_version": rule_version,
        "as_of": str(supplemental_report.get("as_of") or ""),
        "source": str(supplemental_report.get("source") or ""),
        "source_metadata": supplemental_report.get("source_metadata") or {},
        "required_fields": list(fields),
        "candidate_count": len(items),
        "profile_state_counts": dict(counts),
        "items": items,
        "policy": {
            "product_profile_only": True,
            "evidence_only": True,
            "candidate_state_preserved": True,
            "downstream_modules_require_ready": True,
            "financial_analysis_included": False,
            "valuation_included": False,
            "investment_conclusion": False,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _build_item(
    item: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    *,
    required_fields: Sequence[str],
    rule_version: str,
) -> dict[str, Any]:
    company_id = str(item.get("company_id") or "").strip()
    candidate_state = str(item.get("candidate_state") or "").upper()
    supplemental_state = str(item.get("supplemental_state") or "").upper()
    fields = {
        field: _field_summary(field, records)
        for field in _unique(
            ["company_scope", *required_fields, *(record["field"] for record in records)]
        )
    }
    required_product_fields = [field for field in required_fields if field != "company_scope"]
    verified_fields = [
        field
        for field in required_product_fields
        if fields[field]["status"] == "VERIFIED"
    ]
    unverified_fields = [
        field
        for field in required_product_fields
        if fields[field]["status"] in {"UNVERIFIED", "CONFLICTING"}
    ]
    unknowns = [
        field for field in required_product_fields if fields[field]["status"] == "MISSING"
    ]
    scope_status = fields["company_scope"]["status"]
    product_profile_state = _profile_state(
        candidate_state=candidate_state,
        supplemental_state=supplemental_state,
        scope_status=scope_status,
        has_records=bool(records),
        verified_count=len(verified_fields),
        required_count=len(required_product_fields),
        unknowns=unknowns,
    )
    if product_profile_state == "READY":
        reasons = ["PRODUCT_PROFILE_FIELDS_COVERED"]
    elif product_profile_state == "PARTIAL":
        reasons = ["PRODUCT_PROFILE_REQUIRES_DEGRADED_RESEARCH"]
    elif product_profile_state == "INSUFFICIENT":
        reasons = ["PRODUCT_EVIDENCE_SUPPORTS_SCREENING_ONLY"]
    else:
        reasons = ["PRODUCT_PROFILE_BLOCKED"]

    return {
        "company_id": company_id,
        "display_name": str(item.get("display_name") or ""),
        "industry_id": str(item.get("industry_id") or ""),
        "candidate_state": candidate_state,
        "candidate_state_changed": False,
        "candidate_rule_version": str(item.get("candidate_rule_version") or ""),
        "candidate_reasons": _string_list(item.get("candidate_reasons")),
        "candidate_blockers": _string_list(item.get("candidate_blockers")),
        "candidate_evidence_gaps": _string_list(item.get("candidate_evidence_gaps")),
        "candidate_field_sources": _field_sources(
            item.get("candidate_field_sources")
        ),
        "candidate_additional_sources": _string_list(
            item.get("candidate_additional_sources")
        ),
        "supplemental_state": supplemental_state,
        "product_profile_state": product_profile_state,
        "scope_state": scope_status,
        "rule_version": rule_version,
        "fields": fields,
        "verified_fields": verified_fields,
        "unverified_fields": unverified_fields,
        "unknowns": unknowns,
        "evidence_ids": [str(record["evidence_id"]) for record in records],
        "reasons": reasons,
        "downstream_modules": {
            "application_transmission": "READY_REQUIRED",
            "industry_cycle": "READY_REQUIRED",
            "survival_analysis": "READY_REQUIRED",
            "valuation": "READY_REQUIRED",
            "decision_snapshot": "READY_REQUIRED",
        },
        "allowed_actions": _allowed_actions(product_profile_state),
        "prohibited_actions": [
            "application_conclusion",
            "financial_analysis",
            "valuation",
            "investment_conclusion",
            "automatic_candidate_promotion",
            "execution",
        ],
        "review_only": True,
        "investment_conclusion": False,
    }


def _profile_state(
    *,
    candidate_state: str,
    supplemental_state: str,
    scope_status: str,
    has_records: bool,
    verified_count: int,
    required_count: int,
    unknowns: Sequence[str],
) -> str:
    if candidate_state == "REJECTED" or supplemental_state == "BLOCKED":
        return "BLOCKED"
    if scope_status in {"MISSING", "CONFLICTING"}:
        return "BLOCKED"
    if (
        candidate_state == "INSUFFICIENT"
        or supplemental_state == "INSUFFICIENT"
        or not has_records
    ):
        return "INSUFFICIENT"
    if verified_count == required_count and not unknowns and scope_status == "VERIFIED":
        return "READY"
    return "PARTIAL"


def _allowed_actions(state: str) -> list[str]:
    return {
        "READY": ["application_mapping", "evidence_refresh"],
        "PARTIAL": ["product_gap_review", "evidence_refresh"],
        "INSUFFICIENT": ["product_evidence_collection", "evidence_refresh"],
        "BLOCKED": ["scope_resolution", "evidence_refresh"],
    }[state]


def _normalise_fields(fields: Sequence[str]) -> tuple[str, ...]:
    if isinstance(fields, (str, bytes, bytearray)):
        raise ProductProfileError("required_fields must be a string list")
    try:
        normalised = tuple(dict.fromkeys(str(field).strip() for field in fields))
    except TypeError as error:
        raise ProductProfileError("required_fields must be a string list") from error
    if not normalised or any(not field for field in normalised):
        raise ProductProfileError("required_fields must contain non-empty names")
    if "company_scope" in normalised:
        return normalised
    return ("company_scope", *normalised)


def _normalise_records(raw_records: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_records, list):
        raise ProductProfileError("supplemental records must be a list")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_record in raw_records:
        if not isinstance(raw_record, Mapping):
            raise ProductProfileError("supplemental records must be objects")
        evidence_id = str(raw_record.get("evidence_id") or "").strip()
        company_id = str(raw_record.get("company_id") or "").strip()
        field = str(raw_record.get("field") or "").strip()
        if not evidence_id or not company_id or not field:
            raise ProductProfileError(
                "supplemental records require evidence_id, company_id, and field"
            )
        if evidence_id in seen:
            raise ProductProfileError(f"duplicate evidence_id: {evidence_id}")
        seen.add(evidence_id)
        records.append(
            {
                "evidence_id": evidence_id,
                "company_id": company_id,
                "field": field,
                "value": raw_record.get("value"),
                "source": str(raw_record.get("source") or ""),
                "as_of": str(raw_record.get("as_of") or ""),
                "evidence_tier": str(raw_record.get("evidence_tier") or "").upper(),
                "verification_status": str(
                    raw_record.get("verification_status") or ""
                ).upper(),
            }
        )
    return records


def _field_summary(field: str, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    field_records = [record for record in records if record["field"] == field]
    if not field_records:
        return {
            "status": "MISSING",
            "values": [],
            "evidence_ids": [],
            "sources": [],
            "as_of": [],
            "evidence_tiers": [],
        }
    if any(record["verification_status"] == "CONFLICTING" for record in field_records):
        status = "CONFLICTING"
    elif any(
        record["verification_status"] == "VERIFIED"
        and record["evidence_tier"] in {"A", "B"}
        for record in field_records
    ):
        status = "VERIFIED"
    else:
        status = "UNVERIFIED"
    return {
        "status": status,
        "values": [record["value"] for record in field_records],
        "evidence_ids": [record["evidence_id"] for record in field_records],
        "sources": [record["source"] for record in field_records],
        "as_of": [record["as_of"] for record in field_records],
        "evidence_tiers": [record["evidence_tier"] for record in field_records],
    }


def _field_sources(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ProductProfileError("field_sources must be a string mapping")
    return {
        str(field): str(source).strip()
        for field, source in value.items()
        if str(field).strip() and str(source).strip()
    }


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise ProductProfileError("product profile fields must be string lists")
    return [str(item) for item in value if str(item)]


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
