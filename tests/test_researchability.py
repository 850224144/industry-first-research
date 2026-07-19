import pytest

from industry_first_research.candidate_queue import build_candidate_queue
from industry_first_research.company_screen import screen_company_candidates
from industry_first_research.models import CompanyCandidate
from industry_first_research.researchability import (
    ResearchabilityError,
    build_researchability_report,
)
from industry_first_research.supplemental_evidence import (
    build_supplemental_evidence_report,
)


def queue_report(candidate_state="WATCH"):
    screen = screen_company_candidates(
        [
            CompanyCandidate(
                "300317",
                "珈伟新能",
                "881145",
                source="https://example.test/company",
                light_profile={
                    "status": "VERIFIED",
                    "main_business": "新能源发电",
                    "reported_industry": "电力",
                    "source": "https://example.test/profile",
                    "as_of": "2026-07-19",
                    "available_fields": ["main_business", "reported_industry"],
                },
            )
        ],
        expected_industry="电力",
        input_snapshot_id="pool-001",
        input_as_of="2026-07-19",
        input_source={"provider": "tonghuashun_company_pool"},
    )
    report = build_candidate_queue(screen)
    report["items"][0]["candidate_state"] = candidate_state
    return report


def evidence(evidence_id, field, value, *, tier="A", status="VERIFIED", refs=None):
    return {
        "evidence_id": evidence_id,
        "company_id": "300317",
        "field": field,
        "value": value,
        "source": "https://example.test/official",
        "source_refs": refs or [],
        "as_of": "2026-07-19",
        "evidence_tier": tier,
        "verification_status": status,
    }


def supplemental(candidate_state="WATCH", records=None):
    return build_supplemental_evidence_report(
        queue_report(candidate_state),
        records
        or [
            evidence("ev-1", "company_scope", "上市主体"),
            evidence("ev-2", "reporting_scope", "合并口径"),
            evidence("ev-3", "key_products", ["新能源发电"]),
            evidence("ev-4", "key_risks", ["资料待补充"]),
        ],
    )


def test_ready_evidence_allows_standard_research_without_promoting_candidate():
    report = build_researchability_report(supplemental())

    item = report["items"][0]
    assert report["schema_version"] == "company-researchability.v1"
    assert item["research_readiness"] == "READY"
    assert item["research_depth"] == "STANDARD"
    assert item["candidate_state"] == "WATCH"
    assert item["candidate_state_changed"] is False
    assert item["allowed_actions"] == ["standard_research", "evidence_refresh"]


def test_review_candidate_is_partial_even_when_required_fields_are_covered():
    item = build_researchability_report(supplemental("REVIEW"))["items"][0]

    assert item["research_readiness"] == "PARTIAL"
    assert item["research_depth"] == "QUICK"
    assert "CANDIDATE_REVIEW_GAPS_REQUIRE_DEGRADED_RESEARCH" in item["reasons"]


def test_insufficient_and_blocked_states_limit_research():
    insufficient = build_researchability_report(
        supplemental("INSUFFICIENT")
    )["items"][0]
    blocked = build_researchability_report(
        supplemental(
            records=[
                evidence(
                    "ev-1", "company_scope", "冲突", status="CONFLICTING"
                )
            ]
        )
    )["items"][0]

    assert insufficient["research_readiness"] == "INSUFFICIENT"
    assert insufficient["research_depth"] == "SCREEN_ONLY"
    assert blocked["research_readiness"] == "BLOCKED"
    assert blocked["research_depth"] == "NONE"


def test_readiness_rejects_unknown_states_and_wrong_schema():
    with pytest.raises(ResearchabilityError, match="supplemental-evidence.v1"):
        build_researchability_report({"schema_version": "other", "items": []})

    report = supplemental()
    report["items"][0]["supplemental_state"] = "UNKNOWN"
    with pytest.raises(ResearchabilityError, match="supplemental_state"):
        build_researchability_report(report)
