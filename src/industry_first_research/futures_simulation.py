"""Replay a locked domestic-futures simulation with daily settlement accounting.

This module is deliberately separate from ``simulation_portfolio``.  A futures
ledger settles P&L every day and reserves margin; it must not be treated as a
full-cash equity portfolio.  The ledger is read-only and models no broker,
account, order, funding transfer, or automatic roll.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from hashlib import sha256
import json
from math import isfinite, sqrt
from statistics import pstdev
from typing import Any


FUTURES_SIMULATION_INPUT_SCHEMA_VERSION = "futures-simulation-input.v1"
FUTURES_SIMULATION_SCHEMA_VERSION = "futures-simulation.v1"
FUTURES_SIMULATION_OUTCOME_SCHEMA_VERSION = "futures-simulation-outcome.v1"
FUTURES_SIMULATION_REPLAY_SCHEMA_VERSION = "futures-simulation-replay.v1"
RULE_VERSION = "futures-simulation-rules.v1"

_DECISION_SCHEMA_VERSION = "decision-snapshot.v1"
_ACTIONS = {"OBSERVE", "ESTABLISH_SIMULATION", "HOLD", "ADJUST", "EXIT"}
_DIRECTIONS = {"BULLISH", "BEARISH", "NEUTRAL", "OBSERVE"}
_POSITION_DIRECTIONS = {"BULLISH": 1, "BEARISH": -1}
_LIMIT_STATUSES = {"NORMAL", "UP_LIMIT", "DOWN_LIMIT", "UNKNOWN"}
_SIMULATION_STATES = {
    "ACTIVE",
    "CLOSED",
    "REVIEW_REQUIRED",
    "MARGIN_CALL",
    "SIMULATED_FORCED_LIQUIDATION",
    "SIMULATED_FORCED_LIQUIDATION_BLOCKED",
}


class FuturesSimulationError(ValueError):
    """Raised when a futures simulation violates its locked-input boundary."""


def build_futures_simulation(
    simulation_input: Mapping[str, Any],
    decision_snapshots: Sequence[Mapping[str, Any]],
    *,
    simulation_id: str = "",
) -> dict[str, Any]:
    """Create an immutable operation log from locked futures decision snapshots.

    A contract change on an ``ADJUST`` snapshot is a roll only when the
    snapshot contains an explicit ``roll`` object with both legs' execution
    prices.  No contract is inferred from a continuous or main series.
    """

    _validate_simulation_input(simulation_input)
    if not isinstance(decision_snapshots, Sequence) or isinstance(
        decision_snapshots, (str, bytes, bytearray)
    ) or not decision_snapshots:
        raise FuturesSimulationError("decision_snapshots must be a non-empty list")

    benchmark = dict(simulation_input["benchmark"])
    margin_policy = _margin_policy(simulation_input.get("margin_policy"))
    initial_capital = _positive_number(
        simulation_input.get("initial_capital"), "initial_capital"
    )
    operations: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    seen_snapshot_ids: set[str] = set()
    seen_days: set[date] = set()
    last_day: date | None = None

    for snapshot in decision_snapshots:
        _validate_futures_snapshot(snapshot)
        snapshot_id = str(snapshot["snapshot_id"])
        if snapshot_id in seen_snapshot_ids:
            raise FuturesSimulationError(f"duplicate decision snapshot: {snapshot_id}")
        seen_snapshot_ids.add(snapshot_id)

        decision = snapshot["decision"]
        _validate_benchmark_match(benchmark, decision["benchmark"])
        day = _calendar_day(decision.get("decision_at"), "decision_at")
        if day in seen_days:
            raise FuturesSimulationError(
                "futures simulation allows at most one operation per calendar day"
            )
        if last_day is not None and day < last_day:
            raise FuturesSimulationError(
                "futures decision snapshots must be supplied chronologically"
            )
        seen_days.add(day)
        last_day = day

        action = str(decision["action_type"]).strip().upper()
        direction = str(decision["direction"]).strip().upper()
        contract_code = str(decision["contract_code"]).strip().upper()
        quantity = _lots(decision.get("quantity"), f"quantity for {snapshot_id}")
        price = _positive_number(decision.get("price"), f"price for {snapshot_id}")
        multiplier = _positive_number(
            decision.get("contract_multiplier"),
            f"contract_multiplier for {snapshot_id}",
        )
        position_ratio = _non_negative_number(
            decision.get("position_ratio"), f"position_ratio for {snapshot_id}"
        )
        if position_ratio > 1:
            raise FuturesSimulationError(
                f"position_ratio must be at most 1: {snapshot_id}"
            )

        if action == "OBSERVE":
            if direction != "OBSERVE":
                raise FuturesSimulationError(
                    f"OBSERVE operation must use OBSERVE direction: {snapshot_id}"
                )
            target = _position_copy(current)
            roll = None
        elif action == "ESTABLISH_SIMULATION":
            if current is not None:
                raise FuturesSimulationError(
                    f"cannot establish an active futures position twice: {contract_code}"
                )
            if direction not in _POSITION_DIRECTIONS or quantity <= 0:
                raise FuturesSimulationError(
                    f"establish operation requires bullish/bearish positive lots: {snapshot_id}"
                )
            target = {
                "contract_code": contract_code,
                "contract_month": str(decision["contract_month"]).strip(),
                "direction": direction,
                "direction_sign": _POSITION_DIRECTIONS[direction],
                "quantity": quantity,
                "contract_multiplier": multiplier,
            }
            roll = None
        elif action == "HOLD":
            if current is None:
                raise FuturesSimulationError(
                    f"HOLD operation requires an active futures position: {snapshot_id}"
                )
            if direction != current["direction"] or contract_code != current["contract_code"]:
                raise FuturesSimulationError(
                    "HOLD cannot change direction or contract; use ADJUST with explicit roll"
                )
            target = _position_copy(current)
            roll = None
        elif action == "ADJUST":
            if current is None:
                raise FuturesSimulationError(
                    f"ADJUST operation requires an active futures position: {snapshot_id}"
                )
            if direction != current["direction"] or quantity <= 0:
                raise FuturesSimulationError(
                    f"ADJUST must keep direction and use positive lots: {snapshot_id}"
                )
            target = {
                "contract_code": contract_code,
                "contract_month": str(decision["contract_month"]).strip(),
                "direction": direction,
                "direction_sign": current["direction_sign"],
                "quantity": quantity,
                "contract_multiplier": multiplier,
            }
            if contract_code == current["contract_code"]:
                roll = None
            else:
                roll = _validate_roll(
                    decision.get("roll"),
                    current,
                    target,
                    decision,
                    snapshot_id,
                )
        else:  # EXIT
            if current is None:
                raise FuturesSimulationError(
                    f"EXIT operation requires an active futures position: {snapshot_id}"
                )
            if direction not in {current["direction"], "NEUTRAL"}:
                raise FuturesSimulationError(
                    f"EXIT direction must match the position or be NEUTRAL: {snapshot_id}"
                )
            target = None
            roll = None

        operations.append(
            {
                "operation_id": f"futures-operation-{snapshot_id.removeprefix('decision-snapshot-')}",
                "decision_snapshot_id": snapshot_id,
                "executed_at": str(decision["decision_at"]),
                "subject_id": str(snapshot.get("subject_id") or decision.get("subject_id") or "").strip(),
                "display_name": str(snapshot.get("display_name") or ""),
                "action_type": action,
                "direction": direction,
                "contract_code": contract_code,
                "contract_month": str(decision["contract_month"]).strip(),
                "price": price,
                "quantity": quantity,
                "target_position": target,
                "contract_multiplier": multiplier,
                "margin_assumptions": dict(decision["margin_assumptions"]),
                "fee_assumptions": _cost_assumptions(decision["fee_assumptions"], "fee_assumptions"),
                "slippage_assumptions": _cost_assumptions(
                    decision["slippage_assumptions"], "slippage_assumptions"
                ),
                "price_limit_rule": decision["price_limit_rule"],
                "roll": roll,
                "source_snapshot_hash": _payload_hash(snapshot),
            }
        )
        current = target

    if not any(item["action_type"] == "ESTABLISH_SIMULATION" for item in operations):
        raise FuturesSimulationError(
            "futures simulation requires at least one establish operation"
        )
    review_date = str(simulation_input.get("review_date") or "").strip()
    if review_date:
        _calendar_day(review_date, "review_date")
    key = str(simulation_input.get("simulation_id") or simulation_id).strip()
    if not key:
        key = "-".join(item["decision_snapshot_id"].removeprefix("decision-snapshot-") for item in operations)
    contract_codes = sorted({item["contract_code"] for item in operations})
    return {
        "schema_version": FUTURES_SIMULATION_SCHEMA_VERSION,
        "simulation_id": f"futures-simulation-{key.removeprefix('futures-simulation-')}",
        "simulation_name": str(simulation_input.get("simulation_name") or "").strip(),
        "version": int(simulation_input.get("version") or 1),
        "status": "ACTIVE",
        "review_date": review_date,
        "initial_capital": initial_capital,
        "currency": str(simulation_input.get("currency") or "CNY").strip(),
        "benchmark": benchmark,
        "margin_policy": margin_policy,
        "operations": operations,
        "contract_codes": contract_codes,
        "decision_snapshot_ids": [item["decision_snapshot_id"] for item in operations],
        "rule_version": RULE_VERSION,
        "immutable": True,
        "simulation_only": True,
        "execution_enabled": False,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "policy": {
            "specific_contract_only": True,
            "continuous_series_not_tradeable": True,
            "daily_settlement_ledger": True,
            "margin_mode_separate_from_equity": True,
            "automatic_roll": False,
            "automatic_funding": False,
            "decision_snapshots_unchanged": True,
            "revision_requires_new_simulation": True,
            "read_only": True,
            "review_only": True,
            "simulation_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
        },
    }


def replay_futures_simulation(
    simulation: Mapping[str, Any],
    outcome_input: Mapping[str, Any],
    *,
    closed_at: str = "",
    replay_id: str = "",
) -> dict[str, Any]:
    """Replay a futures simulation against dated settlement and rule rows."""

    _validate_simulation(simulation)
    _validate_outcome(outcome_input)
    close_value = str(closed_at or outcome_input.get("closed_at") or "").strip()
    if not close_value:
        raise FuturesSimulationError("closed_at is required")
    closed_day = _calendar_day(close_value, "closed_at")
    review_date = str(simulation.get("review_date") or "").strip()
    if review_date and closed_day < _calendar_day(review_date, "review_date"):
        return _not_evaluable(
            simulation,
            close_value,
            "closed_at is before the futures simulation review_date; replay is not due",
            replay_id=replay_id,
        )

    benchmark = _normalise_value_series(
        outcome_input["benchmark_series"], "benchmark_series", "value"
    )
    contracts = _normalise_contract_series(outcome_input["contract_series"])
    all_rows: list[Mapping[str, Any]] = [*benchmark.values()]
    for rows in contracts.values():
        all_rows.extend(rows.values())
    if any(_calendar_day(row["date"], "series date") > closed_day for row in all_rows):
        return _not_evaluable(
            simulation,
            close_value,
            "outcome input contains observations after closed_at",
            replay_id=replay_id,
        )

    operations = simulation["operations"]
    operation_days = [_calendar_day(item["executed_at"], "executed_at") for item in operations]
    if any(day > closed_day for day in operation_days):
        return _not_evaluable(
            simulation,
            close_value,
            "closed_at is before a locked futures operation",
            replay_id=replay_id,
        )
    if any(day not in benchmark for day in operation_days):
        return _not_evaluable(
            simulation,
            close_value,
            "benchmark series is missing a locked futures operation date",
            replay_id=replay_id,
        )
    start_day = min(operation_days)
    timeline = sorted(day for day in benchmark if start_day <= day <= closed_day)
    if not timeline:
        return _not_evaluable(
            simulation,
            close_value,
            "benchmark series has no observations in the futures simulation period",
            replay_id=replay_id,
        )
    operation_by_day = {
        _calendar_day(item["executed_at"], "executed_at"): item for item in operations
    }
    for operation in operations:
        day = _calendar_day(operation["executed_at"], "executed_at")
        for contract_code in _operation_contract_codes(operation):
            if contract_code not in contracts or day not in contracts[contract_code]:
                return _not_evaluable(
                    simulation,
                    close_value,
                    f"contract settlement/rule row is missing for {contract_code} on {day}",
                    replay_id=replay_id,
                )

    initial_benchmark = float(benchmark[timeline[0]]["value"])
    if initial_benchmark <= 0:
        raise FuturesSimulationError("initial benchmark value must be positive")

    cash = float(simulation["initial_capital"])
    additional_funding = 0.0
    position: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = []
    total_fees = 0.0
    total_slippage = 0.0
    total_roll_pnl = 0.0
    total_price_pnl = 0.0
    margin_calls: list[dict[str, Any]] = []
    blocked_operations: list[str] = []
    forced_liquidations: list[dict[str, Any]] = []
    simulation_state = "ACTIVE"
    last_contract_code = ""

    for day in timeline:
        operation = operation_by_day.get(day)
        position_before = _position_view(position)
        prior_settlement_price = (
            float(position["previous_settlement"]) if position is not None else None
        )
        day_realized_pnl = 0.0
        day_mtm_pnl = 0.0
        day_roll_pnl = 0.0
        day_fees = 0.0
        day_slippage = 0.0
        operation_results: list[dict[str, Any]] = []

        if operation is not None:
            result = _apply_operation(
                operation,
                day,
                position,
                contracts,
                cash,
            )
            position = result["position"]
            cash = result["cash"]
            day_realized_pnl += result["realized_pnl"]
            day_roll_pnl += result["roll_pnl"]
            day_fees += result["fees"]
            day_slippage += result["slippage"]
            operation_results.append(result["operation_result"])
            if result["operation_result"]["status"] != "EXECUTED":
                blocked_operations.append(operation["operation_id"])
            if position is not None:
                last_contract_code = str(position["contract_code"])
            else:
                last_contract_code = str(operation["contract_code"])

        if position is not None:
            contract_row = contracts[position["contract_code"]].get(day)
            if contract_row is None:
                return _not_evaluable(
                    simulation,
                    close_value,
                    f"contract settlement row is missing for {position['contract_code']} on {day}",
                    replay_id=replay_id,
                )
            mark = _mark_position(position, float(contract_row["settlement"]))
            cash += mark["pnl"]
            day_mtm_pnl += mark["pnl"]
            position["previous_settlement"] = float(contract_row["settlement"])

        margin_occupied = 0.0
        active_row: Mapping[str, Any] | None = None
        if position is not None:
            active_row = contracts[position["contract_code"]][day]
            margin_occupied = _margin_occupied(position, active_row)
            last_contract_code = str(position["contract_code"])

        available_cash = cash - margin_occupied
        margin_call_amount = 0.0
        margin_call_status = "NONE"
        funding_added = 0.0
        if position is not None and available_cash < 0:
            margin_call_amount = -available_cash
            remaining_funding = max(
                0.0,
                float(simulation["margin_policy"]["max_additional_funding"]) - additional_funding,
            )
            if simulation["margin_policy"]["allow_additional_funding"] and remaining_funding > 0:
                funding_added = min(margin_call_amount, remaining_funding)
                additional_funding += funding_added
                cash += funding_added
                available_cash = cash - margin_occupied
                margin_call_status = "FUNDED" if available_cash >= 0 else "PARTIALLY_FUNDED"
            margin_calls.append(
                {
                    "date": day.isoformat(),
                    "required_amount": margin_call_amount,
                    "funding_added": funding_added,
                    "unfunded_amount": max(0.0, -available_cash),
                    "status": margin_call_status,
                }
            )
            if available_cash < 0:
                margin_call_status = "MARGIN_CALL"
                margin_calls[-1]["status"] = margin_call_status
                if active_row is not None and _can_exit(active_row):
                    forced_fee, forced_slippage = _trade_cost(
                        position["quantity"],
                        float(active_row["settlement"]),
                        position["contract_multiplier"],
                        _position_cost_assumptions(position, operation, "fee_assumptions"),
                        _position_cost_assumptions(position, operation, "slippage_assumptions"),
                    )
                    cash -= forced_fee + forced_slippage
                    day_fees += forced_fee
                    day_slippage += forced_slippage
                    forced = {
                        "date": day.isoformat(),
                        "contract_code": position["contract_code"],
                        "quantity": position["quantity"],
                        "settlement_price": active_row["settlement"],
                        "reason": "unfunded margin call",
                        "status": "SIMULATED_FORCED_LIQUIDATION",
                    }
                    forced_liquidations.append(forced)
                    operation_results.append({**forced, "operation_type": "FORCED_LIQUIDATION"})
                    position = None
                    margin_occupied = 0.0
                    available_cash = cash
                    simulation_state = "SIMULATED_FORCED_LIQUIDATION"
                else:
                    simulation_state = "SIMULATED_FORCED_LIQUIDATION_BLOCKED"
                    operation_results.append(
                        {
                            "date": day.isoformat(),
                            "operation_type": "FORCED_LIQUIDATION",
                            "status": "SIMULATED_FORCED_LIQUIDATION_BLOCKED",
                            "reason": "contract limit prevents simulated exit",
                        }
                    )
        if position is None and simulation_state == "ACTIVE" and operation and operation["action_type"] == "EXIT":
            simulation_state = "CLOSED"
        if position is not None and simulation_state == "CLOSED":
            simulation_state = "ACTIVE"

        total_fees += day_fees
        total_slippage += day_slippage
        total_roll_pnl += day_roll_pnl
        total_price_pnl += day_realized_pnl + day_mtm_pnl
        benchmark_value = float(benchmark[day]["value"])
        benchmark_equity = float(simulation["initial_capital"]) * benchmark_value / initial_benchmark
        equity = cash
        ledger_contract_code = last_contract_code
        ledger_row = contracts.get(ledger_contract_code, {}).get(day)
        ledger_position = position_before
        if operation is not None and operation["action_type"] not in {"EXIT"}:
            ledger_position = _position_view(position)
        if ledger_position is None:
            ledger_position = position_before
        forced_state = "NONE"
        if any(
            str(item.get("status") or "").startswith("SIMULATED_FORCED_LIQUIDATION")
            for item in operation_results
        ):
            forced_state = str(
                next(
                    item.get("status")
                    for item in operation_results
                    if str(item.get("status") or "").startswith("SIMULATED_FORCED_LIQUIDATION")
                )
            )
        elif margin_call_status == "MARGIN_CALL":
            forced_state = "MARGIN_CALL"
        rows.append(
            {
                "date": day.isoformat(),
                "contract_code": ledger_contract_code,
                "settlement_price": ledger_row["settlement"] if ledger_row else None,
                "prior_settlement_price": prior_settlement_price,
                "position_lots": int(ledger_position["quantity"]) if ledger_position else 0,
                "direction": str(ledger_position["direction"]) if ledger_position else "OBSERVE",
                "price_limit_state": str(ledger_row["price_limit_status"]) if ledger_row else "UNKNOWN",
                "cash_balance": cash,
                "equity": equity,
                "available_simulation_cash": available_cash,
                "margin_occupied": margin_occupied,
                "benchmark_value": benchmark_value,
                "benchmark_equity": benchmark_equity,
                "position": _position_view(position),
                "settlement_prices": {
                    code: contracts[code][day]["settlement"]
                    for code in _active_contract_codes(position, operation)
                    if day in contracts.get(code, {})
                },
                "realized_pnl": day_realized_pnl,
                "daily_mtm_pnl": day_mtm_pnl,
                "price_pnl": day_realized_pnl + day_mtm_pnl,
                "roll_pnl": day_roll_pnl,
                "transaction_fees": day_fees,
                "slippage_cost": day_slippage,
                "additional_funding": funding_added,
                "margin_call_amount": margin_call_amount,
                "margin_call_status": margin_call_status,
                "forced_liquidation_state": forced_state,
                "operations": operation_results,
                "simulation_state": simulation_state,
            }
        )

    if position is not None:
        simulation_state = "REVIEW_REQUIRED"
    if blocked_operations and simulation_state == "CLOSED":
        simulation_state = "REVIEW_REQUIRED"
    evaluation_state = "REVIEW_REQUIRED" if position is not None or blocked_operations or simulation_state == "SIMULATED_FORCED_LIQUIDATION_BLOCKED" else "EVALUABLE"
    if simulation_state == "ACTIVE" and position is None:
        simulation_state = "CLOSED"
    equity_curve = [float(row["equity"]) for row in rows]
    returns = [
        equity_curve[index] / equity_curve[index - 1] - 1
        for index in range(1, len(equity_curve))
        if equity_curve[index - 1] != 0
    ]
    final_equity = equity_curve[-1]
    benchmark_final = float(rows[-1]["benchmark_equity"])
    result_key = replay_id.strip() or f"{simulation['simulation_id']}-{close_value}"
    return {
        "schema_version": FUTURES_SIMULATION_REPLAY_SCHEMA_VERSION,
        "replay_id": f"futures-replay-{result_key.removeprefix('futures-replay-')}",
        "simulation_id": simulation["simulation_id"],
        "simulation_hash": _payload_hash(simulation),
        "outcome_hash": _payload_hash(outcome_input),
        "closed_at": close_value,
        "review_date": review_date,
        "subject_id": str(simulation["operations"][0].get("subject_id") or ""),
        "benchmark_id": str(
            simulation["benchmark"].get("series_id")
            or simulation["benchmark"].get("benchmark_id")
            or simulation["benchmark"].get("name")
            or ""
        ),
        "contract_code": str(simulation["operations"][0]["contract_code"]),
        "contract_codes": list(simulation["contract_codes"]),
        "initial_simulation_capital": float(simulation["initial_capital"]),
        "benchmark_series": [dict(benchmark[day]) for day in timeline],
        "evaluation_state": evaluation_state,
        "evaluation_reason": _evaluation_reason(
            position, blocked_operations, forced_liquidations, margin_calls
        ),
        "simulation_state": simulation_state,
        "benchmark_locked": dict(simulation["benchmark"]),
        "initial_capital": float(simulation["initial_capital"]),
        "final_equity": final_equity,
        "portfolio_return": final_equity / float(simulation["initial_capital"]) - 1,
        "benchmark_return": benchmark_final / float(simulation["initial_capital"]) - 1,
        "excess_return": (final_equity - benchmark_final) / float(simulation["initial_capital"]),
        "max_drawdown": _max_drawdown(equity_curve),
        "annualized_volatility": _annualized_volatility(returns),
        "total_price_pnl": total_price_pnl,
        "total_roll_pnl": total_roll_pnl,
        "total_fees": total_fees,
        "total_slippage": total_slippage,
        "additional_funding": additional_funding,
        "max_margin_occupied": max((float(row["margin_occupied"]) for row in rows), default=0.0),
        "margin_calls": margin_calls,
        "forced_liquidations": forced_liquidations,
        "blocked_operation_ids": blocked_operations,
        "daily_ledger": rows,
        "policy": {
            "specific_contract_only": True,
            "daily_settlement_ledger": True,
            "benchmark_taken_from_simulation": True,
            "roll_is_explicit_only": True,
            "automatic_funding": False,
            "automatic_execution": False,
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


def _apply_operation(
    operation: Mapping[str, Any],
    day: date,
    position: dict[str, Any] | None,
    contracts: Mapping[str, Mapping[date, Mapping[str, Any]]],
    cash: float,
) -> dict[str, Any]:
    action = operation["action_type"]
    code = operation["contract_code"]
    row = contracts[code][day]
    result: dict[str, Any] = {
        "status": "EXECUTED",
        "operation_id": operation["operation_id"],
        "action_type": action,
        "contract_code": code,
        "date": day.isoformat(),
    }
    if action == "OBSERVE":
        result["status"] = "OBSERVE_ONLY"
        return {"position": position, "cash": cash, "realized_pnl": 0.0, "roll_pnl": 0.0, "fees": 0.0, "slippage": 0.0, "operation_result": result}
    if action == "ESTABLISH_SIMULATION":
        if not _can_trade(row):
            result.update({"status": "BLOCKED_BY_LIMIT", "reason": "contract cannot be opened on the locked operation date"})
            return {"position": position, "cash": cash, "realized_pnl": 0.0, "roll_pnl": 0.0, "fees": 0.0, "slippage": 0.0, "operation_result": result}
        fees, slippage = _trade_cost(operation["quantity"], operation["price"], operation["contract_multiplier"], operation["fee_assumptions"], operation["slippage_assumptions"])
        new_position = {
            **operation["target_position"],
            "previous_settlement": float(operation["price"]),
            "entry_price": float(operation["price"]),
            "fee_assumptions": dict(operation["fee_assumptions"]),
            "slippage_assumptions": dict(operation["slippage_assumptions"]),
        }
        cash -= fees + slippage
        result.update({"status": "EXECUTED", "execution_price": operation["price"], "fees": fees, "slippage": slippage})
        return {"position": new_position, "cash": cash, "realized_pnl": 0.0, "roll_pnl": 0.0, "fees": fees, "slippage": slippage, "operation_result": result}
    if position is None:
        result.update({"status": "NOT_EXECUTED_NO_POSITION", "reason": "no active position remained after an earlier blocked or forced operation"})
        return {"position": None, "cash": cash, "realized_pnl": 0.0, "roll_pnl": 0.0, "fees": 0.0, "slippage": 0.0, "operation_result": result}

    if action == "HOLD":
        result.update({"status": "EXECUTED", "execution_price": None})
        result["operation_result"] = result
        return {"position": position, "cash": cash, "realized_pnl": 0.0, "roll_pnl": 0.0, "fees": 0.0, "slippage": 0.0, "operation_result": result}
    if action == "EXIT":
        if not _can_exit(row):
            result.update({"status": "BLOCKED_BY_LIMIT", "reason": "contract cannot be exited on the locked operation date"})
            return {"position": position, "cash": cash, "realized_pnl": 0.0, "roll_pnl": 0.0, "fees": 0.0, "slippage": 0.0, "operation_result": result}
        pnl = _pnl_to_price(position, operation["price"])
        fees, slippage = _trade_cost(position["quantity"], operation["price"], position["contract_multiplier"], operation["fee_assumptions"], operation["slippage_assumptions"])
        cash += pnl - fees - slippage
        result.update({"status": "EXECUTED", "execution_price": operation["price"], "realized_pnl": pnl, "fees": fees, "slippage": slippage})
        return {"position": None, "cash": cash, "realized_pnl": pnl, "roll_pnl": 0.0, "fees": fees, "slippage": slippage, "operation_result": result}

    target = operation["target_position"]
    if operation["roll"] is not None:
        roll = operation["roll"]
        old_row = contracts[position["contract_code"]][day]
        new_row = contracts[target["contract_code"]][day]
        if not _can_exit(old_row) or not _can_trade(new_row):
            result.update({"status": "BLOCKED_BY_LIMIT", "reason": "contract limit prevents one leg of the explicit roll"})
            return {"position": position, "cash": cash, "realized_pnl": 0.0, "roll_pnl": 0.0, "fees": 0.0, "slippage": 0.0, "operation_result": result}
        old_pnl = _pnl_to_price(position, roll["from_exit_price"])
        close_fees, close_slippage = _trade_cost(position["quantity"], roll["from_exit_price"], position["contract_multiplier"], operation["fee_assumptions"], operation["slippage_assumptions"])
        open_fees, open_slippage = _trade_cost(target["quantity"], roll["to_entry_price"], target["contract_multiplier"], operation["fee_assumptions"], operation["slippage_assumptions"])
        cash += old_pnl - close_fees - close_slippage - open_fees - open_slippage
        comparable = position["contract_multiplier"] == target["contract_multiplier"] and position["quantity"] == target["quantity"]
        roll_pnl = position["direction_sign"] * (roll["from_exit_price"] - roll["to_entry_price"]) * target["contract_multiplier"] * min(position["quantity"], target["quantity"]) if comparable else 0.0
        new_position = {
            **target,
            "previous_settlement": roll["to_entry_price"],
            "entry_price": roll["to_entry_price"],
            "fee_assumptions": dict(operation["fee_assumptions"]),
            "slippage_assumptions": dict(operation["slippage_assumptions"]),
        }
        fees = close_fees + open_fees
        slippage = close_slippage + open_slippage
        result.update({"status": "EXECUTED", "execution_price": roll["to_entry_price"], "realized_pnl": old_pnl, "roll_pnl": roll_pnl, "roll_pnl_status": "CALCULATED" if comparable else "NOT_COMPARABLE", "fees": fees, "slippage": slippage, "from_contract_code": position["contract_code"], "to_contract_code": target["contract_code"]})
        return {"position": new_position, "cash": cash, "realized_pnl": old_pnl, "roll_pnl": roll_pnl, "fees": fees, "slippage": slippage, "operation_result": result}

    if not _can_trade(row) or not _can_exit(row):
        result.update({"status": "BLOCKED_BY_LIMIT", "reason": "contract limit prevents the locked adjustment"})
        return {"position": position, "cash": cash, "realized_pnl": 0.0, "roll_pnl": 0.0, "fees": 0.0, "slippage": 0.0, "operation_result": result}
    pnl = _pnl_to_price(position, operation["price"])
    fees, slippage = _trade_cost(abs(target["quantity"] - position["quantity"]), operation["price"], position["contract_multiplier"], operation["fee_assumptions"], operation["slippage_assumptions"])
    cash += pnl - fees - slippage
    new_position = {
        **target,
        "previous_settlement": operation["price"],
        "entry_price": position.get("entry_price", operation["price"]),
        "fee_assumptions": dict(operation["fee_assumptions"]),
        "slippage_assumptions": dict(operation["slippage_assumptions"]),
    }
    result.update({"status": "EXECUTED", "execution_price": operation["price"], "realized_pnl": pnl, "fees": fees, "slippage": slippage, "target_quantity": target["quantity"]})
    return {"position": new_position, "cash": cash, "realized_pnl": pnl, "roll_pnl": 0.0, "fees": fees, "slippage": slippage, "operation_result": result}


def _validate_simulation_input(value: Any) -> None:
    if not isinstance(value, Mapping) or value.get("schema_version") != FUTURES_SIMULATION_INPUT_SCHEMA_VERSION:
        raise FuturesSimulationError(f"input must be {FUTURES_SIMULATION_INPUT_SCHEMA_VERSION}")
    _positive_number(value.get("initial_capital"), "initial_capital")
    if not isinstance(value.get("benchmark"), Mapping) or value["benchmark"].get("locked") is not True:
        raise FuturesSimulationError("futures simulation benchmark must be locked")
    _margin_policy(value.get("margin_policy"))
    review_date = str(value.get("review_date") or "").strip()
    if review_date:
        _calendar_day(review_date, "review_date")


def _validate_futures_snapshot(value: Any) -> None:
    if not isinstance(value, Mapping) or value.get("schema_version") != _DECISION_SCHEMA_VERSION:
        raise FuturesSimulationError(f"input decision must be {_DECISION_SCHEMA_VERSION}")
    if str(value.get("status") or "").upper() != "LOCKED" or value.get("immutable") is not True or value.get("simulation_only") is not True:
        raise FuturesSimulationError("futures simulation requires immutable LOCKED simulation snapshots")
    if value.get("execution_enabled") is not False:
        raise FuturesSimulationError("futures simulation refuses execution-enabled snapshots")
    if str(value.get("subject_type") or "").lower() != "futures_contract":
        raise FuturesSimulationError("futures simulation accepts futures_contract snapshots only")
    decision = value.get("decision")
    if not isinstance(decision, Mapping):
        raise FuturesSimulationError("futures snapshot has no decision object")
    required = (
        "decision_at", "data_cutoff", "action_type", "direction", "price", "quantity", "position_ratio",
        "capital_assumptions", "value_or_price_range", "expected_horizon", "reasons", "industry_judgment",
        "company_judgment", "survival_judgment", "fundamental_assumptions", "market_structure", "risks",
        "triggers", "invalidators", "review_date", "benchmark", "covered_factors", "excluded_factors",
        "contract_code", "contract_month", "last_trade_date", "contract_multiplier", "settlement_basis",
        "margin_assumptions", "fee_assumptions", "slippage_assumptions", "roll_rule", "expiry_handling",
        "delivery_month_limit", "price_limit_rule", "trading_session", "cross_contract_continuation",
    )
    missing = [field for field in required if field not in decision]
    if missing:
        raise FuturesSimulationError("futures snapshot missing required fields: " + ", ".join(missing))
    action = str(decision["action_type"]).strip().upper()
    direction = str(decision["direction"]).strip().upper()
    if action not in _ACTIONS or direction not in _DIRECTIONS:
        raise FuturesSimulationError("futures snapshot has unsupported action or direction")
    code = str(decision["contract_code"]).strip().upper()
    if not code or code in {"CONTINUOUS", "MAIN"}:
        raise FuturesSimulationError("futures snapshot must bind a specific contract")
    if not isinstance(decision["benchmark"], Mapping):
        raise FuturesSimulationError("futures snapshot benchmark must be an object")
    if not isinstance(decision["cross_contract_continuation"], bool):
        raise FuturesSimulationError("cross_contract_continuation must be boolean")
    for field in ("capital_assumptions", "value_or_price_range", "market_structure", "benchmark", "margin_assumptions", "fee_assumptions", "slippage_assumptions"):
        if not isinstance(decision[field], Mapping) or not decision[field]:
            raise FuturesSimulationError(f"{field} must be a non-empty object")
    for field in ("reasons", "fundamental_assumptions", "risks", "triggers", "invalidators", "covered_factors", "excluded_factors"):
        if not isinstance(decision[field], Sequence) or isinstance(decision[field], (str, bytes, bytearray)) or not decision[field]:
            raise FuturesSimulationError(f"{field} must be a non-empty list")
    for field in ("decision_at", "data_cutoff", "expected_horizon", "review_date", "contract_month", "last_trade_date", "settlement_basis", "roll_rule", "expiry_handling", "delivery_month_limit", "price_limit_rule", "trading_session"):
        if not str(decision[field]).strip():
            raise FuturesSimulationError(f"{field} must be non-empty")


def _validate_simulation(value: Any) -> None:
    if not isinstance(value, Mapping) or value.get("schema_version") != FUTURES_SIMULATION_SCHEMA_VERSION:
        raise FuturesSimulationError(f"input must be {FUTURES_SIMULATION_SCHEMA_VERSION}")
    if value.get("immutable") is not True or value.get("simulation_only") is not True or value.get("execution_enabled") is not False:
        raise FuturesSimulationError("futures simulation must be immutable and execution-disabled")
    if not isinstance(value.get("operations"), list) or not value["operations"]:
        raise FuturesSimulationError("futures simulation has no operations")
    if not isinstance(value.get("contract_codes"), list) or not value["contract_codes"]:
        raise FuturesSimulationError("futures simulation has no contract codes")
    _positive_number(value.get("initial_capital"), "initial_capital")
    if not isinstance(value.get("benchmark"), Mapping) or value["benchmark"].get("locked") is not True:
        raise FuturesSimulationError("futures simulation benchmark must be locked")
    _margin_policy(value.get("margin_policy"))


def _validate_outcome(value: Any) -> None:
    if not isinstance(value, Mapping) or value.get("schema_version") != FUTURES_SIMULATION_OUTCOME_SCHEMA_VERSION:
        raise FuturesSimulationError(f"input must be {FUTURES_SIMULATION_OUTCOME_SCHEMA_VERSION}")
    if not isinstance(value.get("contract_series"), Mapping) or not value["contract_series"]:
        raise FuturesSimulationError("outcome contract_series must be an object")
    if not isinstance(value.get("benchmark_series"), Sequence) or isinstance(value["benchmark_series"], (str, bytes, bytearray)):
        raise FuturesSimulationError("outcome benchmark_series must be a list")


def _validate_benchmark_match(left: Mapping[str, Any], right: Mapping[str, Any]) -> None:
    left_id = str(left.get("series_id") or left.get("benchmark_id") or "").strip()
    right_id = str(right.get("series_id") or right.get("benchmark_id") or "").strip()
    if not left_id or left_id != right_id or left.get("locked") is not True or right.get("locked") is not True:
        raise FuturesSimulationError("every futures decision benchmark must match the locked simulation benchmark")


def _normalise_value_series(rows: Sequence[Mapping[str, Any]], name: str, field: str) -> dict[date, dict[str, Any]]:
    result: dict[date, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise FuturesSimulationError(f"{name} rows must be objects")
        day = _calendar_day(row.get("date"), f"{name}.date")
        if day in result:
            raise FuturesSimulationError(f"duplicate date in {name}: {day}")
        result[day] = {**row, "date": day.isoformat(), field: _positive_number(row.get(field), f"{name}.{field}")}
    if not result:
        raise FuturesSimulationError(f"{name} must not be empty")
    return result


def _normalise_contract_series(value: Mapping[str, Any]) -> dict[str, dict[date, dict[str, Any]]]:
    result: dict[str, dict[date, dict[str, Any]]] = {}
    for raw_code, raw_rows in value.items():
        code = str(raw_code).strip().upper()
        if not code or code in {"CONTINUOUS", "MAIN"}:
            raise FuturesSimulationError("contract_series must contain specific contracts only")
        if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes, bytearray)):
            raise FuturesSimulationError(f"contract_series[{code}] must be a list")
        rows: dict[date, dict[str, Any]] = {}
        for raw in raw_rows:
            if not isinstance(raw, Mapping):
                raise FuturesSimulationError(f"contract_series[{code}] rows must be objects")
            day = _calendar_day(raw.get("date"), f"contract_series[{code}].date")
            if day in rows:
                raise FuturesSimulationError(f"duplicate date in contract_series[{code}]: {day}")
            margin_rate = _fraction(raw.get("margin_rate"), f"contract_series[{code}].margin_rate")
            rule_version = str(raw.get("rule_version") or "").strip()
            if not rule_version:
                raise FuturesSimulationError(f"contract_series[{code}] rule_version is required")
            limit_status = str(raw.get("price_limit_status") or "NORMAL").strip().upper()
            if limit_status not in _LIMIT_STATUSES:
                raise FuturesSimulationError(f"unsupported price_limit_status: {limit_status}")
            can_trade = raw.get("can_trade", limit_status == "NORMAL")
            can_exit = raw.get("can_exit", limit_status == "NORMAL")
            if not isinstance(can_trade, bool) or not isinstance(can_exit, bool):
                raise FuturesSimulationError("can_trade and can_exit must be boolean")
            rows[day] = {
                **raw,
                "date": day.isoformat(),
                "settlement": _positive_number(raw.get("settlement"), f"contract_series[{code}].settlement"),
                "margin_rate": margin_rate,
                "rule_version": rule_version,
                "price_limit_status": limit_status,
                "can_trade": can_trade,
                "can_exit": can_exit,
            }
        if not rows:
            raise FuturesSimulationError(f"contract_series[{code}] must not be empty")
        result[code] = rows
    if not result:
        raise FuturesSimulationError("contract_series must not be empty")
    return result


def _apply_position_mark(position: Mapping[str, Any], settlement: float) -> dict[str, float]:
    return {"pnl": _pnl_to_price(position, settlement)}


def _mark_position(position: Mapping[str, Any], settlement: float) -> dict[str, float]:
    return _apply_position_mark(position, settlement)


def _pnl_to_price(position: Mapping[str, Any], price: float) -> float:
    return float(position["direction_sign"]) * (float(price) - float(position["previous_settlement"])) * float(position["contract_multiplier"]) * int(position["quantity"])


def _margin_occupied(position: Mapping[str, Any], row: Mapping[str, Any]) -> float:
    return abs(float(row["settlement"]) * float(position["contract_multiplier"]) * int(position["quantity"]) * float(row["margin_rate"]))


def _trade_cost(quantity: int | float, price: float, multiplier: float, fee: Mapping[str, Any], slippage: Mapping[str, Any]) -> tuple[float, float]:
    quantity = float(quantity)
    notional = abs(quantity) * float(price) * float(multiplier)
    fee_value = notional * float(fee["rate"]) + quantity * float(fee["fixed"])
    slippage_value = notional * float(slippage["rate"]) + quantity * float(slippage["fixed"])
    return fee_value, slippage_value


def _cost_assumptions(value: Any, field: str) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise FuturesSimulationError(f"{field} must be an object")
    return {
        "rate": _non_negative_number(value.get("rate", 0), f"{field}.rate"),
        "fixed": _non_negative_number(value.get("fixed", 0), f"{field}.fixed"),
    }


def _operation_cost_assumptions(operation: Mapping[str, Any] | None, field: str) -> Mapping[str, Any]:
    if operation is not None and isinstance(operation.get(field), Mapping):
        return operation[field]
    return {"rate": 0.0, "fixed": 0.0}


def _position_cost_assumptions(
    position: Mapping[str, Any], operation: Mapping[str, Any] | None, field: str
) -> Mapping[str, Any]:
    if operation is not None and isinstance(operation.get(field), Mapping):
        return operation[field]
    if isinstance(position.get(field), Mapping):
        return position[field]
    return {"rate": 0.0, "fixed": 0.0}


def _margin_policy(value: Any) -> dict[str, Any]:
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise FuturesSimulationError("margin_policy must be an object")
    allow = value.get("allow_additional_funding", False)
    if not isinstance(allow, bool):
        raise FuturesSimulationError("margin_policy.allow_additional_funding must be boolean")
    maximum = _non_negative_number(value.get("max_additional_funding", 0), "max_additional_funding")
    return {
        "allow_additional_funding": allow,
        "max_additional_funding": maximum if allow else 0.0,
        "forced_liquidation_on_unfunded": True,
    }


def _validate_roll(value: Any, current: Mapping[str, Any], target: Mapping[str, Any], decision: Mapping[str, Any], snapshot_id: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise FuturesSimulationError(f"contract change requires an explicit roll object: {snapshot_id}")
    from_code = str(value.get("from_contract_code") or "").strip().upper()
    to_code = str(value.get("to_contract_code") or target["contract_code"]).strip().upper()
    if from_code != current["contract_code"] or to_code != target["contract_code"]:
        raise FuturesSimulationError(f"roll contract codes do not match the locked position: {snapshot_id}")
    from_exit = _positive_number(value.get("from_exit_price"), f"roll.from_exit_price for {snapshot_id}")
    to_entry = _positive_number(value.get("to_entry_price", decision.get("price")), f"roll.to_entry_price for {snapshot_id}")
    if abs(to_entry - float(decision["price"])) > max(1e-9, abs(to_entry) * 1e-9):
        raise FuturesSimulationError(f"roll.to_entry_price must equal decision price: {snapshot_id}")
    return {
        "from_contract_code": from_code,
        "to_contract_code": to_code,
        "from_exit_price": from_exit,
        "to_entry_price": to_entry,
        "reason": str(value.get("reason") or "").strip(),
    }


def _operation_contract_codes(operation: Mapping[str, Any]) -> set[str]:
    codes = {str(operation["contract_code"]).upper()}
    roll = operation.get("roll")
    if isinstance(roll, Mapping):
        codes.add(str(roll["from_contract_code"]).upper())
        codes.add(str(roll["to_contract_code"]).upper())
    return codes


def _active_contract_codes(position: Mapping[str, Any] | None, operation: Mapping[str, Any] | None) -> set[str]:
    codes = set()
    if position is not None:
        codes.add(str(position["contract_code"]).upper())
    if operation is not None:
        codes.update(_operation_contract_codes(operation))
    return codes


def _position_copy(position: Mapping[str, Any] | None) -> dict[str, Any] | None:
    return dict(position) if position is not None else None


def _position_view(position: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if position is None:
        return None
    return {
        "contract_code": position["contract_code"],
        "contract_month": position["contract_month"],
        "direction": position["direction"],
        "quantity": position["quantity"],
        "contract_multiplier": position["contract_multiplier"],
        "entry_price": position.get("entry_price"),
        "previous_settlement": position.get("previous_settlement"),
    }


def _can_trade(row: Mapping[str, Any]) -> bool:
    return bool(row.get("can_trade"))


def _can_exit(row: Mapping[str, Any]) -> bool:
    return bool(row.get("can_exit"))


def _fraction(value: Any, field: str) -> float:
    number = _non_negative_number(value, field)
    if number > 1:
        raise FuturesSimulationError(f"{field} must be between 0 and 1")
    return number


def _lots(value: Any, field: str) -> int:
    number = _positive_number(value, field)
    if not number.is_integer():
        raise FuturesSimulationError(f"{field} must be a whole number of lots")
    return int(number)


def _evaluation_reason(position: Mapping[str, Any] | None, blocked: Sequence[str], forced: Sequence[Mapping[str, Any]], calls: Sequence[Mapping[str, Any]]) -> str:
    if position is not None:
        return "position remained active at closed_at; no automatic exit was inferred"
    if blocked:
        return "one or more locked futures operations were blocked by contract limits"
    if forced:
        return "dated settlement series replayed; an unfunded margin call caused simulated forced liquidation"
    if calls:
        return "dated settlement series replayed with a margin call"
    return "dated settlement, margin and rule rows were replayed"


def _not_evaluable(simulation: Mapping[str, Any], closed_at: str, reason: str, *, replay_id: str) -> dict[str, Any]:
    key = replay_id.strip() or f"{simulation['simulation_id']}-{closed_at}"
    return {
        "schema_version": FUTURES_SIMULATION_REPLAY_SCHEMA_VERSION,
        "replay_id": f"futures-replay-{key.removeprefix('futures-replay-')}",
        "simulation_id": simulation["simulation_id"],
        "closed_at": closed_at,
        "evaluation_state": "NOT_EVALUABLE",
        "evaluation_reason": reason,
        "benchmark_locked": dict(simulation["benchmark"]),
        "daily_ledger": [],
        "policy": {
            "specific_contract_only": True,
            "daily_settlement_ledger": True,
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
        raise FuturesSimulationError(f"{field} must be non-empty")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text)
        except ValueError as error:
            raise FuturesSimulationError(f"{field} must be ISO date/datetime") from error


def _positive_number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise FuturesSimulationError(f"{field} must be numeric") from error
    if not isfinite(number) or number <= 0:
        raise FuturesSimulationError(f"{field} must be positive")
    return number


def _non_negative_number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise FuturesSimulationError(f"{field} must be numeric") from error
    if not isfinite(number) or number < 0:
        raise FuturesSimulationError(f"{field} must be non-negative")
    return number


def _max_drawdown(values: Sequence[float]) -> float:
    if not values:
        return 0.0
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
