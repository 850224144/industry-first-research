import pytest

from industry_first_research.product_profile import (
    ProductProfileError,
    build_product_profile_report,
)


def supplemental(candidate_state="WATCH", supplemental_state="PARTIAL", records=None):
    return {
        "schema_version": "company-supplemental-evidence.v1",
        "report_id": "supplemental-001",
        "input_queue_id": "queue-001",
        "input_snapshot_id": "pool-001",
        "as_of": "2026-07-19",
        "source": "manual",
        "items": [
            {
                "company_id": "300317",
                "display_name": "珈伟新能",
                "industry_id": "881145",
                "candidate_state": candidate_state,
                "candidate_rule_version": "company-candidate-queue-rules.v1",
                "candidate_reasons": [],
                "candidate_blockers": [],
                "candidate_evidence_gaps": [],
                "candidate_field_sources": {},
                "candidate_additional_sources": [],
                "supplemental_state": supplemental_state,
            }
        ],
        "records": records or [],
    }


def record(evidence_id, field, value, *, tier="A", status="VERIFIED"):
    return {
        "evidence_id": evidence_id,
        "company_id": "300317",
        "field": field,
        "value": value,
        "source": "https://example.test/official",
        "as_of": "2026-07-19",
        "evidence_tier": tier,
        "verification_status": status,
    }


def test_product_profile_is_partial_when_product_evidence_is_missing():
    report = build_product_profile_report(
        supplemental(
            records=[record("scope", "company_scope", "珈伟新能源股份有限公司")]
        )
    )

    item = report["items"][0]
    assert report["schema_version"] == "company-product-profile.v1"
    assert item["product_profile_state"] == "PARTIAL"
    assert "product_list" in item["unknowns"]
    assert item["downstream_modules"]["valuation"] == "READY_REQUIRED"
    assert "valuation" in item["prohibited_actions"]


def test_product_profile_ready_requires_all_product_fields_verified():
    fields = [
        "product_list",
        "product_application",
        "customer_purchase_reasons",
        "product_system_layer",
        "product_criticality",
        "substitution_risk",
        "competitors",
        "market_state",
        "profit_sources",
        "product_financial_bridge",
        "lifecycle_state",
        "validation_state",
    ]
    records = [record("scope", "company_scope", "珈伟新能源股份有限公司")]
    records.extend(record(field, field, field) for field in fields)

    item = build_product_profile_report(
        supplemental(
            supplemental_state="READY",
            records=records,
        )
    )["items"][0]

    assert item["product_profile_state"] == "READY"
    assert item["unknowns"] == []
    assert item["allowed_actions"] == ["application_mapping", "evidence_refresh"]


def test_product_profile_blocks_missing_company_scope():
    report = build_product_profile_report(
        supplemental(
            records=[record("product", "product_list", ["光伏消费产品"])]
        )
    )

    item = report["items"][0]
    assert item["product_profile_state"] == "BLOCKED"
    assert item["scope_state"] == "MISSING"
    assert item["allowed_actions"] == ["scope_resolution", "evidence_refresh"]


def test_product_profile_rejects_wrong_schema_and_unsupported_candidate():
    with pytest.raises(ProductProfileError, match="supplemental-evidence.v1"):
        build_product_profile_report({"schema_version": "other", "items": []})

    payload = supplemental()
    payload["items"][0]["candidate_state"] = "UNKNOWN"
    with pytest.raises(ProductProfileError, match="candidate_state"):
        build_product_profile_report(payload)
