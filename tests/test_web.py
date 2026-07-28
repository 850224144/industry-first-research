import json
from pathlib import Path

import pytest

from industry_first_research.web import (
    ResearchWebApplication,
    WebApplicationError,
)


def test_web_health_and_snapshot_index_are_local_and_bounded(tmp_path):
    data_root = tmp_path / "data"
    tasks = data_root / "research_tasks"
    reports = data_root / "company_research_reports"
    tasks.mkdir(parents=True)
    reports.mkdir(parents=True)
    (tasks / "task-1.json").write_text(
        json.dumps(
            {
                "schema_version": "research-task-resolution.v1",
                "task_id": "task-1",
                "status": "NEEDS_CONFIRMATION",
                "research_as_of": "2026-07-27",
                "execution_enabled": False,
                "review_only": True,
            }
        ),
        encoding="utf-8",
    )
    (reports / "report-1.json").write_text(
        json.dumps(
            {
                "schema_version": "company-research-report.v1",
                "report_id": "report-1",
                "status": "REVIEWABLE",
                "as_of": "2026-07-26",
                "execution_enabled": False,
            }
        ),
        encoding="utf-8",
    )

    app = ResearchWebApplication(data_root=data_root, web_root=Path("web"))
    health = app.health()
    summary = app.summary()
    snapshots = app.snapshots()

    assert health["mode"] == "LOCAL_ONLY"
    assert health["execution_enabled"] is False
    assert summary["snapshot_count"] == 2
    assert summary["status_counts"] == {
        "NEEDS_CONFIRMATION": 1,
        "REVIEWABLE": 1,
    }
    assert {item["id"] for item in snapshots} == {"task-1", "report-1"}
    assert all(item["execution_enabled"] is False for item in snapshots)


def test_web_resolve_task_persists_idempotently_and_keeps_execution_disabled(tmp_path):
    app = ResearchWebApplication(data_root=tmp_path / "data")
    payload = {
        "input": "白酒行业",
        "research_as_of": "2026-07-27",
        "requested_depth": "STANDARD",
        "simulation_mode": True,
    }

    first = app.resolve_task(payload)
    second = app.resolve_task(payload)

    assert first["task"]["task_type"] == "industry_research"
    assert first["task"]["subject_type"] == "industry"
    assert first["task"]["execution_enabled"] is False
    assert first["persisted"] is True
    assert second["task"]["content_hash"] == first["task"]["content_hash"]
    assert list((tmp_path / "data" / "research_tasks").glob("*.json"))


def test_web_rejects_invalid_tasks_and_path_escape(tmp_path):
    app = ResearchWebApplication(data_root=tmp_path / "data", web_root=Path("web"))

    with pytest.raises(WebApplicationError, match="input is required"):
        app.resolve_task({})
    with pytest.raises(WebApplicationError, match="outside web root"):
        app.static("/../README.md")


def test_web_static_console_has_operational_sections():
    app = ResearchWebApplication(web_root=Path(__file__).parents[1] / "web")
    status, content, content_type = app.static("/")

    assert status == 200
    assert content_type.startswith("text/html")
    assert "发起研究任务".encode("utf-8") in content
    assert b"execution_enabled" not in content
