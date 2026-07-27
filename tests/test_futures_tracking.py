import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.futures_tracking import (
    FuturesTrackingError,
    build_futures_tracking_report,
)


def report(report_id="futures-cu-current", as_of="2026-07-21", *, spot=101, status="READY"):
    return {
        "schema_version": "futures-fundamentals-report.v1",
        "report_id": report_id,
        "as_of": as_of,
        "exchange": "SHFE",
        "variety_id": "CU",
        "variety_name": "沪铜",
        "object_type": "futures_contract",
        "status": status,
        "identity_status": "READY",
        "contract": {"contract_code": "CU2612"},
        "variety_view": {"status": status},
        "contract_view": {"status": status},
        "simulation_view": {"status": "ELIGIBLE_FOR_USER_REVIEW"},
        "price_scenarios": {
            "status": "READY",
            "missing": [],
            "scenarios": {
                "BASE": {"range": {"low": 90, "high": 110}, "status": "VERIFIED"}
            },
        },
        "fields": {
            "spot_benchmark": {"status": "VERIFIED"},
            "inventory_by_location": {"status": "VERIFIED"},
        },
        "derived_metrics": {
            "spot_latest": {"date": as_of, "value": spot},
            "basis_latest": {"date": as_of, "value": 2},
            "inventory_latest": {"date": as_of, "value": 100},
            "spot_minus_full_cost": {"value": 5},
        },
    }


def test_tracking_reports_initial_update_and_metric_state_changes():
    initial = build_futures_tracking_report(report("old", "2026-07-20", spot=100))
    assert initial["tracking_status"] == "INITIALIZED"
    assert initial["review_required"] is True
    assert initial["policy"]["directional_conclusion"] is False

    updated = build_futures_tracking_report(
        report("new", "2026-07-21", spot=101),
        report("old", "2026-07-20", spot=100),
    )
    assert updated["tracking_status"] == "UPDATED"
    assert updated["changed"] is True
    assert any(item["area"] == "derived_metric" for item in updated["changes"])
    assert "futures_fundamentals" in updated["affected_modules"]
    assert updated["decision_review"]["status"] == "REVIEW_REQUIRED"
    assert updated["decision_review"]["automatic_snapshot_update"] is False
    assert updated["current_report_id"] == "new"


def test_tracking_does_not_compare_future_or_different_series():
    with pytest.raises(FuturesTrackingError, match="newer"):
        build_futures_tracking_report(report("old", "2026-07-20"), report("new", "2026-07-21"))
    other = report("other", "2026-07-21")
    other["variety_id"] = "RB"
    with pytest.raises(FuturesTrackingError, match="variety_id"):
        build_futures_tracking_report(report(), other)


def test_futures_tracking_cli_writes_immutable_report(tmp_path, monkeypatch, capsys):
    current_path = tmp_path / "current.json"
    previous_path = tmp_path / "previous.json"
    current_path.write_text(json.dumps(report()), encoding="utf-8")
    previous_path.write_text(
        json.dumps(report("previous", "2026-07-20", spot=100)), encoding="utf-8"
    )
    output_dir = tmp_path / "tracking"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "futures-tracking",
            "--current",
            str(current_path),
            "--previous",
            str(previous_path),
            "--output-dir",
            str(output_dir),
        ],
    )
    main()
    capsys.readouterr()
    files = list(output_dir.glob("*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert saved["schema_version"] == "futures-fundamentals-tracking.v1"
    assert saved["execution_enabled"] is False
