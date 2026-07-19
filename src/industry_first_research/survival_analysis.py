"""Build an evidence-only survival and stress-test gate."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


class SurvivalAnalysisError(ValueError):
    """Raised when survival evidence cannot be derived safely."""


SURVIVAL_ANALYSIS_SCHEMA_VERSION = "company-survival-analysis.v1"
RULE_VERSION = "company-survival-analysis-rules.v1"
COMPETITIVE_POSITION_SCHEMA_VERSION = "company-competitive-position.v1"
STRESS_SCENARIOS = (
    "LOW_DEMAND_LONGER",
    "REFINANCING_FAILURE",
    "OPERATING_SHOCK",
    "ASSET_IMPAIRMENT",
    "TECHNOLOGY_REPLACEMENT",
    "GOVERNANCE_SHOCK",
)
SURVIVAL_DEPENDENCIES = {
    "self_funded",
    "refinancing_dependent",
    "external_support_dependent",
}
SURVIVAL_LABELS = {
    "SURVIVOR",
    "REVERSAL_BENEFICIARY",
    "FALSE_STRONG",
}
DEFAULT_REQUIRED_FIELDS = (
    "available_cash",
    "monthly_cash_burn",
    "debt_maturity",
    "interest_coverage",
    "operating_cashflow",
    "free_cashflow_after_maintenance_capex",
    "cash_cost_position",
    "capex_commitment",
    "impairment_risk",
    "refinancing_capacity",
    "external_support",
    "technology_obsolescence_risk",
    "effective_capacity",
    "recovery_operating_leverage",
    "survival_label",
    "stress_tests",
)
_GATE_STATES = {"READY", "PARTIAL", "INSUFFICIENT", "BLOCKED"}
_UPSTREAM_STATES = {"READY", "PARTIAL", "INSUFFICIENT", "BLOCKED"}
_QUEUE_STATES = {"WATCH", "REVIEW", "CANDIDATE", "INSUFFICIENT", "REJECTED"}
_STRESS_FIELDS = (
    "scenario",
    "horizon_months",
    "cash_runway_months",
    "debt_gap",
    "minimum_cash_balance",
    "capex_reduction_capacity",
    "asset_sale_actions",
    "survival_dependency",
    "survival_outcome",
)


def build_survival_analysis_report(
    competitive_position_report: Mapping[str, Any],
    *,
    required_fields: Sequence[str] = DEFAULT_REQUIRED_FIELDS,
    rule_version: str = RULE_VERSION,
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Validate runway and stress evidence without inferring survival."""

    _validate_report(competitive_position_report)
    fields = _normalise_fields(required_fields)
    if not rule_version.strip():
        raise SurvivalAnalysisError("rule_version must not be empty")

    items = [
        _build_item(item, required_fields=fields, rule_version=rule_version)
        for item in competitive_position_report["items"]
    ]
    counts = Counter(item["survival_gate_state"] for item in items)
    input_report_id = str(competitive_position_report.get("report_id") or "")
    report_id = snapshot_id or input_report_id or "competitive-position-input"
    return {
        "schema_version": SURVIVAL_ANALYSIS_SCHEMA_VERSION,
        "report_id": f"company-survival-analysis-{report_id}",
        "input_competitive_position_id": input_report_id,
        "input_cycle_reversal_id": str(
            competitive_position_report.get("input_cycle_reversal_id") or ""
        ),
        "input_industry_situation_id": str(
            competitive_position_report.get("input_industry_situation_id") or ""
        ),
        "input_demand_transmission_id": str(
            competitive_position_report.get("input_demand_transmission_id") or ""
        ),
        "input_application_mapping_id": str(
            competitive_position_report.get("input_application_mapping_id") or ""
        ),
        "input_product_profile_id": str(
            competitive_position_report.get("input_product_profile_id") or ""
        ),
        "input_supplemental_id": str(
            competitive_position_report.get("input_supplemental_id") or ""
        ),
        "input_queue_id": str(competitive_position_report.get("input_queue_id") or ""),
        "input_snapshot_id": str(
            competitive_position_report.get("input_snapshot_id") or ""
        ),
        "rule_version": rule_version,
        "as_of": str(competitive_position_report.get("as_of") or ""),
        "source": str(competitive_position_report.get("source") or ""),
        "source_metadata": competitive_position_report.get("source_metadata") or {},
        "required_fields": list(fields),
        "candidate_count": len(items),
        "survival_gate_state_counts": dict(counts),
        "items": items,
        "policy": {
            "survival_analysis_only": True,
            "evidence_only": True,
            "competitive_position_ready_required": True,
            "candidate_state_preserved": True,
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
        raise SurvivalAnalysisError(
            "input competitive position report must be a JSON object"
        )
    if report.get("schema_version") != COMPETITIVE_POSITION_SCHEMA_VERSION:
        raise SurvivalAnalysisError(
            "input must be a company-competitive-position.v1 report"
        )
    if not isinstance(report.get("items"), list):
        raise SurvivalAnalysisError(
            "competitive position report has no items list"
        )


def _build_item(
    item: Any,
    *,
    required_fields: Sequence[str],
    rule_version: str,
) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise SurvivalAnalysisError("each competitive position item must be an object")
    company_id = str(item.get("company_id") or "").strip()
    candidate_state = str(item.get("candidate_state") or "").upper()
    position_state = str(item.get("competitive_position_state") or "").upper()
    if not company_id:
        raise SurvivalAnalysisError(
            "competitive position item company_id is required"
        )
    if candidate_state not in _QUEUE_STATES:
        raise SurvivalAnalysisError(
            f"unsupported candidate_state: {candidate_state or '<empty>'}"
        )
    if position_state not in _UPSTREAM_STATES:
        raise SurvivalAnalysisError(
            f"unsupported competitive_position_state: {position_state or '<empty>'}"
        )

    raw_fields = item.get("fields")
    if not isinstance(raw_fields, Mapping):
        raise SurvivalAnalysisError(
            "competitive position item has no fields mapping"
        )
    fields = {
        field: _normalise_field_summary(field, raw_fields.get(field))
        for field in _unique([*required_fields, *map(str, raw_fields.keys())])
    }
    stress_tests = _stress_tests(fields["stress_tests"])
    verified_fields = [field for field in required_fields if _is_verified(fields[field])]
    unverified_fields = [
        field
        for field in required_fields
        if fields[field]["status"] in {"UNVERIFIED", "CONFLICTING"}
    ]
    unknowns = [
        field for field in required_fields if fields[field]["status"] == "MISSING"
    ]
    survival_label = _survival_label(fields["survival_label"])
    dependencies = sorted(
        {test["survival_dependency"] for test in stress_tests}
    )
    gate_state, reasons = _gate_state(
        candidate_state=candidate_state,
        position_state=position_state,
        fields=fields,
        required_fields=required_fields,
        stress_tests=stress_tests,
        survival_label=survival_label,
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
        "competitive_position_state": position_state,
        "survival_gate_state": gate_state,
        "survival_label": survival_label,
        "survival_dependencies": dependencies,
        "stress_tests": stress_tests,
        "rule_version": rule_version,
        "fields": fields,
        "verified_fields": verified_fields,
        "unverified_fields": unverified_fields,
        "unknowns": unknowns,
        "evidence_ids": evidence_ids,
        "reasons": reasons,
        "downstream_modules": {
            "valuation": "READY_REQUIRED",
            "decision_snapshot": "READY_REQUIRED",
        },
        "allowed_actions": _allowed_actions(gate_state),
        "prohibited_actions": [
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
    position_state: str,
    fields: Mapping[str, Mapping[str, Any]],
    required_fields: Sequence[str],
    stress_tests: Sequence[Mapping[str, Any]],
    survival_label: str,
) -> tuple[str, list[str]]:
    if candidate_state == "REJECTED" or position_state == "BLOCKED":
        return "BLOCKED", ["UPSTREAM_COMPETITIVE_POSITION_BLOCKED"]
    if position_state != "READY":
        return "BLOCKED", ["COMPETITIVE_POSITION_READY_REQUIRED"]
    if any(
        fields[field]["status"] == "CONFLICTING" for field in required_fields
    ):
        return "BLOCKED", ["SURVIVAL_EVIDENCE_CONFLICT"]
    if not stress_tests:
        return "INSUFFICIENT", ["SURVIVAL_STRESS_TESTS_MISSING"]
    if len(stress_tests) != len(STRESS_SCENARIOS):
        return "INSUFFICIENT", ["SURVIVAL_STRESS_TESTS_INCOMPLETE"]
    if survival_label == "UNKNOWN":
        return "PARTIAL", ["SURVIVAL_LABEL_MISSING"]
    if any(not _is_verified(fields[field]) for field in required_fields):
        return "PARTIAL", ["SURVIVAL_EVIDENCE_INCOMPLETE"]
    return "READY", ["SURVIVAL_EVIDENCE_COVERED"]


def _stress_tests(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not _is_verified(summary):
        return []
    values: list[Any] = []
    for value in summary["values"]:
        if isinstance(value, list):
            values.extend(value)
        else:
            values.append(value)
    if not values:
        return []
    tests: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, Mapping):
            raise SurvivalAnalysisError("stress_tests evidence values must be objects")
        missing = [
            field for field in _STRESS_FIELDS if field not in value
        ]
        if missing:
            raise SurvivalAnalysisError(
                "stress test entry missing: " + ", ".join(missing)
            )
        scenario = str(value.get("scenario") or "").strip().upper()
        if scenario not in STRESS_SCENARIOS:
            raise SurvivalAnalysisError(
                f"unsupported stress scenario: {scenario or '<empty>'}"
            )
        if scenario in seen:
            raise SurvivalAnalysisError(f"duplicate stress scenario: {scenario}")
        seen.add(scenario)
        dependency = str(value.get("survival_dependency") or "").strip().lower()
        if dependency not in SURVIVAL_DEPENDENCIES:
            raise SurvivalAnalysisError(
                "unsupported survival_dependency: "
                f"{dependency or '<empty>'}"
            )
        outcome = str(value.get("survival_outcome") or "").strip()
        if not outcome:
            raise SurvivalAnalysisError("survival_outcome must be non-empty")
        tests.append(
            {
                "scenario": scenario,
                "horizon_months": value.get("horizon_months"),
                "cash_runway_months": value.get("cash_runway_months"),
                "debt_gap": value.get("debt_gap"),
                "minimum_cash_balance": value.get("minimum_cash_balance"),
                "capex_reduction_capacity": value.get("capex_reduction_capacity"),
                "asset_sale_actions": value.get("asset_sale_actions"),
                "survival_dependency": dependency,
                "survival_outcome": outcome,
            }
        )
    missing_scenarios = set(STRESS_SCENARIOS) - seen
    if missing_scenarios:
        raise SurvivalAnalysisError(
            "stress tests missing scenarios: " + ", ".join(sorted(missing_scenarios))
        )
    return [
        next(test for test in tests if test["scenario"] == scenario)
        for scenario in STRESS_SCENARIOS
    ]


def _survival_label(summary: Mapping[str, Any]) -> str:
    if not _is_verified(summary):
        return "UNKNOWN"
    values = summary["values"]
    if len(values) != 1:
        raise SurvivalAnalysisError(
            "survival_label evidence must contain exactly one value"
        )
    label = str(values[0] or "").strip().upper()
    if label not in SURVIVAL_LABELS:
        raise SurvivalAnalysisError(f"unsupported survival_label: {label or '<empty>'}")
    return label


def _normalise_fields(fields: Sequence[str]) -> tuple[str, ...]:
    if isinstance(fields, (str, bytes, bytearray)):
        raise SurvivalAnalysisError("required_fields must be a string list")
    try:
        normalised = tuple(dict.fromkeys(str(field).strip() for field in fields))
    except TypeError as error:
        raise SurvivalAnalysisError("required_fields must be a string list") from error
    if not normalised or any(not field for field in normalised):
        raise SurvivalAnalysisError("required_fields must contain non-empty names")
    if "stress_tests" not in normalised:
        return ("stress_tests", *normalised)
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
        raise SurvivalAnalysisError(f"field summary must be an object: {field}")
    status = str(raw_summary.get("status") or "MISSING").upper()
    if status not in {"MISSING", "VERIFIED", "UNVERIFIED", "CONFLICTING"}:
        raise SurvivalAnalysisError(f"unsupported field status: {status}")
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


def _allowed_actions(state: str) -> list[str]:
    return {
        "READY": ["valuation_review", "evidence_refresh"],
        "PARTIAL": ["survival_gap_review", "evidence_refresh"],
        "INSUFFICIENT": ["survival_evidence_collection", "evidence_refresh"],
        "BLOCKED": ["competitive_position_resolution", "evidence_refresh"],
    }[state]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise SurvivalAnalysisError("survival analysis fields must be string lists")
    return [str(item) for item in value if str(item)]


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
