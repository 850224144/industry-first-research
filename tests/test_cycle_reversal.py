import pytest

from industry_first_research.cycle_reversal import (
    CycleReversalError,
    build_cycle_reversal_report,
)


REQUIRED_FIELDS = [
    "industry_applicability",
    "real_demand",
    "effective_supply",
    "nominal_capacity",
    "capacity_utilization",
    "inventory_level",
    "inventory_holder",
    "spot_price",
    "contract_price",
    "cash_cost",
    "full_cost",
    "marginal_capacity",
    "capex_pipeline",
    "capacity_exit",
    "shutdown_and_bankruptcy",
    "industry_cashflow",
    "recovery_speed",
    "cycle_state",
    "cycle_evidence",
    "confirmation_conditions",
    "invalidators",
    "confidence",
]


def situation_report(*, state="READY", fields=None):
    return {
        "schema_version": "company-industry-situation.v1",
        "report_id": "situation-001",
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
                "industry_situation_state": state,
                "fields": fields or {},
                "evidence_ids": ["situation"],
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


def complete_fields(state="TURNING_POINT_CANDIDATE"):
    fields = {
        field: summary(field, field)
        for field in REQUIRED_FIELDS
        if field not in {"industry_applicability", "cycle_state"}
    }
    fields["industry_applicability"] = summary("industry_applicability", True)
    fields["cycle_state"] = summary("cycle_state", state)
    return fields


def test_turning_point_candidate_requires_explicit_cycle_evidence():
    report = build_cycle_reversal_report(
        situation_report(fields=complete_fields())
    )

    item = report["items"][0]
    assert report["schema_version"] == "company-cycle-reversal.v1"
    assert item["cycle_reversal_gate_state"] == "READY"
    assert item["cycle_reversal_state"] == "TURNING_POINT_CANDIDATE"
    assert item["applicable"] is True
    assert item["downstream_modules"]["valuation"] == "READY_REQUIRED"


def test_price_rebound_does_not_require_full_reversal_evidence():
    fields = complete_fields("PRICE_REBOUND")
    fields["real_demand"] = summary("real_demand", "待确认", status="MISSING")
    fields["effective_supply"] = summary(
        "effective_supply", "待确认", status="MISSING"
    )

    item = build_cycle_reversal_report(
        situation_report(fields=fields)
    )["items"][0]

    assert item["cycle_reversal_gate_state"] == "PARTIAL"
    assert item["cycle_reversal_state"] == "PRICE_REBOUND"


def test_non_cyclical_industry_is_not_applicable():
    fields = complete_fields("INDUSTRIAL_REVERSAL_CONFIRMED")
    fields["industry_applicability"] = summary("industry_applicability", False)

    item = build_cycle_reversal_report(
        situation_report(fields=fields)
    )["items"][0]

    assert item["cycle_reversal_gate_state"] == "NOT_APPLICABLE"
    assert item["cycle_reversal_state"] == "NOT_APPLICABLE"
    assert item["allowed_actions"] == ["evidence_refresh"]


def test_reversal_confirmation_is_blocked_when_cashflow_is_missing():
    fields = complete_fields("INDUSTRIAL_REVERSAL_CONFIRMED")
    fields["industry_cashflow"] = summary(
        "industry_cashflow", "待确认", status="UNVERIFIED", tier="C"
    )

    item = build_cycle_reversal_report(
        situation_report(fields=fields)
    )["items"][0]

    assert item["cycle_reversal_gate_state"] == "INSUFFICIENT"
    assert item["cycle_reversal_state"] == "INSUFFICIENT_EVIDENCE"
    assert item["reasons"] == ["CYCLE_STATE_EVIDENCE_INSUFFICIENT"]


def test_cycle_reversal_rejects_unknown_state_and_wrong_schema():
    fields = complete_fields("UNKNOWN")
    with pytest.raises(CycleReversalError, match="cycle_state"):
        build_cycle_reversal_report(situation_report(fields=fields))

    with pytest.raises(CycleReversalError, match="industry-situation.v1"):
        build_cycle_reversal_report({"schema_version": "other", "items": []})
