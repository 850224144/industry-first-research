from pathlib import Path

from industry_first_research.local_assets import LocalResearchAssetCatalog
from industry_first_research.models import (
    CompanyCandidate,
    IndustryRadarSnapshot,
    IndustrySignal,
    IndustryState,
)
from industry_first_research.screening import (
    assess_company_opportunities,
    assess_industry_opportunities,
)


def test_selected_industry_without_company_pool_is_empty(tmp_path: Path):
    from industry_first_research.pipeline import (
        InMemoryCompanyPool,
        InMemoryRadar,
        IndustryFirstDiscovery,
    )

    snapshot = IndustryRadarSnapshot(
        industry_id="empty",
        display_name="空行业",
        as_of="2026-07-18",
        state=IndustryState.INFLECTION_CANDIDATE,
        opportunity_types=("cycle_reversal",),
    )
    # Keep the provider contract explicit without introducing a test-only adapter.
    class EmptyData:
        def enrich(self, candidates, tier):
            return candidates

    result = IndustryFirstDiscovery(
        InMemoryRadar([snapshot]), InMemoryCompanyPool({}), EmptyData()
    ).run("2026-07-18")
    assert result.empty_result is True
    assert result.company_pools == {"empty": []}


def test_opportunity_rules_are_conservative_and_explainable():
    snapshot = IndustryRadarSnapshot(
        industry_id="cycle",
        display_name="周期行业",
        as_of="2026-07-18",
        state=IndustryState.INFLECTION_CANDIDATE,
        evidence_completeness="CROSS_VALIDATED",
        opportunity_types=("cycle_reversal", "quality_repair"),
        signals=(
            IndustrySignal("supply_exit", "visible", "2026-07-18", "test", "VERIFIED"),
        ),
    )
    industry_assessments = assess_industry_opportunities(snapshot)
    assert industry_assessments["cycle_reversal"]["status"] == "WATCH"
    assert "库存" in " ".join(industry_assessments["cycle_reversal"]["missing"])
    assert industry_assessments["quality_repair"]["status"] == "SCOPE_ONLY"

    candidate = CompanyCandidate(
        "000001.SZ",
        "示例公司",
        "cycle",
        metadata={"screening_inputs": {"survival": "strong"}},
    )
    company_assessments = assess_company_opportunities(candidate, industry_assessments)
    assert company_assessments["cycle_reversal"]["status"] == "WATCH"
    assert company_assessments["quality_repair"]["status"] == "INSUFFICIENT"


def test_asset_catalog_records_hash_and_candidate_sections(tmp_path: Path):
    asset = tmp_path / "research.md"
    asset.write_text("# 商业模式\n\n## 产品\n\n## 风险\n", encoding="utf-8")
    inspected = LocalResearchAssetCatalog(tmp_path).inspect(["research.md"])[0]
    assert inspected["exists"] is True
    assert inspected["parse_status"] == "PARSED"
    assert len(inspected["sha256"]) == 64
    assert {item["name"] for item in inspected["fields"]} >= {"商业模式", "产品", "风险"}


def test_missing_asset_is_explicit(tmp_path: Path):
    inspected = LocalResearchAssetCatalog(tmp_path).inspect(["missing.md"])[0]
    assert inspected["exists"] is False
    assert inspected["parse_status"] == "MISSING"
