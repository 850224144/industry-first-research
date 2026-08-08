"""Plan and apply auditable incremental company-research updates."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
import hashlib
import json
from typing import Any

from .research_pipeline import (
    build_incremental_research_pipeline,
    build_research_pipeline,
)
from .supplemental_evidence import build_supplemental_evidence_report
from .company_scope import CompanyScopeError, normalize_scope_reports


INCREMENTAL_UPDATE_SCHEMA_VERSION = "company-incremental-update.v1"
RULE_VERSION = "company-incremental-update-rules.v1"
_EXECUTION_MODES = {"LOCAL_ONLY", "LLM_ASSISTED", "MANUAL_WEB_AI"}

_STAGE_ORDER = (
    "product_profile",
    "application_mapping",
    "demand_transmission",
    "industry_situation",
    "cycle_reversal",
    "competitive_position",
    "survival_analysis",
    "valuation_scenarios",
    "adversarial_review",
    "research_report",
)

# The earliest affected stage is explicit and conservative. Downstream stages
# are rerun because each existing gate consumes the previous gate's projection.
_FIELD_STAGE = {
    "company_scope": "product_profile",
    "reporting_scope": "product_profile",
    "key_products": "product_profile",
    "key_risks": "product_profile",
    "product_list": "product_profile",
    "product_application": "product_profile",
    "customer_purchase_reasons": "product_profile",
    "product_system_layer": "product_profile",
    "product_criticality": "product_profile",
    "substitution_risk": "product_profile",
    "competitors": "product_profile",
    "market_state": "product_profile",
    "profit_sources": "product_profile",
    "product_financial_bridge": "product_profile",
    "lifecycle_state": "product_profile",
    "validation_state": "product_profile",
    "application_mapping": "application_mapping",
    "application_end_market": "application_mapping",
    "demand_driver": "application_mapping",
    "customer_type": "application_mapping",
    "customer_validation": "application_mapping",
    "order_evidence": "application_mapping",
    "shipment_revenue_evidence": "application_mapping",
    "company_supply_capability": "application_mapping",
    "application_competition": "application_mapping",
    "transmission_state": "demand_transmission",
    "demand_evidence": "demand_transmission",
    "technical_feasibility": "demand_transmission",
    "profit_cashflow_evidence": "demand_transmission",
    "company_share_evidence": "demand_transmission",
    "competitive_capture": "demand_transmission",
    "base_case_contribution": "demand_transmission",
    "upside_option": "demand_transmission",
    "industry_demand_horizon": "industry_situation",
    "value_chain_profit_distribution": "industry_situation",
    "supply_demand_state": "industry_situation",
    "inventory_state": "industry_situation",
    "price_state": "industry_situation",
    "utilization_state": "industry_situation",
    "competition_state": "industry_situation",
    "policy_technology_overseas": "industry_situation",
    "cycle_stage": "industry_situation",
    "key_industry_variables": "industry_situation",
    "reversal_conditions": "industry_situation",
    "validation_signals": "industry_situation",
    "product_market_state": "industry_situation",
    "product_competition_matrix": "industry_situation",
    "lifecycle_transition_conditions": "industry_situation",
    "industry_applicability": "cycle_reversal",
    "real_demand": "cycle_reversal",
    "effective_supply": "cycle_reversal",
    "nominal_capacity": "cycle_reversal",
    "capacity_utilization": "cycle_reversal",
    "inventory_level": "cycle_reversal",
    "inventory_holder": "cycle_reversal",
    "spot_price": "cycle_reversal",
    "contract_price": "cycle_reversal",
    "cash_cost": "cycle_reversal",
    "full_cost": "cycle_reversal",
    "marginal_capacity": "cycle_reversal",
    "capex_pipeline": "cycle_reversal",
    "capacity_exit": "cycle_reversal",
    "shutdown_and_bankruptcy": "cycle_reversal",
    "industry_cashflow": "cycle_reversal",
    "recovery_speed": "cycle_reversal",
    "cycle_state": "cycle_reversal",
    "cycle_evidence": "cycle_reversal",
    "confirmation_conditions": "cycle_reversal",
    "confidence": "cycle_reversal",
    "business_model": "competitive_position",
    "revenue_structure": "competitive_position",
    "cost_position": "competitive_position",
    "technology_position": "competitive_position",
    "customer_position": "competitive_position",
    "channel_position": "competitive_position",
    "capital_position": "competitive_position",
    "market_share_position": "competitive_position",
    "competitive_matrix": "competitive_position",
    "delivery_quality": "competitive_position",
    "profitability_quality": "competitive_position",
    "available_cash": "survival_analysis",
    "monthly_cash_burn": "survival_analysis",
    "debt_maturity": "survival_analysis",
    "interest_coverage": "survival_analysis",
    "operating_cashflow": "survival_analysis",
    "free_cashflow_after_maintenance_capex": "survival_analysis",
    "cash_cost_position": "survival_analysis",
    "capex_commitment": "survival_analysis",
    "impairment_risk": "survival_analysis",
    "refinancing_capacity": "survival_analysis",
    "external_support": "survival_analysis",
    "technology_obsolescence_risk": "survival_analysis",
    "effective_capacity": "survival_analysis",
    "recovery_operating_leverage": "survival_analysis",
    "survival_label": "survival_analysis",
    "stress_tests": "survival_analysis",
    "valuation_method": "valuation_scenarios",
    "current_price": "valuation_scenarios",
    "current_price_as_of": "valuation_scenarios",
    "historical_financials": "valuation_scenarios",
    "cycle_center_profit": "valuation_scenarios",
    "net_debt_and_dilution": "valuation_scenarios",
    "scenario_inputs": "valuation_scenarios",
    "implied_assumptions": "valuation_scenarios",
    "evidence_backed_assumptions": "valuation_scenarios",
    "model_assumptions": "valuation_scenarios",
    "excluded_from_base_case": "valuation_scenarios",
    "valuation_sensitivity": "valuation_scenarios",
    "counterevidence": "adversarial_review",
    "invalidators": "adversarial_review",
    "follow_up_checks": "research_report",
    "next_check_at": "research_report",
}


class IncrementalUpdateError(ValueError):
    """Raised when an incremental update cannot preserve research lineage."""


def build_incremental_update(
    previous_pipeline: Mapping[str, Any],
    previous_supplemental: Mapping[str, Any],
    new_evidence_records: Sequence[Mapping[str, Any]],
    *,
    as_of: str = "",
    snapshot_id: str = "",
    execution_mode: str = "LOCAL_ONLY",
    company_scope_reports: Mapping[str, Mapping[str, Any]] | None = None,
    market_structure_report: Mapping[str, Any] | None = None,
    evidence_bundle: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare new evidence, identify affected stages, and create a new version.

    The old pipeline and old supplemental report are never mutated. New raw
    evidence safely starts at ``product_profile``; an independent market
    structure refresh can reuse upstream stages and start at
    ``adversarial_review``. The returned plan records whether the update used a
    partial downstream chain or the bounded full-pipeline fallback.
    """

    _validate_pipeline(previous_pipeline)
    mode = str(execution_mode or "LOCAL_ONLY").strip().upper()
    if mode not in _EXECUTION_MODES:
        raise IncrementalUpdateError(
            "execution_mode must be LOCAL_ONLY, LLM_ASSISTED, or MANUAL_WEB_AI"
        )
    try:
        normalized_scope_reports = normalize_scope_reports(company_scope_reports)
    except CompanyScopeError as error:
        raise IncrementalUpdateError(str(error)) from error
    if market_structure_report is not None and not isinstance(market_structure_report, Mapping):
        raise IncrementalUpdateError("market_structure_report must be an object")
    if evidence_bundle is not None and not isinstance(evidence_bundle, Mapping):
        raise IncrementalUpdateError("evidence_bundle must be an object")
    queue = _queue_from_supplemental(previous_supplemental)
    required_fields = previous_supplemental.get("required_fields") or ()
    if not isinstance(required_fields, list):
        raise IncrementalUpdateError("supplemental required_fields must be a list")
    old_records = _validated_records(queue, previous_supplemental.get("records") or [], required_fields)
    incoming_records = _validated_records(queue, new_evidence_records, required_fields)

    old_by_id = {record["evidence_id"]: record for record in old_records}
    old_by_field = _group_by_field(old_records)
    seen_new_ids: set[str] = set()
    changes_by_company: dict[str, list[dict[str, Any]]] = defaultdict(list)
    accepted_new_records: list[dict[str, Any]] = []
    for record in incoming_records:
        evidence_id = record["evidence_id"]
        if evidence_id in seen_new_ids:
            raise IncrementalUpdateError(f"duplicate new evidence_id: {evidence_id}")
        seen_new_ids.add(evidence_id)
        old_record = old_by_id.get(evidence_id)
        if old_record is not None:
            if _fingerprint(old_record) != _fingerprint(record):
                raise IncrementalUpdateError(
                    f"immutable evidence_id changed: {evidence_id}"
                )
            changes_by_company[record["company_id"]].append(
                _change(record, "DUPLICATE", "")
            )
            continue

        field_key = (record["company_id"], record["field"])
        old_field_records = old_by_field.get(field_key, ())
        if not old_field_records:
            change_type = "NEW"
        elif record["verification_status"] == "CONFLICTING":
            change_type = "CONFLICT"
        elif any(_value_fingerprint(item["value"]) == _value_fingerprint(record["value"]) for item in old_field_records):
            change_type = "REFRESHED"
        else:
            change_type = "CHANGED"
        changes_by_company[record["company_id"]].append(
            _change(record, change_type, _FIELD_STAGE.get(record["field"], "UNKNOWN"))
        )
        accepted_new_records.append(record)

    effective_as_of = _effective_as_of(
        as_of,
        _latest_as_of(incoming_records),
        str(previous_pipeline.get("as_of") or ""),
        str(previous_supplemental.get("as_of") or ""),
    )
    updated_queue = {**queue, "as_of": effective_as_of}
    merged_records = [*old_records, *accepted_new_records]
    if accepted_new_records:
        merged_supplemental = build_supplemental_evidence_report(
            updated_queue,
            merged_records,
            required_fields=required_fields,
            snapshot_id=_version_id(
                previous_pipeline, effective_as_of, snapshot_id, "supplemental"
            ),
        )
    else:
        # No new evidence means the immutable supplemental input can be reused.
        # This is what permits a market-structure-only update to skip all
        # evidence-driven stages without manufacturing a new fact snapshot.
        merged_supplemental = dict(previous_supplemental)

    partial_market_update = bool(
        not accepted_new_records
        and market_structure_report is not None
        and not normalized_scope_reports
        and evidence_bundle is None
    )
    if partial_market_update:
        updated_pipeline = build_incremental_research_pipeline(
            previous_pipeline,
            merged_supplemental,
            rerun_from="adversarial_review",
            market_structure_report=market_structure_report,
            snapshot_id=_version_id(
                previous_pipeline, effective_as_of, snapshot_id, "pipeline"
            ),
        )
        recompute_plan = dict(updated_pipeline.get("incremental_recompute") or {})
        recompute_plan["strategy"] = "PARTIAL_DOWNSTREAM_CHAIN"
    else:
        updated_pipeline = build_research_pipeline(
            merged_supplemental,
            market_structure_report=market_structure_report,
            evidence_bundle=evidence_bundle,
            company_scope_reports=normalized_scope_reports,
            snapshot_id=_version_id(
                previous_pipeline, effective_as_of, snapshot_id, "pipeline"
            ),
        )
        recompute_plan = {
            "strategy": "FULL_PIPELINE_FALLBACK",
            "rerun_from": "product_profile" if accepted_new_records else "research_report",
            "recomputed_modules": list(_STAGE_ORDER),
            "reused_modules": [],
            "previous_pipeline_preserved": True,
        }

    company_updates = []
    for item in queue["items"]:
        company_id = str(item["company_id"])
        changes = changes_by_company.get(company_id, [])
        meaningful = [change for change in changes if change["change_type"] != "DUPLICATE"]
        direct_stages = {
            change["direct_stage"]
            for change in meaningful
            if change["direct_stage"] in _STAGE_ORDER
        }
        earliest = min((_STAGE_ORDER.index(stage) for stage in direct_stages), default=None)
        affected = list(_STAGE_ORDER[earliest:]) if earliest is not None else []
        company_updates.append(
            {
                "company_id": company_id,
                "display_name": str(item.get("display_name") or ""),
                "candidate_state": str(item.get("candidate_state") or ""),
                "update_state": "UPDATED" if meaningful else "NO_NEW_EVIDENCE",
                "thesis_review_state": (
                    "REVIEW_REQUIRED" if meaningful else "UNCHANGED_NOT_PROVEN"
                ),
                "changed_fields": sorted({change["field"] for change in meaningful}),
                "affected_modules": affected,
                "rerun_from": _STAGE_ORDER[earliest] if earliest is not None else None,
                "changes": changes,
            }
        )

    update_id = _version_id(previous_pipeline, effective_as_of, snapshot_id, "update")
    all_changes = [change for changes in changes_by_company.values() for change in changes]
    return {
        "schema_version": INCREMENTAL_UPDATE_SCHEMA_VERSION,
        "update_id": update_id,
        "rule_version": RULE_VERSION,
        "as_of": effective_as_of,
        "previous_pipeline_id": str(previous_pipeline.get("pipeline_id") or ""),
        "previous_supplemental_id": str(previous_supplemental.get("report_id") or ""),
        "updated_pipeline_id": str(updated_pipeline.get("pipeline_id") or ""),
        "research_version_id": "",
        "updated_supplemental_id": str(merged_supplemental.get("report_id") or ""),
        "new_evidence_count": len(accepted_new_records),
        "change_count": sum(change["change_type"] != "DUPLICATE" for change in all_changes),
        "change_counts": _count_changes(
            [change for change in all_changes if change["change_type"] != "DUPLICATE"]
        ),
        "company_updates": company_updates,
        "execution_mode": mode,
        "execution_note": _execution_note(mode),
        "deferred_review_modules": sorted(
            {
                module
                for item in company_updates
                if item["thesis_review_state"] == "REVIEW_REQUIRED"
                for module in item["affected_modules"]
            }
        ),
        "recompute_plan": recompute_plan,
        "lineage": _lineage_summary(
            previous_pipeline,
            updated_pipeline,
            normalized_scope_reports,
            market_structure_report,
            evidence_bundle,
        ),
        "updated_supplemental": merged_supplemental,
        "updated_pipeline": updated_pipeline,
        "policy": {
            "old_versions_preserved": True,
            "immutable_evidence_ids": True,
            "candidate_state_preserved": True,
            "execution_mode_explicit": True,
            "llm_is_not_called_by_incremental_builder": True,
            "manual_web_ai_is_import_only": True,
            "automatic_directional_conclusion": False,
            "automatic_decision_snapshot": False,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _validate_pipeline(report: Mapping[str, Any]) -> None:
    if not isinstance(report, Mapping):
        raise IncrementalUpdateError("previous pipeline must be a JSON object")
    if report.get("schema_version") != "company-research-pipeline.v1":
        raise IncrementalUpdateError("previous pipeline must be company-research-pipeline.v1")
    if not isinstance(report.get("stages"), Mapping):
        raise IncrementalUpdateError("previous pipeline has no stages")


def _execution_note(mode: str) -> str:
    return {
        "LOCAL_ONLY": (
            "Deterministic evidence gates are refreshed locally; no model call is made. "
            "Affected modules remain in the review queue until any semantic review is confirmed."
        ),
        "LLM_ASSISTED": (
            "The update is marked for authorized semantic assistance, but this builder does not "
            "invoke a model; llm_runs must be recorded separately before using model output."
        ),
        "MANUAL_WEB_AI": (
            "The update accepts manually imported web-AI evidence only; it does not log in, browse, "
            "scrape, or call a web-AI service."
        ),
    }[mode]


def _lineage_summary(
    previous_pipeline: Mapping[str, Any],
    updated_pipeline: Mapping[str, Any],
    scope_reports: Mapping[str, Mapping[str, Any]],
    market_structure_report: Mapping[str, Any] | None,
    evidence_bundle: Mapping[str, Any] | None,
) -> dict[str, Any]:
    previous_scope_ids = list(previous_pipeline.get("company_scope_ids") or [])
    current_scope_ids = sorted(
        str(item.get("scope_id") or "")
        for item in scope_reports.values()
        if str(item.get("scope_id") or "")
    )
    previous_market_id = str(previous_pipeline.get("market_data_snapshot_id") or "")
    current_market_id = str(
        (market_structure_report or {}).get("market_data_snapshot_id") or ""
    )
    return {
        "previous_pipeline_id": str(previous_pipeline.get("pipeline_id") or ""),
        "updated_pipeline_id": str(updated_pipeline.get("pipeline_id") or ""),
        "company_scope": {
            "previous_ids": previous_scope_ids,
            "current_ids": current_scope_ids,
            "status": (
                "REFRESHED"
                if current_scope_ids
                else "NOT_SUPPLIED"
                if not previous_scope_ids
                else "REVIEW_REQUIRED_PREVIOUS_SCOPE_NOT_REHYDRATED"
            ),
        },
        "market_data": {
            "previous_id": previous_market_id,
            "current_id": current_market_id,
            "status": (
                "REFRESHED"
                if current_market_id
                else "NOT_SUPPLIED"
                if not previous_market_id
                else "REVIEW_REQUIRED_PREVIOUS_MARKET_DATA_NOT_REHYDRATED"
            ),
        },
        "evidence_bundle_id": str((evidence_bundle or {}).get("bundle_id") or ""),
    }


def _queue_from_supplemental(report: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(report, Mapping):
        raise IncrementalUpdateError("previous supplemental must be a JSON object")
    if report.get("schema_version") != "company-supplemental-evidence.v1":
        raise IncrementalUpdateError(
            "previous supplemental must be company-supplemental-evidence.v1"
        )
    raw_items = report.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise IncrementalUpdateError("previous supplemental has no items")
    items = []
    for item in raw_items:
        if not isinstance(item, Mapping) or not str(item.get("company_id") or "").strip():
            raise IncrementalUpdateError("previous supplemental has invalid company item")
        items.append(
            {
                "company_id": str(item.get("company_id") or ""),
                "display_name": str(item.get("display_name") or ""),
                "industry_id": str(item.get("industry_id") or ""),
                "candidate_state": str(item.get("candidate_state") or "WATCH"),
                "rule_version": str(item.get("candidate_rule_version") or ""),
                "reasons": list(item.get("candidate_reasons") or []),
                "blockers": list(item.get("candidate_blockers") or []),
                "evidence_gaps": list(item.get("candidate_evidence_gaps") or []),
                "field_sources": dict(item.get("candidate_field_sources") or {}),
                "additional_sources": list(item.get("candidate_additional_sources") or []),
            }
        )
    return {
        "schema_version": "company-candidate-queue.v1",
        "queue_id": str(report.get("input_queue_id") or "previous-queue"),
        "input_snapshot_id": str(report.get("input_snapshot_id") or ""),
        "as_of": str(report.get("as_of") or ""),
        "source": str(report.get("source") or ""),
        "source_metadata": report.get("source_metadata") or {},
        "items": items,
    }


def _validated_records(
    queue: Mapping[str, Any], records: Any, required_fields: Sequence[str]
) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        raise IncrementalUpdateError("evidence records must be a list")
    try:
        report = build_supplemental_evidence_report(
            queue, records, required_fields=required_fields
        )
    except ValueError as error:
        raise IncrementalUpdateError(str(error)) from error
    return list(report["records"])


def _group_by_field(records: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[(str(record["company_id"]), str(record["field"]))].append(record)
    return grouped


def _change(record: Mapping[str, Any], change_type: str, direct_stage: str) -> dict[str, Any]:
    return {
        "evidence_id": str(record["evidence_id"]),
        "company_id": str(record["company_id"]),
        "field": str(record["field"]),
        "change_type": change_type,
        "direct_stage": direct_stage,
        "as_of": str(record.get("as_of") or ""),
        "source": str(record.get("source") or ""),
        "verification_status": str(record.get("verification_status") or ""),
        "value_hash": _value_fingerprint(record.get("value")),
    }


def _count_changes(changes: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for change in changes:
        key = str(change.get("change_type") or "UNKNOWN")
        result[key] = result.get(key, 0) + 1
    return result


def _fingerprint(record: Mapping[str, Any]) -> str:
    return _value_fingerprint(
        {
            key: record.get(key)
            for key in (
                "company_id",
                "field",
                "value",
                "source",
                "source_refs",
                "as_of",
                "evidence_tier",
                "verification_status",
                "note",
            )
        }
    )


def _value_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _latest_as_of(records: Sequence[Mapping[str, Any]]) -> str:
    values = [str(record.get("as_of") or "") for record in records]
    return max((value for value in values if value), default="")


def _effective_as_of(*values: str) -> str:
    return max((value.strip() for value in values if value and value.strip()), default="")


def _version_id(previous_pipeline: Mapping[str, Any], as_of: str, snapshot_id: str, kind: str) -> str:
    base = snapshot_id.strip() or str(previous_pipeline.get("pipeline_id") or "pipeline")
    suffix = as_of.strip() or date.today().isoformat()
    return f"{kind}-{base}-{suffix}"
