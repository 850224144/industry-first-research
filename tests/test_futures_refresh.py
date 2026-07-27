import json
import sys
from pathlib import Path

import pytest

from industry_first_research.cli import main
from industry_first_research.data_refresh import build_data_source_refresh
from industry_first_research.data_sources import (
    DataSourceHealth,
    DataSourceRouter,
    FreeDataSourcePolicy,
)
from industry_first_research.futures_fundamentals import (
    FUNDAMENTAL_FIELDS,
    build_futures_fundamentals_report,
)
from industry_first_research.futures_identity import identify_futures_object
from industry_first_research.futures_refresh import (
    FuturesRefreshMappingError,
    build_futures_fundamentals_input_from_refresh,
)


FUTURES_FIXTURE = (
    Path(__file__).parent / "fixtures" / "futures" / "fundamentals_complete.json"
)


class FixtureAdapter:
    name = "eastmoney"
    source_type = "fixture_public_data"

    def __init__(self, payload):
        self.payload = payload

    def health_check(self):
        return DataSourceHealth(
            self.name,
            self.source_type,
            True,
            capabilities=("futures",),
            version="fixture-1",
        )

    def fetch(self, _query, as_of):
        return {"source": self.name, "as_of": as_of, "data": self.payload}

    def normalize(self, value):
        return value


def _refresh_report(subject_id="CU"):
    payload = {
        "schema_version": "data-source-refresh-input.v1",
        "refresh_id": "fixture-futures-refresh-cu",
        "as_of": "2026-07-20",
        "queries": [
            {
                "query_id": "cu-spot-benchmark",
                "subject_type": "futures_variety",
                "subject_id": subject_id,
                "source_names": ["eastmoney"],
                "request": {"endpoint": "spot_fixture"},
            },
            {
                "query_id": "cu-inventory",
                "subject_type": "futures_variety",
                "subject_id": subject_id,
                "source_names": ["eastmoney"],
                "request": {"endpoint": "inventory_fixture"},
            },
            {
                "query_id": "cu-exchange-inventory",
                "subject_type": "futures_variety",
                "subject_id": subject_id,
                "source_names": ["eastmoney"],
                "request": {"endpoint": "exchange_inventory_fixture"},
            },
        ],
    }
    router = DataSourceRouter(
        [
            FixtureAdapter(
                [
                    {"date": "2026-07-19", "price": 100, "inventory": 130},
                    {"date": "2026-07-20", "price": 102, "inventory": 120},
                ]
            )
        ],
        FreeDataSourcePolicy(futures_sources=("eastmoney",)),
    )
    return build_data_source_refresh(payload, router)


def _mapping():
    return {
        "schema_version": "futures-fundamentals-refresh-mapping.v1",
        "mapping_id": "cu-refresh-fixture-mapping",
        "variety_id": "CU",
        "as_of": "2026-07-20",
        "field_mappings": [
            {
                "target": "spot_benchmark",
                "query_id": "cu-spot-benchmark",
                "value_path": "data.0",
                "unit": "CNY/ton",
            },
            {
                "target": "inventory_by_location",
                "query_id": "cu-inventory",
                "value_path": "data.0",
                "unit": "ton",
            },
        ],
        "observation_mappings": [
            {
                "target": "spot_price",
                "query_id": "cu-spot-benchmark",
                "rows_path": "data",
                "date_path": "date",
                "value_path": "price",
                "unit": "CNY/ton",
            },
            {
                "target": "inventory",
                "query_id": "cu-inventory",
                "rows_path": "data",
                "date_path": "date",
                "value_path": "inventory",
                "unit": "ton",
            },
        ],
    }


def _identity(variety_id="CU", exchange="SHFE", contract_code="CU2612"):
    return identify_futures_object(
        {
            "schema_version": "futures-object-input.v1",
            "object_type": "futures_contract",
            "as_of": "2026-07-20",
            "exchange": exchange,
            "variety_id": variety_id,
            "variety_name": variety_id,
            "industry_chain": {"upstream": ["上游"], "downstream": ["下游"]},
            "contract": {
                "contract_code": contract_code,
                "contract_month": "2026-12",
                "last_trade_date": "2026-12-15",
                "contract_multiplier": 5,
                "tick_size": 1,
                "settlement_basis": "daily_settlement",
                "rule_version": f"{exchange.lower()}-{variety_id.lower()}-fixture-1",
            },
        }
    )


def _complete_input(variety_id="CU"):
    def verified(value, unit="CNY/ton"):
        return {
            "status": "VERIFIED",
            "value": value,
            "unit": unit,
            "evidence_ids": [f"fixture-{variety_id}-{len(str(value))}"],
            "sources": ["official_exchange"],
            "as_of": ["2026-07-20"],
            "evidence_tiers": ["A"],
        }

    return {
        "schema_version": "futures-fundamentals-input.v1",
        "report_id": f"fixture-{variety_id.lower()}-complete",
        "as_of": "2026-07-20",
        "source": "fixed-regression-fixture",
        "fields": {
            "supply_demand_balance": verified("balanced"),
            "production_and_utilization": verified("utilization 80%"),
            "imports_exports": verified("net imports stable"),
            "inventory_by_location": verified({"social": 100}, "ton"),
            "exchange_inventory_and_warrants": verified({"inventory": 20}, "ton"),
            "spot_benchmark": verified({"price": 100}),
            "production_and_import_cost": verified(
                {"cash_cost": 80, "full_cost": 95}
            ),
            "industry_margin": verified({"margin": 20}),
            "basis_and_calendar_spread": verified("basis stable"),
            "term_structure": verified("backwardation"),
            "seasonality": verified("seasonal demand"),
            "open_interest_and_available_member_positions": verified(
                {"open_interest": 1000}
            ),
            "delivery_rules_and_warrant_expiry": verified(
                {"warrant_expiry": "2026-11-30"}
            ),
        },
        "observations": {
            "spot_price": [{"date": "2026-07-20", "value": 100}],
            "contract_settlement": [
                {"date": "2026-07-20", "value": 98, "contract_code": f"{variety_id}2612"}
            ],
            "basis": [{"date": "2026-07-20", "value": 2}],
            "calendar_spread": [{"date": "2026-07-20", "value": 1}],
            "inventory": [
                {"date": "2026-07-19", "value": 110},
                {"date": "2026-07-20", "value": 100},
            ],
            "exchange_inventory": [{"date": "2026-07-20", "value": 20}],
            "registered_warrants": [{"date": "2026-07-20", "value": 8}],
            "open_interest": [{"date": "2026-07-20", "value": 1000}],
        },
        "price_scenarios": {
            "BEAR": {"low": 70, "high": 90, "evidence_ids": ["bear"]},
            "BASE": {"low": 90, "high": 110, "evidence_ids": ["base"]},
            "BULL": {"low": 110, "high": 135, "evidence_ids": ["bull"]},
        },
        "assessments": {
            "variety_bias": "CONDITIONALLY_TIGHT",
            "contract_relative_value": "NEUTRAL",
            "conditional_conclusion": "only if inventory remains controlled",
            "evidence_ids": ["fixture-assessment"],
        },
    }


def test_refresh_mapping_preserves_lineage_and_never_promotes_raw_values():
    refresh = _refresh_report()
    mapped = build_futures_fundamentals_input_from_refresh(refresh, _mapping())

    assert mapped["schema_version"] == "futures-fundamentals-input.v1"
    assert mapped["fields"]["spot_benchmark"]["status"] == "UNVERIFIED"
    assert mapped["fields"]["spot_benchmark"]["value"]["price"] == 100
    assert mapped["fields"]["spot_benchmark"]["metadata"]["query_id"] == (
        "cu-spot-benchmark"
    )
    assert mapped["observations"]["spot_price"][-1]["value"] == 102
    assert mapped["policy"]["automatic_fact_promotion"] is False
    assert mapped["source_metadata"]["refresh_content_hash"] == refresh["content_hash"]

    report = build_futures_fundamentals_report(_identity(), mapped)
    assert report["status"] != "READY"
    assert report["policy"]["directional_investment_conclusion"] is False


def test_refresh_mapping_rejects_verified_status_and_future_observation():
    mapping = _mapping()
    mapping["field_mappings"][0]["status"] = "VERIFIED"
    with pytest.raises(FuturesRefreshMappingError, match="cannot mark a field VERIFIED"):
        build_futures_fundamentals_input_from_refresh(_refresh_report(), mapping)

    mapping = _mapping()
    mapping["as_of"] = "2026-07-19"
    with pytest.raises(FuturesRefreshMappingError, match="future observation"):
        build_futures_fundamentals_input_from_refresh(_refresh_report(), mapping)

    refresh = _refresh_report(subject_id="RB")
    with pytest.raises(FuturesRefreshMappingError, match="does not match variety_id"):
        build_futures_fundamentals_input_from_refresh(refresh, _mapping())


def test_five_initial_commodity_families_keep_the_same_report_contract():
    identities = [
        ("CU", "SHFE", "CU2612"),
        ("RB", "SHFE", "RB2612"),
        ("SC", "INE", "SC2612"),
        ("M", "DCE", "M2612"),
        ("LC", "GFEX", "LC2612"),
    ]

    for variety_id, exchange, contract_code in identities:
        report = build_futures_fundamentals_report(
            _identity(variety_id, exchange, contract_code),
            _complete_input(variety_id),
        )
        assert report["schema_version"] == "futures-fundamentals-report.v1"
        assert set(FUNDAMENTAL_FIELDS) <= set(report["fields"])
        assert set(report["phases"]) >= {
            "F1_identity_and_rules",
            "F9_adversarial_review",
        }
        assert report["policy"]["execution_enabled"] is False
        assert report["policy"]["directional_investment_conclusion"] is False


def test_checked_in_complete_futures_fixture_is_reusable_across_initial_families():
    fixture = json.loads(FUTURES_FIXTURE.read_text(encoding="utf-8"))
    for variety_id, exchange, contract_code in (
        ("CU", "SHFE", "CU2612"),
        ("RB", "SHFE", "RB2612"),
        ("SC", "INE", "SC2612"),
        ("M", "DCE", "M2612"),
        ("LC", "GFEX", "LC2612"),
    ):
        payload = json.loads(json.dumps(fixture))
        payload["report_id"] = f"fixture-{variety_id.lower()}-checked-in"
        payload["observations"]["contract_settlement"][0]["contract_code"] = contract_code
        report = build_futures_fundamentals_report(
            _identity(variety_id, exchange, contract_code), payload
        )
        assert report["status"] == "READY"
        assert report["fields"]["spot_benchmark"]["status"] == "VERIFIED"


def test_futures_input_from_refresh_cli_writes_immutable_input(tmp_path, monkeypatch, capsys):
    refresh_path = tmp_path / "refresh.json"
    mapping_path = tmp_path / "mapping.json"
    refresh_path.write_text(json.dumps(_refresh_report(), ensure_ascii=False), encoding="utf-8")
    mapping_path.write_text(json.dumps(_mapping(), ensure_ascii=False), encoding="utf-8")
    output_dir = tmp_path / "inputs"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "futures-input-from-refresh",
            "--refresh",
            str(refresh_path),
            "--mapping",
            str(mapping_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    main()
    capsys.readouterr()
    output = output_dir / "cu-refresh-fixture-mapping-CU.json"
    assert output.exists()
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["review_only"] is True
    assert saved["fields"]["spot_benchmark"]["status"] == "UNVERIFIED"
