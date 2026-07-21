import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.simulation_portfolio import (
    SimulationPortfolioError,
    build_simulation_portfolio,
    replay_simulation_portfolio,
)


def snapshot(
    snapshot_id,
    subject_id,
    action,
    decision_at,
    *,
    price=100,
    quantity=10,
    direction="BULLISH",
):
    decision = {
        "subject_id": subject_id,
        "decision_at": decision_at,
        "price": price,
        "quantity": quantity,
        "position_ratio": 0.2,
        "direction": direction,
        "action_type": action,
        "review_date": "2026-07-04",
        "benchmark": {"name": "CSI300", "series_id": "000300", "locked": True},
        "capital_assumptions": {"currency": "CNY", "simulation_capital": 10000},
    }
    return {
        "schema_version": "decision-snapshot.v1",
        "snapshot_id": snapshot_id,
        "status": "LOCKED",
        "subject_type": "listed_company",
        "subject_id": subject_id,
        "decision": decision,
        "immutable": True,
        "simulation_only": True,
        "execution_enabled": False,
    }


def portfolio_input():
    return {
        "schema_version": "simulation-portfolio-input.v1",
        "portfolio_id": "baijiu-demo",
        "portfolio_name": "白酒模拟组合",
        "initial_capital": 10000,
        "currency": "CNY",
        "review_date": "2026-07-04",
        "benchmark": {"name": "CSI300", "series_id": "000300", "locked": True},
    }


def decisions():
    return [
        snapshot("decision-snapshot-a-open", "600519", "ESTABLISH_SIMULATION", "2026-07-01", price=100),
        snapshot("decision-snapshot-a-hold", "600519", "HOLD", "2026-07-02", price=104),
        snapshot("decision-snapshot-b-open", "000858", "ESTABLISH_SIMULATION", "2026-07-02", price=200, quantity=5),
        snapshot("decision-snapshot-a-adjust", "600519", "ADJUST", "2026-07-03", price=105, quantity=8),
        snapshot("decision-snapshot-a-exit", "600519", "EXIT", "2026-07-04", price=110, quantity=8, direction="AVOID"),
    ]


def outcome():
    return {
        "schema_version": "simulation-portfolio-outcome.v1",
        "asset_series": {
            "600519": [
                {"date": "2026-07-01", "price": 100},
                {"date": "2026-07-02", "price": 105},
                {"date": "2026-07-03", "price": 108, "dividend": 2},
                {"date": "2026-07-04", "price": 109},
            ],
            "000858": [
                {"date": "2026-07-01", "price": 200},
                {"date": "2026-07-02", "price": 200},
                {"date": "2026-07-03", "price": 205},
                {"date": "2026-07-04", "price": 210},
            ],
        },
        "benchmark_series": [
            {"date": "2026-07-01", "value": 100},
            {"date": "2026-07-02", "value": 101},
            {"date": "2026-07-03", "value": 102},
            {"date": "2026-07-04", "value": 104},
        ],
    }


def test_portfolio_keeps_multiple_locked_operations_and_target_quantity_semantics():
    portfolio = build_simulation_portfolio(portfolio_input(), decisions())

    assert portfolio["schema_version"] == "simulation-portfolio.v1"
    assert portfolio["decision_snapshot_ids"] == [item["snapshot_id"] for item in decisions()]
    assert [item["target_quantity"] for item in portfolio["operations"]] == [10, 10, 5, 8, 0]
    assert portfolio["policy"]["decision_snapshots_unchanged"] is True
    assert portfolio["execution_enabled"] is False


def test_portfolio_replay_uses_locked_execution_prices_and_dated_market_marks():
    portfolio = build_simulation_portfolio(portfolio_input(), decisions())
    replay = replay_simulation_portfolio(portfolio, outcome(), closed_at="2026-07-04")

    assert replay["evaluation_state"] == "EVALUABLE"
    assert replay["final_equity"] == pytest.approx(10156)
    assert replay["portfolio_return"] == pytest.approx(0.0156)
    assert replay["benchmark_return"] == pytest.approx(0.04)
    assert replay["excess_return"] == pytest.approx(-0.0244)
    assert replay["total_dividends"] == pytest.approx(16)
    assert replay["max_drawdown"] == pytest.approx(0)
    assert replay["daily_ledger"][-1]["holdings"]["600519"]["quantity"] == 0
    assert replay["policy"]["benchmark_taken_from_portfolio"] is True


def test_portfolio_replay_does_not_fabricate_result_for_missing_or_future_data():
    portfolio = build_simulation_portfolio(portfolio_input(), decisions())
    incomplete = outcome()
    incomplete["asset_series"]["000858"].pop(2)
    replay = replay_simulation_portfolio(portfolio, incomplete, closed_at="2026-07-04")
    assert replay["evaluation_state"] == "NOT_EVALUABLE"
    assert "000858" in replay["evaluation_reason"]

    future = outcome()
    future["benchmark_series"].append({"date": "2026-07-05", "value": 105})
    replay = replay_simulation_portfolio(portfolio, future, closed_at="2026-07-04")
    assert replay["evaluation_state"] == "NOT_EVALUABLE"
    assert "after closed_at" in replay["evaluation_reason"]


def test_portfolio_rejects_unlocked_benchmark_or_ambiguous_operation_order():
    bad_input = portfolio_input()
    bad_input["benchmark"]["locked"] = False
    with pytest.raises(SimulationPortfolioError, match="benchmark must be locked"):
        build_simulation_portfolio(bad_input, decisions())

    reversed_decisions = [
        snapshot("decision-snapshot-a-open-late", "600519", "ESTABLISH_SIMULATION", "2026-07-02"),
        snapshot("decision-snapshot-a-adjust-early", "600519", "ADJUST", "2026-07-01", quantity=8),
    ]
    with pytest.raises(SimulationPortfolioError, match="chronological"):
        build_simulation_portfolio(portfolio_input(), reversed_decisions)


def test_portfolio_requires_exit_before_re_establishing_same_subject():
    more = decisions()[:1] + [
        snapshot(
            "decision-snapshot-a-open-again",
            "600519",
            "ESTABLISH_SIMULATION",
            "2026-07-02",
        )
    ]
    with pytest.raises(SimulationPortfolioError, match="twice"):
        build_simulation_portfolio(portfolio_input(), more)


def test_portfolio_cli_creates_and_replays_saved_records(tmp_path, monkeypatch, capsys):
    input_path = tmp_path / "portfolio-input.json"
    input_path.write_text(json.dumps(portfolio_input()), encoding="utf-8")
    decision_paths = []
    for index, item in enumerate(decisions()):
        path = tmp_path / f"decision-{index}.json"
        path.write_text(json.dumps(item), encoding="utf-8")
        decision_paths.append(str(path))
    portfolio_dir = tmp_path / "portfolios"
    argv = [
        "industry-first-research",
        "portfolio-create",
        "--input",
        str(input_path),
        "--output-dir",
        str(portfolio_dir),
    ]
    for path in decision_paths:
        argv.extend(("--decision", path))
    monkeypatch.setattr(sys, "argv", argv)
    main()
    capsys.readouterr()

    portfolio_path = portfolio_dir / "simulation-portfolio-baijiu-demo.json"
    outcome_path = tmp_path / "outcome.json"
    outcome_path.write_text(json.dumps(outcome()), encoding="utf-8")
    replay_dir = tmp_path / "replays"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "portfolio-replay",
            "--input",
            str(portfolio_path),
            "--outcome",
            str(outcome_path),
            "--closed-at",
            "2026-07-04",
            "--output-dir",
            str(replay_dir),
        ],
    )
    main()
    capsys.readouterr()

    replay_path = replay_dir / "portfolio-replay-simulation-portfolio-baijiu-demo-2026-07-04.json"
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    assert replay["evaluation_state"] == "EVALUABLE"
