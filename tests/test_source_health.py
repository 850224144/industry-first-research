import json
import sys
from types import SimpleNamespace

import pytest

from industry_first_research.cli import main
from industry_first_research.data_sources import (
    AkshareDataSourceAdapter,
    BaoStockDataSourceAdapter,
    DataSourceHealth,
    DataSourceRouter,
    FreeDataSourcePolicy,
)
from industry_first_research.source_health import (
    SourceHealthError,
    build_source_health_snapshot,
    validate_source_health_snapshot,
)


class FakeAdapter:
    def __init__(self, name, *, available=True, capabilities=(), reason=""):
        self.name = name
        self.source_type = "test"
        self._health = DataSourceHealth(
            name, "test", available, tuple(capabilities), reason, "test-version"
        )

    def health_check(self):
        return self._health


def test_source_health_preserves_primary_backup_order_and_rejects_missing_capability():
    router = DataSourceRouter(
        [
            FakeAdapter("primary", capabilities=("basic",)),
            FakeAdapter("backup", capabilities=("history",)),
        ],
        FreeDataSourcePolicy(listed_company_sources=("primary", "backup")),
    )

    snapshot = build_source_health_snapshot(
        router,
        subject_types=("listed_company",),
        required_capabilities={"listed_company": ("history",)},
        checked_at="2026-07-23T09:00:00+08:00",
        snapshot_id="source-health-test",
    )

    route = snapshot["routes"]["listed_company"]
    assert route["primary_source"] == "backup"
    assert route["fallback_sources"] == []
    assert route["rejected_sources"][0]["reason"] == "missing_capability"
    assert validate_source_health_snapshot(snapshot)["snapshot_id"] == "source-health-test"


def test_source_health_marks_optional_dependencies_unavailable_without_failing():
    def missing_dependency():
        raise ModuleNotFoundError("test optional dependency")

    akshare = AkshareDataSourceAdapter()
    baostock = BaoStockDataSourceAdapter()
    akshare._load = missing_dependency
    baostock._load = missing_dependency
    router = DataSourceRouter(
        [akshare, baostock],
        FreeDataSourcePolicy(listed_company_sources=("akshare", "baostock")),
    )

    snapshot = build_source_health_snapshot(
        router,
        subject_types=("listed_company",),
        checked_at="2026-07-23T09:00:00+08:00",
    )

    assert all(item["available"] is False for item in snapshot["sources"])
    assert snapshot["routes"]["listed_company"]["status"] == "INSUFFICIENT"


def test_source_health_hash_rejects_tampering():
    router = DataSourceRouter([FakeAdapter("primary")])
    snapshot = build_source_health_snapshot(
        router,
        subject_types=("listed_company",),
        checked_at="2026-07-23T09:00:00+08:00",
    )
    with pytest.raises(SourceHealthError, match="content_hash"):
        validate_source_health_snapshot(dict(snapshot, checked_at="2026-07-24T09:00:00+08:00"))


def test_source_health_cli_writes_immutable_snapshot_and_validates_it(tmp_path, monkeypatch, capsys):
    router = DataSourceRouter(
        [FakeAdapter("primary", capabilities=("history",))],
        FreeDataSourcePolicy(listed_company_sources=("primary",)),
    )
    monkeypatch.setattr("industry_first_research.cli.default_data_source_router", lambda: router)
    output_dir = tmp_path / "source-health"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "source-health",
            "--subject-type",
            "listed_company",
            "--required-capability",
            "listed_company=history",
            "--checked-at",
            "2026-07-23T09:00:00+08:00",
            "--snapshot-id",
            "source-health-cli",
            "--output-dir",
            str(output_dir),
        ],
    )
    main()
    capsys.readouterr()
    snapshot_path = output_dir / "source-health-cli.json"
    assert snapshot_path.exists()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "validate-source-health",
            "--input",
            str(snapshot_path),
        ],
    )
    main()
    output = json.loads(capsys.readouterr().out)
    assert output["valid"] is True
