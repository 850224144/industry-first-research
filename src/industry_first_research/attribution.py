"""Compare a locked simulation snapshot with its fixed benchmark.

This module deliberately keeps observable return accounting separate from the
explanatory attribution layer.  The latter is only a rough decomposition
unless the caller supplies a complete, auditable attribution package.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from hashlib import sha256
from math import isfinite, sqrt
from statistics import mean, pstdev
from typing import Any


class AttributionError(ValueError):
    """Raised when an attribution input violates the locked-record contract."""


ATTRIBUTION_SCHEMA_VERSION = "attribution-result.v1"
INPUT_SCHEMA_VERSION = "attribution-input.v1"
DECISION_SNAPSHOT_SCHEMA_VERSION = "decision-snapshot.v1"
RULE_VERSION = "attribution-rules.v1"
_EVALUATION_LABELS = {
    "THESIS_WRONG",
    "PARTIALLY_CORRECT",
    "THESIS_RIGHT_TIMING_EARLY",
    "THESIS_RIGHT_PRICE_UNREALIZED",
    "OUTCOME_BETA_OR_EVENT",
    "NOT_EVALUABLE",
}
_CONTRIBUTION_FIELDS = (
    "beta_contribution",
    "fundamental_contribution",
    "valuation_contribution",
    "structure_contribution",
    "event_residual",
    "basis_contribution",
    "term_structure_contribution",
    "roll_contribution",
    "supply_demand_contribution",
)


class _EvidenceGap(ValueError):
    """Internal marker for a valid but not evaluable evidence package."""


def build_attribution_report(
    decision_snapshot: Mapping[str, Any],
    outcome_input: Mapping[str, Any],
    *,
    closed_at: str = "",
    rule_version: str = RULE_VERSION,
    attribution_id: str = "",
) -> dict[str, Any]:
    """Build a read-only result from a locked company or futures snapshot.

    ``outcome_input`` must contain the price/benchmark sequences used for the
    review.  A valid shape with missing or incomparable observations produces a
    ``NOT_EVALUABLE`` report rather than a fabricated result.
    """

    _validate_snapshot(decision_snapshot)
    _validate_input(outcome_input)
    if not rule_version.strip():
        raise AttributionError("rule_version must not be empty")

    decision = decision_snapshot["decision"]
    subject_type = str(decision_snapshot.get("subject_type") or "").strip().lower()
    close_value = str(closed_at or outcome_input.get("closed_at") or "").strip()
    if not close_value:
        raise AttributionError("closed_at is required")
    closed_day = _calendar_day(close_value, "closed_at")
    review_day = _calendar_day(decision.get("review_date"), "review_date")
    base = _base_report(
        decision_snapshot,
        outcome_input,
        close_value,
        rule_version=rule_version,
        attribution_id=attribution_id,
    )

    if closed_day < review_day:
        return _not_evaluable(
            base,
            "closed_at is before the locked review_date; the outcome period is not due",
        )

    try:
        if subject_type == "listed_company":
            result = _company_result(decision_snapshot, outcome_input, base)
        else:
            result = _futures_result(decision_snapshot, outcome_input, base)
    except _EvidenceGap as error:
        return _not_evaluable(base, str(error))
    return result


def build_attribution_result(
    decision_snapshot: Mapping[str, Any],
    outcome_input: Mapping[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    """Compatibility alias for callers that use the storage table name."""

    return build_attribution_report(decision_snapshot, outcome_input, **kwargs)


def _validate_snapshot(snapshot: Any) -> None:
    if not isinstance(snapshot, Mapping):
        raise AttributionError("decision snapshot must be a JSON object")
    if snapshot.get("schema_version") != DECISION_SNAPSHOT_SCHEMA_VERSION:
        raise AttributionError("input must be a decision-snapshot.v1 snapshot")
    if str(snapshot.get("status") or "").upper() != "LOCKED":
        raise AttributionError("attribution requires a LOCKED decision snapshot")
    if snapshot.get("immutable") is not True:
        raise AttributionError("decision snapshot must be immutable")
    if snapshot.get("simulation_only") is not True:
        raise AttributionError("attribution input must be simulation-only")
    if snapshot.get("execution_enabled") is not False:
        raise AttributionError("attribution refuses execution-enabled snapshots")
    if not isinstance(snapshot.get("decision"), Mapping):
        raise AttributionError("decision snapshot has no decision object")
    benchmark = snapshot["decision"].get("benchmark")
    if not isinstance(benchmark, Mapping) or not benchmark:
        raise AttributionError("decision snapshot has no locked benchmark")
    if benchmark.get("locked") is not True:
        raise AttributionError("decision snapshot benchmark must be locked")
    if str(snapshot.get("snapshot_id") or "").strip() == "":
        raise AttributionError("decision snapshot_id is required")


def _validate_input(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise AttributionError("attribution input must be a JSON object")
    schema = value.get("schema_version")
    if schema != INPUT_SCHEMA_VERSION:
        raise AttributionError("input must be an attribution-input.v1 report")


def _base_report(
    snapshot: Mapping[str, Any],
    outcome: Mapping[str, Any],
    closed_at: str,
    *,
    rule_version: str,
    attribution_id: str,
) -> dict[str, Any]:
    snapshot_id = str(snapshot["snapshot_id"])
    result_id = attribution_id.strip() or f"{snapshot_id}-{_compact(closed_at)}"
    benchmark = dict(snapshot["decision"]["benchmark"])
    return {
        "schema_version": ATTRIBUTION_SCHEMA_VERSION,
        "attribution_id": f"attribution-{result_id}",
        "decision_id": snapshot_id,
        "decision_snapshot_hash": _snapshot_hash(snapshot),
        "closed_at": closed_at,
        "review_date": str(snapshot["decision"].get("review_date") or ""),
        "subject_type": str(snapshot.get("subject_type") or ""),
        "subject_id": str(
            snapshot.get("subject_id")
            or snapshot["decision"].get("subject_id")
            or snapshot.get("company_id")
            or ""
        ),
        "benchmark_locked": benchmark,
        "rule_version": rule_version,
        "evaluation_state": "EVALUABLE",
        "evaluation_reason": "",
        "evaluation_label": None,
        "confidence": "ROUGH_ATTRIBUTION",
        "methodology": {
            "observed_return_accounting": (
                "Endpoint and path accounting from the supplied dated series; "
                "no post-period benchmark replacement."
            ),
            "explanatory_attribution": (
                "Explanatory factors are estimates or explicitly supplied review "
                "inputs, not causal proof."
            ),
            "source_outcome_input_schema": outcome.get("schema_version") or "unversioned",
        },
        "data_quality": {
            "status": "PENDING",
            "reasons": [],
            "asset_series_comparable": False,
            "benchmark_series_comparable": False,
        },
        "asset_return": None,
        "asset_annualized_return": None,
        "benchmark_return": None,
        "benchmark_annualized_return": None,
        "excess_return": None,
        "max_drawdown": None,
        "volatility": None,
        "holding_period_days": None,
        "return_components": {
            "price_return": None,
            "dividend_return": None,
            "fx_return": None,
            "cost_return": None,
            "fee_assumption": outcome.get("fee_assumption"),
            "slippage_assumption": outcome.get("slippage_assumption"),
        },
        "contributions": {field: None for field in _CONTRIBUTION_FIELDS},
        "contribution_sources": {},
        "comparison": {
            "status": "PENDING",
            "excess_return_comparable": True,
            "reason": "",
        },
        "policy": {
            "locked_snapshot_unchanged": True,
            "benchmark_taken_from_snapshot": True,
            "not_investment_conclusion": True,
            "read_only": True,
            "simulation_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _company_result(
    snapshot: Mapping[str, Any],
    outcome: Mapping[str, Any],
    base: dict[str, Any],
) -> dict[str, Any]:
    _validate_benchmark_identity(snapshot, outcome)
    _validate_subject_identity(snapshot, outcome)
    asset = _normalise_series(
        _series_input(outcome, ("asset_series", "asset_prices", "price_series")),
        "asset_series",
        value_keys=("price", "value", "close"),
    )
    benchmark = _normalise_series(
        _benchmark_input(outcome),
        "benchmark_series",
        value_keys=("value", "price", "close"),
    )
    _check_comparable_series(asset, benchmark)
    _check_period(
        asset,
        snapshot["decision"].get("decision_at"),
        base["closed_at"],
        "asset_series",
    )

    decision = snapshot["decision"]
    asset_currency = str(outcome.get("asset_currency") or "").strip()
    reporting_currency = str(outcome.get("reporting_currency") or asset_currency).strip()
    fx = None
    if asset_currency and reporting_currency and asset_currency != reporting_currency:
        fx = _normalise_series(
            outcome.get("fx_series") or outcome.get("fx_prices"),
            "fx_series",
            value_keys=("value", "price", "close"),
        )
        _check_same_dates(asset, fx, "asset and FX series")

    metrics = _company_metrics(asset, benchmark, fx=fx, outcome=outcome)
    base.update(metrics)
    base["data_quality"].update(
        {
            "status": "OK",
            "asset_series_comparable": True,
            "benchmark_series_comparable": True,
            "reasons": [],
        }
    )
    base["comparison"] = {
        "status": "COMPARABLE",
        "excess_return_comparable": True,
        "reason": "Both dated series share the same entry and close dates.",
        "benchmark_id": _benchmark_identifier(decision["benchmark"]),
    }
    contributions = _contributions(
        snapshot, outcome, asset, benchmark, is_futures=False
    )
    base["contributions"] = contributions["values"]
    base["contribution_sources"] = contributions["sources"]
    base["confidence"] = contributions["confidence"]
    base["evaluation_label"] = _evaluation_label(snapshot, outcome, base)
    return base


def _company_metrics(
    asset: Sequence[Mapping[str, Any]],
    benchmark: Sequence[Mapping[str, Any]],
    *,
    fx: Sequence[Mapping[str, Any]] | None,
    outcome: Mapping[str, Any],
) -> dict[str, Any]:
    start_price = float(asset[0]["value"])
    if start_price <= 0:
        raise _EvidenceGap("asset entry price must be positive")
    dividends = sum(float(row.get("dividend") or 0.0) for row in asset)
    fees = sum(float(row.get("fee") or 0.0) for row in asset)
    slippage = sum(float(row.get("slippage") or 0.0) for row in asset)
    fees += _optional_number(outcome.get("total_fees"), "total_fees") or 0.0
    slippage += _optional_number(outcome.get("total_slippage"), "total_slippage") or 0.0
    cost_rate = _optional_number(outcome.get("cost_rate"), "cost_rate") or 0.0
    rate_cost = start_price * cost_rate
    total_cost = fees + slippage + rate_cost
    price_return = float(asset[-1]["value"]) / start_price - 1.0
    dividend_return = dividends / start_price
    cost_return = -total_cost / start_price
    local_return = (float(asset[-1]["value"]) + dividends - total_cost) / start_price - 1.0

    fx_return = 0.0
    fx_values: Sequence[Mapping[str, Any]] | None = None
    if fx is not None:
        fx_start = float(fx[0]["value"])
        if fx_start <= 0:
            raise _EvidenceGap("FX entry value must be positive")
        fx_return = float(fx[-1]["value"]) / fx_start - 1.0
        fx_values = fx
    asset_return = (1.0 + local_return) * (1.0 + fx_return) - 1.0

    wealth = _wealth_path(asset, total_cost=total_cost, fx=fx_values)
    asset_period_returns = _period_returns(wealth)
    benchmark_wealth = _wealth_path(benchmark, total_cost=0.0, fx=None)
    benchmark_period_returns = _period_returns(benchmark_wealth)
    holding_days = (asset[-1]["day"] - asset[0]["day"]).days
    if holding_days <= 0:
        raise _EvidenceGap("asset series must span a positive holding period")
    benchmark_start = float(benchmark[0]["value"])
    if benchmark_start <= 0:
        raise _EvidenceGap("benchmark entry value must be positive")
    benchmark_return = benchmark_wealth[-1] / benchmark_wealth[0] - 1.0
    return {
        "asset_return": asset_return,
        "asset_annualized_return": _annualized(asset_return, holding_days),
        "benchmark_return": benchmark_return,
        "benchmark_annualized_return": _annualized(benchmark_return, holding_days),
        "excess_return": asset_return - benchmark_return,
        "max_drawdown": _max_drawdown(wealth),
        "volatility": _annualized_volatility(asset_period_returns, asset),
        "holding_period_days": holding_days,
        "return_components": {
            "price_return": price_return,
            "dividend_return": dividend_return,
            "fx_return": fx_return,
            "cost_return": cost_return,
            "fee_assumption": {
                "observed_cash_cost": fees,
                "rate": cost_rate,
            },
            "slippage_assumption": {
                "observed_cash_cost": slippage,
            },
        },
    }


def _futures_result(
    snapshot: Mapping[str, Any],
    outcome: Mapping[str, Any],
    base: dict[str, Any],
) -> dict[str, Any]:
    _validate_benchmark_identity(snapshot, outcome)
    _validate_subject_identity(snapshot, outcome, require_contract=True)
    ledger_raw = outcome.get("settlement_ledger") or outcome.get("ledger")
    if not isinstance(ledger_raw, Sequence) or isinstance(
        ledger_raw, (str, bytes, bytearray)
    ):
        raise _EvidenceGap("futures settlement_ledger is required")
    ledger = _normalise_ledger(ledger_raw, snapshot, outcome)
    benchmark = _normalise_series(
        _benchmark_input(outcome),
        "benchmark_series",
        value_keys=("value", "price", "close"),
    )
    benchmark_values = [float(row["value"]) for row in benchmark]
    if len(ledger) < 1:
        raise _EvidenceGap("futures settlement_ledger has no rows")
    _check_period(
        ledger,
        snapshot["decision"].get("decision_at"),
        base["closed_at"],
        "settlement_ledger",
    )
    _check_same_days(
        [{"day": row["day"]} for row in ledger], benchmark, "futures ledger and benchmark"
    )
    capital = _futures_capital(snapshot["decision"], outcome)
    if capital <= 0:
        raise _EvidenceGap("futures simulation capital must be positive")

    daily: list[dict[str, Any]] = []
    total_price_pnl = 0.0
    total_roll_pnl = 0.0
    total_fees = 0.0
    total_slippage = 0.0
    available = capital
    equity = capital
    max_margin = 0.0
    margin_call = 0.0
    forced_state = "NONE"
    equity_path = [equity]
    pnl_path: list[float] = []
    previous_margin = 0.0
    for index, row in enumerate(ledger):
        prior = row.get("prior_settlement_price")
        if prior is None:
            if index == 0:
                prior = _optional_number(
                    outcome.get("entry_settlement_price"), "entry_settlement_price"
                )
                if prior is None:
                    prior = _optional_number(snapshot["decision"].get("price"), "decision price")
            else:
                prior = ledger[index - 1]["settlement_price"]
        if prior is None or prior <= 0:
            raise _EvidenceGap("futures first settlement needs an entry price")
        settlement = row["settlement_price"]
        lots = row["position_lots"]
        sign = row["direction_sign"]
        multiplier = row["contract_multiplier"]
        price_pnl = sign * (settlement - prior) * multiplier * lots
        fees = row["fees"]
        slippage = row["slippage"]
        roll_pnl = row["roll_pnl"]
        margin = settlement * multiplier * lots * row["margin_rate"]
        available += price_pnl + roll_pnl - fees - slippage - (margin - previous_margin)
        equity += price_pnl + roll_pnl - fees - slippage
        previous_margin = margin
        total_price_pnl += price_pnl
        total_roll_pnl += roll_pnl
        total_fees += fees
        total_slippage += slippage
        max_margin = max(max_margin, margin)
        row_margin_call = max(0.0, -available)
        margin_call = max(margin_call, row_margin_call, row["margin_call_amount"])
        row_forced = row["forced_liquidation_state"]
        if row_forced != "NONE":
            forced_state = row_forced
        if row_margin_call > 0 and forced_state == "NONE":
            forced_state = "MARGIN_CALL"
        pnl_path.append(price_pnl + roll_pnl - fees - slippage)
        equity_path.append(equity)
        daily.append(
            {
                "trading_date": row["date"],
                "prior_settlement_price": prior,
                "settlement_price": settlement,
                "position_lots": lots,
                "direction": row["direction"],
                "daily_mark_to_market_pnl": price_pnl,
                "roll_pnl": roll_pnl,
                "fees": fees,
                "slippage": slippage,
                "margin_rate": row["margin_rate"],
                "margin_occupied": margin,
                "available_simulated_cash": available,
                "margin_call_amount": max(row_margin_call, row["margin_call_amount"]),
                "price_limit_state": row["price_limit_state"],
                "forced_liquidation_state": row_forced,
            }
        )

    holding_days = (ledger[-1]["day"] - ledger[0]["day"]).days
    if holding_days <= 0:
        raise _EvidenceGap("futures ledger must span a positive holding period")
    benchmark_return = benchmark_values[-1] / benchmark_values[0] - 1.0
    total_pnl = total_price_pnl + total_roll_pnl - total_fees - total_slippage
    asset_return = total_pnl / capital
    base.update(
        {
            "asset_return": asset_return,
            "asset_annualized_return": _annualized(asset_return, holding_days),
            "benchmark_return": benchmark_return,
            "benchmark_annualized_return": _annualized(benchmark_return, holding_days),
            "excess_return": None,
            "max_drawdown": _max_drawdown(equity_path),
            "volatility": _annualized_volatility_from_values(
                [value / capital for value in pnl_path], ledger
            ),
            "holding_period_days": holding_days,
            "return_components": {
                "price_return": total_price_pnl / capital,
                "dividend_return": None,
                "fx_return": None,
                "cost_return": -(total_fees + total_slippage) / capital,
                "fee_assumption": {"total_fees": total_fees},
                "slippage_assumption": {"total_slippage": total_slippage},
            },
            "futures": {
                "total_simulated_pnl": total_pnl,
                "single_contract_price_contribution": total_price_pnl,
                "roll_contribution": total_roll_pnl,
                "fees": total_fees,
                "slippage": total_slippage,
                "initial_simulation_capital": capital,
                "max_margin_occupied": max_margin,
                "max_margin_ratio": max_margin / capital,
                "max_margin_call_amount": margin_call,
                "final_available_simulated_cash": available,
                "forced_liquidation_state": forced_state,
                "contract_code": str(
                    outcome.get("contract_code")
                    or snapshot["decision"].get("contract_code")
                    or ""
                ),
                "contract_multiplier": _required_number(
                    snapshot["decision"].get("contract_multiplier"),
                    "contract_multiplier",
                ),
                "daily_settlement_ledger": daily,
            },
        }
    )
    base["data_quality"].update(
        {
            "status": "OK",
            "asset_series_comparable": True,
            "benchmark_series_comparable": True,
            "reasons": [],
        }
    )
    base["comparison"] = {
        "status": "SEPARATE_CAPITAL_AND_MARGIN_BASIS",
        "excess_return_comparable": False,
        "reason": "Futures return uses locked simulation capital and margin ledger; it is not directly subtracted from a cash/full-capital benchmark.",
        "benchmark_id": _benchmark_identifier(snapshot["decision"]["benchmark"]),
    }
    contributions = _contributions(
        snapshot, outcome, None, benchmark, is_futures=True,
        default_roll=total_roll_pnl / capital,
    )
    base["contributions"] = contributions["values"]
    base["contributions"]["roll_contribution"] = total_roll_pnl / capital
    base["contribution_sources"] = contributions["sources"]
    base["confidence"] = contributions["confidence"]
    base["evaluation_label"] = _evaluation_label(snapshot, outcome, base)
    return base


def _normalise_ledger(
    raw: Sequence[Any], snapshot: Mapping[str, Any], outcome: Mapping[str, Any]
) -> list[dict[str, Any]]:
    decision = snapshot["decision"]
    direction = str(decision.get("direction") or "").upper()
    if direction not in {"BULLISH", "BEARISH", "NEUTRAL", "OBSERVE"}:
        raise AttributionError("unsupported futures direction in locked snapshot")
    sign = {"BULLISH": 1, "BEARISH": -1, "NEUTRAL": 0, "OBSERVE": 0}[direction]
    default_multiplier = _optional_number(
        decision.get("contract_multiplier"), "contract_multiplier"
    )
    if default_multiplier is None or default_multiplier <= 0:
        raise _EvidenceGap("futures contract multiplier is required")
    try:
        default_margin = _optional_number(
            outcome.get("margin_rate"), "margin_rate"
        )
    except AttributionError as error:
        raise _EvidenceGap("numeric futures margin_rate is required") from error
    if default_margin is None:
        try:
            default_margin = _optional_number(
                decision.get("margin_assumptions", {}).get("rate")
                if isinstance(decision.get("margin_assumptions"), Mapping)
                else None,
                "margin rate",
            )
        except AttributionError as error:
            raise _EvidenceGap("numeric futures margin_rate is required") from error
    if default_margin is None or default_margin < 0:
        raise _EvidenceGap("numeric futures margin_rate is required")
    rows: list[dict[str, Any]] = []
    previous_day: date | None = None
    for index, raw_row in enumerate(raw):
        if not isinstance(raw_row, Mapping):
            raise AttributionError(f"settlement_ledger row {index} must be an object")
        day = _calendar_day(
            raw_row.get("date", raw_row.get("trading_date", raw_row.get("timestamp"))),
            f"settlement_ledger[{index}].date",
        )
        if previous_day is not None and day <= previous_day:
            raise AttributionError("settlement_ledger dates must be strictly ascending")
        previous_day = day
        settlement = _required_number(
            raw_row.get("settlement_price", raw_row.get("price")),
            f"settlement_ledger[{index}].settlement_price",
        )
        if settlement <= 0:
            raise _EvidenceGap("futures settlement prices must be positive")
        lots = _optional_number(raw_row.get("position_lots"), "position_lots")
        if lots is None:
            lots = _optional_number(decision.get("quantity"), "quantity")
        if lots is None or lots < 0:
            raise _EvidenceGap("futures position_lots must be non-negative")
        multiplier = _optional_number(
            raw_row.get("contract_multiplier"), "contract_multiplier"
        ) or default_multiplier
        margin_rate = _optional_number(raw_row.get("margin_rate"), "margin_rate")
        if margin_rate is None:
            margin_rate = default_margin
        if margin_rate < 0:
            raise _EvidenceGap("futures margin_rate must be non-negative")
        fees = _optional_number(
            raw_row.get("fees", raw_row.get("fee")), "fees"
        ) or 0.0
        slippage = _optional_number(
            raw_row.get("slippage", raw_row.get("slippage_cost")), "slippage"
        ) or 0.0
        slippage_ticks = _optional_number(raw_row.get("slippage_ticks"), "slippage_ticks")
        if slippage_ticks is not None:
            tick_size = _optional_number(
                raw_row.get("tick_size", outcome.get("tick_size")), "tick_size"
            )
            if tick_size is None or tick_size < 0:
                raise _EvidenceGap("tick_size is required with slippage_ticks")
            slippage += slippage_ticks * tick_size * multiplier * lots
        roll_pnl = _optional_number(
            raw_row.get("roll_pnl", raw_row.get("roll_contribution")), "roll_pnl"
        ) or 0.0
        margin_call_amount = _optional_number(
            raw_row.get("margin_call_amount"), "margin_call_amount"
        ) or 0.0
        forced = str(
            raw_row.get("forced_liquidation_state")
            or ("NONE" if not raw_row.get("forced_liquidation") else "SIMULATED_FORCED_LIQUIDATION")
        ).upper()
        rows.append(
            {
                "day": day,
                "date": str(raw_row.get("date", raw_row.get("trading_date", day.isoformat()))),
                "settlement_price": settlement,
                "prior_settlement_price": _optional_number(
                    raw_row.get("prior_settlement_price"), "prior_settlement_price"
                ),
                "position_lots": lots,
                "direction": direction,
                "direction_sign": sign,
                "contract_multiplier": multiplier,
                "margin_rate": margin_rate,
                "fees": fees,
                "slippage": slippage,
                "roll_pnl": roll_pnl,
                "margin_call_amount": margin_call_amount,
                "price_limit_state": str(raw_row.get("price_limit_state") or "NONE"),
                "forced_liquidation_state": forced,
            }
        )
    return rows


def _contributions(
    snapshot: Mapping[str, Any],
    outcome: Mapping[str, Any],
    asset: Sequence[Mapping[str, Any]] | None,
    benchmark: Sequence[Mapping[str, Any]],
    *,
    is_futures: bool,
    default_roll: float | None = None,
) -> dict[str, Any]:
    raw = outcome.get("contributions") or outcome.get("attribution") or {}
    if not isinstance(raw, Mapping):
        raise AttributionError("contributions must be an object")
    values: dict[str, float | None] = {field: None for field in _CONTRIBUTION_FIELDS}
    sources: dict[str, str] = {}
    for field in _CONTRIBUTION_FIELDS:
        number = _optional_number(raw.get(field), field)
        if number is not None:
            values[field] = number
            sources[field] = "explicit_review_input"
    if default_roll is not None and values["roll_contribution"] is None:
        values["roll_contribution"] = default_roll
        sources["roll_contribution"] = "settlement_ledger"

    industry_raw = (
        outcome.get("industry_series")
        or outcome.get("industry_prices")
        or raw.get("industry_series")
    )
    if industry_raw is not None and asset is not None:
        industry = _normalise_series(
            industry_raw, "industry_series", value_keys=("value", "price", "close")
        )
        _check_same_dates(asset, industry, "asset and industry series")
        beta = _beta(
            _period_returns(_wealth_path(asset, total_cost=0.0, fx=None)),
            _period_returns(_wealth_path(industry, total_cost=0.0, fx=None)),
        )
        industry_return = float(industry[-1]["value"]) / float(industry[0]["value"]) - 1.0
        if beta is not None:
            values["beta_contribution"] = beta * industry_return
            sources["beta_contribution"] = "industry_series_beta_estimate"

    confidence = "ROUGH_ATTRIBUTION"
    requested_confidence = str(outcome.get("attribution_confidence") or raw.get("confidence") or "").upper()
    evidence = outcome.get("attribution_evidence") or raw.get("evidence")
    if (
        requested_confidence == "HIGH_CONFIDENCE_ATTRIBUTION"
        and isinstance(evidence, Sequence)
        and not isinstance(evidence, (str, bytes, bytearray))
        and evidence
        and all(values[field] is not None for field in _CONTRIBUTION_FIELDS if field != "roll_contribution" or not is_futures)
    ):
        confidence = "HIGH_CONFIDENCE_ATTRIBUTION"
    return {"values": values, "sources": sources, "confidence": confidence}


def _evaluation_label(
    snapshot: Mapping[str, Any], outcome: Mapping[str, Any], report: Mapping[str, Any]
) -> str:
    explicit = str(
        outcome.get("evaluation_label")
        or outcome.get("thesis_assessment")
        or ""
    ).upper()
    if explicit:
        if explicit not in _EVALUATION_LABELS - {"NOT_EVALUABLE"}:
            raise AttributionError(f"unsupported evaluation_label: {explicit}")
        return explicit
    if report.get("evaluation_state") != "EVALUABLE":
        return "NOT_EVALUABLE"
    if outcome.get("invalidator_triggered") is True:
        return "THESIS_WRONG"
    direction = str(snapshot["decision"].get("direction") or "").upper()
    asset_return = report.get("asset_return")
    excess = report.get("excess_return")
    if not isinstance(asset_return, (int, float)):
        return "NOT_EVALUABLE"
    if direction in {"BULLISH", "BEARISH"}:
        aligned = asset_return >= 0 if direction == "BULLISH" else asset_return <= 0
        if not aligned:
            return "THESIS_WRONG"
        if outcome.get("timing_early") is True:
            return "THESIS_RIGHT_TIMING_EARLY"
        if outcome.get("price_unrealized") is True:
            return "THESIS_RIGHT_PRICE_UNREALIZED"
        beta = report.get("contributions", {}).get("beta_contribution")
        if isinstance(excess, (int, float)) and isinstance(beta, (int, float)):
            if abs(beta) >= abs(excess) and abs(beta) > 0:
                return "OUTCOME_BETA_OR_EVENT"
        return "PARTIALLY_CORRECT"
    return "PARTIALLY_CORRECT"


def _not_evaluable(report: dict[str, Any], reason: str) -> dict[str, Any]:
    report["evaluation_state"] = "NOT_EVALUABLE"
    report["evaluation_reason"] = reason
    report["evaluation_label"] = "NOT_EVALUABLE"
    report["confidence"] = "NOT_EVALUABLE"
    report["data_quality"] = {
        "status": "INSUFFICIENT_DATA",
        "reasons": [reason],
        "asset_series_comparable": False,
        "benchmark_series_comparable": False,
    }
    report["comparison"] = {
        "status": "NOT_EVALUABLE",
        "excess_return_comparable": False,
        "reason": reason,
    }
    return report


def _series_input(outcome: Mapping[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        if outcome.get(name) is not None:
            return outcome[name]
    return None


def _benchmark_input(outcome: Mapping[str, Any]) -> Any:
    value = _series_input(outcome, ("benchmark_series", "benchmark_prices"))
    if value is not None:
        return value
    benchmark = outcome.get("benchmark")
    if isinstance(benchmark, Mapping):
        return benchmark.get("series") or benchmark.get("prices") or benchmark.get("points")
    return None


def _normalise_series(
    raw: Any, field: str, *, value_keys: Sequence[str]
) -> list[dict[str, Any]]:
    if isinstance(raw, Mapping):
        raw = raw.get("series") or raw.get("prices") or raw.get("points")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise _EvidenceGap(f"{field} is required as a dated list")
    if len(raw) < 2:
        raise _EvidenceGap(f"{field} needs at least two dated observations")
    result: list[dict[str, Any]] = []
    previous: date | None = None
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise AttributionError(f"{field}[{index}] must be an object")
        day = _calendar_day(
            item.get("date", item.get("timestamp", item.get("as_of"))),
            f"{field}[{index}].date",
        )
        if previous is not None and day <= previous:
            raise AttributionError(f"{field} dates must be strictly ascending")
        previous = day
        value = None
        for key in value_keys:
            if item.get(key) is not None:
                value = item[key]
                break
        number = _required_number(value, f"{field}[{index}].value")
        result.append(
            {
                "day": day,
                "date": str(item.get("date", item.get("timestamp", item.get("as_of", day.isoformat())))),
                "value": number,
                "dividend": _optional_number(
                    item.get("dividend", item.get("cash_distribution")), "dividend"
                )
                or 0.0,
                "fee": _optional_number(item.get("fee"), "fee") or 0.0,
                "slippage": _optional_number(item.get("slippage"), "slippage") or 0.0,
            }
        )
    return result


def _check_comparable_series(
    asset: Sequence[Mapping[str, Any]], benchmark: Sequence[Mapping[str, Any]]
) -> None:
    _check_same_dates(asset, benchmark, "asset and benchmark series")


def _check_same_dates(
    left: Sequence[Mapping[str, Any]],
    right: Sequence[Mapping[str, Any]],
    description: str,
) -> None:
    if [row["day"] for row in left] != [row["day"] for row in right]:
        raise _EvidenceGap(f"{description} are not date-comparable")


def _check_same_days(
    left: Sequence[Mapping[str, Any]],
    right: Sequence[Mapping[str, Any]],
    description: str,
) -> None:
    if [row["day"] for row in left] != [row["day"] for row in right]:
        raise _EvidenceGap(f"{description} are not date-comparable")


def _check_period(
    series: Sequence[Mapping[str, Any]],
    start_value: Any,
    end_value: Any,
    field: str,
) -> None:
    start = _calendar_day(start_value, f"{field} decision_at")
    end = _calendar_day(end_value, f"{field} closed_at")
    if series[0]["day"] != start:
        raise _EvidenceGap(
            f"{field} does not start on the locked decision date ({start.isoformat()})"
        )
    if series[-1]["day"] > end:
        raise _EvidenceGap(f"{field} contains observations after closed_at")
    if series[-1]["day"] < end:
        raise _EvidenceGap(
            f"{field} does not end on closed_at ({end.isoformat()})"
        )


def _wealth_path(
    series: Sequence[Mapping[str, Any]],
    *,
    total_cost: float,
    fx: Sequence[Mapping[str, Any]] | None,
) -> list[float]:
    initial = float(series[0]["value"])
    if initial <= 0:
        raise _EvidenceGap("series entry value must be positive")
    cumulative_dividend = 0.0
    cumulative_cost = 0.0
    fx_start = float(fx[0]["value"]) if fx is not None else 1.0
    if fx_start <= 0:
        raise _EvidenceGap("FX entry value must be positive")
    result: list[float] = []
    for index, row in enumerate(series):
        cumulative_dividend += float(row.get("dividend") or 0.0)
        cumulative_cost += float(row.get("fee") or 0.0) + float(row.get("slippage") or 0.0)
        if index == len(series) - 1:
            cumulative_cost += total_cost - sum(
                float(item.get("fee") or 0.0) + float(item.get("slippage") or 0.0)
                for item in series
            )
        local = float(row["value"]) + cumulative_dividend - cumulative_cost
        fx_ratio = (float(fx[index]["value"]) / fx_start) if fx is not None else 1.0
        result.append(local * fx_ratio / initial)
    return result


def _period_returns(values: Sequence[float]) -> list[float]:
    return [values[index] / values[index - 1] - 1.0 for index in range(1, len(values))]


def _annualized(value: float, days: int) -> float:
    if days <= 0 or 1.0 + value <= 0:
        return -1.0 if 1.0 + value <= 0 else 0.0
    return (1.0 + value) ** (365.0 / days) - 1.0


def _annualized_volatility(
    returns: Sequence[float], series: Sequence[Mapping[str, Any]]
) -> float | None:
    if not returns:
        return None
    days = [
        (series[index]["day"] - series[index - 1]["day"]).days
        for index in range(1, len(series))
    ]
    average_days = mean(days) if days else 1.0
    return pstdev(returns) * sqrt(365.0 / max(average_days, 1.0))


def _annualized_volatility_from_values(
    returns: Sequence[float], series: Sequence[Mapping[str, Any]]
) -> float | None:
    return _annualized_volatility(returns, series)


def _max_drawdown(values: Sequence[float]) -> float:
    peak = values[0]
    maximum = 0.0
    for value in values:
        peak = max(peak, value)
        if peak:
            maximum = max(maximum, 1.0 - value / peak)
    return -maximum


def _beta(asset_returns: Sequence[float], factor_returns: Sequence[float]) -> float | None:
    if len(asset_returns) != len(factor_returns) or len(asset_returns) < 2:
        return None
    factor_mean = mean(factor_returns)
    asset_mean = mean(asset_returns)
    variance = sum((value - factor_mean) ** 2 for value in factor_returns)
    if variance == 0:
        return None
    covariance = sum(
        (asset_returns[index] - asset_mean) * (factor_returns[index] - factor_mean)
        for index in range(len(asset_returns))
    )
    return covariance / variance


def _benchmark_identifier(benchmark: Mapping[str, Any]) -> str:
    return str(
        benchmark.get("series_id")
        or benchmark.get("benchmark_id")
        or benchmark.get("name")
        or benchmark.get("id")
        or ""
    ).strip()


def _validate_benchmark_identity(
    snapshot: Mapping[str, Any], outcome: Mapping[str, Any]
) -> None:
    locked = snapshot["decision"]["benchmark"]
    supplied = outcome.get("benchmark_id")
    supplied_mapping = outcome.get("benchmark")
    if supplied is None and isinstance(supplied_mapping, Mapping):
        supplied = _benchmark_identifier(supplied_mapping)
    supplied_text = str(supplied or "").strip()
    locked_text = _benchmark_identifier(locked)
    if supplied_text and locked_text and supplied_text != locked_text:
        raise AttributionError(
            "outcome benchmark does not match the benchmark locked in the decision snapshot"
        )


def _validate_subject_identity(
    snapshot: Mapping[str, Any],
    outcome: Mapping[str, Any],
    *,
    require_contract: bool = False,
) -> None:
    locked_subject = str(
        snapshot.get("subject_id")
        or snapshot["decision"].get("subject_id")
        or snapshot.get("company_id")
        or ""
    ).strip()
    supplied_subject = str(outcome.get("subject_id") or "").strip()
    if supplied_subject and locked_subject and supplied_subject != locked_subject:
        raise AttributionError(
            "outcome subject does not match the locked decision snapshot"
        )
    if not require_contract:
        return
    locked_contract = str(snapshot["decision"].get("contract_code") or "").strip()
    supplied_contract = str(outcome.get("contract_code") or "").strip()
    if not supplied_contract:
        raise _EvidenceGap("futures outcome contract_code is required")
    if supplied_contract != locked_contract:
        raise AttributionError(
            "outcome contract_code does not match the locked futures contract"
        )


def _futures_capital(decision: Mapping[str, Any], outcome: Mapping[str, Any]) -> float:
    explicit = _optional_number(outcome.get("initial_simulation_capital"), "initial_simulation_capital")
    if explicit is not None:
        return explicit
    assumptions = decision.get("capital_assumptions")
    if isinstance(assumptions, Mapping):
        for key in ("simulation_capital", "initial_capital", "capital"):
            value = _optional_number(assumptions.get(key), key)
            if value is not None:
                return value
    return 0.0


def _snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    import json

    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def _calendar_day(value: Any, field: str) -> date:
    text = str(value or "").strip()
    if not text:
        raise AttributionError(f"{field} is required")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text)
        except ValueError as error:
            raise AttributionError(f"{field} must be ISO date or datetime") from error


def _required_number(value: Any, field: str) -> float:
    number = _optional_number(value, field)
    if number is None:
        raise AttributionError(f"{field} must be numeric")
    return number


def _optional_number(value: Any, field: str) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise AttributionError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise AttributionError(f"{field} must be numeric") from error
    if not isfinite(number):
        raise AttributionError(f"{field} must be finite")
    return number


def _compact(value: str) -> str:
    return value.replace(":", "").replace("+", "plus").replace("/", "-")
