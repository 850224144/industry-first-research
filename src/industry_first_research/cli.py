"""Command line entry points for the first local-only prototype."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
from typing import Any

from .company_research import CompanyResearchAssembler, snapshot_from_config
from .cross_validation import CrossSourceIndustryRadar
from .adapters import ChainedCompanyData
from .company_screen import CompanyScreenError, screen_company_candidates
from .candidate_queue import CandidateQueueError, build_candidate_queue
from .supplemental_evidence import (
    SupplementalEvidenceError,
    build_supplemental_evidence_report,
)
from .researchability import ResearchabilityError, build_researchability_report
from .quick_research import QuickResearchError, build_quick_research_report
from .product_profile import ProductProfileError, build_product_profile_report
from .product_profit_bridge import (
    ProductProfitBridgeError,
    build_product_profit_bridge_report,
    validate_product_profit_bridge_report,
)
from .product_lifecycle import (
    ProductLifecycleError,
    build_product_lifecycle_report,
    validate_product_lifecycle_report,
)
from .financial_model import (
    FinancialModelError,
    build_financial_model_report,
    validate_financial_model_report,
)
from .application_mapping import (
    ApplicationMappingError,
    build_application_mapping_report,
)
from .demand_transmission import (
    DemandTransmissionError,
    build_demand_transmission_report,
)
from .industry_situation import (
    IndustrySituationError,
    build_industry_situation_report,
)
from .cycle_reversal import CycleReversalError, build_cycle_reversal_report
from .competitive_position import (
    CompetitivePositionError,
    build_competitive_position_report,
)
from .survival_analysis import SurvivalAnalysisError, build_survival_analysis_report
from .valuation_scenarios import (
    ValuationScenarioError,
    build_valuation_scenarios_report,
)
from .market_structure import MarketStructureError, build_market_structure_report
from .market_structure_adapters import (
    ChanPyAdapter,
    CzscAdapter,
    MarketStructureAdapterError,
    build_market_structure_comparison,
)
from .adversarial_review import (
    AdversarialReviewError,
    build_adversarial_review_report,
)
from .research_report import ResearchReportError, build_research_report
from .report_rendering import (
    ReportRenderingError,
    write_rendered_reports,
)
from .public_draft import PublicDraftError, build_public_draft, validate_public_draft
from .research_pipeline import build_research_pipeline
from .incremental_update import IncrementalUpdateError, build_incremental_update
from .scheduler import (
    SchedulerError,
    build_default_schedule,
    build_scheduler_plan,
    build_scheduler_state,
)
from .tracking import (
    TrackingError,
    build_evidence_freshness_report,
    build_holding_thesis_check,
    build_research_version_comparison,
)
from .scheduled_tasks import LocalScheduledTaskRunner, ScheduledTaskRunnerError
from .holding_thesis import HoldingThesisError, build_holding_thesis
from .decision_snapshot import DecisionSnapshotError, build_decision_snapshot
from .attribution import AttributionError, build_attribution_report
from .quality_scorecard import QualityScorecardError, build_quality_scorecard
from .simulation_portfolio import (
    SimulationPortfolioError,
    build_simulation_portfolio,
    replay_simulation_portfolio,
)
from .futures_simulation import (
    FuturesSimulationError,
    build_futures_simulation,
    replay_futures_simulation,
)
from .opportunity_candidate import (
    OpportunityCandidateError,
    build_opportunity_candidate,
    build_opportunity_scan,
)
from .announcement_asset import (
    AnnouncementAssetError,
    build_announcement_asset,
    build_announcement_impact,
)
from .announcement_templates import (
    AnnouncementTemplateError,
    get_template,
    load_template_catalog,
    parse_announcement_input,
)
from .research_impact import (
    ResearchImpactError,
    build_research_impact_queue,
    validate_research_impact_queue,
)
from .source_health import (
    SourceHealthError,
    build_source_health_snapshot,
    validate_source_health_snapshot,
)
from .source_integrity import (
    apply_source_integrity,
    build_source_integrity_report,
)
from .data_refresh import (
    DataRefreshError,
    build_data_source_refresh,
    validate_data_source_refresh,
)
from .refresh_evidence import (
    RefreshEvidenceError,
    build_refresh_evidence_gate,
    validate_refresh_evidence_gate,
)
from .data_refresh_tracking import (
    DataRefreshTrackingError,
    build_data_refresh_tracking_report,
    validate_data_refresh_tracking_report,
)
from .task_resolution import (
    TaskResolutionError,
    resolve_research_task,
    validate_research_task,
)
from .third_party_components import (
    ThirdPartyComponentError,
    ThirdPartyComponentRegistry,
    build_component_health_snapshot,
    build_component_registry,
    build_performance_metrics_report,
    parse_local_document,
    validate_component_health_snapshot,
    validate_component_registry_links,
    validate_component_registry,
    validate_performance_metrics_report,
)
from .third_party_candidate_review import (
    ThirdPartyCandidateReviewError,
    build_candidate_review,
    build_candidate_review_event,
    build_candidate_review_projection,
    validate_candidate_review,
    validate_candidate_review_event,
    validate_candidate_review_projection,
)
from .futures_identity import FuturesIdentityError, identify_futures_object
from .futures_fundamentals import (
    FuturesFundamentalsError,
    build_futures_fundamentals_report,
)
from .futures_refresh import (
    FuturesRefreshMappingError,
    build_futures_fundamentals_input_from_refresh,
)
from .web import WebApplicationError, run_web_server
from .futures_tracking import FuturesTrackingError, build_futures_tracking_report
from .futures_company_exposure import (
    FuturesCompanyExposureError,
    build_futures_company_exposure_report,
)
from .commodity_adapters import (
    CommodityAdapterError,
    CommodityAdapterRegistry,
    build_commodity_adapter_registry_report,
    build_commodity_adapter_validation_report,
)
from .research_assets import (
    ResearchAssetAdapter,
    ResearchAssetCompanyPool,
    ResearchAssetError,
)
from .security_master import (
    SecurityMasterError,
    build_security_master_snapshot,
    validate_security_master_snapshot,
)
from .company_scope import (
    CompanyScopeError,
    build_company_scope_report,
    normalize_scope_reports,
    validate_company_scope_report,
)
from .market_data import (
    MarketDataError,
    build_market_data_snapshot,
    validate_market_data_snapshot,
)
from .market_registry import (
    MarketRegistry,
    MarketRegistryError,
    build_market_registry_report,
    validate_market_reference,
)
from .industry_adapters import (
    IndustryAdapterError,
    IndustryAdapterRegistry,
    build_industry_adapter_registry_report,
    build_industry_profile_report,
)
from .evidence import (
    EvidenceError,
    build_evidence,
    build_evidence_bundle,
    build_evidence_input_bundle,
    build_model_assumption,
    build_research_artifact,
    build_research_candidate_set,
    build_scorecard_artifact,
    build_source_document,
    reconcile_evidence,
    validate_evidence_cutoff,
)
from .research_execution import (
    ResearchExecutionError,
    build_execution_audit,
    build_llm_run,
    build_research_execution_plan,
    build_research_request,
)
from .research_version import (
    ResearchVersionError,
    build_research_version,
    build_research_version_comparison,
    build_research_version_from_pipeline,
    build_research_version_replay,
    validate_research_version,
)
from .capability_matrix import (
    CapabilityMatrixError,
    build_capability_gap,
    build_capability_matrix,
)
from .opportunity_quality import (
    OpportunityQualityError,
    build_opportunity_quality_report,
)
from .decision_lifecycle import (
    DecisionLifecycleError,
    build_decision_lifecycle,
    build_decision_lifecycle_event,
)
from .manual_evidence import (
    ManualEvidenceTemplateError,
    build_manual_evidence_template,
)
from .eastmoney import EastmoneyAPIError, EastmoneyIndustryRadar
from .eastmoney_company_survey import EastmoneyCompanySurveyData
from .data_sources import default_data_source_router
from .external_ai import ExternalAIResearchRecord
from .industry_radar import IndustryRadarCollector
from .industry_aliases import IndustryAliasError, IndustryAliasRegistry
from .models import (
    CompanyCandidate,
    CompanyDataTier,
    IndustryRadarSnapshot,
    IndustrySignal,
    IndustryState,
    ResourcePolicy,
)
from .pipeline import (
    InMemoryCompanyPool,
    InMemoryRadar,
    IndustryFirstDiscovery,
    PassThroughCompanyData,
    PassThroughDeepResearch,
    current_as_of,
)
from .config import (
    candidates_from_config,
    load_company_config,
    load_config,
    load_radar_config,
    radar_from_config,
    source_documents,
)
from .local_assets import ConfigCompanyPool, LocalAssetDataProvider, LocalResearchAssetCatalog
from .report import render_scan_html, render_scan_markdown
from .storage import (
    ArtifactSnapshotError,
    ImmutableFileExistsError,
    JsonSnapshotStore,
    SnapshotExistsError,
    SnapshotIdError,
    write_bytes_immutable,
    write_files_immutable,
    write_text_immutable,
)
from .trend import RadarTrendError, build_trend_report, write_trend_report


def _payload_hash_without_version_id(payload: Mapping[str, Any]) -> str:
    value = {key: item for key, item in payload.items() if key != "research_version_id"}
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _research_version_content_hash(version: Mapping[str, Any]) -> str:
    value = {key: item for key, item in version.items() if key != "content_hash"}
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _store_artifact(
    parser: argparse.ArgumentParser,
    store: JsonSnapshotStore,
    artifact_id: str,
    payload: dict[str, Any],
) -> Path:
    try:
        return store.write_artifact(artifact_id, payload)
    except (ArtifactSnapshotError, SnapshotExistsError, SnapshotIdError) as error:
        parser.error(str(error))
from .tonghuashun import TonghuashunAPIError, TonghuashunIndustryRadar
from .tonghuashun_company_pool import TonghuashunCompanyPool, TonghuashunCompanyPoolError
from .tonghuashun_light_data import TonghuashunLightCompanyData


def demo() -> dict:
    as_of = current_as_of()
    snapshots = [
        IndustryRadarSnapshot(
            industry_id="example-cycle-industry",
            display_name="示例周期行业",
            as_of=as_of,
            state=IndustryState.INFLECTION_CANDIDATE,
            evidence_completeness="CROSS_VALIDATED",
            opportunity_types=("cycle_reversal",),
            signals=(
                IndustrySignal("inventory", "falling", as_of, "demo", "VERIFIED"),
                IndustrySignal("price_cost", "below_cost", as_of, "demo", "VERIFIED"),
            ),
        ),
        IndustryRadarSnapshot(
            industry_id="example-weak-industry",
            display_name="暂不入选行业",
            as_of=as_of,
            state=IndustryState.DETERIORATING,
        ),
    ]
    pool = InMemoryCompanyPool(
        {
            "example-cycle-industry": [
                CompanyCandidate("demo-001", "示例公司 A", "example-cycle-industry", source="demo"),
                CompanyCandidate("demo-002", "示例公司 B", "example-cycle-industry", source="demo"),
                CompanyCandidate("demo-003", "示例公司 C", "example-cycle-industry", source="demo"),
            ]
        }
    )
    scan = IndustryFirstDiscovery(
        InMemoryRadar(snapshots),
        pool,
        PassThroughCompanyData(),
        PassThroughDeepResearch(),
    ).run(as_of)
    return scan.to_dict()


def _light_profile_status_counts(scan) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidates in scan.company_pools.values():
        for candidate in candidates:
            status = str(candidate.light_profile.get("status", "NOT_REQUESTED"))
            counts[status] = counts.get(status, 0) + 1
    return counts


def _candidate_kwargs(item: dict) -> dict:
    if not isinstance(item, dict):
        raise TypeError("each candidate must be an object")
    return {
        "company_id": str(item.get("company_id") or ""),
        "display_name": str(item.get("display_name") or ""),
        "industry_id": str(item.get("industry_id") or ""),
        "data_tier": CompanyDataTier(item.get("data_tier", CompanyDataTier.LIGHT.value)),
        "source": str(item.get("source") or ""),
        "inclusion_reason": str(item.get("inclusion_reason") or ""),
        "hard_gate_status": str(item.get("hard_gate_status") or "PENDING"),
        "score": item.get("score"),
        "notes": tuple(item.get("notes") or ()),
        "metadata": dict(item.get("metadata") or {}),
        "light_profile": dict(item.get("light_profile") or {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="industry-first-research")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("demo", help="run the local-only industry-first demo")
    web = subparsers.add_parser(
        "web", help="start the local-only research web console"
    )
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--data-root", default="data", dest="data_root")
    web.add_argument(
        "--commodity-directory",
        default="config/commodities",
        dest="commodity_directory",
    )
    web.add_argument("--web-root", default="web", dest="web_root")
    company = subparsers.add_parser(
        "company", help="collect a bounded company research snapshot"
    )
    company.add_argument("--config", required=True, help="path to a company JSON config")
    company.add_argument(
        "--snapshot-dir",
        default="artifacts/company-snapshots",
        help="directory for the JSON company snapshot",
    )
    radar_config = subparsers.add_parser(
        "industry-radar", help="collect configured industry signals only"
    )
    radar_config.add_argument("--config", required=True, help="path to an industry JSON config")
    radar_config.add_argument("--as-of", help="override the configuration data date")
    radar_config.add_argument(
        "--snapshot-dir",
        default="artifacts/radar-snapshots",
        help="directory for the JSON radar snapshot",
    )
    industry_config = subparsers.add_parser(
        "industry", help="run an industry-first scan from a local industry config"
    )
    industry_config.add_argument("--config", required=True, help="path to an industry JSON config")
    industry_config.add_argument("--output", help="write the Markdown report to this path")
    industry_config.add_argument("--html-output", help="write the HTML report to this path")
    industry_config.add_argument(
        "--snapshot-dir",
        default="artifacts/snapshots",
        help="directory for the JSON scan snapshot",
    )
    radar = subparsers.add_parser("radar", help="fetch a read-only industry radar snapshot")
    radar.add_argument(
        "--source", choices=("cross", "eastmoney", "tonghuashun"), default="cross"
    )
    radar.add_argument("--limit", type=int, default=50)
    radar.add_argument("--as-of", default=None, dest="as_of")
    radar.add_argument("--output-dir", default="data/radar", dest="output_dir")
    radar.add_argument(
        "--alias-file",
        default="docs/industry_aliases.v1.json",
        dest="alias_file",
        help="versioned explicit cross-source industry alias registry",
    )
    trend = subparsers.add_parser("trend", help="summarise repeated saved radar snapshots")
    trend.add_argument("--source", choices=("cross", "eastmoney", "tonghuashun"), default="cross")
    trend.add_argument("--input-dir", default="data/radar", dest="input_dir")
    trend.add_argument("--output-dir", default="data/radar", dest="output_dir")
    trend.add_argument("--window", type=int, default=10)
    trend.add_argument("--min-observations", type=int, default=3, dest="min_observations")
    trend.add_argument("--min-direction-ratio", type=float, default=2 / 3, dest="min_direction_ratio")
    trend.add_argument("--as-of", default=None, dest="as_of")
    pool = subparsers.add_parser("company-pool", help="load a bounded company pool for one industry")
    pool.add_argument("--industry-id", required=True, dest="industry_id")
    pool.add_argument("--industry-name", required=True, dest="industry_name")
    pool.add_argument("--as-of", default=None, dest="as_of")
    pool.add_argument("--limit", type=int, default=30)
    pool.add_argument("--output-dir", default="data/company_pools", dest="output_dir")
    pool.add_argument(
        "--with-light-data",
        action="store_true",
        help="enrich the bounded pool with public LIGHT company facts",
    )
    screen = subparsers.add_parser(
        "screen", help="screen saved company-pool LIGHT profiles for data completeness"
    )
    screen.add_argument("--input", required=True, dest="input_path")
    screen.add_argument("--output-dir", default="data/company_screens", dest="output_dir")
    screen.add_argument("--expected-industry", default="", dest="expected_industry")
    screen.add_argument(
        "--alias-file",
        default="docs/industry_aliases.v1.json",
        dest="alias_file",
        help="versioned explicit industry alias registry",
    )
    screen.add_argument(
        "--expected-industry-source",
        default="tonghuashun",
        dest="expected_industry_source",
    )
    screen.add_argument(
        "--reported-industry-source",
        default="tonghuashun_company_profile",
        dest="reported_industry_source",
    )
    queue = subparsers.add_parser(
        "queue", help="build a conservative review queue from a company LIGHT screen"
    )
    queue.add_argument("--input", required=True, dest="input_path")
    queue.add_argument("--output-dir", default="data/candidate_queues", dest="output_dir")
    queue.add_argument("--as-of", default="", dest="as_of")
    queue.add_argument("--source", default="", dest="source")
    queue.add_argument("--snapshot-id", default="", dest="snapshot_id")
    supplemental = subparsers.add_parser(
        "supplemental",
        help="assemble traceable supplemental evidence for a candidate queue",
    )
    supplemental.add_argument("--input", required=True, dest="input_path")
    supplemental.add_argument("--evidence", required=True, dest="evidence_path")
    supplemental.add_argument(
        "--output-dir", default="data/company_supplemental", dest="output_dir"
    )
    supplemental.add_argument(
        "--required-field", action="append", default=None, dest="required_fields"
    )
    supplemental.add_argument("--snapshot-id", default="", dest="snapshot_id")
    product_profile = subparsers.add_parser(
        "product-profile",
        help="build an evidence-only product and profit-source profile",
    )
    product_profile.add_argument("--input", required=True, dest="input_path")
    product_profile.add_argument("--company-scopes", default="", dest="company_scopes_path")
    product_profile.add_argument(
        "--required-field", action="append", default=None, dest="required_fields"
    )
    product_profile.add_argument(
        "--output-dir", default="data/company_product_profiles", dest="output_dir"
    )
    product_profile.add_argument("--snapshot-id", default="", dest="snapshot_id")
    product_profit_bridge = subparsers.add_parser(
        "product-profit-bridge",
        help="build deterministic product revenue, profit, and cash-flow bridge scenarios",
    )
    product_profit_bridge.add_argument("--input", required=True, dest="input_path")
    product_profit_bridge.add_argument(
        "--company-scopes", default="", dest="company_scopes_path"
    )
    product_profit_bridge.add_argument(
        "--output-dir", default="data/product_profit_bridges", dest="output_dir"
    )
    product_profit_bridge.add_argument("--bridge-id", default="", dest="bridge_id")
    product_profit_bridge.add_argument(
        "--rule-version", default="product-profit-bridge-rules.v1", dest="rule_version"
    )
    product_profit_bridge_validate = subparsers.add_parser(
        "product-profit-bridge-validate",
        help="validate one immutable product profit bridge report",
    )
    product_profit_bridge_validate.add_argument("--input", required=True, dest="input_path")
    product_lifecycle = subparsers.add_parser(
        "product-lifecycle",
        help="build an evidence-only product lifecycle and market-state snapshot",
    )
    product_lifecycle.add_argument("--input", required=True, dest="input_path")
    product_lifecycle.add_argument(
        "--company-scopes", default="", dest="company_scopes_path"
    )
    product_lifecycle.add_argument(
        "--output-dir", default="data/product_lifecycles", dest="output_dir"
    )
    product_lifecycle.add_argument("--snapshot-id", default="", dest="snapshot_id")
    product_lifecycle.add_argument(
        "--rule-version", default="product-lifecycle-rules.v1", dest="rule_version"
    )
    product_lifecycle_validate = subparsers.add_parser(
        "product-lifecycle-validate",
        help="validate one immutable product lifecycle snapshot",
    )
    product_lifecycle_validate.add_argument("--input", required=True, dest="input_path")
    financial_model = subparsers.add_parser(
        "financial-model",
        help="build deterministic financial, cash-flow, stress, and scenario observations",
    )
    financial_model.add_argument("--input", required=True, dest="input_path")
    financial_model.add_argument(
        "--company-scopes", default="", dest="company_scopes_path"
    )
    financial_model.add_argument(
        "--output-dir", default="data/financial_models", dest="output_dir"
    )
    financial_model.add_argument("--model-id", default="", dest="model_id")
    financial_model.add_argument(
        "--rule-version", default="financial-model-rules.v1", dest="rule_version"
    )
    financial_model_validate = subparsers.add_parser(
        "financial-model-validate",
        help="validate one immutable financial model report",
    )
    financial_model_validate.add_argument("--input", required=True, dest="input_path")
    application_mapping = subparsers.add_parser(
        "application-mapping",
        help="build an evidence-only product-to-application mapping",
    )
    application_mapping.add_argument("--input", required=True, dest="input_path")
    application_mapping.add_argument(
        "--required-field", action="append", default=None, dest="required_fields"
    )
    application_mapping.add_argument(
        "--output-dir", default="data/company_application_mappings", dest="output_dir"
    )
    application_mapping.add_argument("--snapshot-id", default="", dest="snapshot_id")
    demand_transmission = subparsers.add_parser(
        "demand-transmission",
        help="build an evidence-only demand transmission gate",
    )
    demand_transmission.add_argument("--input", required=True, dest="input_path")
    demand_transmission.add_argument(
        "--required-field", action="append", default=None, dest="required_fields"
    )
    demand_transmission.add_argument(
        "--output-dir", default="data/company_demand_transmission", dest="output_dir"
    )
    demand_transmission.add_argument("--snapshot-id", default="", dest="snapshot_id")
    industry_situation = subparsers.add_parser(
        "industry-situation",
        help="build an evidence-only industry situation report",
    )
    industry_situation.add_argument("--input", required=True, dest="input_path")
    industry_situation.add_argument(
        "--required-field", action="append", default=None, dest="required_fields"
    )
    industry_situation.add_argument(
        "--output-dir", default="data/company_industry_situations", dest="output_dir"
    )
    industry_situation.add_argument("--snapshot-id", default="", dest="snapshot_id")
    cycle_reversal = subparsers.add_parser(
        "cycle-reversal",
        help="build an evidence-only industry cycle reversal report",
    )
    cycle_reversal.add_argument("--input", required=True, dest="input_path")
    cycle_reversal.add_argument(
        "--required-field", action="append", default=None, dest="required_fields"
    )
    cycle_reversal.add_argument(
        "--output-dir", default="data/company_cycle_reversals", dest="output_dir"
    )
    cycle_reversal.add_argument("--snapshot-id", default="", dest="snapshot_id")
    competitive_position = subparsers.add_parser(
        "competitive-position",
        help="build an evidence-only company competitive position report",
    )
    competitive_position.add_argument("--input", required=True, dest="input_path")
    competitive_position.add_argument(
        "--required-field", action="append", default=None, dest="required_fields"
    )
    competitive_position.add_argument(
        "--output-dir", default="data/company_competitive_positions", dest="output_dir"
    )
    competitive_position.add_argument("--snapshot-id", default="", dest="snapshot_id")
    survival_analysis = subparsers.add_parser(
        "survival-analysis",
        help="build an evidence-only survival and stress-test report",
    )
    survival_analysis.add_argument("--input", required=True, dest="input_path")
    survival_analysis.add_argument(
        "--required-field", action="append", default=None, dest="required_fields"
    )
    survival_analysis.add_argument(
        "--output-dir", default="data/company_survival_analysis", dest="output_dir"
    )
    survival_analysis.add_argument("--snapshot-id", default="", dest="snapshot_id")
    valuation_scenarios = subparsers.add_parser(
        "valuation-scenarios",
        help="build an evidence-only valuation and scenario framework",
    )
    valuation_scenarios.add_argument("--input", required=True, dest="input_path")
    valuation_scenarios.add_argument(
        "--required-field", action="append", default=None, dest="required_fields"
    )
    valuation_scenarios.add_argument(
        "--output-dir", default="data/company_valuation_scenarios", dest="output_dir"
    )
    valuation_scenarios.add_argument("--snapshot-id", default="", dest="snapshot_id")
    market_structure = subparsers.add_parser(
        "market-structure",
        help="build a read-only market structure snapshot from OHLCV input",
    )
    market_structure.add_argument("--input", required=True, dest="input_path")
    market_structure.add_argument("--market-data", default="", dest="market_data_path")
    market_structure.add_argument(
        "--output-dir", default="data/market_structure", dest="output_dir"
    )
    market_structure.add_argument("--snapshot-id", default="", dest="snapshot_id")
    market_structure_compare = subparsers.add_parser(
        "market-structure-compare",
        help="compare local, czsc, and chan.py structure results without trading signals",
    )
    market_structure_compare.add_argument("--input", required=True, dest="input_path")
    market_structure_compare.add_argument("--market-data", default="", dest="market_data_path")
    market_structure_compare.add_argument(
        "--output-dir", default="data/market_structure_comparisons", dest="output_dir"
    )
    market_structure_compare.add_argument(
        "--comparison-id", default="", dest="comparison_id"
    )
    adversarial_review = subparsers.add_parser(
        "adversarial-review",
        help="audit a valuation package for evidence and boundary violations",
    )
    adversarial_review.add_argument("--input", required=True, dest="input_path")
    adversarial_review.add_argument(
        "--market-structure", default="", dest="market_structure_path"
    )
    adversarial_review.add_argument(
        "--output-dir", default="data/company_adversarial_reviews", dest="output_dir"
    )
    adversarial_review.add_argument("--snapshot-id", default="", dest="snapshot_id")
    research_report = subparsers.add_parser(
        "research-report",
        help="assemble a structured evidence-bound company research report",
    )
    research_report.add_argument("--input", required=True, dest="input_path")
    research_report.add_argument(
        "--output-dir", default="data/company_research_reports", dest="output_dir"
    )
    research_report.add_argument("--snapshot-id", default="", dest="snapshot_id")
    render_report = subparsers.add_parser(
        "render-report",
        help="render an immutable company/futures report as Markdown and/or HTML",
    )
    render_report.add_argument("--input", required=True, dest="input_path")
    render_report.add_argument(
        "--format",
        action="append",
        choices=("markdown", "html"),
        dest="formats",
        help="repeat to select formats; defaults to both",
    )
    render_report.add_argument("--title", default="", dest="title")
    render_report.add_argument("--basename", default="", dest="basename")
    render_report.add_argument(
        "--output-dir", default="data/rendered_reports", dest="output_dir"
    )
    public_draft = subparsers.add_parser(
        "public-draft",
        help="create a redacted public draft from an explicitly locked research report",
    )
    public_draft.add_argument("--input", required=True, dest="input_path")
    public_draft.add_argument("--source-lock", required=True, dest="source_lock_path")
    public_draft.add_argument("--channel", default="wechat_public_draft", dest="channel")
    public_draft.add_argument("--title", default="", dest="title")
    public_draft.add_argument("--draft-version", type=int, default=1, dest="draft_version")
    public_draft.add_argument("--draft-id", default="", dest="draft_id")
    public_draft.add_argument(
        "--output-dir", default="data/public_drafts", dest="output_dir"
    )
    public_draft_validate = subparsers.add_parser(
        "validate-public-draft",
        help="validate a generated public draft without publishing it",
    )
    public_draft_validate.add_argument("--input", required=True, dest="input_path")
    research_pipeline = subparsers.add_parser(
        "research-pipeline",
        help="run the bounded company deep-research stages as one pipeline",
    )
    research_pipeline.add_argument("--input", required=True, dest="input_path")
    research_pipeline.add_argument(
        "--market-structure", default="", dest="market_structure_path"
    )
    research_pipeline.add_argument(
        "--output-dir", default="data/company_research_pipelines", dest="output_dir"
    )
    research_pipeline.add_argument("--snapshot-id", default="", dest="snapshot_id")
    research_pipeline.add_argument(
        "--evidence-bundle", default="", dest="evidence_bundle_path"
    )
    research_pipeline.add_argument(
        "--company-scopes", default="", dest="company_scopes_path"
    )
    research_pipeline.add_argument(
        "--product-profit-bridge", default="", dest="product_profit_bridge_path"
    )
    research_pipeline.add_argument(
        "--product-lifecycle", default="", dest="product_lifecycle_path"
    )
    research_pipeline.add_argument(
        "--financial-model", default="", dest="financial_model_path"
    )
    research_pipeline.add_argument(
        "--version-output-dir", default="data/research_versions", dest="version_output_dir"
    )
    incremental_update = subparsers.add_parser(
        "incremental-update",
        help="compare new evidence with a prior pipeline and create a new version",
    )
    incremental_update.add_argument(
        "--previous-pipeline", required=True, dest="previous_pipeline_path"
    )
    incremental_update.add_argument(
        "--previous-supplemental", required=True, dest="previous_supplemental_path"
    )
    incremental_update.add_argument(
        "--evidence", required=True, dest="evidence_path"
    )
    incremental_update.add_argument("--as-of", default="", dest="as_of")
    incremental_update.add_argument(
        "--execution-mode",
        choices=("LOCAL_ONLY", "LLM_ASSISTED", "MANUAL_WEB_AI"),
        default="LOCAL_ONLY",
        dest="execution_mode",
    )
    incremental_update.add_argument("--company-scopes", default="", dest="company_scopes_path")
    incremental_update.add_argument("--market-structure", default="", dest="market_structure_path")
    incremental_update.add_argument("--evidence-bundle", default="", dest="evidence_bundle_path")
    incremental_update.add_argument(
        "--output-dir", default="data/company_incremental_updates", dest="output_dir"
    )
    incremental_update.add_argument(
        "--version-output-dir", default="data/research_versions", dest="version_output_dir"
    )
    incremental_update.add_argument("--snapshot-id", default="", dest="snapshot_id")
    schedule_init = subparsers.add_parser(
        "schedule-init",
        help="create the bounded local research schedule and state",
    )
    schedule_init.add_argument("--schedule-id", default="default", dest="schedule_id")
    schedule_init.add_argument("--as-of", default="", dest="as_of")
    schedule_init.add_argument(
        "--output-dir", default="data/scheduler", dest="output_dir"
    )
    schedule_plan = subparsers.add_parser(
        "schedule-plan",
        help="plan due local refresh tasks and event-triggered scans",
    )
    schedule_plan.add_argument("--schedule", required=True, dest="schedule_path")
    schedule_plan.add_argument("--state", required=True, dest="state_path")
    schedule_plan.add_argument("--events", default="", dest="events_path")
    schedule_plan.add_argument("--now", default="", dest="now")
    schedule_plan.add_argument(
        "--output-dir", default="data/scheduler", dest="output_dir"
    )
    schedule_run = subparsers.add_parser(
        "schedule-run",
        help="execute a planned local refresh through bounded read-only adapters",
    )
    schedule_run.add_argument("--state", required=True, dest="state_path")
    schedule_run.add_argument("--plan", required=True, dest="plan_path")
    schedule_run.add_argument("--now", default="", dest="now")
    schedule_run.add_argument("--output-root", default="data", dest="output_root")
    schedule_run.add_argument(
        "--alias-file",
        default="docs/industry_aliases.v1.json",
        dest="alias_file",
    )
    freshness = subparsers.add_parser(
        "freshness",
        help="classify supplemental evidence freshness without changing conclusions",
    )
    freshness.add_argument("--input", required=True, dest="input_path")
    freshness.add_argument("--as-of", default="", dest="as_of")
    freshness.add_argument(
        "--output-dir", default="data/research_freshness", dest="output_dir"
    )
    version_compare = subparsers.add_parser(
        "compare-versions",
        help="compare two research versions and preserve conclusion boundaries",
    )
    version_compare.add_argument("--previous-pipeline", required=True, dest="previous_pipeline_path")
    version_compare.add_argument("--current-pipeline", required=True, dest="current_pipeline_path")
    version_compare.add_argument("--previous-supplemental", default="", dest="previous_supplemental_path")
    version_compare.add_argument("--current-supplemental", default="", dest="current_supplemental_path")
    version_compare.add_argument(
        "--output-dir", default="data/research_version_comparisons", dest="output_dir"
    )
    thesis_check = subparsers.add_parser(
        "thesis-check",
        help="check a holding thesis against current evidence without committing a new thesis",
    )
    thesis_check.add_argument("--thesis", required=True, dest="thesis_path")
    thesis_check.add_argument("--supplemental", required=True, dest="supplemental_path")
    thesis_check.add_argument("--previous-supplemental", default="", dest="previous_supplemental_path")
    thesis_check.add_argument("--as-of", default="", dest="as_of")
    thesis_check.add_argument(
        "--output-dir", default="data/holding_thesis_checks", dest="output_dir"
    )
    thesis_lock = subparsers.add_parser(
        "thesis-lock",
        help="draft or user-confirm and lock a holding-thesis version",
    )
    thesis_lock.add_argument("--input", required=True, dest="input_path")
    thesis_lock.add_argument("--user-confirmed", action="store_true", dest="user_confirmed")
    thesis_lock.add_argument("--previous-thesis", default="", dest="previous_thesis_path")
    thesis_lock.add_argument("--snapshot-id", default="", dest="snapshot_id")
    thesis_lock.add_argument(
        "--output-dir", default="data/holding_theses", dest="output_dir"
    )
    decision_snapshot = subparsers.add_parser(
        "decision-snapshot",
        help="create an immutable user-confirmed simulation decision snapshot",
    )
    decision_snapshot.add_argument("--input", required=True, dest="input_path")
    decision_snapshot.add_argument("--decision", required=True, dest="decision_path")
    decision_snapshot.add_argument(
        "--user-confirmed", action="store_true", dest="user_confirmed"
    )
    decision_snapshot.add_argument(
        "--output-dir", default="data/decision_snapshots", dest="output_dir"
    )
    decision_snapshot.add_argument("--snapshot-id", default="", dest="snapshot_id")
    decision_snapshot.add_argument(
        "--evidence-bundle", default="", dest="evidence_bundle_path"
    )
    decision_snapshot.add_argument(
        "--execution-plan", default="", dest="execution_plan_path"
    )
    decision_snapshot.add_argument(
        "--company-scope", default="", dest="company_scope_path"
    )
    decision_snapshot.add_argument(
        "--market-data", action="append", default=None, dest="market_data_paths"
    )
    attribution = subparsers.add_parser(
        "attribution",
        help="compare a locked simulation snapshot with its fixed benchmark",
    )
    attribution.add_argument("--input", required=True, dest="input_path")
    attribution.add_argument("--outcome", required=True, dest="outcome_path")
    attribution.add_argument("--asset-market-data", default="", dest="asset_market_data_path")
    attribution.add_argument("--benchmark-market-data", default="", dest="benchmark_market_data_path")
    attribution.add_argument("--closed-at", default="", dest="closed_at")
    attribution.add_argument(
        "--output-dir", default="data/attribution_results", dest="output_dir"
    )
    attribution.add_argument("--attribution-id", default="", dest="attribution_id")
    quality_scorecard = subparsers.add_parser(
        "quality-scorecard",
        help="review research quality dimensions without collapsing them into a total score",
    )
    quality_scorecard.add_argument("--input", required=True, dest="input_path")
    quality_scorecard.add_argument(
        "--research-report", default="", dest="research_report_path"
    )
    quality_scorecard.add_argument(
        "--attribution", default="", dest="attribution_path"
    )
    quality_scorecard.add_argument(
        "--thesis-check", default="", dest="thesis_check_path"
    )
    quality_scorecard.add_argument(
        "--freshness", default="", dest="freshness_path"
    )
    quality_scorecard.add_argument(
        "--assessments", default="", dest="assessments_path"
    )
    quality_scorecard.add_argument(
        "--opportunity-scan", default="", dest="opportunity_scan_path"
    )
    quality_scorecard.add_argument(
        "--output-dir", default="data/quality_scorecards", dest="output_dir"
    )
    quality_scorecard.add_argument("--scorecard-id", default="", dest="scorecard_id")
    portfolio_create = subparsers.add_parser(
        "portfolio-create",
        help="create an immutable full-cash company simulation portfolio",
    )
    portfolio_create.add_argument("--input", required=True, dest="input_path")
    portfolio_create.add_argument(
        "--decision", action="append", required=True, dest="decision_paths"
    )
    portfolio_create.add_argument(
        "--output-dir", default="data/simulation_portfolios", dest="output_dir"
    )
    portfolio_create.add_argument("--portfolio-id", default="", dest="portfolio_id")
    portfolio_replay = subparsers.add_parser(
        "portfolio-replay",
        help="replay a company simulation portfolio against dated price and benchmark data",
    )
    portfolio_replay.add_argument("--input", required=True, dest="input_path")
    portfolio_replay.add_argument("--outcome", required=True, dest="outcome_path")
    portfolio_replay.add_argument("--asset-market-data-dir", default="", dest="asset_market_data_dir")
    portfolio_replay.add_argument("--benchmark-market-data", default="", dest="benchmark_market_data_path")
    portfolio_replay.add_argument("--closed-at", default="", dest="closed_at")
    portfolio_replay.add_argument(
        "--output-dir", default="data/simulation_portfolio_replays", dest="output_dir"
    )
    portfolio_replay.add_argument("--replay-id", default="", dest="replay_id")
    futures_simulation_create = subparsers.add_parser(
        "futures-simulation-create",
        help="create an immutable specific-contract futures settlement simulation",
    )
    futures_simulation_create.add_argument("--input", required=True, dest="input_path")
    futures_simulation_create.add_argument(
        "--decision", action="append", required=True, dest="decision_paths"
    )
    futures_simulation_create.add_argument(
        "--output-dir", default="data/futures_simulations", dest="output_dir"
    )
    futures_simulation_create.add_argument("--simulation-id", default="", dest="simulation_id")
    futures_simulation_replay = subparsers.add_parser(
        "futures-simulation-replay",
        help="replay a futures simulation with daily settlement, margin and rule rows",
    )
    futures_simulation_replay.add_argument("--input", required=True, dest="input_path")
    futures_simulation_replay.add_argument("--outcome", required=True, dest="outcome_path")
    futures_simulation_replay.add_argument("--closed-at", default="", dest="closed_at")
    futures_simulation_replay.add_argument(
        "--output-dir", default="data/futures_simulation_replays", dest="output_dir"
    )
    futures_simulation_replay.add_argument("--replay-id", default="", dest="replay_id")
    opportunity_candidate = subparsers.add_parser(
        "opportunity-candidate",
        help="evaluate one industry-first opportunity candidate without a total score",
    )
    opportunity_candidate.add_argument("--input", required=True, dest="input_path")
    opportunity_candidate.add_argument(
        "--output-dir", default="data/opportunity_candidates", dest="output_dir"
    )
    opportunity_candidate.add_argument("--candidate-id", default="", dest="candidate_id")
    opportunity_scan = subparsers.add_parser(
        "opportunity-scan",
        help="evaluate a bounded opportunity candidate scan and retain an empty result",
    )
    opportunity_scan.add_argument("--input", required=True, dest="input_path")
    opportunity_scan.add_argument(
        "--output-dir", default="data/opportunity_scans", dest="output_dir"
    )
    announcement_asset = subparsers.add_parser(
        "announcement-asset",
        help="store an immutable original announcement manifest and raw-content hash",
    )
    announcement_asset.add_argument("--input", required=True, dest="input_path")
    announcement_asset.add_argument("--raw-content", default="", dest="raw_content_path")
    announcement_asset.add_argument(
        "--output-dir", default="data/announcement_assets", dest="output_dir"
    )
    announcement_asset.add_argument("--asset-id", default="", dest="asset_id")
    announcement_impact = subparsers.add_parser(
        "announcement-impact",
        help="create a review-only module-impact record from an announcement asset",
    )
    announcement_impact.add_argument("--input", required=True, dest="input_path")
    announcement_impact.add_argument("--research-cutoff", default="", dest="research_cutoff")
    announcement_impact.add_argument(
        "--output-dir", default="data/announcement_impacts", dest="output_dir"
    )
    announcement_impact.add_argument("--impact-id", default="", dest="impact_id")
    announcement_templates = subparsers.add_parser(
        "announcement-templates",
        help="validate and normalize versioned local announcement templates",
    )
    announcement_templates.add_argument(
        "--config",
        default="config/announcement_templates.v1.json",
        dest="config_path",
    )
    announcement_templates.add_argument(
        "--output-dir", default="data/announcement_templates", dest="output_dir"
    )
    announcement_parse = subparsers.add_parser(
        "announcement-parse",
        help="parse a user-provided JSON, HTML, or text disclosure snapshot locally",
    )
    announcement_parse.add_argument("--input", required=True, dest="input_path")
    announcement_parse.add_argument("--template", required=True, dest="template_id")
    announcement_parse.add_argument(
        "--config",
        default="config/announcement_templates.v1.json",
        dest="config_path",
    )
    announcement_parse.add_argument("--metadata", default="", dest="metadata_path")
    announcement_parse.add_argument("--source-url", default="", dest="source_url")
    announcement_parse.add_argument("--captured-at", default="", dest="captured_at")
    announcement_parse.add_argument("--research-as-of", default="", dest="research_as_of")
    announcement_parse.add_argument("--as-of", default="", dest="as_of")
    announcement_parse.add_argument("--subject-type", default="", dest="subject_type")
    announcement_parse.add_argument("--subject-id", default="", dest="subject_id")
    announcement_parse.add_argument("--issuer", default="", dest="issuer")
    announcement_parse.add_argument("--document-id", default="", dest="document_id")
    announcement_parse.add_argument("--output-dir", default="data/announcement_inputs", dest="output_dir")
    research_impact = subparsers.add_parser(
        "research-impact-queue",
        help="map an event or announcement impact to saved research versions",
    )
    research_impact.add_argument("--event", required=True, dest="event_path")
    research_impact.add_argument(
        "--version", action="append", default=None, dest="version_paths",
        help="research-version manifest path; may be repeated",
    )
    research_impact.add_argument(
        "--versions-dir", default="data/research_versions", dest="versions_dir",
    )
    research_impact.add_argument("--queue-id", default="", dest="queue_id")
    research_impact.add_argument(
        "--output-dir", default="data/research_impact_queues", dest="output_dir"
    )
    research_impact_validate = subparsers.add_parser(
        "validate-research-impact-queue",
        help="validate an immutable research-impact queue",
    )
    research_impact_validate.add_argument("--input", required=True, dest="input_path")
    futures_identify = subparsers.add_parser(
        "futures-identify",
        help="identify a domestic futures variety, contract, continuous series, or spot benchmark",
    )
    futures_identify.add_argument("--input", required=True, dest="input_path")
    futures_identify.add_argument("--market-registry", default="", dest="market_registry_path")
    futures_identify.add_argument(
        "--output-dir", default="data/futures_identities", dest="output_dir"
    )
    futures_identify.add_argument("--identity-id", default="", dest="identity_id")
    futures_fundamentals = subparsers.add_parser(
        "futures-fundamentals",
        help="build an evidence-bound domestic futures fundamentals and contract report",
    )
    futures_fundamentals.add_argument("--identity", required=True, dest="identity_path")
    futures_fundamentals.add_argument("--input", required=True, dest="input_path")
    futures_fundamentals.add_argument(
        "--market-structure", default="", dest="market_structure_path"
    )
    futures_fundamentals.add_argument(
        "--output-dir", default="data/futures_fundamentals", dest="output_dir"
    )
    futures_fundamentals.add_argument(
        "--snapshot-id", default="", dest="snapshot_id"
    )
    futures_input_from_refresh = subparsers.add_parser(
        "futures-input-from-refresh",
        help="map an explicit data refresh into a review-only futures fundamentals input",
    )
    futures_input_from_refresh.add_argument(
        "--refresh", required=True, dest="refresh_path"
    )
    futures_input_from_refresh.add_argument(
        "--mapping", required=True, dest="mapping_path"
    )
    futures_input_from_refresh.add_argument(
        "--input-id", default="", dest="input_id"
    )
    futures_input_from_refresh.add_argument(
        "--output-dir", default="data/futures_inputs", dest="output_dir"
    )
    futures_tracking = subparsers.add_parser(
        "futures-tracking",
        help="compare two saved futures fundamentals reports without changing either report",
    )
    futures_tracking.add_argument("--current", required=True, dest="current_path")
    futures_tracking.add_argument("--previous", default="", dest="previous_path")
    futures_tracking.add_argument("--as-of", default="", dest="as_of")
    futures_tracking.add_argument("--tracking-id", default="", dest="tracking_id")
    futures_tracking.add_argument(
        "--output-dir", default="data/futures_tracking", dest="output_dir"
    )
    futures_company_exposure = subparsers.add_parser(
        "futures-company-exposure",
        help="map a futures variety to explicit listed-company product exposures",
    )
    futures_company_exposure.add_argument(
        "--futures-report", required=True, dest="futures_report_path"
    )
    futures_company_exposure.add_argument("--input", required=True, dest="input_path")
    futures_company_exposure.add_argument(
        "--product-profile", default="", dest="product_profile_path"
    )
    futures_company_exposure.add_argument(
        "--output-dir", default="data/futures_company_exposures", dest="output_dir"
    )
    futures_company_exposure.add_argument(
        "--snapshot-id", default="", dest="snapshot_id"
    )
    commodity_adapters = subparsers.add_parser(
        "commodity-adapters",
        help="list and validate the configuration-driven commodity adapter registry",
    )
    commodity_adapters.add_argument(
        "--directory", default="config/commodities", dest="directory"
    )
    commodity_adapters.add_argument(
        "--output-dir", default="data/commodity_adapters", dest="output_dir"
    )
    commodity_adapters.add_argument(
        "--registry-id", default="default", dest="registry_id"
    )
    commodity_adapter_validate = subparsers.add_parser(
        "commodity-adapter-validate",
        help="validate one commodity adapter against futures fundamentals evidence",
    )
    commodity_adapter_validate.add_argument(
        "--directory", default="config/commodities", dest="directory"
    )
    commodity_adapter_validate.add_argument("--adapter", required=True)
    commodity_adapter_validate.add_argument(
        "--futures-report", default="", dest="futures_report_path"
    )
    commodity_adapter_validate.add_argument(
        "--fundamentals", default="", dest="fundamentals_path"
    )
    commodity_adapter_validate.add_argument(
        "--output-dir", default="data/commodity_adapter_validations", dest="output_dir"
    )
    commodity_adapter_validate.add_argument(
        "--validation-id", default="", dest="validation_id"
    )
    research_assets = subparsers.add_parser(
        "research-assets",
        help="discover or safely import existing luopan/ai-berkshire research assets",
    )
    research_assets.add_argument(
        "--mode",
        choices=("discover", "profile", "artifact", "candidate-set", "scorecard", "validate-identity"),
        default="discover",
    )
    research_assets.add_argument("--root", default=".", help="repository root or vendor directory")
    research_assets.add_argument("--identifier", default="")
    research_assets.add_argument("--as-of", default=None, dest="as_of")
    research_assets.add_argument("--input", default="", dest="input_path")
    research_assets.add_argument("--authoritative", default="", dest="authoritative_path")
    research_assets.add_argument("--limit", type=int, default=500)
    research_assets.add_argument(
        "--output-dir", default="data/research_assets", dest="output_dir"
    )
    research_assets.add_argument("--snapshot-id", default="", dest="snapshot_id")
    security_master = subparsers.add_parser(
        "security-master",
        help="build a lightweight security master and effective-dated industry memberships",
    )
    security_master.add_argument("--input", required=True, dest="input_path")
    security_master.add_argument("--previous", default="", dest="previous_path")
    security_master.add_argument(
        "--output-dir", default="data/security_master", dest="output_dir"
    )
    security_master.add_argument("--snapshot-id", default="", dest="snapshot_id")
    security_master_validate = subparsers.add_parser(
        "security-master-validate",
        help="validate a lightweight security master snapshot",
    )
    security_master_validate.add_argument("--input", required=True, dest="input_path")
    security_master_validate.add_argument(
        "--output-dir", default="data/security_master_validations", dest="output_dir"
    )
    company_scope = subparsers.add_parser(
        "company-scope",
        help="build an immutable company boundary and researchability report",
    )
    company_scope.add_argument("--input", required=True, dest="input_path")
    company_scope.add_argument("--output-dir", default="data/company_scopes", dest="output_dir")
    company_scope.add_argument("--scope-id", default="", dest="scope_id")
    company_scope_validate = subparsers.add_parser(
        "company-scope-validate", help="validate a saved company boundary report"
    )
    company_scope_validate.add_argument("--input", required=True, dest="input_path")
    company_scope_validate.add_argument(
        "--output-dir", default="data/company_scope_validations", dest="output_dir"
    )
    market_data = subparsers.add_parser(
        "market-data", help="build an immutable source-aware market-data snapshot"
    )
    market_data.add_argument("--input", required=True, dest="input_path")
    market_data.add_argument("--market-registry", default="", dest="market_registry_path")
    market_data.add_argument("--output-dir", default="data/market_data", dest="output_dir")
    market_data.add_argument("--snapshot-id", default="", dest="snapshot_id")
    market_data_validate = subparsers.add_parser(
        "market-data-validate", help="validate a saved market-data snapshot"
    )
    market_data_validate.add_argument("--input", required=True, dest="input_path")
    market_data_validate.add_argument(
        "--output-dir", default="data/market_data_validations", dest="output_dir"
    )
    market_data_validate.add_argument(
        "--market-registry", default="", dest="market_registry_path"
    )
    market_registry = subparsers.add_parser(
        "market-registry", help="build a versioned market and calendar registry"
    )
    market_registry.add_argument("--input", required=True, dest="input_path")
    market_registry.add_argument("--output-dir", default="data/market_registries", dest="output_dir")
    market_registry_validate = subparsers.add_parser(
        "market-reference-validate", help="validate a market reference against a registry"
    )
    market_registry_validate.add_argument("--input", required=True, dest="input_path")
    market_registry_validate.add_argument("--registry", required=True, dest="registry_path")
    market_registry_validate.add_argument("--output-dir", default="data/market_registry_validations", dest="output_dir")
    industry_adapters = subparsers.add_parser(
        "industry-adapters",
        help="list the configuration-driven industry adapter registry",
    )
    industry_adapters.add_argument(
        "--directory", default="config/industries/adapters", dest="directory"
    )
    industry_adapters.add_argument(
        "--output-dir", default="data/industry_adapters", dest="output_dir"
    )
    industry_adapters.add_argument("--registry-id", default="default", dest="registry_id")
    industry_profile = subparsers.add_parser(
        "industry-profile",
        help="classify an industry profile and emit its adapter research contract",
    )
    industry_profile.add_argument("--input", required=True, dest="input_path")
    industry_profile.add_argument(
        "--directory", default="config/industries/adapters", dest="directory"
    )
    industry_profile.add_argument("--adapter", default="", dest="adapter_id")
    industry_profile.add_argument(
        "--output-dir", default="data/industry_profiles", dest="output_dir"
    )
    industry_profile.add_argument("--profile-id", default="", dest="profile_id")
    evidence_template = subparsers.add_parser(
        "evidence-template",
        help="create blank records for manually verified company evidence",
    )
    evidence_template.add_argument("--input", required=True, dest="input_path")
    evidence_template.add_argument(
        "--field", action="append", default=None, dest="fields"
    )
    evidence_template.add_argument(
        "--profile",
        choices=("listing-market", "deep-company"),
        default="",
        dest="profile",
        help="predefined evidence field set; --field can append custom fields",
    )
    evidence_template.add_argument(
        "--company-id", action="append", default=None, dest="company_ids"
    )
    evidence_template.add_argument(
        "--output-dir", default="data/supplemental_evidence", dest="output_dir"
    )
    evidence_template.add_argument("--snapshot-id", default="", dest="snapshot_id")
    readiness = subparsers.add_parser(
        "readiness",
        help="derive a conservative researchability gate from supplemental evidence",
    )
    readiness.add_argument("--input", required=True, dest="input_path")
    readiness.add_argument(
        "--output-dir", default="data/company_readiness", dest="output_dir"
    )
    readiness.add_argument("--snapshot-id", default="", dest="snapshot_id")
    quick = subparsers.add_parser(
        "quick-research",
        help="build an evidence-only quick company research snapshot",
    )
    quick.add_argument("--readiness", required=True, dest="readiness_path")
    quick.add_argument("--supplemental", required=True, dest="supplemental_path")
    quick.add_argument(
        "--output-dir", default="data/company_quick_research", dest="output_dir"
    )
    quick.add_argument("--snapshot-id", default="", dest="snapshot_id")
    discover = subparsers.add_parser(
        "discover", help="run the read-only industry-to-company discovery pipeline"
    )
    discover.add_argument("--as-of", default=None, dest="as_of")
    discover.add_argument("--max-selected-industries", type=int, default=3)
    discover.add_argument(
        "--radar-limit",
        type=int,
        default=50,
        help="bounded number of industry rows read by each radar source",
    )
    discover.add_argument("--company-pool-size", type=int, default=10)
    discover.add_argument("--output-dir", default="data/discovery", dest="output_dir")
    discover.add_argument(
        "--version-output-dir", default="data/research_versions", dest="version_output_dir"
    )
    discover.add_argument(
        "--research-candidate-set",
        action="append",
        default=None,
        dest="research_candidate_set_paths",
        help="explicit research-asset-candidate-set.v1 JSON; may be repeated",
    )
    discover.add_argument(
        "--alias-file",
        default="docs/industry_aliases.v1.json",
        dest="alias_file",
    )
    external = subparsers.add_parser("external-ai", help="normalise a pasted web AI answer")
    external.add_argument("--provider", required=True)
    external.add_argument("--question", required=True)
    external.add_argument("--answer", required=True)
    external.add_argument("--model", default="unknown", dest="model_label")
    source_document = subparsers.add_parser(
        "source-document",
        help="create an immutable source document manifest with a content hash",
    )
    source_document.add_argument("--input", required=True, dest="input_path")
    source_document.add_argument("--raw-content", default="", dest="raw_content_path")
    source_document.add_argument(
        "--output-dir", default="data/source_documents", dest="output_dir"
    )
    source_document.add_argument("--document-id", default="", dest="document_id")
    evidence_command = subparsers.add_parser(
        "evidence",
        help="build the unified evidence bundle and optionally reconcile conflicts",
    )
    evidence_command.add_argument("--input", required=True, dest="input_path")
    evidence_command.add_argument(
        "--output-dir", default="data/evidence", dest="output_dir"
    )
    evidence_command.add_argument("--bundle-id", default="", dest="bundle_id")
    evidence_command.add_argument(
        "--reconcile", action="store_true", dest="reconcile"
    )
    evidence_command.add_argument(
        "--group-by", action="append", default=None, dest="group_by"
    )
    evidence_command.add_argument(
        "--source-priority", action="append", default=None, dest="source_priorities"
    )
    refresh_evidence = subparsers.add_parser(
        "evidence-from-refresh",
        help="create a manual evidence-promotion gate from a saved data refresh",
    )
    refresh_evidence.add_argument("--refresh", required=True, dest="refresh_path")
    refresh_evidence.add_argument("--records", required=True, dest="records_path")
    refresh_evidence.add_argument("--refresh-uri", default="", dest="refresh_uri")
    refresh_evidence.add_argument("--research-as-of", default="", dest="research_as_of")
    refresh_evidence.add_argument("--reviewer-id", default="", dest="reviewer_id")
    refresh_evidence.add_argument("--reviewed-at", default="", dest="reviewed_at")
    refresh_evidence.add_argument("--review-reason", default="", dest="review_reason")
    refresh_evidence.add_argument("--bundle-id", default="", dest="bundle_id")
    refresh_evidence.add_argument("--gate-id", default="", dest="gate_id")
    refresh_evidence.add_argument("--user-confirmed", action="store_true", dest="user_confirmed")
    refresh_evidence.add_argument(
        "--output-dir", default="data/refresh_evidence_gates", dest="output_dir"
    )
    refresh_evidence_validate = subparsers.add_parser(
        "validate-evidence-from-refresh",
        help="validate a refresh evidence gate without promoting facts",
    )
    refresh_evidence_validate.add_argument("--input", required=True, dest="input_path")
    research_request = subparsers.add_parser(
        "research-request",
        help="normalize a research request with depth, mode, and budget",
    )
    research_request.add_argument("--input", required=True, dest="input_path")
    research_request.add_argument(
        "--output-dir", default="data/research_execution", dest="output_dir"
    )
    research_request.add_argument("--request-id", default="", dest="request_id")
    research_plan = subparsers.add_parser(
        "research-plan",
        help="build a bounded LOCAL_ONLY or LLM_ASSISTED execution plan",
    )
    research_plan.add_argument("--input", required=True, dest="input_path")
    research_plan.add_argument("--output-dir", default="data/research_execution", dest="output_dir")
    research_plan.add_argument("--available-model", action="store_true", dest="available_model")
    research_plan.add_argument("--used-input-tokens", type=int, default=0, dest="used_input_tokens")
    research_plan.add_argument("--used-output-tokens", type=int, default=0, dest="used_output_tokens")
    research_plan.add_argument("--differences", default="", dest="differences_path")
    research_plan.add_argument("--plan-id", default="", dest="plan_id")
    llm_run = subparsers.add_parser(
        "llm-run",
        help="record an authorized model call without making the call",
    )
    llm_run.add_argument("--input", required=True, dest="input_path")
    llm_run.add_argument("--output-dir", default="data/research_execution", dest="output_dir")
    llm_run.add_argument("--llm-run-id", default="", dest="llm_run_id")
    execution_audit = subparsers.add_parser(
        "execution-audit",
        help="audit model runs against one execution plan",
    )
    execution_audit.add_argument("--plan", required=True, dest="plan_path")
    execution_audit.add_argument("--runs", default="", dest="runs_path")
    execution_audit.add_argument("--output-dir", default="data/research_execution", dest="output_dir")
    execution_audit.add_argument("--audit-id", default="", dest="audit_id")
    capability_matrix = subparsers.add_parser(
        "capability-matrix",
        help="validate the component reuse and capability-gap matrix",
    )
    capability_matrix.add_argument("--input", required=True, dest="input_path")
    capability_matrix.add_argument("--output-dir", default="data/capabilities", dest="output_dir")
    capability_matrix.add_argument("--matrix-id", default="", dest="matrix_id")
    capability_gap = subparsers.add_parser(
        "capability-gap",
        help="record a bounded new-development capability gap",
    )
    capability_gap.add_argument("--input", required=True, dest="input_path")
    capability_gap.add_argument("--output-dir", default="data/capabilities", dest="output_dir")
    capability_gap.add_argument("--gap-id", default="", dest="gap_id")
    opportunity_quality = subparsers.add_parser(
        "opportunity-quality",
        help="evaluate preserved opportunity scans and explicit review samples",
    )
    opportunity_quality.add_argument("--input", required=True, dest="input_path")
    opportunity_quality.add_argument("--output-dir", default="data/opportunity_quality", dest="output_dir")
    opportunity_quality.add_argument("--quality-id", default="", dest="quality_id")
    lifecycle_event = subparsers.add_parser(
        "decision-lifecycle-event",
        help="append one immutable status event to a decision snapshot",
    )
    lifecycle_event.add_argument("--snapshot", required=True, dest="snapshot_path")
    lifecycle_event.add_argument("--input", required=True, dest="input_path")
    lifecycle_event.add_argument("--events", default="", dest="events_path")
    lifecycle_event.add_argument("--output-dir", default="data/decision_lifecycles", dest="output_dir")
    lifecycle_event.add_argument("--event-id", default="", dest="event_id")
    lifecycle = subparsers.add_parser(
        "decision-lifecycle",
        help="validate and project append-only decision lifecycle events",
    )
    lifecycle.add_argument("--snapshot", required=True, dest="snapshot_path")
    lifecycle.add_argument("--events", default="", dest="events_path")
    lifecycle.add_argument("--as-of", default="", dest="as_of")
    lifecycle.add_argument("--output-dir", default="data/decision_lifecycles", dest="output_dir")
    lifecycle.add_argument("--lifecycle-id", default="", dest="lifecycle_id")
    research_version = subparsers.add_parser(
        "research-version",
        help="create an immutable research-version manifest from a pipeline or manifest input",
    )
    research_version.add_argument("--input", required=True, dest="input_path")
    research_version.add_argument("--supplemental", default="", dest="supplemental_path")
    research_version.add_argument("--evidence-bundle", default="", dest="evidence_bundle_path")
    research_version.add_argument("--previous-version-id", default="", dest="previous_version_id")
    research_version.add_argument(
        "--execution-mode",
        choices=("LOCAL_ONLY", "LLM_ASSISTED", "MANUAL_WEB_AI"),
        default="LOCAL_ONLY",
        dest="execution_mode",
    )
    research_version.add_argument("--affected-module", action="append", default=None, dest="affected_modules")
    research_version.add_argument("--version-id", default="", dest="version_id")
    research_version.add_argument(
        "--source-health",
        default="",
        dest="source_health_path",
        help="optional validated data-source-health.v1 snapshot",
    )
    research_version.add_argument("--output-dir", default="data/research_versions", dest="output_dir")
    research_version_compare = subparsers.add_parser(
        "compare-research-versions",
        help="compare two immutable research-version manifests",
    )
    research_version_compare.add_argument("--previous", required=True, dest="previous_path")
    research_version_compare.add_argument("--current", required=True, dest="current_path")
    research_version_compare.add_argument("--output-dir", default="data/research_version_comparisons", dest="output_dir")
    research_version_validate = subparsers.add_parser(
        "validate-research-version",
        help="validate one immutable research-version manifest and its content hash",
    )
    research_version_validate.add_argument("--input", required=True, dest="input_path")
    research_version_replay = subparsers.add_parser(
        "replay-research-version",
        help="validate a research-version manifest and prepare a local replay",
    )
    research_version_replay.add_argument("--version", required=True, dest="version_path")
    research_version_replay.add_argument("--artifacts", default="", dest="artifacts_path")
    research_version_replay.add_argument("--output-dir", default="data/research_version_replays", dest="output_dir")
    source_health = subparsers.add_parser(
        "source-health",
        help="check configured data-source readiness and write an immutable snapshot",
    )
    source_health.add_argument(
        "--source",
        action="append",
        default=None,
        dest="source_names",
        help="limit the check to one source; may be repeated",
    )
    source_health.add_argument(
        "--subject-type",
        action="append",
        default=None,
        dest="subject_types",
        help="route subject type; may be repeated",
    )
    source_health.add_argument(
        "--required-capability",
        action="append",
        default=None,
        dest="required_capabilities",
        help="required capability as subject_type=capability; may be repeated",
    )
    source_health.add_argument("--checked-at", default="", dest="checked_at")
    source_health.add_argument("--snapshot-id", default="", dest="snapshot_id")
    source_health.add_argument("--output-dir", default="data/source_health", dest="output_dir")
    source_health_validate = subparsers.add_parser(
        "validate-source-health",
        help="validate an immutable data-source-health.v1 snapshot",
    )
    source_health_validate.add_argument("--input", required=True, dest="input_path")
    data_refresh = subparsers.add_parser(
        "data-refresh",
        help="fetch an explicit bounded query manifest through primary/fallback sources",
    )
    data_refresh.add_argument("--input", required=True, dest="input_path")
    data_refresh.add_argument("--output-dir", default="data/data_source_refreshes", dest="output_dir")
    data_refresh.add_argument("--refresh-id", default="", dest="refresh_id")
    data_refresh.add_argument("--as-of", default="", dest="as_of")
    data_refresh.add_argument("--max-queries", type=int, default=20, dest="max_queries")
    data_refresh.add_argument("--max-rows-per-query", type=int, default=500, dest="max_rows_per_query")
    data_refresh_validate = subparsers.add_parser(
        "validate-data-refresh",
        help="validate an immutable data-source-refresh.v1 snapshot without fetching",
    )
    data_refresh_validate.add_argument("--input", required=True, dest="input_path")
    data_refresh_tracking = subparsers.add_parser(
        "data-refresh-track",
        help="compare two saved data-source-refresh.v1 snapshots without fetching",
    )
    data_refresh_tracking.add_argument("--current", required=True, dest="current_path")
    data_refresh_tracking.add_argument("--previous", default="", dest="previous_path")
    data_refresh_tracking.add_argument("--as-of", default="", dest="as_of")
    data_refresh_tracking.add_argument("--tracking-id", default="", dest="tracking_id")
    data_refresh_tracking.add_argument(
        "--output-dir", default="data/data_source_refresh_tracking", dest="output_dir"
    )
    data_refresh_tracking_validate = subparsers.add_parser(
        "validate-data-refresh-track",
        help="validate a data-source-refresh-tracking.v1 snapshot",
    )
    data_refresh_tracking_validate.add_argument("--input", required=True, dest="input_path")
    resolve_task = subparsers.add_parser(
        "resolve-task",
        help="resolve user input into a safe research-task envelope",
    )
    resolve_task_input = resolve_task.add_mutually_exclusive_group(required=True)
    resolve_task_input.add_argument("--input", default="", dest="input_path")
    resolve_task_input.add_argument("--input-text", default="", dest="input_text")
    resolve_task.add_argument("--task-type", default="", dest="task_type")
    resolve_task.add_argument("--subject-type", default="", dest="subject_type")
    resolve_task.add_argument("--as-of", default="", dest="research_as_of")
    resolve_task.add_argument(
        "--depth", choices=("QUICK", "STANDARD", "DEEP"), default="STANDARD", dest="requested_depth"
    )
    resolve_task.add_argument("--no-simulation", action="store_false", dest="simulation_mode")
    resolve_task.set_defaults(simulation_mode=True)
    resolve_task.add_argument("--risk-preference", default="", dest="risk_preference")
    resolve_task.add_argument("--confirmed", action="store_true", dest="confirmed")
    resolve_task.add_argument(
        "--security-master",
        default="",
        dest="security_master_path",
        help="optional local security-master-snapshot.v1 for exact identity matching",
    )
    resolve_task.add_argument(
        "--commodity-config",
        action="append",
        default=None,
        dest="commodity_config_paths",
        help="local commodity-adapter.v1 JSON; may be repeated for futures aliases",
    )
    resolve_task.add_argument("--task-id", default="", dest="task_id")
    resolve_task.add_argument("--output-dir", default="data/research_tasks", dest="output_dir")
    validate_task = subparsers.add_parser(
        "validate-research-task",
        help="validate an immutable research-task-resolution.v1 envelope",
    )
    validate_task.add_argument("--input", required=True, dest="input_path")
    third_party_registry = subparsers.add_parser(
        "third-party-components",
        help="validate and list the optional third-party component registry",
    )
    third_party_registry.add_argument("--input", required=True, dest="input_path")
    third_party_registry.add_argument(
        "--output-dir", default="data/third_party_components", dest="output_dir"
    )
    third_party_registry.add_argument("--registry-id", default="", dest="registry_id")
    third_party_registry.add_argument(
        "--candidate-review",
        action="append",
        default=None,
        dest="candidate_review_paths",
        help="optional immutable candidate review/projection JSON; may be repeated",
    )
    third_party_health = subparsers.add_parser(
        "third-party-health",
        help="check local readiness of optional third-party components",
    )
    third_party_health.add_argument("--registry", required=True, dest="registry_path")
    third_party_health.add_argument("--checked-at", default="", dest="checked_at")
    third_party_health.add_argument("--snapshot-id", default="", dest="snapshot_id")
    third_party_health.add_argument(
        "--output-dir", default="data/third_party_components", dest="output_dir"
    )
    third_party_health_validate = subparsers.add_parser(
        "validate-third-party-health",
        help="validate an immutable third-party component health snapshot",
    )
    third_party_health_validate.add_argument("--input", required=True, dest="input_path")
    candidate_review = subparsers.add_parser(
        "third-party-candidate-review",
        help="create or validate one external project capability-slice review",
    )
    candidate_review.add_argument("--input", required=True, dest="input_path")
    candidate_review.add_argument(
        "--output-dir", default="data/third_party_candidate_reviews", dest="output_dir"
    )
    candidate_review.add_argument("--review-id", default="", dest="review_id")
    candidate_review_event = subparsers.add_parser(
        "third-party-candidate-review-event",
        help="append one immutable state event to a candidate review",
    )
    candidate_review_event.add_argument("--review", required=True, dest="review_path")
    candidate_review_event.add_argument("--input", required=True, dest="input_path")
    candidate_review_event.add_argument("--events", default="", dest="events_path")
    candidate_review_event.add_argument(
        "--output-dir", default="data/third_party_candidate_reviews", dest="output_dir"
    )
    candidate_review_event.add_argument("--event-id", default="", dest="event_id")
    candidate_review_event.add_argument("--projection-id", default="", dest="projection_id")
    candidate_review_validate = subparsers.add_parser(
        "validate-third-party-candidate-review",
        help="validate an immutable candidate review, event, or projection",
    )
    candidate_review_validate.add_argument("--input", required=True, dest="input_path")
    third_party_parse = subparsers.add_parser(
        "third-party-parse",
        help="parse a local PDF with an explicitly selected optional adapter",
    )
    third_party_parse.add_argument(
        "--component", choices=("pypdf", "pdfplumber", "camelot"), required=True
    )
    third_party_parse.add_argument("--input", required=True, dest="input_path")
    third_party_parse.add_argument("--document-id", required=True, dest="document_id")
    third_party_parse.add_argument("--research-as-of", required=True, dest="research_as_of")
    third_party_parse.add_argument("--source-uri", default="", dest="source_uri")
    third_party_parse.add_argument(
        "--output-dir", default="data/third_party_document_parses", dest="output_dir"
    )
    third_party_parse.add_argument("--result-id", default="", dest="result_id")
    performance_metrics = subparsers.add_parser(
        "performance-metrics",
        help="calculate read-only return and risk statistics with local fallback",
    )
    performance_metrics.add_argument("--input", required=True, dest="input_path")
    performance_metrics.add_argument(
        "--output-dir", default="data/third_party_performance", dest="output_dir"
    )
    performance_metrics.add_argument("--result-id", default="", dest="result_id")
    performance_validate = subparsers.add_parser(
        "validate-performance-metrics",
        help="validate an immutable third-party performance result",
    )
    performance_validate.add_argument("--input", required=True, dest="input_path")
    args = parser.parse_args()

    if args.command == "demo":
        print(json.dumps(demo(), ensure_ascii=False, indent=2))
    elif args.command == "company":
        config = load_company_config(args.config)
        snapshot = CompanyResearchAssembler(default_data_source_router()).collect(
            snapshot_from_config(config)
        )
        snapshot_path = _store_artifact(
            parser,
            JsonSnapshotStore(args.snapshot_dir),
            f"company-{snapshot.company_id.replace('.', '-')}-{snapshot.as_of}",
            {
                "schema_version": "company-research-snapshot.v1",
                "company": config,
                "research": snapshot.to_dict(),
                "execution_mode": "LOCAL_DATA_ROUTER",
            },
        )
        print(
            json.dumps(
                {"snapshot": str(snapshot_path), "research": snapshot.to_dict()},
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "industry-radar":
        config = load_radar_config(args.config)
        collection = IndustryRadarCollector(default_data_source_router()).collect(
            config, as_of=args.as_of
        )
        snapshot_path = _store_artifact(
            parser,
            JsonSnapshotStore(args.snapshot_dir),
            f"radar-{collection.snapshot.industry_id}-{collection.snapshot.as_of}",
            {
                "schema_version": "configured-industry-radar-snapshot.v1",
                "industry": config,
                "radar": collection.to_dict(),
                "execution_mode": "INDUSTRY_SIGNAL_ROUTER",
            },
        )
        print(
            json.dumps(
                {"snapshot": str(snapshot_path), "radar": collection.to_dict()},
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "industry":
        config = load_config(args.config)
        project_root = Path.cwd()
        source_integrity = build_source_integrity_report(config, project_root)
        config = apply_source_integrity(config, source_integrity)
        catalog = LocalResearchAssetCatalog(project_root)
        scan_id = (
            f"industry-scan-{config['industry_id']}-{config['as_of']}-"
            f"{source_integrity['content_hash'][:12]}"
        )
        scan = IndustryFirstDiscovery(
            InMemoryRadar([radar_from_config(config)]),
            ConfigCompanyPool(
                candidates_from_config(config),
                catalog=catalog,
            ),
            LocalAssetDataProvider(),
        ).run(config["as_of"], scan_id=scan_id)
        store = JsonSnapshotStore(args.snapshot_dir)
        _store_artifact(
            parser,
            store,
            source_integrity["report_id"],
            source_integrity,
        )
        snapshot_path = _store_artifact(
            parser,
            store,
            scan.scan_id,
            {
                "schema_version": "industry-vertical-slice.v1",
                "scan": scan.to_dict(),
                "industry": config,
                "source_integrity_report_id": source_integrity["report_id"],
                "source_integrity_content_hash": source_integrity["content_hash"],
                "execution_mode": "LOCAL_ASSET_REUSE",
            },
        )
        report = render_scan_markdown(scan, config, source_documents(config))
        html_report = render_scan_html(scan, config, source_documents(config))
        if args.output:
            target = Path(args.output)
            result = {"report": str(target), "snapshot": str(snapshot_path)}
            rendered_files = [(target, report.encode("utf-8"))]
            if args.html_output:
                html_target = Path(args.html_output)
                rendered_files.append((html_target, html_report.encode("utf-8")))
                result["html_report"] = str(html_target)
            try:
                write_files_immutable(rendered_files)
            except ImmutableFileExistsError as error:
                parser.error(str(error))
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(report)
    elif args.command == "radar":
        as_of = args.as_of or current_as_of()
        if args.source == "eastmoney":
            radar_provider = EastmoneyIndustryRadar(page_size=args.limit)
            api_errors = (EastmoneyAPIError,)
        elif args.source == "tonghuashun":
            radar_provider = TonghuashunIndustryRadar(page_size=args.limit)
            api_errors = (TonghuashunAPIError,)
        else:
            try:
                alias_registry = IndustryAliasRegistry.from_file(args.alias_file)
            except IndustryAliasError as error:
                parser.error(str(error))
            radar_provider = CrossSourceIndustryRadar(
                EastmoneyIndustryRadar(page_size=args.limit),
                TonghuashunIndustryRadar(page_size=args.limit),
                primary_name="eastmoney",
                secondary_name="tonghuashun",
                alias_registry=alias_registry,
            )
            api_errors = (EastmoneyAPIError, TonghuashunAPIError)
        try:
            items = list(radar_provider.snapshots(as_of))
        except api_errors as error:
            parser.error(str(error))
        snapshot_prefix = f"{args.source}-industry"
        payload = {
            "schema_version": "industry-radar.v1",
            "snapshot_id": f"{snapshot_prefix}-{as_of}",
            "source": radar_provider.metadata(as_of),
            "items": [item.to_dict() for item in items],
        }
        store = JsonSnapshotStore(Path(args.output_dir))
        store.write_immutable(f"{snapshot_prefix}-{as_of}", payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.command == "trend":
        try:
            report = build_trend_report(
                args.input_dir,
                source=args.source,
                as_of=args.as_of,
                window=args.window,
                min_observations=args.min_observations,
                min_direction_ratio=args.min_direction_ratio,
            )
            write_trend_report(report, args.output_dir)
        except RadarTrendError as error:
            parser.error(str(error))
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "company-pool":
        as_of = args.as_of or current_as_of()
        industry = IndustryRadarSnapshot(
            industry_id=args.industry_id,
            display_name=args.industry_name,
            as_of=as_of,
            state=IndustryState.CLEARING,
        )
        provider = TonghuashunCompanyPool(page_size=args.limit)
        try:
            candidates = list(provider.candidates(industry, args.limit))
        except TonghuashunCompanyPoolError as error:
            parser.error(str(error))
        light_data_summary = {"requested": False, "status_counts": {}}
        if args.with_light_data:
            candidates = list(
                ChainedCompanyData(
                    (TonghuashunLightCompanyData(), EastmoneyCompanySurveyData())
                ).enrich(candidates, CompanyDataTier.LIGHT)
            )
            counts: dict[str, int] = {}
            for candidate in candidates:
                status = str(candidate.light_profile.get("status", "UNKNOWN"))
                counts[status] = counts.get(status, 0) + 1
            light_data_summary = {"requested": True, "status_counts": counts}
        payload = {
            "schema_version": "industry-company-pool.v1",
            "snapshot_id": f"tonghuashun-company-pool-{args.industry_id}-{as_of}",
            "industry": industry.to_dict(),
            "source": provider.metadata(),
            "candidates": [candidate.to_dict() for candidate in candidates],
            "read_only": True,
            "full_industry_membership_loaded": False,
            "light_data": light_data_summary,
        }
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            f"tonghuashun-company-pool-{args.industry_id}-{as_of}", payload
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.command == "discover":
        as_of = args.as_of or current_as_of()
        try:
            alias_registry = IndustryAliasRegistry.from_file(args.alias_file)
        except IndustryAliasError as error:
            parser.error(str(error))
        radar_provider = CrossSourceIndustryRadar(
            EastmoneyIndustryRadar(page_size=args.radar_limit),
            TonghuashunIndustryRadar(page_size=args.radar_limit),
            primary_name="eastmoney",
            secondary_name="tonghuashun",
            alias_registry=alias_registry,
        )
        research_candidate_sets: list[Mapping[str, Any]] = []
        if args.research_candidate_set:
            try:
                for candidate_set_path in args.research_candidate_set_paths:
                    candidate_set = json.loads(
                        Path(candidate_set_path).read_text(encoding="utf-8")
                    )
                    if not isinstance(candidate_set, Mapping):
                        raise ResearchAssetError(
                            "research candidate set must be a JSON object"
                        )
                    research_candidate_sets.append(candidate_set)
            except (
                OSError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                TypeError,
                ValueError,
                ResearchAssetError,
            ) as error:
                parser.error(str(error))
        company_pool_provider = ResearchAssetCompanyPool(
            research_candidate_sets,
            fallback=TonghuashunCompanyPool(page_size=args.company_pool_size),
        )
        discovery = IndustryFirstDiscovery(
            radar_provider,
            company_pool_provider,
            ChainedCompanyData(
                (TonghuashunLightCompanyData(), EastmoneyCompanySurveyData())
            ),
            policy=ResourcePolicy(
                max_selected_industries=args.max_selected_industries,
                company_pool_size=args.company_pool_size,
                supplemental_company_limit=min(10, args.company_pool_size),
                deep_company_limit=min(5, args.company_pool_size),
                ai_deep_company_limit=min(3, args.company_pool_size),
            ),
        )
        try:
            scan = discovery.run(as_of)
        except (EastmoneyAPIError, TonghuashunAPIError, TonghuashunCompanyPoolError) as error:
            parser.error(str(error))
        payload = {
            "schema_version": "industry-discovery.v1",
            "snapshot_id": f"cross-discovery-{as_of}",
            "as_of": as_of,
            "scan": scan.to_dict(),
            "radar_source": radar_provider.metadata(as_of),
            "alias_registry": alias_registry.metadata(),
            "company_data": {
                "provider": company_pool_provider.metadata().get("provider")
                or "tonghuashun_light",
                "tier": "LIGHT",
                "read_only": True,
                "execution_enabled": False,
                "status_counts": _light_profile_status_counts(scan),
                "research_asset_reuse": company_pool_provider.metadata(),
            },
        }
        opportunity_candidates = []
        for industry_id, candidates in scan.company_pools.items():
            industry = next(
                (item for item in scan.selected_industries if item.industry_id == industry_id),
                None,
            )
            for candidate in candidates:
                candidate_assessments = (
                    candidate.metadata.get("opportunity_assessments") or {}
                )
                cycle_assessment = candidate_assessments.get("cycle_reversal") or {}
                screening_inputs = candidate.metadata.get("screening_inputs") or {}
                survival_value = screening_inputs.get("survival")
                evidence_refs = [
                    str(candidate.source or "").strip(),
                    str(candidate.light_profile.get("source") or "").strip(),
                ]
                evidence_refs = [item for item in evidence_refs if item]
                opportunity_types = list(industry.opportunity_types) if industry else []
                candidate_payload = {
                    "schema_version": "opportunity-candidate-input.v1",
                    "as_of": as_of,
                    "candidate": {
                        "candidate_id": f"{industry_id}-{candidate.company_id}",
                        "company_id": candidate.company_id,
                        "display_name": candidate.display_name,
                        "industry_id": industry_id,
                    },
                    "opportunity_types": opportunity_types,
                    "dimensions": {
                        "downside_protection": {
                            "status": "PARTIAL" if survival_value else "NOT_EVALUABLE",
                            "survival_gate_pass": (
                                None
                                if survival_value is None
                                else survival_value in {"strong", "adequate"}
                            ),
                            "evidence_refs": evidence_refs,
                        },
                        "inflection_evidence": {
                            "status": "PARTIAL" if cycle_assessment.get("status") in {"WATCH", "PASS"} else "NOT_EVALUABLE",
                            "independent_signal_types": 0,
                            "normal_update_cycles": 0,
                            "evidence_refs": evidence_refs,
                        },
                        "profit_convexity": {"status": "NOT_EVALUABLE", "evidence_refs": []},
                        "expectation_gap": {"status": "NOT_EVALUABLE", "not_obviously_overpriced": False, "evidence_refs": []},
                    },
                    "hard_gates": {
                        "identity": {"status": "PASS" if candidate.company_id and candidate.display_name else "BLOCKED", "evidence_refs": evidence_refs},
                        "company_light_data": {"status": "PASS" if candidate.light_profile.get("status") == "READY" else "INSUFFICIENT", "evidence_refs": evidence_refs},
                    },
                    "clocks": {
                        "industry_clock": {"state": industry.state.value if industry else "UNKNOWN", "evidence_refs": []},
                        "company_clock": {"state": "SURVIVAL_SECURE" if screening_inputs.get("survival") in {"strong", "adequate"} else "UNKNOWN", "evidence_refs": evidence_refs},
                        "market_clock": {"state": "UNKNOWN", "evidence_refs": []},
                    },
                    "evidence_refs": evidence_refs,
                    "deep_research": {"complete": candidate.data_tier.value == "AI_DEEP"},
                }
                opportunity_candidates.append(build_opportunity_candidate(candidate_payload))
        payload["opportunity_candidates"] = opportunity_candidates
        payload["opportunity_discovery"] = {
            "schema_version": "opportunity-scan.v1",
            "candidate_count": len(opportunity_candidates),
            "items": opportunity_candidates,
            "state_counts": {
                state: sum(1 for item in opportunity_candidates if item["status"] == state)
                for state in ("DISCOVERED", "WATCH", "CANDIDATE", "REVIEWABLE", "REJECTED", "EXPIRED")
            },
            "empty_result": not any(
                item["status"] in {"CANDIDATE", "REVIEWABLE"}
                for item in opportunity_candidates
            ),
            "policy": {
                "derived_from_existing_discovery": True,
                "full_market_company_data": False,
                "not_investment_conclusion": True,
                "read_only": True,
                "execution_enabled": False,
            },
        }
        discovery_id = f"cross-discovery-{as_of}"
        version = build_research_version(
            {
                "subject_type": "opportunity_scan",
                "subject_ids": [
                    str(item.industry_id)
                    for item in scan.selected_industries
                    if str(item.industry_id)
                ] or ["opportunity-discovery"],
                "research_as_of": as_of,
                "execution_mode": "LOCAL_ONLY",
                "affected_modules": [
                    "industry_radar",
                    "company_pool",
                    "opportunity_discovery",
                    "opportunity_tracking",
                ],
                "artifact_refs": [{
                    "artifact_id": discovery_id,
                    "artifact_type": "industry_discovery",
                    "as_of": as_of,
                    "content_hash": _payload_hash_without_version_id(payload),
                }],
                "source_ids": ["eastmoney", "tonghuashun"],
                "rule_versions": {"opportunity": "opportunity-candidate-rules.v1"},
                "version_status": "VALID",
            },
            version_id=f"research-version-{discovery_id}",
        )
        payload["research_version_id"] = version["version_id"]
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(discovery_id, payload)
        JsonSnapshotStore(Path(args.version_output_dir)).write_immutable(
            version["version_id"], version
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.command == "screen":
        try:
            alias_registry = IndustryAliasRegistry.from_file(args.alias_file)
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            raw_candidates = payload.get("candidates")
            if not isinstance(raw_candidates, list):
                raise CompanyScreenError("input file has no candidates list")
            candidates = [CompanyCandidate(**_candidate_kwargs(item)) for item in raw_candidates]
            industry = payload.get("industry")
            if not isinstance(industry, dict):
                industry = {}
            report = screen_company_candidates(
                candidates,
                expected_industry=args.expected_industry,
                input_snapshot_id=str(payload.get("snapshot_id") or ""),
                input_as_of=str(industry.get("as_of") or ""),
                input_source=payload.get("source") or "",
                industry_alias_registry=alias_registry,
                expected_industry_source=args.expected_industry_source,
                reported_industry_source=args.reported_industry_source,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            CompanyScreenError,
            IndustryAliasError,
        ) as error:
            parser.error(str(error))
        report_id = f"company-light-screen-{Path(args.input_path).stem}"
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report_id, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "queue":
        try:
            screen_report = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            queue_report = build_candidate_queue(
                screen_report,
                as_of=args.as_of,
                source=args.source,
                snapshot_id=args.snapshot_id or Path(args.input_path).stem,
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, CandidateQueueError) as error:
            parser.error(str(error))
        queue_id = queue_report["queue_id"]
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(queue_id, queue_report)
        print(json.dumps(queue_report, ensure_ascii=False, indent=2))
    elif args.command == "supplemental":
        try:
            queue_report = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            evidence_payload = json.loads(
                Path(args.evidence_path).read_text(encoding="utf-8")
            )
            if isinstance(evidence_payload, list):
                evidence_records = evidence_payload
            elif isinstance(evidence_payload, dict):
                evidence_records = evidence_payload.get("records")
            else:
                evidence_records = None
            if not isinstance(evidence_records, list):
                raise SupplementalEvidenceError(
                    "evidence input must be a list or an object with records list"
                )
            supplemental_kwargs = {"snapshot_id": args.snapshot_id}
            if args.required_fields:
                supplemental_kwargs["required_fields"] = args.required_fields
            report = build_supplemental_evidence_report(
                queue_report, evidence_records, **supplemental_kwargs
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            SupplementalEvidenceError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "product-profile":
        try:
            supplemental_report = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            product_profile_kwargs = {"snapshot_id": args.snapshot_id}
            if args.company_scopes_path:
                product_profile_kwargs["company_scope_reports"] = normalize_scope_reports(
                    json.loads(Path(args.company_scopes_path).read_text(encoding="utf-8"))
                )
            if args.required_fields:
                product_profile_kwargs["required_fields"] = args.required_fields
            report = build_product_profile_report(
                supplemental_report, **product_profile_kwargs
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ProductProfileError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "product-profit-bridge":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            company_scope_reports = None
            if args.company_scopes_path:
                company_scope_reports = normalize_scope_reports(
                    json.loads(Path(args.company_scopes_path).read_text(encoding="utf-8"))
                )
            report = build_product_profit_bridge_report(
                payload,
                company_scope_reports=company_scope_reports,
                bridge_id=args.bridge_id,
                rule_version=args.rule_version,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ProductProfitBridgeError,
        ) as error:
            parser.error(str(error))
        try:
            JsonSnapshotStore(Path(args.output_dir)).write_immutable(
                report["report_id"], report
            )
        except SnapshotExistsError as error:
            parser.error(str(error))
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "product-profit-bridge-validate":
        try:
            report_input = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            validation = validate_product_profit_bridge_report(report_input)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ProductProfitBridgeError,
        ) as error:
            parser.error(str(error))
        print(json.dumps(validation, ensure_ascii=False, indent=2))
    elif args.command == "product-lifecycle":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            company_scope_reports = None
            if args.company_scopes_path:
                company_scope_reports = normalize_scope_reports(
                    json.loads(Path(args.company_scopes_path).read_text(encoding="utf-8"))
                )
            report = build_product_lifecycle_report(
                payload,
                company_scope_reports=company_scope_reports,
                snapshot_id=args.snapshot_id,
                rule_version=args.rule_version,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ProductLifecycleError,
        ) as error:
            parser.error(str(error))
        try:
            JsonSnapshotStore(Path(args.output_dir)).write_immutable(
                report["report_id"], report
            )
        except SnapshotExistsError as error:
            parser.error(str(error))
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "product-lifecycle-validate":
        try:
            report_input = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            validation = validate_product_lifecycle_report(report_input)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ProductLifecycleError,
        ) as error:
            parser.error(str(error))
        print(json.dumps(validation, ensure_ascii=False, indent=2))
    elif args.command == "financial-model":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            company_scope_reports = None
            if args.company_scopes_path:
                company_scope_reports = normalize_scope_reports(
                    json.loads(Path(args.company_scopes_path).read_text(encoding="utf-8"))
                )
            report = build_financial_model_report(
                payload,
                company_scope_reports=company_scope_reports,
                model_id=args.model_id,
                rule_version=args.rule_version,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            FinancialModelError,
        ) as error:
            parser.error(str(error))
        try:
            JsonSnapshotStore(Path(args.output_dir)).write_immutable(
                report["report_id"], report
            )
        except SnapshotExistsError as error:
            parser.error(str(error))
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "financial-model-validate":
        try:
            report_input = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            validation = validate_financial_model_report(report_input)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            FinancialModelError,
        ) as error:
            parser.error(str(error))
        print(json.dumps(validation, ensure_ascii=False, indent=2))
    elif args.command == "application-mapping":
        try:
            product_profile_report = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            mapping_kwargs = {"snapshot_id": args.snapshot_id}
            if args.required_fields:
                mapping_kwargs["required_fields"] = args.required_fields
            report = build_application_mapping_report(
                product_profile_report, **mapping_kwargs
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ApplicationMappingError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "demand-transmission":
        try:
            application_mapping_report = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            transmission_kwargs = {"snapshot_id": args.snapshot_id}
            if args.required_fields:
                transmission_kwargs["required_fields"] = args.required_fields
            report = build_demand_transmission_report(
                application_mapping_report, **transmission_kwargs
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            DemandTransmissionError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "industry-situation":
        try:
            demand_transmission_report = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            situation_kwargs = {"snapshot_id": args.snapshot_id}
            if args.required_fields:
                situation_kwargs["required_fields"] = args.required_fields
            report = build_industry_situation_report(
                demand_transmission_report, **situation_kwargs
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            IndustrySituationError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "cycle-reversal":
        try:
            industry_situation_report = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            cycle_kwargs = {"snapshot_id": args.snapshot_id}
            if args.required_fields:
                cycle_kwargs["required_fields"] = args.required_fields
            report = build_cycle_reversal_report(
                industry_situation_report, **cycle_kwargs
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            CycleReversalError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "competitive-position":
        try:
            cycle_reversal_report = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            position_kwargs = {"snapshot_id": args.snapshot_id}
            if args.required_fields:
                position_kwargs["required_fields"] = args.required_fields
            report = build_competitive_position_report(
                cycle_reversal_report, **position_kwargs
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            CompetitivePositionError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "survival-analysis":
        try:
            competitive_position_report = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            survival_kwargs = {"snapshot_id": args.snapshot_id}
            if args.required_fields:
                survival_kwargs["required_fields"] = args.required_fields
            report = build_survival_analysis_report(
                competitive_position_report, **survival_kwargs
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            SurvivalAnalysisError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "valuation-scenarios":
        try:
            survival_analysis_report = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            valuation_kwargs = {"snapshot_id": args.snapshot_id}
            if args.required_fields:
                valuation_kwargs["required_fields"] = args.required_fields
            report = build_valuation_scenarios_report(
                survival_analysis_report, **valuation_kwargs
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValuationScenarioError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "market-structure":
        try:
            market_structure_input = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            market_data_snapshot = None
            if args.market_data_path:
                market_data_snapshot = json.loads(
                    Path(args.market_data_path).read_text(encoding="utf-8")
                )
            report = build_market_structure_report(
                market_structure_input,
                market_data_snapshot=market_data_snapshot,
                snapshot_id=args.snapshot_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            MarketStructureError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "market-structure-compare":
        try:
            market_structure_input = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            market_data_snapshot = None
            if args.market_data_path:
                market_data_snapshot = json.loads(
                    Path(args.market_data_path).read_text(encoding="utf-8")
                )
            report = build_market_structure_comparison(
                market_structure_input,
                market_data_snapshot=market_data_snapshot,
                adapters=(CzscAdapter(), ChanPyAdapter()),
                comparison_id=args.comparison_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            MarketStructureError,
            MarketStructureAdapterError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(
            report["comparison_id"], report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "adversarial-review":
        try:
            valuation_report = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            market_structure_report = None
            if args.market_structure_path:
                market_structure_report = json.loads(
                    Path(args.market_structure_path).read_text(encoding="utf-8")
                )
            report = build_adversarial_review_report(
                valuation_report,
                market_structure_report=market_structure_report,
                snapshot_id=args.snapshot_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            AdversarialReviewError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "research-report":
        try:
            adversarial_review_report = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            report = build_research_report(
                adversarial_review_report,
                snapshot_id=args.snapshot_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ResearchReportError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "render-report":
        try:
            report = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            paths = write_rendered_reports(
                report,
                args.output_dir,
                formats=args.formats or ("markdown", "html"),
                title=args.title,
                basename=args.basename,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ReportRenderingError,
        ) as error:
            parser.error(str(error))
        print(json.dumps({"schema_version": "research-report-render.v1", "paths": paths}, ensure_ascii=False, indent=2))
    elif args.command == "public-draft":
        try:
            source_report = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            source_lock = json.loads(Path(args.source_lock_path).read_text(encoding="utf-8"))
            draft = build_public_draft(
                source_report,
                source_lock,
                channel=args.channel,
                title=args.title,
                draft_version=args.draft_version,
                public_draft_id=args.draft_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            PublicDraftError,
        ) as error:
            parser.error(str(error))
        output_root = Path(args.output_dir)
        output_root.mkdir(parents=True, exist_ok=True)
        content_path = output_root / f"{draft['public_draft_id']}.md"
        draft["content_uri"] = str(content_path)
        content_existed = content_path.exists()
        try:
            write_text_immutable(content_path, draft["content"])
            try:
                JsonSnapshotStore(output_root).write_artifact(
                    draft["public_draft_id"], draft
                )
            except Exception:
                if not content_existed:
                    content_path.unlink(missing_ok=True)
                raise
        except (ImmutableFileExistsError, SnapshotExistsError) as error:
            parser.error(str(error))
        print(json.dumps({"draft": draft, "content_path": str(content_path)}, ensure_ascii=False, indent=2))
    elif args.command == "validate-public-draft":
        try:
            draft = validate_public_draft(
                json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            PublicDraftError,
        ) as error:
            parser.error(str(error))
        print(json.dumps({"valid": True, "draft": draft}, ensure_ascii=False, indent=2))
    elif args.command == "research-pipeline":
        try:
            supplemental_report = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            market_structure_report = None
            if args.market_structure_path:
                market_structure_report = json.loads(
                    Path(args.market_structure_path).read_text(encoding="utf-8")
                )
            evidence_bundle = None
            if args.evidence_bundle_path:
                evidence_bundle = json.loads(
                    Path(args.evidence_bundle_path).read_text(encoding="utf-8")
                )
            company_scope_reports = None
            if args.company_scopes_path:
                company_scope_reports = normalize_scope_reports(
                    json.loads(Path(args.company_scopes_path).read_text(encoding="utf-8"))
                )
            product_profit_bridge_report = None
            if args.product_profit_bridge_path:
                product_profit_bridge_report = json.loads(
                    Path(args.product_profit_bridge_path).read_text(encoding="utf-8")
                )
            product_lifecycle_report = None
            if args.product_lifecycle_path:
                product_lifecycle_report = json.loads(
                    Path(args.product_lifecycle_path).read_text(encoding="utf-8")
                )
            financial_model_report = None
            if args.financial_model_path:
                financial_model_report = json.loads(
                    Path(args.financial_model_path).read_text(encoding="utf-8")
                )
            report = build_research_pipeline(
                supplemental_report,
                market_structure_report=market_structure_report,
                evidence_bundle=evidence_bundle,
                company_scope_reports=company_scope_reports,
                product_profit_bridge_report=product_profit_bridge_report,
                product_lifecycle_report=product_lifecycle_report,
                financial_model_report=financial_model_report,
                snapshot_id=args.snapshot_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ) as error:
            parser.error(str(error))
        version = build_research_version_from_pipeline(
            report,
            supplemental=supplemental_report,
            evidence_bundle=evidence_bundle,
            product_profit_bridge_report=product_profit_bridge_report,
            product_lifecycle_report=product_lifecycle_report,
            financial_model_report=financial_model_report,
            execution_mode="LOCAL_ONLY",
        )
        version["artifact_refs"] = [
            {
                **reference,
                "content_hash": _payload_hash_without_version_id(report),
            }
            if reference.get("artifact_type") == "pipeline"
            else reference
            for reference in version["artifact_refs"]
        ]
        version["content_hash"] = _research_version_content_hash(version)
        report["research_version_id"] = version["version_id"]
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            report["pipeline_id"], report
        )
        JsonSnapshotStore(Path(args.version_output_dir)).write_immutable(
            version["version_id"], version
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "incremental-update":
        try:
            previous_pipeline = json.loads(
                Path(args.previous_pipeline_path).read_text(encoding="utf-8")
            )
            previous_supplemental = json.loads(
                Path(args.previous_supplemental_path).read_text(encoding="utf-8")
            )
            evidence_payload = json.loads(
                Path(args.evidence_path).read_text(encoding="utf-8")
            )
            if isinstance(evidence_payload, Mapping):
                evidence_records = evidence_payload.get("records")
            else:
                evidence_records = evidence_payload
            if not isinstance(evidence_records, list):
                raise IncrementalUpdateError("evidence input must be a records list")
            company_scope_reports = None
            if args.company_scopes_path:
                company_scope_reports = normalize_scope_reports(
                    json.loads(Path(args.company_scopes_path).read_text(encoding="utf-8"))
                )
            market_structure_report = None
            if args.market_structure_path:
                market_structure_report = json.loads(
                    Path(args.market_structure_path).read_text(encoding="utf-8")
                )
            evidence_bundle = None
            if args.evidence_bundle_path:
                evidence_bundle = json.loads(
                    Path(args.evidence_bundle_path).read_text(encoding="utf-8")
                )
            report = build_incremental_update(
                previous_pipeline,
                previous_supplemental,
                evidence_records,
                as_of=args.as_of,
                snapshot_id=args.snapshot_id,
                execution_mode=args.execution_mode,
                company_scope_reports=company_scope_reports,
                market_structure_report=market_structure_report,
                evidence_bundle=evidence_bundle,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            IncrementalUpdateError,
        ) as error:
            parser.error(str(error))
        previous_version_id = str(previous_pipeline.get("research_version_id") or "")
        version = build_research_version_from_pipeline(
            report["updated_pipeline"],
            supplemental=report["updated_supplemental"],
            evidence_bundle=evidence_bundle,
            previous_version_id=previous_version_id,
            execution_mode=report["execution_mode"],
            affected_modules=report["deferred_review_modules"],
        )
        version["artifact_refs"] = [
            {
                **reference,
                "content_hash": _payload_hash_without_version_id(report["updated_pipeline"]),
            }
            if reference.get("artifact_type") == "pipeline"
            else reference
            for reference in version["artifact_refs"]
        ]
        version["content_hash"] = _research_version_content_hash(version)
        report["research_version_id"] = version["version_id"]
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            report["update_id"], report
        )
        JsonSnapshotStore(Path(args.version_output_dir)).write_immutable(
            version["version_id"], version
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "schedule-init":
        try:
            schedule = build_default_schedule(
                schedule_id=args.schedule_id,
                as_of=args.as_of,
            )
            state = build_scheduler_state(schedule)
        except SchedulerError as error:
            parser.error(str(error))
        store = JsonSnapshotStore(Path(args.output_dir))
        schedule_path = store.write(f"schedule-{schedule['schedule_id']}", schedule)
        state_path = store.write(f"state-{schedule['schedule_id']}", state)
        print(
            json.dumps(
                {
                    "schedule": schedule,
                    "state": state,
                    "schedule_path": str(schedule_path),
                    "state_path": str(state_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "schedule-plan":
        try:
            schedule = json.loads(
                Path(args.schedule_path).read_text(encoding="utf-8")
            )
            state = json.loads(Path(args.state_path).read_text(encoding="utf-8"))
            events: list[Mapping[str, object]] = []
            if args.events_path:
                events_payload = json.loads(
                    Path(args.events_path).read_text(encoding="utf-8")
                )
                if isinstance(events_payload, Mapping):
                    events_payload = events_payload.get("events")
                if not isinstance(events_payload, list):
                    raise SchedulerError("events input must be an events list")
                events = events_payload
            plan, updated_state = build_scheduler_plan(
                schedule,
                state,
                events,
                now=args.now,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            SchedulerError,
        ) as error:
            parser.error(str(error))
        store = JsonSnapshotStore(Path(args.output_dir))
        plan_path = store.write(plan["plan_id"], plan)
        state_path = store.write(f"state-{plan['schedule_id']}", updated_state)
        print(
            json.dumps(
                {
                    "plan": plan,
                    "updated_state": updated_state,
                    "plan_path": str(plan_path),
                    "state_path": str(state_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "schedule-run":
        try:
            state = json.loads(Path(args.state_path).read_text(encoding="utf-8"))
            plan = json.loads(Path(args.plan_path).read_text(encoding="utf-8"))
            runner = LocalScheduledTaskRunner(
                data_root=args.output_root,
                alias_file=args.alias_file,
            )
            execution = runner.execute(state, plan, now=args.now)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ScheduledTaskRunnerError,
        ) as error:
            parser.error(str(error))
        execution_id = f"scheduler-execution-{execution['plan_id']}"
        execution["execution_id"] = execution_id
        JsonSnapshotStore(Path(args.output_root) / "scheduler" / "executions").write_immutable(
            execution_id, execution
        )
        JsonSnapshotStore(Path(args.output_root) / "scheduler").write(
            f"state-{execution['state']['schedule_id']}", execution["state"]
        )
        print(json.dumps(execution, ensure_ascii=False, indent=2))
    elif args.command == "freshness":
        try:
            supplemental_report = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            report = build_evidence_freshness_report(
                supplemental_report,
                as_of=args.as_of,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            TrackingError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "compare-versions":
        try:
            previous_pipeline = json.loads(
                Path(args.previous_pipeline_path).read_text(encoding="utf-8")
            )
            current_pipeline = json.loads(
                Path(args.current_pipeline_path).read_text(encoding="utf-8")
            )
            previous_supplemental = None
            current_supplemental = None
            if args.previous_supplemental_path:
                previous_supplemental = json.loads(
                    Path(args.previous_supplemental_path).read_text(encoding="utf-8")
                )
            if args.current_supplemental_path:
                current_supplemental = json.loads(
                    Path(args.current_supplemental_path).read_text(encoding="utf-8")
                )
            report = build_research_version_comparison(
                previous_pipeline,
                current_pipeline,
                previous_supplemental,
                current_supplemental,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            TrackingError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["comparison_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "thesis-check":
        try:
            thesis = json.loads(Path(args.thesis_path).read_text(encoding="utf-8"))
            supplemental_report = json.loads(
                Path(args.supplemental_path).read_text(encoding="utf-8")
            )
            previous_supplemental = None
            if args.previous_supplemental_path:
                previous_supplemental = json.loads(
                    Path(args.previous_supplemental_path).read_text(encoding="utf-8")
                )
            report = build_holding_thesis_check(
                thesis,
                supplemental_report,
                as_of=args.as_of,
                previous_supplemental=previous_supplemental,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            TrackingError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["check_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "thesis-lock":
        try:
            thesis = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            previous_thesis = None
            if args.previous_thesis_path:
                previous_thesis = json.loads(
                    Path(args.previous_thesis_path).read_text(encoding="utf-8")
                )
            report = build_holding_thesis(
                thesis,
                user_confirmed=args.user_confirmed,
                previous_thesis=previous_thesis,
                snapshot_id=args.snapshot_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            HoldingThesisError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["snapshot_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "decision-snapshot":
        try:
            research_report = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            decision = json.loads(
                Path(args.decision_path).read_text(encoding="utf-8")
            )
            evidence_bundle = None
            if args.evidence_bundle_path:
                evidence_bundle = json.loads(
                    Path(args.evidence_bundle_path).read_text(encoding="utf-8")
                )
            execution_plan = None
            if args.execution_plan_path:
                execution_plan = json.loads(
                    Path(args.execution_plan_path).read_text(encoding="utf-8")
                )
            company_scope_report = None
            if args.company_scope_path:
                company_scope_report = json.loads(
                    Path(args.company_scope_path).read_text(encoding="utf-8")
                )
            market_data_snapshots = None
            if args.market_data_paths:
                market_data_snapshots = [
                    json.loads(Path(path).read_text(encoding="utf-8"))
                    for path in args.market_data_paths
                ]
            report = build_decision_snapshot(
                research_report,
                decision,
                evidence_bundle=evidence_bundle,
                execution_plan=execution_plan,
                company_scope_report=company_scope_report,
                market_data_snapshots=market_data_snapshots,
                user_confirmed=args.user_confirmed,
                snapshot_id=args.snapshot_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            DecisionSnapshotError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["snapshot_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "attribution":
        try:
            decision_snapshot = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            outcome_input = json.loads(
                Path(args.outcome_path).read_text(encoding="utf-8")
            )
            asset_market_data_snapshot = None
            if args.asset_market_data_path:
                asset_market_data_snapshot = json.loads(
                    Path(args.asset_market_data_path).read_text(encoding="utf-8")
                )
            benchmark_market_data_snapshot = None
            if args.benchmark_market_data_path:
                benchmark_market_data_snapshot = json.loads(
                    Path(args.benchmark_market_data_path).read_text(encoding="utf-8")
                )
            report = build_attribution_report(
                decision_snapshot,
                outcome_input,
                closed_at=args.closed_at,
                attribution_id=args.attribution_id,
                asset_market_data_snapshot=asset_market_data_snapshot,
                benchmark_market_data_snapshot=benchmark_market_data_snapshot,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            AttributionError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(
            report["attribution_id"], report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "quality-scorecard":
        try:
            decision_snapshot = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )

            def optional_json(path: str) -> object | None:
                return (
                    json.loads(Path(path).read_text(encoding="utf-8"))
                    if path
                    else None
                )

            report = build_quality_scorecard(
                decision_snapshot,
                research_report=optional_json(args.research_report_path),
                attribution_report=optional_json(args.attribution_path),
                thesis_check=optional_json(args.thesis_check_path),
                freshness_report=optional_json(args.freshness_path),
                assessments=optional_json(args.assessments_path),
                opportunity_scan=optional_json(args.opportunity_scan_path),
                scorecard_id=args.scorecard_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            QualityScorecardError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(
            report["scorecard_id"], report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "portfolio-create":
        try:
            portfolio_input = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            decision_snapshots = [
                json.loads(Path(path).read_text(encoding="utf-8"))
                for path in args.decision_paths
            ]
            report = build_simulation_portfolio(
                portfolio_input,
                decision_snapshots,
                portfolio_id=args.portfolio_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            SimulationPortfolioError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(
            report["portfolio_id"], report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "portfolio-replay":
        try:
            portfolio = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            outcome_input = json.loads(
                Path(args.outcome_path).read_text(encoding="utf-8")
            )
            asset_market_data_snapshots = None
            if args.asset_market_data_dir:
                asset_market_data_snapshots = {}
                for subject_id in outcome_input.get("asset_series", {}):
                    asset_path = Path(args.asset_market_data_dir) / f"{subject_id}.json"
                    if asset_path.exists():
                        asset_market_data_snapshots[str(subject_id)] = json.loads(
                            asset_path.read_text(encoding="utf-8")
                        )
            benchmark_market_data_snapshot = None
            if args.benchmark_market_data_path:
                benchmark_market_data_snapshot = json.loads(
                    Path(args.benchmark_market_data_path).read_text(encoding="utf-8")
                )
            report = replay_simulation_portfolio(
                portfolio,
                outcome_input,
                closed_at=args.closed_at,
                replay_id=args.replay_id,
                asset_market_data_snapshots=asset_market_data_snapshots,
                benchmark_market_data_snapshot=benchmark_market_data_snapshot,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            SimulationPortfolioError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(
            report["replay_id"], report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "futures-simulation-create":
        try:
            simulation_input = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            decision_snapshots = [
                json.loads(Path(path).read_text(encoding="utf-8"))
                for path in args.decision_paths
            ]
            report = build_futures_simulation(
                simulation_input,
                decision_snapshots,
                simulation_id=args.simulation_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            FuturesSimulationError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            report["simulation_id"], report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "futures-simulation-replay":
        try:
            simulation = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            outcome_input = json.loads(
                Path(args.outcome_path).read_text(encoding="utf-8")
            )
            report = replay_futures_simulation(
                simulation,
                outcome_input,
                closed_at=args.closed_at,
                replay_id=args.replay_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            FuturesSimulationError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            report["replay_id"], report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "opportunity-candidate":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            report = build_opportunity_candidate(payload, candidate_id=args.candidate_id)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            OpportunityCandidateError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(
            report["candidate_id"], report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "opportunity-scan":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            report = build_opportunity_scan(payload)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            OpportunityCandidateError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(report["scan_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "announcement-templates":
        try:
            catalog = load_template_catalog(args.config_path)
        except (
            OSError,
            UnicodeDecodeError,
            AnnouncementTemplateError,
        ) as error:
            parser.error(str(error))
        catalog_hash = hashlib.sha256(
            json.dumps(catalog, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:20]
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(
            f"announcement-template-catalog-{catalog_hash}", catalog
        )
        print(json.dumps(catalog, ensure_ascii=False, indent=2))
    elif args.command == "announcement-parse":
        try:
            catalog = load_template_catalog(args.config_path)
            template = get_template(catalog, args.template_id)
            metadata: dict[str, Any] = {}
            if args.metadata_path:
                metadata = json.loads(Path(args.metadata_path).read_text(encoding="utf-8"))
                if not isinstance(metadata, Mapping):
                    raise AnnouncementTemplateError("--metadata must contain a JSON object")
            raw_path = Path(args.input_path)
            raw_content = raw_path.read_bytes()
            metadata.update(
                {
                    key: value
                    for key, value in {
                        "source_url": args.source_url,
                        "captured_at": args.captured_at,
                        "research_as_of": args.research_as_of,
                        "as_of": args.as_of,
                        "subject_type": args.subject_type,
                        "subject_id": args.subject_id,
                        "issuer": args.issuer,
                        "document_id": args.document_id,
                    }.items()
                    if value
                }
            )
            report = parse_announcement_input(metadata, raw_content, template)
            version = report.get("version") or 1
            raw_target = (
                Path(args.output_dir)
                / "raw"
                / f"{report['document_id']}-v{version}{raw_path.suffix or '.bin'}"
            )
            try:
                write_bytes_immutable(raw_target, raw_content)
            except ImmutableFileExistsError:
                if raw_target.read_bytes() != raw_content:
                    raise AnnouncementTemplateError(
                        f"immutable raw snapshot already exists with different content: {raw_target}"
                    )
            report = parse_announcement_input(
                metadata,
                raw_content,
                template,
                raw_content_uri=str(raw_target),
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            AnnouncementTemplateError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            f"{report['document_id']}-v{report.get('version') or 1}", report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "announcement-asset":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            raw_content = None
            raw_content_uri = ""
            if args.raw_content_path:
                source_path = Path(args.raw_content_path)
                raw_content = source_path.read_bytes()
                document_id = str(payload.get("document_id") or args.asset_id).strip()
                version = int(payload.get("version") or 1)
                raw_target = (
                    Path(args.output_dir)
                    / "raw"
                    / f"{document_id}-v{version}{source_path.suffix or '.bin'}"
                )
                write_bytes_immutable(raw_target, raw_content)
                raw_content_uri = str(raw_target)
            report = build_announcement_asset(
                payload,
                raw_content=raw_content,
                raw_content_uri=raw_content_uri,
                asset_id=args.asset_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            AnnouncementAssetError,
            ImmutableFileExistsError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            report["document_id"] + "-v" + str(report["version"]), report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "announcement-impact":
        try:
            asset = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            report = build_announcement_impact(
                asset,
                research_cutoff=args.research_cutoff,
                impact_id=args.impact_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            AnnouncementAssetError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(report["impact_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "research-impact-queue":
        try:
            event = json.loads(Path(args.event_path).read_text(encoding="utf-8"))
            version_paths = [Path(path) for path in args.version_paths or ()]
            if not version_paths:
                version_paths = sorted(Path(args.versions_dir).glob("*.json"))
            versions = [
                json.loads(path.read_text(encoding="utf-8")) for path in version_paths
            ]
            report = build_research_impact_queue(
                event, versions, queue_id=args.queue_id
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ResearchImpactError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            report["queue_id"], report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "validate-research-impact-queue":
        try:
            queue = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            report = validate_research_impact_queue(queue)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ResearchImpactError,
        ) as error:
            parser.error(str(error))
        print(json.dumps({"valid": True, "queue": report}, ensure_ascii=False, indent=2))
    elif args.command == "futures-identify":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            market_registry = None
            if args.market_registry_path:
                market_registry = MarketRegistry.from_payload(
                    json.loads(Path(args.market_registry_path).read_text(encoding="utf-8"))
                )
            report = identify_futures_object(
                payload, identity_id=args.identity_id, market_registry=market_registry
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            FuturesIdentityError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["identity_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "futures-fundamentals":
        try:
            identity_report = json.loads(
                Path(args.identity_path).read_text(encoding="utf-8")
            )
            evidence_input = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            market_structure_report = None
            if args.market_structure_path:
                market_structure_report = json.loads(
                    Path(args.market_structure_path).read_text(encoding="utf-8")
                )
            report = build_futures_fundamentals_report(
                identity_report,
                evidence_input,
                market_structure_report=market_structure_report,
                snapshot_id=args.snapshot_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            FuturesFundamentalsError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "futures-input-from-refresh":
        try:
            refresh_report = json.loads(
                Path(args.refresh_path).read_text(encoding="utf-8")
            )
            mapping = json.loads(
                Path(args.mapping_path).read_text(encoding="utf-8")
            )
            report = build_futures_fundamentals_input_from_refresh(
                refresh_report,
                mapping,
                input_id=args.input_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            FuturesRefreshMappingError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            report["report_id"], report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "futures-tracking":
        try:
            current_report = json.loads(
                Path(args.current_path).read_text(encoding="utf-8")
            )
            previous_report = None
            if args.previous_path:
                previous_report = json.loads(
                    Path(args.previous_path).read_text(encoding="utf-8")
                )
            report = build_futures_tracking_report(
                current_report,
                previous_report,
                as_of=args.as_of,
                tracking_id=args.tracking_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            FuturesTrackingError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            report["tracking_id"], report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "futures-company-exposure":
        try:
            futures_report = json.loads(
                Path(args.futures_report_path).read_text(encoding="utf-8")
            )
            exposure_input = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            product_profile_report = None
            if args.product_profile_path:
                product_profile_report = json.loads(
                    Path(args.product_profile_path).read_text(encoding="utf-8")
                )
            report = build_futures_company_exposure_report(
                futures_report,
                exposure_input,
                product_profile_report=product_profile_report,
                snapshot_id=args.snapshot_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            FuturesCompanyExposureError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "commodity-adapters":
        try:
            registry = CommodityAdapterRegistry.from_directory(args.directory)
            report = build_commodity_adapter_registry_report(
                registry, registry_id=args.registry_id
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            CommodityAdapterError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(
            report["registry_id"], report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "commodity-adapter-validate":
        try:
            registry = CommodityAdapterRegistry.from_directory(args.directory)
            adapter = registry.resolve(args.adapter)
            futures_report = None
            fundamentals_input = None
            if args.futures_report_path:
                futures_report = json.loads(
                    Path(args.futures_report_path).read_text(encoding="utf-8")
                )
            if args.fundamentals_path:
                fundamentals_input = json.loads(
                    Path(args.fundamentals_path).read_text(encoding="utf-8")
                )
            report = build_commodity_adapter_validation_report(
                adapter,
                futures_report=futures_report,
                fundamentals_input=fundamentals_input,
                validation_id=args.validation_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            CommodityAdapterError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(
            report["validation_id"], report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "research-assets":
        try:
            adapter = ResearchAssetAdapter(args.root)
            if args.mode == "discover":
                report = adapter.discover(
                    args.identifier, args.as_of, limit=args.limit
                )
                snapshot_id = args.snapshot_id or report["catalog_id"]
            else:
                if not args.input_path:
                    parser.error("research-assets modes other than discover require --input")
                if args.mode == "profile":
                    report = adapter.map_company_profile(args.input_path)
                elif args.mode == "artifact":
                    report = adapter.import_artifact(args.input_path)
                elif args.mode == "candidate-set":
                    report = adapter.import_candidate_set(args.input_path)
                elif args.mode == "scorecard":
                    report = adapter.import_scorecard(args.input_path)
                else:
                    if not args.authoritative:
                        parser.error("validate-identity requires --authoritative")
                    profile = adapter.map_company_profile(args.input_path)
                    authoritative = json.loads(
                        Path(args.authoritative_path).read_text(encoding="utf-8")
                    )
                    report = adapter.validate_identity(profile, authoritative)
                snapshot_id = args.snapshot_id or (
                    f"{args.mode}-{Path(args.input_path).stem}"
                )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ResearchAssetError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(snapshot_id, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "security-master":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            previous = None
            if args.previous_path:
                previous = json.loads(
                    Path(args.previous_path).read_text(encoding="utf-8")
                )
            report = build_security_master_snapshot(
                payload,
                previous_snapshot=previous,
                snapshot_id=args.snapshot_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            SecurityMasterError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["snapshot_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "security-master-validate":
        try:
            snapshot = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            report = validate_security_master_snapshot(snapshot)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            SecurityMasterError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(
            "security-master-validation-" + Path(args.input_path).stem,
            report,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "company-scope":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            report = build_company_scope_report(payload, scope_id=args.scope_id)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, CompanyScopeError) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["scope_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "company-scope-validate":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            report = validate_company_scope_report(payload)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, CompanyScopeError) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(
            "company-scope-validation-" + Path(args.input_path).stem, report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "market-data":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            market_registry = None
            if args.market_registry_path:
                market_registry = MarketRegistry.from_payload(
                    json.loads(Path(args.market_registry_path).read_text(encoding="utf-8"))
                )
            report = build_market_data_snapshot(
                payload, snapshot_id=args.snapshot_id, market_registry=market_registry
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, MarketDataError) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["snapshot_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "market-data-validate":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            market_registry = None
            if args.market_registry_path:
                market_registry = MarketRegistry.from_payload(
                    json.loads(Path(args.market_registry_path).read_text(encoding="utf-8"))
                )
            report = validate_market_data_snapshot(payload, market_registry=market_registry)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, MarketDataError) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(
            "market-data-validation-" + Path(args.input_path).stem, report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "market-registry":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            report = build_market_registry_report(payload)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, MarketRegistryError) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(
            report["registry_id"] + "-" + report["version"], report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "market-reference-validate":
        try:
            reference = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            registry = MarketRegistry.from_payload(
                json.loads(Path(args.registry_path).read_text(encoding="utf-8"))
            )
            report = validate_market_reference(reference, registry)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, MarketRegistryError) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(
            "market-reference-validation-" + Path(args.input_path).stem, report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "industry-adapters":
        try:
            registry = IndustryAdapterRegistry.from_directory(args.directory)
            report = build_industry_adapter_registry_report(
                registry, registry_id=args.registry_id
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            IndustryAdapterError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["registry_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "industry-profile":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            registry = IndustryAdapterRegistry.from_directory(args.directory)
            report = build_industry_profile_report(
                payload,
                registry,
                adapter_id=args.adapter_id,
                profile_id=args.profile_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            IndustryAdapterError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["profile_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "evidence-template":
        try:
            queue_report = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            template = build_manual_evidence_template(
                queue_report,
                fields=args.fields,
                profile=args.profile,
                company_ids=args.company_ids,
                snapshot_id=args.snapshot_id or Path(args.input_path).stem,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ManualEvidenceTemplateError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(
            template["template_id"], template
        )
        print(json.dumps(template, ensure_ascii=False, indent=2))
    elif args.command == "readiness":
        try:
            supplemental_report = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            report = build_researchability_report(
                supplemental_report,
                snapshot_id=args.snapshot_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ResearchabilityError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "quick-research":
        try:
            readiness_report = json.loads(
                Path(args.readiness_path).read_text(encoding="utf-8")
            )
            supplemental_report = json.loads(
                Path(args.supplemental_path).read_text(encoding="utf-8")
            )
            report = build_quick_research_report(
                readiness_report,
                supplemental_report,
                snapshot_id=args.snapshot_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            QuickResearchError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_artifact(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "external-ai":
        record = ExternalAIResearchRecord(
            provider=args.provider,
            question=args.question,
            answer=args.answer,
            model_label=args.model_label,
        )
        print(json.dumps(record.to_dict(), ensure_ascii=False, indent=2))
    elif args.command == "source-document":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            raw_content = None
            raw_uri = str(payload.get("raw_content_uri") or "")
            if args.raw_content_path:
                raw_path = Path(args.raw_content_path)
                raw_content = raw_path.read_bytes()
                raw_uri = str(raw_path)
            report = build_source_document(
                payload,
                raw_content=raw_content,
                raw_content_uri=raw_uri,
                document_id=args.document_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            EvidenceError,
            SnapshotExistsError,
        ) as error:
            parser.error(str(error))
        try:
            JsonSnapshotStore(Path(args.output_dir)).write_immutable(
                report["document_id"], report
            )
        except SnapshotExistsError as error:
            parser.error(str(error))
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "evidence":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            bundle = build_evidence_input_bundle(payload, bundle_id=args.bundle_id)
            if args.reconcile:
                priorities: dict[str, int] = {}
                for raw in args.source_priorities or []:
                    if "=" not in raw:
                        raise EvidenceError("--source-priority must use source=integer")
                    source_name, rank = raw.split("=", 1)
                    priorities[source_name.strip()] = int(rank)
                reconciliation = reconcile_evidence(
                    bundle,
                    group_by=tuple(args.group_by or ("subject_id", "metric", "period", "unit")),
                    source_priority=priorities,
                )
            else:
                reconciliation = None
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            EvidenceError,
            SnapshotExistsError,
        ) as error:
            parser.error(str(error))
        input_stem = Path(args.input_path).stem
        store = JsonSnapshotStore(Path(args.output_dir))
        try:
            store.write_immutable(f"evidence-bundle-{input_stem}", bundle)
            if reconciliation is not None:
                store.write_immutable(
                    f"evidence-reconciliation-{input_stem}", reconciliation
                )
        except SnapshotExistsError as error:
            parser.error(str(error))
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
    elif args.command == "evidence-from-refresh":
        try:
            refresh_report = json.loads(Path(args.refresh_path).read_text(encoding="utf-8"))
            records_payload = json.loads(Path(args.records_path).read_text(encoding="utf-8"))
            records = (
                records_payload.get("records")
                if isinstance(records_payload, Mapping)
                else records_payload
            )
            if not isinstance(records, list):
                raise RefreshEvidenceError("records input must be a list or an object with records")
            gate = build_refresh_evidence_gate(
                refresh_report,
                records,
                refresh_uri=args.refresh_uri or args.refresh_path,
                research_as_of=args.research_as_of,
                user_confirmed=args.user_confirmed,
                reviewer_id=args.reviewer_id,
                reviewed_at=args.reviewed_at,
                review_reason=args.review_reason,
                bundle_id=args.bundle_id,
                gate_id=args.gate_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            RefreshEvidenceError,
        ) as error:
            parser.error(str(error))
        gate_path = JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            gate["gate_id"], gate
        )
        bundle_path = ""
        if isinstance(gate.get("evidence_bundle"), Mapping):
            bundle = gate["evidence_bundle"]
            bundle_path = str(
                JsonSnapshotStore(Path(args.output_dir).parent / "evidence").write_immutable(
                    str(bundle["bundle_id"]), dict(bundle)
                )
            )
        print(
            json.dumps(
                {
                    "gate": str(gate_path),
                    "evidence_bundle": bundle_path,
                    "report": gate,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "validate-evidence-from-refresh":
        try:
            gate = validate_refresh_evidence_gate(
                json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            RefreshEvidenceError,
        ) as error:
            parser.error(str(error))
        print(json.dumps({"valid": True, "gate": gate}, ensure_ascii=False, indent=2))
    elif args.command == "research-request":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            report = build_research_request(payload, request_id=args.request_id)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ResearchExecutionError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(report["request_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "research-plan":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            differences: list[Mapping[str, Any]] = []
            if args.differences_path:
                differences_payload = json.loads(
                    Path(args.differences_path).read_text(encoding="utf-8")
                )
                differences = differences_payload.get("differences", []) if isinstance(differences_payload, Mapping) else differences_payload
                if not isinstance(differences, list):
                    raise ResearchExecutionError("differences input must be a list")
            report = build_research_execution_plan(
                payload,
                available_model=args.available_model,
                used_input_tokens=args.used_input_tokens,
                used_output_tokens=args.used_output_tokens,
                prior_differences=differences,
                plan_id=args.plan_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ResearchExecutionError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(report["plan_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "llm-run":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            report = build_llm_run(payload, llm_run_id=args.llm_run_id)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ResearchExecutionError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(report["llm_run_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "execution-audit":
        try:
            plan = json.loads(Path(args.plan_path).read_text(encoding="utf-8"))
            runs: list[Mapping[str, Any]] = []
            if args.runs_path:
                runs_payload = json.loads(Path(args.runs_path).read_text(encoding="utf-8"))
                runs = runs_payload.get("runs", []) if isinstance(runs_payload, Mapping) else runs_payload
                if not isinstance(runs, list):
                    raise ResearchExecutionError("runs input must be a list")
            report = build_execution_audit(plan, runs, audit_id=args.audit_id)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ResearchExecutionError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(report["audit_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "capability-matrix":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            report = build_capability_matrix(payload, matrix_id=args.matrix_id)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            CapabilityMatrixError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(report["matrix_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "capability-gap":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            report = build_capability_gap(payload, gap_id=args.gap_id)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            CapabilityMatrixError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(report["gap_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "opportunity-quality":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            report = build_opportunity_quality_report(payload, quality_id=args.quality_id)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            OpportunityQualityError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(report["quality_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "decision-lifecycle-event":
        try:
            snapshot = json.loads(Path(args.snapshot_path).read_text(encoding="utf-8"))
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            previous_events: list[Mapping[str, Any]] = []
            if args.events_path:
                existing = json.loads(Path(args.events_path).read_text(encoding="utf-8"))
                previous_events = existing.get("events", []) if isinstance(existing, Mapping) else existing
                if not isinstance(previous_events, list):
                    raise DecisionLifecycleError("events input must be a list")
            report = build_decision_lifecycle_event(
                snapshot,
                to_status=str(payload.get("to_status") or ""),
                changed_at=str(payload.get("changed_at") or ""),
                reason=str(payload.get("reason") or ""),
                evidence_ids=payload.get("evidence_ids") or [],
                attribution_id=str(payload.get("attribution_id") or ""),
                user_confirmed=payload.get("user_confirmed") is True,
                previous_events=previous_events,
                event_id=args.event_id,
            )
            all_events = [*previous_events, report]
            lifecycle_report = build_decision_lifecycle(snapshot, all_events)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            DecisionLifecycleError,
        ) as error:
            parser.error(str(error))
        store = JsonSnapshotStore(Path(args.output_dir))
        store.write_immutable(report["event_id"], report)
        store.write_immutable(lifecycle_report["lifecycle_id"], lifecycle_report)
        print(json.dumps(lifecycle_report, ensure_ascii=False, indent=2))
    elif args.command == "decision-lifecycle":
        try:
            snapshot = json.loads(Path(args.snapshot_path).read_text(encoding="utf-8"))
            events: list[Mapping[str, Any]] = []
            if args.events_path:
                existing = json.loads(Path(args.events_path).read_text(encoding="utf-8"))
                events = existing.get("events", []) if isinstance(existing, Mapping) else existing
                if not isinstance(events, list):
                    raise DecisionLifecycleError("events input must be a list")
            report = build_decision_lifecycle(
                snapshot, events, as_of=args.as_of, lifecycle_id=args.lifecycle_id
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            DecisionLifecycleError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(report["lifecycle_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "research-version":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            supplemental = None
            if args.supplemental_path:
                supplemental = json.loads(
                    Path(args.supplemental_path).read_text(encoding="utf-8")
                )
            evidence_bundle = None
            if args.evidence_bundle_path:
                evidence_bundle = json.loads(
                    Path(args.evidence_bundle_path).read_text(encoding="utf-8")
                )
            source_health_snapshot = None
            if args.source_health_path:
                source_health_snapshot = json.loads(
                    Path(args.source_health_path).read_text(encoding="utf-8")
                )
                validate_source_health_snapshot(source_health_snapshot)
            if source_health_snapshot is not None:
                payload = dict(payload)
                payload["source_health_snapshot_id"] = str(
                    source_health_snapshot["snapshot_id"]
                )
            if payload.get("schema_version") == "company-research-pipeline.v1":
                report = build_research_version_from_pipeline(
                    payload,
                    supplemental=supplemental,
                    evidence_bundle=evidence_bundle,
                    previous_version_id=args.previous_version_id,
                    execution_mode=args.execution_mode,
                    affected_modules=args.affected_modules or (),
                    version_id=args.version_id,
                )
            else:
                report = build_research_version(payload, version_id=args.version_id)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ResearchVersionError,
            SourceHealthError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            report["version_id"], report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "source-health":
        try:
            required: dict[str, list[str]] = {}
            for item in args.required_capabilities or ():
                subject_type, separator, capability = str(item).partition("=")
                if not separator or not subject_type.strip() or not capability.strip():
                    raise SourceHealthError(
                        "--required-capability must use subject_type=capability"
                    )
                required.setdefault(subject_type.strip(), []).append(capability.strip())
            report = build_source_health_snapshot(
                default_data_source_router(),
                subject_types=args.subject_types or (
                    "listed_company",
                    "industry",
                    "futures_contract",
                    "announcement",
                ),
                source_names=args.source_names or (),
                required_capabilities=required,
                checked_at=args.checked_at,
                snapshot_id=args.snapshot_id,
            )
        except (TypeError, ValueError, SourceHealthError) as error:
            parser.error(str(error))
        path = JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            report["snapshot_id"], report
        )
        print(
            json.dumps(
                {"snapshot": str(path), "health": report},
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "validate-source-health":
        try:
            snapshot = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            report = validate_source_health_snapshot(snapshot)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            SourceHealthError,
        ) as error:
            parser.error(str(error))
        print(
            json.dumps(
                {"valid": True, "health": report},
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "data-refresh":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            router = default_data_source_router()
            health = build_source_health_snapshot(
                router,
                checked_at=args.as_of,
                snapshot_id=f"source-health-refresh-{args.refresh_id or Path(args.input_path).stem}",
            )
            health_path = JsonSnapshotStore(Path(args.output_dir).parent / "source_health").write_immutable(
                health["snapshot_id"], health
            )
            report = build_data_source_refresh(
                payload,
                router,
                as_of=args.as_of,
                refresh_id=args.refresh_id,
                max_queries=args.max_queries,
                max_rows_per_query=args.max_rows_per_query,
                source_health_snapshot_id=health["snapshot_id"],
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            DataRefreshError,
            SourceHealthError,
        ) as error:
            parser.error(str(error))
        path = JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            report["refresh_id"], report
        )
        print(
            json.dumps(
                {
                    "refresh": str(path),
                    "source_health": str(health_path),
                    "report": report,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "validate-data-refresh":
        try:
            report = validate_data_source_refresh(
                json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            DataRefreshError,
        ) as error:
            parser.error(str(error))
        print(json.dumps({"valid": True, "refresh": report}, ensure_ascii=False, indent=2))
    elif args.command == "data-refresh-track":
        try:
            current = json.loads(Path(args.current_path).read_text(encoding="utf-8"))
            previous = (
                json.loads(Path(args.previous_path).read_text(encoding="utf-8"))
                if args.previous_path
                else None
            )
            report = build_data_refresh_tracking_report(
                current,
                previous,
                as_of=args.as_of,
                tracking_id=args.tracking_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            DataRefreshTrackingError,
        ) as error:
            parser.error(str(error))
        path = JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            report["tracking_id"], report
        )
        print(json.dumps({"tracking": str(path), "report": report}, ensure_ascii=False, indent=2))
    elif args.command == "validate-data-refresh-track":
        try:
            report = validate_data_refresh_tracking_report(
                json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            DataRefreshTrackingError,
        ) as error:
            parser.error(str(error))
        print(json.dumps({"valid": True, "tracking": report}, ensure_ascii=False, indent=2))
    elif args.command == "resolve-task":
        try:
            payload = (
                json.loads(Path(args.input_path).read_text(encoding="utf-8"))
                if args.input_path
                else args.input_text
            )
            security_master = (
                json.loads(Path(args.security_master_path).read_text(encoding="utf-8"))
                if args.security_master_path
                else None
            )
            commodity_definitions = []
            for commodity_path in args.commodity_config_paths or ():
                commodity_definition = json.loads(
                    Path(commodity_path).read_text(encoding="utf-8")
                )
                if not isinstance(commodity_definition, Mapping):
                    raise TaskResolutionError(
                        "commodity config must be a JSON object"
                    )
                commodity_definitions.append(commodity_definition)
            report = resolve_research_task(
                payload,
                task_type=args.task_type,
                subject_type=args.subject_type,
                research_as_of=args.research_as_of,
                requested_depth=args.requested_depth,
                simulation_mode=args.simulation_mode,
                risk_preference=args.risk_preference,
                confirmed=args.confirmed,
                task_id=args.task_id,
                security_master=security_master,
                commodity_definitions=commodity_definitions,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            TaskResolutionError,
        ) as error:
            parser.error(str(error))
        path = JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            report["task_id"], report
        )
        print(
            json.dumps(
                {"task": report, "task_path": str(path)},
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "validate-research-task":
        try:
            task = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            report = validate_research_task(task)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            TaskResolutionError,
        ) as error:
            parser.error(str(error))
        print(
            json.dumps(
                {"valid": True, "task": report},
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "third-party-components":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            report = build_component_registry(payload, registry_id=args.registry_id)
            if args.candidate_review_paths:
                candidate_reviews = [
                    json.loads(Path(path).read_text(encoding="utf-8"))
                    for path in args.candidate_review_paths
                ]
                report = validate_component_registry_links(report, candidate_reviews)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ThirdPartyComponentError,
        ) as error:
            parser.error(str(error))
        path = JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            report["registry_id"], report
        )
        print(json.dumps({"registry": report, "registry_path": str(path)}, ensure_ascii=False, indent=2))
    elif args.command == "third-party-health":
        try:
            registry = json.loads(Path(args.registry_path).read_text(encoding="utf-8"))
            validate_component_registry(registry)
            report = build_component_health_snapshot(
                registry,
                checked_at=args.checked_at,
                snapshot_id=args.snapshot_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ThirdPartyComponentError,
        ) as error:
            parser.error(str(error))
        path = JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            report["snapshot_id"], report
        )
        print(json.dumps({"health": report, "snapshot_path": str(path)}, ensure_ascii=False, indent=2))
    elif args.command == "validate-third-party-health":
        try:
            snapshot = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            report = validate_component_health_snapshot(snapshot)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ThirdPartyComponentError,
        ) as error:
            parser.error(str(error))
        print(json.dumps({"valid": True, "health": report}, ensure_ascii=False, indent=2))
    elif args.command == "third-party-candidate-review":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            report = build_candidate_review(payload, review_id=args.review_id)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ThirdPartyCandidateReviewError,
        ) as error:
            parser.error(str(error))
        path = JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            report["review_id"], report
        )
        print(json.dumps({"review": report, "review_path": str(path)}, ensure_ascii=False, indent=2))
    elif args.command == "third-party-candidate-review-event":
        try:
            review = json.loads(Path(args.review_path).read_text(encoding="utf-8"))
            event_input = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            previous_events = []
            if args.events_path:
                previous_events = json.loads(Path(args.events_path).read_text(encoding="utf-8"))
            if not isinstance(previous_events, list):
                raise ThirdPartyCandidateReviewError("events input must be a list")
            event = build_candidate_review_event(
                review,
                to_state=str(event_input.get("to_state") or ""),
                changed_at=str(event_input.get("changed_at") or ""),
                trigger=str(event_input.get("trigger") or ""),
                actor=str(event_input.get("actor") or ""),
                evidence_refs=event_input.get("evidence_refs") or (),
                field_updates=event_input.get("field_updates") or {},
                previous_events=previous_events,
                event_id=args.event_id,
            )
            projection = build_candidate_review_projection(
                review, [*previous_events, event], projection_id=args.projection_id
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ThirdPartyCandidateReviewError,
        ) as error:
            parser.error(str(error))
        store = JsonSnapshotStore(Path(args.output_dir))
        event_path = store.write_immutable(event["event_id"], event)
        projection_path = store.write_immutable(projection["projection_id"], projection)
        print(json.dumps({"event": event, "event_path": str(event_path), "projection": projection, "projection_path": str(projection_path)}, ensure_ascii=False, indent=2))
    elif args.command == "validate-third-party-candidate-review":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            schema = payload.get("schema_version") if isinstance(payload, Mapping) else ""
            if schema == "third-party-candidate-review.v1":
                report = validate_candidate_review(payload)
            elif schema == "third-party-candidate-review-event.v1":
                report = validate_candidate_review_event(payload)
            elif schema == "third-party-candidate-review-projection.v1":
                report = validate_candidate_review_projection(payload)
            else:
                raise ThirdPartyCandidateReviewError("unsupported candidate review schema")
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ThirdPartyCandidateReviewError,
        ) as error:
            parser.error(str(error))
        print(json.dumps({"valid": True, "candidate_review": report}, ensure_ascii=False, indent=2))
    elif args.command == "third-party-parse":
        try:
            raw_content = Path(args.input_path).read_bytes()
            report = parse_local_document(
                args.component,
                raw_content,
                document_id=args.document_id,
                research_as_of=args.research_as_of,
                source_uri=args.source_uri,
            )
            if args.result_id:
                report["result_id"] = args.result_id
        except (
            OSError,
            TypeError,
            ValueError,
            ThirdPartyComponentError,
        ) as error:
            parser.error(str(error))
        path = JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            report["result_id"], report
        )
        print(json.dumps({"parse": report, "result_path": str(path)}, ensure_ascii=False, indent=2))
    elif args.command == "performance-metrics":
        try:
            payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            report = build_performance_metrics_report(payload, result_id=args.result_id)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ThirdPartyComponentError,
        ) as error:
            parser.error(str(error))
        path = JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            report["result_id"], report
        )
        print(json.dumps({"performance": report, "result_path": str(path)}, ensure_ascii=False, indent=2))
    elif args.command == "validate-performance-metrics":
        try:
            report = validate_performance_metrics_report(
                json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ThirdPartyComponentError,
        ) as error:
            parser.error(str(error))
        print(json.dumps({"valid": True, "performance": report}, ensure_ascii=False, indent=2))
    elif args.command == "compare-research-versions":
        try:
            previous = json.loads(Path(args.previous_path).read_text(encoding="utf-8"))
            current = json.loads(Path(args.current_path).read_text(encoding="utf-8"))
            report = build_research_version_comparison(previous, current)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ResearchVersionError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            report["comparison_id"], report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "validate-research-version":
        try:
            version = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            report = validate_research_version(version)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ResearchVersionError,
        ) as error:
            parser.error(str(error))
        print(json.dumps({"valid": True, "version": report}, ensure_ascii=False, indent=2))
    elif args.command == "replay-research-version":
        try:
            version = json.loads(Path(args.version_path).read_text(encoding="utf-8"))
            artifacts: list[Mapping[str, Any]] = []
            if args.artifacts_path:
                artifacts_payload = json.loads(
                    Path(args.artifacts_path).read_text(encoding="utf-8")
                )
                artifacts = (
                    artifacts_payload.get("artifacts", [])
                    if isinstance(artifacts_payload, Mapping)
                    else artifacts_payload
                )
                if not isinstance(artifacts, list):
                    raise ResearchVersionError("artifacts input must be a list")
            report = build_research_version_replay(version, artifacts)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ResearchVersionError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write_immutable(
            report["replay_id"], report
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "web":
        try:
            run_web_server(
                host=args.host,
                port=args.port,
                data_root=args.data_root,
                commodity_directory=args.commodity_directory,
                web_root=args.web_root,
            )
        except (OSError, ValueError, WebApplicationError) as error:
            parser.error(str(error))
