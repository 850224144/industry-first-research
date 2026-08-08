"""Build and replay a bounded, full-cash simulated company portfolio.

Every operation is backed by an immutable decision snapshot.  The portfolio
layer only combines those snapshots; it never changes their reasons, prices,
benchmarks, or research conclusions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from hashlib import sha256
import json
from math import isfinite, sqrt
from statistics import pstdev
from typing import Any

from .market_data import MarketDataError, build_market_data_snapshot, extract_market_data_series


PORTFOLIO_INPUT_SCHEMA_VERSION = "simulation-portfolio-input.v1"
PORTFOLIO_SCHEMA_VERSION = "simulation-portfolio.v1"
PORTFOLIO_OUTCOME_SCHEMA_VERSION = "simulation-portfolio-outcome.v1"
PORTFOLIO_REPLAY_SCHEMA_VERSION = "simulation-portfolio-replay.v1"
RULE_VERSION = "simulation-portfolio-rules.v1"

_DECISION_SCHEMA_VERSION = "decision-snapshot.v1"
_ACTIONS = {"OBSERVE", "ESTABLISH_SIMULATION", "HOLD", "ADJUST", "EXIT"}
_DIRECTIONS = {"OBSERVE", "BULLISH", "AVOID"}


class SimulationPortfolioError(ValueError):
    """Raised when a portfolio or replay input violates its audit boundary."""


def build_simulation_portfolio(
    portfolio_input: Mapping[str, Any],
    decision_snapshots: Sequence[Mapping[str, Any]],
    *,
    portfolio_id: str = "",
) -> dict[str, Any]:
    """Create an immutable portfolio operation log from locked snapshots.

    ``ADJUST`` quantities are target quantities, not deltas. ``HOLD`` keeps the
    previous target quantity. This explicit convention makes a replay
    reproducible even when operations are added months apart.
    """

    _validate_portfolio_input(portfolio_input)
    if not isinstance(decision_snapshots, Sequence) or isinstance(
        decision_snapshots, (str, bytes, bytearray)
    ) or not decision_snapshots:
        raise SimulationPortfolioError("decision_snapshots must be a non-empty list")

    initial_capital = _positive_number(
        portfolio_input.get("initial_capital"), "initial_capital"
    )
    benchmark = dict(portfolio_input["benchmark"])
    operations: list[dict[str, Any]] = []
    current_quantities: dict[str, float] = {}
    position_subjects: set[str] = set()
    seen_snapshot_ids: set[str] = set()
    previous_day: date | None = None

    for snapshot in decision_snapshots:
        _validate_decision_snapshot(snapshot)
        snapshot_id = str(snapshot["snapshot_id"])
        if snapshot_id in seen_snapshot_ids:
            raise SimulationPortfolioError(
                f"duplicate decision snapshot: {snapshot_id}"
            )
        seen_snapshot_ids.add(snapshot_id)
        decision = snapshot["decision"]
        decision_benchmark = decision["benchmark"]
        _validate_benchmark_match(benchmark, decision_benchmark)
        subject_id = str(snapshot.get("subject_id") or decision.get("subject_id") or "").strip()
        if not subject_id:
            raise SimulationPortfolioError(
                f"decision snapshot has no subject_id: {snapshot_id}"
            )
        operation_day = _calendar_day(decision.get("decision_at"), "decision_at")
        if previous_day is not None and operation_day < previous_day:
            raise SimulationPortfolioError(
                "decision snapshots must be supplied in chronological order"
            )
        previous_day = operation_day
        action = str(decision.get("action_type") or "").strip().upper()
        direction = str(decision.get("direction") or "").strip().upper()
        if action not in _ACTIONS:
            raise SimulationPortfolioError(f"unsupported action_type: {action}")
        if direction not in _DIRECTIONS:
            raise SimulationPortfolioError(f"unsupported direction: {direction}")

        price = _positive_number(decision.get("price"), f"price for {snapshot_id}")
        quantity = _non_negative_number(
            decision.get("quantity"), f"quantity for {snapshot_id}"
        )
        position_ratio = _non_negative_number(
            decision.get("position_ratio"), f"position_ratio for {snapshot_id}"
        )
        if position_ratio > 1:
            raise SimulationPortfolioError(
                f"position_ratio must be at most 1: {snapshot_id}"
            )

        current = current_quantities.get(subject_id, 0.0)
        if action == "OBSERVE":
            target = current
            if direction != "OBSERVE":
                raise SimulationPortfolioError(
                    f"OBSERVE operation must use OBSERVE direction: {snapshot_id}"
                )
        elif action == "ESTABLISH_SIMULATION":
            if current > 0:
                raise SimulationPortfolioError(
                    f"cannot establish an active subject twice: {subject_id}"
                )
            if direction != "BULLISH" or quantity <= 0:
                raise SimulationPortfolioError(
                    f"establish operation requires bullish positive quantity: {snapshot_id}"
                )
            target = quantity
        elif action == "HOLD":
            if current <= 0:
                raise SimulationPortfolioError(
                    f"HOLD operation requires an active subject: {snapshot_id}"
                )
            if direction != "BULLISH":
                raise SimulationPortfolioError(
                    f"HOLD operation requires BULLISH direction: {snapshot_id}"
                )
            target = current
        elif action == "ADJUST":
            if current <= 0:
                raise SimulationPortfolioError(
                    f"ADJUST operation requires an active subject: {snapshot_id}"
                )
            if direction != "BULLISH" or quantity <= 0:
                raise SimulationPortfolioError(
                    f"adjust operation requires bullish positive target quantity: {snapshot_id}"
                )
            target = quantity
        else:  # EXIT
            if current <= 0:
                raise SimulationPortfolioError(
                    f"EXIT operation requires an active subject: {snapshot_id}"
                )
            if direction not in {"BULLISH", "AVOID"}:
                raise SimulationPortfolioError(
                    f"EXIT operation requires BULLISH or AVOID direction: {snapshot_id}"
                )
            target = 0.0

        current_quantities[subject_id] = target
        if current > 0 or target > 0:
            position_subjects.add(subject_id)
        operations.append(
            {
                "operation_id": f"portfolio-operation-{snapshot_id.removeprefix('decision-snapshot-')}",
                "decision_snapshot_id": snapshot_id,
                "subject_id": subject_id,
                "display_name": str(snapshot.get("display_name") or ""),
                "action_type": action,
                "direction": direction,
                "executed_at": str(decision["decision_at"]),
                "price": price,
                "quantity": quantity,
                "target_quantity": target,
                "position_ratio": position_ratio,
                "cost_assumptions": _cost_assumptions(decision),
                "source_snapshot_hash": _payload_hash(snapshot),
            }
        )

    if not position_subjects:
        raise SimulationPortfolioError(
            "portfolio requires at least one non-observe simulation operation"
        )
    portfolio_key = str(portfolio_input.get("portfolio_id") or portfolio_id).strip()
    if not portfolio_key:
        portfolio_key = "portfolio-" + "-".join(
            operation["decision_snapshot_id"].removeprefix("decision-snapshot-")
            for operation in operations
        )
    review_date = str(portfolio_input.get("review_date") or "").strip()
    if review_date:
        _calendar_day(review_date, "review_date")
    return {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "portfolio_id": f"simulation-portfolio-{portfolio_key.removeprefix('simulation-portfolio-')}",
        "portfolio_name": str(portfolio_input.get("portfolio_name") or "").strip(),
        "version": int(portfolio_input.get("version") or 1),
        "status": "ACTIVE",
        "review_date": review_date,
        "initial_capital": initial_capital,
        "currency": str(portfolio_input.get("currency") or "CNY").strip(),
        "benchmark": benchmark,
        "operations": operations,
        "subject_ids": sorted(position_subjects),
        "decision_snapshot_ids": [operation["decision_snapshot_id"] for operation in operations],
        "rule_version": RULE_VERSION,
        "immutable": True,
        "simulation_only": True,
        "execution_enabled": False,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "policy": {
            "original_not_overwritable": True,
            "revision_requires_new_portfolio": True,
            "decision_snapshots_unchanged": True,
            "full_cash_company_mode": True,
            "futures_margin_mode_not_mixed": True,
            "read_only": True,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
        },
    }


def replay_simulation_portfolio(
    portfolio: Mapping[str, Any],
    outcome_input: Mapping[str, Any],
    *,
    closed_at: str = "",
    replay_id: str = "",
    asset_market_data_snapshots: Mapping[str, Mapping[str, Any]] | None = None,
    benchmark_market_data_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Replay company operations against a bounded dated price package."""

    _validate_portfolio(portfolio)
    if asset_market_data_snapshots is not None or benchmark_market_data_snapshot is not None:
        try:
            outcome_input = dict(outcome_input)
            if benchmark_market_data_snapshot is not None:
                benchmark = build_market_data_snapshot(benchmark_market_data_snapshot)
                outcome_input["benchmark_series"] = [
                    {"date": row["timestamp"], "value": row.get("value", row.get("close", row.get("settlement")))}
                    for row in extract_market_data_series(benchmark)
                ]
                outcome_input["benchmark_market_data_snapshot_id"] = benchmark["snapshot_id"]
            if asset_market_data_snapshots is not None:
                converted: dict[str, list[dict[str, Any]]] = {}
                for subject_id, raw_snapshot in asset_market_data_snapshots.items():
                    asset = build_market_data_snapshot(raw_snapshot)
                    converted[str(subject_id)] = [
                        {"date": row["timestamp"], "price": row.get("close", row.get("value", row.get("settlement")))}
                        for row in extract_market_data_series(asset)
                    ]
                outcome_input["asset_series"] = converted
                outcome_input["asset_market_data_snapshot_ids"] = {
                    str(subject_id): str(
                        build_market_data_snapshot(raw_snapshot)["snapshot_id"]
                    )
                    for subject_id, raw_snapshot in asset_market_data_snapshots.items()
                }
        except MarketDataError as error:
            raise SimulationPortfolioError(str(error)) from error
    _validate_outcome(outcome_input)
    close_value = str(closed_at or outcome_input.get("closed_at") or "").strip()
    if not close_value:
        raise SimulationPortfolioError("closed_at is required")
    closed_day = _calendar_day(close_value, "closed_at")
    review_date = str(portfolio.get("review_date") or "").strip()
    if review_date and closed_day < _calendar_day(review_date, "review_date"):
        return _not_evaluable(
            portfolio,
            close_value,
            "closed_at is before the portfolio review_date; the replay is not due",
            replay_id=replay_id,
        )

    benchmark_series = _normalise_series(
        outcome_input["benchmark_series"], "benchmark_series", "value"
    )
    asset_series = outcome_input["asset_series"]
    asset_by_subject: dict[str, dict[date, Mapping[str, Any]]] = {}
    for subject_id in portfolio["subject_ids"]:
        rows = asset_series.get(subject_id)
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
            return _not_evaluable(
                portfolio,
                close_value,
                f"missing asset series for subject: {subject_id}",
                replay_id=replay_id,
            )
        asset_by_subject[subject_id] = _normalise_series(
            rows, f"asset_series[{subject_id}]", "price"
        )

    all_rows = [*benchmark_series.values()]
    for series in asset_by_subject.values():
        all_rows.extend(series.values())
    if any(_calendar_day(row["date"], "series date") > closed_day for row in all_rows):
        return _not_evaluable(
            portfolio,
            close_value,
            "outcome input contains observations after closed_at",
            replay_id=replay_id,
        )

    operations = portfolio["operations"]
    operation_days = [
        _calendar_day(operation["executed_at"], "executed_at")
        for operation in operations
    ]
    if any(operation_day > closed_day for operation_day in operation_days):
        return _not_evaluable(
            portfolio,
            close_value,
            "closed_at is before a locked portfolio operation",
            replay_id=replay_id,
        )
    if any(operation_day not in benchmark_series for operation_day in operation_days):
        return _not_evaluable(
            portfolio,
            close_value,
            "benchmark series is missing a locked portfolio operation date",
            replay_id=replay_id,
        )
    start_day = min(operation_days)
    timeline = sorted(
        day for day in benchmark_series if start_day <= day <= closed_day
    )
    if not timeline:
        return _not_evaluable(
            portfolio,
            close_value,
            "benchmark series has no observations in the portfolio period",
            replay_id=replay_id,
        )

    missing = _missing_timeline_data(
        timeline, benchmark_series, asset_by_subject, portfolio["subject_ids"]
    )
    if missing:
        return _not_evaluable(
            portfolio,
            close_value,
            "dated series is incomplete: " + ", ".join(missing[:5]),
            replay_id=replay_id,
        )

    operation_by_day: dict[date, list[Mapping[str, Any]]] = {}
    for operation in operations:
        operation_by_day.setdefault(
            _calendar_day(operation["executed_at"], "executed_at"), []
        ).append(operation)

    quantities = {subject_id: 0.0 for subject_id in portfolio["subject_ids"]}
    cash = float(portfolio["initial_capital"])
    total_fees = 0.0
    total_dividends = 0.0
    shortfall_dates: list[str] = []
    rows: list[dict[str, Any]] = []
    initial_benchmark = float(benchmark_series[timeline[0]]["value"])
    if initial_benchmark <= 0:
        raise SimulationPortfolioError("initial benchmark value must be positive")

    for day in timeline:
        day_operations = operation_by_day.get(day, [])
        operation_results = []
        for operation in day_operations:
            subject_id = operation["subject_id"]
            previous_quantity = quantities[subject_id]
            target_quantity = float(operation["target_quantity"])
            delta = target_quantity - previous_quantity
            fee = _transaction_fee(operation, delta)
            cash -= delta * float(operation["price"]) + fee
            total_fees += fee
            quantities[subject_id] = target_quantity
            operation_results.append(
                {
                    "operation_id": operation["operation_id"],
                    "subject_id": subject_id,
                    "previous_quantity": previous_quantity,
                    "target_quantity": target_quantity,
                    "delta_quantity": delta,
                    "locked_execution_price": operation["price"],
                    "transaction_fee": fee,
                }
            )

        dividend_total = 0.0
        market_value = 0.0
        holdings = {}
        for subject_id, quantity in quantities.items():
            asset_row = asset_by_subject[subject_id][day]
            price = float(asset_row["price"])
            dividend = _non_negative_number(
                asset_row.get("dividend", 0), f"dividend for {subject_id} on {day}"
            )
            dividend_cash = quantity * dividend
            dividend_total += dividend_cash
            market_value += quantity * price
            holdings[subject_id] = {
                "quantity": quantity,
                "price": price,
                "market_value": quantity * price,
                "dividend_per_share": dividend,
            }
        cash += dividend_total
        total_dividends += dividend_total
        if cash < 0:
            shortfall_dates.append(day.isoformat())
        equity = cash + market_value
        benchmark_value = float(benchmark_series[day]["value"])
        benchmark_equity = float(portfolio["initial_capital"]) * benchmark_value / initial_benchmark
        rows.append(
            {
                "date": day.isoformat(),
                "cash": cash,
                "market_value": market_value,
                "equity": equity,
                "benchmark_value": benchmark_value,
                "benchmark_equity": benchmark_equity,
                "holdings": holdings,
                "operations": operation_results,
                "dividend_cash": dividend_total,
            }
        )

    equity_curve = [float(row["equity"]) for row in rows]
    returns = [
        equity_curve[index] / equity_curve[index - 1] - 1
        for index in range(1, len(equity_curve))
        if equity_curve[index - 1] != 0
    ]
    max_drawdown = _max_drawdown(equity_curve)
    benchmark_final = float(rows[-1]["benchmark_equity"])
    initial_capital = float(portfolio["initial_capital"])
    state = "REVIEW_REQUIRED" if shortfall_dates else "EVALUABLE"
    reason = (
        "cash became negative under the locked full-cash assumptions"
        if shortfall_dates
        else "dated company price and benchmark series were replayed"
    )
    result_key = replay_id.strip() or f"{portfolio['portfolio_id']}-{close_value}"
    return {
        "schema_version": PORTFOLIO_REPLAY_SCHEMA_VERSION,
        "replay_id": f"portfolio-replay-{result_key.removeprefix('portfolio-replay-')}",
        "portfolio_id": portfolio["portfolio_id"],
        "portfolio_hash": _payload_hash(portfolio),
        "outcome_hash": _payload_hash(outcome_input),
        "closed_at": close_value,
        "review_date": review_date,
        "evaluation_state": state,
        "evaluation_reason": reason,
        "benchmark_locked": dict(portfolio["benchmark"]),
        "market_data_snapshot_ids": {
            "benchmark": str(outcome_input.get("benchmark_market_data_snapshot_id") or ""),
            "assets": dict(outcome_input.get("asset_market_data_snapshot_ids") or {}),
        },
        "initial_capital": initial_capital,
        "final_equity": equity_curve[-1],
        "portfolio_return": equity_curve[-1] / initial_capital - 1,
        "benchmark_return": benchmark_final / initial_capital - 1,
        "excess_return": (equity_curve[-1] - benchmark_final) / initial_capital,
        "max_drawdown": max_drawdown,
        "annualized_volatility": _annualized_volatility(returns),
        "total_fees": total_fees,
        "total_dividends": total_dividends,
        "cash_shortfall_dates": shortfall_dates,
        "operation_count": len(operations),
        "daily_ledger": rows,
        "policy": {
            "locked_operations_unchanged": True,
            "benchmark_taken_from_portfolio": True,
            "full_cash_company_mode": True,
            "not_investment_conclusion": True,
            "read_only": True,
            "simulation_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "simulation_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _validate_portfolio_input(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise SimulationPortfolioError("portfolio input must be an object")
    if value.get("schema_version") != PORTFOLIO_INPUT_SCHEMA_VERSION:
        raise SimulationPortfolioError(
            f"input must be {PORTFOLIO_INPUT_SCHEMA_VERSION}"
        )
    benchmark = value.get("benchmark")
    if not isinstance(benchmark, Mapping) or benchmark.get("locked") is not True:
        raise SimulationPortfolioError("portfolio benchmark must be locked")


def _validate_decision_snapshot(value: Any) -> None:
    if not isinstance(value, Mapping) or value.get("schema_version") != _DECISION_SCHEMA_VERSION:
        raise SimulationPortfolioError(
            f"input decision must be {_DECISION_SCHEMA_VERSION}"
        )
    if str(value.get("status") or "").upper() != "LOCKED":
        raise SimulationPortfolioError("portfolio requires LOCKED decision snapshots")
    if value.get("immutable") is not True or value.get("simulation_only") is not True:
        raise SimulationPortfolioError(
            "decision snapshot must be immutable and simulation-only"
        )
    if value.get("execution_enabled") is not False:
        raise SimulationPortfolioError("portfolio refuses execution-enabled snapshots")
    if str(value.get("subject_type") or "").lower() != "listed_company":
        raise SimulationPortfolioError(
            "company portfolio accepts listed_company snapshots only; futures use the settlement ledger"
        )
    if not isinstance(value.get("decision"), Mapping):
        raise SimulationPortfolioError("decision snapshot has no decision object")
    if not str(value.get("snapshot_id") or "").strip():
        raise SimulationPortfolioError("decision snapshot_id is required")
    if not str(value.get("subject_id") or value["decision"].get("subject_id") or "").strip():
        raise SimulationPortfolioError("decision snapshot subject_id is required")
    if not isinstance(value["decision"].get("benchmark"), Mapping):
        raise SimulationPortfolioError("decision snapshot has no benchmark")


def _validate_portfolio(value: Any) -> None:
    if not isinstance(value, Mapping) or value.get("schema_version") != PORTFOLIO_SCHEMA_VERSION:
        raise SimulationPortfolioError(f"input must be {PORTFOLIO_SCHEMA_VERSION}")
    if value.get("immutable") is not True or value.get("simulation_only") is not True:
        raise SimulationPortfolioError("portfolio must be immutable and simulation-only")
    if value.get("execution_enabled") is not False:
        raise SimulationPortfolioError("portfolio refuses execution-enabled input")
    if not isinstance(value.get("operations"), list) or not value["operations"]:
        raise SimulationPortfolioError("portfolio has no operations")
    if not isinstance(value.get("subject_ids"), list) or not value["subject_ids"]:
        raise SimulationPortfolioError("portfolio has no subject_ids")
    _positive_number(value.get("initial_capital"), "initial_capital")
    benchmark = value.get("benchmark")
    if not isinstance(benchmark, Mapping) or benchmark.get("locked") is not True:
        raise SimulationPortfolioError("portfolio benchmark must be locked")


def _validate_outcome(value: Any) -> None:
    if not isinstance(value, Mapping) or value.get("schema_version") != PORTFOLIO_OUTCOME_SCHEMA_VERSION:
        raise SimulationPortfolioError(
            f"input must be {PORTFOLIO_OUTCOME_SCHEMA_VERSION}"
        )
    if not isinstance(value.get("asset_series"), Mapping):
        raise SimulationPortfolioError("outcome asset_series must be an object")
    if not isinstance(value.get("benchmark_series"), Sequence) or isinstance(
        value["benchmark_series"], (str, bytes, bytearray)
    ):
        raise SimulationPortfolioError("outcome benchmark_series must be a list")


def _validate_benchmark_match(
    portfolio_benchmark: Mapping[str, Any], decision_benchmark: Mapping[str, Any]
) -> None:
    portfolio_id = str(
        portfolio_benchmark.get("series_id") or portfolio_benchmark.get("benchmark_id") or ""
    ).strip()
    decision_id = str(
        decision_benchmark.get("series_id") or decision_benchmark.get("benchmark_id") or ""
    ).strip()
    if not portfolio_id or not decision_id or portfolio_id != decision_id:
        raise SimulationPortfolioError(
            "every decision benchmark must match the portfolio benchmark"
        )
    if decision_benchmark.get("locked") is not True:
        raise SimulationPortfolioError("decision benchmark must be locked")


def _normalise_series(
    rows: Sequence[Mapping[str, Any]], name: str, value_field: str
) -> dict[date, Mapping[str, Any]]:
    result: dict[date, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise SimulationPortfolioError(f"{name} rows must be objects")
        day = _calendar_day(row.get("date"), f"{name}.date")
        if day in result:
            raise SimulationPortfolioError(f"duplicate date in {name}: {day}")
        value = _positive_number(row.get(value_field), f"{name}.{value_field}")
        result[day] = {**row, "date": day.isoformat(), value_field: value}
    if not result:
        raise SimulationPortfolioError(f"{name} must not be empty")
    return result


def _missing_timeline_data(
    timeline: Sequence[date],
    benchmark: Mapping[date, Mapping[str, Any]],
    assets: Mapping[str, Mapping[date, Mapping[str, Any]]],
    subject_ids: Sequence[str],
) -> list[str]:
    missing = []
    for day in timeline:
        if day not in benchmark:
            missing.append(f"benchmark:{day}")
        for subject_id in subject_ids:
            if day not in assets[subject_id]:
                missing.append(f"{subject_id}:{day}")
    return missing


def _cost_assumptions(decision: Mapping[str, Any]) -> dict[str, float]:
    value = decision.get("cost_assumptions") or decision.get("fee_assumptions") or {}
    if not isinstance(value, Mapping):
        raise SimulationPortfolioError("cost_assumptions must be an object when supplied")
    return {
        "rate": _non_negative_number(value.get("rate", 0), "cost_assumptions.rate"),
        "fixed": _non_negative_number(value.get("fixed", 0), "cost_assumptions.fixed"),
    }


def _transaction_fee(operation: Mapping[str, Any], delta: float) -> float:
    assumptions = operation["cost_assumptions"]
    return abs(delta) * float(operation["price"]) * float(assumptions["rate"]) + (
        float(assumptions["fixed"]) if delta else 0.0
    )


def _not_evaluable(
    portfolio: Mapping[str, Any],
    closed_at: str,
    reason: str,
    *,
    replay_id: str,
) -> dict[str, Any]:
    key = replay_id.strip() or f"{portfolio['portfolio_id']}-{closed_at}"
    return {
        "schema_version": PORTFOLIO_REPLAY_SCHEMA_VERSION,
        "replay_id": f"portfolio-replay-{key.removeprefix('portfolio-replay-')}",
        "portfolio_id": portfolio["portfolio_id"],
        "closed_at": closed_at,
        "evaluation_state": "NOT_EVALUABLE",
        "evaluation_reason": reason,
        "benchmark_locked": dict(portfolio["benchmark"]),
        "daily_ledger": [],
        "policy": {
            "locked_operations_unchanged": True,
            "benchmark_taken_from_portfolio": True,
            "not_investment_conclusion": True,
            "read_only": True,
            "simulation_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "simulation_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _calendar_day(value: Any, field: str) -> date:
    text = str(value or "").strip()
    if not text:
        raise SimulationPortfolioError(f"{field} must be non-empty")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text)
        except ValueError as error:
            raise SimulationPortfolioError(f"{field} must be ISO date/datetime") from error


def _positive_number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise SimulationPortfolioError(f"{field} must be numeric") from error
    if not isfinite(number) or number <= 0:
        raise SimulationPortfolioError(f"{field} must be positive")
    return number


def _non_negative_number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise SimulationPortfolioError(f"{field} must be numeric") from error
    if not isfinite(number) or number < 0:
        raise SimulationPortfolioError(f"{field} must be non-negative")
    return number


def _max_drawdown(values: Sequence[float]) -> float:
    peak = values[0]
    largest = 0.0
    for value in values:
        peak = max(peak, value)
        if peak:
            largest = max(largest, (peak - value) / peak)
    return largest


def _annualized_volatility(returns: Sequence[float]) -> float:
    if len(returns) < 2:
        return 0.0
    return pstdev(returns) * sqrt(252)


def _payload_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()
