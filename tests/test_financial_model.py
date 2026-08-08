import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.financial_model import (
    FinancialModelError,
    build_financial_model_report,
    validate_financial_model_report,
)


FACT_VALUES = {
    "revenue": 1000,
    "gross_profit": 400,
    "operating_profit": 200,
    "net_profit": 150,
    "ebitda": 250,
    "operating_cashflow": 220,
    "maintenance_capex": 50,
    "expansion_capex": 30,
    "cash": 500,
    "debt": 300,
    "current_assets": 800,
    "current_liabilities": 400,
    "receivables": 200,
    "inventory": 150,
    "shares_outstanding": 100,
    "current_price": 10,
    "book_equity": 600,
}


def fact(value, evidence_id=None, **extra):
    payload = {"value": value, "status": "MODEL_ASSUMPTION"}
    if evidence_id:
        payload.update(status="VERIFIED", evidence_ids=[evidence_id])
    payload.update(extra)
    return payload


def model_input(**overrides):
    payload = {
        "schema_version": "financial-model-input.v1",
        "report_id": "financial-input-001",
        "as_of": "2026-07-23",
        "items": [
            {
                "model_item_id": "financial-item-001",
                "company_id": "600438",
                "scope_id": "company-scope-600438",
                "facts": {name: fact(value) for name, value in FACT_VALUES.items()},
                "stress_tests": [
                    {
                        "scenario": "LOW_DEMAND_LONGER",
                        "cash": 500,
                        "monthly_cash_burn": 10,
                        "debt_due": 100,
                        "minimum_cash_balance": 100,
                        "horizon_months": 36,
                    }
                ],
                "valuation_scenarios": [
                    {"scenario": "BEAR", "valuation_method": "PE", "forecast_net_profit": 100, "multiple": 8},
                    {"scenario": "BASE", "valuation_method": "PE", "forecast_net_profit": 150, "multiple": 12},
                    {"scenario": "BULL", "valuation_method": "PE", "forecast_net_profit": 220, "multiple": 15},
                ],
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_financial_model_calculates_ratios_cashflow_stress_and_value_observations():
    report = build_financial_model_report(model_input())

    item = report["items"][0]
    assert report["schema_version"] == "financial-model.v1"
    assert item["model_state"] == "READY"
    assert item["financial_metrics"]["gross_margin"] == 0.4
    assert item["financial_metrics"]["free_cash_flow_after_maintenance_capex"] == 170.0
    assert item["cashflow_bridge"]["free_cash_flow_after_all_capex"] == 140.0
    assert item["stress_tests"][0]["cash_runway_months"] == 40.0
    assert item["stress_tests"][0]["debt_gap"] == 0.0
    assert item["stress_tests"][0]["survival_dependency"] == "SELF_FUNDED"
    assert item["valuation_scenarios"][1]["equity_value_per_share_observation"] == 18.0
    assert item["valuation_scenarios"][1]["target_price_generated"] is False
    assert item["numeric_valuation_included"] is False
    assert report["investment_conclusion"] is False


def test_missing_cashflow_input_is_not_defaulted():
    payload = model_input()
    payload["items"][0]["facts"].pop("maintenance_capex")
    payload["items"][0]["facts"].pop("expansion_capex")

    item = build_financial_model_report(payload)["items"][0]
    assert item["model_state"] == "PARTIAL"
    assert item["cashflow_bridge"]["status"] == "NOT_CALCULATED"
    assert item["cashflow_bridge"]["free_cash_flow_after_maintenance_capex"] is None
    assert "maintenance_capex_or_operating_cashflow_missing" in item["unknowns"]


def test_future_fact_is_excluded_and_zero_denominator_degrades_ratio():
    payload = model_input()
    payload["items"][0]["facts"]["revenue"]["as_of"] = "2026-07-24"
    payload["items"][0]["facts"]["revenue"]["value"] = 0
    payload["items"][0]["facts"]["net_profit"]["value"] = 0

    item = build_financial_model_report(payload)["items"][0]
    assert item["facts"]["revenue"]["status"] == "EXCLUDED_FUTURE"
    assert item["financial_metrics"]["gross_margin"] is None
    assert item["model_state"] == "PARTIAL"
    assert any("future facts" in warning for warning in item["warnings"])


def test_scope_mismatch_blocks_financial_model():
    scope_report = {
        "schema_version": "company-scope.v1",
        "scope_id": "company-scope-other",
        "company_id": "600438",
        "researchability_state": "READY",
    }
    item = build_financial_model_report(
        model_input(),
        company_scope_reports={"600438": scope_report},
    )["items"][0]
    assert item["model_state"] == "BLOCKED"
    assert item["scope_status"] == "CONFLICTING"


def test_invalid_scenario_and_cli_validation(tmp_path, monkeypatch, capsys):
    payload = model_input()
    payload["items"][0]["valuation_scenarios"][0]["valuation_method"] = "UNKNOWN"
    with pytest.raises(FinancialModelError, match="unsupported valuation_method"):
        build_financial_model_report(payload)

    input_path = tmp_path / "financial.json"
    input_path.write_text(json.dumps(model_input(), ensure_ascii=False), encoding="utf-8")
    output_dir = tmp_path / "models"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "financial-model",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
    )
    main()
    capsys.readouterr()
    report_path = output_dir / "financial-model-financial-input-001.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert validate_financial_model_report(report)["status"] == "VALID"
