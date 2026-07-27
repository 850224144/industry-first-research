"""Create immutable, user-confirmed simulation decision snapshots."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from hashlib import sha256
import json
from typing import Any

from .company_scope import CompanyScopeError, scope_item_for_company
from .market_data import MarketDataError, build_market_data_snapshot


class DecisionSnapshotError(ValueError):
    """Raised when a decision snapshot cannot be safely locked."""


DECISION_SNAPSHOT_SCHEMA_VERSION = "decision-snapshot.v1"
RULE_VERSION = "decision-snapshot-rules.v1"
RESEARCH_REPORT_SCHEMA_VERSION = "company-research-report.v1"
EVIDENCE_BUNDLE_SCHEMA_VERSION = "evidence-bundle.v1"
RESEARCH_EXECUTION_PLAN_SCHEMA_VERSION = "research-execution-plan.v1"
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
    evidence_bundle: Mapping[str, Any] | None = None,
    execution_plan: Mapping[str, Any] | None = None,
    company_scope_report: Mapping[str, Any] | None = None,
    market_data_snapshots: Sequence[Mapping[str, Any]] | None = None,
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
    _validate_optional_lineage(evidence_bundle, execution_plan, decision)
    market_lineage = _lock_market_data_lineage(market_data_snapshots, decision)
    scope_projection = None
    if company_scope_report is not None:
        try:
            scope_projection = scope_item_for_company(
                company_scope_report, str(decision.get("company_id") or "")
            )
        except CompanyScopeError as error:
            raise DecisionSnapshotError(str(error)) from error
        if scope_projection is None:
            raise DecisionSnapshotError("company_scope_report company_id does not match decision company_id")
        scope_cutoff = _calendar_day(
            str(company_scope_report.get("as_of") or ""),
            "company_scope_report.as_of",
        )
        decision_cutoff = _calendar_day(
            str(decision.get("data_cutoff") or ""), "data_cutoff"
        )
        if scope_cutoff > decision_cutoff:
            raise DecisionSnapshotError(
                "company_scope_report as_of cannot be after decision data_cutoff"
            )
        if scope_projection["researchability_state"] in {"BLOCKED", "INSUFFICIENT"}:
            raise DecisionSnapshotError(
                "decision snapshot requires a READY or PARTIAL company scope"
            )

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
    lineage = _locked_lineage(evidence_bundle, execution_plan, decision)
    payload = {
        "schema_version": DECISION_SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": f"decision-snapshot-{generated_id}",
        "status": "LOCKED",
        "version": int(decision.get("version") or 1),
        "supersedes_snapshot_id": supersedes or None,
        "revision_reason": revision_reason or None,
        "research_report_id": report_id,
        "research_report_state": "REVIEWABLE",
        "research_id": str(
            decision.get("research_id")
            or (execution_plan or {}).get("research_id")
            or report_id
        ),
        **lineage,
        **market_lineage,
        "company_id": company_id,
        "display_name": str(report_item.get("display_name") or decision.get("display_name") or ""),
        "candidate_state": candidate_state,
        "company_scope": scope_projection,
        "company_scope_id": str(scope_projection.get("scope_id") or "") if scope_projection else "",
        "company_scope_content_hash": str(scope_projection.get("scope_content_hash") or "") if scope_projection else "",
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
            "lineage_locked": bool(
                lineage["evidence_bundle_id"]
                or lineage["execution_plan_id"]
                or lineage["research_version_id"]
            ),
            "evidence_manifest_locked": bool(lineage["evidence_manifest_hash"]),
            "market_data_lineage_locked": bool(market_lineage["market_data_snapshot_ids"]),
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


def _validate_optional_lineage(
    evidence_bundle: Mapping[str, Any] | None,
    execution_plan: Mapping[str, Any] | None,
    decision: Mapping[str, Any],
) -> None:
    if evidence_bundle is not None:
        if not isinstance(evidence_bundle, Mapping):
            raise DecisionSnapshotError("evidence_bundle must be a JSON object")
        if evidence_bundle.get("schema_version") != EVIDENCE_BUNDLE_SCHEMA_VERSION:
            raise DecisionSnapshotError("evidence_bundle must be evidence-bundle.v1")
        for field in ("bundle_id", "research_as_of"):
            if not str(evidence_bundle.get(field) or "").strip():
                raise DecisionSnapshotError(f"evidence_bundle {field} is required")
        if not isinstance(evidence_bundle.get("evidence_ids"), list):
            raise DecisionSnapshotError("evidence_bundle evidence_ids must be a list")
        cutoff = _calendar_day(str(decision.get("data_cutoff") or ""), "data_cutoff")
        evidence_day = _calendar_day(
            str(evidence_bundle.get("research_as_of") or ""), "evidence_bundle.research_as_of"
        )
        if evidence_day > cutoff:
            raise DecisionSnapshotError(
                "evidence_bundle research_as_of cannot be after decision data_cutoff"
            )
    if execution_plan is not None:
        if not isinstance(execution_plan, Mapping):
            raise DecisionSnapshotError("execution_plan must be a JSON object")
        if execution_plan.get("schema_version") != RESEARCH_EXECUTION_PLAN_SCHEMA_VERSION:
            raise DecisionSnapshotError(
                "execution_plan must be research-execution-plan.v1"
            )
        for field in ("plan_id", "research_as_of", "effective_execution_mode"):
            if not str(execution_plan.get(field) or "").strip():
                raise DecisionSnapshotError(f"execution_plan {field} is required")
        cutoff = _calendar_day(str(decision.get("data_cutoff") or ""), "data_cutoff")
        plan_day = _calendar_day(
            str(execution_plan.get("research_as_of") or ""), "execution_plan.research_as_of"
        )
        if plan_day > cutoff:
            raise DecisionSnapshotError(
                "execution_plan research_as_of cannot be after decision data_cutoff"
            )


def _lock_market_data_lineage(
    snapshots: Sequence[Mapping[str, Any]] | None,
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    if snapshots is None:
        return {
            "market_data_snapshot_ids": [],
            "market_data_snapshot_hashes": [],
        }
    if isinstance(snapshots, (str, bytes, bytearray)):
        raise DecisionSnapshotError("market_data_snapshots must be a list")
    cutoff = _calendar_day(str(decision.get("data_cutoff") or ""), "data_cutoff")
    ids: list[str] = []
    hashes: list[str] = []
    for raw in snapshots:
        try:
            snapshot = build_market_data_snapshot(raw)
        except MarketDataError as error:
            raise DecisionSnapshotError(str(error)) from error
        snapshot_day = _calendar_day(snapshot["research_as_of"], "market_data.research_as_of")
        if snapshot_day > cutoff:
            raise DecisionSnapshotError(
                "market data snapshot research_as_of cannot be after decision data_cutoff"
            )
        snapshot_id = str(snapshot["snapshot_id"])
        if snapshot_id in ids:
            raise DecisionSnapshotError(f"duplicate market data snapshot: {snapshot_id}")
        ids.append(snapshot_id)
        hashes.append(str(snapshot["snapshot_content_hash"]))
    return {
        "market_data_snapshot_ids": ids,
        "market_data_snapshot_hashes": hashes,
    }


def _locked_lineage(
    evidence_bundle: Mapping[str, Any] | None,
    execution_plan: Mapping[str, Any] | None,
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    evidence_ids = list((evidence_bundle or {}).get("evidence_ids") or [])
    manifest = str(
        decision.get("evidence_manifest_hash")
        or (evidence_bundle or {}).get("evidence_manifest_hash")
        or ""
    ).strip()
    if evidence_bundle is not None and not manifest:
        encoded = "|".join(sorted(str(item) for item in evidence_ids))
        manifest = sha256(encoded.encode("utf-8")).hexdigest()
    return {
        "evidence_bundle_id": str(
            decision.get("evidence_bundle_id")
            or (evidence_bundle or {}).get("bundle_id")
            or ""
        ),
        "research_version_id": str(
            decision.get("research_version_id")
            or (execution_plan or {}).get("research_version_id")
            or ""
        ),
        "evidence_manifest_hash": manifest,
        "research_as_of": str(
            decision.get("research_as_of")
            or (evidence_bundle or {}).get("research_as_of")
            or decision.get("data_cutoff")
            or ""
        ),
        "evidence_ids": evidence_ids,
        "execution_plan_id": str(
            decision.get("execution_plan_id")
            or (execution_plan or {}).get("plan_id")
            or ""
        ),
        "research_depth": str(
            decision.get("research_depth")
            or (execution_plan or {}).get("effective_depth")
            or ""
        ).upper(),
        "execution_mode": str(
            decision.get("execution_mode")
            or (execution_plan or {}).get("effective_execution_mode")
            or ""
        ).upper(),
    }


def _calendar_day(value: str, field: str) -> date:
    text = str(value or "").strip()
    if not text:
        raise DecisionSnapshotError(f"{field} is required")
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError as error:
            raise DecisionSnapshotError(f"{field} must be an ISO date or datetime") from error


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
