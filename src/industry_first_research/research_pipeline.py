"""Run the bounded company deep-research stages as one auditable pipeline."""

from __future__ import annotations

from collections.abc import Mapping
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
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Run every bounded evidence gate without creating an investment conclusion."""

    _validate_input(supplemental_report)
    if market_structure_report is not None and not isinstance(
        market_structure_report, Mapping
    ):
        raise ValueError("market_structure_report must be a JSON object")

    product_profile = build_product_profile_report(supplemental_report)
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
        "final_state": _single_state(final_counts),
        "stage_summary": stage_summary,
        "stages": stages,
        "policy": {
            "bounded_company_research_only": True,
            "candidate_state_preserved": True,
            "evidence_only": True,
            "investment_conclusion": False,
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
        raise ValueError("input supplemental report must be a JSON object")
    if report.get("schema_version") != "company-supplemental-evidence.v1":
        raise ValueError("input must be a company-supplemental-evidence.v1 report")
    if not isinstance(report.get("items"), list):
        raise ValueError("supplemental report has no items list")


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
