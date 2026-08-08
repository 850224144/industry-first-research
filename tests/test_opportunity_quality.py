import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.opportunity_quality import (
    OpportunityQualityError,
    build_opportunity_quality_report,
)


def scan(scan_id, as_of, items, empty_result=False):
    return {
        "schema_version": "opportunity-scan.v1",
        "scan_id": scan_id,
        "as_of": as_of,
        "scan_scope": {"industry_count": 20},
        "empty_result": empty_result,
        "items": items,
    }


def candidate(status, **overrides):
    payload = {
        "candidate_id": "candidate-1",
        "company_id": "600438",
        "industry_id": "pv",
        "status": status,
    }
    payload.update(overrides)
    return payload


def test_quality_report_keeps_empty_scans_states_and_dwell_time():
    report = build_opportunity_quality_report(
        {
            "as_of": "2026-07-21",
            "scans": [
                scan("scan-1", "2026-07-19", [candidate("WATCH")]),
                scan("scan-2", "2026-07-20", [candidate("CANDIDATE")]),
                scan("scan-3", "2026-07-21", [], empty_result=True),
            ],
        }
    )

    assert report["metrics"]["scan_count"] == 3
    assert report["metrics"]["empty_scan_frequency"] == pytest.approx(1 / 3)
    assert report["transitions"][0]["from_state"] == "WATCH"
    assert report["transitions"][0]["to_state"] == "CANDIDATE"
    assert report["metrics"]["state_dwell_time"]["average_days_by_state"]["WATCH"] == 1
    assert report["policy"]["returns_do_not_rewrite_candidate_state"] is True


def test_quality_report_requires_explicit_error_samples():
    report = build_opportunity_quality_report(
        {
            "as_of": "2026-07-21",
            "scans": [scan("scan-1", "2026-07-21", [])],
            "false_positive_samples": [
                {"candidate_id": "candidate-1", "label": "CONFIRMED"}
            ],
            "false_negative_samples": [
                {"candidate_id": "candidate-2", "confirmed": True}
            ],
        }
    )

    assert report["metrics"]["false_positive_sample"]["sample_count"] == 1
    assert report["metrics"]["false_negative_sample"]["confirmed_count"] == 1
    assert report["metrics"]["hard_gate_accuracy_sample"]["status"] == "NOT_EVALUABLE"


def test_quality_report_rejects_unknown_candidate_state():
    with pytest.raises(OpportunityQualityError, match="unsupported candidate state"):
        build_opportunity_quality_report(
            {"scans": [scan("scan-1", "2026-07-21", [candidate("BUY")])]}
        )


def test_opportunity_quality_cli_writes_report(tmp_path, monkeypatch, capsys):
    input_path = tmp_path / "quality-input.json"
    input_path.write_text(
        json.dumps({"scans": [scan("scan-1", "2026-07-21", [])]}),
        encoding="utf-8",
    )
    output_dir = tmp_path / "quality"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "opportunity-quality",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
    )
    main()
    capsys.readouterr()
    report = json.loads(next(output_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert report["schema_version"] == "opportunity-quality-report.v1"
