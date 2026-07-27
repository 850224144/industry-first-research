import pytest

from industry_first_research.market_data import (
    MarketDataError,
    build_market_data_snapshot,
    extract_market_data_series,
    validate_market_data_snapshot,
)
from industry_first_research.market_registry import MarketRegistry


def market_input(subject_type="listed_company"):
    return {
        "schema_version": "market-data-input.v1",
        "subject_type": subject_type,
        "subject_id": "600438.SH" if subject_type == "listed_company" else "IF2409",
        "display_name": "测试标的",
        "market": "SSE" if subject_type == "listed_company" else "CFFEX",
        "currency": "CNY",
        "source": "baostock",
        "source_version": "0.8.8",
        "timeframe": "daily",
        "adjustment": "QFQ",
        "trading_calendar_version": "SSE-2026-v1",
        "research_as_of": "2026-07-03T15:00:00+08:00",
        "last_market_at": "2026-07-03T15:00:00+08:00",
        "raw_file_uri": "data/raw/market-001.json",
        "content_hash": "raw-hash-001",
        "missing_data_status": "COMPLETE",
        "corporate_action_status": "APPLIED",
        "series": {
            "daily": [
                {"timestamp": "2026-07-01T15:00:00+08:00", "close": 10, "volume": 100},
                {"timestamp": "2026-07-02T15:00:00+08:00", "close": 11, "volume": 110},
                {"timestamp": "2026-07-03T15:00:00+08:00", "close": 12, "volume": 120},
            ]
        },
    }


def test_market_data_locks_lineage_and_normalizes_rows():
    report = build_market_data_snapshot(market_input())
    assert report["schema_version"] == "market-data-snapshot.v1"
    assert report["row_count"] == 3
    assert extract_market_data_series(report)[-1]["close"] == 12
    assert validate_market_data_snapshot(report)["status"] == "VALID"


def test_market_data_requires_segments_for_continuous_series():
    payload = market_input("continuous_series")
    payload["subject_id"] = "RB.CONT"
    with pytest.raises(MarketDataError, match="continuous_series_rule"):
        build_market_data_snapshot(payload)
    payload["continuous_series_rule"] = {
        "rule_version": "main-v1",
        "selection_rule": "highest_open_interest_as_of",
        "roll_rule": "before_delivery",
        "adjustment_rule": "backward_ratio",
    }
    payload["segments"] = [
        {
            "contract_id": "RB2410",
            "start": "2026-07-01T00:00:00+08:00",
            "end": "2026-07-03T00:00:00+08:00",
            "selection_evidence_ids": ["ev-roll-1"],
        },
        {
            "contract_id": "RB2501",
            "start": "2026-07-03T00:00:00+08:00",
            "end": "2026-07-03T15:00:00+08:00",
            "selection_evidence_ids": ["ev-roll-2"],
        },
    ]
    report = build_market_data_snapshot(payload)
    assert report["policy"]["continuous_series_not_tradeable"] is True
    assert len(report["segments"]) == 2


def test_market_data_rejects_future_rows_and_invalid_hash():
    payload = market_input()
    payload["series"]["daily"].append(
        {"timestamp": "2026-07-04T15:00:00+08:00", "close": 13}
    )
    with pytest.raises(MarketDataError, match="future row"):
        build_market_data_snapshot(payload)
    report = build_market_data_snapshot(market_input())
    report["series"]["daily"][0]["close"] = 99
    assert validate_market_data_snapshot(report)["status"] == "INVALID"


def test_market_data_snapshot_can_feed_attribution_and_portfolio_replay(tmp_path):
    from industry_first_research.attribution import build_attribution_report
    from industry_first_research.simulation_portfolio import replay_simulation_portfolio

    asset = build_market_data_snapshot(market_input())
    benchmark_payload = market_input()
    benchmark_payload.update({"subject_type": "benchmark", "subject_id": "000300", "market": "INDEX"})
    benchmark_payload["series"] = {
        "daily": [
            {"timestamp": "2026-07-01T15:00:00+08:00", "value": 100},
            {"timestamp": "2026-07-02T15:00:00+08:00", "value": 101},
            {"timestamp": "2026-07-03T15:00:00+08:00", "value": 102},
        ]
    }
    benchmark_payload["research_as_of"] = "2026-07-03T15:00:00+08:00"
    benchmark_payload["last_market_at"] = benchmark_payload["research_as_of"]
    benchmark = build_market_data_snapshot(benchmark_payload)
    decision = {
        "schema_version": "decision-snapshot.v1",
        "snapshot_id": "decision-snapshot-market-data",
        "status": "LOCKED",
        "subject_type": "listed_company",
        "subject_id": "600438.SH",
        "decision": {
            "subject_id": "600438.SH",
            "decision_at": "2026-07-01",
            "review_date": "2026-07-02",
            "benchmark": {"name": "000300", "series_id": "000300", "locked": True},
        },
        "immutable": True,
        "simulation_only": True,
        "execution_enabled": False,
    }
    outcome = {"schema_version": "attribution-input.v1", "benchmark_id": "000300"}
    report = build_attribution_report(
        decision,
        outcome,
        closed_at="2026-07-03",
        asset_market_data_snapshot=asset,
        benchmark_market_data_snapshot=benchmark,
    )
    assert report["methodology"]["asset_market_data_snapshot_id"] == asset["snapshot_id"]
    assert report["methodology"]["benchmark_market_data_snapshot_id"] == benchmark["snapshot_id"]


def test_market_data_locks_and_validates_registry_reference():
    registry = MarketRegistry(
        [
            {
                "market_id": "SSE",
                "display_name": "上海证券交易所",
                "asset_class": "EQUITY",
                "currency": "CNY",
                "timezone": "Asia/Shanghai",
                "calendar_version": "SSE-2026-v1",
            }
        ],
        registry_id="test-markets",
        version="v1",
    )
    report = build_market_data_snapshot(market_input(), market_registry=registry)
    assert report["market_registry_id"] == "test-markets"
    assert report["policy"]["market_registry_locked"] is True
    assert validate_market_data_snapshot(report)["status"] == "VALID"
    report["market_reference"]["market"]["currency"] = "USD"
    assert validate_market_data_snapshot(report)["status"] == "INVALID"


def test_market_data_rejects_registry_market_mismatch():
    registry = MarketRegistry(
        [
            {
                "market_id": "SZSE",
                "display_name": "深圳证券交易所",
                "asset_class": "EQUITY",
                "currency": "CNY",
                "timezone": "Asia/Shanghai",
                "calendar_version": "SZSE-2026-v1",
            }
        ],
        registry_id="test-markets",
        version="v1",
    )
    with pytest.raises(MarketDataError, match="market is not configured"):
        build_market_data_snapshot(market_input(), market_registry=registry)


def test_market_data_validation_can_check_registry_hash():
    registry = MarketRegistry(
        [
            {
                "market_id": "SSE",
                "display_name": "上海证券交易所",
                "asset_class": "EQUITY",
                "currency": "CNY",
                "timezone": "Asia/Shanghai",
                "calendar_version": "SSE-2026-v1",
            }
        ],
        registry_id="test-markets",
        version="v1",
    )
    snapshot = build_market_data_snapshot(market_input(), market_registry=registry)
    assert validate_market_data_snapshot(snapshot, market_registry=registry)["status"] == "VALID"
    changed = MarketRegistry(
        [
            {
                "market_id": "SSE",
                "display_name": "上海证券交易所",
                "asset_class": "EQUITY",
                "currency": "CNY",
                "timezone": "Asia/Shanghai",
                "calendar_version": "SSE-2027-v1",
            }
        ],
        registry_id="test-markets",
        version="v2",
    )
    assert validate_market_data_snapshot(snapshot, market_registry=changed)["status"] == "INVALID"
