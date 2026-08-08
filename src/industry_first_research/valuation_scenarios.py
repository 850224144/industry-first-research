"""Build an evidence-only valuation and scenario framework gate."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


class ValuationScenarioError(ValueError):
    """Raised when valuation inputs cannot be checked safely."""


VALUATION_SCENARIO_SCHEMA_VERSION = "company-valuation-scenarios.v1"
RULE_VERSION = "company-valuation-scenarios-rules.v1"
SURVIVAL_ANALYSIS_SCHEMA_VERSION = "company-survival-analysis.v1"
SCENARIOS = ("BEAR", "BASE", "BULL")
SCENARIO_FIELDS = (
    "scenario",
    "revenue_assumptions",
    "profit_assumptions",
    "cashflow_assumptions",
    "capex_assumptions",
    "treatment",
)
DEFAULT_REQUIRED_FIELDS = (
    "valuation_method",
    "current_price",
    "current_price_as_of",
    "historical_financials",
    "cycle_center_profit",
    "net_debt_and_dilution",
    "scenario_inputs",
    "implied_assumptions",
    "evidence_backed_assumptions",
    "model_assumptions",
    "excluded_from_base_case",
    "valuation_sensitivity",
)
_GATE_STATES = {"READY", "PARTIAL", "INSUFFICIENT", "BLOCKED"}
_UPSTREAM_STATES = {"READY", "PARTIAL", "INSUFFICIENT", "BLOCKED"}
_QUEUE_STATES = {"WATCH", "REVIEW", "CANDIDATE", "INSUFFICIENT", "REJECTED"}


def build_valuation_scenarios_report(
    survival_analysis_report: Mapping[str, Any],
    *,
    required_fields: Sequence[str] = DEFAULT_REQUIRED_FIELDS,
    rule_version: str = RULE_VERSION,
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Validate valuation inputs without calculating a target price or conclusion."""

    _validate_report(survival_analysis_report)
    fields = _normalise_fields(required_fields)
    if not rule_version.strip():
        raise ValuationScenarioError("rule_version must not be empty")

    items = [
        _build_item(item, required_fields=fields, rule_version=rule_version)
        for item in survival_analysis_report["items"]
    ]
    counts = Counter(item["valuation_gate_state"] for item in items)
    input_report_id = str(survival_analysis_report.get("report_id") or "")
    report_id = snapshot_id or input_report_id or "survival-analysis-input"
    return {
        "schema_version": VALUATION_SCENARIO_SCHEMA_VERSION,
        "report_id": f"company-valuation-scenarios-{report_id}",
        "input_survival_analysis_id": input_report_id,
        "input_competitive_position_id": str(
            survival_analysis_report.get("input_competitive_position_id") or ""
        ),
        "input_cycle_reversal_id": str(
            survival_analysis_report.get("input_cycle_reversal_id") or ""
        ),
        "input_industry_situation_id": str(
            survival_analysis_report.get("input_industry_situation_id") or ""
        ),
        "input_demand_transmission_id": str(
            survival_analysis_report.get("input_demand_transmission_id") or ""
        ),
        "input_application_mapping_id": str(
            survival_analysis_report.get("input_application_mapping_id") or ""
        ),
        "input_product_profile_id": str(
            survival_analysis_report.get("input_product_profile_id") or ""
        ),
        "input_supplemental_id": str(
            survival_analysis_report.get("input_supplemental_id") or ""
        ),
        "input_queue_id": str(survival_analysis_report.get("input_queue_id") or ""),
        "input_snapshot_id": str(
            survival_analysis_report.get("input_snapshot_id") or ""
        ),
        "rule_version": rule_version,
        "as_of": str(survival_analysis_report.get("as_of") or ""),
        "source": str(survival_analysis_report.get("source") or ""),
        "source_metadata": survival_analysis_report.get("source_metadata") or {},
        "required_fields": list(fields),
        "candidate_count": len(items),
        "valuation_gate_state_counts": dict(counts),
        "items": items,
        "policy": {
            "valuation_framework_only": True,
            "evidence_only": True,
            "survival_analysis_ready_required": True,
            "candidate_state_preserved": True,
            "numeric_valuation_included": False,
            "target_price_generated": False,
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
        raise ValuationScenarioError(
            "input survival analysis report must be a JSON object"
        )
    if report.get("schema_version") != SURVIVAL_ANALYSIS_SCHEMA_VERSION:
        raise ValuationScenarioError(
            "input must be a company-survival-analysis.v1 report"
        )
    if not isinstance(report.get("items"), list):
        raise ValuationScenarioError("survival analysis report has no items list")


def _build_item(
    item: Any,
    *,
    required_fields: Sequence[str],
    rule_version: str,
) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise ValuationScenarioError("each survival analysis item must be an object")
    company_id = str(item.get("company_id") or "").strip()
    candidate_state = str(item.get("candidate_state") or "").upper()
    survival_gate_state = str(item.get("survival_gate_state") or "").upper()
    if not company_id:
        raise ValuationScenarioError("survival analysis item company_id is required")
    if candidate_state not in _QUEUE_STATES:
        raise ValuationScenarioError(
            f"unsupported candidate_state: {candidate_state or '<empty>'}"
        )
    if survival_gate_state not in _UPSTREAM_STATES:
        raise ValuationScenarioError(
            "unsupported survival_gate_state: "
            f"{survival_gate_state or '<empty>'}"
        )

    raw_fields = item.get("fields")
    if not isinstance(raw_fields, Mapping):
        raise ValuationScenarioError("survival analysis item has no fields mapping")
    fields = {
        field: _normalise_field_summary(field, raw_fields.get(field))
        for field in _unique([*required_fields, *map(str, raw_fields.keys())])
    }
    scenario_inputs = _scenario_inputs(fields["scenario_inputs"])
    sensitivity = _sensitivity(fields["valuation_sensitivity"])
    verified_fields = [field for field in required_fields if _is_verified(fields[field])]
    unverified_fields = [
        field
        for field in required_fields
        if fields[field]["status"] in {"UNVERIFIED", "CONFLICTING"}
    ]
    unknowns = [
        field for field in required_fields if fields[field]["status"] == "MISSING"
    ]
    gate_state, reasons = _gate_state(
        candidate_state=candidate_state,
        survival_gate_state=survival_gate_state,
        fields=fields,
        required_fields=required_fields,
        scenario_inputs=scenario_inputs,
        sensitivity=sensitivity,
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
        "survival_gate_state": survival_gate_state,
        "valuation_gate_state": gate_state,
        "valuation_framework_state": (
            "EVIDENCE_READY" if gate_state == "READY" else "NOT_READY"
        ),
        "rule_version": rule_version,
        "fields": fields,
        "valuation_method": _single_value(fields["valuation_method"]),
        "current_price": _single_value(fields["current_price"]),
        "current_price_as_of": _single_value(fields["current_price_as_of"]),
        "scenario_inputs": scenario_inputs,
        "implied_assumptions": _values(fields["implied_assumptions"]),
        "evidence_backed_assumptions": _values(
            fields["evidence_backed_assumptions"]
        ),
        "model_assumptions": _values(fields["model_assumptions"]),
        "excluded_from_base_case": _values(fields["excluded_from_base_case"]),
        "valuation_sensitivity": sensitivity,
        "verified_fields": verified_fields,
        "unverified_fields": unverified_fields,
        "unknowns": unknowns,
        "evidence_ids": evidence_ids,
        "numeric_valuation_included": False,
        "target_price_generated": False,
        "reasons": reasons,
        "downstream_modules": {
            "numeric_valuation": "NOT_INCLUDED",
            "decision_snapshot": "READY_REQUIRED",
        },
        "allowed_actions": _allowed_actions(gate_state),
        "prohibited_actions": [
            "target_price_generation",
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
    survival_gate_state: str,
    fields: Mapping[str, Mapping[str, Any]],
    required_fields: Sequence[str],
    scenario_inputs: Sequence[Mapping[str, Any]],
    sensitivity: Sequence[Mapping[str, Any]],
) -> tuple[str, list[str]]:
    if candidate_state == "REJECTED" or survival_gate_state == "BLOCKED":
        return "BLOCKED", ["UPSTREAM_SURVIVAL_ANALYSIS_BLOCKED"]
    if survival_gate_state != "READY":
        return "BLOCKED", ["SURVIVAL_ANALYSIS_READY_REQUIRED"]
    if any(
        fields[field]["status"] == "CONFLICTING" for field in required_fields
    ):
        return "BLOCKED", ["VALUATION_EVIDENCE_CONFLICT"]
    if set(scenario["scenario"] for scenario in scenario_inputs) != set(SCENARIOS):
        return "INSUFFICIENT", ["THREE_SCENARIOS_REQUIRED"]
    if not sensitivity:
        return "INSUFFICIENT", ["VALUATION_SENSITIVITY_MISSING"]
    if any(not _is_verified(fields[field]) for field in required_fields):
        return "PARTIAL", ["VALUATION_EVIDENCE_INCOMPLETE"]
    return "READY", ["VALUATION_FRAMEWORK_FIELDS_COVERED"]


def _scenario_inputs(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not _is_verified(summary):
        return []
    values: list[Any] = []
    for value in summary["values"]:
        if isinstance(value, list):
            values.extend(value)
        else:
            values.append(value)
    scenarios: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, Mapping):
            raise ValuationScenarioError(
                "scenario_inputs evidence values must be objects"
            )
        missing = [field for field in SCENARIO_FIELDS if field not in value]
        if missing:
            raise ValuationScenarioError(
                "scenario entry missing: " + ", ".join(missing)
            )
        scenario = str(value.get("scenario") or "").strip().upper()
        if scenario not in SCENARIOS:
            raise ValuationScenarioError(
                f"unsupported valuation scenario: {scenario or '<empty>'}"
            )
        if scenario in seen:
            raise ValuationScenarioError(f"duplicate valuation scenario: {scenario}")
        treatment = str(value.get("treatment") or "").strip().upper()
        if not treatment:
            raise ValuationScenarioError("scenario treatment must be non-empty")
        seen.add(scenario)
        scenarios.append(
            {
                "scenario": scenario,
                "revenue_assumptions": value["revenue_assumptions"],
                "profit_assumptions": value["profit_assumptions"],
                "cashflow_assumptions": value["cashflow_assumptions"],
                "capex_assumptions": value["capex_assumptions"],
                "treatment": treatment,
            }
        )
    return [
        next(scenario for scenario in scenarios if scenario["scenario"] == name)
        for name in SCENARIOS
        if name in seen
    ]


def _sensitivity(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not _is_verified(summary):
        return []
    values: list[Any] = []
    for value in summary["values"]:
        if isinstance(value, list):
            values.extend(value)
        else:
            values.append(value)
    sensitivity: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise ValuationScenarioError(
                "valuation_sensitivity evidence values must be objects"
            )
        if not all(str(value.get(field) or "").strip() for field in ("variable", "downside", "upside")):
            raise ValuationScenarioError(
                "valuation_sensitivity entries require variable, downside, and upside"
            )
        sensitivity.append(
            {
                "variable": str(value["variable"]).strip(),
                "downside": str(value["downside"]).strip(),
                "upside": str(value["upside"]).strip(),
            }
        )
    return sensitivity


def _normalise_fields(fields: Sequence[str]) -> tuple[str, ...]:
    if isinstance(fields, (str, bytes, bytearray)):
        raise ValuationScenarioError("required_fields must be a string list")
    try:
        normalised = tuple(dict.fromkeys(str(field).strip() for field in fields))
    except TypeError as error:
        raise ValuationScenarioError("required_fields must be a string list") from error
    if not normalised or any(not field for field in normalised):
        raise ValuationScenarioError("required_fields must contain non-empty names")
    if "scenario_inputs" not in normalised:
        return ("scenario_inputs", *normalised)
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
        raise ValuationScenarioError(f"field summary must be an object: {field}")
    status = str(raw_summary.get("status") or "MISSING").upper()
    if status not in {"MISSING", "VERIFIED", "UNVERIFIED", "CONFLICTING"}:
        raise ValuationScenarioError(f"unsupported field status: {status}")
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
        "READY": ["valuation_framework_review", "evidence_refresh"],
        "PARTIAL": ["valuation_gap_review", "evidence_refresh"],
        "INSUFFICIENT": ["valuation_evidence_collection", "evidence_refresh"],
        "BLOCKED": ["survival_analysis_resolution", "evidence_refresh"],
    }[state]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise ValuationScenarioError("valuation scenario fields must be string lists")
    return [str(item) for item in value if str(item)]


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
