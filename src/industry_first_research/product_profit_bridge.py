"""Deterministic product-level revenue, profit, and cash-flow bridges.

This module is a model-input and evidence artifact.  It never turns a market
theme into revenue, never fills missing allocation data, and never emits an
investment conclusion.  Scalar or interval assumptions are preserved so a
product with uncertain allocation can be shown as a range or ``UNKNOWN``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from math import isfinite
from typing import Any

from .company_scope import CompanyScopeError, normalize_scope_reports, scope_item_for_company


PRODUCT_PROFIT_BRIDGE_INPUT_SCHEMA_VERSION = "product-profit-bridge-input.v1"
PRODUCT_PROFIT_BRIDGE_SCHEMA_VERSION = "product-profit-bridge.v1"
RULE_VERSION = "product-profit-bridge-rules.v1"

BRIDGE_STATES = {"READY", "PARTIAL", "INSUFFICIENT", "BLOCKED"}
SCENARIOS = {"BASE_CASE", "UPSIDE_CASE", "DOWNSIDE_CASE"}
ALLOCATION_METHODS = {
    "DIRECT_DISCLOSURE",
    "PRODUCT_UNIT_ECONOMICS",
    "MANUAL_ALLOCATION",
    "NOT_ALLOCABLE",
    "UNKNOWN",
}
BASE_CASE_TREATMENTS = {"INCLUDED", "OPTIONAL", "STRESS", "EXCLUDED", "UNKNOWN"}
FORMAL_EVIDENCE_STATUSES = {"VERIFIED", "CROSS_VALIDATED"}
ASSUMPTION_STATUSES = {
    "VERIFIED",
    "CROSS_VALIDATED",
    "COMPANY_CLAIM",
    "MODEL_ASSUMPTION",
    "UNKNOWN",
    "CONFLICTING",
    "MISSING",
}

_ASSUMPTION_ALIASES = {
    "volume": ("volume", "sales_volume", "shipment_volume", "shipments"),
    "unit_price": ("unit_price", "price", "selling_price"),
    "unit_cost": ("unit_cost", "cost", "variable_cost_per_unit"),
    "direct_expense_total": ("direct_expense_total", "direct_expenses", "direct_expense"),
    "direct_expense_per_unit": ("direct_expense_per_unit",),
    "working_capital_investment": ("working_capital_investment", "working_capital"),
    "capex": ("capex", "capital_expenditure", "capital_expenditures"),
    "tax_and_interest_outflow": (
        "tax_and_interest_outflow",
        "tax_and_interest",
        "tax_interest",
    ),
}


class ProductProfitBridgeError(ValueError):
    """Raised when a product bridge violates its input or lineage contract."""


def build_product_profit_bridge_report(
    payload: Mapping[str, Any],
    *,
    company_scope_reports: Mapping[str, Mapping[str, Any]] | None = None,
    bridge_id: str = "",
    rule_version: str = RULE_VERSION,
) -> dict[str, Any]:
    """Build one or more scenario bridges from explicit product assumptions."""

    if not isinstance(payload, Mapping):
        raise ProductProfitBridgeError("product bridge input must be a JSON object")
    if payload.get("schema_version") != PRODUCT_PROFIT_BRIDGE_INPUT_SCHEMA_VERSION:
        raise ProductProfitBridgeError(
            f"input must be {PRODUCT_PROFIT_BRIDGE_INPUT_SCHEMA_VERSION}"
        )
    if not str(rule_version or "").strip():
        raise ProductProfitBridgeError("rule_version must not be empty")
    try:
        scope_reports = normalize_scope_reports(company_scope_reports)
    except CompanyScopeError as error:
        raise ProductProfitBridgeError(str(error)) from error

    raw_items = payload.get("items")
    if raw_items is None:
        raw_items = [payload] if payload.get("product_id") else []
    if not isinstance(raw_items, list) or not raw_items:
        raise ProductProfitBridgeError("input must contain a non-empty items list")

    expanded: list[Mapping[str, Any]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, Mapping):
            raise ProductProfitBridgeError("each product bridge item must be an object")
        scenarios = raw_item.get("scenarios")
        if scenarios is None:
            expanded.append(raw_item)
            continue
        if not isinstance(scenarios, list) or not scenarios:
            raise ProductProfitBridgeError("scenarios must be a non-empty list")
        for raw_scenario in scenarios:
            if not isinstance(raw_scenario, Mapping):
                raise ProductProfitBridgeError("each scenario must be an object")
            merged = dict(raw_item)
            merged.pop("scenarios", None)
            merged.update(raw_scenario)
            expanded.append(merged)

    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_item in enumerate(expanded):
        item = _build_item(
            raw_item,
            payload=payload,
            scope_reports=scope_reports,
            index=index,
            rule_version=rule_version,
        )
        if item["bridge_id"] in seen_ids:
            raise ProductProfitBridgeError(f"duplicate bridge_id: {item['bridge_id']}")
        seen_ids.add(item["bridge_id"])
        items.append(item)

    counts = Counter(item["bridge_state"] for item in items)
    input_id = str(payload.get("input_product_profile_id") or payload.get("product_profile_id") or "")
    report_key = str(bridge_id or payload.get("report_id") or input_id or "input").strip()
    return {
        "schema_version": PRODUCT_PROFIT_BRIDGE_SCHEMA_VERSION,
        "report_id": f"product-profit-bridge-{report_key}",
        "input_product_profile_id": input_id,
        "input_supplemental_id": str(payload.get("input_supplemental_id") or ""),
        "as_of": str(payload.get("as_of") or ""),
        "rule_version": rule_version,
        "bridge_count": len(items),
        "bridge_state_counts": dict(counts),
        "items": items,
        "immutable": True,
        "policy": {
            "explicit_assumptions_only": True,
            "intervals_preserved": True,
            "missing_allocation_not_inferred": True,
            "base_case_requires_explicit_treatment": True,
            "product_bridge_is_not_company_forecast": True,
            "investment_conclusion": False,
            "target_price_generated": False,
            "decision_snapshot_created": False,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def validate_product_profit_bridge_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a stored bridge without recalculating or rewriting it."""

    if not isinstance(report, Mapping) or report.get("schema_version") != PRODUCT_PROFIT_BRIDGE_SCHEMA_VERSION:
        raise ProductProfitBridgeError(f"input must be {PRODUCT_PROFIT_BRIDGE_SCHEMA_VERSION}")
    if report.get("immutable") is False:
        raise ProductProfitBridgeError("product bridge must be read-only")
    items = report.get("items")
    if not isinstance(items, list):
        raise ProductProfitBridgeError("product bridge report has no items list")
    seen: set[str] = set()
    errors: list[str] = []
    for item in items:
        if not isinstance(item, Mapping):
            errors.append("item is not an object")
            continue
        identifier = str(item.get("bridge_id") or "")
        if not identifier:
            errors.append("bridge_id is missing")
        elif identifier in seen:
            errors.append(f"duplicate bridge_id: {identifier}")
        seen.add(identifier)
        if str(item.get("bridge_state") or "") not in BRIDGE_STATES:
            errors.append(f"unsupported bridge_state: {identifier}")
    return {
        "schema_version": "product-profit-bridge-validation.v1",
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
        raise ProductProfitBridgeError("company_id is required")
    if not product_id:
        raise ProductProfitBridgeError("product_id is required")
    if not product_name:
        raise ProductProfitBridgeError("product_name is required")
    if not scope_id:
        raise ProductProfitBridgeError("scope_id is required")
    _validate_as_of(as_of)

    scenario = _normalise_scenario(raw.get("scenario") or "BASE_CASE")
    allocation_method = str(raw.get("allocation_method") or "UNKNOWN").strip().upper()
    if allocation_method not in ALLOCATION_METHODS:
        raise ProductProfitBridgeError(f"unsupported allocation_method: {allocation_method}")
    treatment = str(
        raw.get("base_case_treatment")
        or {"BASE_CASE": "INCLUDED", "UPSIDE_CASE": "OPTIONAL", "DOWNSIDE_CASE": "STRESS"}[scenario]
    ).strip().upper()
    if treatment not in BASE_CASE_TREATMENTS:
        raise ProductProfitBridgeError(f"unsupported base_case_treatment: {treatment}")

    scope_projection, scope_status = _scope_status(scope_reports, company_id, scope_id)
    assumptions = _normalise_assumptions(raw, as_of=as_of)
    calculation, unknown_items, warnings = _calculate(assumptions, allocation_method)
    if scope_status != "VERIFIED":
        warnings.append("scope is not verified for this company/product bridge")
    if allocation_method == "NOT_ALLOCABLE":
        warnings.append("product economics are not reasonably allocable to this product")
    if allocation_method == "UNKNOWN":
        warnings.append("allocation_method is unknown; product contribution cannot be treated as fully allocated")

    if allocation_method == "NOT_ALLOCABLE" or scope_status == "CONFLICTING":
        bridge_state = "BLOCKED"
    elif calculation["revenue_estimate"] is None:
        bridge_state = "INSUFFICIENT"
    elif calculation["cashflow_contribution_estimate"] is None:
        bridge_state = "PARTIAL"
    else:
        bridge_state = (
            "READY"
            if not unknown_items and allocation_method != "UNKNOWN"
            else "PARTIAL"
        )

    evidence_status = _evidence_status(assumptions, bridge_state)
    confidence = _confidence(assumptions, bridge_state, scope_status)
    identifier = str(raw.get("bridge_id") or "").strip() or (
        f"bridge-{company_id}-{product_id}-{scenario.lower()}-{index + 1}"
    )
    return {
        "bridge_id": identifier,
        "company_id": company_id,
        "scope_id": scope_id,
        "scope_status": scope_status,
        "scope_projection": scope_projection,
        "product_id": product_id,
        "product_name": product_name,
        "as_of": as_of,
        "scenario": scenario,
        "base_case_treatment": treatment,
        "allocation_method": allocation_method,
        "assumptions": assumptions,
        "revenue_estimate": calculation["revenue_estimate"],
        "unit_cost_assumption": calculation["unit_cost_assumption"],
        "gross_profit_estimate": calculation["gross_profit_estimate"],
        "direct_expense_assumption": calculation["direct_expense_assumption"],
        "operating_profit_estimate": calculation["operating_profit_estimate"],
        "working_capital_assumption": calculation["working_capital_assumption"],
        "capex_assumption": calculation["capex_assumption"],
        "cashflow_contribution_estimate": calculation["cashflow_contribution_estimate"],
        "calculation": calculation,
        "unknown_items": unknown_items,
        "warnings": warnings,
        "evidence_status": evidence_status,
        "confidence": confidence,
        "bridge_state": bridge_state,
        "rule_version": rule_version,
        "evidence_ids": _evidence_ids(assumptions),
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _normalise_assumptions(raw: Mapping[str, Any], *, as_of: str) -> dict[str, dict[str, Any]]:
    supplied = raw.get("assumptions")
    if supplied is None:
        supplied = raw
    if not isinstance(supplied, Mapping):
        raise ProductProfitBridgeError("assumptions must be an object")
    result: dict[str, dict[str, Any]] = {}
    for name, aliases in _ASSUMPTION_ALIASES.items():
        value_present = False
        value: Any = None
        for alias in aliases:
            if alias in supplied:
                value = supplied[alias]
                value_present = True
                break
        if not value_present or value in (None, ""):
            result[name] = {
                "value": None,
                "status": "MISSING",
                "unit": "",
                "evidence_ids": [],
                "source": "",
            }
            continue
        result[name] = _normalise_assumption(name, value, as_of=as_of)
    return result


def _normalise_assumption(name: str, raw: Any, *, as_of: str) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        value = raw.get("value") if "value" in raw else raw
        status = str(raw.get("status") or raw.get("verification_status") or "MODEL_ASSUMPTION").strip().upper()
        unit = str(raw.get("unit") or "").strip()
        evidence_ids = _string_list(raw.get("evidence_ids") or raw.get("source_evidence_ids"))
        source = str(raw.get("source") or "").strip()
        note = str(raw.get("note") or "").strip()
        assumption_as_of = str(raw.get("as_of") or "").strip()
    else:
        value = raw
        status = "MODEL_ASSUMPTION"
        unit = ""
        evidence_ids = []
        source = "manual_input"
        note = ""
        assumption_as_of = ""
    if status not in ASSUMPTION_STATUSES:
        raise ProductProfitBridgeError(f"unsupported assumption status for {name}: {status}")
    if assumption_as_of:
        _validate_as_of(assumption_as_of)
        if _as_of_key(assumption_as_of) > _as_of_key(as_of):
            raise ProductProfitBridgeError(
                f"assumption as_of is after bridge as_of: {name}"
            )
    interval = _normalise_interval(value, name) if status not in {"MISSING", "UNKNOWN", "CONFLICTING"} else None
    if status in FORMAL_EVIDENCE_STATUSES and not evidence_ids:
        status = "COMPANY_CLAIM"
        note = "; ".join(item for item in (note, "formal evidence status requires evidence_ids") if item)
    return {
        "value": _display(interval),
        "interval": interval,
        "status": status,
        "unit": unit,
        "evidence_ids": evidence_ids,
        "source": source,
        "note": note,
        "as_of": assumption_as_of,
    }


def _calculate(
    assumptions: Mapping[str, Mapping[str, Any]], allocation_method: str
) -> tuple[dict[str, Any], list[str], list[str]]:
    unknown: list[str] = []
    warnings: list[str] = []
    volume = _interval_for(assumptions, "volume", unknown)
    unit_price = _interval_for(assumptions, "unit_price", unknown)
    unit_cost = _interval_for(assumptions, "unit_cost", unknown)
    revenue = _mul(volume, unit_price)
    if revenue is None:
        unknown.append("REVENUE_REQUIRES_VOLUME_AND_UNIT_PRICE")
    variable_cost = _mul(volume, unit_cost)
    if variable_cost is None:
        unknown.extend(
            [
                "VARIABLE_COST_REQUIRES_VOLUME_AND_UNIT_COST",
                "VARIABLE_COST_MISSING",
            ]
        )
    gross_profit = _sub(revenue, variable_cost)

    direct_total = _interval_for(assumptions, "direct_expense_total", unknown, append_missing=False)
    direct_per_unit = _interval_for(assumptions, "direct_expense_per_unit", unknown, append_missing=False)
    if direct_total is not None and direct_per_unit is not None:
        direct_expense = None
        unknown.append("DIRECT_EXPENSE_TOTAL_AND_PER_UNIT_CONFLICT")
        warnings.append("both direct expense total and per-unit expense were supplied; neither was selected")
    elif direct_total is not None:
        direct_expense = direct_total
    elif direct_per_unit is not None:
        direct_expense = _mul(volume, direct_per_unit)
    else:
        direct_expense = None
        unknown.append("DIRECT_EXPENSE_NOT_ALLOCATED")
    operating_profit = _sub(gross_profit, direct_expense)

    working_capital = _interval_for(assumptions, "working_capital_investment", unknown)
    capex = _interval_for(assumptions, "capex", unknown)
    tax_interest = _interval_for(assumptions, "tax_and_interest_outflow", unknown)
    cashflow = _sub(_sub(_sub(operating_profit, working_capital), capex), tax_interest)
    if cashflow is None:
        unknown.append("CASHFLOW_REQUIRES_OPERATING_PROFIT_AND_CASH_OUTFLOWS")
    if allocation_method == "NOT_ALLOCABLE":
        warnings.append("allocation_method=NOT_ALLOCABLE prevents use as a product contribution")

    calculation = {
        "volume_assumption": _display(volume),
        "unit_price_assumption": _display(unit_price),
        "unit_cost_assumption": _display(unit_cost),
        "revenue_estimate": _display(revenue),
        "variable_cost_estimate": _display(variable_cost),
        "gross_profit_estimate": _display(gross_profit),
        "direct_expense_assumption": _display(direct_expense),
        "operating_profit_estimate": _display(operating_profit),
        "working_capital_assumption": _display(working_capital),
        "capex_assumption": _display(capex),
        "tax_and_interest_assumption": _display(tax_interest),
        "cashflow_contribution_estimate": _display(cashflow),
        "formulas": {
            "revenue": "volume * unit_price",
            "variable_cost": "volume * unit_cost",
            "gross_profit": "revenue - variable_cost",
            "operating_profit": "gross_profit - direct_expense",
            "cashflow_contribution": "operating_profit - working_capital_investment - capex - tax_and_interest_outflow",
        },
    }
    return calculation, _unique(unknown), _unique(warnings)


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
        raise ProductProfitBridgeError(str(error)) from error
    if projection is None or projection["scope_id"] != scope_id:
        return projection, "CONFLICTING"
    state = str(projection.get("researchability_state") or "INSUFFICIENT").upper()
    return projection, {"READY": "VERIFIED", "PARTIAL": "PARTIAL"}.get(state, state)


def _evidence_status(assumptions: Mapping[str, Mapping[str, Any]], bridge_state: str) -> str:
    statuses = [str(value.get("status") or "MISSING") for value in assumptions.values()]
    if "CONFLICTING" in statuses:
        return "CONFLICTING"
    if bridge_state in {"INSUFFICIENT", "BLOCKED"}:
        return "UNKNOWN"
    if bridge_state == "PARTIAL":
        return "PARTIAL"
    if all(status in FORMAL_EVIDENCE_STATUSES for status in statuses if status != "MISSING") and all(
        value.get("evidence_ids")
        for value in assumptions.values()
        if value.get("status") not in {"MISSING", "UNKNOWN"}
    ):
        return "VERIFIED"
    if any(status == "MODEL_ASSUMPTION" for status in statuses):
        return "MODEL_ASSUMPTION"
    return "PARTIAL"


def _confidence(
    assumptions: Mapping[str, Mapping[str, Any]], bridge_state: str, scope_status: str
) -> str:
    if bridge_state != "READY":
        return "LOW"
    if scope_status != "VERIFIED":
        return "MEDIUM"
    if all(
        value.get("status") in FORMAL_EVIDENCE_STATUSES and value.get("evidence_ids")
        for value in assumptions.values()
    ):
        return "HIGH"
    return "MEDIUM"


def _interval_for(
    assumptions: Mapping[str, Mapping[str, Any]],
    name: str,
    unknown: list[str],
    *,
    append_missing: bool = True,
) -> tuple[float, float] | None:
    item = assumptions[name]
    interval = item.get("interval")
    if interval is None and append_missing:
        unknown.append(f"{name.upper()}_MISSING")
    return interval


def _normalise_interval(value: Any, name: str) -> tuple[float, float]:
    if isinstance(value, Mapping) and ("low" in value or "high" in value):
        low = value.get("low")
        high = value.get("high")
    else:
        low = high = value
    try:
        low_number = float(low)
        high_number = float(high)
    except (TypeError, ValueError) as error:
        raise ProductProfitBridgeError(f"{name} must be numeric or a low/high interval") from error
    if not isfinite(low_number) or not isfinite(high_number):
        raise ProductProfitBridgeError(f"{name} must be finite")
    if low_number < 0 or high_number < 0:
        raise ProductProfitBridgeError(f"{name} cannot be negative")
    if low_number > high_number:
        raise ProductProfitBridgeError(f"{name} low cannot exceed high")
    return low_number, high_number


def _mul(left: tuple[float, float] | None, right: tuple[float, float] | None) -> tuple[float, float] | None:
    if left is None or right is None:
        return None
    values = (left[0] * right[0], left[0] * right[1], left[1] * right[0], left[1] * right[1])
    return min(values), max(values)


def _sub(left: tuple[float, float] | None, right: tuple[float, float] | None) -> tuple[float, float] | None:
    if left is None or right is None:
        return None
    return left[0] - right[1], left[1] - right[0]


def _display(value: tuple[float, float] | None) -> float | dict[str, float] | None:
    if value is None:
        return None
    low, high = value
    if low == high:
        return low
    return {"low": low, "high": high}


def _evidence_ids(assumptions: Mapping[str, Mapping[str, Any]]) -> list[str]:
    return _unique(
        evidence_id
        for item in assumptions.values()
        for evidence_id in _string_list(item.get("evidence_ids"))
    )


def _normalise_scenario(value: Any) -> str:
    text = str(value or "").strip().upper().replace("-", "_")
    aliases = {
        "BASE": "BASE_CASE",
        "UPSIDE": "UPSIDE_CASE",
        "BULL": "UPSIDE_CASE",
        "DOWNSIDE": "DOWNSIDE_CASE",
        "BEAR": "DOWNSIDE_CASE",
    }
    text = aliases.get(text, text)
    if text not in SCENARIOS:
        raise ProductProfitBridgeError(f"unsupported scenario: {text}")
    return text


def _validate_as_of(value: str) -> None:
    if not value:
        raise ProductProfitBridgeError("as_of is required")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            date.fromisoformat(value)
        except ValueError as error:
            raise ProductProfitBridgeError("as_of must be an ISO date or datetime") from error


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
        raise ProductProfitBridgeError("expected a string list")
    return [str(item).strip() for item in value if str(item).strip()]


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))
