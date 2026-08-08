import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.task_resolution import (
    TaskResolutionError,
    resolve_research_task,
    validate_research_task,
)
from industry_first_research.security_master import build_security_master_snapshot


def test_company_code_with_market_suffix_is_ready_and_safe():
    task = resolve_research_task(
        "研究 600438.SH",
        research_as_of="2026-07-23",
        requested_depth="DEEP",
    )

    assert task["task_type"] == "company_research"
    assert task["subject_type"] == "listed_company"
    assert task["identifier"] == "600438.SH"
    assert task["status"] == "READY"
    assert task["identity_resolution"]["market"] == "SSE"
    assert task["execution_enabled"] is False
    assert validate_research_task(task)["task_id"] == task["task_id"]


def test_bare_company_code_does_not_infer_listing_market():
    task = resolve_research_task("600438", research_as_of="2026-07-23")

    assert task["task_type"] == "company_research"
    assert task["status"] == "NEEDS_CONFIRMATION"
    assert task["identity_resolution"]["market_confirmation_required"] is True
    assert "security_master_confirmation" in task["missing_fields"]


def test_task_resolver_uses_explicit_local_security_master_when_supplied():
    master = build_security_master_snapshot(
        {
            "schema_version": "security-master-input.v1",
            "as_of": "2026-07-23",
            "scope": {"scope_type": "EXPLICIT", "coverage_claim": "BOUNDED"},
            "records": [
                {
                    "company_id": "600519.SH",
                    "display_name": "贵州茅台",
                    "market": "SSE",
                    "listing_status": "LISTED",
                    "source": "official-company-profile",
                    "industry_memberships": [],
                }
            ],
        }
    )

    task = resolve_research_task(
        "600519",
        research_as_of="2026-07-23",
        security_master=master,
    )

    assert task["status"] == "READY"
    assert task["identity_resolution"]["canonical_identifier"] == "600519.SH"
    assert task["security_master_match"]["status"] == "MATCHED"
    assert task["policy"]["security_master_lookup_performed"] is True


def test_industry_and_opportunity_inputs_are_classified_without_company_data():
    industry = resolve_research_task("分析白酒行业", research_as_of="2026-07-23")
    opportunity = resolve_research_task("主动发现机会", research_as_of="2026-07-23")

    assert industry["task_type"] == "industry_research"
    assert industry["subject_type"] == "industry"
    assert industry["status"] == "READY"
    assert opportunity["task_type"] == "opportunity_discovery"
    assert opportunity["subject_type"] == "opportunity_scan"
    assert opportunity["status"] == "READY"


def test_futures_contract_and_continuous_series_require_explicit_exchange():
    contract = resolve_research_task(
        {"task_type": "futures_research", "input": "RB2501", "exchange": "SHFE"},
        research_as_of="2026-07-23",
    )
    continuous = resolve_research_task(
        {"task_type": "futures_research", "input": "RB888", "exchange": "SHFE"},
        research_as_of="2026-07-23",
    )
    variety = resolve_research_task(
        {"task_type": "futures_research", "input": "螺纹钢"},
        research_as_of="2026-07-23",
    )

    assert contract["subject_type"] == "futures_contract"
    assert contract["status"] == "READY"
    assert continuous["subject_type"] == "continuous_series"
    assert continuous["status"] == "READY"
    assert variety["subject_type"] == "futures_variety"
    assert variety["status"] == "NEEDS_CONFIRMATION"


def test_configured_commodity_alias_can_classify_chinese_futures_input():
    copper = {
        "adapter_id": "copper",
        "display_name": "铜产业链",
        "aliases": ["铜", "沪铜"],
        "variety_ids": ["CU"],
        "exchanges": ["SHFE", "INE"],
    }
    without_exchange = resolve_research_task(
        "沪铜",
        research_as_of="2026-07-23",
        commodity_definitions=[copper],
    )
    with_exchange = resolve_research_task(
        {"input": "CU", "exchange": "SHFE"},
        research_as_of="2026-07-23",
        commodity_definitions=[copper],
    )

    assert without_exchange["task_type"] == "futures_research"
    assert without_exchange["subject_type"] == "futures_variety"
    assert without_exchange["status"] == "NEEDS_CONFIRMATION"
    assert with_exchange["status"] == "READY"
    assert with_exchange["identity_resolution"]["commodity_adapter_id"] == "copper"


def test_company_name_and_execution_request_are_not_silently_accepted():
    name_task = resolve_research_task(
        {"task_type": "company_research", "input": "贵州茅台"},
        research_as_of="2026-07-23",
    )
    assert name_task["status"] == "NEEDS_CONFIRMATION"
    with pytest.raises(TaskResolutionError, match="execution_enabled"):
        resolve_research_task(
            {"task_type": "company_research", "input": "600438.SH", "execution_enabled": True},
            research_as_of="2026-07-23",
        )


def test_task_resolution_cli_writes_and_validates_immutable_task(tmp_path, monkeypatch, capsys):
    output_dir = tmp_path / "tasks"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "resolve-task",
            "--input-text",
            "研究 600438.SH",
            "--as-of",
            "2026-07-23",
            "--output-dir",
            str(output_dir),
        ],
    )
    main()
    result = json.loads(capsys.readouterr().out)
    task_path = output_dir / f"{result['task']['task_id']}.json"
    assert task_path.exists()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "validate-research-task",
            "--input",
            str(task_path),
        ],
    )
    main()
    validated = json.loads(capsys.readouterr().out)
    assert validated["valid"] is True
