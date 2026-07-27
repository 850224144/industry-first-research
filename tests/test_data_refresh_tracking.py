import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.data_refresh import build_data_source_refresh
from industry_first_research.data_refresh_tracking import (
    DataRefreshTrackingError,
    build_data_refresh_tracking_report,
    validate_data_refresh_tracking_report,
)
from industry_first_research.data_sources import (
    DataSourceHealth,
    DataSourceRouter,
    FreeDataSourcePolicy,
)


class Adapter:
    name = "eastmoney"
    source_type = "test"

    def __init__(self, value):
        self.value = value

    def health_check(self):
        return DataSourceHealth(self.name, self.source_type, True, capabilities=("cn_stock",))

    def fetch(self, _query, as_of):
        return {
            "source": self.name,
            "source_type": self.source_type,
            "retrieved_at": f"{as_of}T09:00:00+08:00",
            "data": [{"close": self.value}],
        }

    def normalize(self, value):
        return value


def refresh(as_of, value):
    router = DataSourceRouter(
        [Adapter(value)],
        FreeDataSourcePolicy(listed_company_sources=("eastmoney",)),
    )
    return build_data_source_refresh(
        {
            "schema_version": "data-source-refresh-input.v1",
            "refresh_id": f"refresh-{as_of}",
            "as_of": as_of,
            "queries": [
                {
                    "query_id": "company-600438-quote",
                    "subject_type": "listed_company",
                    "subject_id": "600438.SH",
                    "source_names": ["eastmoney"],
                    "request": {"required_fields": ["data"]},
                }
            ],
        },
        router,
    )


def test_refresh_tracking_initial_update_and_no_change():
    initial = build_data_refresh_tracking_report(refresh("2026-07-24", 10))
    assert initial["tracking_status"] == "INITIALIZED"
    assert initial["review_required"] is True

    updated = build_data_refresh_tracking_report(
        refresh("2026-07-25", 11),
        refresh("2026-07-24", 10),
    )
    assert updated["tracking_status"] == "UPDATED"
    assert updated["changed"] is True
    assert "company-600438-quote" in updated["changed_query_ids"]
    assert any(item["key"] == "data_hash" for item in updated["changes"])
    assert "company_research" in updated["affected_modules"]
    assert updated["decision_review"]["status"] == "REVIEW_REQUIRED"
    assert updated["decision_review"]["automatic_snapshot_update"] is False

    unchanged = build_data_refresh_tracking_report(
        refresh("2026-07-25", 10),
        refresh("2026-07-24", 10),
    )
    assert unchanged["tracking_status"] == "NO_CHANGE"
    assert unchanged["changed"] is False


def test_refresh_tracking_rejects_future_previous_and_fact_promotion():
    with pytest.raises(DataRefreshTrackingError, match="newer"):
        build_data_refresh_tracking_report(
            refresh("2026-07-24", 10),
            refresh("2026-07-25", 10),
        )
    report = build_data_refresh_tracking_report(refresh("2026-07-25", 10))
    assert validate_data_refresh_tracking_report(report)["tracking_id"] == report["tracking_id"]
    report["policy"]["fact_promotion"] = True
    with pytest.raises(DataRefreshTrackingError, match="promote"):
        validate_data_refresh_tracking_report(report)


def test_data_refresh_track_cli_writes_immutable_report(tmp_path, monkeypatch, capsys):
    current_path = tmp_path / "current.json"
    previous_path = tmp_path / "previous.json"
    output_dir = tmp_path / "tracking"
    current_path.write_text(json.dumps(refresh("2026-07-25", 11)), encoding="utf-8")
    previous_path.write_text(json.dumps(refresh("2026-07-24", 10)), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "industry-first-research",
        "data-refresh-track",
        "--current",
        str(current_path),
        "--previous",
        str(previous_path),
        "--output-dir",
        str(output_dir),
    ])

    main()
    result = json.loads(capsys.readouterr().out)
    assert result["report"]["tracking_status"] == "UPDATED"
    assert len(list(output_dir.glob("*.json"))) == 1
