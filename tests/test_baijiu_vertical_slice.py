import json
from pathlib import Path

from industry_first_research.config import candidates_from_config, load_config, radar_from_config
from industry_first_research.local_assets import ConfigCompanyPool, LocalAssetDataProvider, LocalResearchAssetCatalog
from industry_first_research.pipeline import InMemoryRadar, IndustryFirstDiscovery
from industry_first_research.report import render_scan_html, render_scan_markdown


ROOT = Path(__file__).parents[1]


def run_baijiu():
    config = load_config(ROOT / "config/industries/baijiu.json")
    result = IndustryFirstDiscovery(
        InMemoryRadar([radar_from_config(config)]),
        ConfigCompanyPool(
            candidates_from_config(config),
            LocalResearchAssetCatalog(ROOT),
        ),
        LocalAssetDataProvider(),
    ).run(config["as_of"])
    return config, result


def test_baijiu_config_runs_bounded_vertical_slice():
    config, result = run_baijiu()

    assert result.empty_result is False
    assert result.selected_industries[0].industry_id == "baijiu"
    assert result.resource_audit["light_data_company_count"] == 13
    assert result.resource_audit["deep_data_company_count"] == 5
    assert result.resource_audit["full_market_deep_data"] is False
    assert result.company_pools["baijiu"][0].metadata["asset_status"]


def test_baijiu_report_has_sources_and_boundaries():
    config, result = run_baijiu()
    markdown = render_scan_markdown(result, config, config["source_documents"])
    html = render_scan_html(result, config, config["source_documents"])

    assert "中国白酒" in markdown
    assert "LOCAL_ASSET_REUSE" in markdown
    assert "全市场深度数据" in html
    assert "REFERENCE_ONLY" in markdown


def test_baijiu_config_is_valid_json():
    payload = json.loads((ROOT / "config/industries/baijiu.json").read_text(encoding="utf-8"))
    assert payload["industry_id"] == "baijiu"
    assert len(payload["companies"]) == 13
