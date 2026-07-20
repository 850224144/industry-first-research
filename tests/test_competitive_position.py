import pytest

from industry_first_research.competitive_position import (
    CompetitivePositionError,
    build_competitive_position_report,
)


REQUIRED_FIELDS = [
    "business_model",
    "revenue_structure",
    "cost_position",
    "technology_position",
    "customer_position",
    "channel_position",
    "capital_position",
    "market_share_position",
    "competitive_matrix",
    "substitution_risk",
    "delivery_quality",
    "profitability_quality",
]
MATRIX_FIELDS = [
    "cost",
    "performance",
    "yield",
    "certification",
    "delivery",
    "customers",
    "scale",
    "substitution_route",
]


def cycle_report(*, gate_state="READY", fields=None):
    return {
        "schema_version": "company-cycle-reversal.v1",
        "report_id": "cycle-001",
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
                "cycle_reversal_gate_state": gate_state,
                "cycle_reversal_state": "TURNING_POINT_CANDIDATE",
                "fields": fields or {},
                "evidence_ids": ["cycle"],
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
        if field != "competitive_matrix"
    }
    fields["competitive_matrix"] = summary(
        "competitive_matrix",
        {
            "competitor": "竞争对手 A",
            **{field: f"{field} evidence" for field in MATRIX_FIELDS},
        },
    )
    return fields


def test_competitive_position_is_ready_with_complete_matrix():
    report = build_competitive_position_report(
        cycle_report(fields=complete_fields())
    )

    item = report["items"][0]
    assert report["schema_version"] == "company-competitive-position.v1"
    assert item["competitive_position_state"] == "READY"
    assert item["competitive_matrix"][0]["competitor"] == "竞争对手 A"
    assert item["downstream_modules"]["survival_analysis"] == "READY_REQUIRED"
    assert "moat_conclusion" in item["prohibited_actions"]


def test_competitive_position_requires_upstream_cycle_ready():
    item = build_competitive_position_report(
        cycle_report(gate_state="PARTIAL", fields=complete_fields())
    )["items"][0]

    assert item["competitive_position_state"] == "BLOCKED"
    assert item["reasons"] == ["UPSTREAM_CYCLE_EVIDENCE_READY_REQUIRED"]
    assert item["allowed_actions"] == [
        "upstream_evidence_resolution",
        "evidence_refresh",
    ]


def test_missing_matrix_is_not_a_competitive_advantage():
    fields = complete_fields()
    fields["competitive_matrix"] = summary(
        "competitive_matrix", [], status="VERIFIED"
    )

    item = build_competitive_position_report(
        cycle_report(fields=fields)
    )["items"][0]

    assert item["competitive_position_state"] == "INSUFFICIENT"
    assert item["reasons"] == ["COMPETITIVE_MATRIX_MISSING"]


def test_competitive_matrix_rejects_missing_dimension_and_wrong_schema():
    fields = complete_fields()
    fields["competitive_matrix"] = summary(
        "competitive_matrix", {"competitor": "竞争对手 A"}
    )
    with pytest.raises(CompetitivePositionError, match="missing: cost"):
        build_competitive_position_report(cycle_report(fields=fields))

    with pytest.raises(CompetitivePositionError, match="cycle-reversal.v1"):
        build_competitive_position_report({"schema_version": "other", "items": []})
