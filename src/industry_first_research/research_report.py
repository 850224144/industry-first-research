"""Assemble a structured, evidence-bound company research report."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


class ResearchReportError(ValueError):
    """Raised when a structured research report cannot be assembled safely."""


RESEARCH_REPORT_SCHEMA_VERSION = "company-research-report.v1"
RULE_VERSION = "company-research-report-rules.v1"
ADVERSARIAL_REVIEW_SCHEMA_VERSION = "company-adversarial-review.v1"
_AUDIT_STATES = {"PASS", "REVIEW", "BLOCKED"}
_QUEUE_STATES = {"WATCH", "REVIEW", "CANDIDATE", "INSUFFICIENT", "REJECTED"}
_REPORT_STATES = {"REVIEWABLE", "REVIEW", "BLOCKED"}
_FOLLOW_UP_FIELDS = ("follow_up_checks", "next_check_at")


def build_research_report(
    adversarial_review_report: Mapping[str, Any],
    *,
    rule_version: str = RULE_VERSION,
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Create report sections and tracking items without inventing conclusions."""

    _validate_input(adversarial_review_report)
    if not rule_version.strip():
        raise ResearchReportError("rule_version must not be empty")

    items = [
        _build_item(item, rule_version=rule_version)
        for item in adversarial_review_report["items"]
    ]
    counts = Counter(item["report_state"] for item in items)
    input_report_id = str(adversarial_review_report.get("report_id") or "")
    report_id = snapshot_id or input_report_id or "adversarial-review-input"
    return {
        "schema_version": RESEARCH_REPORT_SCHEMA_VERSION,
        "report_id": f"company-research-report-{report_id}",
        "input_adversarial_review_id": input_report_id,
        "input_valuation_scenarios_id": str(
            adversarial_review_report.get("input_valuation_scenarios_id") or ""
        ),
        "input_survival_analysis_id": str(
            adversarial_review_report.get("input_survival_analysis_id") or ""
        ),
        "input_competitive_position_id": str(
            adversarial_review_report.get("input_competitive_position_id") or ""
        ),
        "input_cycle_reversal_id": str(
            adversarial_review_report.get("input_cycle_reversal_id") or ""
        ),
        "input_industry_situation_id": str(
            adversarial_review_report.get("input_industry_situation_id") or ""
        ),
        "input_demand_transmission_id": str(
            adversarial_review_report.get("input_demand_transmission_id") or ""
        ),
        "input_application_mapping_id": str(
            adversarial_review_report.get("input_application_mapping_id") or ""
        ),
        "input_product_profile_id": str(
            adversarial_review_report.get("input_product_profile_id") or ""
        ),
        "input_supplemental_id": str(
            adversarial_review_report.get("input_supplemental_id") or ""
        ),
        "input_queue_id": str(adversarial_review_report.get("input_queue_id") or ""),
        "input_snapshot_id": str(
            adversarial_review_report.get("input_snapshot_id") or ""
        ),
        "rule_version": rule_version,
        "as_of": str(adversarial_review_report.get("as_of") or ""),
        "source": str(adversarial_review_report.get("source") or ""),
        "source_metadata": adversarial_review_report.get("source_metadata") or {},
        "candidate_count": len(items),
        "report_state_counts": dict(counts),
        "items": items,
        "policy": {
            "structured_report_only": True,
            "evidence_bound": True,
            "candidate_state_preserved": True,
            "directional_investment_conclusion": False,
            "numeric_valuation_included": False,
            "target_price_generated": False,
            "decision_snapshot_created": False,
            "user_confirmation_required_for_simulation": True,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _validate_input(report: Any) -> None:
    if not isinstance(report, Mapping):
        raise ResearchReportError("input adversarial review must be a JSON object")
    if report.get("schema_version") != ADVERSARIAL_REVIEW_SCHEMA_VERSION:
        raise ResearchReportError(
            "input must be a company-adversarial-review.v1 report"
        )
    if not isinstance(report.get("items"), list):
        raise ResearchReportError("adversarial review has no items list")


def _build_item(item: Any, *, rule_version: str) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise ResearchReportError("each adversarial review item must be an object")
    company_id = str(item.get("company_id") or "").strip()
    candidate_state = str(item.get("candidate_state") or "").upper()
    audit_state = str(item.get("audit_state") or "").upper()
    if not company_id:
        raise ResearchReportError("adversarial review item company_id is required")
    if candidate_state not in _QUEUE_STATES:
        raise ResearchReportError(
            f"unsupported candidate_state: {candidate_state or '<empty>'}"
        )
    if audit_state not in _AUDIT_STATES:
        raise ResearchReportError(
            f"unsupported audit_state: {audit_state or '<empty>'}"
        )
    fields = item.get("fields") or {}
    if not isinstance(fields, Mapping):
        raise ResearchReportError("adversarial review item fields must be an object")
    report_state = _report_state(audit_state, candidate_state)
    follow_up_checks = _values(fields.get("follow_up_checks"))
    next_check_at = _single_value(fields.get("next_check_at"))
    sections = _sections(item, fields, report_state)
    tracking = _tracking(
        fields=fields,
        report_state=report_state,
        follow_up_checks=follow_up_checks,
        next_check_at=next_check_at,
    )
    return {
        "company_id": company_id,
        "company_scope": item.get("company_scope"),
        "display_name": str(item.get("display_name") or ""),
        "industry_id": str(item.get("industry_id") or ""),
        "candidate_state": candidate_state,
        "candidate_state_changed": False,
        "candidate_rule_version": str(item.get("candidate_rule_version") or ""),
        "audit_state": audit_state,
        "report_state": report_state,
        "rule_version": rule_version,
        "sections": sections,
        "tracking_checklist": tracking,
        "simulation_recommendation": _simulation_recommendation(
            report_state=report_state,
            candidate_state=candidate_state,
            tracking=tracking,
            sections=sections,
        ),
        "audit_findings": item.get("findings") or [],
        "reasons": _string_list(item.get("reasons")),
        "unknowns": _string_list(item.get("unknowns")),
        "evidence_ids": _string_list(item.get("evidence_ids")),
        "conclusion_state": _conclusion_state(report_state),
        "simulation_entry": "USER_CONFIRMATION_REQUIRED",
        "decision_snapshot_created": False,
        "numeric_valuation_included": False,
        "target_price_generated": False,
        "allowed_actions": _allowed_actions(report_state),
        "prohibited_actions": [
            "directional_investment_conclusion",
            "decision_snapshot_creation",
            "automatic_candidate_promotion",
            "execution",
        ],
        "review_only": True,
        "investment_conclusion": False,
    }


def _report_state(audit_state: str, candidate_state: str) -> str:
    if audit_state == "BLOCKED" or candidate_state in {"REJECTED", "INSUFFICIENT"}:
        return "BLOCKED"
    if audit_state == "REVIEW" or candidate_state == "REVIEW":
        return "REVIEW"
    return "REVIEWABLE"


def _conclusion_state(report_state: str) -> str:
    return {
        "REVIEWABLE": "EVIDENCE_ASSEMBLED_NO_DIRECTIONAL_CONCLUSION",
        "REVIEW": "CONDITIONAL_REVIEW_ONLY",
        "BLOCKED": "NO_CONCLUSION_DATA_GAP_OR_BLOCKER",
    }[report_state]


def _sections(
    item: Mapping[str, Any],
    fields: Mapping[str, Any],
    report_state: str,
) -> dict[str, dict[str, Any]]:
    return {
        "industry": _section(
            "industry_situation",
            item.get("input_industry_situation_id"),
            fields,
            ("industry_demand_horizon", "supply_demand_state", "cycle_stage"),
            report_state,
        ),
        "company_quality": _section(
            "competitive_position",
            item.get("input_competitive_position_id"),
            fields,
            ("business_model", "cost_position", "customer_position"),
            report_state,
        ),
        "product_and_transmission": _section(
            "product_and_demand_transmission",
            item.get("input_demand_transmission_id"),
            fields,
            ("product_list", "product_application", "transmission_state"),
            report_state,
        ),
        "survival": _section(
            "survival_and_stress",
            item.get("input_survival_analysis_id"),
            fields,
            ("available_cash", "stress_tests", "survival_label"),
            report_state,
        ),
        "valuation": _section(
            "valuation_framework",
            item.get("input_valuation_scenarios_id"),
            fields,
            ("scenario_inputs", "implied_assumptions", "valuation_sensitivity"),
            report_state,
        ),
        "risks_and_counterevidence": _section(
            "adversarial_review",
            item.get("input_adversarial_review_id"),
            fields,
            ("counterevidence", "invalidators", "excluded_from_base_case"),
            report_state,
        ),
    }


def _section(
    name: str,
    source_id: Any,
    fields: Mapping[str, Any],
    expected_fields: Sequence[str],
    report_state: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "source_report_id": str(source_id or ""),
        "status": report_state,
        "facts": {
            field: _field_projection(fields.get(field))
            for field in expected_fields
            if field in fields
        },
        "unknowns": [
            field
            for field in expected_fields
            if field not in fields or _field_status(fields.get(field)) == "MISSING"
        ],
        "directional_conclusion_included": False,
    }


def _tracking(
    *,
    fields: Mapping[str, Any],
    report_state: str,
    follow_up_checks: Sequence[Any],
    next_check_at: Any,
) -> dict[str, Any]:
    checks = list(follow_up_checks)
    if not checks:
        checks = [
            {
                "indicator": "evidence freshness",
                "reason": "确认关键资料仍在研究时点内",
                "status": "MISSING_CONFIG",
            },
            {
                "indicator": "counterevidence and invalidators",
                "reason": "检查核心判断是否仍可反驳",
                "status": "MISSING_CONFIG",
            },
        ]
    return {
        "status": "READY" if report_state == "REVIEWABLE" else "NEEDS_REVIEW",
        "checks": checks,
        "next_check_at": next_check_at,
        "next_check_at_status": "VERIFIED" if next_check_at else "MISSING",
        "simulation_action": "USER_CONFIRMATION_REQUIRED",
        "failure_conditions": _values(fields.get("invalidators")),
        "normal_volatility_contract": _values(fields.get("normal_volatility")),
    }


def _simulation_recommendation(
    *,
    report_state: str,
    candidate_state: str,
    tracking: Mapping[str, Any],
    sections: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Project evidence readiness into a user-facing simulation workflow.

    This is deliberately a workflow recommendation, not a directional
    investment conclusion. A user-confirmed decision snapshot remains a
    separate step with its own required inputs and lock.
    """

    unknowns = [
        f"{section_name}.{field}"
        for section_name, section in sections.items()
        for field in section.get("unknowns", [])
    ]
    if report_state == "BLOCKED":
        state = "WAIT_FOR_DATA"
        recommended_action = "CONTINUE_DATA_REVIEW"
        actions = ["CONTINUE_DATA_REVIEW", "OBSERVE"]
        reasons = ["报告处于 BLOCKED，不能建立确定性模拟决策"]
    elif report_state == "REVIEW":
        state = "REVIEW_REQUIRED"
        recommended_action = "CONTINUE_DATA_REVIEW"
        actions = ["CONTINUE_DATA_REVIEW", "OBSERVE"]
        reasons = ["报告仍需补证、反证或对抗审查"]
    else:
        state = "USER_CONFIRMATION_REQUIRED"
        recommended_action = "USER_CONFIRMATION_REQUIRED"
        actions = ["OBSERVE", "ESTABLISH_SIMULATION", "PHASED_SIMULATION"]
        reasons = [
            "证据整理和对抗审查已完成",
            "是否建立模拟记录必须由用户确认",
        ]

    return {
        "state": state,
        "recommended_action": recommended_action,
        "available_actions": actions,
        "direction": "NEUTRAL",
        "candidate_state": candidate_state,
        "reasons": reasons,
        "data_gaps": list(dict.fromkeys(unknowns)),
        "triggers": list(tracking.get("checks") or []),
        "invalidators": list(tracking.get("failure_conditions") or []),
        "next_check_at": tracking.get("next_check_at"),
        "target_price_generated": False,
        "decision_snapshot_created": False,
        "user_confirmation_required": True,
        "policy": {
            "workflow_guidance_only": True,
            "directional_conclusion": False,
            "target_price_generated": False,
            "automatic_candidate_promotion": False,
            "decision_snapshot_created": False,
            "execution_enabled": False,
            "read_only": True,
            "review_only": True,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _field_projection(raw_field: Any) -> dict[str, Any]:
    if not isinstance(raw_field, Mapping):
        return {"status": "MISSING", "values": [], "evidence_ids": []}
    return {
        "status": str(raw_field.get("status") or "MISSING").upper(),
        "values": raw_field.get("values") or [],
        "evidence_ids": _string_list(raw_field.get("evidence_ids")),
        "sources": _string_list(raw_field.get("sources")),
        "as_of": _string_list(raw_field.get("as_of")),
    }


def _field_status(raw_field: Any) -> str:
    return str(raw_field.get("status") or "MISSING").upper() if isinstance(raw_field, Mapping) else "MISSING"


def _single_value(raw_field: Any) -> Any:
    values = _values(raw_field)
    return values[0] if len(values) == 1 else (values or None)


def _values(raw_field: Any) -> list[Any]:
    if not isinstance(raw_field, Mapping):
        return []
    status = str(raw_field.get("status") or "MISSING").upper()
    if status not in {"VERIFIED", "UNVERIFIED"}:
        return []
    values = raw_field.get("values") or []
    return list(values) if isinstance(values, list) else [values]


def _allowed_actions(state: str) -> list[str]:
    return {
        "REVIEWABLE": ["user_confirmation_review", "evidence_refresh"],
        "REVIEW": ["gap_review", "counterevidence_review", "evidence_refresh"],
        "BLOCKED": ["blocker_resolution", "evidence_refresh"],
    }[state]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise ResearchReportError("research report fields must be string lists")
    return [str(item) for item in value if str(item)]
