import json
from pathlib import Path

import pytest

from industry_first_research.research_assets import (
    DIRECT_REUSE,
    REFERENCE_ONLY,
    REUSE_WITH_CHECK,
    ResearchAssetCompanyPool,
    ResearchAssetAdapter,
    ResearchAssetError,
)
from industry_first_research.models import IndustryRadarSnapshot, IndustryState


ROOT = Path(__file__).parents[1]


def test_discover_keeps_hash_version_and_cutoff_exclusions():
    adapter = ResearchAssetAdapter(ROOT)

    result = adapter.discover("NVIDIA", "2026-07-11", limit=20)

    assert result["schema_version"] == "research-asset-catalog.v1"
    assert result["asset_count"] >= 1
    assert result["excluded_count"] >= 1
    excluded = result["excluded_items"][0]
    assert excluded["source_project"] == "luopan"
    assert len(excluded["file_hash"]) == 64
    assert excluded["temporal_status"] == "AFTER_CUTOFF"
    assert excluded["exclusion_reason"] == "RESEARCH_DATE_AFTER_CUTOFF"
    assert excluded["source_version"] == "1a8075059b9ca4d1750f3cb24e191aa7ba1c770c"


def test_map_company_profile_only_prefills_explicit_fields():
    adapter = ResearchAssetAdapter(ROOT)
    asset = ROOT / "vendor/luopan/review-output/NVIDIA-公司调研-2026-07-12.json"

    profile = adapter.map_company_profile(asset)

    assert profile["company_id"] == "NVDA"
    assert profile["display_name"] == "NVIDIA"
    assert profile["fields"]["company_id"]["reuse_strategy"] == DIRECT_REUSE
    assert "industry" not in profile["fields"]
    assert profile["fields"]["company_name"]["reuse_strategy"] == DIRECT_REUSE
    assert profile["excluded_claims"]["target_price"] == REFERENCE_ONLY
    assert profile["investment_conclusion"] is False
    assert profile["policy"]["external_claims_not_verified"] is True


def test_markdown_filename_subject_is_not_direct_identity():
    adapter = ResearchAssetAdapter(ROOT)

    profile = adapter.map_company_profile(
        ROOT / "vendor/ai-berkshire/reports/英维克/英维克投资研究报告-20260706.md"
    )

    assert profile["fields"]["company_name"]["reuse_strategy"] == REUSE_WITH_CHECK
    assert profile["validation_status"] == "PENDING"


def test_validate_identity_respects_cutoff_and_records_conflict():
    adapter = ResearchAssetAdapter(ROOT)
    profile = adapter.map_company_profile(
        ROOT / "vendor/luopan/review-output/NVIDIA-公司调研-2026-07-12.json"
    )
    result = adapter.validate_identity(
        profile,
        [
            {
                "source_id": "official-nvda",
                "company_id": "NVDA",
                "company_name": "NVIDIA",
                "market": "NASDAQ",
                "as_of": "2026-07-10",
            },
            {
                "source_id": "future-conflict",
                "company_id": "OTHER",
                "company_name": "NVIDIA",
                "as_of": "2026-07-13",
            },
        ],
    )

    assert result["validation_status"] == "VERIFIED"
    assert result["field_validation"]["company_id"]["status"] == "VERIFIED"
    assert result["temporal_excluded_source_ids"] == ["future-conflict"]
    assert result["claims_are_verified"] is True


def test_candidate_set_is_bounded_and_never_security_master():
    adapter = ResearchAssetAdapter(ROOT)

    result = adapter.import_candidate_set(
        ROOT / "vendor/ai-berkshire/data/watchlist.json"
    )

    assert result["candidate_count"] == 25
    assert result["scope"]["complete"] is False
    assert result["scope"]["may_enter_security_master"] is False
    assert result["reuse_strategy"] == REUSE_WITH_CHECK
    assert result["investment_conclusion"] is False


def test_scorecard_does_not_infer_scores_from_report_prose():
    adapter = ResearchAssetAdapter(ROOT)

    result = adapter.import_scorecard(
        ROOT / "vendor/luopan/review-output/NVIDIA-公司调研-2026-07-12.json"
    )

    assert result["status"] == "NOT_AVAILABLE"
    assert result["items"] == []
    assert "NO_STRUCTURED_SCORECARD" in result["missing_items"]
    assert result["final_rating"] is False


def test_artifact_import_is_manifest_only():
    adapter = ResearchAssetAdapter(ROOT)

    result = adapter.import_artifact(
        ROOT / "vendor/ai-berkshire/reports/英维克/英维克投资研究报告-20260706.md"
    )

    assert result["reuse_strategy"] == REFERENCE_ONLY
    assert result["claims_are_verified"] is False
    assert result["content_copied"] is False
    assert len(result["file_hash"]) == 64


def test_method_guides_are_reused_as_method_not_as_external_conclusions():
    adapter = ResearchAssetAdapter(ROOT)

    result = adapter.import_artifact(
        ROOT / "vendor/ai-berkshire/skills/industry-funnel.md"
    )

    assert result["reuse_strategy"] == "METHOD_REUSE"
    assert result["claims_are_verified"] is False


def test_invalid_asset_and_invalid_cutoff_are_explicit():
    adapter = ResearchAssetAdapter(ROOT)

    with pytest.raises(ResearchAssetError, match="does not exist"):
        adapter.import_artifact("vendor/luopan/missing.json")
    with pytest.raises(ResearchAssetError, match="invalid as_of"):
        adapter.discover("NVIDIA", "not-a-date")


def test_adapter_accepts_vendor_and_single_project_roots():
    vendor_adapter = ResearchAssetAdapter(ROOT / "vendor")
    project_adapter = ResearchAssetAdapter(ROOT / "vendor/luopan")

    assert vendor_adapter.map_company_profile(
        "vendor/luopan/review-output/NVIDIA-公司调研-2026-07-12.json"
    )["company_id"] == "NVDA"
    assert project_adapter.map_company_profile(
        "review-output/NVIDIA-公司调研-2026-07-12.json"
    )["company_id"] == "NVDA"


def test_research_asset_company_pool_reuses_supported_candidate_set_without_fallback():
    imported = ResearchAssetAdapter(ROOT).import_candidate_set(
        ROOT / "vendor/ai-berkshire/data/watchlist.json"
    )
    pool = ResearchAssetCompanyPool([imported])
    industry = IndustryRadarSnapshot(
        industry_id="consumer", display_name="消费", as_of="2026-07-23", state=IndustryState.CLEARING
    )

    candidates = pool.candidates(industry, 10)

    assert [item.company_id for item in candidates] == [
        "0700.HK",
        "9888.HK",
        "1024.HK",
        "9992.HK",
    ]
    assert pool.metadata()["provider"] == "research_assets"
    assert pool.metadata()["rejected_count"] > 0


def test_research_asset_company_pool_filters_non_initial_markets():
    imported = {
        "schema_version": "research-asset-candidate-set.v1",
        "import_id": "candidate-set-cn",
        "source_project": "luopan",
        "source_path": "candidate.json",
        "reuse_strategy": "REUSE_WITH_CHECK",
        "scope": {"bounded": True, "complete": False},
        "candidates": [
            {"candidate_id": "600519.SH", "display_name": "贵州茅台"},
            {"candidate_id": "NVDA", "display_name": "NVIDIA"},
            {"candidate_id": "0700.HK", "display_name": "腾讯控股"},
        ],
    }
    pool = ResearchAssetCompanyPool([imported])
    industry = IndustryRadarSnapshot(
        industry_id="consumer", display_name="消费", as_of="2026-07-23", state=IndustryState.CLEARING
    )

    candidates = pool.candidates(industry, 10)

    assert [item.company_id for item in candidates] == ["600519.SH", "0700.HK"]
    assert pool.metadata()["rejected"][0]["reason"] == "INITIAL_MARKET_OUT_OF_SCOPE"
