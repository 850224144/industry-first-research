import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.research_execution import (
    ResearchExecutionError,
    build_execution_audit,
    build_llm_run,
    build_research_execution_plan,
    build_research_request,
)
from industry_first_research.task_resolution import resolve_research_task


def request(**overrides):
    payload = {
        "task_type": "company_research",
        "subject_type": "listed_company",
        "identifier": "600438",
        "research_as_of": "2026-07-21",
        "requested_depth": "STANDARD",
        "execution_mode": "LLM_ASSISTED",
        "budget": {"max_tokens": 10000, "max_cost": 100, "currency": "CNY"},
    }
    payload.update(overrides)
    return payload


def test_request_separates_request_id_from_subject_identifier():
    report = build_research_request(
        {
            "task_type": "company_research",
            "subject_type": "listed_company",
            "subject_id": "600438",
            "research_as_of": "2026-07-21",
        },
        request_id="research-001",
    )

    assert report["request_id"] == "research-001"
    assert report["identifier"] == "600438"
    assert report["execution_enabled"] is False


def test_research_request_accepts_ready_task_resolution_envelope():
    task = resolve_research_task("研究 600438.SH", research_as_of="2026-07-21")
    report = build_research_request(task)

    assert report["task_type"] == "company_research"
    assert report["identifier"] == "600438.SH"
    assert report["requested_execution_mode"] == "LOCAL_ONLY"


def test_research_request_blocks_task_that_needs_identity_confirmation():
    task = resolve_research_task("600438", research_as_of="2026-07-21")
    with pytest.raises(ResearchExecutionError, match="confirmation"):
        build_research_request(task)


def test_research_request_allows_identifier_free_opportunity_and_continuous_research():
    opportunity = build_research_request(
        {
            "task_type": "opportunity_discovery",
            "subject_type": "opportunity_scan",
            "research_as_of": "2026-07-21",
        }
    )
    continuous = build_research_request(
        {
            "task_type": "futures_research",
            "subject_type": "continuous_series",
            "identifier": "RB888",
            "research_as_of": "2026-07-21",
        }
    )

    assert opportunity["identifier"] == "opportunity-discovery"
    assert continuous["subject_type"] == "continuous_series"


def test_plan_uses_model_only_for_semantic_tasks_when_available():
    report = build_research_execution_plan(
        build_research_request(request()), available_model=True
    )

    assert report["effective_execution_mode"] == "LLM_ASSISTED"
    assert any(item["execution"] == "MODEL_OPTIONAL" for item in report["tasks"])
    assert all(
        item["module"] not in {"valuation_formula", "market_data_calculation"}
        for item in report["tasks"]
    )


def test_plan_degrades_to_local_only_when_budget_is_exhausted():
    report = build_research_execution_plan(
        build_research_request(request(budget={"max_tokens": 10, "max_cost": 1})),
        available_model=True,
        used_input_tokens=10,
    )

    assert report["effective_execution_mode"] == "LOCAL_ONLY"
    assert report["budget_exhausted"] is True
    assert report["deferred_model_tasks"]
    assert any(item["execution"] == "DEFERRED" for item in report["tasks"])
    assert report["last_locked_conclusion_policy"]["local_only_cannot_rewrite_ai_conclusion"] is True


def test_local_only_is_explicit_when_model_is_unavailable():
    report = build_research_execution_plan(
        build_research_request(request()), available_model=False
    )

    assert report["effective_execution_mode"] == "LOCAL_ONLY"
    assert "unavailable" in report["degradation_reason"]


def test_manual_web_ai_never_becomes_an_automatic_model_call():
    report = build_research_execution_plan(
        build_research_request(request(execution_mode="MANUAL_WEB_AI")),
        available_model=True,
    )

    assert report["effective_execution_mode"] == "MANUAL_WEB_AI"
    assert report["model_available"] is False
    assert report["deferred_model_tasks"]


def test_llm_run_records_auditable_call_and_rejects_wrong_mode():
    run = build_llm_run(
        {
            "research_id": "research-001",
            "research_depth": "STANDARD",
            "execution_mode": "LLM_ASSISTED",
            "trigger_reason": "产品应用语义无法由规则明确判断",
            "affected_modules": ["product_application_semantics"],
            "model_name": "local-test-model",
            "method_version": "prompt-v1",
            "evidence_manifest_hash": "e" * 64,
            "input_tokens": 100,
            "output_tokens": 50,
            "estimated_cost": 0.12,
            "started_at": "2026-07-21T09:00:00+08:00",
            "finished_at": "2026-07-21T09:00:03+08:00",
        }
    )

    assert run["schema_version"] == "llm-run.v1"
    assert run["total_tokens"] if "total_tokens" in run else run["input_tokens"] + run["output_tokens"]
    with pytest.raises(ResearchExecutionError, match="LLM_ASSISTED"):
        build_llm_run({"research_id": "r", "execution_mode": "LOCAL_ONLY", "trigger_reason": "x", "affected_modules": ["x"], "started_at": "2026-07-21", "finished_at": "2026-07-21"})


def test_execution_audit_blocks_unplanned_modules_and_counts_cost():
    plan = build_research_execution_plan(
        build_research_request(request()), available_model=True
    )
    run = build_llm_run(
        {
            "research_id": plan["research_id"],
            "execution_mode": "LLM_ASSISTED",
            "trigger_reason": "审查",
            "affected_modules": ["unplanned_module"],
            "input_tokens": 3,
            "output_tokens": 2,
            "estimated_cost": 0.5,
            "started_at": "2026-07-21T09:00:00+08:00",
            "finished_at": "2026-07-21T09:00:01+08:00",
        }
    )
    audit = build_execution_audit(plan, [run])

    assert audit["status"] == "BLOCKED"
    assert audit["total_tokens"] == 5
    assert audit["estimated_cost"] == 0.5


def test_research_plan_cli_writes_immutable_plan(tmp_path, monkeypatch, capsys):
    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(request()), encoding="utf-8")
    output_dir = tmp_path / "execution"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "research-plan",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    main()
    capsys.readouterr()

    assert len(list(output_dir.glob("*.json"))) == 1
    plan = json.loads(next(output_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert plan["effective_execution_mode"] == "LOCAL_ONLY"
