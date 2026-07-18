"""Command line entry points for the first local-only prototype."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .company_research import CompanyResearchAssembler, snapshot_from_config
from .config import (
    candidates_from_config,
    load_company_config,
    load_config,
    radar_from_config,
    source_documents,
)
from .data_sources import default_data_source_router
from .external_ai import ExternalAIResearchRecord
from .local_assets import ConfigCompanyPool, LocalAssetDataProvider, LocalResearchAssetCatalog
from .models import CompanyCandidate, IndustryRadarSnapshot, IndustrySignal, IndustryState
from .pipeline import (
    InMemoryCompanyPool,
    InMemoryRadar,
    IndustryFirstDiscovery,
    PassThroughCompanyData,
    PassThroughDeepResearch,
    current_as_of,
)
from .report import render_scan_html, render_scan_markdown
from .storage import JsonSnapshotStore


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
    company = subparsers.add_parser(
        "company", help="collect a bounded company research snapshot"
    )
    company.add_argument("--config", required=True, help="path to a company JSON config")
    company.add_argument(
        "--snapshot-dir",
        default="artifacts/company-snapshots",
        help="directory for the JSON company snapshot",
    )
    industry = subparsers.add_parser(
        "industry", help="run an industry-first scan from a local industry config"
    )
    industry.add_argument("--config", required=True, help="path to an industry JSON config")
    industry.add_argument("--output", help="write the Markdown report to this path")
    industry.add_argument("--html-output", help="write the HTML report to this path")
    industry.add_argument(
        "--snapshot-dir",
        default="artifacts/snapshots",
        help="directory for the JSON scan snapshot",
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
    elif args.command == "external-ai":
        record = ExternalAIResearchRecord(
            provider=args.provider,
            question=args.question,
            answer=args.answer,
            model_label=args.model_label,
        )
        print(json.dumps(record.to_dict(), ensure_ascii=False, indent=2))
