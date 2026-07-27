import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.futures_company_exposure import (
    FuturesCompanyExposureError,
    build_futures_company_exposure_report,
)


def futures_report(status="READY"):
    return {
        "schema_version": "futures-fundamentals-report.v1",
        "report_id": "futures-fundamentals-cu-2026-07-20",
        "as_of": "2026-07-20",
        "status": status,
        "variety_id": "CU",
        "variety_name": "沪铜",
        "object_type": "futures_contract",
        "exchange": "SHFE",
        "derived_metrics": {
            "spot_latest": {"date": "2026-07-19", "value": 100},
            "contract_settlement_latest": {"date": "2026-07-19", "value": 98},
            "basis_latest": {"date": "2026-07-19", "value": 2},
            "inventory_latest": {"date": "2026-07-19", "value": 100},
        },
        "price_scenarios": {
            "status": "READY",
            "scenarios": {
                "BEAR": {"range": {"low": 70, "high": 90}},
                "BASE": {"range": {"low": 90, "high": 110}},
                "BULL": {"range": {"low": 110, "high": 130}},
            },
        },
        "contract_view": {"status": "READY"},
        "evidence_gaps": [],
    }


def product_company(profile_status="READY", product_status="VERIFIED"):
    return {
        "company_id": "600000",
        "display_name": "示例铜业",
        "company_scope_status": "VERIFIED",
        "profile_status": profile_status,
        "products": [
            {
                "product_id": "copper-cathode",
                "product_name": "电解铜",
                "status": product_status,
                "evidence_ids": ["product-copper"],
                "sources": ["official_annual_report"],
                "as_of": ["2026-07-19"],
            }
        ],
        "evidence_ids": ["company-scope"],
    }


def exposure_input(**overrides):
    payload = {
        "schema_version": "futures-company-exposure-input.v1",
        "report_id": "cu-company-exposures-2026-07-20",
        "as_of": "2026-07-20",
        "variety_id": "CU",
        "source": "manual-after-company-research",
        "companies": [product_company()],
        "exposures": [
            {
                "exposure_id": "exp-001",
                "variety_id": "CU",
                "company_id": "600000",
                "product_id": "copper-cathode",
                "product_name": "电解铜",
                "exposure_role": "PRODUCER",
                "revenue_or_cost_link": "REVENUE",
                "pricing_lag": {"days": 30, "basis": "monthly_average", "status": "VERIFIED"},
                "inventory_effect": {"owned_inventory": 1000, "status": "VERIFIED"},
                "hedging_policy": {"hedge_ratio": 0.4, "status": "VERIFIED"},
                "transmission_formula": {
                    "volume": 100,
                    "volume_unit": "ton_per_period",
                    "revenue_sensitivity": 1,
                    "cost_sensitivity": 0,
                    "pass_through_ratio": 1,
                    "hedge_ratio": 0.4,
                    "cash_conversion_ratio": 0.8,
                    "impact_unit": "CNY_per_period",
                },
                "source_evidence_ids": ["exposure-role", "pricing-policy"],
                "sources": ["official_annual_report"],
                "as_of": ["2026-07-19"],
                "status": "VERIFIED",
                "confidence": "HIGH",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_producer_exposure_maps_product_and_calculates_illustrative_scenarios():
    report = build_futures_company_exposure_report(
        futures_report(), exposure_input()
    )

    assert report["schema_version"] == "commodity-company-exposure-report.v1"
    assert report["status"] == "READY"
    item = report["items"][0]
    assert item["product_match"] == "EXACT"
    assert item["directional_reading"] == "PRICE_UP_REVENUE_POSITIVE"
    assert item["mapping_state"] == "READY"
    assert item["transmission_bridge"]["status"] == "READY"
    assert item["transmission_bridge"]["scenario_impacts"]["BULL"][
        "unhedged_high_impact"
    ] == 3200
    assert item["transmission_bridge"]["scenario_impacts"]["BULL"][
        "after_hedge_high_impact"
    ] == 1920
    assert item["transmission_bridge"]["profit_forecast"] is None


def test_consumer_and_processor_keep_role_and_spread_logic_separate():
    payload = exposure_input()
    payload["companies"][0]["products"][0]["product_name"] = "铜加工品"
    exposure = payload["exposures"][0]
    exposure.update(
        {
            "product_id": "copper-products",
            "product_name": "铜加工品",
            "exposure_role": "PROCESSOR",
            "revenue_or_cost_link": "BOTH",
        }
    )
    item = build_futures_company_exposure_report(futures_report(), payload)["items"][0]

    assert item["directional_reading"] == "MIXED_SPREAD_DEPENDENT"


def test_industry_label_without_explicit_product_does_not_create_exposure():
    payload = exposure_input()
    payload["companies"][0]["products"] = []
    payload["exposures"][0]["product_id"] = "copper-cathode"
    item = build_futures_company_exposure_report(futures_report(), payload)["items"][0]

    assert item["product_match"] == "NOT_MATCHED"
    assert item["mapping_state"] == "INSUFFICIENT"
    assert "PRODUCT_NOT_EXPLICITLY_VERIFIED" in item["blockers"]
    assert item["directional_reading"] == "NOT_ASSESSED"
    assert item["declared_directional_reading"] == "PRICE_UP_REVENUE_POSITIVE"
    assert item["transmission_bridge"]["scenario_impacts"] == {}
    assert item["investment_conclusion"] is False


def test_incomplete_futures_report_or_missing_transmission_inputs_degrades():
    payload = exposure_input()
    payload["exposures"][0]["transmission_formula"] = {}
    report = build_futures_company_exposure_report(
        futures_report(status="INSUFFICIENT"), payload
    )

    item = report["items"][0]
    assert report["status"] == "PARTIAL"
    assert item["mapping_state"] == "PARTIAL"
    assert item["transmission_bridge"]["status"] == "PARTIAL"
    assert "volume" in item["transmission_bridge"]["unknowns"]


def test_future_exposure_evidence_is_rejected():
    payload = exposure_input()
    payload["exposures"][0]["as_of"] = ["2026-07-21"]
    with pytest.raises(FuturesCompanyExposureError, match="future data"):
        build_futures_company_exposure_report(futures_report(), payload)


def test_existing_company_product_profile_can_supply_product_scope():
    profile = {
        "schema_version": "company-product-profile.v1",
        "report_id": "company-product-profile-001",
        "as_of": "2026-07-19",
        "items": [
            {
                "company_id": "600000",
                "display_name": "示例铜业",
                "scope_state": "VERIFIED",
                "product_profile_state": "READY",
                "evidence_ids": ["company-scope"],
                "fields": {
                    "product_list": {
                        "status": "VERIFIED",
                        "values": [
                            {
                                "product_id": "copper-cathode",
                                "product_name": "电解铜",
                                "status": "VERIFIED",
                                "evidence_ids": ["product-copper"],
                                "sources": ["official_annual_report"],
                                "as_of": ["2026-07-19"],
                            }
                        ],
                    }
                },
            }
        ],
    }
    payload = exposure_input(companies=None)
    report = build_futures_company_exposure_report(
        futures_report(), payload, product_profile_report=profile
    )

    assert report["input_product_profile_id"] == "company-product-profile-001"
    assert report["items"][0]["product_match"] == "EXACT"
    assert report["items"][0]["mapping_state"] == "READY"


def test_exposure_cli_writes_report(tmp_path, monkeypatch, capsys):
    futures_path = tmp_path / "futures.json"
    input_path = tmp_path / "exposures.json"
    futures_path.write_text(json.dumps(futures_report()), encoding="utf-8")
    input_path.write_text(json.dumps(exposure_input()), encoding="utf-8")
    output_dir = tmp_path / "reports"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "futures-company-exposure",
            "--futures-report",
            str(futures_path),
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
    )
    main()
    capsys.readouterr()

    report_path = output_dir / (
        "commodity-company-exposure-cu-company-exposures-2026-07-20.json"
    )
    assert report_path.exists()
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "READY"
