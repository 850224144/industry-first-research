from industry_first_research.company_screen import screen_company_candidates
from industry_first_research.industry_aliases import IndustryAliasRegistry
from industry_first_research.models import CompanyCandidate


def candidate(**profile):
    return CompanyCandidate(
        "300317",
        "珈伟新能",
        "881145",
        source="https://example.test/company",
        light_profile=profile,
    )


def test_complete_light_profile_passes_data_quality_screen():
    report = screen_company_candidates(
        [
            candidate(
                status="VERIFIED",
                legal_name="深圳珈伟新能源股份有限公司",
                main_business="新能源发电",
                reported_industry="电力",
                listing_market="深圳证券交易所",
                source="https://example.test/profile",
                field_sources={
                    "listing_market": "https://example.test/listing-market"
                },
                additional_sources=["https://example.test/listing-market"],
            )
        ],
        expected_industry="电力",
    )

    result = report["items"][0]
    assert result["screen_state"] == "PASS"
    assert result["evidence_gaps"] == []
    assert result["investment_conclusion"] is False
    assert result["field_sources"]["listing_market"].endswith("listing-market")
    assert result["additional_sources"] == ["https://example.test/listing-market"]


def test_screen_preserves_input_snapshot_provenance():
    report = screen_company_candidates(
        [candidate(status="PARTIAL", main_business="新能源发电")],
        expected_industry="电力",
        input_snapshot_id="pool-001",
        input_as_of="2026-07-19",
        input_source={"provider": "tonghuashun_company_pool"},
    )

    assert report["input_snapshot_id"] == "pool-001"
    assert report["input_as_of"] == "2026-07-19"
    assert report["input_source"]["provider"] == "tonghuashun_company_pool"


def test_partial_profile_requires_review_without_being_called_a_failure():
    report = screen_company_candidates(
        [candidate(status="PARTIAL", main_business="新能源发电")],
        expected_industry="电力",
    )

    result = report["items"][0]
    assert result["screen_state"] == "REVIEW"
    assert "REPORTED_INDUSTRY_MISSING" in result["reasons"]
    assert "LISTING_MARKET_MISSING" in result["evidence_gaps"]
    assert result["blockers"] == []


def test_unavailable_or_mismatched_profile_is_insufficient():
    report = screen_company_candidates(
        [
            candidate(
                status="UNAVAILABLE",
                reported_industry="银行",
            )
        ],
        expected_industry="电力",
    )

    result = report["items"][0]
    assert result["screen_state"] == "INSUFFICIENT"
    assert "LIGHT_DATA_UNAVAILABLE" in result["blockers"]


def test_explicit_industry_alias_allows_hierarchical_company_label():
    registry = IndustryAliasRegistry.from_dict(
        {
            "schema_version": "industry-aliases.v1",
            "mappings": [
                {
                    "canonical_id": "baijiu",
                    "canonical_name": "白酒",
                    "aliases": {
                        "tonghuashun": ["白酒"],
                        "tonghuashun_company_profile": ["白酒Ⅱ", "白酒Ⅲ"],
                    },
                    "note": "test mapping",
                }
            ],
        }
    )
    report = screen_company_candidates(
        [
            candidate(
                status="VERIFIED",
                legal_name="测试白酒",
                main_business="白酒生产和销售",
                reported_industry="白酒Ⅱ",
                listing_market="上海证券交易所",
            )
        ],
        expected_industry="白酒",
        industry_alias_registry=registry,
    )

    result = report["items"][0]
    assert result["screen_state"] == "PASS"
    assert "INDUSTRY_MISMATCH" not in result["blockers"]
    assert report["rules"]["industry_matching"]["alias_registry"]["mapping_count"] == 1
