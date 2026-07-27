from industry_first_research.scheduler import (
    PermanentTaskError,
    RetryableTaskError,
    build_default_schedule,
    build_scheduler_plan,
    build_scheduler_state,
    execute_scheduler_plan,
)


def test_default_schedule_is_bounded_and_plans_recurring_jobs_once():
    schedule = build_default_schedule()
    state = build_scheduler_state(schedule)

    plan, state = build_scheduler_plan(
        schedule,
        state,
        now="2026-07-21T09:00:00+08:00",
    )

    assert {task["task_type"] for task in plan["tasks"]} == {
        "industry_radar_refresh",
        "daily_delta_scan",
        "futures_fundamentals_delta_scan",
        "data_source_refresh",
    }
    assert plan["resource_audit"]["full_market_deep_data"] is False
    assert plan["resource_audit"]["deep_research_limit"] == 3

    second_plan, _ = build_scheduler_plan(
        schedule,
        state,
        now="2026-07-21T09:00:00+08:00",
    )
    assert second_plan["task_ids"] == []


def test_event_tasks_are_deduplicated_and_company_pool_is_event_scoped():
    schedule = build_default_schedule()
    state = build_scheduler_state(schedule)
    event = {
        "event_id": "event-001",
        "event_type": "industry_membership_changed",
        "occurred_at": "2026-07-21T08:30:00+08:00",
        "source": "exchange",
        "industry_id": "881273",
        "payload_ref": "evidence-001",
    }

    plan, state = build_scheduler_plan(
        schedule, state, [event], now="2026-07-21T09:00:00+08:00"
    )
    assert {task["task_type"] for task in plan["tasks"]} == {
        "event_triggered_scan",
        "company_pool_refresh",
        "industry_radar_refresh",
        "daily_delta_scan",
        "futures_fundamentals_delta_scan",
        "data_source_refresh",
    }
    assert sum(task["event_id"] == "event-001" for task in plan["tasks"]) == 2

    first_task_id = next(
        task["task_id"]
        for task in plan["tasks"]
        if task["task_type"] == "event_triggered_scan"
    )
    first_result = execute_scheduler_plan(
        state,
        {**plan, "task_ids": [first_task_id]},
        {"event_triggered_scan": lambda _task: {"status": "SUCCESS"}},
        now="2026-07-21T09:00:00+08:00",
    )
    assert first_result["state"]["events"]["event-001"]["status"] == "SCHEDULED"
    remaining_plan, _ = build_scheduler_plan(
        schedule, first_result["state"], now="2026-07-21T09:00:00+08:00"
    )
    assert any(
        task["task_type"] == "company_pool_refresh"
        for task in remaining_plan["tasks"]
    )

    repeated_plan, _ = build_scheduler_plan(
        schedule, first_result["state"], [event], now="2026-07-21T09:00:00+08:00"
    )
    assert repeated_plan["new_event_ids"] == []
    assert any(task["event_id"] == "event-001" for task in repeated_plan["tasks"])


def test_retry_then_degraded_success_preserves_task_and_event_state():
    schedule = build_default_schedule()
    state = build_scheduler_state(schedule)
    event = {
        "event_id": "event-002",
        "event_type": "earnings_report",
        "occurred_at": "2026-07-21T08:30:00+08:00",
        "source": "company-disclosure",
        "company_id": "600519",
    }
    plan, state = build_scheduler_plan(
        schedule, state, [event], now="2026-07-21T09:00:00+08:00"
    )
    event_task_id = next(
        task["task_id"] for task in plan["tasks"] if task["event_id"] == "event-002"
    )

    calls = {event_task_id: 0}

    def handler(task):
        calls[task["task_id"]] += 1
        if calls[task["task_id"]] == 1:
            raise RetryableTaskError("temporary source outage")
        return {"status": "INSUFFICIENT", "reason": "source fields incomplete"}

    handlers = {"event_triggered_scan": handler}
    result = execute_scheduler_plan(state, plan, handlers, now="2026-07-21T09:00:00+08:00")
    task = result["state"]["tasks"][event_task_id]
    assert task["status"] == "RETRY_WAIT"
    assert result["state"]["events"]["event-002"]["status"] == "FAILED_RETRYABLE"
    assert result["state"]["jobs"]["event-triggered-scan"]["last_failure_at"]

    retry_plan, retry_state = build_scheduler_plan(
        schedule, result["state"], now="2026-07-21T09:00:30+08:00"
    )
    assert event_task_id not in retry_plan["task_ids"]
    retry_plan, retry_state = build_scheduler_plan(
        schedule, result["state"], now="2026-07-21T09:02:00+08:00"
    )
    assert event_task_id in retry_plan["task_ids"]
    retry_result = execute_scheduler_plan(
        retry_state, retry_plan, handlers, now="2026-07-21T09:02:00+08:00"
    )
    assert retry_result["state"]["tasks"][event_task_id]["status"] == "SUCCEEDED_DEGRADED"
    assert retry_result["state"]["events"]["event-002"]["status"] == "PROCESSED"


def test_permanent_failure_does_not_retry():
    schedule = build_default_schedule()
    state = build_scheduler_state(schedule)
    plan, state = build_scheduler_plan(schedule, state, now="2026-07-21T09:00:00+08:00")

    def handler(_task):
        raise PermanentTaskError("invalid local configuration")

    task_id = plan["task_ids"][0]
    result = execute_scheduler_plan(
        state,
        {**plan, "task_ids": [task_id]},
        {"industry_radar_refresh": handler},
        now="2026-07-21T09:00:00+08:00",
    )
    assert result["state"]["tasks"][task_id]["status"] == "FAILED_FINAL"
