import pytest

from industry_first_research.market_structure import (
    MarketStructureError,
    build_market_structure_report,
)


def bars(count=25, *, start=100.0, step=1.0):
    result = []
    for index in range(count):
        close = start + index * step
        result.append(
            {
                "timestamp": f"2026-07-{index + 1:02d}T15:00:00+08:00",
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1000 + index,
            }
        )
    return result


def input_report(*, subject_type="listed_company", timeframes=None):
    return {
        "schema_version": "market-structure-input.v1",
        "subject_type": subject_type,
        "subject_id": "600438",
        "display_name": "测试标的",
        "as_of": "2026-07-25T15:00:00+08:00",
        "price_series_id": "600438-daily-adjusted",
        "adjustment": "qfq",
        "timeframes": timeframes or {"daily": bars()},
    }


def test_market_structure_is_confirmed_until_as_of_and_has_no_signal():
    report = build_market_structure_report(input_report())

    assert report["schema_version"] == "market-structure-snapshot.v1"
    assert report["implementation"] == "local_deterministic"
    assert report["confirmation"] == "CONFIRMED_UNTIL_AS_OF"
    assert report["timeframes"]["daily"]["state"] == "UPTREND"
    assert report["timeframes"]["daily"]["signal"] is None
    assert report["policy"]["automatic_order_included"] is False


def test_short_timeframe_is_unconfirmed_and_interpretation_is_degraded():
    report = build_market_structure_report(
        input_report(timeframes={"60m": bars(5, step=-1.0)})
    )

    item = report["timeframes"]["60m"]
    assert report["confirmation"] == "UNCONFIRMED"
    assert item["state"] == "INSUFFICIENT_DATA"
    assert item["confirmation"] == "UNCONFIRMED"
    assert "数据不足" in report["interpretation"]


def test_future_bar_and_non_ascending_bars_are_rejected():
    future = input_report(timeframes={"daily": bars(2)})
    future["as_of"] = "2026-07-01T15:00:00+08:00"
    with pytest.raises(MarketStructureError, match="future bar"):
        build_market_structure_report(future)

    duplicate = input_report(timeframes={"daily": bars(2)})
    duplicate["timeframes"]["daily"][1]["timestamp"] = duplicate["timeframes"]["daily"][0]["timestamp"]
    with pytest.raises(MarketStructureError, match="duplicate"):
        build_market_structure_report(duplicate)


def test_continuous_series_requires_locked_rule_and_wrong_schema_is_rejected():
    with pytest.raises(MarketStructureError, match="continuous_series_rule"):
        build_market_structure_report(input_report(subject_type="continuous_series"))

    with pytest.raises(MarketStructureError, match="market-structure-input.v1"):
        build_market_structure_report({"schema_version": "other"})
