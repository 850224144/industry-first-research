from industry_first_research.company_screen import screen_company_candidates
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
                main_business="新能源发电",
                reported_industry="电力",
                source="https://example.test/profile",
            )
        ],
        expected_industry="电力",
    )

    result = report["items"][0]
    assert result["screen_state"] == "PASS"
    assert result["investment_conclusion"] is False


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
