"""Command line entry points for the first local-only prototype."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cross_validation import CrossSourceIndustryRadar
from .eastmoney import EastmoneyAPIError, EastmoneyIndustryRadar
from .external_ai import ExternalAIResearchRecord
from .industry_aliases import IndustryAliasError, IndustryAliasRegistry
from .models import CompanyCandidate, IndustryRadarSnapshot, IndustrySignal, IndustryState
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
    elif args.command == "external-ai":
        record = ExternalAIResearchRecord(
            provider=args.provider,
            question=args.question,
            answer=args.answer,
            model_label=args.model_label,
        )
        print(json.dumps(record.to_dict(), ensure_ascii=False, indent=2))
