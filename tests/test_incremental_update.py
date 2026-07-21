import json

import pytest

from industry_first_research.candidate_queue import build_candidate_queue
from industry_first_research.company_screen import screen_company_candidates
from industry_first_research.incremental_update import (
    IncrementalUpdateError,
    build_incremental_update,
)
from industry_first_research.industry_aliases import IndustryAliasRegistry
from industry_first_research.models import CompanyCandidate
from industry_first_research.research_pipeline import build_research_pipeline
from industry_first_research.supplemental_evidence import (
    build_supplemental_evidence_report,
)


def _supplemental(records):
    aliases = IndustryAliasRegistry.from_dict(
        {
            "schema_version": "industry-aliases.v1",
            "mappings": [
                {
                    "canonical_id": "baijiu",
                    "canonical_name": "白酒",
                    "aliases": {
                        "tonghuashun": ["白酒"],
                        "tonghuashun_company_profile": ["白酒Ⅱ"],
                    },
                    "note": "test mapping",
                }
            ],
        }
    )
    screen = screen_company_candidates(
        [
            CompanyCandidate(
                "600519",
                "贵州茅台",
                "881273",
                source="https://example.test/company",
                light_profile={
                    "status": "VERIFIED",
                    "legal_name": "贵州茅台",
                    "main_business": "白酒生产与销售",
                    "reported_industry": "白酒Ⅱ",
                    "listing_market": "上海证券交易所",
                    "source": "https://example.test/profile",
                    "as_of": "2026-07-20",
                    "available_fields": [
                        "legal_name",
                        "main_business",
                        "reported_industry",
                        "listing_market",
                    ],
                },
            )
        ],
        expected_industry="白酒",
        industry_alias_registry=aliases,
        input_snapshot_id="pool-001",
        input_as_of="2026-07-20",
        input_source={"provider": "test"},
    )
    queue = build_candidate_queue(screen)
    return build_supplemental_evidence_report(
        queue,
        records,
        required_fields=["company_scope", "key_products", "key_risks"],
        snapshot_id="supplemental-001",
    )


def _record(evidence_id, field, value, as_of="2026-07-20"):
    return {
        "evidence_id": evidence_id,
        "company_id": "600519",
        "field": field,
        "value": value,
        "source": "https://example.test/official",
        "source_refs": [],
        "as_of": as_of,
        "evidence_tier": "A",
        "verification_status": "VERIFIED",
    }


def test_incremental_update_preserves_old_version_and_maps_affected_stages():
    old = _supplemental(
        [
            _record("scope-1", "company_scope", "上市主体"),
            _record("products-1", "key_products", ["白酒"]),
        ]
    )
    previous_pipeline = build_research_pipeline(old, snapshot_id="pipeline-001")
    update = build_incremental_update(
        previous_pipeline,
        old,
        [
            _record("scope-1", "company_scope", "上市主体"),
            _record("products-2", "key_products", ["白酒、系列酒"], "2026-07-21"),
        ],
        as_of="2026-07-21",
    )

    assert update["new_evidence_count"] == 1
    assert update["change_counts"] == {"CHANGED": 1}
    company = update["company_updates"][0]
    assert company["rerun_from"] == "product_profile"
    assert "valuation_scenarios" in company["affected_modules"]
    assert update["policy"]["old_versions_preserved"] is True
    assert update["previous_pipeline_id"] == "company-research-pipeline-pipeline-001"
    assert update["updated_pipeline_id"] != update["previous_pipeline_id"]
    assert update["updated_supplemental"]["as_of"] == "2026-07-21"
    assert update["updated_pipeline"]["as_of"] == "2026-07-21"
    assert json.dumps(update, ensure_ascii=False)


def test_incremental_update_rejects_mutating_an_immutable_evidence_id():
    old = _supplemental([_record("scope-1", "company_scope", "上市主体")])
    previous_pipeline = build_research_pipeline(old)

    with pytest.raises(IncrementalUpdateError, match="immutable evidence_id changed"):
        build_incremental_update(
            previous_pipeline,
            old,
            [_record("scope-1", "company_scope", "合并主体")],
            as_of="2026-07-21",
        )
