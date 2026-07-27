import pytest

from industry_first_research.company_scope import (
    CompanyScopeError,
    build_company_scope_report,
    validate_company_scope_report,
)


def scope_input():
    return {
        "schema_version": "company-scope-input.v1",
        "company_id": "600438.SH",
        "display_name": "通威股份",
        "as_of": "2026-07-18",
        "objects": [
            {
                "object_id": "600438.SH",
                "object_type": "ListedEntity",
                "legal_name": "通威股份有限公司",
                "consolidation_method": "CONSOLIDATED",
            },
            {
                "object_id": "group-600438",
                "object_type": "ConsolidatedGroup",
                "parent_entity_id": "600438.SH",
                "consolidation_method": "CONSOLIDATED",
            },
            {
                "object_id": "associate-1",
                "object_type": "Associate",
                "ownership_percent": 30,
                "consolidation_method": "EQUITY_METHOD",
            },
        ],
        "facts": [
            {
                "fact_id": "scope-product",
                "object_id": "group-600438",
                "field": "product_ownership",
                "value": ["高纯晶硅"],
                "transmission_to_listed": "CONSOLIDATED",
                "evidence_ids": ["ev-1"],
                "verification_status": "VERIFIED",
            },
            {
                "fact_id": "scope-revenue",
                "object_id": "600438.SH",
                "field": "revenue_attribution",
                "value": "consolidated",
                "transmission_to_listed": "DIRECT",
                "evidence_ids": ["ev-2"],
                "verification_status": "VERIFIED",
            },
        ],
    }


def test_company_scope_keeps_object_ownership_and_degrades_missing_fields():
    report = build_company_scope_report(scope_input())
    assert report["schema_version"] == "company-scope.v1"
    assert report["researchability_state"] == "PARTIAL"
    assert report["field_status"]["product_ownership"] == "VERIFIED"
    assert report["field_status"]["revenue_attribution"] == "VERIFIED"
    assert report["field_status"]["debt_attribution"] == "MISSING"
    assert report["object_counts"]["Associate"] == 1
    assert validate_company_scope_report(report)["status"] == "VALID"


def test_company_scope_rejects_unconsolidated_fact_as_direct_transmission():
    payload = scope_input()
    payload["facts"].append(
        {
            "fact_id": "bad-associate",
            "object_id": "associate-1",
            "field": "profit_attribution",
            "value": 100,
            "transmission_to_listed": "DIRECT",
            "evidence_ids": ["ev-3"],
        }
    )
    with pytest.raises(CompanyScopeError, match="cannot use DIRECT"):
        build_company_scope_report(payload)


def test_company_scope_rejects_future_fact_and_hash_tampering():
    payload = scope_input()
    payload["facts"][0]["as_of"] = "2026-07-19"
    with pytest.raises(CompanyScopeError, match="after as_of"):
        build_company_scope_report(payload)
    report = build_company_scope_report(scope_input())
    report["objects"][0]["display_name"] = "篡改"
    assert validate_company_scope_report(report)["status"] == "INVALID"


def test_company_scope_allows_same_field_on_different_scope_objects():
    payload = scope_input()
    payload["facts"].append(
        {
            "fact_id": "associate-revenue",
            "object_id": "associate-1",
            "field": "revenue_attribution",
            "value": "权益法投资收益",
            "transmission_to_listed": "EQUITY_METHOD",
            "evidence_ids": ["ev-associate-revenue"],
            "verification_status": "VERIFIED",
        }
    )
    report = build_company_scope_report(payload)
    assert report["field_status"]["revenue_attribution"] == "VERIFIED"
