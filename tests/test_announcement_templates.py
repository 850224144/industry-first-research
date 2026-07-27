import json
import sys
from pathlib import Path

from industry_first_research.announcement_templates import (
    get_template,
    load_template_catalog,
    parse_announcement_input,
    validate_template_catalog,
)
from industry_first_research.announcement_asset import build_announcement_asset
from industry_first_research.cli import main


CATALOG = Path(__file__).resolve().parents[1] / "config" / "announcement_templates.v1.json"


def test_checked_in_catalog_contains_all_disclosure_template_families():
    catalog = load_template_catalog(CATALOG)

    assert catalog["template_count"] == 4
    assert {
        item["template_id"] for item in catalog["templates"]
    } == {
        "official_exchange",
        "company_disclosure",
        "eastmoney_announcement",
        "futures_exchange_disclosure",
    }
    assert all(item["url_contract"]["required_params"] for item in catalog["templates"])


def test_json_snapshot_is_parsed_with_field_lineage_and_cutoff_metadata():
    template = get_template(load_template_catalog(CATALOG), "official_exchange")
    raw = json.dumps(
        {
            "document_id": "ex-001",
            "title": "示例公司2025年年度报告",
            "publish_time": "2026-04-30 18:00:00",
            "security_code": "600438",
            "company_name": "示例公司",
        },
        ensure_ascii=False,
    )

    report = parse_announcement_input(
        {
            "source_url": "https://exchange.example/notice/ex-001",
            "subject_type": "listed_company",
            "research_as_of": "2026-07-23",
        },
        raw,
        template,
    )

    assert report["status"] == "READY"
    assert report["document_id"] == "ex-001"
    assert report["subject_id"] == "600438"
    assert report["document_type"] == "annual_report"
    assert report["published_at"].startswith("2026-04-30T18:00:00")
    assert report["field_locators"]["published_at"]["method"] == "json_path"
    assert report["original_content_locator"]["locator_kind"] == "entire_original_snapshot"
    assert report["source_attempts"][0]["status"] == "PARSED"
    assert report["policy"]["no_network_fetch"] is True


def test_html_template_extracts_meta_fields_and_detects_correction():
    template = get_template(load_template_catalog(CATALOG), "company_disclosure")
    raw = """
    <html><head>
      <title>示例公司关于更正年度报告的公告</title>
      <meta name="publish-time" content="2026-07-22 09:00:00">
      <meta name="security-code" content="600438">
      <meta name="document-id" content="ex-001-v2">
    </head><body>原公告编号：ex-001</body></html>
    """

    report = parse_announcement_input(
        {"source_url": "https://company.example/notice/ex-001-v2"},
        raw,
        template,
    )

    assert report["status"] == "READY"
    assert report["correction_status"] == "CORRECTED"
    assert report["supersedes_document_id"] == "ex-001"
    assert report["version"] == 2
    assert report["field_locators"]["published_at"]["method"] == "html_meta"


def test_missing_correction_parent_is_blocked_without_inference():
    template = get_template(load_template_catalog(CATALOG), "company_disclosure")
    report = parse_announcement_input(
        {
            "source_url": "https://company.example/notice/ex-001-v2",
            "subject_id": "600438",
        },
        "<title>示例公司更正公告</title><meta name='publish-time' content='2026-07-22'>",
        template,
    )

    assert report["status"] == "BLOCKED"
    assert any(item["field"] == "supersedes_document_id" for item in report["missing_or_invalid_fields"])


def test_future_announcement_is_blocked_for_historical_cutoff():
    template = get_template(load_template_catalog(CATALOG), "company_disclosure")
    report = parse_announcement_input(
        {
            "source_url": "https://company.example/notice/future",
            "subject_id": "600438",
            "research_as_of": "2026-07-21",
        },
        "标题：公司公告\n发布日期：2026-07-22\n正文：原始披露",
        template,
    )

    assert report["status"] == "BLOCKED"
    assert any(
        item["code"] == "PUBLISHED_AFTER_RESEARCH_AS_OF"
        for item in report["missing_or_invalid_fields"]
    )


def test_degraded_parse_can_be_promoted_only_after_asset_contract_is_valid(tmp_path):
    template = get_template(load_template_catalog(CATALOG), "company_disclosure")
    report = parse_announcement_input(
        {
            "source_url": "https://company.example/notice/ex-002",
            "subject_id": "600438",
        },
        "标题：公司公告\n发布日期：2026-07-20\n正文：原始披露",
        template,
    )

    assert report["status"] == "DEGRADED"
    assert report["document_type"] == "announcement"
    report["raw_content_uri"] = str(tmp_path / "raw.txt")
    asset = build_announcement_asset(report)
    assert asset["document_type"] == "announcement"
    assert asset["review_only"] is True


def test_announcement_parse_cli_preserves_raw_snapshot_for_asset_chain(tmp_path, monkeypatch, capsys):
    raw_path = tmp_path / "notice.json"
    raw_path.write_text(
        json.dumps(
            {
                "document_id": "cli-001",
                "title": "公司重大合同公告",
                "publish_time": "2026-07-20 18:00:00",
                "security_code": "600438",
                "company_name": "示例公司",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    parsed_dir = tmp_path / "parsed"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "announcement-parse",
            "--input",
            str(raw_path),
            "--template",
            "official_exchange",
            "--config",
            str(CATALOG),
            "--source-url",
            "https://exchange.example/notice/cli-001",
            "--subject-type",
            "listed_company",
            "--output-dir",
            str(parsed_dir),
        ],
    )
    main()
    capsys.readouterr()
    parsed_path = parsed_dir / "cli-001-v1.json"
    assert parsed_path.exists()
    parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
    assert (parsed_dir / "raw" / "cli-001-v1.json").read_bytes() == raw_path.read_bytes()

    assets_dir = tmp_path / "assets"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "announcement-asset",
            "--input",
            str(parsed_path),
            "--output-dir",
            str(assets_dir),
        ],
    )
    main()
    capsys.readouterr()
    asset = json.loads((assets_dir / "cli-001-v1.json").read_text(encoding="utf-8"))
    assert asset["content_hash"] == parsed["content_hash"]
    assert asset["raw_content_uri"] == parsed["raw_content_uri"]
