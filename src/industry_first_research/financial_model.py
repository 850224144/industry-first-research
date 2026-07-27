"""Deterministic company financial, cash-flow, stress, and valuation model.

The model is intentionally separate from the directional research report.  It
only evaluates explicit facts and explicit scenario assumptions, preserves
intervals, and returns ``NOT_CALCULATED`` when a formula cannot be supported.
It does not create a target price, buy/sell instruction, or investment
conclusion.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from math import isfinite
from typing import Any

from .company_scope import CompanyScopeError, normalize_scope_reports, scope_item_for_company


FINANCIAL_MODEL_INPUT_SCHEMA_VERSION = "financial-model-input.v1"
FINANCIAL_MODEL_SCHEMA_VERSION = "financial-model.v1"
RULE_VERSION = "financial-model-rules.v1"

MODEL_STATES = {"READY", "PARTIAL", "INSUFFICIENT", "BLOCKED"}
VALUATION_STATES = {"READY", "PARTIAL", "NOT_CALCULATED", "BLOCKED"}
VALUATION_METHODS = {"PE", "PB", "FCF", "EV_EBITDA", "NOT_CALCULATED"}
SCENARIOS = ("BEAR", "BASE", "BULL")
FORMAL_EVIDENCE_STATUSES = {"VERIFIED", "CROSS_VALIDATED"}
FACT_STATUSES = {
    "VERIFIED",
    "CROSS_VALIDATED",
    "COMPANY_CLAIM",
    "MODEL_ASSUMPTION",
    "UNVERIFIED",
    "CONFLICTING",
    "UNKNOWN",
    "MISSING",
    "EXCLUDED_FUTURE",
}

FACT_NAMES = (
    "revenue",
    "gross_profit",
    "operating_profit",
    "net_profit",
    "ebitda",
    "operating_cashflow",
    "maintenance_capex",
    "expansion_capex",
    "cash",
    "debt",
    "current_assets",
    "current_liabilities",
    "receivables",
    "inventory",
    "shares_outstanding",
    "current_price",
    "book_equity",
)

_NON_NEGATIVE_FACTS = {
    "revenue",
    "gross_profit",
    "ebitda",
    "maintenance_capex",
    "expansion_capex",
    "cash",
    "debt",
    "current_assets",
    "current_liabilities",
    "receivables",
    "inventory",
    "shares_outstanding",
    "current_price",
    "book_equity",
}


class FinancialModelError(ValueError):
    """Raised when a financial model input violates its contract."""


def build_financial_model_report(
    payload: Mapping[str, Any],
    *,
    company_scope_reports: Mapping[str, Mapping[str, Any]] | None = None,
    model_id: str = "",
    rule_version: str = RULE_VERSION,
) -> dict[str, Any]:
    """Build financial metrics, cash-flow bridges, stress tests, and scenarios."""

    if not isinstance(payload, Mapping):
        raise FinancialModelError("financial model input must be a JSON object")
    if payload.get("schema_version") != FINANCIAL_MODEL_INPUT_SCHEMA_VERSION:
        raise FinancialModelError(f"input must be {FINANCIAL_MODEL_INPUT_SCHEMA_VERSION}")
    if not str(rule_version or "").strip():
        raise FinancialModelError("rule_version must not be empty")
    try:
        scope_reports = normalize_scope_reports(company_scope_reports)
    except CompanyScopeError as error:
        raise FinancialModelError(str(error)) from error
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise FinancialModelError("input must contain a non-empty items list")

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, Mapping):
            raise FinancialModelError("each financial model item must be an object")
        item = _build_item(
            raw_item,
            payload=payload,
            scope_reports=scope_reports,
            index=index,
            rule_version=rule_version,
        )
        if item["model_item_id"] in seen:
            raise FinancialModelError(f"duplicate model_item_id: {item['model_item_id']}")
        seen.add(item["model_item_id"])
        items.append(item)

    counts = Counter(item["model_state"] for item in items)
    report_key = str(model_id or payload.get("report_id") or "input").strip()
    return {
        "schema_version": FINANCIAL_MODEL_SCHEMA_VERSION,
        "report_id": f"financial-model-{report_key}",
        "as_of": str(payload.get("as_of") or ""),
        "rule_version": rule_version,
        "item_count": len(items),
        "model_state_counts": dict(counts),
        "items": items,
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "policy": {
            "explicit_facts_and_assumptions_only": True,
            "future_facts_excluded": True,
            "missing_formula_inputs_not_defaulted": True,
            "intervals_preserved": True,
            "numeric_valuation_is_observation_only": True,
            "target_price_generated": False,
            "investment_conclusion": False,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
    }


def validate_financial_model_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a stored financial model envelope without changing it."""

    if not isinstance(report, Mapping) or report.get("schema_version") != FINANCIAL_MODEL_SCHEMA_VERSION:
        raise FinancialModelError(f"input must be {FINANCIAL_MODEL_SCHEMA_VERSION}")
    if report.get("immutable") is not True:
        raise FinancialModelError("financial model report must be immutable")
    items = report.get("items")
    if not isinstance(items, list):
        raise FinancialModelError("financial model report has no items list")
    errors: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            errors.append("item is not an object")
            continue
        identifier = str(item.get("model_item_id") or "")
        if not identifier:
            errors.append("model_item_id is missing")
        elif identifier in seen:
            errors.append(f"duplicate model_item_id: {identifier}")
        seen.add(identifier)
        if str(item.get("model_state") or "") not in MODEL_STATES:
            errors.append(f"unsupported model_state: {identifier}")
    return {
        "schema_version": "financial-model-validation.v1",
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
    scope_id = str(raw.get("scope_id") or payload.get("scope_id") or "").strip()
    as_of = str(raw.get("as_of") or payload.get("as_of") or "").strip()
    if not company_id:
        raise FinancialModelError("company_id is required")
    if not scope_id:
        raise FinancialModelError("scope_id is required")
    _validate_as_of(as_of)
    scope_projection, scope_status = _scope_status(scope_reports, company_id, scope_id)

    facts = _normalise_facts(raw.get("facts") or {}, as_of)
    metrics, metric_unknowns = _financial_metrics(facts)
    cashflow_bridge, cashflow_unknowns = _cashflow_bridge(facts)
    stress_tests, stress_unknowns = _stress_tests(raw, facts, as_of)
    valuation_scenarios, valuation_unknowns = _valuation_scenarios(raw, facts, as_of)
    unknowns = _unique([*metric_unknowns, *cashflow_unknowns, *stress_unknowns, *valuation_unknowns])
    warnings: list[str] = []
    if scope_status != "VERIFIED":
        warnings.append("scope is not verified for this financial model")
    if any(fact.get("status") == "EXCLUDED_FUTURE" for fact in facts.values()):
        warnings.append("future facts were excluded from historical calculations")
    if any(scenario["valuation_state"] == "NOT_CALCULATED" for scenario in valuation_scenarios):
        warnings.append("one or more valuation scenarios lack explicit formula inputs")

    if scope_status == "CONFLICTING":
        model_state = "BLOCKED"
    elif not facts or all(fact["status"] in {"MISSING", "UNKNOWN", "EXCLUDED_FUTURE"} for fact in facts.values()):
        model_state = "INSUFFICIENT"
    elif unknowns:
        model_state = "PARTIAL"
    else:
        model_state = "READY"

    identifier = str(raw.get("model_item_id") or "").strip() or f"financial-{company_id}-{index + 1}"
    return {
        "model_item_id": identifier,
        "company_id": company_id,
        "display_name": str(raw.get("display_name") or ""),
        "scope_id": scope_id,
        "scope_status": scope_status,
        "scope_projection": scope_projection,
        "as_of": as_of,
        "facts": facts,
        "financial_metrics": metrics,
        "cashflow_bridge": cashflow_bridge,
        "stress_tests": stress_tests,
        "valuation_scenarios": valuation_scenarios,
        "unknowns": unknowns,
        "warnings": warnings,
        "evidence_ids": _evidence_ids(facts),
        "evidence_status": _evidence_status(facts, model_state),
        "confidence": _confidence(model_state, scope_status, facts),
        "model_state": model_state,
        "rule_version": rule_version,
        "numeric_valuation_included": False,
        "target_price_generated": False,
        "investment_conclusion": False,
        "execution_enabled": False,
        "read_only": True,
        "review_only": True,
    }


def _normalise_facts(raw_facts: Any, as_of: str) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_facts, Mapping):
        raise FinancialModelError("facts must be an object")
    result: dict[str, dict[str, Any]] = {}
    for name in FACT_NAMES:
        raw = raw_facts.get(name)
        if raw in (None, ""):
            result[name] = _missing_fact()
            continue
        result[name] = _normalise_fact(name, raw, as_of)
    return result


def _normalise_fact(name: str, raw: Any, as_of: str) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        value = raw.get("value") if "value" in raw else raw.get("values")
        if value is None and ("low" in raw or "high" in raw):
            value = {"low": raw.get("low"), "high": raw.get("high")}
        status = str(raw.get("status") or raw.get("verification_status") or "MODEL_ASSUMPTION").strip().upper()
        evidence_ids = _string_list(raw.get("evidence_ids") or raw.get("source_evidence_ids"))
        period = str(raw.get("period") or "").strip()
        fact_as_of = str(raw.get("as_of") or "").strip()
        unit = str(raw.get("unit") or "").strip()
        source = str(raw.get("source") or "").strip()
    else:
        value = raw
        status = "MODEL_ASSUMPTION"
        evidence_ids = []
        period = ""
        fact_as_of = ""
        unit = ""
        source = "manual_input"
    if status not in FACT_STATUSES:
        raise FinancialModelError(f"unsupported fact status for {name}: {status}")
    interval: tuple[float, float] | None = None
    future = False
    if fact_as_of:
        _validate_as_of(fact_as_of)
        future = _as_of_key(fact_as_of) > _as_of_key(as_of)
    if future:
        status = "EXCLUDED_FUTURE"
    elif status not in {"MISSING", "UNKNOWN", "CONFLICTING"}:
        interval = _normalise_interval(value, name, allow_negative=name not in _NON_NEGATIVE_FACTS)
    if status in FORMAL_EVIDENCE_STATUSES and not evidence_ids:
        status = "COMPANY_CLAIM"
    return {
        "value": _display(interval),
        "interval": interval,
        "status": status,
        "evidence_ids": evidence_ids,
        "period": period,
        "as_of": fact_as_of,
        "unit": unit,
        "source": source,
        "future": future,
    }


def _missing_fact() -> dict[str, Any]:
    return {
        "value": None,
        "interval": None,
        "status": "MISSING",
        "evidence_ids": [],
        "period": "",
        "as_of": "",
        "unit": "",
        "source": "",
        "future": False,
    }


def _financial_metrics(facts: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    unknown: list[str] = []
    revenue = _fact(facts, "revenue", unknown)
    gross_profit = _fact(facts, "gross_profit", unknown)
    operating_profit = _fact(facts, "operating_profit", unknown)
    net_profit = _fact(facts, "net_profit", unknown)
    operating_cashflow = _fact(facts, "operating_cashflow", unknown)
    cash = _fact(facts, "cash", unknown)
    debt = _fact(facts, "debt", unknown)
    current_assets = _fact(facts, "current_assets", unknown)
    current_liabilities = _fact(facts, "current_liabilities", unknown)
    receivables = _fact(facts, "receivables", unknown)
    inventory = _fact(facts, "inventory", unknown)
    fcf = _sub(operating_cashflow, _fact(facts, "maintenance_capex", unknown))
    if fcf is None:
        unknown.append("free_cash_flow_requires_operating_cashflow_and_maintenance_capex")
    metrics = {
        "gross_margin": _ratio(gross_profit, revenue, "gross_margin", unknown),
        "operating_margin": _ratio(operating_profit, revenue, "operating_margin", unknown),
        "net_margin": _ratio(net_profit, revenue, "net_margin", unknown),
        "cash_conversion_ratio": _ratio(operating_cashflow, net_profit, "cash_conversion_ratio", unknown),
        "free_cash_flow_after_maintenance_capex": _display(fcf),
        "free_cash_flow_margin": _ratio(fcf, revenue, "free_cash_flow_margin", unknown),
        "current_ratio": _ratio(current_assets, current_liabilities, "current_ratio", unknown),
        "debt_to_cash": _ratio(debt, cash, "debt_to_cash", unknown),
        "net_debt": _sub(debt, cash),
        "working_capital": _sub(_add(receivables, inventory), current_liabilities),
        "working_capital_to_revenue": _ratio(_sub(_add(receivables, inventory), current_liabilities), revenue, "working_capital_to_revenue", unknown),
    }
    return metrics, _unique(unknown)


def _cashflow_bridge(facts: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    unknown: list[str] = []
    operating_cashflow = _fact(facts, "operating_cashflow", unknown)
    maintenance = _fact(facts, "maintenance_capex", unknown)
    expansion = _fact(facts, "expansion_capex", unknown)
    after_maintenance = _sub(operating_cashflow, maintenance)
    after_all = _sub(after_maintenance, expansion)
    if after_maintenance is None:
        unknown.append("maintenance_capex_or_operating_cashflow_missing")
    if after_all is None:
        unknown.append("expansion_capex_missing_for_full_free_cash_flow")
    return {
        "status": "READY" if after_all is not None else "PARTIAL" if after_maintenance is not None else "NOT_CALCULATED",
        "operating_cashflow": _display(operating_cashflow),
        "maintenance_capex": _display(maintenance),
        "free_cash_flow_after_maintenance_capex": _display(after_maintenance),
        "expansion_capex": _display(expansion),
        "free_cash_flow_after_all_capex": _display(after_all),
        "formula": "operating_cashflow - maintenance_capex - expansion_capex",
        "unknowns": _unique(unknown),
        "cash_conversion_verified": after_all is not None,
    }, _unique(unknown)


def _stress_tests(
    raw: Mapping[str, Any], facts: Mapping[str, Mapping[str, Any]], as_of: str
) -> tuple[list[dict[str, Any]], list[str]]:
    raw_tests = raw.get("stress_tests")
    if raw_tests is None:
        raw_tests = []
    if not isinstance(raw_tests, list):
        raise FinancialModelError("stress_tests must be a list")
    results: list[dict[str, Any]] = []
    unknown: list[str] = []
    for raw_test in raw_tests:
        if not isinstance(raw_test, Mapping):
            raise FinancialModelError("each stress test must be an object")
        scenario = str(raw_test.get("scenario") or "").strip().upper()
        if not scenario:
            raise FinancialModelError("stress test scenario is required")
        cash = _scenario_value(raw_test, ("cash", "available_cash"), facts.get("cash"), as_of, "cash")
        burn = _scenario_value(raw_test, ("monthly_cash_burn", "cash_burn"), None, as_of, "monthly_cash_burn")
        debt_due = _scenario_value(raw_test, ("debt_due", "debt_maturity"), None, as_of, "debt_due")
        minimum_cash = _scenario_value(raw_test, ("minimum_cash_balance", "minimum_cash"), None, as_of, "minimum_cash_balance")
        horizon = _scenario_value(raw_test, ("horizon_months",), None, as_of, "horizon_months")
        runway = None
        if cash is not None and burn is not None and minimum_cash is not None and burn[0] > 0:
            runway = _div(_sub(cash, minimum_cash), burn)
        elif burn is None:
            unknown.append(f"{scenario}:monthly_cash_burn")
        available_after_min = _sub(cash, minimum_cash)
        debt_gap = _max_zero(_sub(debt_due, available_after_min))
        if debt_gap is None:
            unknown.append(f"{scenario}:debt_gap")
        dependency = "UNKNOWN"
        if debt_gap is not None and runway is not None:
            if debt_gap[1] > 0:
                dependency = "REFINANCING_DEPENDENT"
            elif horizon is not None and runway[0] < horizon[0]:
                dependency = "REFINANCING_DEPENDENT"
            else:
                dependency = "SELF_FUNDED"
        elif cash is not None and minimum_cash is not None and available_after_min is not None and available_after_min[1] < 0:
            dependency = "EXTERNAL_SUPPORT_DEPENDENT"
        state = "READY" if runway is not None and debt_gap is not None else "NOT_CALCULATED"
        if state != "READY":
            unknown.append(f"{scenario}:cash_runway_or_debt_gap")
        results.append({
            "scenario": scenario,
            "horizon_months": _display(horizon),
            "cash_runway_months": _display(runway),
            "debt_gap": _display(debt_gap),
            "minimum_cash_balance": _display(minimum_cash),
            "survival_dependency": dependency,
            "state": state,
            "inputs": {
                "cash": _display(cash),
                "monthly_cash_burn": _display(burn),
                "debt_due": _display(debt_due),
            },
            "formula": "max((cash - minimum_cash_balance) / monthly_cash_burn, 0)",
            "review_only": True,
            "investment_conclusion": False,
        })
    return results, _unique(unknown)


def _valuation_scenarios(
    raw: Mapping[str, Any], facts: Mapping[str, Mapping[str, Any]], as_of: str
) -> tuple[list[dict[str, Any]], list[str]]:
    raw_scenarios = raw.get("valuation_scenarios") or raw.get("scenarios") or []
    if not isinstance(raw_scenarios, list):
        raise FinancialModelError("valuation_scenarios must be a list")
    by_name: dict[str, Mapping[str, Any]] = {}
    for raw_scenario in raw_scenarios:
        if not isinstance(raw_scenario, Mapping):
            raise FinancialModelError("each valuation scenario must be an object")
        name = str(raw_scenario.get("scenario") or "").strip().upper()
        if name not in SCENARIOS:
            raise FinancialModelError(f"unsupported valuation scenario: {name or '<empty>'}")
        if name in by_name:
            raise FinancialModelError(f"duplicate valuation scenario: {name}")
        by_name[name] = raw_scenario

    results: list[dict[str, Any]] = []
    unknown: list[str] = []
    for name in SCENARIOS:
        raw_scenario = by_name.get(name, {})
        assumptions = raw_scenario.get("assumptions") or raw_scenario
        if not isinstance(assumptions, Mapping):
            raise FinancialModelError(f"{name} assumptions must be an object")
        method = str(assumptions.get("valuation_method") or "NOT_CALCULATED").strip().upper()
        if method not in VALUATION_METHODS:
            raise FinancialModelError(f"unsupported valuation_method: {method}")
        multiple = _scenario_value(assumptions, ("valuation_multiple", "multiple"), None, as_of, "valuation_multiple")
        shares = _scenario_value(assumptions, ("shares_outstanding", "shares"), facts.get("shares_outstanding"), as_of, "shares_outstanding")
        current_price = _scenario_value(assumptions, ("current_price",), facts.get("current_price"), as_of, "current_price")
        revenue = _scenario_value(assumptions, ("forecast_revenue",), None, as_of, "forecast_revenue")
        if revenue is None:
            current_revenue = _fact(facts, "revenue", [])
            growth = _scenario_value(assumptions, ("revenue_growth",), None, as_of, "revenue_growth", allow_negative=True)
            if current_revenue is not None and growth is not None:
                revenue = _mul(current_revenue, _add((1.0, 1.0), growth))
        net_profit = _scenario_value(assumptions, ("forecast_net_profit",), None, as_of, "forecast_net_profit", allow_negative=True)
        net_margin = _scenario_value(assumptions, ("net_margin",), None, as_of, "net_margin", allow_negative=True)
        if net_profit is None and revenue is not None and net_margin is not None:
            net_profit = _mul(revenue, net_margin)
        ebitda = _scenario_value(assumptions, ("forecast_ebitda",), None, as_of, "forecast_ebitda", allow_negative=True)
        fcf = _scenario_value(assumptions, ("forecast_fcf",), None, as_of, "forecast_fcf", allow_negative=True)
        cfo_conversion = _scenario_value(assumptions, ("cfo_conversion",), None, as_of, "cfo_conversion", allow_negative=True)
        capex = _scenario_value(assumptions, ("forecast_capex",), None, as_of, "forecast_capex")
        if fcf is None and net_profit is not None and cfo_conversion is not None and capex is not None:
            fcf = _sub(_mul(net_profit, cfo_conversion), capex)
        net_debt = _scenario_value(assumptions, ("net_debt",), None, as_of, "net_debt", allow_negative=True)
        if net_debt is None:
            net_debt = _sub(_fact(facts, "debt", []), _fact(facts, "cash", []))
        book_equity = _scenario_value(assumptions, ("book_equity",), facts.get("book_equity"), as_of, "book_equity", allow_negative=True)
        driver = {"PE": net_profit, "PB": book_equity, "FCF": fcf, "EV_EBITDA": ebitda}.get(method)
        equity_value = None
        if method != "NOT_CALCULATED" and driver is not None and multiple is not None:
            equity_value = _mul(driver, multiple)
            if method == "EV_EBITDA":
                equity_value = _sub(equity_value, net_debt)
        per_share = _div(equity_value, shares)
        market_cap = _mul(current_price, shares)
        valuation_state = "READY" if per_share is not None else "NOT_CALCULATED"
        if method == "NOT_CALCULATED":
            valuation_state = "NOT_CALCULATED"
        if valuation_state != "READY":
            unknown.append(f"{name}:valuation_inputs")
        results.append({
            "scenario": name,
            "treatment": str(raw_scenario.get("treatment") or {"BEAR": "STRESS", "BASE": "INCLUDED", "BULL": "OPTIONAL"}[name]).upper(),
            "valuation_method": method,
            "valuation_multiple": _display(multiple),
            "forecast_revenue": _display(revenue),
            "forecast_net_profit": _display(net_profit),
            "forecast_ebitda": _display(ebitda),
            "forecast_fcf": _display(fcf),
            "net_debt": _display(net_debt),
            "equity_value_observation": _display(equity_value),
            "equity_value_per_share_observation": _display(per_share),
            "current_market_cap_observation": _display(market_cap),
            "valuation_state": valuation_state,
            "target_price_generated": False,
            "investment_conclusion": False,
            "unknowns": [] if valuation_state == "READY" else [f"{name}:valuation_inputs"],
            "formula": _valuation_formula(method),
        })
    return results, _unique(unknown)


def _scenario_value(
    raw: Mapping[str, Any],
    names: Sequence[str],
    fallback: Mapping[str, Any] | None,
    as_of: str,
    field: str,
    *,
    allow_negative: bool = False,
) -> tuple[float, float] | None:
    value: Any = None
    for name in names:
        if name in raw:
            value = raw[name]
            break
    if value is None and fallback is not None:
        return fallback.get("interval")
    if value is None:
        return None
    if isinstance(value, Mapping):
        fact_as_of = str(value.get("as_of") or "").strip()
        if fact_as_of:
            _validate_as_of(fact_as_of)
            if _as_of_key(fact_as_of) > _as_of_key(as_of):
                return None
        status = str(value.get("status") or "MODEL_ASSUMPTION").upper()
        if status in {"UNKNOWN", "MISSING", "CONFLICTING", "EXCLUDED_FUTURE"}:
            return None
        value = value.get("value") if "value" in value else value
    return _normalise_interval(value, field, allow_negative=allow_negative)


def _valuation_formula(method: str) -> str:
    return {
        "PE": "forecast_net_profit * valuation_multiple",
        "PB": "book_equity * valuation_multiple",
        "FCF": "forecast_fcf * valuation_multiple",
        "EV_EBITDA": "forecast_ebitda * valuation_multiple - net_debt",
        "NOT_CALCULATED": "not_calculated",
    }[method]


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
        raise FinancialModelError(str(error)) from error
    if projection is None or projection["scope_id"] != scope_id:
        return projection, "CONFLICTING"
    state = str(projection.get("researchability_state") or "INSUFFICIENT").upper()
    return projection, {"READY": "VERIFIED", "PARTIAL": "PARTIAL"}.get(state, state)


def _financial_fact(
    facts: Mapping[str, Mapping[str, Any]], name: str, unknown: list[str]
) -> tuple[float, float] | None:
    item = facts.get(name) or _missing_fact()
    interval = item.get("interval")
    if interval is None:
        unknown.append(f"{name}_missing")
    return interval


def _fact(facts: Mapping[str, Mapping[str, Any]], name: str, unknown: list[str]) -> tuple[float, float] | None:
    return _financial_fact(facts, name, unknown)


def _ratio(
    numerator: tuple[float, float] | None,
    denominator: tuple[float, float] | None,
    name: str,
    unknown: list[str],
) -> float | dict[str, float] | None:
    value = _div(numerator, denominator)
    if value is None:
        unknown.append(f"{name}_not_calculated")
    return _display(value)


def _evidence_status(facts: Mapping[str, Mapping[str, Any]], model_state: str) -> str:
    statuses = [str(item.get("status") or "MISSING") for item in facts.values()]
    if "CONFLICTING" in statuses:
        return "CONFLICTING"
    if model_state in {"INSUFFICIENT", "BLOCKED"}:
        return "UNKNOWN"
    if model_state == "PARTIAL":
        return "PARTIAL"
    present = [item for item in facts.values() if item.get("status") not in {"MISSING", "UNKNOWN", "EXCLUDED_FUTURE"}]
    if present and all(item.get("status") in FORMAL_EVIDENCE_STATUSES and item.get("evidence_ids") for item in present):
        return "VERIFIED"
    if any(item.get("status") == "MODEL_ASSUMPTION" for item in present):
        return "MODEL_ASSUMPTION"
    return "PARTIAL"


def _confidence(model_state: str, scope_status: str, facts: Mapping[str, Mapping[str, Any]]) -> str:
    if model_state != "READY":
        return "LOW"
    if scope_status != "VERIFIED":
        return "MEDIUM"
    present = [item for item in facts.values() if item.get("status") not in {"MISSING", "UNKNOWN", "EXCLUDED_FUTURE"}]
    return "HIGH" if present and all(item.get("status") in FORMAL_EVIDENCE_STATUSES and item.get("evidence_ids") for item in present) else "MEDIUM"


def _evidence_ids(facts: Mapping[str, Mapping[str, Any]]) -> list[str]:
    return _unique(
        evidence_id
        for item in facts.values()
        for evidence_id in _string_list(item.get("evidence_ids"))
    )


def _normalise_interval(value: Any, name: str, *, allow_negative: bool = False) -> tuple[float, float]:
    if isinstance(value, Mapping) and ("low" in value or "high" in value):
        low = value.get("low")
        high = value.get("high")
    else:
        low = high = value
    try:
        low_number = float(low)
        high_number = float(high)
    except (TypeError, ValueError) as error:
        raise FinancialModelError(f"{name} must be numeric or a low/high interval") from error
    if not isfinite(low_number) or not isfinite(high_number):
        raise FinancialModelError(f"{name} must be finite")
    if not allow_negative and (low_number < 0 or high_number < 0):
        raise FinancialModelError(f"{name} cannot be negative")
    if low_number > high_number:
        raise FinancialModelError(f"{name} low cannot exceed high")
    return low_number, high_number


def _add(left: tuple[float, float] | None, right: tuple[float, float] | None) -> tuple[float, float] | None:
    if left is None or right is None:
        return None
    return left[0] + right[0], left[1] + right[1]


def _sub(left: tuple[float, float] | None, right: tuple[float, float] | None) -> tuple[float, float] | None:
    if left is None or right is None:
        return None
    return left[0] - right[1], left[1] - right[0]


def _mul(left: tuple[float, float] | None, right: tuple[float, float] | None) -> tuple[float, float] | None:
    if left is None or right is None:
        return None
    values = (left[0] * right[0], left[0] * right[1], left[1] * right[0], left[1] * right[1])
    return min(values), max(values)


def _div(left: tuple[float, float] | None, right: tuple[float, float] | None) -> tuple[float, float] | None:
    if left is None or right is None or right[0] <= 0 <= right[1]:
        return None
    values = (left[0] / right[0], left[0] / right[1], left[1] / right[0], left[1] / right[1])
    return min(values), max(values)


def _max_zero(value: tuple[float, float] | None) -> tuple[float, float] | None:
    if value is None:
        return None
    return max(0.0, value[0]), max(0.0, value[1])


def _display(value: tuple[float, float] | None) -> float | dict[str, float] | None:
    if value is None:
        return None
    if value[0] == value[1]:
        return value[0]
    return {"low": value[0], "high": value[1]}


def _validate_as_of(value: str) -> None:
    if not value:
        raise FinancialModelError("as_of is required")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            date.fromisoformat(value)
        except ValueError as error:
            raise FinancialModelError("as_of must be an ISO date or datetime") from error


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
        raise FinancialModelError("expected a string list")
    return [str(item).strip() for item in value if str(item).strip()]


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))
