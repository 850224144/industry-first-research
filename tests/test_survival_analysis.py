import pytest

from industry_first_research.survival_analysis import (
    STRESS_SCENARIOS,
    SurvivalAnalysisError,
    build_survival_analysis_report,
)


REQUIRED_FIELDS = [
    "available_cash",
    "monthly_cash_burn",
    "debt_maturity",
    "interest_coverage",
    "operating_cashflow",
    "free_cashflow_after_maintenance_capex",
    "cash_cost_position",
    "capex_commitment",
    "impairment_risk",
    "refinancing_capacity",
    "external_support",
    "technology_obsolescence_risk",
    "effective_capacity",
    "recovery_operating_leverage",
    "survival_label",
    "stress_tests",
]
STRESS_FIELDS = [
    "scenario",
    "horizon_months",
    "cash_runway_months",
    "debt_gap",
    "minimum_cash_balance",
    "capex_reduction_capacity",
    "asset_sale_actions",
    "survival_dependency",
    "survival_outcome",
]


def competitive_report(*, state="READY", fields=None):
    return {
        "schema_version": "company-competitive-position.v1",
        "report_id": "position-001",
        "input_cycle_reversal_id": "cycle-001",
        "input_industry_situation_id": "situation-001",
        "input_demand_transmission_id": "transmission-001",
        "input_application_mapping_id": "mapping-001",
        "input_product_profile_id": "product-profile-001",
        "input_supplemental_id": "supplemental-001",
        "input_queue_id": "queue-001",
        "input_snapshot_id": "pool-001",
        "as_of": "2026-07-19",
        "source": "manual",
        "items": [
            {
                "company_id": "300317",
                "display_name": "珈伟新能",
                "industry_id": "881145",
                "candidate_state": "WATCH",
                "candidate_rule_version": "company-candidate-queue-rules.v1",
                "competitive_position_state": state,
                "fields": fields or {},
                "evidence_ids": ["position"],
            }
        ],
    }


def summary(field, value, *, status="VERIFIED", tier="A"):
    return {
        "status": status,
        "values": [value],
        "evidence_ids": [field],
        "sources": ["https://example.test/official"],
        "as_of": ["2026-07-19"],
        "evidence_tiers": [tier],
    }


def stress_tests():
    return [
        {
            "scenario": scenario,
            "horizon_months": 24,
            "cash_runway_months": 18,
            "debt_gap": 0,
            "minimum_cash_balance": 10,
            "capex_reduction_capacity": "可削减",
            "asset_sale_actions": "可选",
            "survival_dependency": "self_funded",
            "survival_outcome": "CONTINUOUS_OPERATIONS",
        }
        for scenario in STRESS_SCENARIOS
    ]


def complete_fields():
    fields = {
        field: summary(field, field)
        for field in REQUIRED_FIELDS
        if field != "stress_tests"
    }
    fields["survival_label"] = summary("survival_label", "SURVIVOR")
    fields["stress_tests"] = summary("stress_tests", stress_tests())
    return fields


def test_survival_requires_all_six_stress_scenarios_and_preserves_dependencies():
    report = build_survival_analysis_report(
        competitive_report(fields=complete_fields())
    )

    item = report["items"][0]
    assert report["schema_version"] == "company-survival-analysis.v1"
    assert item["survival_gate_state"] == "READY"
    assert item["survival_label"] == "SURVIVOR"
    assert item["survival_dependencies"] == ["self_funded"]
    assert len(item["stress_tests"]) == 6
    assert item["downstream_modules"]["valuation"] == "READY_REQUIRED"


def test_refinancing_dependency_is_not_self_funded_survival():
    fields = complete_fields()
    fields["stress_tests"]["values"][0][0]["survival_dependency"] = (
        "refinancing_dependent"
    )

    item = build_survival_analysis_report(
        competitive_report(fields=fields)
    )["items"][0]

    assert item["survival_gate_state"] == "READY"
    assert item["survival_dependencies"] == [
        "refinancing_dependent",
        "self_funded",
    ]


def test_missing_stress_tests_is_insufficient():
    fields = complete_fields()
    fields["stress_tests"] = summary("stress_tests", [], status="VERIFIED")

    item = build_survival_analysis_report(
        competitive_report(fields=fields)
    )["items"][0]

    assert item["survival_gate_state"] == "INSUFFICIENT"
    assert item["reasons"] == ["SURVIVAL_STRESS_TESTS_MISSING"]


def test_stress_tests_reject_duplicate_scenario_and_wrong_schema():
    fields = complete_fields()
    fields["stress_tests"]["values"][0][0]["scenario"] = STRESS_SCENARIOS[1]
    with pytest.raises(SurvivalAnalysisError, match="duplicate stress scenario"):
        build_survival_analysis_report(competitive_report(fields=fields))

    with pytest.raises(SurvivalAnalysisError, match="competitive-position.v1"):
        build_survival_analysis_report({"schema_version": "other", "items": []})
