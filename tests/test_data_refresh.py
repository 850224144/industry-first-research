import json
import sys
from pathlib import Path

import pytest

from industry_first_research.cli import main
from industry_first_research.data_refresh import (
    DataRefreshError,
    build_data_source_refresh,
    validate_data_source_refresh,
)
from industry_first_research.data_sources import (
    DataSourceHealth,
    DataSourceRouter,
    FreeDataSourcePolicy,
    EastmoneyDataSourceAdapter,
    PublicHttpDataSourceAdapter,
)
from industry_first_research.scheduled_tasks import LocalScheduledTaskRunner
from industry_first_research.scheduler import build_default_schedule, build_scheduler_plan, build_scheduler_state


class FakeAdapter:
    source_type = "test"

    def __init__(self, name, payload=None, error=None):
        self.name = name
        self.payload = payload
        self.error = error

    def health_check(self):
        return DataSourceHealth(
            self.name,
            self.source_type,
            True,
            capabilities=("cn_stock", "industry", "futures"),
        )

    def fetch(self, _query, as_of):
        if self.error:
            raise self.error
        return {"source": self.name, "data": self.payload, "as_of": as_of}

    def normalize(self, value):
        return value


def router(payload=None):
    return DataSourceRouter(
        [
            FakeAdapter("first", error=TimeoutError("first source timed out")),
            FakeAdapter("second", payload=payload or [{"close": 10}]),
        ],
        FreeDataSourcePolicy(listed_company_sources=("first", "second")),
    )


def test_refresh_end_to_end_uses_fixed_public_response_after_primary_failure():
    fixture_dir = Path(__file__).parent / "fixtures" / "data_sources"
    eastmoney_payload = (fixture_dir / "eastmoney_quote.json").read_bytes()

    class Response:
        headers = {"Content-Type": "application/json"}

        def read(self):
            return eastmoney_payload

        def close(self):
            pass

    def unavailable(_request, timeout):
        raise TimeoutError("fixture primary unavailable")

    router = DataSourceRouter(
        [
            PublicHttpDataSourceAdapter(
                "official_exchange", ("exchange_disclosure",), unavailable
            ),
            EastmoneyDataSourceAdapter(lambda _request, timeout: Response()),
        ],
        FreeDataSourcePolicy(
            listed_company_sources=("official_exchange", "eastmoney")
        ),
    )
    payload = {
        "schema_version": "data-source-refresh-input.v1",
        "refresh_id": "fixture-refresh-600438",
        "as_of": "2026-07-25",
        "queries": [
            {
                "query_id": "company-600438-quote",
                "subject_type": "listed_company",
                "subject_id": "600438.SH",
                "source_names": ["official_exchange", "eastmoney"],
                "request": {
                    "url": "https://fixture.test/quote",
                    "required_fields": ["data"],
                },
            }
        ],
    }

    report = build_data_source_refresh(payload, router)
    row = report["queries"][0]
    assert report["status"] == "SUCCESS"
    assert row["source"] == "eastmoney"
    assert [attempt["status"] for attempt in row["attempts"]] == [
        "FAILED",
        "SUCCESS",
    ]
    assert row["data"]["data"]["data"]["diff"][0]["f12"] == "600438"
    assert validate_data_source_refresh(report)["content_hash"] == report["content_hash"]


def refresh_input():
    return {
        "schema_version": "data-source-refresh-input.v1",
        "as_of": "2026-07-25",
        "queries": [
            {
                "query_id": "company-600438-daily",
                "subject_type": "listed_company",
                "subject_id": "600438.SH",
                "source_names": ["first", "second"],
                "request": {
                    "required_fields": ["data"],
                    "query_type": "history",
                },
            }
        ],
    }


def test_refresh_uses_fallback_and_preserves_attempts():
    report = build_data_source_refresh(refresh_input(), router())
    row = report["queries"][0]

    assert report["status"] == "SUCCESS"
    assert row["source"] == "second"
    assert [item["status"] for item in row["attempts"]] == ["FAILED", "SUCCESS"]
    assert report["policy"]["fact_promotion"] is False
    assert report["resource_audit"]["full_market_deep_data"] is False
    assert validate_data_source_refresh(report)["refresh_id"] == report["refresh_id"]


def test_refresh_is_bounded_and_marks_truncation():
    report = build_data_source_refresh(
        refresh_input(),
        router([{"close": 1}, {"close": 2}, {"close": 3}]),
        max_rows_per_query=2,
    )

    assert report["status"] == "PARTIAL"
    assert report["truncated_query_count"] == 1
    assert len(report["queries"][0]["data"]["data"]) == 2
    assert report["queries"][0]["truncated"] is True


def test_refresh_rejects_credentials_and_unbounded_manifest():
    secret_input = refresh_input()
    secret_input["queries"][0]["request"]["token"] = "do-not-store"
    with pytest.raises(DataRefreshError, match="credentials"):
        build_data_source_refresh(secret_input, router())

    too_many = refresh_input()
    too_many["queries"] = too_many["queries"] * 2
    with pytest.raises(DataRefreshError, match="max_queries"):
        build_data_source_refresh(too_many, router(), max_queries=1)


def test_refresh_validation_rejects_tampering():
    report = build_data_source_refresh(refresh_input(), router())
    report["queries"][0]["reason"] = "changed"
    with pytest.raises(DataRefreshError, match="content_hash"):
        validate_data_source_refresh(report)


def test_data_refresh_cli_writes_refresh_and_health(tmp_path, monkeypatch, capsys):
    input_path = tmp_path / "refresh.json"
    output_dir = tmp_path / "refreshes"
    input_path.write_text(json.dumps(refresh_input()), encoding="utf-8")
    monkeypatch.setattr(
        "industry_first_research.cli.default_data_source_router",
        lambda: router(),
    )
    monkeypatch.setattr(sys, "argv", [
        "industry-first-research",
        "data-refresh",
        "--input",
        str(input_path),
        "--output-dir",
        str(output_dir),
    ])

    main()
    result = json.loads(capsys.readouterr().out)
    assert result["report"]["status"] == "SUCCESS"
    assert (output_dir / f"{result['report']['refresh_id']}.json").exists()
    assert (tmp_path / "source_health").exists()


def test_scheduler_refreshes_only_explicit_queries(tmp_path):
    schedule = build_default_schedule()
    state = build_scheduler_state(schedule)
    plan, state = build_scheduler_plan(
        schedule, state, now="2026-07-25T09:00:00+08:00"
    )
    task_id = next(
        task["task_id"]
        for task in plan["tasks"]
        if task["task_type"] == "data_source_refresh"
    )
    queries = refresh_input()["queries"]
    plan["tasks"] = [
        {
            **task,
            "scope": {
                **task.get("scope", {}),
                "refresh_manifest_path": "",
                "queries": queries,
            },
        }
        for task in plan["tasks"]
    ]
    state["tasks"][task_id]["scope"]["refresh_manifest_path"] = ""
    state["tasks"][task_id]["scope"]["queries"] = queries

    result = LocalScheduledTaskRunner(
        data_root=tmp_path,
        data_source_router_factory=lambda: router(),
    ).execute(
        state,
        {**plan, "task_ids": [task_id]},
        now="2026-07-25T09:00:00+08:00",
    )

    assert result["results"][0]["status"] == "SUCCEEDED"
    refresh_dir = tmp_path / "data_source_refreshes"
    saved = json.loads(next(refresh_dir.glob("*.json")).read_text())
    assert saved["query_count"] == 1
    assert saved["source_health_snapshot_id"]
    assert saved["execution_enabled"] is False
    tracking_dir = tmp_path / "data_source_refresh_tracking"
    tracking = json.loads(next(tracking_dir.glob("*.json")).read_text())
    assert tracking["tracking_status"] == "INITIALIZED"
    assert tracking["policy"]["fact_promotion"] is False
