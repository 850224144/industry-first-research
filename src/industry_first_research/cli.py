"""Command line entry points for the first local-only prototype."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
from pathlib import Path

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
from .adversarial_review import (
    AdversarialReviewError,
    build_adversarial_review_report,
)
from .research_report import ResearchReportError, build_research_report
from .research_pipeline import build_research_pipeline
from .incremental_update import IncrementalUpdateError, build_incremental_update
from .scheduler import (
    SchedulerError,
    build_default_schedule,
    build_scheduler_plan,
    build_scheduler_state,
)
from .decision_snapshot import DecisionSnapshotError, build_decision_snapshot
from .attribution import AttributionError, build_attribution_report
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
from .storage import JsonSnapshotStore
from .trend import RadarTrendError, build_trend_report, write_trend_report
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
    product_profile.add_argument(
        "--required-field", action="append", default=None, dest="required_fields"
    )
    product_profile.add_argument(
        "--output-dir", default="data/company_product_profiles", dest="output_dir"
    )
    product_profile.add_argument("--snapshot-id", default="", dest="snapshot_id")
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
    market_structure.add_argument(
        "--output-dir", default="data/market_structure", dest="output_dir"
    )
    market_structure.add_argument("--snapshot-id", default="", dest="snapshot_id")
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
        "--output-dir", default="data/company_incremental_updates", dest="output_dir"
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
    attribution = subparsers.add_parser(
        "attribution",
        help="compare a locked simulation snapshot with its fixed benchmark",
    )
    attribution.add_argument("--input", required=True, dest="input_path")
    attribution.add_argument("--outcome", required=True, dest="outcome_path")
    attribution.add_argument("--closed-at", default="", dest="closed_at")
    attribution.add_argument(
        "--output-dir", default="data/attribution_results", dest="output_dir"
    )
    attribution.add_argument("--attribution-id", default="", dest="attribution_id")
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
        "--alias-file",
        default="docs/industry_aliases.v1.json",
        dest="alias_file",
    )
    external = subparsers.add_parser("external-ai", help="normalise a pasted web AI answer")
    external.add_argument("--provider", required=True)
    external.add_argument("--question", required=True)
    external.add_argument("--answer", required=True)
    external.add_argument("--model", default="unknown", dest="model_label")
    args = parser.parse_args()

    if args.command == "demo":
        print(json.dumps(demo(), ensure_ascii=False, indent=2))
    elif args.command == "company":
        config = load_company_config(args.config)
        snapshot = CompanyResearchAssembler(default_data_source_router()).collect(
            snapshot_from_config(config)
        )
        snapshot_path = JsonSnapshotStore(args.snapshot_dir).write(
            f"company-{snapshot.company_id.replace('.', '-')}-{snapshot.as_of}",
            {
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
        snapshot_path = JsonSnapshotStore(args.snapshot_dir).write(
            f"radar-{collection.snapshot.industry_id}-{collection.snapshot.as_of}",
            {
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
        scan = IndustryFirstDiscovery(
            InMemoryRadar([radar_from_config(config)]),
            ConfigCompanyPool(
                candidates_from_config(config),
                catalog=LocalResearchAssetCatalog(project_root),
            ),
            LocalAssetDataProvider(),
        ).run(config["as_of"])
        snapshot_path = JsonSnapshotStore(args.snapshot_dir).write(
            scan.scan_id,
            {
                "scan": scan.to_dict(),
                "industry": config,
                "execution_mode": "LOCAL_ASSET_REUSE",
            },
        )
        report = render_scan_markdown(scan, config, source_documents(config))
        html_report = render_scan_html(scan, config, source_documents(config))
        if args.output:
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(report, encoding="utf-8")
            result = {"report": str(target), "snapshot": str(snapshot_path)}
            if args.html_output:
                html_target = Path(args.html_output)
                html_target.parent.mkdir(parents=True, exist_ok=True)
                html_target.write_text(html_report, encoding="utf-8")
                result["html_report"] = str(html_target)
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
        store.write(f"{snapshot_prefix}-{as_of}", payload)
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
        JsonSnapshotStore(Path(args.output_dir)).write(
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
        discovery = IndustryFirstDiscovery(
            radar_provider,
            TonghuashunCompanyPool(page_size=args.company_pool_size),
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
                "provider": "tonghuashun_light",
                "tier": "LIGHT",
                "read_only": True,
                "execution_enabled": False,
                "status_counts": _light_profile_status_counts(scan),
            },
        }
        JsonSnapshotStore(Path(args.output_dir)).write(
            f"cross-discovery-{as_of}", payload
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
        JsonSnapshotStore(Path(args.output_dir)).write(report_id, report)
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
        JsonSnapshotStore(Path(args.output_dir)).write(queue_id, queue_report)
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
        JsonSnapshotStore(Path(args.output_dir)).write(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "product-profile":
        try:
            supplemental_report = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            product_profile_kwargs = {"snapshot_id": args.snapshot_id}
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
        JsonSnapshotStore(Path(args.output_dir)).write(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
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
        JsonSnapshotStore(Path(args.output_dir)).write(report["report_id"], report)
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
        JsonSnapshotStore(Path(args.output_dir)).write(report["report_id"], report)
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
        JsonSnapshotStore(Path(args.output_dir)).write(report["report_id"], report)
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
        JsonSnapshotStore(Path(args.output_dir)).write(report["report_id"], report)
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
        JsonSnapshotStore(Path(args.output_dir)).write(report["report_id"], report)
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
        JsonSnapshotStore(Path(args.output_dir)).write(report["report_id"], report)
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
        JsonSnapshotStore(Path(args.output_dir)).write(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "market-structure":
        try:
            market_structure_input = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            report = build_market_structure_report(
                market_structure_input,
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
        JsonSnapshotStore(Path(args.output_dir)).write(report["report_id"], report)
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
        JsonSnapshotStore(Path(args.output_dir)).write(report["report_id"], report)
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
        JsonSnapshotStore(Path(args.output_dir)).write(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
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
            report = build_research_pipeline(
                supplemental_report,
                market_structure_report=market_structure_report,
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
        JsonSnapshotStore(Path(args.output_dir)).write(report["pipeline_id"], report)
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
            report = build_incremental_update(
                previous_pipeline,
                previous_supplemental,
                evidence_records,
                as_of=args.as_of,
                snapshot_id=args.snapshot_id,
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
        JsonSnapshotStore(Path(args.output_dir)).write(report["update_id"], report)
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
    elif args.command == "decision-snapshot":
        try:
            research_report = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            decision = json.loads(
                Path(args.decision_path).read_text(encoding="utf-8")
            )
            report = build_decision_snapshot(
                research_report,
                decision,
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
        JsonSnapshotStore(Path(args.output_dir)).write(report["snapshot_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "attribution":
        try:
            decision_snapshot = json.loads(
                Path(args.input_path).read_text(encoding="utf-8")
            )
            outcome_input = json.loads(
                Path(args.outcome_path).read_text(encoding="utf-8")
            )
            report = build_attribution_report(
                decision_snapshot,
                outcome_input,
                closed_at=args.closed_at,
                attribution_id=args.attribution_id,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            AttributionError,
        ) as error:
            parser.error(str(error))
        JsonSnapshotStore(Path(args.output_dir)).write(
            report["attribution_id"], report
        )
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
        JsonSnapshotStore(Path(args.output_dir)).write(
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
        JsonSnapshotStore(Path(args.output_dir)).write(report["report_id"], report)
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
        JsonSnapshotStore(Path(args.output_dir)).write(report["report_id"], report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "external-ai":
        record = ExternalAIResearchRecord(
            provider=args.provider,
            question=args.question,
            answer=args.answer,
            model_label=args.model_label,
        )
        print(json.dumps(record.to_dict(), ensure_ascii=False, indent=2))
