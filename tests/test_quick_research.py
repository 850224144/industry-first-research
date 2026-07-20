import pytest

from industry_first_research.candidate_queue import build_candidate_queue
from industry_first_research.company_screen import screen_company_candidates
from industry_first_research.models import CompanyCandidate
from industry_first_research.quick_research import (
    QuickResearchError,
    build_quick_research_report,
)
from industry_first_research.researchability import build_researchability_report
from industry_first_research.supplemental_evidence import (
    build_supplemental_evidence_report,
)


def build_inputs(candidate_state="REVIEW", records=None):
    screen = screen_company_candidates(
        [
            CompanyCandidate(
                "300317",
                "珈伟新能",
                "881145",
                source="https://example.test/company",
                light_profile={
                    "status": "PARTIAL",
                    "main_business": "新能源发电",
                    "source": "https://example.test/profile",
                    "as_of": "2026-07-19",
                    "available_fields": ["main_business"],
                    "field_sources": {
                        "listing_market": "https://example.test/listing-market"
                    },
                    "additional_sources": ["https://example.test/listing-market"],
                },
            )
        ],
        expected_industry="电力",
        input_snapshot_id="pool-001",
        input_as_of="2026-07-19",
        input_source={"provider": "tonghuashun_company_pool"},
    )
    queue = build_candidate_queue(screen)
    queue["items"][0]["candidate_state"] = candidate_state
    supplemental = build_supplemental_evidence_report(queue, records or [])
    readiness = build_researchability_report(supplemental)
    return readiness, supplemental


def record(evidence_id, field, value, *, tier="A", status="VERIFIED"):
    return {
        "evidence_id": evidence_id,
        "company_id": "300317",
        "field": field,
        "value": value,
        "source": "https://example.test/official",
        "source_refs": [],
        "as_of": "2026-07-19",
        "evidence_tier": tier,
        "verification_status": status,
    }


def test_quick_research_preserves_facts_and_marks_unknowns():
    readiness, supplemental = build_inputs(
        records=[
            record("ev-product", "key_products", ["新能源发电"]),
            record("ev-risk", "key_risks", ["资料待补充"]),
        ]
    )

    report = build_quick_research_report(readiness, supplemental)

    item = report["items"][0]
    assert report["schema_version"] == "company-quick-research.v1"
    assert report["research_mode"] == "LOCAL_ONLY"
    assert item["research_depth"] == "QUICK"
    assert item["known_facts"]["key_products"]["values"] == [["新能源发电"]]
    assert item["unknowns"] == ["company_scope", "reporting_scope"]
    assert item["candidate_field_sources"]["listing_market"].endswith(
        "listing-market"
    )
    assert item["candidate_additional_sources"] == [
        "https://example.test/listing-market"
    ]
    assert "FINANCIAL_DATA_NOT_INCLUDED" in item["limitations"]
    assert item["candidate_state_changed"] is False


def test_unverified_claim_is_not_known_fact():
    readiness, supplemental = build_inputs(
        records=[
            record("ev-product", "key_products", ["概念产品"], tier="C", status="UNVERIFIED")
        ]
    )

    item = build_quick_research_report(readiness, supplemental)["items"][0]

    assert "key_products" not in item["known_facts"]
    assert item["unverified_claims"]["key_products"]["status"] == "UNVERIFIED"


def test_quick_research_rejects_mismatched_report_lineage():
    readiness, supplemental = build_inputs()
    supplemental["report_id"] = "different-report"

    with pytest.raises(QuickResearchError, match="input_report_id"):
        build_quick_research_report(readiness, supplemental)
