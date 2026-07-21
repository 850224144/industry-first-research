import json
import sys

import pytest

from industry_first_research.announcement_asset import (
    AnnouncementAssetError,
    build_announcement_asset,
    build_announcement_impact,
)
from industry_first_research.cli import main


def announcement(**overrides):
    payload = {
        "schema_version": "original-announcement-input.v1",
        "document_id": "announcement-001",
        "version": 1,
        "subject_type": "listed_company",
        "subject_id": "600438",
        "issuer": "示例公司",
        "document_type": "quarterly_report",
        "title": "2026年半年度报告",
        "source": "official_exchange",
        "source_url": "https://example.test/announcement-001",
        "published_at": "2026-07-20T18:00:00+08:00",
        "captured_at": "2026-07-21T08:00:00+08:00",
        "as_of": "2026-06-30",
        "source_version": "exchange-feed-1",
        "parser_version": "parser-1",
        "raw_content": "official announcement body",
    }
    payload.update(overrides)
    return payload


def test_announcement_asset_is_hashed_immutable_and_maps_review_modules():
    asset = build_announcement_asset(announcement())

    assert asset["schema_version"] == "original-announcement-asset.v1"
    assert len(asset["content_hash"]) == 64
    assert asset["immutable"] is True
    assert "valuation_scenarios" in asset["affected_modules"]
    assert asset["supersedes_document_id"] is None


def test_correction_creates_a_new_version_and_impact_does_not_rewrite_history():
    asset = build_announcement_asset(
        announcement(
            document_id="announcement-001-v2",
            version=2,
            correction_status="CORRECTED",
            supersedes_document_id="announcement-001",
            correction_reason="修正现金流表",
            raw_content="corrected announcement body",
        )
    )
    impact = build_announcement_impact(asset, research_cutoff="2026-07-21T00:00:00+08:00")

    assert asset["correction_status"] == "CORRECTED"
    assert "announcement_correction" in impact["event_type"]
    assert impact["temporal_relation"] == "PRE_CUTOFF"
    assert impact["decision_snapshot_changed"] is False
    assert impact["policy"]["old_research_preserved"] is True


def test_post_cutoff_correction_is_not_backfilled_into_historical_research():
    asset = build_announcement_asset(
        announcement(
            document_id="announcement-002",
            version=2,
            correction_status="SUPPLEMENT",
            supersedes_document_id="announcement-001",
            published_at="2026-07-22T10:00:00+08:00",
            captured_at="2026-07-22T11:00:00+08:00",
            raw_content="supplement announcement body",
        )
    )
    impact = build_announcement_impact(asset, research_cutoff="2026-07-21T00:00:00+08:00")
    assert impact["temporal_relation"] == "POST_CUTOFF"
    assert impact["policy"]["future_information_not_backfilled"] is True


def test_announcement_rejects_invalid_correction_contract_and_hash():
    with pytest.raises(AnnouncementAssetError, match="supersedes_document_id"):
        build_announcement_asset(announcement(correction_status="CORRECTED"))
    with pytest.raises(AnnouncementAssetError, match="content_hash"):
        build_announcement_asset(announcement(content_hash="0" * 64))


def test_announcement_cli_writes_asset_and_impact(tmp_path, monkeypatch, capsys):
    input_path = tmp_path / "announcement.json"
    input_path.write_text(json.dumps(announcement()), encoding="utf-8")
    raw_path = tmp_path / "source.txt"
    raw_path.write_text("official announcement body", encoding="utf-8")
    assets_dir = tmp_path / "assets"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "announcement-asset",
            "--input",
            str(input_path),
            "--raw-content",
            str(raw_path),
            "--output-dir",
            str(assets_dir),
        ],
    )
    main()
    capsys.readouterr()
    asset_path = assets_dir / "announcement-001-v1.json"
    assert asset_path.exists()
    asset = json.loads(asset_path.read_text(encoding="utf-8"))
    raw_copy = assets_dir / "raw" / "announcement-001-v1.txt"
    assert raw_copy.read_text(encoding="utf-8") == "official announcement body"
    assert asset["raw_content_uri"] == str(raw_copy)

    impacts_dir = tmp_path / "impacts"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "announcement-impact",
            "--input",
            str(asset_path),
            "--research-cutoff",
            "2026-07-21T00:00:00+08:00",
            "--output-dir",
            str(impacts_dir),
        ],
    )
    main()
    capsys.readouterr()
    assert len(list(impacts_dir.glob("*.json"))) == 1
