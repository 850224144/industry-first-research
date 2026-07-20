import pytest

from industry_first_research.attribution import (
    AttributionError,
    build_attribution_report,
)


def snapshot(*, subject_type="listed_company", direction="BULLISH"):
    decision = {
        "subject_id": "600438",
        "subject_type": subject_type,
        "decision_at": "2026-07-01T15:00:00+08:00",
        "price": 100.0,
        "quantity": 1,
        "direction": direction,
        "review_date": "2026-07-31",
        "benchmark": {"name": "CSI300", "series_id": "000300", "locked": True},
        "capital_assumptions": {"currency": "CNY", "simulation_capital": 1000},
    }
    if subject_type == "futures_contract":
        decision.update(
            {
                "contract_code": "RB2610",
                "contract_multiplier": 10,
                "margin_assumptions": {"rate": 0.1},
            }
        )
    return {
        "schema_version": "decision-snapshot.v1",
        "snapshot_id": "decision-snapshot-001",
        "status": "LOCKED",
        "subject_type": subject_type,
        "subject_id": decision["subject_id"],
        "decision": decision,
        "immutable": True,
        "simulation_only": True,
        "execution_enabled": False,
    }


def company_outcome():
    return {
        "schema_version": "attribution-input.v1",
        "benchmark_id": "000300",
        "asset_series": [
            {"date": "2026-07-01", "price": 100},
            {"date": "2026-07-31", "price": 110, "dividend": 2, "fee": 1},
        ],
        "benchmark_series": [
            {"date": "2026-07-01", "value": 100},
            {"date": "2026-07-31", "value": 105},
        ],
    }


def test_company_attribution_uses_locked_benchmark_and_observable_components():
    report = build_attribution_report(snapshot(), company_outcome(), closed_at="2026-07-31")

    assert report["evaluation_state"] == "EVALUABLE"
    assert report["asset_return"] == pytest.approx(0.11)
    assert report["benchmark_return"] == pytest.approx(0.05)
    assert report["excess_return"] == pytest.approx(0.06)
    assert report["return_components"]["price_return"] == pytest.approx(0.10)
    assert report["return_components"]["dividend_return"] == pytest.approx(0.02)
    assert report["return_components"]["cost_return"] == pytest.approx(-0.01)
    assert report["comparison"]["benchmark_id"] == "000300"
    assert report["policy"]["locked_snapshot_unchanged"] is True


def test_attribution_rejects_benchmark_replacement_and_future_observations():
    outcome = company_outcome()
    outcome["benchmark_id"] = "000905"
    with pytest.raises(AttributionError, match="locked in the decision snapshot"):
        build_attribution_report(snapshot(), outcome, closed_at="2026-07-31")

    outcome = company_outcome()
    outcome["asset_series"].append({"date": "2026-08-01", "price": 111})
    outcome["benchmark_series"].append({"date": "2026-08-01", "value": 106})
    report = build_attribution_report(snapshot(), outcome, closed_at="2026-07-31")
    assert report["evaluation_label"] == "NOT_EVALUABLE"
    assert "after closed_at" in report["evaluation_reason"]


def test_not_due_and_incomparable_data_are_not_evaluable():
    report = build_attribution_report(snapshot(), company_outcome(), closed_at="2026-07-15")
    assert report["evaluation_state"] == "NOT_EVALUABLE"
    assert "review_date" in report["evaluation_reason"]

    outcome = company_outcome()
    outcome["benchmark_series"][1]["date"] = "2026-07-30"
    report = build_attribution_report(snapshot(), outcome, closed_at="2026-07-31")
    assert report["evaluation_label"] == "NOT_EVALUABLE"
    assert "date-comparable" in report["evaluation_reason"]


def test_futures_attribution_uses_daily_mark_to_market_and_separates_margin_basis():
    futures = snapshot(subject_type="futures_contract")
    outcome = {
        "schema_version": "attribution-input.v1",
        "benchmark_id": "000300",
        "contract_code": "RB2610",
        "initial_simulation_capital": 1000,
        "benchmark_series": [
            {"date": "2026-07-01", "value": 100},
            {"date": "2026-07-31", "value": 102},
        ],
        "settlement_ledger": [
            {
                "date": "2026-07-01",
                "settlement_price": 100,
                "position_lots": 1,
                "margin_rate": 0.1,
            },
            {
                "date": "2026-07-31",
                "settlement_price": 105,
                "position_lots": 1,
                "margin_rate": 0.1,
            },
        ],
    }

    report = build_attribution_report(futures, outcome, closed_at="2026-07-31")

    assert report["asset_return"] == pytest.approx(0.05)
    assert report["futures"]["total_simulated_pnl"] == pytest.approx(50)
    assert report["futures"]["max_margin_occupied"] == pytest.approx(105)
    assert report["futures"]["daily_settlement_ledger"][1]["daily_mark_to_market_pnl"] == pytest.approx(50)
    assert report["comparison"]["excess_return_comparable"] is False
    assert report["contributions"]["roll_contribution"] == pytest.approx(0)


def test_futures_missing_numeric_margin_degrades_without_fabricating_ledger():
    futures = snapshot(subject_type="futures_contract")
    futures["decision"]["margin_assumptions"] = {"rate": "locked"}
    outcome = {
        "schema_version": "attribution-input.v1",
        "benchmark_id": "000300",
        "contract_code": "RB2610",
        "benchmark_series": [
            {"date": "2026-07-01", "value": 100},
            {"date": "2026-07-31", "value": 102},
        ],
        "settlement_ledger": [
            {"date": "2026-07-01", "settlement_price": 100, "position_lots": 1},
            {"date": "2026-07-31", "settlement_price": 105, "position_lots": 1},
        ],
    }
    report = build_attribution_report(futures, outcome, closed_at="2026-07-31")
    assert report["evaluation_label"] == "NOT_EVALUABLE"
    assert "margin_rate" in report["evaluation_reason"]
