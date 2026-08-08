import pytest

from industry_first_research.research_report import (
    ResearchReportError,
    build_research_report,
)


def summary(field, value, *, status="VERIFIED"):
    return {
        "status": status,
        "values": [value],
        "evidence_ids": [field],
        "sources": ["https://example.test/official"],
        "as_of": ["2026-07-19"],
        "evidence_tiers": ["A"],
    }


def review_report(*, audit_state="PASS", candidate_state="WATCH", fields=None):
    return {
        "schema_version": "company-adversarial-review.v1",
        "report_id": "review-001",
        "input_valuation_scenarios_id": "valuation-001",
        "input_survival_analysis_id": "survival-001",
        "input_competitive_position_id": "position-001",
        "input_cycle_reversal_id": "cycle-001",
        "input_industry_situation_id": "situation-001",
        "input_demand_transmission_id": "transmission-001",
        "input_application_mapping_id": "mapping-001",
        "input_product_profile_id": "product-profile-001",
        "input_supplemental_id": "supplemental-001",
        "input_queue_id": "queue-001",
        "as_of": "2026-07-19",
        "source": "manual",
        "items": [
            {
                "company_id": "300317",
                "display_name": "珈伟新能",
                "industry_id": "881145",
                "candidate_state": candidate_state,
                "candidate_state_changed": False,
                "candidate_rule_version": "company-candidate-queue-rules.v1",
                "audit_state": audit_state,
                "fields": fields or {},
                "findings": [],
                "reasons": [],
                "unknowns": [],
                "evidence_ids": ["review"],
            }
        ],
    }


def complete_fields():
    return {
        "industry_demand_horizon": summary("industry_demand_horizon", "long-term"),
        "supply_demand_state": summary("supply_demand_state", "balanced"),
        "cycle_stage": summary("cycle_stage", "recovery"),
        "business_model": summary("business_model", "manufacturing"),
        "cost_position": summary("cost_position", "verified"),
        "customer_position": summary("customer_position", "verified"),
        "product_list": summary("product_list", ["产品 A"]),
        "product_application": summary("product_application", ["应用 A"]),
        "transmission_state": summary("transmission_state", "REVENUE_VALIDATED"),
        "available_cash": summary("available_cash", "verified"),
        "stress_tests": summary("stress_tests", ["six scenarios"]),
        "survival_label": summary("survival_label", "SURVIVOR"),
        "scenario_inputs": summary("scenario_inputs", ["BEAR", "BASE", "BULL"]),
        "implied_assumptions": summary("implied_assumptions", ["assumption"]),
        "valuation_sensitivity": summary("valuation_sensitivity", ["price"]),
        "counterevidence": summary("counterevidence", ["counterevidence"]),
        "invalidators": summary("invalidators", ["invalidator"]),
        "excluded_from_base_case": summary("excluded_from_base_case", ["theme"]),
        "follow_up_checks": summary("follow_up_checks", ["cash flow"]),
        "next_check_at": summary("next_check_at", "2026-08-19"),
    }


def test_reviewable_report_assembles_sections_and_tracking():
    report = build_research_report(
        review_report(fields=complete_fields())
    )

    item = report["items"][0]
    assert report["schema_version"] == "company-research-report.v1"
    assert item["report_state"] == "REVIEWABLE"
    assert item["conclusion_state"] == "EVIDENCE_ASSEMBLED_NO_DIRECTIONAL_CONCLUSION"
    assert item["sections"]["valuation"]["directional_conclusion_included"] is False
    assert item["tracking_checklist"]["next_check_at"] == "2026-08-19"
    assert item["decision_snapshot_created"] is False
    recommendation = item["simulation_recommendation"]
    assert recommendation["state"] == "USER_CONFIRMATION_REQUIRED"
    assert recommendation["available_actions"] == [
        "OBSERVE",
        "ESTABLISH_SIMULATION",
        "PHASED_SIMULATION",
    ]
    assert recommendation["direction"] == "NEUTRAL"
    assert recommendation["policy"]["directional_conclusion"] is False


def test_review_or_insufficient_candidate_is_not_reviewable():
    review = build_research_report(
        review_report(audit_state="REVIEW", fields=complete_fields())
    )["items"][0]
    blocked = build_research_report(
        review_report(candidate_state="INSUFFICIENT", fields=complete_fields())
    )["items"][0]

    assert review["report_state"] == "REVIEW"
    assert blocked["report_state"] == "BLOCKED"
    assert blocked["conclusion_state"] == "NO_CONCLUSION_DATA_GAP_OR_BLOCKER"
    assert review["simulation_recommendation"]["state"] == "REVIEW_REQUIRED"
    assert blocked["simulation_recommendation"]["state"] == "WAIT_FOR_DATA"
    assert blocked["simulation_recommendation"]["recommended_action"] == "CONTINUE_DATA_REVIEW"


def test_research_report_preserves_candidate_state_and_rejects_wrong_schema():
    item = build_research_report(
        review_report(candidate_state="CANDIDATE", fields=complete_fields())
    )["items"][0]
    assert item["candidate_state"] == "CANDIDATE"
    assert item["candidate_state_changed"] is False

    with pytest.raises(ResearchReportError, match="adversarial-review.v1"):
        build_research_report({"schema_version": "other", "items": []})
