import json

from industry_first_research.models import (
    CompanyCandidate,
    CompanyDataTier,
    IndustryRadarSnapshot,
    IndustryState,
)
from industry_first_research.pipeline import IndustryFirstDiscovery


def test_company_candidate_light_profile_is_preserved_across_tiers():
    candidate = CompanyCandidate(
        "300317",
        "珈伟新能",
        "881145",
        light_profile={"status": "PARTIAL", "source": "fixture"},
    )

    upgraded = candidate.with_tier(CompanyDataTier.SUPPLEMENTAL)

    assert upgraded.data_tier == CompanyDataTier.SUPPLEMENTAL
    assert upgraded.light_profile == {"status": "PARTIAL", "source": "fixture"}
    assert upgraded.to_dict()["light_profile"]["status"] == "PARTIAL"


def test_discovery_result_json_is_serialisable():
    snapshot = IndustryRadarSnapshot(
        "881145",
        "电力",
        "2026-07-19",
        IndustryState.CLEARING,
        source_ids={"tonghuashun": "881145"},
    )

    assert snapshot.to_dict()["source_ids"] == {"tonghuashun": "881145"}
    assert json.dumps(snapshot.to_dict(), ensure_ascii=False)

