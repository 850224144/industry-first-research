import json
import sys
from pathlib import Path

import pytest

from industry_first_research.cli import main
from industry_first_research.commodity_adapters import (
    CommodityAdapterDefinition,
    CommodityAdapterError,
    CommodityAdapterRegistry,
    build_commodity_adapter_registry_report,
    build_commodity_adapter_validation_report,
)


REQUIRED_FIELDS = {
    "supply_demand_balance",
    "production_and_utilization",
    "imports_exports",
    "inventory_by_location",
    "exchange_inventory_and_warrants",
    "spot_benchmark",
    "production_and_import_cost",
    "industry_margin",
    "basis_and_calendar_spread",
    "term_structure",
    "seasonality",
    "open_interest_and_available_member_positions",
    "delivery_rules_and_warrant_expiry",
}


def definition(**overrides):
    payload = {
        "schema_version": "commodity-adapter.v1",
        "adapter_id": "copper",
        "display_name": "铜产业链",
        "aliases": ["铜", "沪铜"],
        "exchanges": ["SHFE"],
        "variety_ids": ["CU"],
        "commodity_category": "non_ferrous",
        "quote_unit": "CNY/ton",
        "trading_unit": "ton",
        "spot_benchmarks": [
            {
                "benchmark_id": "shanghai_copper_spot",
                "name": "上海电解铜现货",
                "unit": "CNY/ton",
                "region": "Shanghai",
                "comparability_rule": "same_grade_and_region",
            }
        ],
        "indicator_groups": {
            "supply_demand": ["supply_demand_balance"],
            "production": ["production_and_utilization"],
            "trade": ["imports_exports"],
            "inventory": ["inventory_by_location", "exchange_inventory_and_warrants"],
            "pricing": ["spot_benchmark", "basis_and_calendar_spread", "term_structure"],
            "cost_margin": ["production_and_import_cost", "industry_margin"],
            "structure": ["open_interest_and_available_member_positions"],
            "seasonality": ["seasonality"],
            "position": ["open_interest_and_available_member_positions"],
            "delivery": ["delivery_rules_and_warrant_expiry"],
        },
        "inventory_locations": ["social", "port", "exchange", "registered_warrant"],
        "cost_components": ["cash_cost", "full_cost", "import_parity"],
        "margin_components": ["spot_minus_cash_cost", "spot_minus_full_cost"],
        "seasonality": {"required_drivers": ["construction_demand"]},
        "delivery_rules": {"required_fields": ["delivery_grade", "warrant_expiry"]},
        "scenario_method": {
            "method": "supply_demand_cost_ranges",
            "required_drivers": ["demand", "supply", "inventory"],
            "invalidators": ["demand_collapse"],
        },
        "acceptance_samples": [
            {"sample_id": "ready", "description": "complete package"}
        ],
    }
    payload.update(overrides)
    return payload


def futures_report(status="READY"):
    return {
        "schema_version": "futures-fundamentals-report.v1",
        "report_id": "futures-copper-001",
        "as_of": "2026-07-20",
        "status": status,
        "variety_id": "CU",
        "exchange": "SHFE",
        "contract": {"quote_unit": "CNY/ton"},
        "contract_view": {"status": "READY", "quote_unit": "CNY/ton"},
    }


def fundamentals_input(status="VERIFIED"):
    return {
        "schema_version": "futures-fundamentals-input.v1",
        "report_id": "fundamentals-copper-001",
        "as_of": "2026-07-20",
        "fields": {
            field: {
                "status": status,
                "value": {"benchmark_id": "shanghai_copper_spot"}
                if field == "spot_benchmark"
                else field,
                "evidence_ids": [field],
            }
            for field in REQUIRED_FIELDS
        },
    }


def test_definition_requires_all_shared_futures_fields_and_serializes():
    adapter = CommodityAdapterDefinition.from_mapping(definition())

    assert set(adapter.required_fields) == REQUIRED_FIELDS
    assert adapter.matches("沪铜") is True
    assert adapter.matches("CU") is True
    assert adapter.to_dict()["schema_version"] == "commodity-adapter.v1"


def test_registry_resolves_aliases_and_rejects_ambiguous_identifiers():
    adapter = CommodityAdapterDefinition.from_mapping(definition())
    registry = CommodityAdapterRegistry([adapter])

    assert registry.resolve("copper").adapter_id == "copper"
    assert registry.resolve("CU").display_name == "铜产业链"
    with pytest.raises(CommodityAdapterError, match="ambiguous"):
        registry.register(
            CommodityAdapterDefinition.from_mapping(
                definition(adapter_id="steel", aliases=["铜"])
            )
        )


def test_validation_report_is_configuration_only_until_data_is_supplied():
    adapter = CommodityAdapterDefinition.from_mapping(definition())
    report = build_commodity_adapter_validation_report(adapter)

    assert report["status"] == "CONFIG_READY"
    assert report["policy"]["data_fetched"] is False
    assert report["policy"]["directional_conclusion"] is False


def test_validation_report_checks_variety_units_and_field_coverage():
    adapter = CommodityAdapterDefinition.from_mapping(definition())
    report = build_commodity_adapter_validation_report(
        adapter,
        futures_report=futures_report(),
        fundamentals_input=fundamentals_input(),
    )

    assert report["status"] == "READY"
    assert report["compatibility"]["variety_match"] is True
    assert report["compatibility"]["exchange_match"] is True
    assert report["compatibility"]["quote_unit_match"] is True
    assert report["compatibility"]["spot_benchmark_match"] is True
    assert set(report["field_coverage"]) == REQUIRED_FIELDS


def test_non_ready_futures_or_missing_fields_degrades_adapter_validation():
    adapter = CommodityAdapterDefinition.from_mapping(definition())
    payload = fundamentals_input(status="MISSING")
    report = build_commodity_adapter_validation_report(
        adapter,
        futures_report=futures_report(status="PARTIAL"),
        fundamentals_input=payload,
    )

    assert report["status"] == "PARTIAL"
    assert any(item["type"] == "REQUIRED_FIELD_MISSING" for item in report["findings"])


def test_registry_and_validation_cli_write_json(tmp_path, monkeypatch, capsys):
    config_dir = tmp_path / "commodities"
    config_dir.mkdir()
    (config_dir / "copper.json").write_text(
        json.dumps(definition(), ensure_ascii=False), encoding="utf-8"
    )
    output_dir = tmp_path / "registry-output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "commodity-adapters",
            "--directory",
            str(config_dir),
            "--output-dir",
            str(output_dir),
        ],
    )
    main()
    capsys.readouterr()
    registry_path = output_dir / "commodity-adapter-registry-default.json"
    assert registry_path.exists()
    assert json.loads(registry_path.read_text(encoding="utf-8"))["adapter_count"] == 1

    futures_path = tmp_path / "futures.json"
    fundamentals_path = tmp_path / "fundamentals.json"
    futures_path.write_text(json.dumps(futures_report()), encoding="utf-8")
    fundamentals_path.write_text(json.dumps(fundamentals_input()), encoding="utf-8")
    validation_dir = tmp_path / "validation-output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "commodity-adapter-validate",
            "--directory",
            str(config_dir),
            "--adapter",
            "CU",
            "--futures-report",
            str(futures_path),
            "--fundamentals",
            str(fundamentals_path),
            "--output-dir",
            str(validation_dir),
        ],
    )
    main()
    capsys.readouterr()
    validation_path = validation_dir / "commodity-adapter-validation-copper.json"
    assert validation_path.exists()
    assert json.loads(validation_path.read_text(encoding="utf-8"))["status"] == "READY"


def test_repository_commodity_directory_covers_initial_categories():
    directory = Path(__file__).parents[1] / "config" / "commodities"
    registry = CommodityAdapterRegistry.from_directory(directory)

    assert len(registry.list()) == 5
    assert {
        definition.adapter_id for definition in registry.list()
    } == {"copper", "crude_oil", "lithium_carbonate", "soybean_meal", "steel"}
    assert {
        variety_id
        for definition in registry.list()
        for variety_id in definition.variety_ids
    } == {"BC", "CU", "HC", "LC", "M", "RB", "SC"}
    assert {
        definition.commodity_category for definition in registry.list()
    } == {
        "agriculture",
        "energy_chemical",
        "ferrous",
        "new_energy_material",
        "non_ferrous",
    }


def test_repository_adapters_accept_complete_local_field_packages():
    directory = Path(__file__).parents[1] / "config" / "commodities"
    registry = CommodityAdapterRegistry.from_directory(directory)

    for adapter in registry.list():
        benchmark = adapter.spot_benchmarks[0]
        complete_fields = {
            field: {
                "status": "VERIFIED",
                "value": (
                    {"benchmark_id": benchmark["benchmark_id"]}
                    if field == "spot_benchmark"
                    else {"field": field, "as_of": "2026-07-20"}
                ),
                "evidence_ids": [f"fixture-{adapter.adapter_id}-{field}"],
            }
            for field in adapter.required_fields
        }
        report = build_commodity_adapter_validation_report(
            adapter,
            futures_report={
                "schema_version": "futures-fundamentals-report.v1",
                "report_id": f"fixture-{adapter.adapter_id}",
                "as_of": "2026-07-20",
                "status": "READY",
                "variety_id": adapter.variety_ids[0],
                "exchange": adapter.exchanges[0],
                "contract": {"quote_unit": adapter.quote_unit},
            },
            fundamentals_input={
                "schema_version": "futures-fundamentals-input.v1",
                "report_id": f"fixture-input-{adapter.adapter_id}",
                "as_of": "2026-07-20",
                "fields": complete_fields,
            },
        )

        assert report["status"] == "READY", adapter.adapter_id
        assert report["compatibility"] == {
            "variety_match": True,
            "exchange_match": True,
            "quote_unit_match": True,
            "spot_benchmark_match": True,
        }
        assert set(report["field_coverage"]) == set(adapter.required_fields)
        assert all(
            item["status"] == "VERIFIED"
            for item in report["field_coverage"].values()
        )


def test_definition_rejects_missing_indicator_group_and_bad_schema():
    payload = definition()
    del payload["indicator_groups"]["delivery"]
    with pytest.raises(CommodityAdapterError, match="indicator_groups missing"):
        CommodityAdapterDefinition.from_mapping(payload)
    with pytest.raises(CommodityAdapterError, match="commodity-adapter.v1"):
        CommodityAdapterDefinition.from_mapping({"schema_version": "other"})
