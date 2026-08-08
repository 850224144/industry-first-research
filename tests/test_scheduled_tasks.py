import json

from industry_first_research.models import (
    CompanyCandidate,
    IndustryRadarSnapshot,
    IndustryState,
)
import industry_first_research.scheduled_tasks as scheduled_tasks_module
from industry_first_research.scheduled_tasks import LocalScheduledTaskRunner
from industry_first_research.scheduler import (
    build_default_schedule,
    build_scheduler_plan,
    build_scheduler_state,
)
from industry_first_research.research_version import build_research_version
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
    version_id = task_result["research_version_id"]
    version = json.loads(
        (tmp_path / "research_versions" / f"{version_id}.json").read_text()
    )
    assert version["schema_version"] == "research-version.v1"
    assert version["artifact_refs"][0]["artifact_id"] == "cross-industry-2026-07-21"
    assert version["source_health_snapshot_id"] == task_result["source_health_snapshot_id"]
    assert (
        tmp_path / "source_health" / f"{task_result['source_health_snapshot_id']}.json"
    ).exists()


def test_scheduled_research_version_links_previous_compatible_artifact(tmp_path):
    previous = build_research_version(
        {
            "subject_type": "industry",
            "subject_ids": ["881273"],
            "research_as_of": "2026-07-20",
            "artifact_refs": [
                {
                    "artifact_id": "cross-industry-2026-07-20",
                    "artifact_type": "industry_radar",
                    "as_of": "2026-07-20",
                    "content_hash": "a" * 64,
                }
            ],
        },
        version_id="research-version-radar-old",
        created_at="2026-07-20T09:00:00+08:00",
    )
    JsonSnapshotStore(tmp_path / "research_versions").write_immutable(
        previous["version_id"], previous
    )

    schedule = build_default_schedule()
    state = build_scheduler_state(schedule)
    plan, state = build_scheduler_plan(
        schedule, state, now="2026-07-21T09:00:00+08:00"
    )
    task_id = next(
        task["task_id"]
        for task in plan["tasks"]
        if task["task_type"] == "industry_radar_refresh"
    )
    result = LocalScheduledTaskRunner(
        data_root=tmp_path,
        radar_factory=lambda source, _limit: FakeRadar(source),
    ).execute(
        state,
        {**plan, "task_ids": [task_id]},
        now="2026-07-21T09:00:00+08:00",
    )

    version = json.loads(
        (
            tmp_path
            / "research_versions"
            / f"{result['results'][0]['research_version_id']}.json"
        ).read_text()
    )
    assert version["previous_version_id"] == "research-version-radar-old"


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


def test_futures_delta_scan_compares_saved_reports_with_a_bounded_scope(tmp_path):
    futures_dir = tmp_path / "futures_fundamentals"
    futures_dir.mkdir()

    def futures_report(report_id, as_of, spot):
        return {
            "schema_version": "futures-fundamentals-report.v1",
            "report_id": report_id,
            "as_of": as_of,
            "exchange": "SHFE",
            "variety_id": "CU",
            "variety_name": "沪铜",
            "object_type": "futures_contract",
            "status": "READY",
            "identity_status": "READY",
            "contract": {"contract_code": "CU2612"},
            "variety_view": {"status": "READY"},
            "contract_view": {"status": "READY"},
            "simulation_view": {"status": "ELIGIBLE_FOR_USER_REVIEW"},
            "price_scenarios": {
                "status": "READY",
                "missing": [],
                "scenarios": {},
            },
            "fields": {"spot_benchmark": {"status": "VERIFIED"}},
            "derived_metrics": {
                "spot_latest": {"date": as_of, "value": spot},
            },
        }

    (futures_dir / "old.json").write_text(
        json.dumps(futures_report("futures-old", "2026-07-20", 100)),
        encoding="utf-8",
    )
    (futures_dir / "new.json").write_text(
        json.dumps(futures_report("futures-new", "2026-07-21", 101)),
        encoding="utf-8",
    )
    schedule = build_default_schedule()
    state = build_scheduler_state(schedule)
    plan, state = build_scheduler_plan(
        schedule, state, now="2026-07-21T09:00:00+08:00"
    )
    task_id = next(
        task["task_id"]
        for task in plan["tasks"]
        if task["task_type"] == "futures_fundamentals_delta_scan"
    )
    plan["tasks"] = [
        {**task, "scope": {**task.get("scope", {}), "futures_report_dir": str(futures_dir)}}
        for task in plan["tasks"]
    ]
    state["tasks"][task_id]["scope"]["futures_report_dir"] = str(futures_dir)
    result = LocalScheduledTaskRunner(data_root=tmp_path).execute(
        state,
        {**plan, "task_ids": [task_id]},
        now="2026-07-21T09:00:00+08:00",
    )

    assert result["results"][0]["status"] == "SUCCEEDED"
    saved = json.loads(
        (tmp_path / "futures_tracking" / "futures-delta-2026-07-21.json").read_text()
    )
    assert saved["tracked_series_count"] == 1
    assert saved["rows"][0]["tracking_status"] == "UPDATED"
    assert saved["resource_audit"]["full_market_deep_data"] is False


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
    assert report["impact_queue_status"] == "NO_MATCHING_VERSION"
    assert (
        tmp_path
        / "research_impact_queues"
        / "research-impact-event-earnings-1.json"
    ).exists()
    assert report["automatic_incremental_update"]["status"] == "NOT_REQUESTED"


def test_event_task_runs_incremental_update_only_for_explicit_local_inputs(
    tmp_path, monkeypatch
):
    previous_pipeline_path = tmp_path / "previous-pipeline.json"
    previous_supplemental_path = tmp_path / "previous-supplemental.json"
    evidence_path = tmp_path / "new-evidence.json"
    previous_pipeline_path.write_text(
        json.dumps(
            {
                "schema_version": "company-research-pipeline.v1",
                "pipeline_id": "pipeline-old",
                "as_of": "2026-07-20",
                "stages": {"research_report": {"items": [{"company_id": "600519"}]}},
            }
        ),
        encoding="utf-8",
    )
    previous_supplemental_path.write_text(json.dumps({"report_id": "supplemental-old"}), encoding="utf-8")
    evidence_path.write_text(json.dumps({"records": []}), encoding="utf-8")

    def fake_incremental_update(*_args, **_kwargs):
        return {
            "schema_version": "company-incremental-update.v1",
            "update_id": "incremental-auto-001",
            "as_of": "2026-07-21",
            "updated_supplemental": {
                "schema_version": "company-supplemental-evidence.v1",
                "report_id": "supplemental-new",
                "as_of": "2026-07-21",
            },
            "updated_pipeline": {
                "schema_version": "company-research-pipeline.v1",
                "pipeline_id": "pipeline-new",
                "as_of": "2026-07-21",
                "stages": {
                    "research_report": {"items": [{"company_id": "600519"}]}
                },
            },
            "new_evidence_count": 0,
            "deferred_review_modules": ["research_report"],
            "policy": {
                "automatic_directional_conclusion": False,
                "automatic_decision_snapshot": False,
            },
        }

    monkeypatch.setattr(
        scheduled_tasks_module, "build_incremental_update", fake_incremental_update
    )
    event = {
        "event_id": "event-earnings-auto-1",
        "event_type": "earnings_report",
        "occurred_at": "2026-07-21T08:30:00+08:00",
        "source": "company-disclosure",
        "company_id": "600519",
        "payload_ref": "announcement-auto-1",
        "payload": {
            "previous_pipeline_path": str(previous_pipeline_path),
            "previous_supplemental_path": str(previous_supplemental_path),
            "evidence_path": str(evidence_path),
        },
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
        (tmp_path / "scheduled_events" / "event-scan-event-earnings-auto-1.json").read_text()
    )
    automatic = report["automatic_incremental_update"]
    assert automatic["status"] == "UPDATED"
    assert automatic["update_id"] == "incremental-auto-001"
    assert (tmp_path / "company_supplemental" / "supplemental-new.json").exists()
    assert (tmp_path / "company_research_pipelines" / "pipeline-new.json").exists()
    assert (tmp_path / "company_incremental_updates" / "incremental-auto-001.json").exists()
    assert (tmp_path / "research_versions" / f"{automatic['research_version_id']}.json").exists()
    updated_version = json.loads(
        (tmp_path / "research_versions" / f"{automatic['research_version_id']}.json").read_text()
    )
    assert updated_version["previous_version_id"] == ""
    assert updated_version["source_health_snapshot_id"].startswith("source-health-")
    updated_pipeline = json.loads(
        (tmp_path / "company_research_pipelines" / "pipeline-new.json").read_text()
    )
    assert updated_pipeline["research_version_id"] == automatic["research_version_id"]


def test_event_task_blocks_partial_incremental_input_without_writing_new_pipeline(tmp_path):
    event = {
        "event_id": "event-earnings-partial-1",
        "event_type": "earnings_report",
        "occurred_at": "2026-07-21T08:30:00+08:00",
        "source": "company-disclosure",
        "company_id": "600519",
        "payload": {"previous_pipeline_path": "missing-pipeline.json"},
    }
    _, state, plan = _event_plan(event)
    task_id = next(
        task["task_id"]
        for task in plan["tasks"]
        if task["task_type"] == "event_triggered_scan"
    )
    result = LocalScheduledTaskRunner(data_root=tmp_path).execute(
        state,
        {**plan, "task_ids": [task_id]},
        now="2026-07-21T09:00:00+08:00",
    )

    assert result["results"][0]["status"] == "SUCCEEDED"
    report = json.loads(
        (tmp_path / "scheduled_events" / "event-scan-event-earnings-partial-1.json").read_text()
    )
    automatic = report["automatic_incremental_update"]
    assert automatic["status"] == "BLOCKED"
    assert set(automatic["missing_inputs"]) == {
        "previous_supplemental_path",
        "evidence_path",
    }
    assert not (tmp_path / "company_research_pipelines").exists()


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
