"""Build a conservative product-to-application evidence mapping."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


class ApplicationMappingError(ValueError):
    """Raised when an application mapping cannot be derived safely."""


APPLICATION_MAPPING_SCHEMA_VERSION = "company-application-mapping.v1"
RULE_VERSION = "company-application-mapping-rules.v1"
PRODUCT_PROFILE_SCHEMA_VERSION = "company-product-profile.v1"
DEFAULT_REQUIRED_FIELDS = (
    "application_mapping",
    "application_end_market",
    "demand_driver",
    "customer_type",
    "customer_validation",
    "order_evidence",
    "shipment_revenue_evidence",
    "company_supply_capability",
    "application_competition",
    "transmission_state",
)
_PROFILE_STATES = {"READY", "PARTIAL", "INSUFFICIENT", "BLOCKED"}
_QUEUE_STATES = {"WATCH", "REVIEW", "CANDIDATE", "INSUFFICIENT", "REJECTED"}
_TRANSMISSION_STATES = {
    "CONCEPT_LINKED",
    "TECHNICALLY_FEASIBLE",
    "CUSTOMER_QUALIFIED",
    "ORDER_VALIDATED",
    "REVENUE_VALIDATED",
    "PROFIT_VALIDATED",
    "COMPETITIVE_VALIDATED",
}
_MAPPING_ENTRY_FIELDS = ("product", "application", "end_market")


def build_application_mapping_report(
    product_profile_report: Mapping[str, Any],
    *,
    required_fields: Sequence[str] = DEFAULT_REQUIRED_FIELDS,
    rule_version: str = RULE_VERSION,
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Derive only explicit product/application relations and their coverage."""

    _validate_report(product_profile_report)
    fields = _normalise_fields(required_fields)
    if not rule_version.strip():
        raise ApplicationMappingError("rule_version must not be empty")

    items = []
    for raw_item in product_profile_report["items"]:
        if not isinstance(raw_item, Mapping):
            raise ApplicationMappingError("each product profile item must be an object")
        items.append(
            _build_item(
                raw_item,
                required_fields=fields,
                rule_version=rule_version,
            )
        )

    counts = Counter(item["mapping_state"] for item in items)
    input_report_id = str(product_profile_report.get("report_id") or "")
    report_id = snapshot_id or input_report_id or "product-profile-input"
    return {
        "schema_version": APPLICATION_MAPPING_SCHEMA_VERSION,
        "report_id": f"company-application-mapping-{report_id}",
        "input_product_profile_id": input_report_id,
        "input_supplemental_id": str(
            product_profile_report.get("input_supplemental_id") or ""
        ),
        "input_queue_id": str(product_profile_report.get("input_queue_id") or ""),
        "input_snapshot_id": str(
            product_profile_report.get("input_snapshot_id") or ""
        ),
        "rule_version": rule_version,
        "as_of": str(product_profile_report.get("as_of") or ""),
        "source": str(product_profile_report.get("source") or ""),
        "source_metadata": product_profile_report.get("source_metadata") or {},
        "required_fields": list(fields),
        "candidate_count": len(items),
        "mapping_state_counts": dict(counts),
        "items": items,
        "policy": {
            "application_mapping_only": True,
            "evidence_only": True,
            "product_profile_ready_required": True,
            "candidate_state_preserved": True,
            "transmission_analysis_included": False,
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


def _validate_report(report: Any) -> None:
    if not isinstance(report, Mapping):
        raise ApplicationMappingError("input product profile report must be a JSON object")
    if report.get("schema_version") != PRODUCT_PROFILE_SCHEMA_VERSION:
        raise ApplicationMappingError(
            "input must be a company-product-profile.v1 report"
        )
    if not isinstance(report.get("items"), list):
        raise ApplicationMappingError("product profile report has no items list")


def _build_item(
    item: Mapping[str, Any],
    *,
    required_fields: Sequence[str],
    rule_version: str,
) -> dict[str, Any]:
    company_id = str(item.get("company_id") or "").strip()
    if not company_id:
        raise ApplicationMappingError("product profile item company_id is required")
    candidate_state = str(item.get("candidate_state") or "").upper()
    profile_state = str(item.get("product_profile_state") or "").upper()
    scope_state = str(item.get("scope_state") or "").upper()
    if candidate_state not in _QUEUE_STATES:
        raise ApplicationMappingError(
            f"unsupported candidate_state: {candidate_state or '<empty>'}"
        )
    if profile_state not in _PROFILE_STATES:
        raise ApplicationMappingError(
            f"unsupported product_profile_state: {profile_state or '<empty>'}"
        )

    raw_fields = item.get("fields")
    if not isinstance(raw_fields, Mapping):
        raise ApplicationMappingError("product profile item has no fields mapping")
    fields = {
        field: _normalise_field_summary(field, raw_fields.get(field))
        for field in _unique([*required_fields, *map(str, raw_fields.keys())])
    }
    verified_fields = [
        field for field in required_fields if fields[field]["status"] == "VERIFIED"
    ]
    unverified_fields = [
        field
        for field in required_fields
        if fields[field]["status"] in {"UNVERIFIED", "CONFLICTING"}
    ]
    unknowns = [
        field for field in required_fields if fields[field]["status"] == "MISSING"
    ]
    mapping_entries = _mapping_entries(fields["application_mapping"])
    mapping_state, reasons = _mapping_state(
        candidate_state=candidate_state,
        profile_state=profile_state,
        scope_state=scope_state,
        fields=fields,
        required_fields=required_fields,
        mapping_entries=mapping_entries,
        unknowns=unknowns,
    )

    return {
        "company_id": company_id,
        "display_name": str(item.get("display_name") or ""),
        "industry_id": str(item.get("industry_id") or ""),
        "candidate_state": candidate_state,
        "candidate_state_changed": False,
        "candidate_rule_version": str(item.get("candidate_rule_version") or ""),
        "product_profile_state": profile_state,
        "scope_state": scope_state,
        "product_profile_rule_version": str(item.get("rule_version") or ""),
        "mapping_state": mapping_state,
        "rule_version": rule_version,
        "fields": fields,
        "mapping_entries": mapping_entries,
        "verified_fields": verified_fields,
        "unverified_fields": unverified_fields,
        "unknowns": unknowns,
        "evidence_ids": _string_list(item.get("evidence_ids")),
        "reasons": reasons,
        "downstream_modules": {
            "demand_transmission": "READY_REQUIRED",
            "industry_cycle": "READY_REQUIRED",
            "survival_analysis": "READY_REQUIRED",
            "valuation": "READY_REQUIRED",
            "decision_snapshot": "READY_REQUIRED",
        },
        "allowed_actions": _allowed_actions(mapping_state),
        "prohibited_actions": [
            "demand_transmission_conclusion",
            "financial_analysis",
            "valuation",
            "investment_conclusion",
            "automatic_candidate_promotion",
            "execution",
        ],
        "review_only": True,
        "investment_conclusion": False,
    }


def _mapping_state(
    *,
    candidate_state: str,
    profile_state: str,
    scope_state: str,
    fields: Mapping[str, Mapping[str, Any]],
    required_fields: Sequence[str],
    mapping_entries: Sequence[Mapping[str, Any]],
    unknowns: Sequence[str],
) -> tuple[str, list[str]]:
    if candidate_state == "REJECTED" or profile_state == "BLOCKED":
        return "BLOCKED", ["PRODUCT_PROFILE_BLOCKED"]
    if scope_state in {"MISSING", "CONFLICTING"}:
        return "BLOCKED", ["COMPANY_SCOPE_NOT_VERIFIED"]
    if profile_state != "READY":
        return "BLOCKED", ["PRODUCT_PROFILE_READY_REQUIRED"]
    if fields["application_mapping"]["status"] == "CONFLICTING":
        return "BLOCKED", ["APPLICATION_MAPPING_CONFLICT"]
    if not mapping_entries:
        return "INSUFFICIENT", ["EXPLICIT_APPLICATION_MAPPING_MISSING"]
    if unknowns:
        return "PARTIAL", ["APPLICATION_MAPPING_EVIDENCE_INCOMPLETE"]
    if any(
        fields[field]["status"] in {"UNVERIFIED", "CONFLICTING"}
        for field in required_fields
    ):
        return "PARTIAL", ["APPLICATION_MAPPING_EVIDENCE_UNVERIFIED"]
    return "READY", ["APPLICATION_MAPPING_FIELDS_COVERED"]


def _normalise_fields(fields: Sequence[str]) -> tuple[str, ...]:
    if isinstance(fields, (str, bytes, bytearray)):
        raise ApplicationMappingError("required_fields must be a string list")
    try:
        normalised = tuple(dict.fromkeys(str(field).strip() for field in fields))
    except TypeError as error:
        raise ApplicationMappingError("required_fields must be a string list") from error
    if not normalised or any(not field for field in normalised):
        raise ApplicationMappingError("required_fields must contain non-empty names")
    if "application_mapping" not in normalised:
        return ("application_mapping", *normalised)
    return normalised


def _normalise_field_summary(field: str, raw_summary: Any) -> dict[str, Any]:
    if raw_summary is None:
        return {
            "status": "MISSING",
            "values": [],
            "evidence_ids": [],
            "sources": [],
            "as_of": [],
            "evidence_tiers": [],
        }
    if not isinstance(raw_summary, Mapping):
        raise ApplicationMappingError(f"field summary must be an object: {field}")
    status = str(raw_summary.get("status") or "MISSING").upper()
    if status not in {"MISSING", "VERIFIED", "UNVERIFIED", "CONFLICTING"}:
        raise ApplicationMappingError(f"unsupported field status: {status}")
    return {
        "status": status,
        "values": raw_summary.get("values") or [],
        "evidence_ids": _string_list(raw_summary.get("evidence_ids")),
        "sources": _string_list(raw_summary.get("sources")),
        "as_of": _string_list(raw_summary.get("as_of")),
        "evidence_tiers": _string_list(raw_summary.get("evidence_tiers")),
    }


def _mapping_entries(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    if summary["status"] != "VERIFIED":
        return []
    entries: list[dict[str, Any]] = []
    for value in summary["values"]:
        if value == []:
            continue
        if not isinstance(value, Mapping):
            raise ApplicationMappingError(
                "application_mapping evidence values must be objects"
            )
        missing = [field for field in _MAPPING_ENTRY_FIELDS if not str(value.get(field) or "").strip()]
        if missing:
            raise ApplicationMappingError(
                "application_mapping entry missing: " + ", ".join(missing)
            )
        entries.append(
            {
                "product": str(value["product"]).strip(),
                "application": str(value["application"]).strip(),
                "end_market": str(value["end_market"]).strip(),
                "role": str(value.get("role") or "").strip(),
                "demand_driver": str(value.get("demand_driver") or "").strip(),
            }
        )
    return entries


def _allowed_actions(state: str) -> list[str]:
    return {
        "READY": ["demand_transmission", "evidence_refresh"],
        "PARTIAL": ["application_gap_review", "evidence_refresh"],
        "INSUFFICIENT": ["application_evidence_collection", "evidence_refresh"],
        "BLOCKED": ["product_profile_resolution", "evidence_refresh"],
    }[state]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise ApplicationMappingError("application mapping fields must be string lists")
    return [str(item) for item in value if str(item)]


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
