import json

from industry_first_research.models import (
    CompanyCandidate,
    IndustryRadarSnapshot,
    IndustryState,
)
from industry_first_research.scheduled_tasks import LocalScheduledTaskRunner
from industry_first_research.scheduler import (
    build_default_schedule,
    build_scheduler_plan,
    build_scheduler_state,
)
from industry_first_research.storage import JsonSnapshotStore


class FakeRadar:
    def __init__(self, source="fake", items=None):
        self.source = source
        self.items = items or [
            IndustryRadarSnapshot(
                "881273",
                "白酒",
                "2026-07-21",
                IndustryState.CLEARING,
            )
        ]

    def snapshots(self, _as_of):
        return self.items

    def metadata(self, as_of):
        return {"provider": self.source, "as_of": as_of, "read_only": True}


class FakePool:
    def __init__(self, _limit):
        self._candidates = [
            CompanyCandidate("600519", "贵州茅台", "881273", source="fake")
        ]

    def candidates(self, _industry, _limit):
        return self._candidates

    def metadata(self):
        return {"provider": "fake_company_pool", "read_only": True}


class FakeCompanyData:
    def enrich(self, candidates, _tier):
        return [
            candidate.with_light_profile(
                {
                    "status": "VERIFIED",
                    "main_business": "白酒生产与销售",
                    "as_of": "2026-07-21",
                    "source": "fake",
                }
            )
            for candidate in candidates
        ]


def _event_plan(event, now="2026-07-21T09:00:00+08:00"):
    schedule = build_default_schedule()
    state = build_scheduler_state(schedule)
    plan, state = build_scheduler_plan(schedule, state, [event], now=now)
    return schedule, state, plan


def test_radar_task_reuses_provider_and_writes_bounded_snapshot(tmp_path):
    schedule = build_default_schedule()
    state = build_scheduler_state(schedule)
    plan, state = build_scheduler_plan(schedule, state, now="2026-07-21T09:00:00+08:00")
    task_id = next(
        task["task_id"]
        for task in plan["tasks"]
        if task["task_type"] == "industry_radar_refresh"
    )
    runner = LocalScheduledTaskRunner(
        data_root=tmp_path,
        radar_factory=lambda source, _limit: FakeRadar(source),
    )

    result = runner.execute(
        state,
        {**plan, "task_ids": [task_id]},
        now="2026-07-21T09:00:00+08:00",
    )

    task_result = result["results"][0]
    assert task_result["status"] == "SUCCEEDED"
    snapshot = json.loads(
        (tmp_path / "radar" / "cross-industry-2026-07-21.json").read_text()
    )
    assert snapshot["schema_version"] == "industry-radar.v1"
    assert snapshot["resource_audit"]["full_market_deep_data"] is False


def test_daily_delta_writes_opportunity_tracking_without_inventing_state(tmp_path):
    radar_dir = tmp_path / "radar"
    radar_dir.mkdir()
    for day in ("2026-07-19", "2026-07-20", "2026-07-21"):
        (radar_dir / f"cross-industry-{day}.json").write_text(
            json.dumps(
                {
                    "schema_version": "industry-radar.v1",
                    "source": {"provider": "cross", "as_of": day},
                    "items": [
                        {
                            "industry_id": "881273",
                            "display_name": "白酒",
                            "as_of": day,
                            "state": "CLEARING",
                            "evidence_completeness": "CROSS_VALIDATED",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
    schedule = build_default_schedule()
    state = build_scheduler_state(schedule)
    plan, state = build_scheduler_plan(
        schedule, state, now="2026-07-21T09:00:00+08:00"
    )
    task_id = next(
        task["task_id"] for task in plan["tasks"] if task["task_type"] == "daily_delta_scan"
    )
    runner = LocalScheduledTaskRunner(data_root=tmp_path)
    result = runner.execute(
        state,
        {**plan, "task_ids": [task_id]},
        now="2026-07-21T09:00:00+08:00",
    )

    assert result["results"][0]["status"] == "SUCCEEDED"
    report = json.loads(
        (tmp_path / "scheduled_deltas" / "daily-delta-cross-2026-07-21.json").read_text()
    )
    tracking = report["opportunity_tracking"]
    assert tracking["current_scan_status"] == "NO_SNAPSHOT"
    assert tracking["state_transition_requires_new_evidence"] is True


def test_event_task_writes_affected_module_review_only_record(tmp_path):
    event = {
        "event_id": "event-earnings-1",
        "event_type": "earnings_report",
        "occurred_at": "2026-07-21T08:30:00+08:00",
        "source": "company-disclosure",
        "company_id": "600519",
        "payload_ref": "announcement-1",
    }
    _, state, plan = _event_plan(event)
    task_id = next(
        task["task_id"]
        for task in plan["tasks"]
        if task["task_type"] == "event_triggered_scan"
    )
    runner = LocalScheduledTaskRunner(data_root=tmp_path)

    result = runner.execute(
        state,
        {**plan, "task_ids": [task_id]},
        now="2026-07-21T09:00:00+08:00",
    )

    assert result["results"][0]["status"] == "SUCCEEDED"
    report = json.loads(
        (tmp_path / "scheduled_events" / "event-scan-event-earnings-1.json").read_text()
    )
    assert report["status"] == "REVIEW_REQUIRED"
    assert "valuation_scenarios" in report["affected_modules"]
    assert report["directional_conclusion"] is False


def test_company_pool_refresh_stays_light_and_event_scoped(tmp_path):
    event = {
        "event_id": "event-industry-1",
        "event_type": "industry_selected",
        "occurred_at": "2026-07-21T08:30:00+08:00",
        "source": "industry-radar",
        "industry_id": "881273",
        "payload": {"industry_name": "白酒", "tonghuashun_industry_id": "881273"},
    }
    _, state, plan = _event_plan(event)
    task_id = next(
        task["task_id"]
        for task in plan["tasks"]
        if task["task_type"] == "company_pool_refresh"
    )
    runner = LocalScheduledTaskRunner(
        data_root=tmp_path,
        company_pool_factory=lambda limit: FakePool(limit),
        company_data_factory=lambda: FakeCompanyData(),
    )

    result = runner.execute(
        state,
        {**plan, "task_ids": [task_id]},
        now="2026-07-21T09:00:00+08:00",
    )

    assert result["results"][0]["status"] == "SUCCEEDED"
    pool_path = tmp_path / "company_pools" / "scheduled-company-pool-881273-2026-07-21.json"
    pool = json.loads(pool_path.read_text())
    assert pool["light_data"]["tier"] == "LIGHT"
    assert pool["resource_audit"]["company_pool_limit"] == 30
    assert pool["full_industry_membership_loaded"] is False
