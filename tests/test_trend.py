import json

import pytest
from pytest import approx

from industry_first_research.trend import RadarTrendError, build_trend_report


def write_snapshot(root, date, items, source="cross"):
    items = [dict(item, as_of=date) for item in items]
    path = root / f"{source}-industry-{date}.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "industry-radar.v1",
                "source": {"provider": source, "as_of": date, "read_only": True},
                "items": items,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def radar_item(name, state, evidence="CROSS_VALIDATED"):
    return {
        "industry_id": "BK1",
        "display_name": name,
        "as_of": "2026-07-19",
        "state": state,
        "evidence_completeness": evidence,
    }


def test_trend_requires_repeated_observations_and_keeps_provenance(tmp_path):
    write_snapshot(tmp_path, "2026-07-17", [radar_item("\u7535\u529b\u884c\u4e1a", "CLEARING")])
    write_snapshot(tmp_path, "2026-07-18", [radar_item("\u7535\u529b", "CLEARING")])
    write_snapshot(tmp_path, "2026-07-19", [radar_item("\u7535\u529b", "CLEARING")])

    report = build_trend_report(tmp_path, source="cross", min_observations=3)

    result = report["items"][0]
    assert report["schema_version"] == "industry-radar-trend.v1"
    assert report["read_only"] is True
    assert report["execution_enabled"] is False
    assert result["trend_state"] == "PERSISTENT_STRENGTH"
    assert result["observation_count"] == 3
    assert result["evidence_completeness"] == "CROSS_VALIDATED_TREND"
    assert result["review_only"] is True


def test_trend_mixed_direction_is_not_promoted(tmp_path):
    write_snapshot(tmp_path, "2026-07-17", [radar_item("\u94f6\u884c", "CLEARING")])
    write_snapshot(tmp_path, "2026-07-18", [radar_item("\u94f6\u884c", "DETERIORATING")])
    write_snapshot(tmp_path, "2026-07-19", [radar_item("\u94f6\u884c", "DETERIORATING")])

    result = build_trend_report(tmp_path)["items"][0]

    assert result["trend_state"] == "PERSISTENT_WEAKNESS"
    assert result["direction"] == "DETERIORATING"
    assert result["direction_ratio"] == approx(2 / 3)


def test_trend_insufficient_data_and_invalid_options(tmp_path):
    write_snapshot(tmp_path, "2026-07-19", [radar_item("\u7535\u529b", "CLEARING")])

    result = build_trend_report(tmp_path)["items"][0]

    assert result["trend_state"] == "INSUFFICIENT"
    assert result["direction"] is None
    with pytest.raises(RadarTrendError):
        build_trend_report(tmp_path, window=0)
