import json
import sys

import pytest

from industry_first_research.futures_fundamentals import (
    FuturesFundamentalsError,
    build_futures_fundamentals_report,
)
from industry_first_research.futures_identity import identify_futures_object
from industry_first_research.cli import main


def identity(object_type="futures_contract"):
    payload = {
        "schema_version": "futures-object-input.v1",
        "object_type": object_type,
        "as_of": "2026-07-20",
        "exchange": "SHFE",
        "variety_id": "CU",
        "variety_name": "沪铜",
        "industry_chain": {
            "upstream": ["铜矿"],
            "downstream": ["电网", "家电"],
        },
        "contract": {
            "contract_code": "CU2612",
            "contract_month": "2026-12",
            "last_trade_date": "2026-12-15",
            "contract_multiplier": 5,
            "tick_size": 10,
            "settlement_basis": "daily_settlement",
            "rule_version": "shfe-cu-rules-2026-01",
        },
    }
    if object_type == "continuous_series":
        payload["continuous_series_rule"] = {
            "main_contract_rule": "highest_open_interest_at_observation_time",
            "roll_rule": "five_sessions_before_last_trade",
            "stitching_rule": "unadjusted",
            "adjustment_rule": "none",
            "components": [{"contract_code": "CU2612", "valid_from": "2026-07-01"}],
        }
        payload["contract"] = {}
    return identify_futures_object(payload)


def field(value, *, evidence_id):
    return {
        "status": "VERIFIED",
        "value": value,
        "unit": "CNY/ton",
        "evidence_ids": [evidence_id],
        "sources": ["official_exchange"],
        "as_of": ["2026-07-20"],
        "evidence_tiers": ["A"],
    }


def complete_input(**overrides):
    fields = {
        "supply_demand_balance": field("demand stable, supply constrained", evidence_id="sd"),
        "production_and_utilization": field("utilization 82%", evidence_id="production"),
        "imports_exports": field("net imports 250", evidence_id="trade"),
        "inventory_by_location": field({"social": 100, "port": 40}, evidence_id="inventory"),
        "exchange_inventory_and_warrants": field({"inventory": 20, "warrants": 8}, evidence_id="warrants"),
        "spot_benchmark": field({"price": 100}, evidence_id="spot"),
        "production_and_import_cost": field(
            {"cash_cost": 80, "full_cost": 95}, evidence_id="cost"
        ),
        "industry_margin": field({"margin": 20}, evidence_id="margin"),
        "basis_and_calendar_spread": field("basis stable, near-far backwardation", evidence_id="basis"),
        "term_structure": field("backwardation", evidence_id="term"),
        "seasonality": field("summer demand season", evidence_id="seasonality"),
        "open_interest_and_available_member_positions": field(
            {"open_interest": 1000}, evidence_id="oi"
        ),
        "delivery_rules_and_warrant_expiry": field(
            {"delivery_month_limit": "2026-12", "warrant_expiry": "2026-11-30"},
            evidence_id="delivery",
        ),
    }
    observations = {
        "spot_price": [{"date": "2026-07-19", "value": 100}],
        "contract_settlement": [
            {"date": "2026-07-19", "value": 98, "contract_code": "CU2612"}
        ],
        "basis": [{"date": "2026-07-19", "value": 2}],
        "calendar_spread": [{"date": "2026-07-19", "value": 1}],
        "inventory": [
            {"date": "2026-07-12", "value": 130},
            {"date": "2026-07-19", "value": 100},
        ],
        "exchange_inventory": [{"date": "2026-07-19", "value": 20}],
        "registered_warrants": [
            {"date": "2026-07-12", "value": 10},
            {"date": "2026-07-19", "value": 8},
        ],
        "open_interest": [{"date": "2026-07-19", "value": 1000}],
    }
    payload = {
        "schema_version": "futures-fundamentals-input.v1",
        "report_id": "cu-2026-07-20",
        "as_of": "2026-07-20",
        "source": "manual-after-fallback",
        "fields": fields,
        "observations": observations,
        "price_scenarios": {
            scenario: {
                "low": low,
                "high": high,
                "drivers": [f"{scenario.lower()} driver"],
                "invalidators": ["demand shock"],
                "evidence_ids": [f"scenario-{scenario.lower()}"],
                "as_of": "2026-07-20",
            }
            for scenario, low, high in (
                ("BEAR", 70, 90),
                ("BASE", 90, 110),
                ("BULL", 110, 135),
            )
        },
        "assessments": {
            "variety_bias": "CONDITIONALLY_TIGHT",
            "contract_relative_value": "NEUTRAL_TO_POSITIVE",
            "conditional_conclusion": "only if inventory continues to fall",
            "evidence_ids": ["sd", "inventory", "basis"],
        },
    }
    payload.update(overrides)
    return payload


def test_complete_contract_report_keeps_four_layers_separate_and_derives_metrics():
    report = build_futures_fundamentals_report(identity(), complete_input())

    assert report["schema_version"] == "futures-fundamentals-report.v1"
    assert report["status"] == "READY"
    assert report["variety_view"]["status"] == "READY"
    assert report["contract_view"]["status"] == "READY"
    assert report["contract_view"]["latest"]["basis"]["value"] == 2
    assert report["derived_metrics"]["spot_minus_full_cost"]["value"] == 5
    assert report["simulation_view"]["status"] == "ELIGIBLE_FOR_USER_REVIEW"
    assert report["simulation_view"]["decision_snapshot_created"] is False
    assert report["policy"]["intrinsic_value_generated"] is False


def test_missing_spot_inventory_and_warrants_degrade_without_direction():
    payload = complete_input(
        fields={
            "supply_demand_balance": field("unknown", evidence_id="sd"),
        },
        observations={},
        price_scenarios={},
    )
    report = build_futures_fundamentals_report(identity(), payload)

    assert report["status"] == "INSUFFICIENT"
    assert report["variety_view"]["status"] == "INSUFFICIENT"
    assert report["contract_view"]["status"] == "INSUFFICIENT"
    assert report["simulation_view"]["direction"] == "NOT_ASSESSED"
    assert "CONTRACT_VIEW_INSUFFICIENT" in report["simulation_view"]["blockers"]
    assert report["price_scenarios"]["intrinsic_value"] is None


def test_continuous_series_is_research_only_and_cannot_become_simulation_ready():
    report = build_futures_fundamentals_report(
        identity("continuous_series"), complete_input()
    )

    assert report["object_type"] == "continuous_series"
    assert report["contract_view"]["status"] == "NOT_APPLICABLE"
    assert report["simulation_view"]["status"] == "INSUFFICIENT"
    assert "SPECIFIC_CONTRACT_REQUIRED" in report["simulation_view"]["blockers"]
    assert report["phases"]["F9_adversarial_review"]["findings"][0]["type"] == (
        "RESEARCH_ONLY_OBJECT"
    )


def test_future_evidence_is_rejected_instead_of_backfilled():
    payload = complete_input()
    payload["observations"]["spot_price"].append(
        {"date": "2026-07-21", "value": 101}
    )
    with pytest.raises(FuturesFundamentalsError, match="future observation"):
        build_futures_fundamentals_report(identity(), payload)


def test_futures_fundamentals_cli_writes_report(tmp_path, monkeypatch, capsys):
    identity_path = tmp_path / "identity.json"
    input_path = tmp_path / "input.json"
    identity_path.write_text(json.dumps(identity()), encoding="utf-8")
    input_path.write_text(json.dumps(complete_input()), encoding="utf-8")
    output_dir = tmp_path / "reports"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "futures-fundamentals",
            "--identity",
            str(identity_path),
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    main()
    capsys.readouterr()
    report_path = output_dir / "futures-fundamentals-cu-2026-07-20.json"
    assert report_path.exists()
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "READY"
