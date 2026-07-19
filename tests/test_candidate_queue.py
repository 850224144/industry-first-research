import pytest

from industry_first_research.candidate_queue import (
    CandidateQueueError,
    build_candidate_queue,
)
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


def test_pass_is_watch_only_and_keeps_provenance():
    screen = screen_company_candidates(
        [
            candidate(
                status="VERIFIED",
                legal_name="深圳珈伟新能源股份有限公司",
                main_business="新能源发电",
                reported_industry="电力",
                listing_market="深圳证券交易所",
                source="https://example.test/profile",
                as_of="2026-07-19",
                available_fields=[
                    "legal_name",
                    "main_business",
                    "reported_industry",
                    "listing_market",
                ],
            )
        ],
        expected_industry="电力",
    )

    report = build_candidate_queue(screen, snapshot_id="screen-001")

    item = report["items"][0]
    assert report["schema_version"] == "company-candidate-queue.v1"
    assert item["candidate_state"] == "WATCH"
    assert item["source"] == "https://example.test/profile"
    assert item["as_of"] == "2026-07-19"
    assert item["evidence_gaps"] == []
    assert report["policy"]["light_data_can_be_candidate"] is False
    assert item["investment_conclusion"] is False


def test_queue_uses_screen_input_provenance_for_root_traceability():
    screen = screen_company_candidates(
        [candidate(status="PARTIAL", main_business="新能源发电")],
        expected_industry="电力",
        input_snapshot_id="pool-001",
        input_as_of="2026-07-19",
        input_source={"provider": "tonghuashun_company_pool"},
    )

    report = build_candidate_queue(screen)

    assert report["input_snapshot_id"] == "pool-001"
    assert report["as_of"] == "2026-07-19"
    assert report["source"] == "tonghuashun_company_pool"
    assert report["source_metadata"]["provider"] == "tonghuashun_company_pool"
    assert report["queue_id"] == "company-candidate-queue-pool-001"


def test_partial_profile_stays_review_and_records_gaps():
    screen = screen_company_candidates(
        [candidate(status="PARTIAL", main_business="新能源发电")],
        expected_industry="电力",
    )

    item = build_candidate_queue(screen)["items"][0]

    assert item["candidate_state"] == "REVIEW"
    assert "REPORTED_INDUSTRY_MISSING" in item["evidence_gaps"]
    assert "AS_OF_MISSING" in item["evidence_gaps"]
    assert item["rule_version"] == "company-candidate-queue-rules.v1"


def test_identity_or_industry_conflicts_are_rejected():
    screen = screen_company_candidates(
        [candidate(status="VERIFIED", reported_industry="银行")],
        expected_industry="电力",
    )

    item = build_candidate_queue(screen)["items"][0]

    assert item["candidate_state"] == "REJECTED"
    assert "INDUSTRY_MISMATCH" in item["blockers"]


def test_queue_rejects_non_screen_input():
    with pytest.raises(CandidateQueueError, match="company-light-screen.v1"):
        build_candidate_queue({"schema_version": "industry-radar.v1", "items": []})


def test_queue_rejects_non_object_input():
    with pytest.raises(CandidateQueueError, match="JSON object"):
        build_candidate_queue([])
