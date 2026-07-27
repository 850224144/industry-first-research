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

_DEMAND_SIGNAL_GROUPS = {
    "demand": (
        "demand",
        "real_demand",
        "demand_growth",
        "penetration",
        "adoption",
    ),
    "orders": (
        "orders",
        "order_growth",
        "order_book",
        "customer_capex",
        "downstream_capex",
    ),
    "shipments": (
        "shipments",
        "shipment_growth",
        "sales_volume",
        "sell_through",
    ),
    "economics": (
        "industry_profit",
        "profit_growth",
        "margin",
        "cashflow",
        "operating_cashflow",
    ),
}

_BOTTLENECK_SIGNAL_GROUPS = {
    "scarcity": (
        "lead_time",
        "delivery_lead_time",
        "inventory",
        "inventory_days",
        "capacity_utilization",
        "utilization",
    ),
    "pricing": (
        "price",
        "spot_price",
        "contract_price",
        "price_spread",
        "margin",
        "pricing_power",
    ),
    "barrier": (
        "substitution_difficulty",
        "substitutability",
        "expansion_lead_time",
        "qualification_cycle",
        "capacity_constraint",
    ),
}

_DEMAND_POSITIVE = _POSITIVE_VALUES | {
    "accelerating",
    "increasing",
    "rising",
    "up",
    "growth",
    "high",
    "strong",
}

_BOTTLENECK_POSITIVE = _POSITIVE_VALUES | {
    "accelerating",
    "increasing",
    "rising",
    "up",
    "high",
    "full",
    "near_capacity",
    "tight",
    "extended",
    "long",
    "difficult",
    "limited",
    "low_substitutability",
}

_NEGATIVE_VALUES = {
    "deteriorating",
    "declining",
    "falling",
    "weak",
    "low",
    "stagnant",
    "failed",
    "short",
    "easy",
    "high_substitutability",
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
        elif opportunity_type == "demand_acceleration":
            assessments[opportunity_type] = _assess_demand_acceleration(snapshot)
        elif opportunity_type == "bottleneck_pricing":
            assessments[opportunity_type] = _assess_bottleneck_pricing(snapshot)
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
        elif opportunity_type == "demand_acceleration":
            assessments[opportunity_type] = _assess_company_demand_acceleration(
                candidate, industry_assessment
            )
        elif opportunity_type == "bottleneck_pricing":
            assessments[opportunity_type] = _assess_company_bottleneck_pricing(
                candidate, industry_assessment
            )
        else:
            assessments[opportunity_type] = {
                "status": "UNSUPPORTED",
                "score": 0,
                "reasons": [],
                "missing": ["该机会类型的确定性规则"],
            }
    return assessments


def _assess_demand_acceleration(snapshot: IndustryRadarSnapshot) -> dict[str, Any]:
    """Require independent demand, order and commercial evidence.

    A single price, index or market-volume observation must not upgrade a
    demand opportunity.  The output is a queue status only.
    """

    signal_map = _signal_map(snapshot)
    groups = _assess_signal_groups(signal_map, _DEMAND_SIGNAL_GROUPS, "demand")
    positive_groups = [name for name, item in groups.items() if item["positive"]]
    verified_groups = [
        name
        for name, item in groups.items()
        if item["positive"] and item["verified"]
    ]
    structural = snapshot.state in _ELIGIBLE_STATES
    score = len(positive_groups) + int(structural)
    missing = [
        {
            "demand": "真实需求或渗透率连续改善",
            "orders": "客户订单或下游资本开支改善",
            "shipments": "出货、销量或终端动销改善",
            "economics": "行业利润或经营现金流改善",
        }[name]
        for name, item in groups.items()
        if not item["positive"]
    ]
    if (
        structural
        and len(positive_groups) >= 3
        and len(verified_groups) >= 2
        and snapshot.evidence_completeness in {"VERIFIED", "CROSS_VALIDATED"}
    ):
        status = "PASS"
    elif structural and len(positive_groups) >= 2:
        status = "WATCH"
    else:
        status = "INSUFFICIENT"
    return {
        "status": status,
        "score": score,
        "positive_signal_groups": positive_groups,
        "verified_signal_groups": verified_groups,
        "reasons": [
            f"行业状态={snapshot.state.value}",
            f"需求加速证据组={', '.join(positive_groups) or '无'}",
        ],
        "missing": missing,
        "policy": {
            "independent_signal_groups_required": 2,
            "price_only_cannot_upgrade": True,
            "not_investment_conclusion": True,
        },
    }


def _assess_bottleneck_pricing(snapshot: IndustryRadarSnapshot) -> dict[str, Any]:
    """Require scarcity, pricing and barrier evidence for a bottleneck claim."""

    signal_map = _signal_map(snapshot)
    groups = _assess_signal_groups(signal_map, _BOTTLENECK_SIGNAL_GROUPS, "bottleneck")
    positive_groups = [name for name, item in groups.items() if item["positive"]]
    verified_groups = [
        name
        for name, item in groups.items()
        if item["positive"] and item["verified"]
    ]
    structural = snapshot.state in _ELIGIBLE_STATES
    score = len(positive_groups) + int(structural)
    missing = [
        {
            "scarcity": "交期、库存或利用率证明供给紧张",
            "pricing": "现货/合同价格、价差或利润率改善",
            "barrier": "替代困难、认证周期或扩产周期较长",
        }[name]
        for name, item in groups.items()
        if not item["positive"]
    ]
    if (
        structural
        and len(positive_groups) == len(_BOTTLENECK_SIGNAL_GROUPS)
        and len(verified_groups) >= 2
        and snapshot.evidence_completeness in {"VERIFIED", "CROSS_VALIDATED"}
    ):
        status = "PASS"
    elif structural and len(positive_groups) >= 2:
        status = "WATCH"
    else:
        status = "INSUFFICIENT"
    return {
        "status": status,
        "score": score,
        "positive_signal_groups": positive_groups,
        "verified_signal_groups": verified_groups,
        "reasons": [
            f"行业状态={snapshot.state.value}",
            f"瓶颈证据组={', '.join(positive_groups) or '无'}",
        ],
        "missing": missing,
        "policy": {
            "scarcity_pricing_barrier_required": True,
            "price_only_cannot_upgrade": True,
            "not_investment_conclusion": True,
        },
    }


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


def _assess_company_demand_acceleration(
    candidate: CompanyCandidate,
    industry_assessment: Mapping[str, Any],
) -> dict[str, Any]:
    inputs = _specific_screening_inputs(candidate, "demand_acceleration")
    groups = {
        "customer": ("customer_validation", "customer_adoption", "certification", "orders"),
        "commercial": ("shipment_validation", "shipments", "revenue_growth", "revenue_validation", "market_share"),
        "economics": ("profit_validation", "profit_growth", "operating_cashflow", "cashflow_validation", "margin"),
    }
    assessed = _assess_input_groups(inputs, groups, "demand")
    positive = [name for name, item in assessed.items() if item["positive"]]
    missing = [
        {
            "customer": "客户认证、订单或客户导入",
            "commercial": "出货、收入或市场份额验证",
            "economics": "利润或经营现金流验证",
        }[name]
        for name, item in assessed.items()
        if not item["positive"]
    ]
    industry_status = str(industry_assessment.get("status") or "")
    if len(positive) == len(groups) and industry_status == "PASS":
        status = "PASS"
    elif len(positive) >= 2 and industry_status in {"PASS", "WATCH"}:
        status = "WATCH"
    else:
        status = "INSUFFICIENT"
    return {
        "status": status,
        "score": len(positive),
        "positive_evidence_groups": positive,
        "reasons": ["公司层需求加速必须逐级验证客户、商业化和经济结果"],
        "missing": missing,
        "policy": {"concept_only_is_insufficient": True, "not_investment_conclusion": True},
    }


def _assess_company_bottleneck_pricing(
    candidate: CompanyCandidate,
    industry_assessment: Mapping[str, Any],
) -> dict[str, Any]:
    inputs = _specific_screening_inputs(candidate, "bottleneck_pricing")
    groups = {
        "criticality": ("product_criticality", "critical_component", "substitutability", "replacement_difficulty"),
        "pricing": ("pricing_power", "price_increase", "contract_price", "spot_price", "margin"),
        "exposure": ("revenue_exposure", "profit_exposure", "revenue_validation", "cashflow_validation", "orders"),
    }
    assessed = _assess_input_groups(inputs, groups, "bottleneck")
    positive = [name for name, item in assessed.items() if item["positive"]]
    missing = [
        {
            "criticality": "产品关键程度和替代难度",
            "pricing": "公司层定价或利润率改善",
            "exposure": "收入、利润或现金流暴露已经验证",
        }[name]
        for name, item in assessed.items()
        if not item["positive"]
    ]
    industry_status = str(industry_assessment.get("status") or "")
    if len(positive) == len(groups) and industry_status == "PASS":
        status = "PASS"
    elif len(positive) >= 2 and industry_status in {"PASS", "WATCH"}:
        status = "WATCH"
    else:
        status = "INSUFFICIENT"
    return {
        "status": status,
        "score": len(positive),
        "positive_evidence_groups": positive,
        "reasons": ["瓶颈涨价必须证明稀缺性如何传导到该公司的利润和现金流"],
        "missing": missing,
        "policy": {"concept_only_is_insufficient": True, "price_only_is_insufficient": True, "not_investment_conclusion": True},
    }


def _screening_inputs(candidate: CompanyCandidate) -> dict[str, Any]:
    value = candidate.metadata.get("screening_inputs", {})
    return dict(value) if isinstance(value, Mapping) else {}


def _specific_screening_inputs(
    candidate: CompanyCandidate, opportunity_type: str
) -> dict[str, Any]:
    inputs = _screening_inputs(candidate)
    specific = inputs.get(opportunity_type, {})
    if not isinstance(specific, Mapping):
        return inputs
    merged = dict(inputs)
    merged.update(specific)
    return merged


def _signal_map(snapshot: IndustryRadarSnapshot) -> dict[str, tuple[Any, str]]:
    return {
        signal.name.strip().lower(): (signal.value, signal.evidence_status.upper())
        for signal in snapshot.signals
        if signal.name.strip()
    }


def _assess_signal_groups(
    signals: Mapping[str, tuple[Any, str]],
    groups: Mapping[str, tuple[str, ...]],
    kind: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for group_name, names in groups.items():
        matched = []
        for name in names:
            if name not in signals:
                continue
            value, evidence_status = signals[name]
            if _is_positive_value(name, value, kind):
                matched.append(
                    {
                        "name": name,
                        "value": _value_status(value),
                        "evidence_status": evidence_status,
                    }
                )
        result[group_name] = {
            "positive": bool(matched),
            "verified": any(
                item["evidence_status"] in {"VERIFIED", "CROSS_VALIDATED"}
                for item in matched
            ),
            "matches": matched,
        }
    return result


def _assess_input_groups(
    inputs: Mapping[str, Any],
    groups: Mapping[str, tuple[str, ...]],
    kind: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for group_name, names in groups.items():
        matches = [
            name
            for name in names
            if name in inputs and _is_positive_value(name, inputs[name], kind)
        ]
        result[group_name] = {"positive": bool(matches), "matches": matches}
    return result


def _is_positive_value(name: str, value: Any, kind: str) -> bool:
    status = _value_status(value)
    if isinstance(value, Mapping):
        explicit = value.get("positive")
        if isinstance(explicit, bool):
            return explicit
    if isinstance(value, bool):
        return value
    if kind == "bottleneck" and name in {"substitutability", "replacement_difficulty"}:
        return status in {"low", "difficult", "limited", "hard", "low_substitutability"}
    if kind == "bottleneck" and name in {"lead_time", "delivery_lead_time", "expansion_lead_time", "qualification_cycle"}:
        return status in _BOTTLENECK_POSITIVE
    if kind == "bottleneck" and name in {"inventory", "inventory_days"}:
        return status in {"falling", "low", "tight", "declining"}
    if kind == "bottleneck" and name in {"price", "spot_price", "contract_price", "price_spread", "pricing_power", "margin"}:
        return status in {"rising", "increasing", "up", "improving", "expanding", "strong", "confirmed", "visible"}
    positive = _DEMAND_POSITIVE if kind == "demand" else _BOTTLENECK_POSITIVE
    return status in positive and status not in _NEGATIVE_VALUES


def _value_status(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("status", "state", "direction", "value"):
            if key in value:
                return str(value[key]).strip().lower()
    return str(value).strip().lower()
