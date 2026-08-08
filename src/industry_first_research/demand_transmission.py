"""Build a conservative, evidence-only demand transmission gate."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


class DemandTransmissionError(ValueError):
    """Raised when a demand transmission report cannot be derived safely."""


DEMAND_TRANSMISSION_SCHEMA_VERSION = "company-demand-transmission.v1"
RULE_VERSION = "company-demand-transmission-rules.v1"
APPLICATION_MAPPING_SCHEMA_VERSION = "company-application-mapping.v1"
DEFAULT_REQUIRED_FIELDS = (
    "demand_evidence",
    "technical_feasibility",
    "customer_validation",
    "order_evidence",
    "shipment_revenue_evidence",
    "profit_cashflow_evidence",
    "company_supply_capability",
    "company_share_evidence",
    "competitive_capture",
    "base_case_contribution",
    "upside_option",
    "invalidators",
    "transmission_state",
)
_GATE_STATES = {"READY", "PARTIAL", "INSUFFICIENT", "BLOCKED"}
_QUEUE_STATES = {"WATCH", "REVIEW", "CANDIDATE", "INSUFFICIENT", "REJECTED"}
TRANSMISSION_STATES = (
    "CONCEPT_LINKED",
    "TECHNICALLY_FEASIBLE",
    "CUSTOMER_QUALIFIED",
    "ORDER_VALIDATED",
    "REVENUE_VALIDATED",
    "PROFIT_VALIDATED",
    "COMPETITIVE_VALIDATED",
)
_STATE_INDEX = {state: index for index, state in enumerate(TRANSMISSION_STATES)}
_STATE_SUPPORT = {
    "CONCEPT_LINKED": ("demand_evidence",),
    "TECHNICALLY_FEASIBLE": ("demand_evidence", "technical_feasibility"),
    "CUSTOMER_QUALIFIED": (
        "demand_evidence",
        "technical_feasibility",
        "customer_validation",
    ),
    "ORDER_VALIDATED": (
        "demand_evidence",
        "technical_feasibility",
        "customer_validation",
        "order_evidence",
    ),
    "REVENUE_VALIDATED": (
        "demand_evidence",
        "technical_feasibility",
        "customer_validation",
        "order_evidence",
        "shipment_revenue_evidence",
    ),
    "PROFIT_VALIDATED": (
        "demand_evidence",
        "technical_feasibility",
        "customer_validation",
        "order_evidence",
        "shipment_revenue_evidence",
        "profit_cashflow_evidence",
    ),
    "COMPETITIVE_VALIDATED": (
        "demand_evidence",
        "technical_feasibility",
        "customer_validation",
        "order_evidence",
        "shipment_revenue_evidence",
        "profit_cashflow_evidence",
        "competitive_capture",
    ),
}


def build_demand_transmission_report(
    application_mapping_report: Mapping[str, Any],
    *,
    required_fields: Sequence[str] = DEFAULT_REQUIRED_FIELDS,
    rule_version: str = RULE_VERSION,
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Assess demand transmission without creating revenue or investment claims."""

    _validate_report(application_mapping_report)
    fields = _normalise_fields(required_fields)
    if not rule_version.strip():
        raise DemandTransmissionError("rule_version must not be empty")

    items = [
        _build_item(item, required_fields=fields, rule_version=rule_version)
        for item in application_mapping_report["items"]
    ]
    counts = Counter(item["transmission_gate_state"] for item in items)
    input_report_id = str(application_mapping_report.get("report_id") or "")
    report_id = snapshot_id or input_report_id or "application-mapping-input"
    return {
        "schema_version": DEMAND_TRANSMISSION_SCHEMA_VERSION,
        "report_id": f"company-demand-transmission-{report_id}",
        "input_application_mapping_id": input_report_id,
        "input_product_profile_id": str(
            application_mapping_report.get("input_product_profile_id") or ""
        ),
        "input_supplemental_id": str(
            application_mapping_report.get("input_supplemental_id") or ""
        ),
        "input_queue_id": str(application_mapping_report.get("input_queue_id") or ""),
        "input_snapshot_id": str(
            application_mapping_report.get("input_snapshot_id") or ""
        ),
        "rule_version": rule_version,
        "as_of": str(application_mapping_report.get("as_of") or ""),
        "source": str(application_mapping_report.get("source") or ""),
        "source_metadata": application_mapping_report.get("source_metadata") or {},
        "required_fields": list(fields),
        "candidate_count": len(items),
        "transmission_state_counts": dict(counts),
        "items": items,
        "policy": {
            "demand_transmission_only": True,
            "evidence_only": True,
            "application_mapping_ready_required": True,
            "candidate_state_preserved": True,
            "base_case_valuation_included": False,
            "upside_option_valuation_included": False,
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
        raise DemandTransmissionError(
            "input application mapping report must be a JSON object"
        )
    if report.get("schema_version") != APPLICATION_MAPPING_SCHEMA_VERSION:
        raise DemandTransmissionError(
            "input must be a company-application-mapping.v1 report"
        )
    if not isinstance(report.get("items"), list):
        raise DemandTransmissionError("application mapping report has no items list")


def _build_item(
    item: Any,
    *,
    required_fields: Sequence[str],
    rule_version: str,
) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise DemandTransmissionError("each application mapping item must be an object")
    company_id = str(item.get("company_id") or "").strip()
    candidate_state = str(item.get("candidate_state") or "").upper()
    mapping_state = str(item.get("mapping_state") or "").upper()
    if not company_id:
        raise DemandTransmissionError("application mapping item company_id is required")
    if candidate_state not in _QUEUE_STATES:
        raise DemandTransmissionError(
            f"unsupported candidate_state: {candidate_state or '<empty>'}"
        )
    if mapping_state not in _GATE_STATES:
        raise DemandTransmissionError(
            f"unsupported mapping_state: {mapping_state or '<empty>'}"
        )

    raw_fields = item.get("fields")
    if not isinstance(raw_fields, Mapping):
        raise DemandTransmissionError("application mapping item has no fields mapping")
    fields = {
        field: _normalise_field_summary(field, raw_fields.get(field))
        for field in _unique([*required_fields, *map(str, raw_fields.keys())])
    }
    verified_fields = [
        field for field in required_fields if _is_verified(fields[field])
    ]
    unverified_fields = [
        field
        for field in required_fields
        if fields[field]["status"] in {"UNVERIFIED", "CONFLICTING"}
    ]
    unknowns = [
        field for field in required_fields if fields[field]["status"] == "MISSING"
    ]
    claimed_state = _claimed_state(fields["transmission_state"])
    max_supported_state = _max_supported_state(fields)
    state_validation = _validate_claimed_state(
        claimed_state, max_supported_state, fields
    )
    gate_state, reasons = _gate_state(
        candidate_state=candidate_state,
        mapping_state=mapping_state,
        fields=fields,
        required_fields=required_fields,
        claimed_state=claimed_state,
        state_validation=state_validation,
    )
    evidence_ids = _unique(
        [
            *map(str, item.get("evidence_ids") or []),
            *(
                evidence_id
                for field in fields.values()
                for evidence_id in field["evidence_ids"]
            ),
        ]
    )
    return {
        "company_id": company_id,
        "company_scope": item.get("company_scope"),
        "display_name": str(item.get("display_name") or ""),
        "industry_id": str(item.get("industry_id") or ""),
        "candidate_state": candidate_state,
        "candidate_state_changed": False,
        "candidate_rule_version": str(item.get("candidate_rule_version") or ""),
        "application_mapping_state": mapping_state,
        "mapping_rule_version": str(item.get("rule_version") or ""),
        "transmission_gate_state": gate_state,
        "transmission_state": claimed_state,
        "max_evidence_supported_state": max_supported_state,
        "state_validation": state_validation,
        "rule_version": rule_version,
        "fields": fields,
        "verified_fields": verified_fields,
        "unverified_fields": unverified_fields,
        "unknowns": unknowns,
        "evidence_ids": evidence_ids,
        "base_case_treatment": _base_case_treatment(claimed_state),
        "reasons": reasons,
        "downstream_modules": {
            "industry_cycle": "READY_REQUIRED",
            "survival_analysis": "READY_REQUIRED",
            "valuation": "READY_REQUIRED",
            "decision_snapshot": "READY_REQUIRED",
        },
        "allowed_actions": _allowed_actions(gate_state),
        "prohibited_actions": [
            "base_case_earnings_forecast",
            "upside_option_valuation",
            "financial_analysis",
            "valuation",
            "investment_conclusion",
            "automatic_candidate_promotion",
            "execution",
        ],
        "review_only": True,
        "investment_conclusion": False,
    }


def _gate_state(
    *,
    candidate_state: str,
    mapping_state: str,
    fields: Mapping[str, Mapping[str, Any]],
    required_fields: Sequence[str],
    claimed_state: str,
    state_validation: str,
) -> tuple[str, list[str]]:
    if candidate_state == "REJECTED" or mapping_state == "BLOCKED":
        return "BLOCKED", ["APPLICATION_MAPPING_BLOCKED"]
    if mapping_state != "READY":
        if mapping_state == "INSUFFICIENT":
            return "INSUFFICIENT", ["APPLICATION_MAPPING_INSUFFICIENT"]
        return "BLOCKED", ["APPLICATION_MAPPING_READY_REQUIRED"]
    if state_validation == "CONFLICTING":
        return "BLOCKED", ["TRANSMISSION_STATE_CONFLICT"]
    if claimed_state == "UNKNOWN":
        if not _is_verified(fields["demand_evidence"]):
            return "INSUFFICIENT", ["DEMAND_EVIDENCE_MISSING"]
        return "PARTIAL", ["TRANSMISSION_STATE_MISSING"]
    if not _is_verified(fields["demand_evidence"]):
        return "INSUFFICIENT", ["DEMAND_EVIDENCE_MISSING"]
    if any(not _is_verified(fields[field]) for field in required_fields):
        return "PARTIAL", ["TRANSMISSION_EVIDENCE_INCOMPLETE"]
    return "READY", ["TRANSMISSION_EVIDENCE_COVERED"]


def _claimed_state(summary: Mapping[str, Any]) -> str:
    if not _is_verified(summary):
        return "UNKNOWN"
    values = summary["values"]
    if len(values) != 1:
        raise DemandTransmissionError(
            "transmission_state evidence must contain exactly one value"
        )
    value = values[0]
    if isinstance(value, Mapping):
        value = value.get("state")
    state = str(value or "").strip().upper()
    if state not in _STATE_INDEX:
        raise DemandTransmissionError(
            f"unsupported transmission_state: {state or '<empty>'}"
        )
    return state


def _max_supported_state(fields: Mapping[str, Mapping[str, Any]]) -> str:
    supported = "UNKNOWN"
    for state in TRANSMISSION_STATES:
        if all(_is_verified(fields[field]) for field in _STATE_SUPPORT[state]):
            supported = state
    return supported


def _validate_claimed_state(
    claimed_state: str,
    max_supported_state: str,
    fields: Mapping[str, Mapping[str, Any]],
) -> str:
    if fields["transmission_state"]["status"] == "CONFLICTING":
        return "CONFLICTING"
    if claimed_state == "UNKNOWN":
        return "MISSING"
    if max_supported_state == "UNKNOWN":
        return "CONFLICTING"
    if _STATE_INDEX[claimed_state] > _STATE_INDEX[max_supported_state]:
        return "CONFLICTING"
    return "SUPPORTED"


def _base_case_treatment(state: str) -> str:
    if state in {"PROFIT_VALIDATED", "COMPETITIVE_VALIDATED"}:
        return "EVIDENCE_BACKED_PROFIT_CONTRIBUTION"
    if state == "REVENUE_VALIDATED":
        return "EVIDENCE_BACKED_REVENUE_ONLY"
    if state in {
        "CONCEPT_LINKED",
        "TECHNICALLY_FEASIBLE",
        "CUSTOMER_QUALIFIED",
        "ORDER_VALIDATED",
    }:
        return "UPSIDE_OPTION_ONLY"
    return "UNKNOWN_UNTIL_VALIDATED"


def _allowed_actions(state: str) -> list[str]:
    return {
        "READY": ["transmission_review", "evidence_refresh"],
        "PARTIAL": ["transmission_gap_review", "evidence_refresh"],
        "INSUFFICIENT": ["transmission_evidence_collection", "evidence_refresh"],
        "BLOCKED": ["application_mapping_resolution", "evidence_refresh"],
    }[state]


def _normalise_fields(fields: Sequence[str]) -> tuple[str, ...]:
    if isinstance(fields, (str, bytes, bytearray)):
        raise DemandTransmissionError("required_fields must be a string list")
    try:
        normalised = tuple(dict.fromkeys(str(field).strip() for field in fields))
    except TypeError as error:
        raise DemandTransmissionError("required_fields must be a string list") from error
    if not normalised or any(not field for field in normalised):
        raise DemandTransmissionError("required_fields must contain non-empty names")
    if "transmission_state" not in normalised:
        return ("transmission_state", *normalised)
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
        raise DemandTransmissionError(f"field summary must be an object: {field}")
    status = str(raw_summary.get("status") or "MISSING").upper()
    if status not in {"MISSING", "VERIFIED", "UNVERIFIED", "CONFLICTING"}:
        raise DemandTransmissionError(f"unsupported field status: {status}")
    return {
        "status": status,
        "values": raw_summary.get("values") or [],
        "evidence_ids": _string_list(raw_summary.get("evidence_ids")),
        "sources": _string_list(raw_summary.get("sources")),
        "as_of": _string_list(raw_summary.get("as_of")),
        "evidence_tiers": _string_list(raw_summary.get("evidence_tiers")),
    }


def _is_verified(summary: Mapping[str, Any]) -> bool:
    return summary["status"] == "VERIFIED" and any(
        tier in {"A", "B"} for tier in summary["evidence_tiers"]
    )


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise DemandTransmissionError("demand transmission fields must be string lists")
    return [str(item) for item in value if str(item)]


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
