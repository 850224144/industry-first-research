import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.quality_scorecard import (
    QualityScorecardError,
    build_quality_scorecard,
)


def snapshot():
    return {
        "schema_version": "decision-snapshot.v1",
        "snapshot_id": "decision-snapshot-001",
        "status": "LOCKED",
        "immutable": True,
        "simulation_only": True,
        "execution_enabled": False,
        "decision": {
            "fundamental_assumptions": ["cash flow remains observable"],
            "risks": ["industry remains weak"],
            "invalidators": ["cash flow turns persistently negative"],
            "value_or_price_range": {"bear": 80, "base": 110, "bull": 150},
        },
    }


def test_scorecard_keeps_quality_dimensions_separate_from_outcome():
    scorecard = build_quality_scorecard(
        snapshot(),
        attribution_report={
            "schema_version": "attribution-result.v1",
            "attribution_id": "attribution-001",
            "evaluation_label": "THESIS_RIGHT_TIMING_EARLY",
        },
        assessments={
            "fact_accuracy": {
                "status": "PASS",
                "score": 90,
                "basis": "Later filing confirms the scoped facts.",
                "evidence_type": "OBSERVED_FACT",
                "evidence_refs": ["filing-001"],
            },
            "state_judgment": {"status": "PARTIAL", "basis": "State partly confirmed."},
        },
    )

    assert scorecard["outcome_label"] == "THESIS_RIGHT_TIMING_EARLY"
    assert scorecard["dimensions"]["fact_accuracy"]["status"] == "PASS"
    assert scorecard["dimensions"]["state_judgment"]["status"] == "PARTIAL"
    assert scorecard["dimensions"]["outcome_performance"]["status"] == "PARTIAL"
    assert "overall_score" not in scorecard
    assert scorecard["policy"]["return_does_not_prove_fact_accuracy"] is True


def test_scorecard_marks_missing_outcome_not_evaluable_and_validates_snapshot_boundary():
    scorecard = build_quality_scorecard(snapshot())

    assert scorecard["evaluation_state"] == "PARTIAL_NOT_EVALUABLE"
    assert scorecard["dimensions"]["outcome_performance"]["status"] == "NOT_EVALUABLE"
    assert "outcome_performance" in scorecard["weakest_dimensions"]

    bad = dict(snapshot())
    bad["status"] = "DRAFT"
    with pytest.raises(QualityScorecardError, match="LOCKED"):
        build_quality_scorecard(bad)


def test_opportunity_metrics_keep_empty_scan_and_selection_bias_visible():
    scorecard = build_quality_scorecard(
        snapshot(),
        opportunity_scan={
            "scan_coverage": {"industry_count": 50},
            "empty_scan_frequency": 0.4,
            "false_positive_sample": [],
        },
    )

    assert scorecard["opportunity_discovery"]["status"] == "REVIEW_ONLY"
    assert scorecard["opportunity_discovery"]["metrics"]["empty_scan_frequency"] == 0.4
    assert "selection_bias_warning" in scorecard["opportunity_discovery"]


def test_quality_scorecard_cli_writes_a_review_only_snapshot(tmp_path, monkeypatch):
    input_path = tmp_path / "decision-snapshot.json"
    output_dir = tmp_path / "quality-scorecards"
    input_path.write_text(json.dumps(snapshot()), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "quality-scorecard",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    main()

    output_path = output_dir / "quality-scorecard-001.json"
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["evaluation_state"] == "PARTIAL_NOT_EVALUABLE"
    assert report["read_only"] is True
    assert report["execution_enabled"] is False
