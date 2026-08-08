import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.product_profit_bridge import (
    ProductProfitBridgeError,
    build_product_profit_bridge_report,
    validate_product_profit_bridge_report,
)


def assumption(value, *, status="MODEL_ASSUMPTION", evidence_ids=None, unit=""):
    return {
        "value": value,
        "status": status,
        "evidence_ids": evidence_ids or [],
        "unit": unit,
    }


def bridge_input(**overrides):
    payload = {
        "schema_version": "product-profit-bridge-input.v1",
        "report_id": "bridge-input-001",
        "as_of": "2026-07-23",
        "items": [
            {
                "bridge_id": "bridge-base-001",
                "company_id": "600438",
                "scope_id": "company-scope-600438",
                "product_id": "module-001",
                "product_name": "示例组件",
                "scenario": "BASE_CASE",
                "allocation_method": "PRODUCT_UNIT_ECONOMICS",
                "assumptions": {
                    "volume": assumption({"low": 100, "high": 120}, unit="unit"),
                    "unit_price": assumption(10, unit="CNY/unit"),
                    "unit_cost": assumption(6, unit="CNY/unit"),
                    "direct_expense_per_unit": assumption(1, unit="CNY/unit"),
                    "working_capital_investment": assumption(20, unit="CNY"),
                    "capex": assumption(10, unit="CNY"),
                    "tax_and_interest_outflow": assumption(5, unit="CNY"),
                },
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_bridge_calculates_interval_revenue_profit_and_cashflow_without_collapsing_range():
    report = build_product_profit_bridge_report(bridge_input())

    item = report["items"][0]
    assert report["schema_version"] == "product-profit-bridge.v1"
    assert item["bridge_state"] == "READY"
    assert item["revenue_estimate"] == {"low": 1000.0, "high": 1200.0}
    assert item["gross_profit_estimate"] == {"low": 280.0, "high": 600.0}
    assert item["operating_profit_estimate"] == {"low": 160.0, "high": 500.0}
    assert item["cashflow_contribution_estimate"] == {"low": 125.0, "high": 465.0}
    assert item["scenario"] == "BASE_CASE"
    assert item["base_case_treatment"] == "INCLUDED"
    assert item["scope_status"] == "UNVERIFIED"
    assert item["confidence"] == "MEDIUM"
    assert report["policy"]["product_bridge_is_not_company_forecast"] is True
    assert report["investment_conclusion"] is False


def test_formal_evidence_is_required_for_verified_status():
    payload = bridge_input()
    for name, value in payload["items"][0]["assumptions"].items():
        value["status"] = "VERIFIED"
        value["evidence_ids"] = [f"ev-{name}"]

    item = build_product_profit_bridge_report(payload)["items"][0]
    assert item["evidence_status"] == "VERIFIED"
    assert item["evidence_ids"]


def test_missing_cost_and_cash_outflows_degrade_without_filling_defaults():
    payload = bridge_input()
    assumptions = payload["items"][0]["assumptions"]
    assumptions.pop("unit_cost")
    assumptions.pop("working_capital_investment")
    assumptions.pop("capex")
    assumptions.pop("tax_and_interest_outflow")

    item = build_product_profit_bridge_report(payload)["items"][0]
    assert item["bridge_state"] == "PARTIAL"
    assert item["revenue_estimate"] == {"low": 1000.0, "high": 1200.0}
    assert item["gross_profit_estimate"] is None
    assert item["cashflow_contribution_estimate"] is None
    assert "VARIABLE_COST_MISSING" in item["unknown_items"]
    assert "CASHFLOW_REQUIRES_OPERATING_PROFIT_AND_CASH_OUTFLOWS" in item["unknown_items"]
    assert item["evidence_status"] == "PARTIAL"


def test_conflicting_direct_expense_allocations_are_not_selected():
    payload = bridge_input()
    assumptions = payload["items"][0]["assumptions"]
    assumptions["direct_expense_total"] = assumption(100)

    item = build_product_profit_bridge_report(payload)["items"][0]
    assert item["bridge_state"] == "PARTIAL"
    assert item["direct_expense_assumption"] is None
    assert "DIRECT_EXPENSE_TOTAL_AND_PER_UNIT_CONFLICT" in item["unknown_items"]


def test_not_allocable_product_is_blocked_even_when_numbers_are_present():
    payload = bridge_input()
    payload["items"][0]["allocation_method"] = "NOT_ALLOCABLE"

    item = build_product_profit_bridge_report(payload)["items"][0]
    assert item["bridge_state"] == "BLOCKED"
    assert item["warnings"]
    assert item["investment_conclusion"] is False


def test_unknown_allocation_method_is_partial_not_ready():
    payload = bridge_input()
    payload["items"][0]["allocation_method"] = "UNKNOWN"

    item = build_product_profit_bridge_report(payload)["items"][0]
    assert item["bridge_state"] == "PARTIAL"
    assert any("allocation_method is unknown" in warning for warning in item["warnings"])


def test_invalid_ranges_and_scenarios_are_rejected():
    payload = bridge_input()
    payload["items"][0]["assumptions"]["volume"] = assumption({"low": 120, "high": 100})
    with pytest.raises(ProductProfitBridgeError, match="low cannot exceed high"):
        build_product_profit_bridge_report(payload)

    payload = bridge_input()
    payload["items"][0]["scenario"] = "UNKNOWN"
    with pytest.raises(ProductProfitBridgeError, match="unsupported scenario"):
        build_product_profit_bridge_report(payload)


def test_validation_and_cli_write_an_immutable_bridge(tmp_path, monkeypatch, capsys):
    input_path = tmp_path / "bridge.json"
    input_path.write_text(json.dumps(bridge_input(), ensure_ascii=False), encoding="utf-8")
    output_dir = tmp_path / "bridges"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "product-profit-bridge",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
    )
    main()
    capsys.readouterr()
    report_path = output_dir / "product-profit-bridge-bridge-input-001.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert validate_product_profit_bridge_report(report)["status"] == "VALID"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "product-profit-bridge",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
    )
    main()
    replay = json.loads(capsys.readouterr().out)

    assert replay == report
    assert len(list(output_dir.glob("*.json"))) == 1
