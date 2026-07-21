import pytest

from industry_first_research.holding_thesis import (
    HoldingThesisError,
    build_holding_thesis,
)


def thesis(**overrides):
    payload = {
        "schema_version": "holding-thesis.v1",
        "thesis_id": "thesis-001",
        "company_id": "600519",
        "version": 1,
        "core_thesis": "主业现金流稳定，行业调整中龙头具备下行保护，等待经营验证而非追逐价格波动。",
        "hypotheses": [
            {
                "hypothesis_id": "H1",
                "statement": "经营现金流保持正值",
                "field": "operating_cashflow",
                "expected_direction": "IMPROVING",
                "validation_frequency": "quarterly",
                "evidence_ids": ["cash-1"],
            },
            {
                "hypothesis_id": "H2",
                "statement": "核心产品仍有客户需求",
                "field": "customer_validation",
                "operator": "equals",
                "expected_value": "VERIFIED",
                "validation_frequency": "quarterly",
                "evidence_ids": ["customer-1"],
            },
            {
                "hypothesis_id": "H3",
                "statement": "行业库存不过度累积",
                "field": "inventory_state",
                "operator": "not_equals",
                "expected_value": "HIGH",
                "validation_frequency": "monthly",
                "evidence_ids": ["inventory-1"],
            },
        ],
        "red_lines": [
            {
                "red_line_id": "R1",
                "statement": "经营现金流持续转负",
                "field": "operating_cashflow",
                "severity": "FATAL",
                "operator": "lt",
                "expected_value": 0,
                "action": "重新评估论文",
            }
        ],
        "normal_volatility": {"price_drawdown": "30%", "verification_gap": "1 quarter"},
        "valuation_anchors": {"bear": "low", "base": "mid", "bull": "high"},
        "timebox": {
            "expected_horizon": "12 months",
            "maximum_extension_until": "2028-01-01",
            "next_check_at": "2026-10-30",
        },
        "relative_opportunity": {"compare_on": ["survival", "cashflow", "valuation"]},
        "source_research_id": "research-001",
    }
    payload.update(overrides)
    return payload


def test_thesis_can_be_drafted_but_only_user_confirmation_locks_it():
    draft = build_holding_thesis(thesis(), user_confirmed=False)
    assert draft["lock_status"] == "DRAFT"
    assert draft["immutable"] is False
    assert draft["policy"]["execution_enabled"] is False

    locked = build_holding_thesis(thesis(), user_confirmed=True)
    assert locked["lock_status"] == "LOCKED"
    assert locked["immutable"] is True
    assert locked["user_confirmed"] is True
    assert locked["policy"]["original_version_not_overwritable"] is True


def test_revision_requires_new_version_and_reason():
    old = build_holding_thesis(thesis(), user_confirmed=True)
    revised_input = thesis(
        thesis_id="thesis-002",
        version=2,
        supersedes_thesis_id=old["thesis_id"],
        revision_reason="新增财报改变现金流假设",
    )
    revised = build_holding_thesis(
        revised_input,
        user_confirmed=True,
        previous_thesis=old,
    )
    assert revised["version"] == 2
    assert revised["supersedes_thesis_id"] == old["thesis_id"]

    with pytest.raises(HoldingThesisError, match="revision_reason"):
        build_holding_thesis(
            thesis(
                thesis_id="thesis-002",
                version=2,
                supersedes_thesis_id=old["thesis_id"],
            ),
            user_confirmed=True,
        )


def test_thesis_requires_three_to_seven_hypotheses_and_complete_contract():
    with pytest.raises(HoldingThesisError, match="3-7"):
        build_holding_thesis(thesis(hypotheses=[]), user_confirmed=True)
    with pytest.raises(HoldingThesisError, match="core_thesis"):
        build_holding_thesis(thesis(core_thesis=""), user_confirmed=True)
    with pytest.raises(HoldingThesisError, match="red line"):
        build_holding_thesis(
            thesis(red_lines=[{"red_line_id": "R1", "field": "cashflow"}]),
            user_confirmed=True,
        )
