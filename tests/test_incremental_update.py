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


def test_incremental_update_records_execution_mode_and_lineage():
    old = _supplemental([_record("scope-1", "company_scope", "上市主体")])
    previous_pipeline = build_research_pipeline(old)
    scope = {
        "schema_version": "company-scope.v1",
        "scope_id": "company-scope-600519",
        "company_id": "600519",
        "researchability_state": "PARTIAL",
        "as_of": "2026-07-20",
        "content_hash": "scope-hash",
        "field_status": {},
        "evidence_ids": ["scope-ev"],
        "blockers": [],
        "unknowns": ["debt_attribution"],
    }
    update = build_incremental_update(
        previous_pipeline,
        old,
        [_record("scope-2", "company_scope", "合并主体", "2026-07-21")],
        as_of="2026-07-21",
        execution_mode="MANUAL_WEB_AI",
        company_scope_reports={"600519": scope},
    )
    assert update["execution_mode"] == "MANUAL_WEB_AI"
    assert update["policy"]["manual_web_ai_is_import_only"] is True
    assert update["lineage"]["company_scope"]["status"] == "REFRESHED"
    assert update["updated_pipeline"]["company_scope_review"] == "SUPPLIED"


def test_incremental_update_reuses_upstream_stages_for_market_structure_only_change():
    old = _supplemental([_record("scope-1", "company_scope", "上市主体")])
    previous_pipeline = build_research_pipeline(old, snapshot_id="pipeline-market-old")
    market_structure = {
        "schema_version": "market-structure-snapshot.v1",
        "timeframes": {"daily": {"state": "RANGE"}},
    }

    update = build_incremental_update(
        previous_pipeline,
        old,
        [],
        as_of="2026-07-21",
        market_structure_report=market_structure,
    )

    plan = update["recompute_plan"]
    assert plan["strategy"] == "PARTIAL_DOWNSTREAM_CHAIN"
    assert plan["rerun_from"] == "adversarial_review"
    assert plan["reused_modules"] == [
        "product_profile",
        "application_mapping",
        "demand_transmission",
        "industry_situation",
        "cycle_reversal",
        "competitive_position",
        "survival_analysis",
        "valuation_scenarios",
    ]
    assert plan["recomputed_modules"] == ["adversarial_review", "research_report"]
    assert update["updated_supplemental_id"] == old["report_id"]
    assert (
        update["updated_pipeline"]["stages"]["valuation_scenarios"]
        == previous_pipeline["stages"]["valuation_scenarios"]
    )
    assert (
        update["updated_pipeline"]["stages"]["research_report"]
        != previous_pipeline["stages"]["research_report"]
    )
