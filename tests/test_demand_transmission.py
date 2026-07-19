import pytest

from industry_first_research.demand_transmission import (
    DemandTransmissionError,
    build_demand_transmission_report,
)


REQUIRED_FIELDS = [
    "demand_evidence",
    "technical_feasibility",
    "customer_validation",
    "order_evidence",
    "shipment_revenue_evidence",
    "profit_cashflow_evidence",
    "company_supply_capability",
    "company_share_evidence",
    "competitive_capture",
    "base_case_contribution",
    "upside_option",
    "invalidators",
    "transmission_state",
]


def mapping_report(*, state="READY", fields=None):
    return {
        "schema_version": "company-application-mapping.v1",
        "report_id": "mapping-001",
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
                "mapping_state": state,
                "rule_version": "company-application-mapping-rules.v1",
                "fields": fields or {},
                "evidence_ids": ["mapping"],
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


def complete_fields(state="PROFIT_VALIDATED"):
    fields = {
        field: summary(field, field)
        for field in REQUIRED_FIELDS
        if field != "transmission_state"
    }
    fields["transmission_state"] = summary("transmission_state", state)
    return fields


def test_profit_validation_is_supported_and_kept_out_of_valuation():
    report = build_demand_transmission_report(
        mapping_report(fields=complete_fields())
    )

    item = report["items"][0]
    assert report["schema_version"] == "company-demand-transmission.v1"
    assert item["transmission_gate_state"] == "READY"
    assert item["transmission_state"] == "PROFIT_VALIDATED"
    assert item["max_evidence_supported_state"] == "COMPETITIVE_VALIDATED"
    assert item["base_case_treatment"] == "EVIDENCE_BACKED_PROFIT_CONTRIBUTION"
    assert "valuation" in item["prohibited_actions"]


def test_order_validation_is_only_an_upside_option():
    fields = complete_fields("ORDER_VALIDATED")
    fields["shipment_revenue_evidence"] = summary(
        "shipment_revenue_evidence", "待验证", status="MISSING"
    )
    fields["profit_cashflow_evidence"] = summary(
        "profit_cashflow_evidence", "待验证", status="MISSING"
    )

    item = build_demand_transmission_report(
        mapping_report(fields=fields)
    )["items"][0]

    assert item["transmission_gate_state"] == "PARTIAL"
    assert item["transmission_state"] == "ORDER_VALIDATED"
    assert item["max_evidence_supported_state"] == "ORDER_VALIDATED"
    assert item["base_case_treatment"] == "UPSIDE_OPTION_ONLY"


def test_claimed_profit_state_is_blocked_when_profit_evidence_is_missing():
    fields = complete_fields("PROFIT_VALIDATED")
    fields["profit_cashflow_evidence"] = summary(
        "profit_cashflow_evidence", "未披露", status="UNVERIFIED", tier="C"
    )

    item = build_demand_transmission_report(
        mapping_report(fields=fields)
    )["items"][0]

    assert item["transmission_gate_state"] == "BLOCKED"
    assert item["state_validation"] == "CONFLICTING"
    assert item["reasons"] == ["TRANSMISSION_STATE_CONFLICT"]


def test_transmission_rejects_unknown_state_and_wrong_schema():
    fields = complete_fields("NOT_A_STATE")
    with pytest.raises(DemandTransmissionError, match="transmission_state"):
        build_demand_transmission_report(mapping_report(fields=fields))

    with pytest.raises(DemandTransmissionError, match="application-mapping.v1"):
        build_demand_transmission_report({"schema_version": "other", "items": []})
