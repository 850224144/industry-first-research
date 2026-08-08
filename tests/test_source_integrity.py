import json
from copy import deepcopy
from pathlib import Path

import pytest

from industry_first_research.config import load_config
from industry_first_research.source_integrity import (
    SourceIntegrityError,
    apply_source_integrity,
    build_source_integrity_report,
    validate_source_integrity_report,
)


ROOT = Path(__file__).parents[1]


def test_missing_local_sources_cannot_remain_cross_validated():
    config = load_config(ROOT / "config/industries/baijiu.json")

    report = build_source_integrity_report(config, ROOT)
    adjusted = apply_source_integrity(config, report)

    assert report["status"] == "INSUFFICIENT"
    assert report["summary"]["downgraded_signal_count"] == 3
    assert report["summary"]["blocked_company_count"] == 13
    assert adjusted["evidence_completeness"] == "INSUFFICIENT"
    assert [
        signal["evidence_status"] for signal in adjusted["signals"]
    ] == ["UNVERIFIED", "UNVERIFIED", "REFERENCE_ONLY", "UNVERIFIED"]
    assert all(
        signal["source_availability"] == "MISSING"
        for signal in adjusted["signals"]
    )
    assert all(
        company["hard_gate_status"] == "BLOCKED"
        for company in adjusted["companies"]
    )


def test_available_local_sources_preserve_declared_statuses():
    config = load_config(ROOT / "config/industries/baijiu.json")
    fixture = "tests/fixtures/baijiu/industry-primary.md"
    adjusted_input = deepcopy(config)
    for signal in adjusted_input["signals"]:
        signal["source"] = fixture

    report = build_source_integrity_report(adjusted_input, ROOT)
    adjusted = apply_source_integrity(adjusted_input, report)

    assert report["status"] == "PARTIAL"
    assert report["summary"]["downgraded_signal_count"] == 0
    assert adjusted["evidence_completeness"] == "CROSS_VALIDATED"
    assert adjusted["signals"][0]["evidence_status"] == "CROSS_VALIDATED"


@pytest.mark.parametrize(
    ("source_kind", "expected"),
    [
        ("empty", "EMPTY"),
        ("directory", "NOT_FILE"),
        ("outside", "OUTSIDE_PROJECT"),
        ("unreadable", "UNREADABLE"),
    ],
)
def test_unusable_local_sources_fail_closed(
    tmp_path, monkeypatch, source_kind, expected
):
    root = tmp_path / "project"
    root.mkdir()
    source = root / "source.md"
    if source_kind == "empty":
        source.touch()
    elif source_kind == "directory":
        source.mkdir()
    elif source_kind == "outside":
        source = tmp_path / "outside.md"
        source.write_text("outside\n", encoding="utf-8")
    else:
        source.write_text("unreadable\n", encoding="utf-8")
        original_read_bytes = Path.read_bytes

        def fail_selected_path(path):
            if path == source:
                raise PermissionError("fixture is unreadable")
            return original_read_bytes(path)

        monkeypatch.setattr(Path, "read_bytes", fail_selected_path)
    config = {
        "industry_id": "source-boundary",
        "as_of": "2026-07-31",
        "evidence_completeness": "VERIFIED",
        "signals": [
            {
                "name": "boundary",
                "source": str(source),
                "evidence_status": "VERIFIED",
            }
        ],
        "source_documents": [],
        "companies": [],
    }

    report = build_source_integrity_report(config, root)
    adjusted = apply_source_integrity(config, report)

    assert report["signals"][0]["availability"] == expected
    assert adjusted["signals"][0]["evidence_status"] == "UNVERIFIED"
    assert adjusted["evidence_completeness"] == "INSUFFICIENT"


def test_company_without_any_available_asset_is_blocked(tmp_path):
    available = tmp_path / "available.md"
    available.write_text("available\n", encoding="utf-8")
    config = {
        "industry_id": "company-source-gate",
        "as_of": "2026-07-31",
        "signals": [],
        "source_documents": [],
        "companies": [
            {
                "company_id": "blocked",
                "hard_gate_status": "PASS",
                "source_assets": ["missing.md"],
            },
            {
                "company_id": "partial",
                "hard_gate_status": "PASS",
                "source_assets": ["available.md", "missing.md"],
            },
        ],
    }

    report = build_source_integrity_report(config, tmp_path)
    adjusted = apply_source_integrity(config, report)

    assert adjusted["companies"][0]["hard_gate_status"] == "BLOCKED"
    assert adjusted["companies"][0]["declared_hard_gate_status"] == "PASS"
    assert adjusted["companies"][1]["hard_gate_status"] == "PASS"
    assert adjusted["companies"][1]["source_asset_summary"]["complete"] is False
    assert report["summary"]["blocked_company_count"] == 1


def test_source_integrity_hash_rejects_tampering():
    config = load_config(ROOT / "config/industries/baijiu.json")
    report = build_source_integrity_report(config, ROOT)

    with pytest.raises(SourceIntegrityError, match="content_hash"):
        validate_source_integrity_report(dict(report, status="READY"))


def test_source_integrity_rejects_a_report_for_changed_config():
    config = load_config(ROOT / "config/industries/baijiu.json")
    report = build_source_integrity_report(config, ROOT)
    changed = deepcopy(config)
    changed["signals"][0]["source"] = "different-source.md"

    with pytest.raises(SourceIntegrityError, match="input_config_hash"):
        apply_source_integrity(changed, report)


def test_source_integrity_hash_is_portable_across_checkout_roots(tmp_path):
    config = {
        "industry_id": "portable",
        "as_of": "2026-07-30",
        "evidence_completeness": "VERIFIED",
        "signals": [
            {
                "name": "fixture",
                "source": "sources/fixture.txt",
                "evidence_status": "VERIFIED",
            }
        ],
        "source_documents": [],
        "companies": [],
    }
    roots = [tmp_path / "checkout-a", tmp_path / "checkout-b"]
    for root in roots:
        source = root / "sources/fixture.txt"
        source.parent.mkdir(parents=True)
        source.write_text("same source bytes\n", encoding="utf-8")

    first = build_source_integrity_report(config, roots[0])
    second = build_source_integrity_report(config, roots[1])

    assert first["project_root"] == "."
    assert first["report_id"] == second["report_id"]
    assert first["content_hash"] == second["content_hash"]


def test_source_integrity_report_is_json_serialisable():
    config = load_config(ROOT / "config/industries/baijiu.json")
    report = build_source_integrity_report(config, ROOT)

    assert json.loads(json.dumps(report, ensure_ascii=False))["report_id"] == report["report_id"]
