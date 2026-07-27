import json
from pathlib import Path

import pytest

from industry_first_research.industry_adapters import (
    IndustryAdapterError,
    IndustryAdapterRegistry,
    build_industry_adapter_registry_report,
    build_industry_profile_report,
)


ROOT = Path(__file__).parents[1]
ADAPTER_DIR = ROOT / "config/industries/adapters"


def profile(**overrides):
    payload = {
        "schema_version": "industry-profile-input.v1",
        "profile_id": "baijiu-2026-07-22",
        "subject_type": "industry",
        "subject_id": "baijiu",
        "industry_id": "baijiu",
        "industry_name": "中国白酒",
        "industry_family": "consumer",
        "business_model": "消费",
        "as_of": "2026-07-22",
        "source": "config",
        "evidence_ids": ["industry-source-1"],
        "attributes": {"segment": "白酒", "cyclicality": "WEAK_CYCLICAL"},
    }
    payload.update(overrides)
    return payload


def test_registry_resolves_baijiu_and_keeps_configuration_only_boundary():
    registry = IndustryAdapterRegistry.from_directory(ADAPTER_DIR)
    adapter = registry.resolve("白酒")
    report = build_industry_adapter_registry_report(registry)

    assert adapter.adapter_id == "consumer_brand"
    assert report["adapter_count"] == 7
    assert report["policy"]["data_fetched"] is False
    assert report["investment_conclusion"] is False


def test_profile_classification_is_explicit_and_not_a_verified_fact():
    registry = IndustryAdapterRegistry.from_directory(ADAPTER_DIR)

    report = build_industry_profile_report(profile(), registry)

    assert report["adapter_id"] == "consumer_brand"
    assert report["classification"]["classification_state"] == "READY"
    assert report["classification"]["match_method"] == "INDUSTRY_ID_EXACT"
    assert report["claims_are_verified"] is False
    assert report["cycle_model_available"] is True
    assert report["policy"]["product_exposure_requires_explicit_product"] is True


def test_unknown_industry_uses_generic_fallback_and_downgrades():
    registry = IndustryAdapterRegistry.from_directory(ADAPTER_DIR)
    unknown = profile(
        industry_id="unknown-thing",
        industry_name="未知行业",
        industry_family="unknown",
        business_model="unknown",
    )

    adapter, classification = registry.resolve_for_profile(unknown)

    assert adapter.adapter_id == "generic_company"
    assert classification["classification_state"] == "PARTIAL"
    assert classification["confidence"] == "LOW"
    assert classification["match_method"] == "FALLBACK_GENERIC"


def test_non_cyclical_adapter_returns_no_cycle_model(tmp_path: Path):
    payload = json.loads((ADAPTER_DIR / "consumer_brand.json").read_text(encoding="utf-8"))
    payload["adapter_id"] = "software_test"
    payload["display_name"] = "软件测试"
    payload["aliases"] = ["software-test"]
    payload["supported_industry_ids"] = ["software"]
    payload["supported_industry_names"] = ["软件"]
    payload["supported_industry_families"] = ["software"]
    payload["business_models"] = ["软件"]
    payload["classification_attributes"]["cyclicality"] = "NON_CYCLICAL"
    path = tmp_path / "software.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    adapter = IndustryAdapterRegistry.from_directory(tmp_path).resolve("software")

    assert adapter.build_cycle_model({"inventory": "missing"}) is None


@pytest.mark.parametrize(
    ("industry_id", "industry_name", "industry_family", "business_model", "adapter_id", "metric"),
    [
        ("bank", "银行", "financial_services", "银行", "financial_services", "asset_quality"),
        ("software", "软件", "software", "SaaS", "software_saas", "net_revenue_retention"),
        ("pharma", "医药", "healthcare", "创新药", "healthcare", "pipeline_or_product_approval"),
        ("power", "电力", "utilities", "发电", "utilities", "tariff_or_price_mechanism"),
    ],
)
def test_non_photovoltaic_industry_profiles_select_domain_contract(
    industry_id, industry_name, industry_family, business_model, adapter_id, metric
):
    registry = IndustryAdapterRegistry.from_directory(ADAPTER_DIR)
    adapter, classification = registry.resolve_for_profile(
        profile(
            profile_id=f"{industry_id}-2026",
            subject_id=industry_id,
            industry_id=industry_id,
            industry_name=industry_name,
            industry_family=industry_family,
            business_model=business_model,
        )
    )

    assert adapter.adapter_id == adapter_id
    assert classification["classification_state"] == "READY"
    assert metric in adapter.required_metrics
    assert adapter.build_cycle_model({}) is None


def test_product_application_requires_explicit_mapping_and_transmission_is_staged():
    registry = IndustryAdapterRegistry.from_directory(ADAPTER_DIR)
    adapter = registry.resolve("baijiu")
    mapping = adapter.map_product_applications(
        {"products": [{"product_id": "p1", "product_name": "高端白酒"}]},
        {
            "product_applications": [
                {
                    "product_id": "p1",
                    "application_name": "商务宴请",
                    "system_layer": "终端消费",
                    "criticality": "OPTIONAL",
                    "substitution_risk": "MEDIUM",
                    "evidence_id": "app-1",
                    "status": "VERIFIED",
                }
            ]
        },
    )
    transmission = adapter.assess_demand_transmission(
        mapping,
        {
            "demand_transmission": [
                {"product_id": "p1", "stage": "CONCEPT", "status": "VERIFIED", "evidence_id": "d1"},
                {"product_id": "p1", "stage": "CHANNEL_VALIDATED", "status": "VERIFIED", "evidence_id": "d2"},
            ]
        },
    )

    assert mapping["mapping_state"] == "READY"
    assert transmission["items"][0]["transmission_state"] == "PARTIAL"
    assert transmission["investment_conclusion"] is False


def test_invalid_definition_and_conclusion_validation_are_conservative():
    registry = IndustryAdapterRegistry.from_directory(ADAPTER_DIR)
    with pytest.raises(IndustryAdapterError, match="no industry adapter"):
        registry.resolve_for_profile(
            profile(
                industry_id="none",
                industry_name="none",
                industry_family="none",
                business_model="none",
            ),
            allow_fallback=False,
        )
    issues = registry.resolve("baijiu").validate_conclusion({})
    assert "MISSING_SECTION:product_profile" in issues
    assert "CONCLUSION_REMAINS_REVIEW_ONLY" in issues
