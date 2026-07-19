import pytest

from industry_first_research.adversarial_review import (
    AdversarialReviewError,
    build_adversarial_review_report,
)


def summary(field, value, *, status="VERIFIED", tier="A", as_of="2026-07-19"):
    return {
        "status": status,
        "values": [value],
        "evidence_ids": [field],
        "sources": ["https://example.test/official"],
        "as_of": [as_of],
        "evidence_tiers": [tier],
    }


def valuation_report(*, fields=None, item_overrides=None, policy=None):
    item = {
        "company_id": "300317",
        "display_name": "珈伟新能",
        "industry_id": "881145",
        "candidate_state": "WATCH",
        "candidate_state_changed": False,
        "candidate_rule_version": "company-candidate-queue-rules.v1",
        "valuation_gate_state": "READY",
        "numeric_valuation_included": False,
        "target_price_generated": False,
        "fields": fields or {},
        "evidence_ids": ["valuation"],
    }
    item.update(item_overrides or {})
    return {
        "schema_version": "company-valuation-scenarios.v1",
        "report_id": "valuation-001",
        "input_survival_analysis_id": "survival-001",
        "as_of": "2026-07-19",
        "source": "manual",
        "policy": {
            "target_price_generated": False,
            "investment_conclusion": False,
            **(policy or {}),
        },
        "items": [item],
    }


def clean_fields():
    return {
        "counterevidence": summary("counterevidence", ["需求下修会推翻判断"]),
        "invalidators": summary("invalidators", ["现金流连续恶化"]),
        "profit_cashflow_evidence": summary(
            "profit_cashflow_evidence", "经营现金流已核验"
        ),
        "excluded_from_base_case": summary(
            "excluded_from_base_case", ["未验证风口业务"]
        ),
        "product_financial_bridge": summary(
            "product_financial_bridge", "收入到现金流桥接"
        ),
    }


def market_structure_report(*, signal=None, policy=None):
    return {
        "schema_version": "market-structure-snapshot.v1",
        "report_id": "market-001",
        "policy": {
            "trading_signal_included": False,
            "automatic_order_included": False,
            **(policy or {}),
        },
        "timeframes": {"daily": {"signal": signal}},
    }


def test_adversarial_review_passes_clean_package():
    report = build_adversarial_review_report(
        valuation_report(fields=clean_fields()),
        market_structure_report=market_structure_report(),
    )

    item = report["items"][0]
    assert report["schema_version"] == "company-adversarial-review.v1"
    assert item["audit_state"] == "PASS"
    assert item["reasons"] == []
    assert item["candidate_state_changed"] is False
    assert item["allowed_actions"] == [
        "decision_snapshot_review",
        "evidence_refresh",
    ]


def test_future_evidence_blocks_review():
    fields = clean_fields()
    fields["counterevidence"] = summary(
        "counterevidence", ["future fact"], as_of="2026-07-20"
    )

    item = build_adversarial_review_report(
        valuation_report(fields=fields)
    )["items"][0]

    assert item["audit_state"] == "BLOCKED"
    assert "FUTURE_INFORMATION" in item["reasons"]


def test_missing_counterevidence_and_cashflow_are_review_findings():
    fields = {
        "excluded_from_base_case": clean_fields()["excluded_from_base_case"]
    }
    item = build_adversarial_review_report(
        valuation_report(fields=fields)
    )["items"][0]

    assert item["audit_state"] == "REVIEW"
    assert "COUNTEREVIDENCE_PRESENT" in item["reasons"]
    assert "CASHFLOW_CONVERSION" in item["reasons"]


def test_boundary_violations_block_and_market_size_leak_is_reviewed():
    fields = clean_fields()
    fields["market_size"] = summary("market_size", "large market")
    item = build_adversarial_review_report(
        valuation_report(
            fields=fields,
            item_overrides={"target_price_generated": True},
        ),
        market_structure_report=market_structure_report(signal="BUY"),
    )["items"][0]

    assert item["audit_state"] == "BLOCKED"
    assert "VALUATION_OUTPUT_BOUNDARY" in item["reasons"]
    assert "MARKET_STRUCTURE_SIGNAL_BOUNDARY" in item["reasons"]
    assert item["findings"][-1]["status"] == "PASS"


def test_adversarial_review_rejects_wrong_schema():
    with pytest.raises(AdversarialReviewError, match="valuation-scenarios.v1"):
        build_adversarial_review_report({"schema_version": "other", "items": []})
