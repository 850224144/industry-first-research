import json

import pytest

from industry_first_research.security_master import (
    SecurityMasterError,
    build_security_master_snapshot,
    lookup_security_master_company,
    validate_security_master_snapshot,
)


def master_input(as_of="2026-07-22", *, industry_id="baijiu", company_id="600519"):
    return {
        "schema_version": "security-master-input.v1",
        "snapshot_id": f"input-{as_of}",
        "as_of": as_of,
        "scope": {"scope_type": "EXPLICIT", "coverage_claim": "BOUNDED"},
        "records": [
            {
                "company_id": company_id,
                "display_name": "贵州茅台",
                "market": "上海证券交易所",
                "listing_status": "LISTED",
                "source": "official-company-profile",
                "industry_memberships": [
                    {
                        "industry_id": industry_id,
                        "industry_name": "白酒",
                        "membership_type": "PRIMARY",
                        "classification_source": "official-company-profile",
                        "classification_version": "v1",
                        "confidence": "HIGH",
                    }
                ],
            }
        ],
    }


def test_master_is_lightweight_and_validates():
    report = build_security_master_snapshot(master_input())

    assert report["schema_version"] == "security-master-snapshot.v1"
    assert report["company_count"] == 1
    assert report["current_membership_count"] == 1
    assert report["scope"]["deep_data_loaded"] is False
    assert report["policy"]["full_market_deep_data_forbidden"] is True
    assert validate_security_master_snapshot(report)["status"] == "VALID"


def test_industry_membership_change_closes_old_interval_and_opens_new_one():
    first = build_security_master_snapshot(master_input("2026-07-22"))
    second_input = master_input("2026-08-01", industry_id="new-energy")
    second = build_security_master_snapshot(second_input, previous_snapshot=first)

    history = second["industry_membership_history"]
    assert len(history) == 2
    old = next(item for item in history if item["industry_id"] == "baijiu")
    new = next(item for item in history if item["industry_id"] == "new-energy")
    assert old["effective_to"] == "2026-08-01"
    assert old["membership_state"] == "CLOSED"
    assert new["effective_from"] == "2026-08-01"
    assert new["effective_to"] == ""
    assert second["membership_changes"]["closed"] == 1
    assert validate_security_master_snapshot(second)["status"] == "VALID"


def test_bounded_input_absence_does_not_close_old_membership():
    first = build_security_master_snapshot(master_input("2026-07-22"))
    later = {
        "schema_version": "security-master-input.v1",
        "as_of": "2026-08-01",
        "scope": {"scope_type": "BOUNDED_POOL", "coverage_claim": "BOUNDED"},
        "records": [],
    }

    second = build_security_master_snapshot(later, previous_snapshot=first)

    assert second["current_membership_count"] == 1
    assert second["membership_changes"]["closed"] == 0
    assert second["policy"]["bounded_pool_absence_does_not_close_membership"] is True


def test_deep_data_is_rejected_and_research_candidate_set_never_enters_master():
    deep = master_input()
    deep["records"][0]["financials"] = {"revenue": 1}
    report = build_security_master_snapshot(deep)
    assert report["company_count"] == 0
    assert report["rejected_record_count"] == 1
    assert "deep data" in report["rejected_records"][0]["reason"]

    candidate_set = {
        "schema_version": "research-asset-candidate-set.v1",
        "import_id": "research-candidates-luopan-1",
        "source_project": "luopan",
        "as_of": "2026-07-22",
        "candidates": [{"candidate_id": "600519", "display_name": "贵州茅台"}],
    }
    boundary = build_security_master_snapshot(candidate_set)
    assert boundary["company_count"] == 0
    assert boundary["rejected_record_count"] == 1
    assert boundary["scope"]["representative_research_candidates_in_master"] is False


def test_duplicate_and_unknown_market_are_rejected_without_inference():
    payload = master_input()
    payload["records"].append(dict(payload["records"][0]))
    payload["records"][0].pop("market")
    report = build_security_master_snapshot(payload)

    assert report["company_count"] == 0
    assert report["rejected_record_count"] == 2
    reasons = " ".join(item["reason"] for item in report["rejected_records"])
    assert "market is required and cannot be inferred" in reasons
    assert "DUPLICATE_COMPANY_ID_IN_INPUT" in reasons


def test_invalid_previous_snapshot_and_schema_are_explicit():
    with pytest.raises(SecurityMasterError, match="input must be"):
        build_security_master_snapshot({"schema_version": "unknown", "as_of": "2026-07-22"})
    with pytest.raises(SecurityMasterError, match="previous snapshot"):
        build_security_master_snapshot(
            master_input(),
            previous_snapshot={"schema_version": "unknown"},
        )
    assert json.dumps(master_input(), ensure_ascii=False)


def test_exact_local_identity_lookup_does_not_treat_bounded_absence_as_exit():
    snapshot = build_security_master_snapshot(master_input())

    by_code = lookup_security_master_company(snapshot, "600519")
    by_name = lookup_security_master_company(snapshot, "贵州茅台")
    absent = lookup_security_master_company(snapshot, "600438")

    assert by_code["status"] == "MATCHED"
    assert by_code["match_method"] == "EXACT"
    assert by_code["company"]["company_id"] == "600519"
    assert by_name["status"] == "MATCHED"
    assert absent["status"] == "NOT_FOUND"
    assert absent["absence_is_not_exit"] is True
