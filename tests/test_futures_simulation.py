import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.attribution import build_attribution_report
from industry_first_research.quality_scorecard import build_quality_scorecard
from industry_first_research.futures_simulation import (
    FuturesSimulationError,
    build_futures_simulation,
    replay_futures_simulation,
)


def snapshot(
    snapshot_id,
    contract_code,
    action,
    decision_at,
    *,
    price=100,
    quantity=1,
    direction="BULLISH",
    roll=None,
    cross_contract_continuation=False,
):
    decision = {
        "subject_id": contract_code,
        "decision_at": decision_at,
        "data_cutoff": decision_at,
        "price": price,
        "quantity": quantity,
        "position_ratio": 0.2,
        "direction": direction,
        "action_type": action,
        "review_date": "2026-07-01",
        "benchmark": {"name": "commodity-index", "series_id": "CMI", "locked": True},
        "capital_assumptions": {"currency": "CNY", "simulation_capital": 10000},
        "value_or_price_range": {"low": 90, "high": 110},
        "expected_horizon": "one-week",
        "reasons": ["test"],
        "industry_judgment": "test",
        "company_judgment": "not_applicable",
        "survival_judgment": "not_applicable",
        "fundamental_assumptions": ["test"],
        "market_structure": {"state": "test"},
        "risks": ["test"],
        "triggers": ["test"],
        "invalidators": ["test"],
        "covered_factors": ["settlement"],
        "excluded_factors": ["execution"],
        "contract_code": contract_code,
        "contract_month": contract_code[-4:],
        "last_trade_date": "2026-08-14",
        "contract_multiplier": 10,
        "settlement_basis": "exchange_daily_settlement",
        "margin_assumptions": {"source": "locked-rule"},
        "fee_assumptions": {"rate": 0, "fixed": 0},
        "slippage_assumptions": {"rate": 0, "fixed": 0},
        "roll_rule": "user_confirmed_explicit_roll",
        "expiry_handling": "exit_before_last_trade_date",
        "delivery_month_limit": "not_entered",
        "price_limit_rule": "exchange_rule_version",
        "trading_session": "exchange_session",
        "cross_contract_continuation": cross_contract_continuation,
    }
    if roll is not None:
        decision["roll"] = roll
    return {
        "schema_version": "decision-snapshot.v1",
        "snapshot_id": snapshot_id,
        "status": "LOCKED",
        "subject_type": "futures_contract",
        "subject_id": contract_code,
        "decision": decision,
        "immutable": True,
        "simulation_only": True,
        "execution_enabled": False,
    }


def simulation_input(**overrides):
    value = {
        "schema_version": "futures-simulation-input.v1",
        "simulation_id": "copper-demo",
        "simulation_name": "铜期货模拟",
        "initial_capital": 10000,
        "currency": "CNY",
        "review_date": "2026-07-01",
        "benchmark": {"name": "commodity-index", "series_id": "CMI", "locked": True},
        "margin_policy": {
            "allow_additional_funding": False,
            "max_additional_funding": 0,
        },
    }
    value.update(overrides)
    return value


def contract_rows(code, settlements, *, margin_rate=0.1, limit_status="NORMAL", can_exit=None):
    rows = []
    for index, settlement in enumerate(settlements, start=1):
        row = {
            "date": f"2026-07-0{index}",
            "settlement": settlement,
            "margin_rate": margin_rate,
            "rule_version": "SHFE-test-v1",
            "price_limit_status": limit_status,
        }
        if can_exit is not None:
            row["can_exit"] = can_exit
        rows.append(row)
    return rows


def benchmark_rows(values):
    return [
        {"date": f"2026-07-0{index}", "value": value}
        for index, value in enumerate(values, start=1)
    ]


def outcome(contract_series, benchmark=None):
    return {
        "schema_version": "futures-simulation-outcome.v1",
        "contract_series": contract_series,
        "benchmark_series": benchmark or benchmark_rows([100, 101, 102]),
    }


def test_futures_replay_marks_to_daily_settlement_and_keeps_margin_separate():
    decisions = [
        snapshot("decision-snapshot-open", "CU2608", "ESTABLISH_SIMULATION", "2026-07-01", price=100),
        snapshot("decision-snapshot-hold", "CU2608", "HOLD", "2026-07-02", price=103),
        snapshot("decision-snapshot-exit", "CU2608", "EXIT", "2026-07-03", price=102),
    ]
    simulation = build_futures_simulation(simulation_input(), decisions)
    replay = replay_futures_simulation(
        simulation,
        outcome({"CU2608": contract_rows("CU2608", [101, 103, 102])}),
        closed_at="2026-07-03",
    )

    assert replay["evaluation_state"] == "EVALUABLE"
    assert replay["simulation_state"] == "CLOSED"
    assert replay["final_equity"] == pytest.approx(10020)
    assert replay["total_price_pnl"] == pytest.approx(20)
    assert replay["daily_ledger"][0]["margin_occupied"] == pytest.approx(101)
    assert replay["daily_ledger"][-1]["margin_occupied"] == pytest.approx(0)
    assert replay["daily_ledger"][-1]["position"] is None
    assert replay["policy"]["daily_settlement_ledger"] is True
    assert replay["execution_enabled"] is False


def test_futures_replay_flows_through_attribution_and_quality_scorecard():
    decisions = [
        snapshot("decision-snapshot-open", "CU2608", "ESTABLISH_SIMULATION", "2026-07-01", price=100),
        snapshot("decision-snapshot-exit", "CU2608", "EXIT", "2026-07-03", price=102),
    ]
    simulation = build_futures_simulation(simulation_input(), decisions)
    replay = replay_futures_simulation(
        simulation,
        outcome({"CU2608": contract_rows("CU2608", [101, 103, 102])}),
        closed_at="2026-07-03",
    )
    attribution = build_attribution_report(
        decisions[0], replay, closed_at="2026-07-03"
    )
    scorecard = build_quality_scorecard(
        decisions[0],
        attribution_report=attribution,
    )

    assert attribution["schema_version"] == "attribution-result.v1"
    assert attribution["methodology"]["source_outcome_input_schema"] == "futures-simulation-replay.v1"
    assert attribution["futures"]["daily_settlement_ledger"]
    assert scorecard["attribution_id"] == attribution["attribution_id"]
    assert scorecard["dimensions"]["outcome_performance"]["status"] != "NOT_EVALUABLE"
    assert scorecard["policy"]["return_does_not_prove_fact_accuracy"] is True


def test_futures_replay_requires_explicit_roll_and_records_roll_diagnostic():
    decisions = [
        snapshot("decision-snapshot-open", "CU2608", "ESTABLISH_SIMULATION", "2026-07-01", price=100),
        snapshot(
            "decision-snapshot-roll",
            "CU2609",
            "ADJUST",
            "2026-07-02",
            price=95,
            roll={
                "from_contract_code": "CU2608",
                "to_contract_code": "CU2609",
                "from_exit_price": 101,
                "to_entry_price": 95,
                "reason": "explicit test roll",
            },
            cross_contract_continuation=True,
        ),
        snapshot("decision-snapshot-exit", "CU2609", "EXIT", "2026-07-03", price=96),
    ]
    simulation = build_futures_simulation(simulation_input(), decisions)
    replay = replay_futures_simulation(
        simulation,
        outcome(
            {
                "CU2608": contract_rows("CU2608", [101, 101, 101]),
                "CU2609": contract_rows("CU2609", [95, 96, 96]),
            }
        ),
        closed_at="2026-07-03",
    )

    assert replay["evaluation_state"] == "EVALUABLE"
    assert replay["final_equity"] == pytest.approx(10020)
    assert replay["total_roll_pnl"] == pytest.approx(60)
    roll_result = replay["daily_ledger"][1]["operations"][0]
    assert roll_result["status"] == "EXECUTED"
    assert roll_result["roll_pnl_status"] == "CALCULATED"
    assert roll_result["from_contract_code"] == "CU2608"
    assert roll_result["to_contract_code"] == "CU2609"


def test_futures_margin_shortfall_triggers_simulated_forced_liquidation():
    decisions = [
        snapshot("decision-snapshot-open", "CU2608", "ESTABLISH_SIMULATION", "2026-07-01", price=100),
    ]
    simulation = build_futures_simulation(
        simulation_input(initial_capital=50),
        decisions,
    )
    replay = replay_futures_simulation(
        simulation,
        outcome({"CU2608": contract_rows("CU2608", [80, 80, 80])}),
        closed_at="2026-07-03",
    )

    assert replay["evaluation_state"] == "EVALUABLE"
    assert replay["simulation_state"] == "SIMULATED_FORCED_LIQUIDATION"
    assert replay["forced_liquidations"][0]["status"] == "SIMULATED_FORCED_LIQUIDATION"
    assert replay["margin_calls"][0]["unfunded_amount"] > 0
    assert replay["daily_ledger"][0]["position"] is None
    assert replay["execution_enabled"] is False


def test_futures_limit_blocked_exit_is_review_required_and_not_filled():
    decisions = [
        snapshot("decision-snapshot-open", "CU2608", "ESTABLISH_SIMULATION", "2026-07-01", price=100),
        snapshot("decision-snapshot-exit", "CU2608", "EXIT", "2026-07-02", price=110),
    ]
    simulation = build_futures_simulation(simulation_input(), decisions)
    rows = contract_rows("CU2608", [101, 110, 109])
    rows[1]["price_limit_status"] = "UP_LIMIT"
    rows[1]["can_exit"] = False
    rows[1]["can_trade"] = False
    replay = replay_futures_simulation(
        simulation,
        outcome({"CU2608": rows}),
        closed_at="2026-07-03",
    )

    assert replay["evaluation_state"] == "REVIEW_REQUIRED"
    assert replay["blocked_operation_ids"] == ["futures-operation-exit"]
    assert replay["daily_ledger"][-1]["position"]["contract_code"] == "CU2608"
    assert replay["daily_ledger"][1]["operations"][0]["status"] == "BLOCKED_BY_LIMIT"


def test_futures_simulation_rejects_continuous_contract_and_future_rows():
    with pytest.raises(FuturesSimulationError, match="specific contract"):
        build_futures_simulation(
            simulation_input(),
            [snapshot("decision-snapshot-open", "CONTINUOUS", "ESTABLISH_SIMULATION", "2026-07-01")],
        )

    decisions = [
        snapshot("decision-snapshot-open", "CU2608", "ESTABLISH_SIMULATION", "2026-07-01"),
    ]
    simulation = build_futures_simulation(simulation_input(), decisions)
    future = contract_rows("CU2608", [101, 102, 103])
    future.append({
        "date": "2026-07-05",
        "settlement": 104,
        "margin_rate": 0.1,
        "rule_version": "SHFE-test-v1",
    })
    replay = replay_futures_simulation(
        simulation,
        outcome({"CU2608": future}),
        closed_at="2026-07-03",
    )
    assert replay["evaluation_state"] == "NOT_EVALUABLE"
    assert "after closed_at" in replay["evaluation_reason"]


def test_futures_simulation_cli_creates_and_replays_immutable_records(tmp_path, monkeypatch, capsys):
    decisions = [
        snapshot("decision-snapshot-open", "CU2608", "ESTABLISH_SIMULATION", "2026-07-01"),
        snapshot("decision-snapshot-exit", "CU2608", "EXIT", "2026-07-02", price=101),
    ]
    input_path = tmp_path / "simulation-input.json"
    input_path.write_text(json.dumps(simulation_input()), encoding="utf-8")
    decision_paths = []
    for index, item in enumerate(decisions):
        path = tmp_path / f"decision-{index}.json"
        path.write_text(json.dumps(item), encoding="utf-8")
        decision_paths.append(path)
    outcome_path = tmp_path / "outcome.json"
    outcome_path.write_text(
        json.dumps(outcome({"CU2608": contract_rows("CU2608", [100, 101, 101])})),
        encoding="utf-8",
    )
    simulation_dir = tmp_path / "simulations"
    argv = [
        "industry-first-research",
        "futures-simulation-create",
        "--input",
        str(input_path),
        "--output-dir",
        str(simulation_dir),
    ]
    for path in decision_paths:
        argv.extend(("--decision", str(path)))
    monkeypatch.setattr(sys, "argv", argv)
    main()
    capsys.readouterr()
    simulation_path = simulation_dir / "futures-simulation-copper-demo.json"
    assert simulation_path.exists()

    replay_dir = tmp_path / "replays"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "futures-simulation-replay",
            "--input",
            str(simulation_path),
            "--outcome",
            str(outcome_path),
            "--closed-at",
            "2026-07-02",
            "--output-dir",
            str(replay_dir),
        ],
    )
    main()
    capsys.readouterr()
    replay_path = replay_dir / "futures-replay-futures-simulation-copper-demo-2026-07-02.json"
    assert replay_path.exists()
    assert json.loads(replay_path.read_text(encoding="utf-8"))["execution_enabled"] is False


def test_futures_replay_can_feed_the_shared_attribution_envelope():
    decisions = [
        snapshot("decision-snapshot-open", "CU2608", "ESTABLISH_SIMULATION", "2026-07-01"),
        snapshot("decision-snapshot-exit", "CU2608", "EXIT", "2026-07-03", price=102),
    ]
    simulation = build_futures_simulation(simulation_input(), decisions)
    replay = replay_futures_simulation(
        simulation,
        outcome({"CU2608": contract_rows("CU2608", [101, 103, 102])}),
        closed_at="2026-07-03",
    )
    report = build_attribution_report(decisions[0], replay, closed_at="2026-07-03")

    assert report["evaluation_state"] == "EVALUABLE"
    assert report["futures"]["total_simulated_pnl"] == pytest.approx(20)
    assert report["comparison"]["excess_return_comparable"] is False
    assert report["policy"]["execution_enabled"] is False
