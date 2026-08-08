import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.research_version import (
    ResearchVersionError,
    build_research_version,
    build_research_version_comparison,
    build_research_version_replay,
    validate_research_version,
)


def manifest(**overrides):
    value = {
        "subject_type": "listed_company",
        "subject_ids": ["600519"],
        "research_as_of": "2026-07-21",
        "pipeline_id": "pipeline-001",
        "supplemental_id": "supplemental-001",
        "artifact_refs": [
            {
                "artifact_id": "pipeline-001",
                "artifact_type": "pipeline",
                "as_of": "2026-07-21",
                "content_hash": "a" * 64,
            }
        ],
    }
    value.update(overrides)
    return value


def test_research_version_is_immutable_and_validates_hash():
    version = build_research_version(
        manifest(), version_id="version-001", created_at="2026-07-21T09:00:00+08:00"
    )

    assert version["schema_version"] == "research-version.v1"
    assert version["immutable"] is True
    assert len(version["content_hash"]) == 64
    assert validate_research_version(version)["version_id"] == "version-001"

    changed = dict(version, research_as_of="2026-07-22")
    with pytest.raises(ResearchVersionError, match="content_hash"):
        validate_research_version(changed)


def test_research_version_can_reference_source_health_snapshot():
    version = build_research_version(
        manifest(source_health_snapshot_id="source-health-001"),
        version_id="version-with-health",
        created_at="2026-07-21T09:00:00+08:00",
    )
    assert version["source_health_snapshot_id"] == "source-health-001"
    assert validate_research_version(version)["version_id"] == "version-with-health"


def test_manifest_comparison_and_replay_are_read_only():
    old = build_research_version(
        manifest(), version_id="version-old", created_at="2026-07-21T09:00:00+08:00"
    )
    current = build_research_version(
        manifest(
            previous_version_id="version-old",
            affected_modules=["valuation_scenarios"],
            execution_mode="MANUAL_WEB_AI",
        ),
        version_id="version-current",
        created_at="2026-07-22T09:00:00+08:00",
    )
    comparison = build_research_version_comparison(old, current)
    assert "affected_modules" in comparison["changed_fields"]
    assert comparison["requires_review"] is True
    replay = build_research_version_replay(
        old,
        [{"artifact_id": "pipeline-001", "content_hash": "b" * 64}],
    )
    assert replay["status"] == "BLOCKED"
    assert replay["network_calls"] == 0
    assert replay["model_calls"] == 0


def test_research_version_cli_creates_manifest(tmp_path, monkeypatch, capsys):
    input_path = tmp_path / "manifest.json"
    input_path.write_text(json.dumps(manifest()), encoding="utf-8")
    output_dir = tmp_path / "versions"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "research-version",
            "--input",
            str(input_path),
            "--version-id",
            "version-cli",
            "--output-dir",
            str(output_dir),
        ],
    )
    main()
    capsys.readouterr()
    assert (output_dir / "version-cli.json").exists()


def test_validate_research_version_rejects_future_artifact_in_replay():
    version = build_research_version(
        manifest(), version_id="version-future", created_at="2026-07-21T09:00:00+08:00"
    )
    replay = __import__(
        "industry_first_research.research_version",
        fromlist=["build_research_version_replay"],
    ).build_research_version_replay(
        version,
        [{"artifact_id": "pipeline-001", "content_hash": "a" * 64, "as_of": "2026-07-22"}],
    )
    assert replay["status"] == "BLOCKED"
