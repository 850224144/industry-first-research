import pytest

from industry_first_research.industry_situation import (
    IndustrySituationError,
    build_industry_situation_report,
)


REQUIRED_FIELDS = [
    "industry_demand_horizon",
    "value_chain_profit_distribution",
    "supply_demand_state",
    "inventory_state",
    "price_state",
    "utilization_state",
    "competition_state",
    "policy_technology_overseas",
    "cycle_stage",
    "key_industry_variables",
    "reversal_conditions",
    "validation_signals",
    "product_market_state",
    "product_competition_matrix",
    "lifecycle_transition_conditions",
]


def transmission_report(*, gate_state="READY", fields=None):
    return {
        "schema_version": "company-demand-transmission.v1",
        "report_id": "transmission-001",
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
                "transmission_gate_state": gate_state,
                "transmission_state": "PROFIT_VALIDATED",
                "fields": fields or {},
                "evidence_ids": ["transmission"],
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


def complete_fields():
    fields = {
        field: summary(field, field)
        for field in REQUIRED_FIELDS
        if field != "key_industry_variables"
    }
    fields["key_industry_variables"] = summary(
        "key_industry_variables",
        [
            {"name": "真实需求", "reason": "决定终端消化", "direction": "改善"},
            {"name": "有效供给", "reason": "决定价格竞争", "direction": "收缩"},
            {"name": "库存", "reason": "决定补库强度", "direction": "下降"},
        ],
    )
    return fields


def test_industry_situation_is_ready_with_three_explicit_key_variables():
    report = build_industry_situation_report(
        transmission_report(fields=complete_fields())
    )

    item = report["items"][0]
    assert report["schema_version"] == "company-industry-situation.v1"
    assert item["industry_situation_state"] == "READY"
    assert len(item["key_industry_variables"]) == 3
    assert item["downstream_modules"]["cycle_reversal"] == "READY_REQUIRED"
    assert "valuation" in item["prohibited_actions"]


def test_industry_situation_blocks_until_transmission_is_ready():
    report = build_industry_situation_report(
        transmission_report(gate_state="PARTIAL", fields=complete_fields())
    )

    item = report["items"][0]
    assert item["industry_situation_state"] == "BLOCKED"
    assert item["reasons"] == ["DEMAND_TRANSMISSION_READY_REQUIRED"]
    assert item["allowed_actions"] == [
        "demand_transmission_resolution",
        "evidence_refresh",
    ]


def test_industry_situation_requires_at_most_three_key_variables():
    fields = complete_fields()
    fields["key_industry_variables"] = summary(
        "key_industry_variables", ["a", "b", "c", "d"]
    )

    with pytest.raises(IndustrySituationError, match="at most three"):
        build_industry_situation_report(transmission_report(fields=fields))


def test_industry_situation_rejects_wrong_schema():
    with pytest.raises(IndustrySituationError, match="demand-transmission.v1"):
        build_industry_situation_report({"schema_version": "other", "items": []})
