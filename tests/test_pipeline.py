from industry_first_research.models import (
    CompanyCandidate,
    CompanyDataTier,
    IndustryRadarSnapshot,
    IndustrySignal,
    IndustryState,
    ResourcePolicy,
)
from industry_first_research.pipeline import (
    InMemoryCompanyPool,
    InMemoryRadar,
    IndustryFirstDiscovery,
    PassThroughCompanyData,
    PassThroughDeepResearch,
)


def snapshot(industry_id: str, state: IndustryState) -> IndustryRadarSnapshot:
    return IndustryRadarSnapshot(
        industry_id=industry_id,
        display_name=industry_id,
        as_of="2026-07-18",
        state=state,
        evidence_completeness="CROSS_VALIDATED",
    )


def candidates(industry_id: str, count: int) -> list[CompanyCandidate]:
    return [
        CompanyCandidate(f"{industry_id}-{index}", f"公司 {index}", industry_id)
        for index in range(count)
    ]


def test_discovery_selects_industry_before_loading_company_data():
    radar = InMemoryRadar(
        [
            snapshot("selected", IndustryState.INFLECTION_CANDIDATE),
            snapshot("rejected", IndustryState.DETERIORATING),
        ]
    )
    pool = InMemoryCompanyPool({"selected": candidates("selected", 8), "rejected": candidates("rejected", 8)})
    result = IndustryFirstDiscovery(
        radar,
        pool,
        PassThroughCompanyData(),
        PassThroughDeepResearch(),
        ResourcePolicy(company_pool_size=5, supplemental_company_limit=3, deep_company_limit=2, ai_deep_company_limit=1),
    ).run("2026-07-18")

    assert [item.industry_id for item in result.selected_industries] == ["selected"]
    assert "rejected" in result.rejected_industries
    assert len(result.company_pools["selected"]) == 1
    assert result.company_pools["selected"][0].data_tier == CompanyDataTier.AI_DEEP
    assert result.resource_audit["full_market_deep_data"] is False
    assert result.resource_audit["light_data_company_count"] == 5


def test_empty_result_is_valid():
    result = IndustryFirstDiscovery(
        InMemoryRadar([snapshot("weak", IndustryState.INSUFFICIENT)]),
        InMemoryCompanyPool({}),
        PassThroughCompanyData(),
    ).run("2026-07-18")

    assert result.empty_result is True
    assert result.selected_industries == []
    assert result.company_pools == {}


def test_full_market_deep_data_is_rejected_by_policy():
    try:
        ResourcePolicy(allow_full_market_deep_data=True).validate()
    except ValueError as error:
        assert "full-market" in str(error)
    else:
        raise AssertionError("full-market deep data must require a separate approved workflow")


class RecordingCompanyPool:
    def __init__(self, candidates_by_industry):
        self.candidates_by_industry = candidates_by_industry
        self.calls = []

    def candidates(self, industry, limit):
        self.calls.append((industry.industry_id, limit))
        return self.candidates_by_industry.get(industry.industry_id, ())[:limit]


class RecordingCompanyData:
    def __init__(self):
        self.calls = []

    def enrich(self, candidates, tier):
        self.calls.append((len(candidates), tier))
        return [candidate.with_tier(tier) for candidate in candidates]


def test_discovery_only_loads_company_data_for_selected_industries():
    selected = snapshot("selected", IndustryState.CLEARING)
    rejected = snapshot("rejected", IndustryState.DETERIORATING)
    pool = RecordingCompanyPool({"selected": candidates("selected", 4), "rejected": candidates("rejected", 4)})
    data = RecordingCompanyData()

    result = IndustryFirstDiscovery(
        InMemoryRadar([selected, rejected]),
        pool,
        data,
        policy=ResourcePolicy(
            company_pool_size=3,
            supplemental_company_limit=2,
            deep_company_limit=1,
            ai_deep_company_limit=1,
        ),
    ).run("2026-07-19")

    assert pool.calls == [("selected", 3)]
    assert result.resource_audit["light_data_company_count"] == 3
    assert [tier for _, tier in data.calls] == [
        CompanyDataTier.LIGHT,
        CompanyDataTier.SUPPLEMENTAL,
        CompanyDataTier.DEEP,
    ]
    assert len(result.company_pools["selected"]) == 1


def test_discovery_carries_all_four_opportunity_screening_assessments():
    selected = IndustryRadarSnapshot(
        "four-types",
        "四类机会行业",
        "2026-07-25",
        IndustryState.INFLECTION_CANDIDATE,
        signals=(
            # Demand acceleration groups.
            IndustrySignal(
                "demand_growth", "accelerating", "2026-07-25", "fixture", "VERIFIED"
            ),
            IndustrySignal(
                "order_growth", "improving", "2026-07-25", "fixture", "VERIFIED"
            ),
            IndustrySignal(
                "shipment_growth", "rising", "2026-07-25", "fixture", "VERIFIED"
            ),
            # Bottleneck pricing groups.
            IndustrySignal(
                "lead_time", "extended", "2026-07-25", "fixture", "VERIFIED"
            ),
            IndustrySignal(
                "spot_price", "rising", "2026-07-25", "fixture", "VERIFIED"
            ),
            IndustrySignal(
                "substitution_difficulty", "difficult", "2026-07-25", "fixture", "VERIFIED"
            ),
        ),
        evidence_completeness="CROSS_VALIDATED",
        opportunity_types=(
            "cycle_reversal",
            "quality_repair",
            "demand_acceleration",
            "bottleneck_pricing",
        ),
    )
    candidate = CompanyCandidate(
        "600438.SH",
        "示例公司",
        "four-types",
        metadata={
            "screening_inputs": {
                "survival": "strong",
                "demand_acceleration": {
                    "customer_validation": "confirmed",
                    "revenue_validation": "improving",
                    "profit_validation": "improving",
                },
                "bottleneck_pricing": {
                    "product_criticality": "high",
                    "pricing_power": "strong",
                    "revenue_validation": "confirmed",
                },
            }
        },
    )

    result = IndustryFirstDiscovery(
        InMemoryRadar([selected]),
        InMemoryCompanyPool({"four-types": [candidate]}),
        PassThroughCompanyData(),
        policy=ResourcePolicy(
            company_pool_size=1,
            supplemental_company_limit=1,
            deep_company_limit=1,
            ai_deep_company_limit=1,
        ),
    ).run("2026-07-25")

    assessments = result.company_pools["four-types"][0].metadata[
        "opportunity_assessments"
    ]
    assert set(assessments) == {
        "cycle_reversal",
        "quality_repair",
        "demand_acceleration",
        "bottleneck_pricing",
    }
    assert assessments["demand_acceleration"]["status"] == "PASS"
    assert assessments["bottleneck_pricing"]["status"] == "PASS"
