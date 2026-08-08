import json
import sys

import pytest

from industry_first_research.capability_matrix import (
    CapabilityMatrixError,
    build_capability_gap,
    build_capability_matrix,
)
from industry_first_research.cli import main


def item(decision="ADAPTER_REUSE", **overrides):
    payload = {
        "capability_id": "data.router",
        "capability_name": "数据主备路由",
        "component": "existing-router",
        "interfaces": ["fetch", "health_check"],
        "output_quality": "traceable",
        "license_status": "reviewed",
        "temporal_cutoff_support": "as_of",
        "safety_boundary": "read-only",
        "decision": decision,
    }
    payload.update(overrides)
    return payload


def test_capability_matrix_requires_gap_for_new_development():
    with pytest.raises(CapabilityMatrixError, match="capability_gap"):
        build_capability_matrix({"items": [item("NEW_DEVELOPMENT")]})

    report = build_capability_matrix(
        {"as_of": "2026-07-22", "items": [item(), item("REFERENCE_ONLY", capability_id="ai.reference")]}
    )
    assert report["decision_counts"] == {"ADAPTER_REUSE": 1, "REFERENCE_ONLY": 1}
    assert report["policy"]["reuse_before_new_development"] is True


def test_capability_gap_is_bounded_and_traceable():
    report = build_capability_gap(
        {
            "capability_name": "统一证据",
            "capability_gap": "字段级血缘缺失",
            "existing_components_checked": ["announcement_asset"],
            "rejected_reuse_reasons": ["只覆盖公告，不覆盖行情与研究资产"],
            "owner_module": "evidence",
            "created_as_of": "2026-07-22",
        },
        gap_id="gap-evidence",
    )
    assert report["gap_id"] == "gap-evidence"
    assert report["capability_gap"] == "字段级血缘缺失"


def test_capability_cli_validates_checked_in_matrix(tmp_path, monkeypatch, capsys):
    input_path = tmp_path / "matrix.json"
    input_path.write_text(
        json.dumps({"items": [item("NEW_DEVELOPMENT", capability_gap="missing protocol")]}),
        encoding="utf-8",
    )
    output_dir = tmp_path / "capabilities"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "capability-matrix",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
    )
    main()
    capsys.readouterr()
    report = json.loads(next(output_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert report["decision_counts"] == {"NEW_DEVELOPMENT": 1}
