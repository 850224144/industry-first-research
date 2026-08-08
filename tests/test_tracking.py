import pytest

from industry_first_research.tracking import (
    TrackingError,
    build_evidence_freshness_report,
    build_holding_thesis_check,
    build_research_version_comparison,
)


def record(evidence_id, company_id, field, value, as_of="2026-07-20", status="VERIFIED"):
    return {
        "evidence_id": evidence_id,
        "company_id": company_id,
        "field": field,
        "value": value,
        "source": "https://example.test/official",
        "source_refs": [],
        "as_of": as_of,
        "evidence_tier": "A",
        "verification_status": status,
    }


def supplemental(records, as_of="2026-07-21"):
    return {
        "schema_version": "company-supplemental-evidence.v1",
        "report_id": "supplemental-001",
        "as_of": as_of,
        "records": records,
    }


def pipeline(pipeline_id, final_state, item_state):
    return {
        "schema_version": "company-research-pipeline.v1",
        "pipeline_id": pipeline_id,
        "as_of": "2026-07-21",
        "final_state": final_state,
        "stages": {
            "research_report": {
                "schema_version": "company-research-report.v1",
                "as_of": "2026-07-21",
                "report_state_counts": {item_state: 1},
                "items": [
                    {
                        "company_id": "600519",
                        "candidate_state": "WATCH",
                        "report_state": item_state,
                        "conclusion_state": "CONDITIONAL_REVIEW_ONLY",
                    }
                ],
            }
        },
    }


def test_freshness_classifies_fresh_due_expired_and_future_records():
    report = build_evidence_freshness_report(
        supplemental(
            [
                record("fresh", "600519", "key_products", "白酒"),
                record("due", "600519", "current_price", 100, "2026-07-16"),
                record("expired", "600519", "current_price", 90, "2026-07-01"),
                record("future", "600519", "key_risks", "future", "2026-07-22"),
            ]
        )
    )

    assert report["freshness_status"] == "FUTURE_DATA_BLOCKED"
    assert report["status_counts"] == {
        "FRESH": 1,
        "DUE": 1,
        "EXPIRED": 1,
        "FUTURE": 1,
    }
    assert report["expired_evidence_ids"] == ["expired"]
    assert report["future_evidence_ids"] == ["future"]
    assert build_evidence_freshness_report(supplemental([]))["freshness_status"] == "UNKNOWN"


def test_version_comparison_reports_evidence_and_state_changes_without_direction():
    old_supplemental = supplemental(
        [record("products-1", "600519", "key_products", ["白酒"])]
    )
    new_supplemental = supplemental(
        [
            record("products-1", "600519", "key_products", ["白酒"]),
            record("products-2", "600519", "key_products", ["白酒", "系列酒"], "2026-07-21"),
        ]
    )
    comparison = build_research_version_comparison(
        pipeline("pipeline-old", "REVIEW", "REVIEW"),
        pipeline("pipeline-new", "REVIEWABLE", "REVIEWABLE"),
        old_supplemental,
        new_supplemental,
    )

    assert comparison["evidence_diff"]["added_evidence_ids"] == ["products-2"]
    assert comparison["conclusion_change"]["requires_review"] is True
    assert comparison["conclusion_change"]["directional_conclusion_changed"] is False
    assert comparison["policy"]["old_version_preserved"] is True


def test_thesis_check_proposes_status_but_does_not_commit_it():
    current = supplemental(
        [
            record("cash-1", "600519", "operating_cashflow", -10),
            record("price-1", "600519", "current_price", 90),
        ]
    )
    thesis = {
        "schema_version": "holding-thesis.v1",
        "thesis_id": "thesis-001",
        "company_id": "600519",
        "version": 1,
        "status": "INTACT",
        "hypotheses": [
            {
                "hypothesis_id": "cash-positive",
                "field": "operating_cashflow",
                "operator": "gt",
                "expected_value": 0,
            }
        ],
        "red_lines": [
            {
                "red_line_id": "cash-burn",
                "field": "operating_cashflow",
                "severity": "FATAL",
                "operator": "lt",
                "expected_value": 0,
            }
        ],
    }
    check = build_holding_thesis_check(thesis, current)

    assert check["current_status"] == "INTACT"
    assert check["proposed_status"] == "BROKEN"
    assert check["status_change_requires_confirmation"] is True
    assert check["policy"]["thesis_version_unchanged"] is True
    assert check["policy"]["price_alone_cannot_break_thesis"] is True


def test_broken_thesis_cannot_be_silently_restored_by_later_evidence():
    current = supplemental([record("cash-2", "600519", "operating_cashflow", 10)])
    thesis = {
        "schema_version": "holding-thesis.v1",
        "thesis_id": "thesis-002",
        "company_id": "600519",
        "version": 2,
        "status": "BROKEN",
        "hypotheses": [],
        "red_lines": [],
    }
    check = build_holding_thesis_check(thesis, current)

    assert check["proposed_status"] == "BROKEN"
    assert check["status_downgrade_blocked"] is True


def test_tracking_rejects_future_or_invalid_thesis_schema():
    with pytest.raises(TrackingError, match="holding-thesis"):
        build_holding_thesis_check(
            {"schema_version": "other", "thesis_id": "x"},
            supplemental([]),
        )
