"""Run conservative adversarial checks over a valuation research package."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any


class AdversarialReviewError(ValueError):
    """Raised when an adversarial-review input cannot be checked safely."""


ADVERSARIAL_REVIEW_SCHEMA_VERSION = "company-adversarial-review.v1"
RULE_VERSION = "company-adversarial-review-rules.v1"
VALUATION_SCHEMA_VERSION = "company-valuation-scenarios.v1"
MARKET_STRUCTURE_SCHEMA_VERSION = "market-structure-snapshot.v1"
_QUEUE_STATES = {"WATCH", "REVIEW", "CANDIDATE", "INSUFFICIENT", "REJECTED"}
_AUDIT_STATES = {"PASS", "REVIEW", "BLOCKED"}
_BLOCKING_SEVERITY = "BLOCKING"

_CHECKS = (
    "FUTURE_INFORMATION",
    "EVIDENCE_CONFLICT",
    "COUNTEREVIDENCE_PRESENT",
    "INVALIDATORS_PRESENT",
    "CASHFLOW_CONVERSION",
    "BASE_CASE_EXCLUSIONS",
    "EXTERNAL_AI_INDEPENDENCE",
    "VALUATION_OUTPUT_BOUNDARY",
    "MARKET_STRUCTURE_SIGNAL_BOUNDARY",
    "CANDIDATE_STATE_PRESERVED",
    "MARKET_SIZE_TO_COMPANY_PROFIT",
)


def build_adversarial_review_report(
    valuation_report: Mapping[str, Any],
    *,
    market_structure_report: Mapping[str, Any] | None = None,
    rule_version: str = RULE_VERSION,
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Audit facts and boundaries without changing research conclusions."""

    _validate_valuation_report(valuation_report)
    if not rule_version.strip():
        raise AdversarialReviewError("rule_version must not be empty")
    if market_structure_report is not None:
        _validate_market_structure_report(market_structure_report)

    items = [
        _build_item(
            item,
            valuation_report=valuation_report,
            market_structure_report=market_structure_report,
            rule_version=rule_version,
        )
        for item in valuation_report["items"]
    ]
    counts = Counter(item["audit_state"] for item in items)
    input_report_id = str(valuation_report.get("report_id") or "")
    report_id = snapshot_id or input_report_id or "valuation-input"
    return {
        "schema_version": ADVERSARIAL_REVIEW_SCHEMA_VERSION,
        "report_id": f"company-adversarial-review-{report_id}",
        "input_valuation_scenarios_id": input_report_id,
        "input_survival_analysis_id": str(
            valuation_report.get("input_survival_analysis_id") or ""
        ),
        "input_competitive_position_id": str(
            valuation_report.get("input_competitive_position_id") or ""
        ),
        "input_cycle_reversal_id": str(
            valuation_report.get("input_cycle_reversal_id") or ""
        ),
        "input_industry_situation_id": str(
            valuation_report.get("input_industry_situation_id") or ""
        ),
        "input_demand_transmission_id": str(
            valuation_report.get("input_demand_transmission_id") or ""
        ),
        "input_application_mapping_id": str(
            valuation_report.get("input_application_mapping_id") or ""
        ),
        "input_product_profile_id": str(
            valuation_report.get("input_product_profile_id") or ""
        ),
        "input_supplemental_id": str(
            valuation_report.get("input_supplemental_id") or ""
        ),
        "input_queue_id": str(valuation_report.get("input_queue_id") or ""),
        "input_snapshot_id": str(valuation_report.get("input_snapshot_id") or ""),
        "rule_version": rule_version,
        "as_of": str(valuation_report.get("as_of") or ""),
        "source": str(valuation_report.get("source") or ""),
        "source_metadata": valuation_report.get("source_metadata") or {},
        "market_structure_review": (
            "SUPPLIED" if market_structure_report is not None else "OPTIONAL_NOT_SUPPLIED"
        ),
        "candidate_count": len(items),
        "audit_state_counts": dict(counts),
        "items": items,
        "policy": {
            "adversarial_review_only": True,
            "evidence_only": True,
            "facts_not_rewritten": True,
            "candidate_state_preserved": True,
            "decision_snapshot_requires_pass": True,
            "investment_conclusion": False,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _validate_valuation_report(report: Any) -> None:
    if not isinstance(report, Mapping):
        raise AdversarialReviewError("input valuation report must be a JSON object")
    if report.get("schema_version") != VALUATION_SCHEMA_VERSION:
        raise AdversarialReviewError(
            "input must be a company-valuation-scenarios.v1 report"
        )
    if not isinstance(report.get("items"), list):
        raise AdversarialReviewError("valuation report has no items list")


def _validate_market_structure_report(report: Mapping[str, Any]) -> None:
    if report.get("schema_version") != MARKET_STRUCTURE_SCHEMA_VERSION:
        raise AdversarialReviewError(
            "market structure input must be a market-structure-snapshot.v1 report"
        )
    if not isinstance(report.get("timeframes"), Mapping):
        raise AdversarialReviewError("market structure report has no timeframes mapping")


def _build_item(
    item: Any,
    *,
    valuation_report: Mapping[str, Any],
    market_structure_report: Mapping[str, Any] | None,
    rule_version: str,
) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise AdversarialReviewError("each valuation item must be an object")
    company_id = str(item.get("company_id") or "").strip()
    candidate_state = str(item.get("candidate_state") or "").upper()
    if not company_id:
        raise AdversarialReviewError("valuation item company_id is required")
    if candidate_state not in _QUEUE_STATES:
        raise AdversarialReviewError(
            f"unsupported candidate_state: {candidate_state or '<empty>'}"
        )
    raw_fields = item.get("fields")
    if not isinstance(raw_fields, Mapping):
        raise AdversarialReviewError("valuation item has no fields mapping")
    fields = {
        str(field): _normalise_field_summary(str(field), value)
        for field, value in raw_fields.items()
    }
    findings = [
        _check_future_information(fields, valuation_report),
        _check_evidence_conflict(fields),
        _check_required_counterevidence(fields),
        _check_required_invalidators(fields),
        _check_cashflow_conversion(fields),
        _check_base_case_exclusions(fields),
        _check_external_ai(fields),
        _check_valuation_boundary(item, valuation_report),
        _check_market_structure_boundary(market_structure_report),
        _check_candidate_state(item),
        _check_market_size_leak(fields),
    ]
    audit_state = _audit_state(findings)
    reasons = [finding["check_id"] for finding in findings if finding["status"] != "PASS"]
    evidence_ids = _unique(
        [
            *map(str, item.get("evidence_ids") or []),
            *(
                evidence_id
                for field in fields.values()
                for evidence_id in field["evidence_ids"]
            ),
        ]
    )
    return {
        "company_id": company_id,
        "company_scope": item.get("company_scope"),
        "display_name": str(item.get("display_name") or ""),
        "industry_id": str(item.get("industry_id") or ""),
        "candidate_state": candidate_state,
        "candidate_state_changed": False,
        "candidate_rule_version": str(item.get("candidate_rule_version") or ""),
        "valuation_gate_state": str(item.get("valuation_gate_state") or ""),
        "audit_state": audit_state,
        "rule_version": rule_version,
        "findings": findings,
        "reasons": reasons,
        "evidence_ids": evidence_ids,
        "unknowns": [
            field for field, summary in fields.items() if summary["status"] == "MISSING"
        ],
        "downstream_modules": {
            "decision_snapshot": "READY_REQUIRED",
            "public_draft": "LOCKED_RESEARCH_REQUIRED",
        },
        "allowed_actions": _allowed_actions(audit_state),
        "prohibited_actions": [
            "rewrite_source_facts",
            "decision_snapshot",
            "investment_conclusion",
            "automatic_candidate_promotion",
            "execution",
        ],
        "review_only": True,
        "investment_conclusion": False,
    }


def _check_future_information(
    fields: Mapping[str, Mapping[str, Any]], report: Mapping[str, Any]
) -> dict[str, Any]:
    report_as_of = _parse_date(report.get("as_of"))
    if report_as_of is None:
        return _finding(
            "FUTURE_INFORMATION",
            "REVIEW",
            "HIGH",
            "研究报告缺少可解析的 as_of，无法完成事后信息检查。",
            ["report.as_of"],
        )
    future_fields: list[str] = []
    for field, summary in fields.items():
        for value in summary["as_of"]:
            parsed = _parse_date(value)
            if parsed is not None and parsed > report_as_of:
                future_fields.append(field)
    if future_fields:
        return _finding(
            "FUTURE_INFORMATION",
            "BLOCKED",
            _BLOCKING_SEVERITY,
            "证据时间晚于研究时点，必须创建修订研究版本。",
            _unique(future_fields),
        )
    return _finding(
        "FUTURE_INFORMATION", "PASS", "NONE", "未发现晚于研究时点的证据。", []
    )


def _check_evidence_conflict(fields: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    conflicted = [field for field, summary in fields.items() if summary["status"] == "CONFLICTING"]
    if conflicted:
        return _finding(
            "EVIDENCE_CONFLICT",
            "BLOCKED",
            _BLOCKING_SEVERITY,
            "存在未解决的冲突证据，不能进入决策快照。",
            conflicted,
        )
    return _finding("EVIDENCE_CONFLICT", "PASS", "NONE", "未发现冲突证据。", [])


def _check_required_counterevidence(fields: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return _required_field_finding(
        "COUNTEREVIDENCE_PRESENT",
        fields,
        "counterevidence",
        "缺少主要反证；结论不能被充分审查。",
    )


def _check_required_invalidators(fields: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return _required_field_finding(
        "INVALIDATORS_PRESENT",
        fields,
        "invalidators",
        "缺少失效条件；无法定义何时改变判断。",
    )


def _check_cashflow_conversion(fields: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    names = ("profit_cashflow_evidence", "cashflow_evidence", "operating_cashflow")
    matching = [name for name in names if name in fields]
    if any(_is_verified(fields[name]) for name in matching):
        return _finding(
            "CASHFLOW_CONVERSION", "PASS", "NONE", "存在现金流验证证据。", matching
        )
    return _finding(
        "CASHFLOW_CONVERSION",
        "REVIEW",
        "HIGH",
        "收入或利润假设缺少经营现金流验证。",
        matching or ["profit_cashflow_evidence", "operating_cashflow"],
    )


def _check_base_case_exclusions(fields: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return _required_field_finding(
        "BASE_CASE_EXCLUSIONS",
        fields,
        "excluded_from_base_case",
        "缺少基准情景排除项，未验证业务可能被静默纳入基准。",
    )


def _check_external_ai(fields: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    ai_fields = []
    for field, summary in fields.items():
        source_text = " ".join(summary["sources"]).lower()
        if "ai" in source_text or "deepseek" in source_text or "doubao" in source_text:
            ai_fields.append(field)
    if ai_fields:
        return _finding(
            "EXTERNAL_AI_INDEPENDENCE",
            "REVIEW",
            "HIGH",
            "发现网页 AI 来源；不能作为独立验证，必须回到官方或独立来源核验。",
            ai_fields,
        )
    return _finding(
        "EXTERNAL_AI_INDEPENDENCE", "PASS", "NONE", "未发现网页 AI 作为关键证据来源。", []
    )


def _check_valuation_boundary(
    item: Mapping[str, Any], report: Mapping[str, Any]
) -> dict[str, Any]:
    policy = report.get("policy") or {}
    leaks = []
    if item.get("numeric_valuation_included") is not False:
        leaks.append("numeric_valuation_included")
    if item.get("target_price_generated") is not False:
        leaks.append("target_price_generated")
    if policy.get("target_price_generated") is True or policy.get("investment_conclusion") is True:
        leaks.append("policy")
    if leaks:
        return _finding(
            "VALUATION_OUTPUT_BOUNDARY",
            "BLOCKED",
            _BLOCKING_SEVERITY,
            "估值框架越过边界生成了目标价或投资结论。",
            leaks,
        )
    return _finding(
        "VALUATION_OUTPUT_BOUNDARY", "PASS", "NONE", "估值框架未生成目标价或投资结论。", []
    )


def _check_market_structure_boundary(
    report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if report is None:
        return _finding(
            "MARKET_STRUCTURE_SIGNAL_BOUNDARY",
            "PASS",
            "NONE",
            "未提供可选市场结构快照。",
            [],
        )
    policy = report.get("policy") or {}
    leaks = []
    if policy.get("trading_signal_included") is not False:
        leaks.append("policy.trading_signal_included")
    if policy.get("automatic_order_included") is not False:
        leaks.append("policy.automatic_order_included")
    for timeframe, snapshot in (report.get("timeframes") or {}).items():
        if snapshot.get("signal") is not None:
            leaks.append(f"timeframes.{timeframe}.signal")
    if leaks:
        return _finding(
            "MARKET_STRUCTURE_SIGNAL_BOUNDARY",
            "BLOCKED",
            _BLOCKING_SEVERITY,
            "市场结构快照含交易信号或自动执行边界泄漏。",
            leaks,
        )
    return _finding(
        "MARKET_STRUCTURE_SIGNAL_BOUNDARY", "PASS", "NONE", "市场结构未越过交易信号边界。", []
    )


def _check_candidate_state(item: Mapping[str, Any]) -> dict[str, Any]:
    if item.get("candidate_state_changed") is True:
        return _finding(
            "CANDIDATE_STATE_PRESERVED",
            "BLOCKED",
            _BLOCKING_SEVERITY,
            "审计输入改变了候选状态，必须保留原候选状态并创建新版本。",
            ["candidate_state_changed"],
        )
    return _finding(
        "CANDIDATE_STATE_PRESERVED", "PASS", "NONE", "候选状态保持不变。", []
    )


def _check_market_size_leak(fields: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if "market_size" in fields and not any(
        name in fields and _is_verified(fields[name])
        for name in ("product_financial_bridge", "revenue_structure", "revenue_bridge")
    ):
        return _finding(
            "MARKET_SIZE_TO_COMPANY_PROFIT",
            "REVIEW",
            "HIGH",
            "存在市场规模证据但缺少公司收入/利润桥接，不能把市场规模当成公司利润。",
            ["market_size"],
        )
    return _finding(
        "MARKET_SIZE_TO_COMPANY_PROFIT", "PASS", "NONE", "未发现市场规模直接替代公司利润桥接。", []
    )


def _required_field_finding(
    check_id: str,
    fields: Mapping[str, Mapping[str, Any]],
    field: str,
    message: str,
) -> dict[str, Any]:
    if field in fields and _is_verified(fields[field]) and fields[field]["values"]:
        return _finding(check_id, "PASS", "NONE", f"已提供 {field} 证据。", [field])
    return _finding(check_id, "REVIEW", "HIGH", message, [field])


def _finding(
    check_id: str,
    status: str,
    severity: str,
    message: str,
    evidence_fields: Sequence[str],
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": status,
        "severity": severity,
        "message": message,
        "evidence_fields": list(evidence_fields),
    }


def _audit_state(findings: Sequence[Mapping[str, Any]]) -> str:
    if any(finding["status"] == "BLOCKED" for finding in findings):
        return "BLOCKED"
    if any(finding["status"] == "REVIEW" for finding in findings):
        return "REVIEW"
    return "PASS"


def _allowed_actions(state: str) -> list[str]:
    return {
        "PASS": ["decision_snapshot_review", "evidence_refresh"],
        "REVIEW": ["counterevidence_review", "evidence_refresh"],
        "BLOCKED": ["audit_blocker_resolution", "evidence_refresh"],
    }[state]


def _normalise_field_summary(field: str, raw_summary: Any) -> dict[str, Any]:
    if not isinstance(raw_summary, Mapping):
        raise AdversarialReviewError(f"field summary must be an object: {field}")
    status = str(raw_summary.get("status") or "MISSING").upper()
    if status not in {"MISSING", "VERIFIED", "UNVERIFIED", "CONFLICTING"}:
        raise AdversarialReviewError(f"unsupported field status: {status}")
    return {
        "status": status,
        "values": raw_summary.get("values") or [],
        "evidence_ids": _string_list(raw_summary.get("evidence_ids")),
        "sources": _string_list(raw_summary.get("sources")),
        "as_of": _string_list(raw_summary.get("as_of")),
        "evidence_tiers": _string_list(raw_summary.get("evidence_tiers")),
    }


def _is_verified(summary: Mapping[str, Any]) -> bool:
    return summary["status"] == "VERIFIED" and any(
        tier in {"A", "B"} for tier in summary["evidence_tiers"]
    )


def _parse_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise AdversarialReviewError("adversarial review fields must be string lists")
    return [str(item) for item in value if str(item)]


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
