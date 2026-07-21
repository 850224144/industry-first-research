"""Create auditable opportunity-candidate states after industry-first screening.

The module deliberately consumes explicit assessments. It does not turn a
price move, a single score, or a missing field into a candidate conclusion.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
from typing import Any


OPPORTUNITY_INPUT_SCHEMA_VERSION = "opportunity-candidate-input.v1"
OPPORTUNITY_SCHEMA_VERSION = "opportunity-candidate.v1"
OPPORTUNITY_SCAN_INPUT_SCHEMA_VERSION = "opportunity-scan-input.v1"
OPPORTUNITY_SCAN_SCHEMA_VERSION = "opportunity-scan.v1"
RULE_VERSION = "opportunity-candidate-rules.v1"

_DIMENSIONS = (
    "downside_protection",
    "inflection_evidence",
    "profit_convexity",
    "expectation_gap",
)
_DIMENSION_STATUSES = {"PASS", "PARTIAL", "INSUFFICIENT", "BLOCKED", "NOT_EVALUABLE"}
_GATE_STATUSES = {"PASS", "BLOCKED", "INSUFFICIENT", "NOT_EVALUABLE"}
_STATES = {"DISCOVERED", "WATCH", "CANDIDATE", "REVIEWABLE", "REJECTED", "EXPIRED"}
_CLOCK_FIELDS = ("industry_clock", "company_clock", "market_clock")


class OpportunityCandidateError(ValueError):
    """Raised when an opportunity candidate cannot be evaluated safely."""


def build_opportunity_candidate(
    payload: Mapping[str, Any],
    *,
    candidate_id: str = "",
) -> dict[str, Any]:
    """Evaluate one candidate from explicit four-dimensional evidence.

    ``status`` is a workflow state, not an investment conclusion. Values inside
    dimensions are retained as supplied and are never collapsed into a score.
    """

    _validate_input(payload)
    candidate = payload.get("candidate")
    if not isinstance(candidate, Mapping):
        raise OpportunityCandidateError("candidate must be an object")
    identifier = str(candidate.get("candidate_id") or candidate_id).strip()
    if not identifier:
        identifier = _generated_candidate_id(candidate)

    dimensions = _dimensions(payload.get("dimensions"))
    hard_gates = _hard_gates(payload.get("hard_gates"))
    clocks = _clocks(payload.get("clocks"))
    previous = payload.get("previous")
    if previous is not None and not isinstance(previous, Mapping):
        raise OpportunityCandidateError("previous must be an object")
    previous_status = _state(previous.get("status") if previous else "")

    evidence_refs = _string_list(payload.get("evidence_refs"))
    deep_research = payload.get("deep_research") or {}
    if not isinstance(deep_research, Mapping):
        raise OpportunityCandidateError("deep_research must be an object")
    expired = payload.get("expired") is True
    hard_status = _hard_gate_status(hard_gates)
    status, reasons, missing = _next_state(
        dimensions,
        hard_gates,
        deep_research,
        expired=expired,
        previous_status=previous_status,
        reentry_conditions_met=payload.get("reentry_conditions_met") is True,
    )
    if status == "REJECTED":
        rejection = {
            "status": "RECORDED",
            "reasons": list(reasons),
            "evidence_refs": list(evidence_refs),
            "rule_version": RULE_VERSION,
            "reentry_conditions": _string_list(payload.get("reentry_conditions")),
        }
    else:
        rejection = None

    transition_reason = _transition_reason(previous_status, status, reasons)
    return {
        "schema_version": OPPORTUNITY_SCHEMA_VERSION,
        "candidate_id": identifier,
        "company_id": str(candidate.get("company_id") or ""),
        "display_name": str(candidate.get("display_name") or ""),
        "industry_id": str(candidate.get("industry_id") or ""),
        "as_of": str(payload.get("as_of") or candidate.get("as_of") or ""),
        "opportunity_types": _string_list(payload.get("opportunity_types")),
        "status": status,
        "previous_status": previous_status,
        "state_transition": {
            "changed": previous_status != status,
            "from": previous_status or None,
            "to": status,
            "reason": transition_reason,
            "evidence_refs": list(evidence_refs),
            "rule_version": RULE_VERSION,
        },
        "industry_clock": clocks["industry_clock"],
        "company_clock": clocks["company_clock"],
        "market_clock": clocks["market_clock"],
        "dimensions": dimensions,
        "weakest_dimensions": [
            name
            for name, item in dimensions.items()
            if item["status"] in {"BLOCKED", "INSUFFICIENT", "NOT_EVALUABLE"}
        ],
        "hard_gate": {
            "status": hard_status,
            "gates": hard_gates,
            "blocked_gates": [
                name for name, item in hard_gates.items() if item["status"] == "BLOCKED"
            ],
            "incomplete_gates": [
                name
                for name, item in hard_gates.items()
                if item["status"] in {"INSUFFICIENT", "NOT_EVALUABLE"}
            ],
        },
        "reasons": list(dict.fromkeys(reasons)),
        "missing": list(dict.fromkeys(missing)),
        "rejection": rejection,
        "deep_research": dict(deep_research),
        "source_payload_hash": _hash_payload(payload),
        "rule_version": RULE_VERSION,
        "policy": {
            "dimensions_not_collapsed_to_total_score": True,
            "price_or_volume_cannot_upgrade_state": True,
            "hard_gates_precede_sorting": True,
            "rejections_and_empty_results_must_be_retained": True,
            "not_investment_conclusion": True,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def build_opportunity_scan(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate a bounded candidate list and retain an empty scan explicitly."""

    if not isinstance(payload, Mapping):
        raise OpportunityCandidateError("scan input must be an object")
    if payload.get("schema_version") != OPPORTUNITY_SCAN_INPUT_SCHEMA_VERSION:
        raise OpportunityCandidateError(
            f"input must be {OPPORTUNITY_SCAN_INPUT_SCHEMA_VERSION}"
        )
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise OpportunityCandidateError("candidates must be a list")
    items = [build_opportunity_candidate(item) for item in candidates]
    counts = {state: 0 for state in sorted(_STATES)}
    for item in items:
        counts[item["status"]] += 1
    rejections = [item for item in items if item["status"] == "REJECTED"]
    return {
        "schema_version": OPPORTUNITY_SCAN_SCHEMA_VERSION,
        "scan_id": str(payload.get("scan_id") or "opportunity-scan-unknown"),
        "as_of": str(payload.get("as_of") or ""),
        "scan_scope": dict(payload.get("scan_scope") or {}),
        "candidate_count": len(items),
        "items": items,
        "rejections": rejections,
        "state_counts": counts,
        "empty_result": not any(
            item["status"] in {"CANDIDATE", "REVIEWABLE"} for item in items
        ),
        "resource_audit": dict(payload.get("resource_audit") or {}),
        "rule_version": RULE_VERSION,
        "policy": {
            "empty_result_is_valid": True,
            "selection_bias_warning": "保留空集、淘汰对象和所有已评估候选，不只保留上涨或盈利样本。",
            "not_investment_conclusion": True,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _next_state(
    dimensions: Mapping[str, Mapping[str, Any]],
    hard_gates: Mapping[str, Mapping[str, Any]],
    deep_research: Mapping[str, Any],
    *,
    expired: bool,
    previous_status: str,
    reentry_conditions_met: bool,
) -> tuple[str, list[str], list[str]]:
    reasons: list[str] = []
    missing: list[str] = []
    hard_status = _hard_gate_status(hard_gates)
    blocked = [name for name, gate in hard_gates.items() if gate["status"] == "BLOCKED"]
    incomplete = [
        name
        for name, gate in hard_gates.items()
        if gate["status"] in {"INSUFFICIENT", "NOT_EVALUABLE"}
    ]
    if blocked:
        return "REJECTED", [f"硬否决: {name}" for name in blocked], []
    if previous_status in {"REJECTED", "EXPIRED"} and not reentry_conditions_met:
        return (
            "DISCOVERED",
            [f"上一状态为 {previous_status}，尚未提供满足重新进入条件的新证据"],
            ["reentry_conditions_met", "新的有效证据"],
        )
    if expired:
        return "EXPIRED", ["证据过期、兑现超期或机会已充分定价"], ["重新获得有效且更新的证据"]
    if incomplete:
        reasons.append("硬闸门证据不完整")
        missing.extend(incomplete)

    survival_gate = dimensions["downside_protection"].get("survival_gate_pass")
    if survival_gate is not None and _truthy(survival_gate) is False:
        return "REJECTED", ["生存能力或重大治理闸门未通过"], ["补充生存与治理证据"]

    inflection = dimensions["inflection_evidence"]
    independent_types = _number(inflection.get("independent_signal_types"))
    normal_cycles = _number(inflection.get("normal_update_cycles"))
    candidate_ready = (
        not incomplete
        and hard_gates
        and hard_status == "PASS"
        and dimensions["downside_protection"]["status"] in {"PASS", "PARTIAL"}
        and inflection["status"] in {"PASS", "PARTIAL"}
        and independent_types >= 2
        and normal_cycles >= 2
        and _truthy(dimensions["expectation_gap"].get("not_obviously_overpriced"))
        and not any(item["status"] == "BLOCKED" for item in dimensions.values())
    )
    reviewable_ready = candidate_ready and all(
        _truthy(deep_research.get(field))
        for field in (
            "complete",
            "product_profit_source_review",
            "survival_stress_test",
            "reverse_valuation",
            "adversarial_review_passed",
        )
    )
    if reviewable_ready:
        return "REVIEWABLE", ["深研、反向估值和对抗审查均已完成"], missing
    if candidate_ready:
        return "CANDIDATE", ["生存闸门通过，至少两类领先证据持续两个周期，估值未明显透支"], missing

    for name, item in dimensions.items():
        if item["status"] in {"INSUFFICIENT", "NOT_EVALUABLE"}:
            missing.append(name)
    if any(item["status"] in {"PASS", "PARTIAL"} for item in dimensions.values()):
        reasons.append("部分四维证据已出现，但尚不足以升级候选")
        return "WATCH", reasons, missing
    return "DISCOVERED", ["仅发现异常或机会标签，尚未完成四维验证"], missing


def _dimensions(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        raise OpportunityCandidateError("dimensions must be an object")
    result: dict[str, dict[str, Any]] = {}
    for name in _DIMENSIONS:
        item = value.get(name)
        if item is None:
            item = {}
        if not isinstance(item, Mapping):
            raise OpportunityCandidateError(f"dimension {name} must be an object")
        status = str(item.get("status") or "NOT_EVALUABLE").upper()
        if status not in _DIMENSION_STATUSES:
            raise OpportunityCandidateError(f"unsupported dimension status: {status}")
        result[name] = {
            **dict(item),
            "status": status,
            "evidence_refs": _string_list(item.get("evidence_refs")),
            "confidence": str(item.get("confidence") or "UNKNOWN").upper(),
        }
    return result


def _hard_gates(value: Any) -> dict[str, dict[str, Any]]:
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise OpportunityCandidateError("hard_gates must be an object")
    result = {}
    for name, raw in value.items():
        if not isinstance(raw, Mapping):
            raise OpportunityCandidateError(f"hard gate {name} must be an object")
        status = str(raw.get("status") or "NOT_EVALUABLE").upper()
        if status not in _GATE_STATUSES:
            raise OpportunityCandidateError(f"unsupported hard gate status: {status}")
        result[str(name)] = {
            **dict(raw),
            "status": status,
            "evidence_refs": _string_list(raw.get("evidence_refs")),
        }
    return result


def _clocks(value: Any) -> dict[str, dict[str, Any]]:
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise OpportunityCandidateError("clocks must be an object")
    return {
        name: _clock(value.get(name))
        for name in _CLOCK_FIELDS
    }


def _clock(value: Any) -> dict[str, Any]:
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise OpportunityCandidateError("each clock must be an object")
    return {
        **dict(value),
        "state": str(value.get("state") or "UNKNOWN").upper(),
        "evidence_refs": _string_list(value.get("evidence_refs")),
    }


def _hard_gate_status(gates: Mapping[str, Mapping[str, Any]]) -> str:
    if any(item["status"] == "BLOCKED" for item in gates.values()):
        return "BLOCKED"
    if any(item["status"] in {"INSUFFICIENT", "NOT_EVALUABLE"} for item in gates.values()):
        return "INSUFFICIENT"
    return "PASS" if gates else "INSUFFICIENT"


def _validate_input(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping):
        raise OpportunityCandidateError("candidate input must be an object")
    if value.get("schema_version") != OPPORTUNITY_INPUT_SCHEMA_VERSION:
        raise OpportunityCandidateError(
            f"input must be {OPPORTUNITY_INPUT_SCHEMA_VERSION}"
        )


def _state(value: Any) -> str:
    text = str(value or "").upper()
    if not text:
        return ""
    if text not in _STATES:
        raise OpportunityCandidateError(f"unsupported candidate state: {text}")
    return text


def _transition_reason(previous: str, current: str, reasons: Sequence[str]) -> str:
    if not previous:
        return reasons[0] if reasons else "首次评估"
    if previous == current:
        return "状态保持，证据仍在当前阶段"
    return reasons[0] if reasons else f"状态由 {previous} 迁移到 {current}"


def _generated_candidate_id(candidate: Mapping[str, Any]) -> str:
    company_id = str(candidate.get("company_id") or "unknown")
    industry_id = str(candidate.get("industry_id") or "unknown")
    return f"candidate-{industry_id}-{company_id}"


def _hash_payload(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        raise OpportunityCandidateError("expected a string list")
    return [str(item) for item in value if str(item).strip()]


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "pass", "passed", "1"}
    return value is True
