"""Build an evidence-only industry supply and cycle-reversal report."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


class CycleReversalError(ValueError):
    """Raised when a cycle-reversal report cannot be derived safely."""


CYCLE_REVERSAL_SCHEMA_VERSION = "company-cycle-reversal.v1"
RULE_VERSION = "company-cycle-reversal-rules.v1"
INDUSTRY_SITUATION_SCHEMA_VERSION = "company-industry-situation.v1"
DEFAULT_REQUIRED_FIELDS = (
    "industry_applicability",
    "real_demand",
    "effective_supply",
    "nominal_capacity",
    "capacity_utilization",
    "inventory_level",
    "inventory_holder",
    "spot_price",
    "contract_price",
    "cash_cost",
    "full_cost",
    "marginal_capacity",
    "capex_pipeline",
    "capacity_exit",
    "shutdown_and_bankruptcy",
    "industry_cashflow",
    "recovery_speed",
    "cycle_state",
    "cycle_evidence",
    "confirmation_conditions",
    "invalidators",
    "confidence",
)
_GATE_STATES = {
    "READY",
    "PARTIAL",
    "INSUFFICIENT",
    "BLOCKED",
    "NOT_APPLICABLE",
}
_QUEUE_STATES = {"WATCH", "REVIEW", "CANDIDATE", "INSUFFICIENT", "REJECTED"}
CYCLE_STATES = (
    "PRICE_REBOUND",
    "TURNING_POINT_CANDIDATE",
    "INDUSTRIAL_REVERSAL_CONFIRMED",
)
_STATE_SUPPORT = {
    "PRICE_REBOUND": ("spot_price", "cycle_evidence"),
    "TURNING_POINT_CANDIDATE": (
        "real_demand",
        "effective_supply",
        "inventory_level",
        "capex_pipeline",
        "capacity_exit",
        "cycle_evidence",
    ),
    "INDUSTRIAL_REVERSAL_CONFIRMED": (
        "real_demand",
        "effective_supply",
        "inventory_level",
        "spot_price",
        "capacity_exit",
        "industry_cashflow",
        "cycle_evidence",
    ),
}


def build_cycle_reversal_report(
    industry_situation_report: Mapping[str, Any],
    *,
    required_fields: Sequence[str] = DEFAULT_REQUIRED_FIELDS,
    rule_version: str = RULE_VERSION,
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Assess cycle evidence without turning price movement into a conclusion."""

    _validate_report(industry_situation_report)
    fields = _normalise_fields(required_fields)
    if not rule_version.strip():
        raise CycleReversalError("rule_version must not be empty")

    items = [
        _build_item(item, required_fields=fields, rule_version=rule_version)
        for item in industry_situation_report["items"]
    ]
    counts = Counter(item["cycle_reversal_gate_state"] for item in items)
    input_report_id = str(industry_situation_report.get("report_id") or "")
    report_id = snapshot_id or input_report_id or "industry-situation-input"
    return {
        "schema_version": CYCLE_REVERSAL_SCHEMA_VERSION,
        "report_id": f"company-cycle-reversal-{report_id}",
        "input_industry_situation_id": input_report_id,
        "input_demand_transmission_id": str(
            industry_situation_report.get("input_demand_transmission_id") or ""
        ),
        "input_application_mapping_id": str(
            industry_situation_report.get("input_application_mapping_id") or ""
        ),
        "input_product_profile_id": str(
            industry_situation_report.get("input_product_profile_id") or ""
        ),
        "input_supplemental_id": str(
            industry_situation_report.get("input_supplemental_id") or ""
        ),
        "input_queue_id": str(industry_situation_report.get("input_queue_id") or ""),
        "input_snapshot_id": str(
            industry_situation_report.get("input_snapshot_id") or ""
        ),
        "rule_version": rule_version,
        "as_of": str(industry_situation_report.get("as_of") or ""),
        "source": str(industry_situation_report.get("source") or ""),
        "source_metadata": industry_situation_report.get("source_metadata") or {},
        "required_fields": list(fields),
        "candidate_count": len(items),
        "cycle_reversal_gate_state_counts": dict(counts),
        "items": items,
        "policy": {
            "cycle_reversal_only": True,
            "evidence_only": True,
            "industry_situation_ready_required": True,
            "candidate_state_preserved": True,
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
        raise CycleReversalError(
            "input industry situation report must be a JSON object"
        )
    if report.get("schema_version") != INDUSTRY_SITUATION_SCHEMA_VERSION:
        raise CycleReversalError(
            "input must be a company-industry-situation.v1 report"
        )
    if not isinstance(report.get("items"), list):
        raise CycleReversalError("industry situation report has no items list")


def _build_item(
    item: Any,
    *,
    required_fields: Sequence[str],
    rule_version: str,
) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise CycleReversalError("each industry situation item must be an object")
    company_id = str(item.get("company_id") or "").strip()
    candidate_state = str(item.get("candidate_state") or "").upper()
    situation_state = str(item.get("industry_situation_state") or "").upper()
    if not company_id:
        raise CycleReversalError("industry situation item company_id is required")
    if candidate_state not in _QUEUE_STATES:
        raise CycleReversalError(
            f"unsupported candidate_state: {candidate_state or '<empty>'}"
        )
    if situation_state not in {"READY", "PARTIAL", "INSUFFICIENT", "BLOCKED"}:
        raise CycleReversalError(
            f"unsupported industry_situation_state: {situation_state or '<empty>'}"
        )

    raw_fields = item.get("fields")
    if not isinstance(raw_fields, Mapping):
        raise CycleReversalError("industry situation item has no fields mapping")
    fields = {
        field: _normalise_field_summary(field, raw_fields.get(field))
        for field in _unique([*required_fields, *map(str, raw_fields.keys())])
    }
    verified_fields = [field for field in required_fields if _is_verified(fields[field])]
    unverified_fields = [
        field
        for field in required_fields
        if fields[field]["status"] in {"UNVERIFIED", "CONFLICTING"}
    ]
    unknowns = [
        field for field in required_fields if fields[field]["status"] == "MISSING"
    ]
    applicable = _applicability(fields["industry_applicability"])
    claimed_state = _claimed_state(fields["cycle_state"])
    state_validation = _validate_claimed_state(claimed_state, fields)
    gate_state, cycle_state, reasons = _gate_state(
        candidate_state=candidate_state,
        situation_state=situation_state,
        applicable=applicable,
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
        "display_name": str(item.get("display_name") or ""),
        "industry_id": str(item.get("industry_id") or ""),
        "candidate_state": candidate_state,
        "candidate_state_changed": False,
        "candidate_rule_version": str(item.get("candidate_rule_version") or ""),
        "industry_situation_state": situation_state,
        "applicable": applicable,
        "cycle_reversal_gate_state": gate_state,
        "cycle_reversal_state": cycle_state,
        "state_validation": state_validation,
        "rule_version": rule_version,
        "fields": fields,
        "real_demand": _values(fields["real_demand"]),
        "effective_supply": _values(fields["effective_supply"]),
        "inventory_level": _values(fields["inventory_level"]),
        "capacity_exit": _values(fields["capacity_exit"]),
        "industry_cashflow": _values(fields["industry_cashflow"]),
        "evidence": _values(fields["cycle_evidence"]),
        "confirmation_conditions": _values(fields["confirmation_conditions"]),
        "invalidators": _values(fields["invalidators"]),
        "confidence": _single_value(fields["confidence"]),
        "verified_fields": verified_fields,
        "unverified_fields": unverified_fields,
        "unknowns": unknowns,
        "evidence_ids": evidence_ids,
        "reasons": reasons,
        "downstream_modules": {
            "survival_analysis": "READY_REQUIRED",
            "valuation": "READY_REQUIRED",
            "decision_snapshot": "READY_REQUIRED",
        },
        "allowed_actions": _allowed_actions(gate_state),
        "prohibited_actions": [
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


def _gate_state(
    *,
    candidate_state: str,
    situation_state: str,
    applicable: bool | None,
    fields: Mapping[str, Mapping[str, Any]],
    required_fields: Sequence[str],
    claimed_state: str,
    state_validation: str,
) -> tuple[str, str, list[str]]:
    if candidate_state == "REJECTED" or situation_state == "BLOCKED":
        return "BLOCKED", "BLOCKED", ["INDUSTRY_SITUATION_BLOCKED"]
    if applicable is False:
        return "NOT_APPLICABLE", "NOT_APPLICABLE", ["CYCLE_MODULE_NOT_APPLICABLE"]
    if applicable is None:
        return "INSUFFICIENT", "INSUFFICIENT_EVIDENCE", [
            "INDUSTRY_APPLICABILITY_MISSING"
        ]
    if state_validation == "CONFLICTING":
        return "BLOCKED", "CONFLICTING", ["CYCLE_STATE_CONFLICT"]
    if claimed_state == "UNKNOWN":
        return "INSUFFICIENT", "INSUFFICIENT_EVIDENCE", ["CYCLE_STATE_MISSING"]
    support_fields = _STATE_SUPPORT[claimed_state]
    if any(not _is_verified(fields[field]) for field in support_fields):
        return "INSUFFICIENT", "INSUFFICIENT_EVIDENCE", [
            "CYCLE_STATE_EVIDENCE_INSUFFICIENT"
        ]
    if any(not _is_verified(fields[field]) for field in required_fields):
        return "PARTIAL", claimed_state, ["CYCLE_REVERSAL_EVIDENCE_INCOMPLETE"]
    return "READY", claimed_state, ["CYCLE_REVERSAL_EVIDENCE_COVERED"]


def _applicability(summary: Mapping[str, Any]) -> bool | None:
    if not _is_verified(summary):
        return None
    values = summary["values"]
    if len(values) != 1:
        raise CycleReversalError(
            "industry_applicability evidence must contain exactly one value"
        )
    value = values[0]
    if isinstance(value, Mapping):
        value = value.get("applicable")
    if not isinstance(value, bool):
        raise CycleReversalError("industry_applicability must be a boolean")
    return value


def _claimed_state(summary: Mapping[str, Any]) -> str:
    if not _is_verified(summary):
        return "UNKNOWN"
    values = summary["values"]
    if len(values) != 1:
        raise CycleReversalError("cycle_state evidence must contain exactly one value")
    value = values[0]
    if isinstance(value, Mapping):
        value = value.get("state")
    state = str(value or "").strip().upper()
    if state not in CYCLE_STATES:
        raise CycleReversalError(f"unsupported cycle_state: {state or '<empty>'}")
    return state


def _validate_claimed_state(
    claimed_state: str,
    fields: Mapping[str, Mapping[str, Any]],
) -> str:
    if fields["cycle_state"]["status"] == "CONFLICTING":
        return "CONFLICTING"
    if claimed_state == "UNKNOWN":
        return "MISSING"
    if all(_is_verified(fields[field]) for field in _STATE_SUPPORT[claimed_state]):
        return "SUPPORTED"
    return "INSUFFICIENT"


def _normalise_fields(fields: Sequence[str]) -> tuple[str, ...]:
    if isinstance(fields, (str, bytes, bytearray)):
        raise CycleReversalError("required_fields must be a string list")
    try:
        normalised = tuple(dict.fromkeys(str(field).strip() for field in fields))
    except TypeError as error:
        raise CycleReversalError("required_fields must be a string list") from error
    if not normalised or any(not field for field in normalised):
        raise CycleReversalError("required_fields must contain non-empty names")
    if "industry_applicability" not in normalised:
        normalised = ("industry_applicability", *normalised)
    if "cycle_state" not in normalised:
        normalised = (*normalised, "cycle_state")
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
        raise CycleReversalError(f"field summary must be an object: {field}")
    status = str(raw_summary.get("status") or "MISSING").upper()
    if status not in {"MISSING", "VERIFIED", "UNVERIFIED", "CONFLICTING"}:
        raise CycleReversalError(f"unsupported field status: {status}")
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
        "READY": ["survival_analysis", "evidence_refresh"],
        "PARTIAL": ["cycle_gap_review", "evidence_refresh"],
        "INSUFFICIENT": ["cycle_evidence_collection", "evidence_refresh"],
        "BLOCKED": ["industry_situation_resolution", "evidence_refresh"],
        "NOT_APPLICABLE": ["evidence_refresh"],
    }[state]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise CycleReversalError("cycle reversal fields must be string lists")
    return [str(item) for item in value if str(item)]


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
