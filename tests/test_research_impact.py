import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.research_impact import (
    ResearchImpactError,
    build_research_impact_queue,
    validate_research_impact_queue,
)
from industry_first_research.research_version import build_research_version


def version(version_id, as_of="2026-07-21"):
    return build_research_version(
        {
            "subject_type": "listed_company",
            "subject_ids": ["600438"],
            "research_as_of": as_of,
            "pipeline_id": f"pipeline-{version_id}",
            "version_status": "VALID",
        },
        version_id=version_id,
        created_at=f"{as_of}T09:00:00+08:00",
    )


def event(**overrides):
    payload = {
        "event_id": "announcement-600438-20260722",
        "event_type": "quarterly_report",
        "subject_type": "listed_company",
        "subject_id": "600438",
        "event_at": "2026-07-22T18:00:00+08:00",
        "source": "official_exchange",
        "asset_id": "announcement-600438-20260722-v1",
    }
    payload.update(overrides)
    return payload


def test_event_maps_matching_versions_and_preserves_cutoff_boundary():
    queue = build_research_impact_queue(
        event(),
        [version("version-old", "2026-07-21"), version("version-new", "2026-07-23")],
    )

    assert queue["review_status"] == "REVIEW_REQUIRED"
    assert queue["impacted_version_count"] == 2
    actions = {item["version_id"]: item["action"] for item in queue["impacted_versions"]}
    assert actions["version-old"] == "CREATE_NEXT_VERSION_DO_NOT_BACKFILL"
    assert actions["version-new"] == "CREATE_REVISED_VERSION"
    assert validate_research_impact_queue(queue)["queue_id"] == queue["queue_id"]


def test_unmatched_event_is_retained_without_creating_conclusion():
    queue = build_research_impact_queue(
        event(subject_id="600519"), [version("version-001")]
    )

    assert queue["review_status"] == "NO_MATCHING_VERSION"
    assert queue["unmatched_reason"] == "NO_SUBJECT_MATCHING_RESEARCH_VERSION"
    assert queue["policy"]["automatic_directional_conclusion"] is False

    with pytest.raises(ResearchImpactError, match="content_hash"):
        validate_research_impact_queue(dict(queue, content_hash="0" * 64))


def test_research_impact_queue_cli_reads_version_directory(tmp_path, monkeypatch, capsys):
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event()), encoding="utf-8")
    versions_dir = tmp_path / "versions"
    versions_dir.mkdir()
    manifest = version("version-cli")
    (versions_dir / "version-cli.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    output_dir = tmp_path / "impact"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "research-impact-queue",
            "--event",
            str(event_path),
            "--versions-dir",
            str(versions_dir),
            "--output-dir",
            str(output_dir),
        ],
    )
    main()
    capsys.readouterr()
    output = output_dir / "research-impact-announcement-600438-20260722.json"
    assert output.exists()
