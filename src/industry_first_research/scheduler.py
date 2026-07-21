"""Auditable local scheduling for bounded research refreshes."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any


SCHEDULER_SCHEMA_VERSION = "research-scheduler.v1"
SCHEDULE_RULE_VERSION = "research-scheduler-rules.v1"
TASK_TYPES = (
    "industry_radar_refresh",
    "daily_delta_scan",
    "event_triggered_scan",
    "company_pool_refresh",
)
_INTERVAL_TASK_TYPES = {"industry_radar_refresh", "daily_delta_scan"}
_EVENT_TASK_TYPES = {"event_triggered_scan", "company_pool_refresh"}
_EVENT_TYPES = {
    "announcement_correction",
    "buyback",
    "customer_certification",
    "earnings_preview",
    "earnings_report",
    "industry_data_release",
    "industry_membership_changed",
    "industry_selected",
    "major_contract",
    "merger_acquisition",
    "policy_change",
    "price_shock",
    "rights_issue_or_placement",
    "shutdown_or_bankruptcy",
    "technology_route_change",
}
_DEGRADED_RESULT_STATUSES = {"DEGRADED", "PARTIAL", "INSUFFICIENT", "BLOCKED"}
_RETRYABLE_EXCEPTIONS = (ConnectionError, TimeoutError)


class SchedulerError(ValueError):
    """Raised when a scheduler configuration or state is invalid."""


class RetryableTaskError(RuntimeError):
    """A task failed temporarily and may be retried."""


class PermanentTaskError(RuntimeError):
    """A task failed for a reason that should not be retried."""


def build_default_schedule(*, schedule_id: str = "default", as_of: str = "") -> dict[str, Any]:
    """Return the bounded local schedule described by the design document."""

    if not schedule_id.strip():
        raise SchedulerError("schedule_id must not be empty")
    return {
        "schema_version": SCHEDULER_SCHEMA_VERSION,
        "schedule_id": schedule_id,
        "rule_version": SCHEDULE_RULE_VERSION,
        "as_of": as_of,
        "policy": {
            "max_tasks_per_tick": 8,
            "max_selected_industries": 3,
            "company_pool_size": 30,
            "candidate_capacity": 15,
            "watch_capacity": 60,
            "deep_research_limit": 3,
            "allow_full_market_deep_data": False,
            "read_only": True,
            "execution_enabled": False,
        },
        "jobs": [
            {
                "job_id": "industry-radar-refresh",
                "task_type": "industry_radar_refresh",
                "enabled": True,
                "trigger": "interval",
                "interval_seconds": 86400,
                "max_attempts": 3,
                "backoff_seconds": [60, 300, 900],
                "scope": {"radar_limit": 50},
            },
            {
                "job_id": "daily-delta-scan",
                "task_type": "daily_delta_scan",
                "enabled": True,
                "trigger": "interval",
                "interval_seconds": 86400,
                "max_attempts": 3,
                "backoff_seconds": [60, 300, 900],
                "scope": {
                    "candidate_capacity": 15,
                    "watch_capacity": 60,
                    "deep_research_limit": 3,
                },
            },
            {
                "job_id": "event-triggered-scan",
                "task_type": "event_triggered_scan",
                "enabled": True,
                "trigger": "event",
                "event_types": sorted(_EVENT_TYPES),
                "max_attempts": 3,
                "backoff_seconds": [60, 300, 900],
                "scope": {"deep_research_limit": 3},
            },
            {
                "job_id": "company-pool-refresh",
                "task_type": "company_pool_refresh",
                "enabled": True,
                "trigger": "event",
                "event_types": ["industry_membership_changed", "industry_selected"],
                "max_attempts": 3,
                "backoff_seconds": [60, 300, 900],
                "scope": {"company_pool_size": 30},
            },
        ],
    }


def build_scheduler_state(schedule: Mapping[str, Any]) -> dict[str, Any]:
    """Create an empty state file for a validated schedule."""

    _validate_schedule(schedule)
    return {
        "schema_version": SCHEDULER_SCHEMA_VERSION,
        "schedule_id": str(schedule["schedule_id"]),
        "rule_version": str(schedule.get("rule_version") or SCHEDULE_RULE_VERSION),
        "updated_at": "",
        "last_tick_at": "",
        "jobs": {
            str(job["job_id"]): {
                "last_scheduled_at": "",
                "last_success_at": "",
                "last_failure_at": "",
                "last_task_id": "",
            }
            for job in schedule["jobs"]
        },
        "tasks": {},
        "events": {},
        "audit_log": [],
        "policy": {
            "read_only": True,
            "execution_enabled": False,
        },
    }


def build_scheduler_plan(
    schedule: Mapping[str, Any],
    state: Mapping[str, Any] | None = None,
    incoming_events: Sequence[Mapping[str, Any]] = (),
    *,
    now: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Plan one idempotent scheduler tick and return the updated state.

    Planning records events and task metadata but never fetches data, calls an LLM,
    creates a decision snapshot, or changes an investment conclusion. A later
    executor can use the returned task records with registered local handlers.
    """

    _validate_schedule(schedule)
    current = _parse_time(now) if now else datetime.now(timezone.utc)
    current_iso = current.isoformat()
    next_state = _normalise_state(schedule, state)
    next_state["updated_at"] = current_iso
    next_state["last_tick_at"] = current_iso
    new_event_ids: list[str] = []
    for raw_event in incoming_events:
        event = _normalise_event(raw_event)
        event_id = event["event_id"]
        existing = next_state["events"].get(event_id)
        if existing is None:
            next_state["events"][event_id] = {
                **event,
                "status": "RECEIVED",
                "scheduled_task_ids": [],
                "processed_at": "",
            }
            new_event_ids.append(event_id)
        elif _event_fingerprint(existing) != _event_fingerprint(event):
            raise SchedulerError(f"immutable event_id changed: {event_id}")

    task_ids: list[str] = []
    policy = schedule["policy"]
    for job in schedule["jobs"]:
        if not job.get("enabled", True):
            continue
        task_type = str(job["task_type"])
        if job["trigger"] == "interval" and _interval_due(
            next_state["jobs"][str(job["job_id"])], job, current
        ):
            task = _ensure_task(next_state, schedule, job, current, event=None)
            task_ids.append(task["task_id"])
            next_state["jobs"][str(job["job_id"])] = {
                **next_state["jobs"][str(job["job_id"])],
                "last_scheduled_at": current_iso,
                "last_task_id": task["task_id"],
            }
        elif job["trigger"] == "event":
            for event_id, event in next_state["events"].items():
                if event.get("status") not in {
                    "RECEIVED",
                    "SCHEDULED",
                    "FAILED_RETRYABLE",
                }:
                    continue
                if str(event.get("event_type")) not in set(job.get("event_types") or ()):
                    continue
                existing_task = next_state["tasks"].get(
                    _task_id(str(schedule["schedule_id"]), str(job["job_id"]), str(event["event_id"]))
                )
                task = _ensure_task(next_state, schedule, job, current, event=event)
                if existing_task is not None and existing_task.get("status") not in {
                    "PENDING",
                    "RETRY_WAIT",
                    "DEFERRED",
                }:
                    continue
                if _parse_time(str(task.get("not_before") or "")) > current:
                    continue
                task_ids.append(task["task_id"])
                scheduled = list(event.get("scheduled_task_ids") or [])
                if task["task_id"] not in scheduled:
                    scheduled.append(task["task_id"])
                event["scheduled_task_ids"] = scheduled
                event["status"] = "SCHEDULED"

    # Retries are selected independently of new jobs and remain bounded by the tick cap.
    for task_id, task in next_state["tasks"].items():
        if task.get("status") not in {"RETRY_WAIT", "DEFERRED"}:
            continue
        not_before = _parse_time(str(task.get("not_before") or ""))
        if not_before <= current:
            task_ids.append(task_id)

    selected_task_ids = _dedupe(task_ids)
    max_tasks = int(policy["max_tasks_per_tick"])
    deferred_task_ids = selected_task_ids[max_tasks:]
    selected_task_ids = selected_task_ids[:max_tasks]
    for task_id in deferred_task_ids:
        task = next_state["tasks"].get(task_id)
        if task is not None:
            task["status"] = "DEFERRED"
            task["deferred_count"] = int(task.get("deferred_count") or 0) + 1
            task["last_deferred_at"] = current_iso

    plan_id = _plan_id(str(schedule["schedule_id"]), current_iso, selected_task_ids)
    plan = {
        "schema_version": SCHEDULER_SCHEMA_VERSION,
        "plan_id": plan_id,
        "schedule_id": str(schedule["schedule_id"]),
        "rule_version": str(schedule.get("rule_version") or SCHEDULE_RULE_VERSION),
        "created_at": current_iso,
        "new_event_ids": new_event_ids,
        "task_ids": selected_task_ids,
        "deferred_task_ids": deferred_task_ids,
        "tasks": [deepcopy(next_state["tasks"][task_id]) for task_id in selected_task_ids],
        "resource_audit": {
            "max_tasks_per_tick": max_tasks,
            "task_count": len(selected_task_ids),
            "deferred_count": len(deferred_task_ids),
            "full_market_deep_data": False,
            "max_selected_industries": int(policy["max_selected_industries"]),
            "company_pool_size": int(policy["company_pool_size"]),
            "candidate_capacity": int(policy["candidate_capacity"]),
            "watch_capacity": int(policy["watch_capacity"]),
            "deep_research_limit": int(policy["deep_research_limit"]),
        },
        "policy": {
            "read_only": True,
            "execution_enabled": False,
            "investment_conclusion": False,
            "decision_snapshot_created": False,
        },
    }
    return plan, next_state


def execute_scheduler_plan(
    state: Mapping[str, Any],
    plan: Mapping[str, Any],
    handlers: Mapping[str, Callable[[Mapping[str, Any]], Mapping[str, Any] | None]],
    *,
    now: str = "",
) -> dict[str, Any]:
    """Execute planned tasks with retry and degradation bookkeeping.

    Handlers are deliberately injected. This keeps scheduling independent from
    network adapters and allows the same state machine to run in tests, launchd,
    cron, or a future application service.
    """

    current = _parse_time(now) if now else datetime.now(timezone.utc)
    next_state = deepcopy(dict(state))
    _validate_state(next_state)
    if plan.get("schema_version") != SCHEDULER_SCHEMA_VERSION:
        raise SchedulerError("plan must be research-scheduler.v1")
    results: list[dict[str, Any]] = []
    for task_id in plan.get("task_ids") or []:
        task = next_state["tasks"].get(str(task_id))
        if task is None:
            raise SchedulerError(f"plan references unknown task: {task_id}")
        if task.get("status") not in {"PENDING", "RETRY_WAIT", "DEFERRED"}:
            continue
        not_before = _parse_time(str(task.get("not_before") or ""))
        if not_before > current:
            continue
        handler = handlers.get(str(task["task_type"]))
        if handler is None:
            _record_failure(
                next_state,
                task,
                PermanentTaskError(f"no handler registered: {task['task_type']}"),
                current,
            )
            results.append(_execution_result(task))
            continue

        task["status"] = "RUNNING"
        task["started_at"] = current.isoformat()
        task["attempts"] = int(task.get("attempts") or 0) + 1
        try:
            raw_result = handler(task)
            result = dict(raw_result or {})
            result_status = str(result.get("status") or "SUCCESS").upper()
            if result_status in _DEGRADED_RESULT_STATUSES:
                task["status"] = "SUCCEEDED_DEGRADED"
                task["degradation"] = result_status
            else:
                task["status"] = "SUCCEEDED"
                task["degradation"] = ""
            task["result_status"] = result_status
            task["result"] = result
            task["finished_at"] = current.isoformat()
            task["not_before"] = ""
            _mark_event_after_success(next_state, task, current)
            _mark_job_success(next_state, task, current)
        except Exception as error:
            _record_failure(next_state, task, error, current)
        results.append(_execution_result(task))

    next_state["updated_at"] = current.isoformat()
    next_state.setdefault("audit_log", []).append(
        {
            "at": current.isoformat(),
            "action": "EXECUTE_PLAN",
            "plan_id": str(plan.get("plan_id") or ""),
            "task_ids": [str(task_id) for task_id in plan.get("task_ids") or []],
        }
    )
    return {
        "schema_version": SCHEDULER_SCHEMA_VERSION,
        "plan_id": str(plan.get("plan_id") or ""),
        "executed_at": current.isoformat(),
        "results": results,
        "state": next_state,
        "policy": {
            "read_only": True,
            "execution_enabled": False,
            "investment_conclusion": False,
        },
    }


def _ensure_task(
    state: dict[str, Any],
    schedule: Mapping[str, Any],
    job: Mapping[str, Any],
    current: datetime,
    *,
    event: Mapping[str, Any] | None,
) -> dict[str, Any]:
    period = current.date().isoformat() if event is None else str(event["event_id"])
    scope = _merged_scope(schedule["policy"], job.get("scope") or {})
    task_id = _task_id(str(schedule["schedule_id"]), str(job["job_id"]), period)
    existing = state["tasks"].get(task_id)
    if existing is not None:
        return existing
    task = {
        "schema_version": "research-task.v1",
        "task_id": task_id,
        "job_id": str(job["job_id"]),
        "task_type": str(job["task_type"]),
        "trigger": str(job["trigger"]),
        "event_id": str(event.get("event_id") or "") if event else "",
        "event_type": str(event.get("event_type") or "") if event else "",
        "event": deepcopy(dict(event)) if event else {},
        "status": "PENDING",
        "attempts": 0,
        "max_attempts": int(job.get("max_attempts") or 1),
        "backoff_seconds": [int(value) for value in job.get("backoff_seconds") or []],
        "not_before": current.isoformat(),
        "created_at": current.isoformat(),
        "started_at": "",
        "finished_at": "",
        "last_error": "",
        "degradation": "",
        "deferred_count": 0,
        "scope": scope,
        "policy": {
            "read_only": True,
            "execution_enabled": False,
            "full_market_deep_data": False,
        },
    }
    state["tasks"][task_id] = task
    return task


def _record_failure(
    state: dict[str, Any], task: dict[str, Any], error: Exception, current: datetime
) -> None:
    retryable = isinstance(error, _RETRYABLE_EXCEPTIONS + (RetryableTaskError,))
    if isinstance(error, PermanentTaskError):
        retryable = False
    task["last_error"] = f"{type(error).__name__}: {error}"
    task["finished_at"] = current.isoformat()
    if retryable and int(task.get("attempts") or 0) < int(task.get("max_attempts") or 1):
        backoffs = list(task.get("backoff_seconds") or [])
        attempt_index = max(0, int(task.get("attempts") or 1) - 1)
        delay = int(backoffs[min(attempt_index, len(backoffs) - 1)]) if backoffs else 0
        task["status"] = "RETRY_WAIT"
        task["not_before"] = (current + timedelta(seconds=delay)).isoformat()
    else:
        task["status"] = "FAILED_FINAL"
        task["not_before"] = ""
    _mark_job_failure(state, task, current)
    if task.get("event_id"):
        event = state["events"].get(str(task["event_id"]))
        if event is not None:
            event["last_error"] = task["last_error"]
            _refresh_event_status(state, str(task["event_id"]))


def _mark_event_after_success(state: dict[str, Any], task: Mapping[str, Any], current: datetime) -> None:
    event_id = str(task.get("event_id") or "")
    if not event_id:
        return
    event = state["events"].get(event_id)
    if event is not None:
        _refresh_event_status(state, event_id, current)


def _refresh_event_status(
    state: dict[str, Any], event_id: str, current: datetime | None = None
) -> None:
    event = state["events"].get(event_id)
    if event is None:
        return
    tasks = [
        task
        for task in state["tasks"].values()
        if str(task.get("event_id") or "") == event_id
    ]
    if not tasks:
        event["status"] = "RECEIVED"
        return
    statuses = {str(task.get("status") or "") for task in tasks}
    if statuses & {"PENDING", "RUNNING", "DEFERRED"}:
        event["status"] = "SCHEDULED"
    elif "RETRY_WAIT" in statuses:
        event["status"] = "FAILED_RETRYABLE"
    elif "FAILED_FINAL" in statuses:
        event["status"] = "FAILED_FINAL"
    elif statuses <= {"SUCCEEDED", "SUCCEEDED_DEGRADED"}:
        event["status"] = "PROCESSED"
        if current is not None:
            event["processed_at"] = current.isoformat()


def _mark_job_success(state: dict[str, Any], task: Mapping[str, Any], current: datetime) -> None:
    job_id = str(task.get("job_id") or "")
    job = state["jobs"].get(job_id)
    if job is not None:
        job["last_success_at"] = current.isoformat()


def _mark_job_failure(state: dict[str, Any], task: Mapping[str, Any], current: datetime) -> None:
    job_id = str(task.get("job_id") or "")
    job = state["jobs"].get(job_id)
    if job is not None:
        job["last_failure_at"] = current.isoformat()


def _execution_result(task: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "task_id": str(task["task_id"]),
        "task_type": str(task["task_type"]),
        "status": str(task["status"]),
        "attempts": int(task.get("attempts") or 0),
        "result_status": str(task.get("result_status") or ""),
        "last_error": str(task.get("last_error") or ""),
        "degradation": str(task.get("degradation") or ""),
    }


def _normalise_event(raw_event: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw_event, Mapping):
        raise SchedulerError("each event must be an object")
    event_type = str(raw_event.get("event_type") or "").strip()
    occurred_at = str(raw_event.get("occurred_at") or "").strip()
    source = str(raw_event.get("source") or "").strip()
    if event_type not in _EVENT_TYPES:
        raise SchedulerError(f"unsupported event_type: {event_type or '<empty>'}")
    if not occurred_at or not source:
        raise SchedulerError("event occurred_at and source are required")
    _parse_time(occurred_at)
    event_id = str(raw_event.get("event_id") or "").strip()
    base = {
        "event_type": event_type,
        "occurred_at": occurred_at,
        "source": source,
        "industry_id": str(raw_event.get("industry_id") or ""),
        "company_id": str(raw_event.get("company_id") or ""),
        "severity": str(raw_event.get("severity") or "NORMAL"),
        "evidence_ids": [str(value) for value in raw_event.get("evidence_ids") or []],
        "payload_ref": str(raw_event.get("payload_ref") or ""),
        "payload": deepcopy(dict(raw_event.get("payload") or {})),
    }
    if not isinstance(raw_event.get("payload") or {}, Mapping):
        raise SchedulerError("event payload must be an object")
    if not event_id:
        event_id = "event-" + _event_fingerprint(base)[:20]
    return {"event_id": event_id, **base}


def _validate_schedule(schedule: Mapping[str, Any]) -> None:
    if not isinstance(schedule, Mapping) or schedule.get("schema_version") != SCHEDULER_SCHEMA_VERSION:
        raise SchedulerError("schedule must be research-scheduler.v1")
    if not str(schedule.get("schedule_id") or "").strip():
        raise SchedulerError("schedule_id is required")
    policy = schedule.get("policy")
    if not isinstance(policy, Mapping):
        raise SchedulerError("schedule policy is required")
    _validate_limits(policy)
    jobs = schedule.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise SchedulerError("schedule jobs must be a non-empty list")
    seen: set[str] = set()
    for job in jobs:
        if not isinstance(job, Mapping):
            raise SchedulerError("each schedule job must be an object")
        job_id = str(job.get("job_id") or "").strip()
        task_type = str(job.get("task_type") or "").strip()
        trigger = str(job.get("trigger") or "").strip()
        if not job_id or job_id in seen:
            raise SchedulerError(f"duplicate or empty job_id: {job_id or '<empty>'}")
        if task_type not in TASK_TYPES:
            raise SchedulerError(f"unsupported task_type: {task_type or '<empty>'}")
        if trigger not in {"interval", "event"}:
            raise SchedulerError(f"unsupported trigger: {trigger or '<empty>'}")
        if task_type in _INTERVAL_TASK_TYPES and trigger != "interval":
            raise SchedulerError(f"{task_type} must use interval trigger")
        if task_type in _EVENT_TASK_TYPES and trigger != "event":
            raise SchedulerError(f"{task_type} must use event trigger")
        if trigger == "interval" and int(job.get("interval_seconds") or 0) <= 0:
            raise SchedulerError(f"{job_id} interval_seconds must be positive")
        if int(job.get("max_attempts") or 0) <= 0:
            raise SchedulerError(f"{job_id} max_attempts must be positive")
        event_types = job.get("event_types") or []
        if trigger == "event" and (
            not isinstance(event_types, list)
            or not event_types
            or any(str(value) not in _EVENT_TYPES for value in event_types)
        ):
            raise SchedulerError(f"{job_id} has invalid event_types")
        seen.add(job_id)


def _validate_limits(policy: Mapping[str, Any]) -> None:
    limits = (
        "max_tasks_per_tick",
        "max_selected_industries",
        "company_pool_size",
        "candidate_capacity",
        "watch_capacity",
        "deep_research_limit",
    )
    for name in limits:
        value = int(policy.get(name) or 0)
        if value <= 0:
            raise SchedulerError(f"policy {name} must be positive")
    if int(policy["max_selected_industries"]) > 3:
        raise SchedulerError("max_selected_industries may not exceed 3")
    if int(policy["company_pool_size"]) > 30:
        raise SchedulerError("company_pool_size may not exceed 30")
    if int(policy["candidate_capacity"]) > 15:
        raise SchedulerError("candidate_capacity may not exceed 15")
    if int(policy["watch_capacity"]) > 60:
        raise SchedulerError("watch_capacity may not exceed 60")
    if int(policy["deep_research_limit"]) > 3:
        raise SchedulerError("deep_research_limit may not exceed 3")
    if policy.get("allow_full_market_deep_data") is True:
        raise SchedulerError("full-market deep data is disabled by the default scheduler boundary")


def _normalise_state(schedule: Mapping[str, Any], state: Mapping[str, Any] | None) -> dict[str, Any]:
    if state is None:
        return build_scheduler_state(schedule)
    next_state = deepcopy(dict(state))
    _validate_state(next_state)
    if str(next_state.get("schedule_id")) != str(schedule["schedule_id"]):
        raise SchedulerError("state schedule_id does not match schedule")
    for job in schedule["jobs"]:
        next_state["jobs"].setdefault(
            str(job["job_id"]),
            {"last_scheduled_at": "", "last_success_at": "", "last_failure_at": "", "last_task_id": ""},
        )
    return next_state


def _validate_state(state: Mapping[str, Any]) -> None:
    if not isinstance(state, Mapping) or state.get("schema_version") != SCHEDULER_SCHEMA_VERSION:
        raise SchedulerError("state must be research-scheduler.v1")
    if not str(state.get("schedule_id") or "").strip():
        raise SchedulerError("state schedule_id must be non-empty")
    for key in ("jobs", "tasks", "events"):
        if key not in state or not isinstance(state[key], Mapping):
            raise SchedulerError(f"state {key} must be an object")


def _interval_due(job_state: Mapping[str, Any], job: Mapping[str, Any], current: datetime) -> bool:
    last = str(job_state.get("last_scheduled_at") or "")
    if not last:
        return True
    return current >= _parse_time(last) + timedelta(seconds=int(job["interval_seconds"]))


def _merged_scope(policy: Mapping[str, Any], scope: Mapping[str, Any]) -> dict[str, Any]:
    merged = {
        "max_selected_industries": int(policy["max_selected_industries"]),
        "company_pool_size": int(policy["company_pool_size"]),
        "candidate_capacity": int(policy["candidate_capacity"]),
        "watch_capacity": int(policy["watch_capacity"]),
        "deep_research_limit": int(policy["deep_research_limit"]),
        "full_market_deep_data": False,
    }
    merged.update(dict(scope))
    _validate_limits({**policy, **merged})
    if merged.get("full_market_deep_data") is True:
        raise SchedulerError("task scope cannot enable full-market deep data")
    return merged


def _parse_time(value: str) -> datetime:
    text = value.strip()
    if not text:
        raise SchedulerError("timestamp must not be empty")
    if len(text) == 10:
        text += "T00:00:00+00:00"
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise SchedulerError(f"invalid timestamp: {value}") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _task_id(schedule_id: str, job_id: str, period: str) -> str:
    return f"task-{schedule_id}-{job_id}-{period}".replace("/", "-")


def _plan_id(schedule_id: str, current_iso: str, task_ids: Sequence[str]) -> str:
    digest = hashlib.sha256(
        json.dumps([schedule_id, current_iso, list(task_ids)], ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]
    return f"scheduler-plan-{schedule_id}-{digest}"


def _event_fingerprint(event: Mapping[str, Any]) -> str:
    value = {
        key: event.get(key)
        for key in (
            "event_type",
            "occurred_at",
            "source",
            "industry_id",
            "company_id",
            "severity",
            "evidence_ids",
            "payload_ref",
            "payload",
        )
    }
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
