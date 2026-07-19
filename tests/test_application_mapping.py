import pytest

from industry_first_research.application_mapping import (
    ApplicationMappingError,
    build_application_mapping_report,
)


REQUIRED_FIELDS = [
    "application_mapping",
    "application_end_market",
    "demand_driver",
    "customer_type",
    "customer_validation",
    "order_evidence",
    "shipment_revenue_evidence",
    "company_supply_capability",
    "application_competition",
    "transmission_state",
]


def product_profile(*, state="READY", fields=None):
    return {
        "schema_version": "company-product-profile.v1",
        "report_id": "product-profile-001",
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
                "product_profile_state": state,
                "scope_state": "VERIFIED",
                "rule_version": "company-product-profile-rules.v1",
                "fields": fields or {},
                "evidence_ids": ["scope", "product"],
            }
        ],
    }


def summary(field, value, *, status="VERIFIED"):
    return {
        "status": status,
        "values": [value],
        "evidence_ids": [field],
        "sources": ["https://example.test/official"],
        "as_of": ["2026-07-19"],
        "evidence_tiers": ["A"],
    }


def complete_fields():
    fields = {
        field: summary(field, field)
        for field in REQUIRED_FIELDS
        if field != "application_mapping"
    }
    fields["application_mapping"] = summary(
        "application_mapping",
        {
            "product": "光伏组件",
            "application": "分布式光伏发电",
            "end_market": "可再生能源发电",
            "role": "设备",
            "demand_driver": "客户资本开支",
        },
    )
    return fields


def test_mapping_is_ready_only_when_product_profile_and_mapping_evidence_are_ready():
    report = build_application_mapping_report(
        product_profile(fields=complete_fields())
    )

    item = report["items"][0]
    assert report["schema_version"] == "company-application-mapping.v1"
    assert item["mapping_state"] == "READY"
    assert item["mapping_entries"] == [
        {
            "product": "光伏组件",
            "application": "分布式光伏发电",
            "end_market": "可再生能源发电",
            "role": "设备",
            "demand_driver": "客户资本开支",
        }
    ]
    assert item["allowed_actions"] == ["demand_transmission", "evidence_refresh"]
    assert item["downstream_modules"]["valuation"] == "READY_REQUIRED"


def test_mapping_blocks_until_product_profile_is_ready():
    report = build_application_mapping_report(
        product_profile(state="PARTIAL", fields=complete_fields())
    )

    item = report["items"][0]
    assert item["mapping_state"] == "BLOCKED"
    assert item["reasons"] == ["PRODUCT_PROFILE_READY_REQUIRED"]
    assert item["allowed_actions"] == [
        "product_profile_resolution",
        "evidence_refresh",
    ]


def test_mapping_keeps_missing_application_relation_as_insufficient():
    fields = complete_fields()
    fields["application_mapping"] = summary(
        "application_mapping", [], status="VERIFIED"
    )

    item = build_application_mapping_report(
        product_profile(fields=fields)
    )["items"][0]

    assert item["mapping_state"] == "INSUFFICIENT"
    assert item["reasons"] == ["EXPLICIT_APPLICATION_MAPPING_MISSING"]
    assert item["mapping_entries"] == []


def test_mapping_rejects_malformed_mapping_and_wrong_schema():
    fields = complete_fields()
    fields["application_mapping"] = summary(
        "application_mapping", {"product": "光伏组件"}
    )
    with pytest.raises(ApplicationMappingError, match="missing: application"):
        build_application_mapping_report(product_profile(fields=fields))

    with pytest.raises(ApplicationMappingError, match="product-profile.v1"):
        build_application_mapping_report({"schema_version": "other", "items": []})
