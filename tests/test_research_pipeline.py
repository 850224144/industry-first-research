import pytest

from industry_first_research.candidate_queue import build_candidate_queue
from industry_first_research.company_screen import screen_company_candidates
from industry_first_research.industry_aliases import IndustryAliasRegistry
from industry_first_research.models import CompanyCandidate
from industry_first_research.research_pipeline import build_research_pipeline
from industry_first_research.supplemental_evidence import (
    build_supplemental_evidence_report,
)


def supplemental_report(records=None):
    aliases = IndustryAliasRegistry.from_dict(
        {
            "schema_version": "industry-aliases.v1",
            "mappings": [
                {
                    "canonical_id": "baijiu",
                    "canonical_name": "白酒",
                    "aliases": {
                        "tonghuashun": ["白酒"],
                        "tonghuashun_company_profile": ["白酒Ⅱ"],
                    },
                    "note": "test mapping",
                }
            ],
        }
    )
    screen = screen_company_candidates(
        [
            CompanyCandidate(
                "600519",
                "贵州茅台",
                "881273",
                source="https://example.test/company",
                light_profile={
                    "status": "VERIFIED",
                    "legal_name": "贵州茅台",
                    "main_business": "白酒生产与销售",
                    "reported_industry": "白酒Ⅱ",
                    "listing_market": "上海证券交易所",
                    "source": "https://example.test/profile",
                    "as_of": "2026-07-20",
                    "available_fields": [
                        "legal_name",
                        "main_business",
                        "reported_industry",
                        "listing_market",
                    ],
                },
            )
        ],
        expected_industry="白酒",
        input_snapshot_id="pool-001",
        input_as_of="2026-07-20",
        input_source={"provider": "tonghuashun_company_pool"},
        industry_alias_registry=aliases,
    )
    queue = build_candidate_queue(screen)
    return build_supplemental_evidence_report(queue, records or [])


def test_pipeline_runs_all_stages_and_blocks_without_deep_evidence():
    report = build_research_pipeline(supplemental_report())

    assert report["schema_version"] == "company-research-pipeline.v1"
    assert report["candidate_count"] == 1
    assert report["final_state"] == "REVIEW"
    assert list(report["stages"]) == [
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
    ]
    assert report["stages"]["product_profile"]["profile_state_counts"] == {
        "BLOCKED": 1
    }
    assert report["stages"]["demand_transmission"]["transmission_state_counts"] == {
        "BLOCKED": 1
    }
    assert report["stages"]["research_report"]["items"][0]["candidate_state"] == "WATCH"
    assert report["policy"]["investment_conclusion"] is False


def test_pipeline_rejects_wrong_input_schema():
    with pytest.raises(ValueError, match="supplemental-evidence.v1"):
        build_research_pipeline({"schema_version": "other", "items": []})


def test_pipeline_records_unified_evidence_bundle_cutoff_and_manifest():
    bundle = {
        "schema_version": "evidence-bundle.v1",
        "bundle_id": "bundle-001",
        "research_as_of": "2026-07-21",
        "evidence": [],
        "evidence_ids": ["ev-1", "ev-2"],
        "excluded_future_evidence_ids": [],
        "unknown_temporal_evidence_ids": [],
        "status": "READY",
        "cutoff_validation": {},
    }
    report = build_research_pipeline(
        supplemental_report(), evidence_bundle=bundle
    )

    assert report["evidence_bundle_id"] == "bundle-001"
    assert report["evidence_bundle_review"] == "SUPPLIED"
    assert report["evidence_cutoff_status"] == "SAFE"
    assert len(report["evidence_manifest_hash"]) == 64


def test_pipeline_accepts_product_profit_bridge_as_optional_reference_stage():
    bridge = {
        "schema_version": "product-profit-bridge.v1",
        "report_id": "product-profit-bridge-001",
        "as_of": "2026-07-21",
        "items": [],
        "investment_conclusion": False,
    }
    report = build_research_pipeline(
        supplemental_report(),
        product_profit_bridge_report=bridge,
    )

    assert report["product_profit_bridge_review"] == "SUPPLIED"
    assert report["product_profit_bridge_id"] == "product-profit-bridge-001"
    assert report["stages"]["product_profit_bridge"] is bridge
    assert report["policy"]["product_profit_bridge_is_reference_only"] is True


def test_pipeline_rejects_wrong_evidence_bundle_schema():
    with pytest.raises(ValueError, match="evidence-bundle.v1"):
        build_research_pipeline(
            supplemental_report(),
            evidence_bundle={"schema_version": "other"},
        )
