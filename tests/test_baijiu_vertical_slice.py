import json
from pathlib import Path
import sys

from industry_first_research.config import candidates_from_config, load_config, radar_from_config
from industry_first_research.cli import main
from industry_first_research.local_assets import ConfigCompanyPool, LocalAssetDataProvider, LocalResearchAssetCatalog
from industry_first_research.pipeline import InMemoryRadar, IndustryFirstDiscovery
from industry_first_research.report import render_scan_html, render_scan_markdown
from industry_first_research.source_integrity import (
    apply_source_integrity,
    build_source_integrity_report,
)


ROOT = Path(__file__).parents[1]


def run_baijiu():
    config = load_config(ROOT / "config/industries/baijiu.json")
    integrity = build_source_integrity_report(config, ROOT)
    config = apply_source_integrity(config, integrity)
    result = IndustryFirstDiscovery(
        InMemoryRadar([radar_from_config(config)]),
        ConfigCompanyPool(
            candidates_from_config(config),
            LocalResearchAssetCatalog(ROOT),
        ),
        LocalAssetDataProvider(),
    ).run(config["as_of"], scan_id="baijiu-current-config")
    return config, integrity, result


def test_baijiu_config_runs_bounded_vertical_slice():
    config, integrity, result = run_baijiu()

    assert result.empty_result is True
    assert result.selected_industries[0].industry_id == "baijiu"
    assert result.selected_industries[0].evidence_completeness == "INSUFFICIENT"
    assert integrity["summary"]["downgraded_signal_count"] == 3
    assert integrity["summary"]["blocked_company_count"] == 13
    assert result.resource_audit["light_data_company_count"] == 13
    assert result.resource_audit["deep_data_company_count"] == 0
    assert result.resource_audit["rejected_company_count"] == 13
    assert result.resource_audit["full_market_deep_data"] is False
    assert all(
        candidate.hard_gate_status == "BLOCKED"
        for candidate in result.rejected_companies
    )
    assert result.rejected_companies[0].metadata["asset_status"]


def test_baijiu_report_has_sources_and_boundaries():
    config, _integrity, result = run_baijiu()
    markdown = render_scan_markdown(result, config, config["source_documents"])
    html = render_scan_html(result, config, config["source_documents"])

    assert "中国白酒" in markdown
    assert "LOCAL_ASSET_REUSE" in markdown
    assert "全市场深度数据" in html
    assert "REFERENCE_ONLY" in markdown
    assert "MISSING" in markdown


def test_baijiu_config_is_valid_json():
    payload = json.loads((ROOT / "config/industries/baijiu.json").read_text(encoding="utf-8"))
    assert payload["industry_id"] == "baijiu"
    assert len(payload["companies"]) == 13


def test_baijiu_fixture_backed_golden_path_is_reproducible():
    config = load_config(ROOT / "tests/fixtures/baijiu/config.json")

    integrity = build_source_integrity_report(config, ROOT)
    adjusted = apply_source_integrity(config, integrity)

    def run():
        return IndustryFirstDiscovery(
            InMemoryRadar([radar_from_config(adjusted)]),
            ConfigCompanyPool(
                candidates_from_config(adjusted),
                LocalResearchAssetCatalog(ROOT),
            ),
            LocalAssetDataProvider(),
        ).run(adjusted["as_of"], scan_id="baijiu-golden-2026-07-16")

    first = run()
    second = run()
    expected = json.loads(
        (ROOT / "tests/fixtures/baijiu/golden_expected.json").read_text(
            encoding="utf-8"
        )
    )
    actual = {
        "industry_id": first.selected_industries[0].industry_id,
        "evidence_completeness": first.selected_industries[0].evidence_completeness,
        "source_integrity_status": integrity["status"],
        "light_data_company_count": first.resource_audit["light_data_company_count"],
        "deep_data_company_count": first.resource_audit["deep_data_company_count"],
        "selected_company_ids": [
            candidate.company_id for candidate in first.company_pools["baijiu"]
        ],
    }

    assert first.to_dict() == second.to_dict()
    assert actual == expected
    assert all(
        candidate.metadata["asset_summary"]["complete"]
        for candidate in first.company_pools["baijiu"]
    )


def test_baijiu_golden_cli_is_replayable(
    tmp_path, monkeypatch, capsys
):
    snapshot_dir = tmp_path / "snapshots"
    markdown_path = tmp_path / "baijiu-golden.md"
    html_path = tmp_path / "baijiu-golden.html"
    argv = [
        "industry-first-research",
        "industry",
        "--config",
        "tests/fixtures/baijiu/config.json",
        "--snapshot-dir",
        str(snapshot_dir),
        "--output",
        str(markdown_path),
        "--html-output",
        str(html_path),
    ]
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(sys, "argv", argv)

    main()
    first = json.loads(capsys.readouterr().out)
    main()
    second = json.loads(capsys.readouterr().out)

    assert first == second
    snapshot = json.loads(Path(first["snapshot"]).read_text(encoding="utf-8"))
    assert snapshot["industry"]["source_integrity"]["status"] == "READY"
    assert snapshot["scan"]["resource_audit"]["light_data_company_count"] == 13
    assert snapshot["scan"]["resource_audit"]["deep_data_company_count"] == 5
    assert markdown_path.is_file()
    assert html_path.is_file()
