from industry_first_research.opportunity_tracking import (
    build_opportunity_tracking_report,
)


def scan(scan_id, status="WATCH", dimension_status="PARTIAL"):
    return {
        "schema_version": "opportunity-scan.v1",
        "scan_id": scan_id,
        "as_of": scan_id[-10:],
        "items": [
            {
                "candidate_id": "candidate-600438",
                "company_id": "600438",
                "display_name": "示例公司",
                "status": status,
                "dimensions": {
                    "downside_protection": {"status": dimension_status},
                    "inflection_evidence": {"status": "NOT_EVALUABLE"},
                },
            }
        ],
    }


def test_tracking_keeps_state_unchanged_without_new_candidate_evidence():
    report = build_opportunity_tracking_report(
        scan("scan-2026-07-21"),
        previous_scan=scan("scan-2026-07-20"),
        trend_report={"trend_state": "PERSISTENT_STRENGTH"},
        candidate_delta={"items": [{"company_id": "600438"}]},
        as_of="2026-07-21",
    )

    change = report["changes"][0]
    assert change["change_type"] == "QUEUE_DELTA_REVIEW"
    assert change["state_changed"] is False
    assert report["state_transition_requires_new_evidence"] is True
    assert report["policy"]["no_state_inference_from_trend_only"] is True


def test_tracking_reports_dimension_and_state_changes():
    report = build_opportunity_tracking_report(
        scan("scan-2026-07-21", status="CANDIDATE", dimension_status="PASS"),
        previous_scan=scan("scan-2026-07-20", status="WATCH", dimension_status="PARTIAL"),
        as_of="2026-07-21",
    )

    change = report["changes"][0]
    assert change["change_type"] == "STATE_OR_DIMENSION_CHANGED"
    assert change["changed_dimensions"] == ["downside_protection"]
    assert change["affected_modules"] == ["survival_analysis"]


def test_tracking_makes_missing_snapshots_explicit():
    report = build_opportunity_tracking_report(None, as_of="2026-07-21")
    assert report["current_scan_status"] == "NO_SNAPSHOT"
    assert report["changed_count"] == 0
