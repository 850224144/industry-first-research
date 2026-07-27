"""Run the bounded company deep-research stages as one auditable pipeline."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .adversarial_review import build_adversarial_review_report
from .application_mapping import build_application_mapping_report
from .competitive_position import build_competitive_position_report
from .cycle_reversal import build_cycle_reversal_report
from .demand_transmission import build_demand_transmission_report
from .industry_situation import build_industry_situation_report
from .product_profile import build_product_profile_report
from .research_report import build_research_report
from .survival_analysis import build_survival_analysis_report
from .valuation_scenarios import build_valuation_scenarios_report
from .company_scope import CompanyScopeError, normalize_scope_reports


EVIDENCE_BUNDLE_SCHEMA_VERSION = "evidence-bundle.v1"


RESEARCH_PIPELINE_SCHEMA_VERSION = "company-research-pipeline.v1"
PIPELINE_RULE_VERSION = "company-research-pipeline-rules.v1"

_STAGES = (
    ("product_profile", "profile_state_counts"),
    ("application_mapping", "mapping_state_counts"),
    ("demand_transmission", "transmission_state_counts"),
    ("industry_situation", "industry_situation_state_counts"),
    ("cycle_reversal", "cycle_reversal_gate_state_counts"),
    ("competitive_position", "competitive_position_state_counts"),
    ("survival_analysis", "survival_gate_state_counts"),
    ("valuation_scenarios", "valuation_gate_state_counts"),
    ("adversarial_review", "audit_state_counts"),
    ("research_report", "report_state_counts"),
)


def build_research_pipeline(
    supplemental_report: Mapping[str, Any],
    *,
    market_structure_report: Mapping[str, Any] | None = None,
    evidence_bundle: Mapping[str, Any] | None = None,
    company_scope_reports: Mapping[str, Mapping[str, Any]] | None = None,
    product_profit_bridge_report: Mapping[str, Any] | None = None,
    product_lifecycle_report: Mapping[str, Any] | None = None,
    financial_model_report: Mapping[str, Any] | None = None,
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Run every bounded evidence gate without creating an investment conclusion."""

    _validate_input(supplemental_report)
    if market_structure_report is not None and not isinstance(
        market_structure_report, Mapping
    ):
        raise ValueError("market_structure_report must be a JSON object")
    if evidence_bundle is not None:
        _validate_evidence_bundle(evidence_bundle)
    if product_profit_bridge_report is not None:
        if not isinstance(product_profit_bridge_report, Mapping):
            raise ValueError("product_profit_bridge_report must be a JSON object")
        if product_profit_bridge_report.get("schema_version") != "product-profit-bridge.v1":
            raise ValueError("product_profit_bridge_report must be product-profit-bridge.v1")
    if product_lifecycle_report is not None:
        if not isinstance(product_lifecycle_report, Mapping):
            raise ValueError("product_lifecycle_report must be a JSON object")
        if product_lifecycle_report.get("schema_version") != "product-lifecycle-snapshot.v1":
            raise ValueError("product_lifecycle_report must be product-lifecycle-snapshot.v1")
    if financial_model_report is not None:
        if not isinstance(financial_model_report, Mapping):
            raise ValueError("financial_model_report must be a JSON object")
        if financial_model_report.get("schema_version") != "financial-model.v1":
            raise ValueError("financial_model_report must be financial-model.v1")

    try:
        normalized_scope_reports = normalize_scope_reports(company_scope_reports)
    except CompanyScopeError as error:
        raise ValueError(str(error)) from error
    product_profile = build_product_profile_report(
        supplemental_report,
        company_scope_reports=normalized_scope_reports,
    )
    application_mapping = build_application_mapping_report(product_profile)
    demand_transmission = build_demand_transmission_report(application_mapping)
    industry_situation = build_industry_situation_report(demand_transmission)
    cycle_reversal = build_cycle_reversal_report(industry_situation)
    competitive_position = build_competitive_position_report(cycle_reversal)
    survival_analysis = build_survival_analysis_report(competitive_position)
    valuation_scenarios = build_valuation_scenarios_report(survival_analysis)
    adversarial_review = build_adversarial_review_report(
        valuation_scenarios,
        market_structure_report=market_structure_report,
    )
    research_report = build_research_report(adversarial_review)

    stages = {
        "product_profile": product_profile,
        "application_mapping": application_mapping,
        "demand_transmission": demand_transmission,
        "industry_situation": industry_situation,
        "cycle_reversal": cycle_reversal,
        "competitive_position": competitive_position,
        "survival_analysis": survival_analysis,
        "valuation_scenarios": valuation_scenarios,
        "adversarial_review": adversarial_review,
        "research_report": research_report,
    }
    if product_profit_bridge_report is not None:
        stages["product_profit_bridge"] = product_profit_bridge_report
    if product_lifecycle_report is not None:
        stages["product_lifecycle"] = product_lifecycle_report
    if financial_model_report is not None:
        stages["financial_model"] = financial_model_report
    stage_summary = {
        name: _stage_summary(stages[name], count_key)
        for name, count_key in _STAGES
    }
    input_report_id = str(supplemental_report.get("report_id") or "")
    report_id = snapshot_id or input_report_id or "supplemental-input"
    final_counts = research_report.get("report_state_counts") or {}
    return {
        "schema_version": RESEARCH_PIPELINE_SCHEMA_VERSION,
        "pipeline_id": f"company-research-pipeline-{report_id}",
        "research_version_id": "",
        "rule_version": PIPELINE_RULE_VERSION,
        "input_supplemental_id": input_report_id,
        "input_queue_id": str(supplemental_report.get("input_queue_id") or ""),
        "input_snapshot_id": str(supplemental_report.get("input_snapshot_id") or ""),
        "as_of": str(supplemental_report.get("as_of") or ""),
        "source": str(supplemental_report.get("source") or ""),
        "source_metadata": supplemental_report.get("source_metadata") or {},
        "candidate_count": int(
            supplemental_report.get("candidate_count")
            or len(supplemental_report.get("items") or [])
        ),
        "market_structure_review": (
            "SUPPLIED" if market_structure_report is not None else "OPTIONAL_NOT_SUPPLIED"
        ),
        "evidence_bundle_review": (
            "SUPPLIED" if evidence_bundle is not None else "OPTIONAL_NOT_SUPPLIED"
        ),
        "evidence_bundle_id": str(evidence_bundle.get("bundle_id") or "")
        if evidence_bundle is not None
        else "",
        "product_profit_bridge_review": (
            "SUPPLIED" if product_profit_bridge_report is not None else "OPTIONAL_NOT_SUPPLIED"
        ),
        "product_profit_bridge_id": str(
            product_profit_bridge_report.get("report_id") or ""
        )
        if product_profit_bridge_report is not None
        else "",
        "product_lifecycle_review": (
            "SUPPLIED" if product_lifecycle_report is not None else "OPTIONAL_NOT_SUPPLIED"
        ),
        "product_lifecycle_id": str(product_lifecycle_report.get("report_id") or "")
        if product_lifecycle_report is not None
        else "",
        "financial_model_review": (
            "SUPPLIED" if financial_model_report is not None else "OPTIONAL_NOT_SUPPLIED"
        ),
        "financial_model_id": str(financial_model_report.get("report_id") or "")
        if financial_model_report is not None
        else "",
        "evidence_manifest_hash": _evidence_manifest_hash(evidence_bundle),
        "evidence_bundle_status": str(evidence_bundle.get("status") or "")
        if evidence_bundle is not None
        else "",
        "company_scope_review": "SUPPLIED" if company_scope_reports is not None else "OPTIONAL_NOT_SUPPLIED",
        "company_scope_ids": sorted(
            str(item.get("scope_id") or "")
            for item in normalized_scope_reports.values()
            if isinstance(item, Mapping) and str(item.get("scope_id") or "")
        ),
        "market_data_snapshot_id": str(
            (market_structure_report or {}).get("market_data_snapshot_id") or ""
        ),
        "evidence_cutoff_status": (
            "SAFE"
            if evidence_bundle is not None
            and not (evidence_bundle.get("excluded_future_evidence_ids") or [])
            and not (evidence_bundle.get("unknown_temporal_evidence_ids") or [])
            else "REVIEW_REQUIRED"
            if evidence_bundle is not None
            else "NOT_SUPPLIED"
        ),
        "final_state": _single_state(final_counts),
        "stage_summary": stage_summary,
        "stages": stages,
        "policy": {
            "bounded_company_research_only": True,
            "candidate_state_preserved": True,
            "evidence_only": True,
            "unified_evidence_bundle_is_reference": True,
            "future_evidence_cannot_backfill": True,
            "investment_conclusion": False,
            "target_price_generated": False,
            "product_profit_bridge_is_reference_only": True,
            "product_lifecycle_is_reference_only": True,
            "financial_model_is_reference_only": True,
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


def build_incremental_research_pipeline(
    previous_pipeline: Mapping[str, Any],
    supplemental_report: Mapping[str, Any],
    *,
    rerun_from: str,
    market_structure_report: Mapping[str, Any] | None = None,
    evidence_bundle: Mapping[str, Any] | None = None,
    company_scope_reports: Mapping[str, Mapping[str, Any]] | None = None,
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Reuse immutable upstream stages and rebuild only the downstream chain.

    Raw supplemental evidence changes the product-profile input, so callers must
    use ``product_profile`` as the start stage for those updates.  Later starts
    are intended for independent inputs such as a newly supplied market
    structure snapshot; silently reusing a product profile with a different
    supplemental report would hide evidence.
    """

    _validate_input(supplemental_report)
    if not isinstance(previous_pipeline, Mapping):
        raise ValueError("previous_pipeline must be a JSON object")
    if previous_pipeline.get("schema_version") != RESEARCH_PIPELINE_SCHEMA_VERSION:
        raise ValueError("previous_pipeline must be company-research-pipeline.v1")
    previous_stages = previous_pipeline.get("stages")
    if not isinstance(previous_stages, Mapping):
        raise ValueError("previous_pipeline has no stages")

    stage_names = tuple(name for name, _ in _STAGES)
    start = str(rerun_from or "").strip()
    if start not in stage_names:
        raise ValueError(f"unsupported incremental rerun_from: {start or '<empty>'}")
    previous_input_id = str(previous_pipeline.get("input_supplemental_id") or "")
    current_input_id = str(supplemental_report.get("report_id") or "")
    if start != "product_profile" and previous_input_id != current_input_id:
        raise ValueError(
            "incremental stages after product_profile require the same supplemental report"
        )

    if market_structure_report is not None and not isinstance(
        market_structure_report, Mapping
    ):
        raise ValueError("market_structure_report must be a JSON object")
    if evidence_bundle is not None:
        _validate_evidence_bundle(evidence_bundle)
    try:
        normalized_scope_reports = normalize_scope_reports(company_scope_reports)
    except CompanyScopeError as error:
        raise ValueError(str(error)) from error

    start_index = stage_names.index(start)
    stages: dict[str, dict[str, Any]] = {}
    for index, (name, _count_key) in enumerate(_STAGES):
        if index < start_index:
            previous_stage = previous_stages.get(name)
            if not isinstance(previous_stage, Mapping):
                raise ValueError(f"previous_pipeline is missing reusable stage: {name}")
            stages[name] = deepcopy(dict(previous_stage))
            continue

        if name == "product_profile":
            stages[name] = build_product_profile_report(
                supplemental_report,
                company_scope_reports=normalized_scope_reports,
            )
        elif name == "application_mapping":
            stages[name] = build_application_mapping_report(stages["product_profile"])
        elif name == "demand_transmission":
            stages[name] = build_demand_transmission_report(stages["application_mapping"])
        elif name == "industry_situation":
            stages[name] = build_industry_situation_report(stages["demand_transmission"])
        elif name == "cycle_reversal":
            stages[name] = build_cycle_reversal_report(stages["industry_situation"])
        elif name == "competitive_position":
            stages[name] = build_competitive_position_report(stages["cycle_reversal"])
        elif name == "survival_analysis":
            stages[name] = build_survival_analysis_report(stages["competitive_position"])
        elif name == "valuation_scenarios":
            stages[name] = build_valuation_scenarios_report(stages["survival_analysis"])
        elif name == "adversarial_review":
            if (
                market_structure_report is None
                and str(previous_pipeline.get("market_structure_review") or "") == "SUPPLIED"
            ):
                raise ValueError(
                    "market_structure_report is required to rebuild adversarial_review"
                )
            stages[name] = build_adversarial_review_report(
                stages["valuation_scenarios"],
                market_structure_report=market_structure_report,
            )
        elif name == "research_report":
            stages[name] = build_research_report(stages["adversarial_review"])

    for optional_name in ("product_profit_bridge", "product_lifecycle", "financial_model"):
        previous_optional = previous_stages.get(optional_name)
        if isinstance(previous_optional, Mapping):
            stages[optional_name] = deepcopy(dict(previous_optional))

    input_report_id = str(supplemental_report.get("report_id") or "")
    report_id = snapshot_id or input_report_id or "supplemental-input"
    final_counts = stages["research_report"].get("report_state_counts") or {}
    return {
        "schema_version": RESEARCH_PIPELINE_SCHEMA_VERSION,
        "pipeline_id": f"company-research-pipeline-{report_id}",
        "research_version_id": "",
        "previous_pipeline_id": str(previous_pipeline.get("pipeline_id") or ""),
        "rule_version": PIPELINE_RULE_VERSION,
        "input_supplemental_id": input_report_id,
        "input_queue_id": str(supplemental_report.get("input_queue_id") or ""),
        "input_snapshot_id": str(supplemental_report.get("input_snapshot_id") or ""),
        "as_of": str(supplemental_report.get("as_of") or ""),
        "source": str(supplemental_report.get("source") or ""),
        "source_metadata": supplemental_report.get("source_metadata") or {},
        "candidate_count": int(
            supplemental_report.get("candidate_count")
            or len(supplemental_report.get("items") or [])
        ),
        "market_structure_review": (
            "SUPPLIED" if market_structure_report is not None else str(
                previous_pipeline.get("market_structure_review") or "OPTIONAL_NOT_SUPPLIED"
            )
        ),
        "evidence_bundle_review": (
            "SUPPLIED" if evidence_bundle is not None else str(
                previous_pipeline.get("evidence_bundle_review") or "OPTIONAL_NOT_SUPPLIED"
            )
        ),
        "evidence_bundle_id": str(evidence_bundle.get("bundle_id") or "")
        if evidence_bundle is not None
        else str(previous_pipeline.get("evidence_bundle_id") or ""),
        "evidence_bundle_status": str(evidence_bundle.get("status") or "")
        if evidence_bundle is not None
        else str(previous_pipeline.get("evidence_bundle_status") or ""),
        "evidence_manifest_hash": _evidence_manifest_hash(evidence_bundle)
        if evidence_bundle is not None
        else str(previous_pipeline.get("evidence_manifest_hash") or ""),
        "product_profit_bridge_review": (
            "SUPPLIED"
            if isinstance(stages.get("product_profit_bridge"), Mapping)
            else str(previous_pipeline.get("product_profit_bridge_review") or "OPTIONAL_NOT_SUPPLIED")
        ),
        "product_profit_bridge_id": str(
            (stages.get("product_profit_bridge") or {}).get("report_id")
            if isinstance(stages.get("product_profit_bridge"), Mapping)
            else previous_pipeline.get("product_profit_bridge_id") or ""
        ),
        "product_lifecycle_review": (
            "SUPPLIED"
            if isinstance(stages.get("product_lifecycle"), Mapping)
            else str(previous_pipeline.get("product_lifecycle_review") or "OPTIONAL_NOT_SUPPLIED")
        ),
        "product_lifecycle_id": str(
            (stages.get("product_lifecycle") or {}).get("report_id")
            if isinstance(stages.get("product_lifecycle"), Mapping)
            else previous_pipeline.get("product_lifecycle_id") or ""
        ),
        "financial_model_review": (
            "SUPPLIED"
            if isinstance(stages.get("financial_model"), Mapping)
            else str(previous_pipeline.get("financial_model_review") or "OPTIONAL_NOT_SUPPLIED")
        ),
        "financial_model_id": str(
            (stages.get("financial_model") or {}).get("report_id")
            if isinstance(stages.get("financial_model"), Mapping)
            else previous_pipeline.get("financial_model_id") or ""
        ),
        "company_scope_review": (
            "SUPPLIED" if company_scope_reports is not None else str(
                previous_pipeline.get("company_scope_review") or "OPTIONAL_NOT_SUPPLIED"
            )
        ),
        "company_scope_ids": sorted(
            str(item.get("scope_id") or "")
            for item in normalized_scope_reports.values()
            if isinstance(item, Mapping) and str(item.get("scope_id") or "")
        ) or list(previous_pipeline.get("company_scope_ids") or []),
        "market_data_snapshot_id": str(
            (market_structure_report or {}).get("market_data_snapshot_id")
            or previous_pipeline.get("market_data_snapshot_id")
            or ""
        ),
        "evidence_cutoff_status": (
            "SAFE"
            if evidence_bundle is not None
            and not (evidence_bundle.get("excluded_future_evidence_ids") or [])
            and not (evidence_bundle.get("unknown_temporal_evidence_ids") or [])
            else "REVIEW_REQUIRED"
            if evidence_bundle is not None
            else str(previous_pipeline.get("evidence_cutoff_status") or "NOT_SUPPLIED")
        ),
        "final_state": _single_state(final_counts),
        "stage_summary": {
            name: _stage_summary(stages[name], count_key)
            for name, count_key in _STAGES
        },
        "stages": stages,
        "incremental_recompute": {
            "rerun_from": start,
            "recomputed_modules": list(stage_names[start_index:]),
            "reused_modules": list(stage_names[:start_index]),
            "previous_pipeline_preserved": True,
        },
        "policy": {
            "bounded_company_research_only": True,
            "candidate_state_preserved": True,
            "evidence_only": True,
            "unified_evidence_bundle_is_reference": True,
            "future_evidence_cannot_backfill": True,
            "incremental_recompute_is_downstream_only": True,
            "investment_conclusion": False,
            "target_price_generated": False,
            "product_profit_bridge_is_reference_only": True,
            "product_lifecycle_is_reference_only": True,
            "financial_model_is_reference_only": True,
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
        raise ValueError("input supplemental report must be a JSON object")
    if report.get("schema_version") != "company-supplemental-evidence.v1":
        raise ValueError("input must be a company-supplemental-evidence.v1 report")
    if not isinstance(report.get("items"), list):
        raise ValueError("supplemental report has no items list")


def _validate_evidence_bundle(bundle: Mapping[str, Any]) -> None:
    if bundle.get("schema_version") != EVIDENCE_BUNDLE_SCHEMA_VERSION:
        raise ValueError("evidence_bundle must be an evidence-bundle.v1 package")
    if not str(bundle.get("bundle_id") or "").strip():
        raise ValueError("evidence_bundle bundle_id is required")
    if not str(bundle.get("research_as_of") or "").strip():
        raise ValueError("evidence_bundle research_as_of is required")
    if not isinstance(bundle.get("evidence"), list):
        raise ValueError("evidence_bundle has no evidence list")
    if not isinstance(bundle.get("cutoff_validation"), Mapping):
        raise ValueError("evidence_bundle has no cutoff_validation")


def _evidence_manifest_hash(bundle: Mapping[str, Any] | None) -> str:
    if bundle is None:
        return ""
    value = bundle.get("evidence_ids") or []
    encoded = "|".join(sorted(str(item) for item in value))
    import hashlib

    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _stage_summary(report: Mapping[str, Any], count_key: str) -> dict[str, Any]:
    counts = report.get(count_key) or {}
    items = report.get("items") or []
    return {
        "schema_version": str(report.get("schema_version") or ""),
        "report_id": str(report.get("report_id") or ""),
        "candidate_count": len(items),
        "state_counts": dict(counts) if isinstance(counts, Mapping) else {},
        "candidate_states": sorted(
            {
                str(item.get("candidate_state") or "")
                for item in items
                if isinstance(item, Mapping) and item.get("candidate_state")
            }
        ),
    }


def _single_state(counts: Mapping[str, Any]) -> str:
    if len(counts) == 1:
        return str(next(iter(counts)))
    if not counts:
        return "NO_ITEMS"
    return "MIXED"
