"""Plan research depth and audit optional model execution.

The planner is local and deterministic.  It never calls a model itself.  A
future model runner can consume the plan and record each call with
``build_llm_run`` while the rest of the research platform remains usable in
``LOCAL_ONLY`` mode.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

from .task_resolution import TaskResolutionError, validate_research_task


RESEARCH_REQUEST_SCHEMA_VERSION = "research-request.v1"
RESEARCH_EXECUTION_PLAN_SCHEMA_VERSION = "research-execution-plan.v1"
LLM_RUN_SCHEMA_VERSION = "llm-run.v1"
RULE_VERSION = "research-execution-rules.v1"

DEPTHS = {"QUICK", "STANDARD", "DEEP"}
EXECUTION_MODES = {"LOCAL_ONLY", "LLM_ASSISTED", "MANUAL_WEB_AI"}
TASK_TYPES = {
    "company_research",
    "industry_research",
    "futures_research",
    "opportunity_discovery",
    "thesis_check",
    "public_draft",
}
MODEL_ELIGIBLE_TASKS = {
    "product_application_semantics",
    "industry_relationship_reasoning",
    "evidence_conflict_explanation",
    "conclusion_synthesis",
    "adversarial_review",
}
DETERMINISTIC_TASKS = {
    "data_collection",
    "freshness_check",
    "difference_detection",
    "market_data_calculation",
    "financial_ratio_calculation",
    "scorecard_calculation",
    "cycle_series_calculation",
    "market_structure_calculation",
    "valuation_formula",
    "simulation_ledger",
    "benchmark_attribution",
}


class ResearchExecutionError(ValueError):
    """Raised when a research execution object is unsafe or incomplete."""


def build_research_request(
    payload: Mapping[str, Any], *, request_id: str = ""
) -> dict[str, Any]:
    """Normalize a user research request without selecting a security or trade."""

    if not isinstance(payload, Mapping):
        raise ResearchExecutionError("research request must be a JSON object")
    if payload.get("schema_version") == "research-task-resolution.v1":
        try:
            task = validate_research_task(payload)
        except TaskResolutionError as error:
            raise ResearchExecutionError(str(error)) from error
        if task.get("status") not in {"READY", "PARTIAL"}:
            raise ResearchExecutionError(
                "research task requires identity confirmation before execution planning"
            )
        payload = {
            **task,
            "requested_execution_mode": str(
                task.get("requested_execution_mode") or "LOCAL_ONLY"
            ),
        }
    task_type = str(payload.get("task_type") or "").strip().lower()
    if task_type not in TASK_TYPES:
        raise ResearchExecutionError(f"unsupported task_type: {task_type or '<empty>'}")
    subject_type = str(payload.get("subject_type") or "").strip().lower()
    if subject_type not in {
        "listed_company",
        "industry",
        "futures_variety",
        "futures_contract",
        "continuous_series",
        "opportunity_scan",
    }:
        raise ResearchExecutionError(f"unsupported subject_type: {subject_type or '<empty>'}")
    subject_identifier = str(
        payload.get("identifier") or payload.get("subject_id") or ""
    ).strip()
    if not subject_identifier and task_type == "opportunity_discovery":
        subject_identifier = "opportunity-discovery"
    if not subject_identifier:
        raise ResearchExecutionError("identifier or subject_id is required")
    research_as_of = str(payload.get("research_as_of") or payload.get("as_of") or "").strip()
    if not research_as_of:
        raise ResearchExecutionError("research_as_of is required")
    _parse_time(research_as_of)
    requested_depth = str(payload.get("requested_depth") or "STANDARD").strip().upper()
    if requested_depth not in DEPTHS:
        raise ResearchExecutionError(f"unsupported requested_depth: {requested_depth}")
    requested_mode = str(payload.get("execution_mode") or "LOCAL_ONLY").strip().upper()
    if requested_mode not in EXECUTION_MODES:
        raise ResearchExecutionError(f"unsupported execution_mode: {requested_mode}")
    budget = _budget(payload.get("budget") or {})
    identifier = request_id.strip() or f"request-{_hash_payload({'task': task_type, 'subject': subject_identifier, 'as_of': research_as_of})[:20]}"
    return {
        "schema_version": RESEARCH_REQUEST_SCHEMA_VERSION,
        "request_id": identifier,
        "task_type": task_type,
        "subject_type": subject_type,
        "identifier": subject_identifier,
        "subject_id": str(payload.get("subject_id") or ""),
        "research_as_of": research_as_of,
        "simulation_mode": bool(payload.get("simulation_mode", True)),
        "execution_enabled": False,
        "requested_depth": requested_depth,
        "requested_execution_mode": requested_mode,
        "budget": budget,
        "modules": _string_list(payload.get("modules")),
        "affected_modules": _string_list(payload.get("affected_modules")),
        "previous_research_id": str(payload.get("previous_research_id") or ""),
        "evidence_manifest_hash": str(payload.get("evidence_manifest_hash") or ""),
        "asset_ids": _string_list(payload.get("asset_ids")),
        "capability_gap_id": str(payload.get("capability_gap_id") or ""),
        "new_development": bool(payload.get("new_development", False)),
        "rule_version": RULE_VERSION,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "policy": _policy(),
    }


def build_research_execution_plan(
    request: Mapping[str, Any],
    *,
    available_model: bool = False,
    used_input_tokens: int = 0,
    used_output_tokens: int = 0,
    prior_differences: Sequence[Mapping[str, Any]] = (),
    plan_id: str = "",
) -> dict[str, Any]:
    """Choose a bounded local/model plan and make degradation explicit."""

    normalized = (
        dict(request)
        if request.get("schema_version") == RESEARCH_REQUEST_SCHEMA_VERSION
        else build_research_request(request)
    )
    _validate_request(normalized)
    if normalized.get("new_development") is True and not str(
        normalized.get("capability_gap_id") or ""
    ).strip():
        raise ResearchExecutionError(
            "new development requires capability_gap_id"
        )
    requested_depth = normalized["requested_depth"]
    requested_mode = normalized["requested_execution_mode"]
    budget = normalized["budget"]
    budget_exhausted = (
        int(used_input_tokens) + int(used_output_tokens) >= int(budget["max_tokens"])
        or float(budget["used_cost"]) >= float(budget["max_cost"])
    )
    if requested_mode == "MANUAL_WEB_AI":
        effective_mode = "MANUAL_WEB_AI"
        model_available = False
        degradation_reason = "网页 AI 只能人工导入，不能由本系统自动调用"
    elif requested_mode == "LLM_ASSISTED" and available_model and not budget_exhausted:
        effective_mode = "LLM_ASSISTED"
        model_available = True
        degradation_reason = ""
    else:
        effective_mode = "LOCAL_ONLY"
        model_available = False
        degradation_reason = (
            "requested model unavailable"
            if requested_mode == "LLM_ASSISTED" and not budget_exhausted
            else "budget exhausted; deterministic local path retained"
            if budget_exhausted
            else "local-only mode requested"
        )

    modules = _planned_modules(normalized, prior_differences)
    tasks = []
    for module in modules:
        tasks.append(
            {
                "task_id": f"local-{module}",
                "module": module,
                "execution": "LOCAL_DETERMINISTIC",
                "model_required": False,
                "reason": "data, rules, formulas, snapshots and history remain local",
            }
        )
    model_tasks = _model_tasks(normalized, modules)
    if effective_mode == "LLM_ASSISTED":
        tasks.extend(
            {
                "task_id": f"model-{task}",
                "module": task,
                "execution": "MODEL_OPTIONAL",
                "model_required": True,
                "reason": "semantic task cannot be safely completed by deterministic rules alone",
            }
            for task in model_tasks
        )
    elif model_tasks:
        tasks.append(
            {
                "task_id": "model-deferred-review",
                "module": "model_deferred_review",
                "execution": "DEFERRED",
                "model_required": True,
                "deferred_tasks": model_tasks,
                "reason": degradation_reason or "model task deferred",
            }
        )

    return {
        "schema_version": RESEARCH_EXECUTION_PLAN_SCHEMA_VERSION,
        "plan_id": plan_id.strip() or f"plan-{normalized['request_id']}-{_hash_payload({'modules': modules, 'mode': effective_mode})[:12]}",
        "request_id": normalized["request_id"],
        "research_id": str(normalized.get("previous_research_id") or normalized["request_id"]),
        "task_type": normalized["task_type"],
        "subject_type": normalized["subject_type"],
        "identifier": normalized["identifier"],
        "research_as_of": normalized["research_as_of"],
        "requested_depth": requested_depth,
        "effective_depth": requested_depth,
        "requested_execution_mode": requested_mode,
        "effective_execution_mode": effective_mode,
        "model_available": model_available,
        "budget_exhausted": budget_exhausted,
        "degradation_reason": degradation_reason,
        "modules": modules,
        "tasks": tasks,
        "deferred_model_tasks": model_tasks if effective_mode != "LLM_ASSISTED" else [],
        "prior_differences": [dict(item) for item in prior_differences if isinstance(item, Mapping)],
        "token_budget": {
            **budget,
            "used_input_tokens": int(used_input_tokens),
            "used_output_tokens": int(used_output_tokens),
            "remaining_tokens": max(0, int(budget["max_tokens"]) - int(used_input_tokens) - int(used_output_tokens)),
            "remaining_cost": max(0.0, float(budget["max_cost"]) - float(budget["used_cost"])),
        },
        "last_locked_conclusion_policy": {
            "local_only_can_project_facts_and_rules": True,
            "local_only_cannot_rewrite_ai_conclusion": True,
            "previous_locked_conclusion_id": str(normalized.get("previous_research_id") or "") or None,
        },
        "execution_enabled": False,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "rule_version": RULE_VERSION,
        "policy": _policy(),
    }


def build_llm_run(
    payload: Mapping[str, Any], *, llm_run_id: str = ""
) -> dict[str, Any]:
    """Record one optional model call; this function does not make the call."""

    if not isinstance(payload, Mapping):
        raise ResearchExecutionError("llm run must be a JSON object")
    research_id = str(payload.get("research_id") or "").strip()
    if not research_id:
        raise ResearchExecutionError("research_id is required")
    execution_mode = str(payload.get("execution_mode") or "").strip().upper()
    if execution_mode != "LLM_ASSISTED":
        raise ResearchExecutionError("llm_runs must use LLM_ASSISTED execution_mode")
    trigger_reason = str(payload.get("trigger_reason") or "").strip()
    if not trigger_reason:
        raise ResearchExecutionError("trigger_reason is required")
    affected_modules = _string_list(payload.get("affected_modules"))
    if not affected_modules:
        raise ResearchExecutionError("affected_modules is required")
    input_tokens = _nonnegative_int(payload.get("input_tokens"), "input_tokens")
    output_tokens = _nonnegative_int(payload.get("output_tokens"), "output_tokens")
    estimated_cost = _nonnegative_float(payload.get("estimated_cost", 0), "estimated_cost")
    started_at = str(payload.get("started_at") or "").strip()
    finished_at = str(payload.get("finished_at") or "").strip()
    if not started_at or not finished_at:
        raise ResearchExecutionError("started_at and finished_at are required")
    _parse_time(started_at)
    _parse_time(finished_at)
    status = str(payload.get("status") or "SUCCEEDED").strip().upper()
    if status not in {"RUNNING", "SUCCEEDED", "FAILED", "DEFERRED", "CANCELLED"}:
        raise ResearchExecutionError(f"unsupported llm run status: {status}")
    identifier = str(payload.get("llm_run_id") or llm_run_id).strip() or f"llm-run-{_hash_payload(payload)[:20]}"
    return {
        "schema_version": LLM_RUN_SCHEMA_VERSION,
        "llm_run_id": identifier,
        "research_id": research_id,
        "research_depth": str(payload.get("research_depth") or "STANDARD").strip().upper(),
        "execution_mode": execution_mode,
        "trigger_reason": trigger_reason,
        "affected_modules": affected_modules,
        "model_name": str(payload.get("model_name") or "unknown"),
        "method_version": str(payload.get("method_version") or "unknown"),
        "evidence_manifest_hash": str(payload.get("evidence_manifest_hash") or ""),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost": estimated_cost,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "output_artifact_id": str(payload.get("output_artifact_id") or ""),
        "failure_reason": str(payload.get("failure_reason") or ""),
        "content_hash": _hash_payload({
            "research_id": research_id,
            "model_name": payload.get("model_name"),
            "method_version": payload.get("method_version"),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "started_at": started_at,
            "finished_at": finished_at,
        }),
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "rule_version": RULE_VERSION,
        "policy": _policy(),
    }


def build_execution_audit(
    plan: Mapping[str, Any],
    llm_runs: Sequence[Mapping[str, Any]] = (),
    *,
    audit_id: str = "",
) -> dict[str, Any]:
    """Summarize resource use and verify model runs against a plan."""

    if not isinstance(plan, Mapping) or plan.get("schema_version") != RESEARCH_EXECUTION_PLAN_SCHEMA_VERSION:
        raise ResearchExecutionError("plan must be research-execution-plan.v1")
    runs = [
        item if item.get("schema_version") == LLM_RUN_SCHEMA_VERSION else build_llm_run(item)
        for item in llm_runs
        if isinstance(item, Mapping)
    ]
    allowed_modules = {str(item.get("module") or "") for item in plan.get("tasks") or []}
    violations = [
        {
            "llm_run_id": item["llm_run_id"],
            "affected_modules": [module for module in item["affected_modules"] if module not in allowed_modules],
        }
        for item in runs
        if any(module not in allowed_modules for module in item["affected_modules"])
    ]
    input_tokens = sum(int(item["input_tokens"]) for item in runs)
    output_tokens = sum(int(item["output_tokens"]) for item in runs)
    cost = sum(float(item["estimated_cost"]) for item in runs)
    budget = plan.get("token_budget") or {}
    return {
        "schema_version": "research-execution-audit.v1",
        "audit_id": audit_id.strip() or f"execution-audit-{plan['plan_id']}",
        "plan_id": str(plan["plan_id"]),
        "request_id": str(plan.get("request_id") or ""),
        "effective_execution_mode": str(plan.get("effective_execution_mode") or ""),
        "llm_run_ids": [item["llm_run_id"] for item in runs],
        "llm_run_count": len(runs),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "estimated_cost": cost,
        "budget_status": "EXCEEDED" if input_tokens + output_tokens > int(budget.get("max_tokens", 0)) or cost > float(budget.get("max_cost", 0)) else "WITHIN_BUDGET",
        "plan_violations": violations,
        "status": "BLOCKED" if violations else "AUDITED",
        "policy": {
            "model_calls_are_optional": True,
            "deterministic_tasks_remain_local": True,
            "budget_overrun_requires_local_only": True,
            "unplanned_modules_are_blocked": True,
            "no_investment_conclusion": True,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _planned_modules(request: Mapping[str, Any], differences: Sequence[Mapping[str, Any]]) -> list[str]:
    explicit = _string_list(request.get("affected_modules")) or _string_list(request.get("modules"))
    if explicit:
        return list(dict.fromkeys(explicit))
    if differences:
        modules = [str(item.get("module") or "") for item in differences if str(item.get("module") or "").strip()]
        if modules:
            return list(dict.fromkeys(modules))
    defaults = {
        "company_research": ["company_scope", "product_profile", "application_mapping", "financials", "valuation", "adversarial_review"],
        "industry_research": ["industry_situation", "cycle_reversal", "market_structure", "adversarial_review"],
        "futures_research": ["futures_identity", "futures_fundamentals", "market_structure", "adversarial_review"],
        "opportunity_discovery": ["industry_radar", "candidate_screen", "opportunity_features", "adversarial_review"],
        "thesis_check": ["evidence_freshness", "invalidators", "holding_thesis"],
        "public_draft": ["report_projection", "publication_safety"],
    }
    return list(defaults[request["task_type"]])


def _model_tasks(request: Mapping[str, Any], modules: Sequence[str]) -> list[str]:
    if request["requested_depth"] == "QUICK":
        return ["evidence_conflict_explanation"] if "adversarial_review" in modules else []
    tasks = []
    if any(module in modules for module in ("product_profile", "application_mapping")):
        tasks.append("product_application_semantics")
    if any(module in modules for module in ("industry_situation", "cycle_reversal", "futures_fundamentals")):
        tasks.append("industry_relationship_reasoning")
    if "adversarial_review" in modules:
        tasks.extend(("evidence_conflict_explanation", "adversarial_review"))
    if request["requested_depth"] == "DEEP":
        tasks.append("conclusion_synthesis")
    return list(dict.fromkeys(tasks))


def _validate_request(request: Mapping[str, Any]) -> None:
    if request.get("schema_version") != RESEARCH_REQUEST_SCHEMA_VERSION:
        raise ResearchExecutionError(f"request must be {RESEARCH_REQUEST_SCHEMA_VERSION}")
    if request.get("execution_enabled") is not False:
        raise ResearchExecutionError("execution_enabled must be false")
    if request.get("requested_depth") not in DEPTHS:
        raise ResearchExecutionError("request has unsupported requested_depth")
    if request.get("requested_execution_mode") not in EXECUTION_MODES:
        raise ResearchExecutionError("request has unsupported execution mode")


def _budget(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ResearchExecutionError("budget must be an object")
    max_tokens = _positive_int(value.get("max_tokens", 100000), "budget.max_tokens")
    max_cost = _nonnegative_float(value.get("max_cost", 1000), "budget.max_cost")
    used_cost = _nonnegative_float(value.get("used_cost", 0), "budget.used_cost")
    return {"max_tokens": max_tokens, "max_cost": max_cost, "used_cost": used_cost, "currency": str(value.get("currency") or "CNY")}


def _positive_int(value: Any, field: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ResearchExecutionError(f"{field} must be a positive integer") from error
    if number < 1:
        raise ResearchExecutionError(f"{field} must be a positive integer")
    return number


def _nonnegative_int(value: Any, field: str) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError) as error:
        raise ResearchExecutionError(f"{field} must be a non-negative integer") from error
    if number < 0:
        raise ResearchExecutionError(f"{field} must be a non-negative integer")
    return number


def _nonnegative_float(value: Any, field: str) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError) as error:
        raise ResearchExecutionError(f"{field} must be non-negative") from error
    if number < 0:
        raise ResearchExecutionError(f"{field} must be non-negative")
    return number


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ResearchExecutionError(f"invalid datetime: {value}") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise ResearchExecutionError("expected a string list")
    return [str(item).strip() for item in value if str(item).strip()]


def _hash_payload(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()


def _policy() -> dict[str, Any]:
    return {
        "no_model_call_in_planner": True,
        "deterministic_calculations_local": True,
        "local_only_does_not_rewrite_locked_ai_conclusion": True,
        "budget_exhaustion_degrades_to_local_only": True,
        "web_ai_not_automated": True,
        "execution_enabled": False,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
    }
