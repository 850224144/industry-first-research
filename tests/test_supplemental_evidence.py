import pytest

from industry_first_research.candidate_queue import build_candidate_queue
from industry_first_research.company_screen import screen_company_candidates
from industry_first_research.models import CompanyCandidate
from industry_first_research.supplemental_evidence import (
    SupplementalEvidenceError,
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


def test_verified_a_and_b_evidence_can_make_package_ready_only():
    report = build_supplemental_evidence_report(
        queue_report(),
        [
            evidence("ev-1", "company_scope", "上市主体", tier="A"),
            evidence(
                "ev-2",
                "reporting_scope",
                "合并口径",
                tier="B",
                refs=["https://example.test/a", "https://example.test/b"],
            ),
            evidence("ev-3", "key_products", ["新能源发电"], tier="A"),
            evidence("ev-4", "key_risks", ["资料待补充"], tier="A"),
        ],
    )

    item = report["items"][0]
    assert report["schema_version"] == "company-supplemental-evidence.v1"
    assert item["supplemental_state"] == "READY"
    assert item["candidate_state"] == "WATCH"
    assert item["candidate_rule_version"] == "company-candidate-queue-rules.v1"
    assert item["candidate_reasons"]
    assert item["candidate_evidence_gaps"] == []
    assert item["candidate_state_changed"] is False
    assert report["policy"]["supplemental_evidence_can_promote"] is False


def test_unverified_or_c_tier_evidence_stays_partial():
    report = build_supplemental_evidence_report(
        queue_report(),
        [evidence("ev-1", "company_scope", "上市主体", tier="C", status="UNVERIFIED")],
    )

    item = report["items"][0]
    assert item["supplemental_state"] == "PARTIAL"
    assert item["verified_fields"] == []
    assert "company_scope" in item["evidence_gaps"]
    assert "company_scope" in item["unverified_fields"]


def test_conflicts_block_supplemental_review():
    report = build_supplemental_evidence_report(
        queue_report(),
        [evidence("ev-1", "company_scope", "上市主体", status="CONFLICTING")],
    )

    item = report["items"][0]
    assert item["supplemental_state"] == "BLOCKED"
    assert item["blockers"] == ["EVIDENCE_CONFLICT"]


def test_rejected_queue_item_cannot_be_reopened_by_evidence():
    report = build_supplemental_evidence_report(
        queue_report("REJECTED"),
        [evidence("ev-1", "company_scope", "上市主体", tier="A")],
    )

    assert report["items"][0]["supplemental_state"] == "BLOCKED"
    assert report["items"][0]["candidate_state"] == "REJECTED"


def test_tier_b_requires_two_source_references_and_unknown_company_is_rejected():
    with pytest.raises(SupplementalEvidenceError, match="two source_refs"):
        build_supplemental_evidence_report(
            queue_report(),
            [evidence("ev-1", "company_scope", "上市主体", tier="B")],
        )

    unknown = evidence("ev-2", "company_scope", "上市主体")
    unknown["company_id"] = "000001"
    with pytest.raises(SupplementalEvidenceError, match="not in the input queue"):
        build_supplemental_evidence_report(queue_report(), [unknown])
