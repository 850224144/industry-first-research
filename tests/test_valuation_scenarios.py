import pytest

from industry_first_research.valuation_scenarios import (
    SCENARIOS,
    ValuationScenarioError,
    build_valuation_scenarios_report,
)


REQUIRED_FIELDS = [
    "valuation_method",
    "current_price",
    "current_price_as_of",
    "historical_financials",
    "cycle_center_profit",
    "net_debt_and_dilution",
    "scenario_inputs",
    "implied_assumptions",
    "evidence_backed_assumptions",
    "model_assumptions",
    "excluded_from_base_case",
    "valuation_sensitivity",
]
SCENARIO_FIELDS = [
    "scenario",
    "revenue_assumptions",
    "profit_assumptions",
    "cashflow_assumptions",
    "capex_assumptions",
    "treatment",
]


def survival_report(*, state="READY", fields=None):
    return {
        "schema_version": "company-survival-analysis.v1",
        "report_id": "survival-001",
        "input_competitive_position_id": "position-001",
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
                "survival_gate_state": state,
                "fields": fields or {},
                "evidence_ids": ["survival"],
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


def scenario_inputs():
    return [
        {
            "scenario": scenario,
            "revenue_assumptions": "evidence",
            "profit_assumptions": "evidence",
            "cashflow_assumptions": "evidence",
            "capex_assumptions": "evidence",
            "treatment": "BASE_CASE" if scenario == "BASE" else "RANGE",
        }
        for scenario in SCENARIOS
    ]


def complete_fields():
    fields = {
        field: summary(field, field)
        for field in REQUIRED_FIELDS
        if field not in {"scenario_inputs", "valuation_sensitivity"}
    }
    fields["scenario_inputs"] = summary("scenario_inputs", scenario_inputs())
    fields["valuation_sensitivity"] = summary(
        "valuation_sensitivity",
        [
            {"variable": "price", "downside": "-20%", "upside": "+20%"},
            {"variable": "cost", "downside": "+15%", "upside": "-10%"},
        ],
    )
    return fields


def test_valuation_framework_requires_three_scenarios_and_sensitivity():
    report = build_valuation_scenarios_report(
        survival_report(fields=complete_fields())
    )

    item = report["items"][0]
    assert report["schema_version"] == "company-valuation-scenarios.v1"
    assert item["valuation_gate_state"] == "READY"
    assert [scenario["scenario"] for scenario in item["scenario_inputs"]] == [
        "BEAR",
        "BASE",
        "BULL",
    ]
    assert item["numeric_valuation_included"] is False
    assert item["target_price_generated"] is False
    assert "target_price_generation" in item["prohibited_actions"]


def test_valuation_framework_blocks_until_survival_is_ready():
    item = build_valuation_scenarios_report(
        survival_report(state="PARTIAL", fields=complete_fields())
    )["items"][0]

    assert item["valuation_gate_state"] == "BLOCKED"
    assert item["reasons"] == ["SURVIVAL_ANALYSIS_READY_REQUIRED"]


def test_valuation_framework_requires_all_three_scenarios():
    fields = complete_fields()
    fields["scenario_inputs"]["values"][0] = scenario_inputs()[:2]

    item = build_valuation_scenarios_report(
        survival_report(fields=fields)
    )["items"][0]

    assert item["valuation_gate_state"] == "INSUFFICIENT"
    assert item["reasons"] == ["THREE_SCENARIOS_REQUIRED"]


def test_valuation_framework_rejects_duplicate_scenario_and_wrong_schema():
    fields = complete_fields()
    fields["scenario_inputs"]["values"][0][0]["scenario"] = "BASE"
    with pytest.raises(ValuationScenarioError, match="duplicate valuation scenario"):
        build_valuation_scenarios_report(survival_report(fields=fields))

    with pytest.raises(ValuationScenarioError, match="survival-analysis.v1"):
        build_valuation_scenarios_report({"schema_version": "other", "items": []})
