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


def test_demand_acceleration_requires_independent_industry_and_company_evidence():
    snapshot = IndustryRadarSnapshot(
        industry_id="demand",
        display_name="需求加速行业",
        as_of="2026-07-18",
        state=IndustryState.INFLECTION_CANDIDATE,
        evidence_completeness="CROSS_VALIDATED",
        opportunity_types=("demand_acceleration",),
        signals=(
            IndustrySignal("demand_growth", "accelerating", "2026-07-18", "test", "VERIFIED"),
            IndustrySignal("order_growth", "improving", "2026-07-18", "test", "VERIFIED"),
            IndustrySignal("shipment_growth", "rising", "2026-07-18", "test", "VERIFIED"),
        ),
    )
    industry = assess_industry_opportunities(snapshot)["demand_acceleration"]
    assert industry["status"] == "PASS"
    assert industry["verified_signal_groups"] == ["demand", "orders", "shipments"]

    candidate = CompanyCandidate(
        "000001.SZ",
        "需求验证公司",
        "demand",
        metadata={
            "screening_inputs": {
                "demand_acceleration": {
                    "customer_validation": "confirmed",
                    "revenue_validation": "improving",
                    "profit_validation": "improving",
                }
            }
        },
    )
    company = assess_company_opportunities(candidate, {"demand_acceleration": industry})[
        "demand_acceleration"
    ]
    assert company["status"] == "PASS"


def test_bottleneck_pricing_requires_scarcity_pricing_and_barrier():
    snapshot = IndustryRadarSnapshot(
        industry_id="bottleneck",
        display_name="瓶颈行业",
        as_of="2026-07-18",
        state=IndustryState.CLEARING,
        evidence_completeness="VERIFIED",
        opportunity_types=("bottleneck_pricing",),
        signals=(
            IndustrySignal("lead_time", "extended", "2026-07-18", "test", "VERIFIED"),
            IndustrySignal("inventory", "low", "2026-07-18", "test", "VERIFIED"),
            IndustrySignal("spot_price", "rising", "2026-07-18", "test", "VERIFIED"),
            IndustrySignal("substitution_difficulty", "difficult", "2026-07-18", "test", "VERIFIED"),
        ),
    )
    industry = assess_industry_opportunities(snapshot)["bottleneck_pricing"]
    assert industry["status"] == "PASS"
    assert set(industry["positive_signal_groups"]) == {"scarcity", "pricing", "barrier"}

    candidate = CompanyCandidate(
        "000002.SZ",
        "瓶颈受益公司",
        "bottleneck",
        metadata={
            "screening_inputs": {
                "bottleneck_pricing": {
                    "product_criticality": "high",
                    "pricing_power": "strong",
                    "revenue_validation": "confirmed",
                }
            }
        },
    )
    company = assess_company_opportunities(candidate, {"bottleneck_pricing": industry})[
        "bottleneck_pricing"
    ]
    assert company["status"] == "PASS"


def test_price_only_cannot_create_bottleneck_opportunity():
    snapshot = IndustryRadarSnapshot(
        industry_id="price-only",
        display_name="只有价格信号",
        as_of="2026-07-18",
        state=IndustryState.INFLECTION_CANDIDATE,
        evidence_completeness="CROSS_VALIDATED",
        opportunity_types=("bottleneck_pricing",),
        signals=(
            IndustrySignal("spot_price", "rising", "2026-07-18", "test", "VERIFIED"),
        ),
    )
    assessment = assess_industry_opportunities(snapshot)["bottleneck_pricing"]
    assert assessment["status"] == "INSUFFICIENT"
    assert "供给紧张" in " ".join(assessment["missing"])


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
    assert inspected["available"] is False
    assert inspected["parse_status"] == "MISSING"


def test_empty_and_outside_assets_are_not_available(tmp_path: Path):
    empty = tmp_path / "empty.md"
    empty.touch()
    outside = tmp_path.parent / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")

    empty_status, outside_status = LocalResearchAssetCatalog(tmp_path).inspect(
        ["empty.md", str(outside)]
    )

    assert empty_status["parse_status"] == "EMPTY"
    assert empty_status["available"] is False
    assert outside_status["parse_status"] == "OUTSIDE_PROJECT"
    assert outside_status["available"] is False
