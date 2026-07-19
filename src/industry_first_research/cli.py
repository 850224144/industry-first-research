"""Command line entry points for the first local-only prototype."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cross_validation import CrossSourceIndustryRadar
from .company_screen import CompanyScreenError, screen_company_candidates
from .candidate_queue import CandidateQueueError, build_candidate_queue
from .supplemental_evidence import (
    SupplementalEvidenceError,
    build_supplemental_evidence_report,
)
from .researchability import ResearchabilityError, build_researchability_report
from .quick_research import QuickResearchError, build_quick_research_report
from .manual_evidence import (
    ManualEvidenceTemplateError,
    build_manual_evidence_template,
)
from .eastmoney import EastmoneyAPIError, EastmoneyIndustryRadar
from .external_ai import ExternalAIResearchRecord
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
        "light_profile": dict(item.get("light_profile") or {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="industry-first-research")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("demo", help="run the local-only industry-first demo")
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
    evidence_template = subparsers.add_parser(
        "evidence-template",
        help="create blank records for manually verified company evidence",
    )
    evidence_template.add_argument("--input", required=True, dest="input_path")
    evidence_template.add_argument(
        "--field", action="append", default=None, dest="fields"
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
                TonghuashunLightCompanyData().enrich(candidates, CompanyDataTier.LIGHT)
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
            EastmoneyIndustryRadar(page_size=args.company_pool_size),
            TonghuashunIndustryRadar(page_size=args.company_pool_size),
            primary_name="eastmoney",
            secondary_name="tonghuashun",
            alias_registry=alias_registry,
        )
        discovery = IndustryFirstDiscovery(
            radar_provider,
            TonghuashunCompanyPool(page_size=args.company_pool_size),
            TonghuashunLightCompanyData(),
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
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, CompanyScreenError) as error:
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
    elif args.command == "evidence-template":
        try:
            queue_report = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
            template = build_manual_evidence_template(
                queue_report,
                fields=args.fields or ("listing_market",),
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
