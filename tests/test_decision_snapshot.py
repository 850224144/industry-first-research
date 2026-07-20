import pytest

from industry_first_research.decision_snapshot import (
    DecisionSnapshotError,
    build_decision_snapshot,
)


def research_report(*, state="REVIEWABLE", candidate_state="WATCH"):
    return {
        "schema_version": "company-research-report.v1",
        "report_id": "research-report-001",
        "items": [
            {
                "company_id": "300317",
                "display_name": "珈伟新能",
                "candidate_state": candidate_state,
                "report_state": state,
            }
        ],
    }


def common_decision(subject_type="listed_company"):
    decision = {
        "company_id": "300317",
        "display_name": "珈伟新能",
        "subject_type": subject_type,
        "subject_id": "300317",
        "market_or_exchange": "深圳证券交易所",
        "decision_at": "2026-07-19T15:00:00+08:00",
        "data_cutoff": "2026-07-19",
        "action_type": "OBSERVE",
        "direction": "OBSERVE",
        "price": 10.0,
        "quantity": 0,
        "position_ratio": 0,
        "capital_assumptions": {"currency": "CNY", "simulation_capital": 100000},
        "value_or_price_range": {"bear": "待确认", "base": "待确认", "bull": "待确认"},
        "expected_horizon": "6 months",
        "reasons": ["evidence review"],
        "industry_judgment": {"state": "review"},
        "company_judgment": {"state": "review"},
        "survival_judgment": {"state": "review"},
        "fundamental_assumptions": ["cash flow remains observable"],
        "market_structure": {"state": "range", "source": "market-001"},
        "risks": ["evidence may expire"],
        "triggers": ["new verified filing"],
        "invalidators": ["scope conflict"],
        "review_date": "2026-08-19",
        "benchmark": {"name": "cash", "locked": True},
        "covered_factors": ["evidence"],
        "excluded_factors": ["execution"],
    }
    if subject_type == "futures_contract":
        decision.update(
            {
                "subject_id": "RB2610",
                "market_or_exchange": "SHFE",
                "action_type": "OBSERVE",
                "direction": "NEUTRAL",
                "contract_code": "RB2610",
                "contract_month": "2026-10",
                "last_trade_date": "2026-10-15",
                "contract_multiplier": 10,
                "settlement_basis": "daily_settlement",
                "margin_assumptions": {"rate": "locked"},
                "fee_assumptions": {"fee": "locked"},
                "slippage_assumptions": {"ticks": 1},
                "roll_rule": "none",
                "expiry_handling": "close_before_delivery",
                "delivery_month_limit": "no_entry",
                "price_limit_rule": "exchange_rule_v1",
                "trading_session": "day_and_night",
                "cross_contract_continuation": False,
            }
        )
    return decision


def test_locked_company_snapshot_requires_confirmation_and_is_simulation_only():
    with pytest.raises(DecisionSnapshotError, match="user_confirmed"):
        build_decision_snapshot(
            research_report(), common_decision(), user_confirmed=False
        )

    snapshot = build_decision_snapshot(
        research_report(), common_decision(), user_confirmed=True
    )
    assert snapshot["schema_version"] == "decision-snapshot.v1"
    assert snapshot["status"] == "LOCKED"
    assert snapshot["immutable"] is True
    assert snapshot["simulation_only"] is True
    assert snapshot["order_sent"] is False
    assert snapshot["execution_enabled"] is False


def test_non_reviewable_report_cannot_create_snapshot():
    with pytest.raises(DecisionSnapshotError, match="REVIEWABLE"):
        build_decision_snapshot(
            research_report(state="REVIEW"), common_decision(), user_confirmed=True
        )


def test_futures_snapshot_requires_specific_contract_and_complete_fields():
    snapshot = build_decision_snapshot(
        research_report(), common_decision("futures_contract"), user_confirmed=True
    )
    assert snapshot["subject_type"] == "futures_contract"
    assert snapshot["decision"]["contract_code"] == "RB2610"
    assert snapshot["policy"]["continuous_series_not_tradeable"] is True

    continuous = common_decision("futures_contract")
    continuous["contract_code"] = "CONTINUOUS"
    with pytest.raises(DecisionSnapshotError, match="specific contract"):
        build_decision_snapshot(
            research_report(), continuous, user_confirmed=True
        )


def test_revision_requires_reason_and_rejected_candidate_is_blocked():
    decision = common_decision()
    decision["supersedes_snapshot_id"] = "decision-snapshot-old"
    with pytest.raises(DecisionSnapshotError, match="revision_reason"):
        build_decision_snapshot(research_report(), decision, user_confirmed=True)

    with pytest.raises(DecisionSnapshotError, match="cannot create"):
        build_decision_snapshot(
            research_report(candidate_state="INSUFFICIENT"),
            common_decision(),
            user_confirmed=True,
        )
