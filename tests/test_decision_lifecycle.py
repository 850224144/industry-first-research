import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.decision_lifecycle import (
    DecisionLifecycleError,
    build_decision_lifecycle,
    build_decision_lifecycle_event,
)


def snapshot():
    return {
        "schema_version": "decision-snapshot.v1",
        "snapshot_id": "decision-snapshot-001",
        "status": "LOCKED",
        "immutable": True,
        "simulation_only": True,
        "decision": {"review_date": "2026-08-19"},
    }


def test_lifecycle_events_are_append_only_and_project_status():
    active = build_decision_lifecycle_event(
        snapshot(),
        to_status="ACTIVE",
        changed_at="2026-07-21T09:00:00+08:00",
        reason="用户确认进入模拟跟踪",
        user_confirmed=True,
    )
    due = build_decision_lifecycle_event(
        snapshot(),
        to_status="REVIEW_DUE",
        changed_at="2026-08-19T09:00:00+08:00",
        reason="到达复查日期",
        previous_events=[active],
    )
    report = build_decision_lifecycle(snapshot(), [active, due], as_of="2026-08-19")

    assert report["current_status"] == "REVIEW_DUE"
    assert report["event_count"] == 2
    assert report["policy"]["snapshot_unchanged"] is True
    assert report["events"][0]["to_status"] == "ACTIVE"


def test_invalidated_requires_evidence_and_closed_requires_attribution():
    with pytest.raises(DecisionLifecycleError, match="evidence_ids"):
        build_decision_lifecycle_event(
            snapshot(),
            to_status="INVALIDATED",
            changed_at="2026-07-21",
            reason="核心假设失效",
        )
    with pytest.raises(DecisionLifecycleError, match="attribution_id"):
        build_decision_lifecycle_event(
            snapshot(),
            to_status="CLOSED",
            changed_at="2026-08-20",
            reason="完成复盘",
            previous_events=[
                build_decision_lifecycle_event(
                    snapshot(),
                    to_status="ACTIVE",
                    changed_at="2026-07-21",
                    reason="开始跟踪",
                    user_confirmed=True,
                )
            ],
        )


def test_lifecycle_rejects_invalid_transition_and_marks_due_as_projection():
    with pytest.raises(DecisionLifecycleError, match="invalid lifecycle transition"):
        build_decision_lifecycle_event(
            snapshot(),
            to_status="CLOSED",
            changed_at="2026-07-21",
            reason="直接关闭",
        )
    report = build_decision_lifecycle(snapshot(), as_of="2026-08-20")
    assert report["current_status"] == "REVIEW_DUE"
    assert report["review_due_projection"] is True
    assert report["event_count"] == 0


def test_lifecycle_cli_writes_event_and_projection(tmp_path, monkeypatch, capsys):
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot()), encoding="utf-8")
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "to_status": "ACTIVE",
                "changed_at": "2026-07-21",
                "reason": "进入跟踪",
                "user_confirmed": True,
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "lifecycle"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "decision-lifecycle-event",
            "--snapshot",
            str(snapshot_path),
            "--input",
            str(event_path),
            "--output-dir",
            str(output_dir),
        ],
    )
    main()
    capsys.readouterr()
    assert len(list(output_dir.glob("*.json"))) == 2
