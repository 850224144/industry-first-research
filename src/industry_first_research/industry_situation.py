"""Build an evidence-only industry-situation report."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


class IndustrySituationError(ValueError):
    """Raised when an industry-situation report cannot be derived safely."""


INDUSTRY_SITUATION_SCHEMA_VERSION = "company-industry-situation.v1"
RULE_VERSION = "company-industry-situation-rules.v1"
DEMAND_TRANSMISSION_SCHEMA_VERSION = "company-demand-transmission.v1"
DEFAULT_REQUIRED_FIELDS = (
    "industry_demand_horizon",
    "value_chain_profit_distribution",
    "supply_demand_state",
    "inventory_state",
    "price_state",
    "utilization_state",
    "competition_state",
    "policy_technology_overseas",
    "cycle_stage",
    "key_industry_variables",
    "reversal_conditions",
    "validation_signals",
    "product_market_state",
    "product_competition_matrix",
    "lifecycle_transition_conditions",
)
_GATE_STATES = {"READY", "PARTIAL", "INSUFFICIENT", "BLOCKED"}
_QUEUE_STATES = {"WATCH", "REVIEW", "CANDIDATE", "INSUFFICIENT", "REJECTED"}


def build_industry_situation_report(
    demand_transmission_report: Mapping[str, Any],
    *,
    required_fields: Sequence[str] = DEFAULT_REQUIRED_FIELDS,
    rule_version: str = RULE_VERSION,
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Organise industry facts without inferring a cycle reversal or valuation."""

    _validate_report(demand_transmission_report)
    fields = _normalise_fields(required_fields)
    if not rule_version.strip():
        raise IndustrySituationError("rule_version must not be empty")

    items = [
        _build_item(item, required_fields=fields, rule_version=rule_version)
        for item in demand_transmission_report["items"]
    ]
    counts = Counter(item["industry_situation_state"] for item in items)
    input_report_id = str(demand_transmission_report.get("report_id") or "")
    report_id = snapshot_id or input_report_id or "demand-transmission-input"
    return {
        "schema_version": INDUSTRY_SITUATION_SCHEMA_VERSION,
        "report_id": f"company-industry-situation-{report_id}",
        "input_demand_transmission_id": input_report_id,
        "input_application_mapping_id": str(
            demand_transmission_report.get("input_application_mapping_id") or ""
        ),
        "input_product_profile_id": str(
            demand_transmission_report.get("input_product_profile_id") or ""
        ),
        "input_supplemental_id": str(
            demand_transmission_report.get("input_supplemental_id") or ""
        ),
        "input_queue_id": str(demand_transmission_report.get("input_queue_id") or ""),
        "input_snapshot_id": str(
            demand_transmission_report.get("input_snapshot_id") or ""
        ),
        "rule_version": rule_version,
        "as_of": str(demand_transmission_report.get("as_of") or ""),
        "source": str(demand_transmission_report.get("source") or ""),
        "source_metadata": demand_transmission_report.get("source_metadata") or {},
        "required_fields": list(fields),
        "candidate_count": len(items),
        "industry_situation_state_counts": dict(counts),
        "items": items,
        "policy": {
            "industry_situation_only": True,
            "evidence_only": True,
            "demand_transmission_ready_required": True,
            "candidate_state_preserved": True,
            "cycle_reversal_analysis_included": False,
            "survival_analysis_included": False,
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
        raise IndustrySituationError(
            "input demand transmission report must be a JSON object"
        )
    if report.get("schema_version") != DEMAND_TRANSMISSION_SCHEMA_VERSION:
        raise IndustrySituationError(
            "input must be a company-demand-transmission.v1 report"
        )
    if not isinstance(report.get("items"), list):
        raise IndustrySituationError(
            "demand transmission report has no items list"
        )


def _build_item(
    item: Any,
    *,
    required_fields: Sequence[str],
    rule_version: str,
) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise IndustrySituationError(
            "each demand transmission item must be an object"
        )
    company_id = str(item.get("company_id") or "").strip()
    candidate_state = str(item.get("candidate_state") or "").upper()
    transmission_gate_state = str(
        item.get("transmission_gate_state") or ""
    ).upper()
    if not company_id:
        raise IndustrySituationError(
            "demand transmission item company_id is required"
        )
    if candidate_state not in _QUEUE_STATES:
        raise IndustrySituationError(
            f"unsupported candidate_state: {candidate_state or '<empty>'}"
        )
    if transmission_gate_state not in _GATE_STATES:
        raise IndustrySituationError(
            "unsupported transmission_gate_state: "
            f"{transmission_gate_state or '<empty>'}"
        )

    raw_fields = item.get("fields")
    if not isinstance(raw_fields, Mapping):
        raise IndustrySituationError(
            "demand transmission item has no fields mapping"
        )
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
    key_variables = _key_variables(fields["key_industry_variables"])
    industry_state, reasons = _industry_state(
        candidate_state=candidate_state,
        transmission_gate_state=transmission_gate_state,
        fields=fields,
        required_fields=required_fields,
        key_variables=key_variables,
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
        "display_name": str(item.get("display_name") or ""),
        "industry_id": str(item.get("industry_id") or ""),
        "candidate_state": candidate_state,
        "candidate_state_changed": False,
        "candidate_rule_version": str(item.get("candidate_rule_version") or ""),
        "transmission_gate_state": transmission_gate_state,
        "transmission_state": str(item.get("transmission_state") or ""),
        "industry_situation_state": industry_state,
        "rule_version": rule_version,
        "fields": fields,
        "industry_cycle_stage": _single_value(fields["cycle_stage"]),
        "key_industry_variables": key_variables,
        "reversal_conditions": _values(fields["reversal_conditions"]),
        "validation_signals": _values(fields["validation_signals"]),
        "verified_fields": verified_fields,
        "unverified_fields": unverified_fields,
        "unknowns": unknowns,
        "evidence_ids": evidence_ids,
        "reasons": reasons,
        "downstream_modules": {
            "cycle_reversal": "READY_REQUIRED",
            "survival_analysis": "READY_REQUIRED",
            "valuation": "READY_REQUIRED",
            "decision_snapshot": "READY_REQUIRED",
        },
        "allowed_actions": _allowed_actions(industry_state),
        "prohibited_actions": [
            "cycle_reversal_conclusion",
            "survival_analysis",
            "financial_analysis",
            "valuation",
            "investment_conclusion",
            "automatic_candidate_promotion",
            "execution",
        ],
        "review_only": True,
        "investment_conclusion": False,
    }


def _industry_state(
    *,
    candidate_state: str,
    transmission_gate_state: str,
    fields: Mapping[str, Mapping[str, Any]],
    required_fields: Sequence[str],
    key_variables: Sequence[Mapping[str, Any]],
) -> tuple[str, list[str]]:
    if candidate_state == "REJECTED":
        return "BLOCKED", ["CANDIDATE_REJECTED"]
    if transmission_gate_state != "READY":
        return "BLOCKED", ["DEMAND_TRANSMISSION_READY_REQUIRED"]
    if any(
        fields[field]["status"] == "CONFLICTING" for field in required_fields
    ):
        return "BLOCKED", ["INDUSTRY_EVIDENCE_CONFLICT"]
    if not any(_is_verified(fields[field]) for field in required_fields):
        return "INSUFFICIENT", ["INDUSTRY_EVIDENCE_MISSING"]
    if not key_variables:
        return "INSUFFICIENT", ["KEY_INDUSTRY_VARIABLES_MISSING"]
    if any(not _is_verified(fields[field]) for field in required_fields):
        return "PARTIAL", ["INDUSTRY_SITUATION_EVIDENCE_INCOMPLETE"]
    return "READY", ["INDUSTRY_SITUATION_FIELDS_COVERED"]


def _key_variables(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not _is_verified(summary):
        return []
    values: list[Any] = []
    for value in summary["values"]:
        if isinstance(value, (list, tuple)):
            values.extend(value)
        else:
            values.append(value)
    if not values:
        return []
    if len(values) > 3:
        raise IndustrySituationError(
            "key_industry_variables must contain at most three variables"
        )
    variables: list[dict[str, Any]] = []
    for value in values:
        if isinstance(value, Mapping):
            name = str(value.get("name") or value.get("variable") or "").strip()
            if not name:
                raise IndustrySituationError(
                    "key industry variable object requires name"
                )
            variables.append(
                {
                    "name": name,
                    "reason": str(value.get("reason") or "").strip(),
                    "direction": str(value.get("direction") or "").strip(),
                }
            )
        else:
            name = str(value or "").strip()
            if not name:
                raise IndustrySituationError(
                    "key industry variables must be non-empty"
                )
            variables.append({"name": name, "reason": "", "direction": ""})
    return variables


def _normalise_fields(fields: Sequence[str]) -> tuple[str, ...]:
    if isinstance(fields, (str, bytes, bytearray)):
        raise IndustrySituationError("required_fields must be a string list")
    try:
        normalised = tuple(dict.fromkeys(str(field).strip() for field in fields))
    except TypeError as error:
        raise IndustrySituationError("required_fields must be a string list") from error
    if not normalised or any(not field for field in normalised):
        raise IndustrySituationError("required_fields must contain non-empty names")
    if "key_industry_variables" not in normalised:
        return ("key_industry_variables", *normalised)
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
        raise IndustrySituationError(f"field summary must be an object: {field}")
    status = str(raw_summary.get("status") or "MISSING").upper()
    if status not in {"MISSING", "VERIFIED", "UNVERIFIED", "CONFLICTING"}:
        raise IndustrySituationError(f"unsupported field status: {status}")
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


def _single_value(summary: Mapping[str, Any]) -> Any:
    if not _is_verified(summary):
        return None
    values = summary["values"]
    return values[0] if len(values) == 1 else values


def _values(summary: Mapping[str, Any]) -> list[Any]:
    return list(summary["values"]) if _is_verified(summary) else []


def _allowed_actions(state: str) -> list[str]:
    return {
        "READY": ["cycle_reversal_analysis", "evidence_refresh"],
        "PARTIAL": ["industry_gap_review", "evidence_refresh"],
        "INSUFFICIENT": ["industry_evidence_collection", "evidence_refresh"],
        "BLOCKED": ["demand_transmission_resolution", "evidence_refresh"],
    }[state]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise IndustrySituationError("industry situation fields must be string lists")
    return [str(item) for item in value if str(item)]


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
