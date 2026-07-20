"""Create immutable, user-confirmed simulation decision snapshots."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class DecisionSnapshotError(ValueError):
    """Raised when a decision snapshot cannot be safely locked."""


DECISION_SNAPSHOT_SCHEMA_VERSION = "decision-snapshot.v1"
RULE_VERSION = "decision-snapshot-rules.v1"
RESEARCH_REPORT_SCHEMA_VERSION = "company-research-report.v1"
_REPORT_STATES = {"REVIEWABLE", "REVIEW", "BLOCKED"}
_QUEUE_STATES = {"WATCH", "REVIEW", "CANDIDATE", "INSUFFICIENT", "REJECTED"}
_COMPANY_ACTIONS = {"OBSERVE", "ESTABLISH_SIMULATION", "HOLD", "ADJUST", "EXIT"}
_COMPANY_DIRECTIONS = {"OBSERVE", "BULLISH", "AVOID"}
_FUTURES_ACTIONS = _COMPANY_ACTIONS
_FUTURES_DIRECTIONS = {"BULLISH", "BEARISH", "NEUTRAL", "OBSERVE"}
_REQUIRED_COMMON = (
    "decision_at",
    "data_cutoff",
    "action_type",
    "direction",
    "price",
    "quantity",
    "position_ratio",
    "capital_assumptions",
    "value_or_price_range",
    "expected_horizon",
    "reasons",
    "industry_judgment",
    "company_judgment",
    "survival_judgment",
    "fundamental_assumptions",
    "market_structure",
    "risks",
    "triggers",
    "invalidators",
    "review_date",
    "benchmark",
    "covered_factors",
    "excluded_factors",
)
_REQUIRED_FUTURES = (
    "contract_code",
    "contract_month",
    "last_trade_date",
    "contract_multiplier",
    "settlement_basis",
    "margin_assumptions",
    "fee_assumptions",
    "slippage_assumptions",
    "roll_rule",
    "expiry_handling",
    "delivery_month_limit",
    "price_limit_rule",
    "trading_session",
    "cross_contract_continuation",
)


def build_decision_snapshot(
    research_report: Mapping[str, Any],
    decision: Mapping[str, Any],
    *,
    user_confirmed: bool = False,
    rule_version: str = RULE_VERSION,
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Lock a confirmed simulation record without connecting to execution."""

    _validate_report(research_report)
    if not isinstance(decision, Mapping):
        raise DecisionSnapshotError("decision input must be a JSON object")
    if not user_confirmed:
        raise DecisionSnapshotError(
            "user_confirmed must be true before creating a locked snapshot"
        )
    if not rule_version.strip():
        raise DecisionSnapshotError("rule_version must not be empty")

    company_id = str(decision.get("company_id") or "").strip()
    if not company_id:
        raise DecisionSnapshotError("decision company_id is required")
    report_item = _find_report_item(research_report, company_id)
    if str(report_item.get("report_state") or "").upper() != "REVIEWABLE":
        raise DecisionSnapshotError(
            "decision snapshot requires a REVIEWABLE research report item"
        )
    candidate_state = str(report_item.get("candidate_state") or "").upper()
    if candidate_state not in _QUEUE_STATES:
        raise DecisionSnapshotError("research report item has unsupported candidate_state")
    if candidate_state in {"INSUFFICIENT", "REJECTED"}:
        raise DecisionSnapshotError(
            "insufficient or rejected candidate cannot create a decision snapshot"
        )

    subject_type = str(decision.get("subject_type") or "").strip().lower()
    if subject_type not in {"listed_company", "futures_contract"}:
        raise DecisionSnapshotError(
            "subject_type must be listed_company or futures_contract"
        )
    required = _REQUIRED_COMMON + (
        _REQUIRED_FUTURES if subject_type == "futures_contract" else ()
    )
    _require_fields(decision, required)
    action_type = str(decision["action_type"]).strip().upper()
    directions = _COMPANY_DIRECTIONS if subject_type == "listed_company" else _FUTURES_DIRECTIONS
    actions = _COMPANY_ACTIONS if subject_type == "listed_company" else _FUTURES_ACTIONS
    if action_type not in actions:
        raise DecisionSnapshotError(f"unsupported action_type: {action_type}")
    direction = str(decision["direction"]).strip().upper()
    if direction not in directions:
        raise DecisionSnapshotError(f"unsupported direction: {direction}")
    _validate_snapshot_values(decision, subject_type)

    if subject_type == "futures_contract" and str(decision.get("contract_code") or "").strip() in {
        "CONTINUOUS",
        "MAIN",
    }:
        raise DecisionSnapshotError(
            "futures decision snapshots must bind a specific contract, not a continuous series"
        )

    report_id = str(research_report.get("report_id") or "")
    generated_id = snapshot_id or f"{company_id}-{str(decision['decision_at']).strip()}"
    supersedes = str(decision.get("supersedes_snapshot_id") or "").strip()
    revision_reason = str(decision.get("revision_reason") or "").strip()
    if supersedes and not revision_reason:
        raise DecisionSnapshotError(
            "revision_reason is required when supersedes_snapshot_id is supplied"
        )
    payload = {
        "schema_version": DECISION_SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": f"decision-snapshot-{generated_id}",
        "status": "LOCKED",
        "version": int(decision.get("version") or 1),
        "supersedes_snapshot_id": supersedes or None,
        "revision_reason": revision_reason or None,
        "research_report_id": report_id,
        "research_report_state": "REVIEWABLE",
        "company_id": company_id,
        "display_name": str(report_item.get("display_name") or decision.get("display_name") or ""),
        "candidate_state": candidate_state,
        "candidate_state_changed": False,
        "subject_type": subject_type,
        "subject_id": str(decision.get("subject_id") or company_id).strip(),
        "market_or_exchange": str(decision.get("market_or_exchange") or "").strip(),
        "decision": dict(decision),
        "rule_version": rule_version,
        "user_confirmed": True,
        "immutable": True,
        "simulation_only": True,
        "execution_enabled": False,
        "broker_connection": False,
        "order_sent": False,
        "policy": {
            "locked_before_simulation": True,
            "original_snapshot_not_overwritable": True,
            "revision_requires_new_snapshot": True,
            "user_confirmed_required": True,
            "continuous_series_not_tradeable": subject_type == "futures_contract",
            "read_only": True,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
    }
    return payload


def _validate_report(report: Any) -> None:
    if not isinstance(report, Mapping):
        raise DecisionSnapshotError("input research report must be a JSON object")
    if report.get("schema_version") != RESEARCH_REPORT_SCHEMA_VERSION:
        raise DecisionSnapshotError("input must be a company-research-report.v1 report")
    if not isinstance(report.get("items"), list):
        raise DecisionSnapshotError("research report has no items list")


def _find_report_item(report: Mapping[str, Any], company_id: str) -> Mapping[str, Any]:
    matches = [
        item
        for item in report["items"]
        if isinstance(item, Mapping) and str(item.get("company_id") or "") == company_id
    ]
    if not matches:
        raise DecisionSnapshotError(
            f"company_id is not in research report: {company_id}"
        )
    if len(matches) > 1:
        raise DecisionSnapshotError(f"duplicate company_id in research report: {company_id}")
    return matches[0]


def _require_fields(decision: Mapping[str, Any], fields: Sequence[str]) -> None:
    missing = [field for field in fields if field not in decision]
    if missing:
        raise DecisionSnapshotError(
            "decision input missing required fields: " + ", ".join(missing)
        )


def _validate_snapshot_values(decision: Mapping[str, Any], subject_type: str) -> None:
    for field in ("decision_at", "data_cutoff", "review_date", "expected_horizon"):
        if not str(decision[field]).strip():
            raise DecisionSnapshotError(f"{field} must be non-empty")
    for field in ("reasons", "fundamental_assumptions", "risks", "triggers", "invalidators", "covered_factors", "excluded_factors"):
        value = decision[field]
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or not value:
            raise DecisionSnapshotError(f"{field} must be a non-empty list")
    for field in ("capital_assumptions", "value_or_price_range", "market_structure", "benchmark"):
        if not isinstance(decision[field], Mapping) or not decision[field]:
            raise DecisionSnapshotError(f"{field} must be a non-empty object")
    if subject_type == "futures_contract":
        for field in _REQUIRED_FUTURES:
            if isinstance(decision[field], str) and not decision[field].strip():
                raise DecisionSnapshotError(f"{field} must be non-empty")
        if not isinstance(decision["cross_contract_continuation"], bool):
            raise DecisionSnapshotError("cross_contract_continuation must be boolean")
