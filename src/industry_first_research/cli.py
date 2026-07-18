"""Command line entry points for the first local-only prototype."""

from __future__ import annotations

import argparse
import json

from .external_ai import ExternalAIResearchRecord
from .models import CompanyCandidate, IndustryRadarSnapshot, IndustrySignal, IndustryState
from .pipeline import (
    InMemoryCompanyPool,
    InMemoryRadar,
    IndustryFirstDiscovery,
    PassThroughCompanyData,
    PassThroughDeepResearch,
    current_as_of,
)


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
    external = subparsers.add_parser("external-ai", help="normalise a pasted web AI answer")
    external.add_argument("--provider", required=True)
    external.add_argument("--question", required=True)
    external.add_argument("--answer", required=True)
    external.add_argument("--model", default="unknown", dest="model_label")
    args = parser.parse_args()

    if args.command == "demo":
        print(json.dumps(demo(), ensure_ascii=False, indent=2))
    elif args.command == "external-ai":
        record = ExternalAIResearchRecord(
            provider=args.provider,
            question=args.question,
            answer=args.answer,
            model_label=args.model_label,
        )
        print(json.dumps(record.to_dict(), ensure_ascii=False, indent=2))
