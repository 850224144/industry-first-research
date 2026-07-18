"""Deterministic opportunity checks used before any semantic deep research.

These checks are deliberately conservative. They classify evidence readiness for
the research queue; they never create a trading instruction or a valuation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import CompanyCandidate, IndustryRadarSnapshot, IndustryState


_ELIGIBLE_STATES = {
    IndustryState.CLEARING,
    IndustryState.INFLECTION_CANDIDATE,
    IndustryState.REVERSAL_CONFIRMED,
}

_POSITIVE_VALUES = {
    "confirmed",
    "improving",
    "falling",
    "low",
    "near_cash_cost",
    "above_cash_cost",
    "narrowing",
    "visible",
}


def assess_industry_opportunities(
    snapshot: IndustryRadarSnapshot,
) -> dict[str, dict[str, Any]]:
    """Return explainable industry-level readiness for configured opportunity types."""

    assessments: dict[str, dict[str, Any]] = {}
    for opportunity_type in snapshot.opportunity_types:
        if opportunity_type == "cycle_reversal":
            assessments[opportunity_type] = _assess_cycle_reversal(snapshot)
        elif opportunity_type == "quality_repair":
            assessments[opportunity_type] = {
                "status": "SCOPE_ONLY" if snapshot.state in _ELIGIBLE_STATES else "BLOCKED",
                "score": 0,
                "reasons": ["质量修复需要在入选行业的公司层验证"],
                "missing": [
                    "现金跑道与债务到期",
                    "治理与融资风险",
                    "产品竞争力与盈利修复",
                    "估值安全边际",
                ],
            }
        else:
            assessments[opportunity_type] = {
                "status": "UNSUPPORTED",
                "score": 0,
                "reasons": [],
                "missing": ["首期没有该机会类型的确定性规则"],
            }
    return assessments


def assess_company_opportunities(
    candidate: CompanyCandidate,
    industry_assessments: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Assess company evidence without silently treating a score as a conclusion."""

    if candidate.hard_gate_status in {"REJECTED", "BLOCKED"}:
        return {
            opportunity_type: {
                "status": "BLOCKED",
                "score": 0,
                "reasons": [f"公司硬闸门状态为 {candidate.hard_gate_status}"],
                "missing": [],
            }
            for opportunity_type in industry_assessments
        }

    assessments: dict[str, dict[str, Any]] = {}
    for opportunity_type, industry_assessment in industry_assessments.items():
        if opportunity_type == "cycle_reversal":
            assessments[opportunity_type] = _assess_company_cycle(
                candidate, industry_assessment
            )
        elif opportunity_type == "quality_repair":
            assessments[opportunity_type] = _assess_company_quality_repair(candidate)
    return assessments


def _assess_cycle_reversal(snapshot: IndustryRadarSnapshot) -> dict[str, Any]:
    values = {signal.name: str(signal.value).lower() for signal in snapshot.signals}
    positive_signals = [
        name for name, value in values.items() if value in _POSITIVE_VALUES
    ]
    structural = snapshot.state in _ELIGIBLE_STATES
    score = len(positive_signals) + int(structural)
    missing = [
        label
        for name, label in (
            ("inventory", "库存下降且不反弹"),
            ("channel_price", "价格高于综合拿货/现金成本"),
            ("consumer_demand", "真实需求或动销改善"),
            ("profitability", "行业利润或现金流改善"),
        )
        if name not in values or values[name] not in _POSITIVE_VALUES
    ]
    if (
        snapshot.state == IndustryState.REVERSAL_CONFIRMED
        and snapshot.evidence_completeness in {"VERIFIED", "CROSS_VALIDATED"}
        and score >= 3
    ):
        status = "PASS"
    elif structural and score >= 2:
        status = "WATCH"
    else:
        status = "INSUFFICIENT"
    return {
        "status": status,
        "score": score,
        "reasons": [
            f"行业状态={snapshot.state.value}",
            f"已识别支持信号={', '.join(positive_signals) or '无'}",
        ],
        "missing": missing,
    }


def _assess_company_cycle(
    candidate: CompanyCandidate,
    industry_assessment: Mapping[str, Any],
) -> dict[str, Any]:
    inputs = _screening_inputs(candidate)
    survival = str(inputs.get("survival", "")).lower()
    if survival in {"strong", "adequate"} and industry_assessment.get("status") in {
        "PASS",
        "WATCH",
    }:
        return {
            "status": "WATCH",
            "score": 2 if survival == "strong" else 1,
            "reasons": ["公司生存能力输入已提供", "行业处于可研究状态"],
            "missing": ["产品利润和现金流对行业反转的传导证据"],
        }
    return {
        "status": "INSUFFICIENT",
        "score": 0,
        "reasons": ["行业信号只能筛选行业，不能替代公司受益验证"],
        "missing": [
            "现金跑道与债务到期",
            "有效产能/成本位置",
            "产品收入、利润和现金流传导",
        ],
    }


def _assess_company_quality_repair(candidate: CompanyCandidate) -> dict[str, Any]:
    inputs = _screening_inputs(candidate)
    required = (
        "survival",
        "balance_sheet",
        "governance",
        "product_competitiveness",
        "valuation_gap",
    )
    missing = [field for field in required if field not in inputs]
    if missing:
        return {
            "status": "INSUFFICIENT",
            "score": 0,
            "reasons": ["八指标/公司分数只能作为初筛，不能单独证明质量修复"],
            "missing": missing,
        }

    positive = 0
    adverse = []
    for field in required:
        value = str(inputs[field]).lower()
        if value in {"strong", "adequate", "improving", "cheap", "low"}:
            positive += 1
        if value in {"weak", "deteriorating", "expensive", "high"}:
            adverse.append(field)
    if positive == len(required):
        status = "PASS"
    elif positive >= 3 and not adverse:
        status = "WATCH"
    else:
        status = "INSUFFICIENT"
    return {
        "status": status,
        "score": positive,
        "reasons": [f"通过确定性字段 {positive}/{len(required)}"],
        "missing": adverse,
    }


def _screening_inputs(candidate: CompanyCandidate) -> dict[str, Any]:
    value = candidate.metadata.get("screening_inputs", {})
    return dict(value) if isinstance(value, Mapping) else {}
