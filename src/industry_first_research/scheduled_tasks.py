"""Local handlers for the bounded scheduler task types."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from .adapters import ChainedCompanyData
from .cross_validation import CrossSourceIndustryRadar
from .eastmoney import EastmoneyAPIError, EastmoneyIndustryRadar
from .eastmoney_company_survey import EastmoneyCompanySurveyData
from .industry_aliases import IndustryAliasRegistry
from .models import CompanyDataTier, IndustryRadarSnapshot, IndustryState
from .opportunity_tracking import build_opportunity_tracking_report
from .scheduler import (
    RetryableTaskError,
    execute_scheduler_plan,
)
from .storage import JsonSnapshotStore
from .research_version import (
    build_research_version,
    build_research_version_from_pipeline,
    validate_research_version,
)
from .research_impact import build_research_impact_queue
from .data_sources import DataSourceRouter, default_data_source_router
from .data_refresh import (
    DataRefreshError,
    build_data_source_refresh,
    validate_data_source_refresh,
)
from .data_refresh_tracking import (
    DataRefreshTrackingError,
    build_data_refresh_tracking_report,
)
from .source_health import build_source_health_snapshot
from .incremental_update import IncrementalUpdateError, build_incremental_update
from .futures_tracking import FuturesTrackingError, build_futures_tracking_report
from .tonghuashun import TonghuashunAPIError, TonghuashunIndustryRadar
from .tonghuashun_company_pool import (
    TonghuashunCompanyPool,
    TonghuashunCompanyPoolError,
)
from .tonghuashun_light_data import TonghuashunLightCompanyData
from .trend import RadarTrendError, build_trend_report


class ScheduledTaskRunnerError(ValueError):
    """Raised when a local scheduled task cannot be configured."""


RadarFactory = Callable[[str, int], Any]
CompanyPoolFactory = Callable[[int], Any]
CompanyDataFactory = Callable[[], Any]

_EVENT_MODULES = {
    "announcement_correction": ("evidence_freshness", "research_version_comparison"),
    "buyback": ("valuation_scenarios", "adversarial_review"),
    "customer_certification": ("product_profile", "application_mapping", "demand_transmission"),
    "earnings_preview": ("survival_analysis", "valuation_scenarios", "research_report"),
    "earnings_report": ("survival_analysis", "valuation_scenarios", "research_report"),
    "industry_data_release": ("industry_situation", "cycle_reversal"),
    "industry_membership_changed": ("company_pool", "company_screen"),
    "industry_selected": ("company_pool", "company_screen"),
    "major_contract": ("application_mapping", "demand_transmission", "competitive_position"),
    "merger_acquisition": ("company_scope", "competitive_position", "valuation_scenarios"),
    "policy_change": ("industry_situation", "cycle_reversal", "adversarial_review"),
    "price_shock": ("market_structure", "valuation_scenarios", "thesis_check"),
    "rights_issue_or_placement": ("survival_analysis", "valuation_scenarios", "adversarial_review"),
    "shutdown_or_bankruptcy": ("industry_situation", "survival_analysis", "thesis_check"),
    "technology_route_change": ("product_profile", "application_mapping", "competitive_position"),
}


class LocalScheduledTaskRunner:
    """Execute scheduler tasks through existing read-only data adapters.

    The runner deliberately stops at radar, bounded company pools, delta summaries,
    and event review records by default. An event with explicit local version and
    evidence inputs may invoke the deterministic incremental builder, but still
    cannot create a directional conclusion, thesis, or decision snapshot.
    """

    def __init__(
        self,
        *,
        data_root: str | Path = "data",
        alias_file: str | Path = "docs/industry_aliases.v1.json",
        radar_factory: RadarFactory | None = None,
        company_pool_factory: CompanyPoolFactory | None = None,
        company_data_factory: CompanyDataFactory | None = None,
        data_source_router_factory: Callable[[], DataSourceRouter] | None = None,
    ) -> None:
        self.data_root = Path(data_root)
        self.alias_file = Path(alias_file)
        self.radar_factory = radar_factory or self._default_radar_factory
        self.company_pool_factory = company_pool_factory or (
            lambda limit: TonghuashunCompanyPool(page_size=limit)
        )
        self.company_data_factory = company_data_factory or (
            lambda: ChainedCompanyData(
                (TonghuashunLightCompanyData(), EastmoneyCompanySurveyData())
            )
        )
        self.data_source_router_factory = (
            data_source_router_factory or default_data_source_router
        )

    def handlers(self) -> dict[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]]:
        return {
            "industry_radar_refresh": self._run_industry_radar_refresh,
            "daily_delta_scan": self._run_daily_delta_scan,
            "futures_fundamentals_delta_scan": self._run_futures_fundamentals_delta_scan,
            "data_source_refresh": self._run_data_source_refresh,
            "event_triggered_scan": self._run_event_triggered_scan,
            "company_pool_refresh": self._run_company_pool_refresh,
        }

    def execute(
        self,
        state: Mapping[str, Any],
        plan: Mapping[str, Any],
        *,
        now: str = "",
    ) -> dict[str, Any]:
        return execute_scheduler_plan(state, plan, self.handlers(), now=now)

    def _run_industry_radar_refresh(self, task: Mapping[str, Any]) -> dict[str, Any]:
        scope = task.get("scope") or {}
        source = str(scope.get("radar_source") or "cross")
        limit = min(int(scope.get("radar_limit") or 50), 50)
        as_of = _task_as_of(task)
        source_health_id, source_health_path = self._write_source_health_snapshot(task)
        try:
            provider = self.radar_factory(source, limit)
            items = list(provider.snapshots(as_of))
        except (EastmoneyAPIError, TonghuashunAPIError, OSError, TimeoutError) as error:
            raise RetryableTaskError(f"industry radar source unavailable: {error}") from error
        if not items:
            return {
                "status": "INSUFFICIENT",
                "reason": "radar returned no industry rows",
                "source_health_snapshot_id": source_health_id,
                "source_health_snapshot_path": source_health_path,
            }
        snapshot_id = f"{source}-industry-{as_of}"
        payload = {
            "schema_version": "industry-radar.v1",
            "snapshot_id": snapshot_id,
            "source": _metadata(provider, as_of, source),
            "items": [item.to_dict() for item in items],
            "trigger_task_id": str(task.get("task_id") or ""),
            "resource_audit": {
                "industry_row_limit": limit,
                "company_pool_loaded": False,
                "company_deep_data_loaded": False,
                "full_market_deep_data": False,
            },
            "read_only": True,
            "execution_enabled": False,
        }
        path = JsonSnapshotStore(self.data_root / "radar").write_immutable(snapshot_id, payload)
        version = build_research_version(
            {
                "subject_type": "industry",
                "subject_ids": [str(item.industry_id) for item in items if str(item.industry_id)],
                "research_as_of": as_of,
                "previous_version_id": _latest_previous_research_version_id(
                    self.data_root / "research_versions",
                    artifact_type="industry_radar",
                    subject_ids=[str(item.industry_id) for item in items if str(item.industry_id)],
                    as_of=as_of,
                    artifact_id=snapshot_id,
                ),
                "execution_mode": "LOCAL_ONLY",
                "affected_modules": ["industry_radar"],
                "artifact_refs": [
                    {
                        "artifact_id": snapshot_id,
                        "artifact_type": "industry_radar",
                        "as_of": as_of,
                        "content_hash": _hash_payload(payload),
                    }
                ],
                "rule_versions": {"scheduler": "research-scheduler-rules.v1"},
                "source_health_snapshot_id": source_health_id,
                "version_status": "VALID",
                "review_status": "NOT_REVIEWED",
            },
            version_id=f"research-version-{snapshot_id}",
        )
        version_path = JsonSnapshotStore(self.data_root / "research_versions").write_immutable(
            version["version_id"], version
        )
        return {
            "status": "SUCCESS",
            "artifact_path": str(path),
            "snapshot_id": snapshot_id,
            "item_count": len(items),
            "source": source,
            "research_version_id": version["version_id"],
            "research_version_path": str(version_path),
            "source_health_snapshot_id": source_health_id,
            "source_health_snapshot_path": source_health_path,
        }

    def _run_daily_delta_scan(self, task: Mapping[str, Any]) -> dict[str, Any]:
        scope = task.get("scope") or {}
        source = str(scope.get("radar_source") or "cross")
        as_of = _task_as_of(task)
        source_health_id, source_health_path = self._write_source_health_snapshot(task)
        input_dir = Path(scope.get("radar_input_dir") or self.data_root / "radar")
        try:
            report = build_trend_report(
                input_dir,
                source=source,
                as_of=as_of,
                window=min(int(scope.get("trend_window") or 10), 30),
                min_observations=max(1, int(scope.get("min_observations") or 3)),
            )
        except RadarTrendError as error:
            return {
                "status": "INSUFFICIENT",
                "reason": str(error),
                "source_health_snapshot_id": source_health_id,
                "source_health_snapshot_path": source_health_path,
            }
        candidate_summary = _candidate_queue_summary(
            Path(scope.get("candidate_queue_dir") or self.data_root / "candidate_queues"),
            candidate_capacity=min(int(scope.get("candidate_capacity") or 15), 15),
            watch_capacity=min(int(scope.get("watch_capacity") or 60), 60),
        )
        report["trigger_task_id"] = str(task.get("task_id") or "")
        report["candidate_delta"] = candidate_summary
        current_scan, previous_scan = _latest_opportunity_scans(
            Path(scope.get("opportunity_scan_dir") or self.data_root / "opportunity_scans"),
            as_of=as_of,
        )
        report["opportunity_tracking"] = build_opportunity_tracking_report(
            current_scan,
            previous_scan=previous_scan,
            trend_report=report,
            candidate_delta=candidate_summary,
            as_of=as_of,
        )
        report["resource_audit"] = {
            "industry_only_first": True,
            "candidate_capacity": candidate_summary["candidate_capacity"],
            "watch_capacity": candidate_summary["watch_capacity"],
            "deep_research_limit": min(int(scope.get("deep_research_limit") or 3), 3),
            "full_market_deep_data": False,
        }
        report["read_only"] = True
        report["execution_enabled"] = False
        report_id = f"daily-delta-{source}-{as_of}"
        version = build_research_version(
            {
                "subject_type": "mixed",
                "subject_ids": sorted(
                    str(item.get("industry_id") or "")
                    for item in report.get("items") or []
                    if isinstance(item, Mapping) and str(item.get("industry_id") or "")
                ) or [f"daily-delta:{source}"],
                "research_as_of": as_of,
                "previous_version_id": _latest_previous_research_version_id(
                    self.data_root / "research_versions",
                    artifact_type="daily_delta",
                    subject_ids=[
                        str(item.get("industry_id") or "")
                        for item in report.get("items") or []
                        if isinstance(item, Mapping)
                    ],
                    as_of=as_of,
                    artifact_id=report_id,
                ),
                "execution_mode": "LOCAL_ONLY",
                "affected_modules": ["industry_trend", "opportunity_tracking"],
                "artifact_refs": [{
                    "artifact_id": report_id,
                    "artifact_type": "daily_delta",
                    "as_of": as_of,
                    "content_hash": _hash_payload(report),
                }],
                "rule_versions": {"trend": "industry-radar-trend.v1"},
                "source_health_snapshot_id": source_health_id,
                "version_status": "VALID" if report["data_quality"]["status"] == "OK" else "REVIEW_REQUIRED",
            },
            version_id=f"research-version-{report_id}",
        )
        report["research_version_id"] = version["version_id"]
        path = JsonSnapshotStore(self.data_root / "scheduled_deltas").write_immutable(report_id, report)
        version_path = JsonSnapshotStore(self.data_root / "research_versions").write_immutable(version["version_id"], version)
        status = "SUCCESS" if report["data_quality"]["status"] == "OK" else "INSUFFICIENT"
        return {
            "status": status,
            "artifact_path": str(path),
            "report_id": report_id,
            "candidate_count": candidate_summary["candidate_count"],
            "reason": report["data_quality"]["reason"],
            "research_version_id": version["version_id"],
            "research_version_path": str(version_path),
            "source_health_snapshot_id": source_health_id,
            "source_health_snapshot_path": source_health_path,
        }

    def _run_futures_fundamentals_delta_scan(
        self, task: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Compare a bounded set of locally saved futures reports.

        Data acquisition remains outside the scheduler.  This task only reads
        reports already produced by the futures fundamentals pipeline, keeps
        one series per variety/object/contract, and records the resulting
        comparison as a new immutable research artifact.
        """

        scope = task.get("scope") or {}
        as_of = _task_as_of(task)
        source_health_id, source_health_path = self._write_source_health_snapshot(task)
        report_dir = self._resolve_input_path(
            str(scope.get("futures_report_dir") or self.data_root / "futures_fundamentals")
        )
        report_limit = min(int(scope.get("futures_report_limit") or 50), 100)
        allowed_varieties = {
            str(value).strip().upper()
            for value in scope.get("futures_varieties") or []
            if str(value).strip()
        }
        loaded: list[dict[str, Any]] = []
        rejected_inputs: list[dict[str, str]] = []
        try:
            paths = sorted(report_dir.glob("*.json"))
        except OSError as error:
            raise RetryableTaskError(f"futures report directory unavailable: {error}") from error

        for path in paths:
            if len(loaded) >= report_limit:
                break
            try:
                payload = _read_json_object(path)
                if payload.get("schema_version") != "futures-fundamentals-report.v1":
                    continue
                report_as_of = _date_text(payload.get("as_of"), "futures report as_of")
                if report_as_of > as_of[:10]:
                    rejected_inputs.append(
                        {"path": str(path), "reason": "future_report_exceeds_task_as_of"}
                    )
                    continue
                variety_id = str(payload.get("variety_id") or "").strip().upper()
                if allowed_varieties and variety_id not in allowed_varieties:
                    continue
                loaded.append({"path": str(path), "report": payload})
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
                rejected_inputs.append({"path": str(path), "reason": "invalid_futures_report"})

        grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        for item in loaded:
            report = item["report"]
            contract = report.get("contract") or {}
            contract_code = str(contract.get("contract_code") or "") if isinstance(contract, Mapping) else ""
            key = (
                str(report.get("exchange") or ""),
                str(report.get("variety_id") or ""),
                str(report.get("object_type") or ""),
                contract_code,
            )
            grouped.setdefault(key, []).append(item)

        rows: list[dict[str, Any]] = []
        for key, items in sorted(grouped.items()):
            items.sort(
                key=lambda item: (
                    str(item["report"].get("as_of") or "")[:10],
                    str(item["report"].get("report_id") or ""),
                )
            )
            current = items[-1]["report"]
            previous = items[-2]["report"] if len(items) > 1 else None
            try:
                rows.append(build_futures_tracking_report(current, previous, as_of=as_of))
            except FuturesTrackingError as error:
                rejected_inputs.append(
                    {"path": items[-1]["path"], "reason": f"comparison_blocked: {error}"}
                )

        report_id = f"futures-delta-{as_of[:10]}"
        payload: dict[str, Any] = {
            "schema_version": "futures-fundamentals-delta-scan.v1",
            "report_id": report_id,
            "as_of": as_of,
            "tracking_rule_version": "futures-tracking-rules.v1",
            "rows": rows,
            "loaded_report_count": len(loaded),
            "tracked_series_count": len(rows),
            "rejected_inputs": rejected_inputs,
            "status": "SUCCESS" if rows else "INSUFFICIENT",
            "review_required": True,
            "resource_audit": {
                "futures_report_limit": report_limit,
                "selected_varieties": sorted(allowed_varieties),
                "full_market_deep_data": False,
                "data_fetched": False,
            },
            "source_health_snapshot_id": source_health_id,
            "read_only": True,
            "directional_conclusion": False,
            "investment_conclusion": False,
            "decision_snapshot_created": False,
            "execution_enabled": False,
        }
        object_types = {
            str(row.get("subject", {}).get("object_type") or "")
            for row in rows
            if str(row.get("subject", {}).get("object_type") or "")
        }
        version_subject_type = (
            "futures_contract"
            if object_types and object_types <= {"futures_contract"}
            else "futures_variety"
            if object_types and object_types <= {"futures_variety", "spot_benchmark"}
            else "mixed"
        )
        version = build_research_version(
            {
                "subject_type": version_subject_type,
                "subject_ids": sorted(
                    {
                        str(row.get("subject", {}).get("variety_id") or "")
                        for row in rows
                        if str(row.get("subject", {}).get("variety_id") or "")
                    }
                ) or ["futures-tracking"],
                "research_as_of": as_of,
                "previous_version_id": _latest_previous_research_version_id(
                    self.data_root / "research_versions",
                    artifact_type="futures_fundamentals_tracking",
                    subject_ids=[
                        str(row.get("subject", {}).get("variety_id") or "")
                        for row in rows
                        if isinstance(row.get("subject"), Mapping)
                    ],
                    as_of=as_of,
                    artifact_id=report_id,
                ),
                "execution_mode": "LOCAL_ONLY",
                "affected_modules": ["futures_fundamentals", "futures_tracking"],
                "artifact_refs": [{
                    "artifact_id": report_id,
                    "artifact_type": "futures_fundamentals_tracking",
                    "as_of": as_of,
                    "content_hash": _hash_payload(payload),
                }],
                "rule_versions": {"futures_tracking": "futures-tracking-rules.v1"},
                "source_health_snapshot_id": source_health_id,
                "version_status": "VALID" if rows else "REVIEW_REQUIRED",
            },
            version_id=f"research-version-{report_id}",
        )
        payload["research_version_id"] = version["version_id"]
        path = JsonSnapshotStore(self.data_root / "futures_tracking").write_immutable(
            report_id, payload
        )
        version_path = JsonSnapshotStore(self.data_root / "research_versions").write_immutable(
            version["version_id"], version
        )
        return {
            "status": payload["status"],
            "artifact_path": str(path),
            "report_id": report_id,
            "loaded_report_count": len(loaded),
            "tracked_series_count": len(rows),
            "research_version_id": version["version_id"],
            "research_version_path": str(version_path),
            "source_health_snapshot_id": source_health_id,
            "source_health_snapshot_path": source_health_path,
        }

    def _run_data_source_refresh(self, task: Mapping[str, Any]) -> dict[str, Any]:
        """Fetch only the explicit, bounded query manifest for this task."""

        scope = task.get("scope") or {}
        router = self.data_source_router_factory()
        source_health_id, source_health_path = self._write_source_health_snapshot(
            task, router=router
        )
        manifest_path_text = str(scope.get("refresh_manifest_path") or "").strip()
        raw_manifest = scope.get("queries")
        if raw_manifest is None and manifest_path_text:
            manifest_path = self._resolve_input_path(manifest_path_text)
            try:
                manifest = _read_json_object(manifest_path)
            except FileNotFoundError:
                return {
                    "status": "INSUFFICIENT",
                    "reason": "refresh manifest is not configured; no network request was made",
                    "source_health_snapshot_id": source_health_id,
                    "source_health_snapshot_path": source_health_path,
                    "resource_audit": {
                        "explicit_query_manifest": False,
                        "full_market_deep_data": False,
                        "data_fetched": False,
                    },
                }
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
                return {
                    "status": "BLOCKED",
                    "reason": f"refresh manifest cannot be read: {type(error).__name__}: {error}",
                    "source_health_snapshot_id": source_health_id,
                    "source_health_snapshot_path": source_health_path,
                }
        else:
            manifest = {
                "schema_version": "data-source-refresh-input.v1",
                "as_of": _task_as_of(task),
                "queries": raw_manifest,
            }
        if not isinstance(manifest, Mapping):
            return {
                "status": "BLOCKED",
                "reason": "refresh manifest must be an object",
                "source_health_snapshot_id": source_health_id,
                "source_health_snapshot_path": source_health_path,
            }
        if not isinstance(manifest.get("queries"), list) or not manifest.get("queries"):
            return {
                "status": "INSUFFICIENT",
                "reason": "no explicit refresh queries configured; no network request was made",
                "source_health_snapshot_id": source_health_id,
                "source_health_snapshot_path": source_health_path,
                "resource_audit": {
                    "explicit_query_manifest": False,
                    "full_market_deep_data": False,
                    "data_fetched": False,
                },
            }
        try:
            report = build_data_source_refresh(
                manifest,
                router,
                as_of=str(scope.get("as_of") or _task_as_of(task)),
                refresh_id=str(scope.get("refresh_id") or ""),
                max_queries=min(int(scope.get("query_limit") or 20), 20),
                max_rows_per_query=min(int(scope.get("row_limit") or 500), 5000),
                source_health_snapshot_id=source_health_id,
            )
        except (DataRefreshError, TypeError, ValueError) as error:
            return {
                "status": "BLOCKED",
                "reason": f"refresh manifest rejected: {type(error).__name__}: {error}",
                "source_health_snapshot_id": source_health_id,
                "source_health_snapshot_path": source_health_path,
            }

        report["trigger_task_id"] = str(task.get("task_id") or "")
        report_id = str(report["refresh_id"])
        previous_report = self._latest_data_refresh_report(
            self.data_root / "data_source_refreshes",
            current_as_of=str(report["as_of"]),
            current_id=report_id,
        )
        try:
            tracking = build_data_refresh_tracking_report(
                report,
                previous_report,
                as_of=str(report["as_of"]),
                tracking_id=f"data-refresh-tracking-{report_id}",
            )
        except DataRefreshTrackingError as error:
            return {
                "status": "BLOCKED",
                "reason": f"refresh tracking failed: {error}",
                "source_health_snapshot_id": source_health_id,
                "source_health_snapshot_path": source_health_path,
            }
        tracking["trigger_task_id"] = str(task.get("task_id") or "")
        version = build_research_version(
            {
                "subject_type": "mixed",
                "subject_ids": sorted(
                    {
                        str(row.get("subject_id") or "")
                        for row in report.get("queries") or []
                        if isinstance(row, Mapping) and str(row.get("subject_id") or "")
                    }
                ) or ["bounded-refresh"],
                "research_as_of": str(report["as_of"]),
                "previous_version_id": _latest_previous_research_version_id(
                    self.data_root / "research_versions",
                    artifact_type="data_source_refresh",
                    subject_ids=[
                        str(row.get("subject_id") or "")
                        for row in report.get("queries") or []
                        if isinstance(row, Mapping)
                    ],
                    as_of=str(report["as_of"]),
                    artifact_id=report_id,
                ),
                "execution_mode": "LOCAL_ONLY",
                "affected_modules": ["data_source_refresh", "evidence_freshness"],
                "artifact_refs": [{
                    "artifact_id": report_id,
                    "artifact_type": "data_source_refresh",
                    "as_of": str(report["as_of"]),
                    "content_hash": _hash_payload(
                        {
                            key: value
                            for key, value in report.items()
                            if key not in {"research_version_id", "trigger_task_id"}
                        }
                    ),
                }, {
                    "artifact_id": tracking["tracking_id"],
                    "artifact_type": "data_source_refresh_tracking",
                    "as_of": str(tracking["as_of"]),
                    "content_hash": _hash_payload(tracking),
                }],
                "source_ids": sorted(
                    {
                        str(row.get("source") or "")
                        for row in report.get("queries") or []
                        if isinstance(row, Mapping) and str(row.get("source") or "")
                    }
                ),
                "rule_versions": {"data_refresh": "data-source-refresh-rules.v1"},
                "source_health_snapshot_id": source_health_id,
                "version_status": "VALID" if report["status"] == "SUCCESS" else "REVIEW_REQUIRED",
            },
            version_id=f"research-version-{report_id}",
        )
        report["research_version_id"] = version["version_id"]
        path = JsonSnapshotStore(self.data_root / "data_source_refreshes").write_immutable(
            report_id, report
        )
        tracking_path = JsonSnapshotStore(
            self.data_root / "data_source_refresh_tracking"
        ).write_immutable(tracking["tracking_id"], tracking)
        version_path = JsonSnapshotStore(self.data_root / "research_versions").write_immutable(
            version["version_id"], version
        )
        return {
            "status": report["status"],
            "artifact_path": str(path),
            "refresh_id": report_id,
            "successful_query_count": report["successful_query_count"],
            "query_count": report["query_count"],
            "tracking_id": tracking["tracking_id"],
            "tracking_status": tracking["tracking_status"],
            "tracking_path": str(tracking_path),
            "research_version_id": version["version_id"],
            "research_version_path": str(version_path),
            "source_health_snapshot_id": source_health_id,
            "source_health_snapshot_path": source_health_path,
        }

    def _latest_data_refresh_report(
        self,
        directory: Path,
        *,
        current_as_of: str,
        current_id: str,
    ) -> dict[str, Any] | None:
        if not directory.exists():
            return None
        candidates: list[dict[str, Any]] = []
        for path in sorted(directory.glob("*.json")):
            try:
                report = validate_data_source_refresh(_read_json_object(path))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, DataRefreshError):
                continue
            if report["refresh_id"] == current_id:
                continue
            if str(report["as_of"]) < str(current_as_of):
                candidates.append(report)
        return max(
            candidates,
            key=lambda item: (str(item.get("as_of") or ""), str(item.get("refresh_id") or "")),
            default=None,
        )

    def _run_event_triggered_scan(self, task: Mapping[str, Any]) -> dict[str, Any]:
        event = dict(task.get("event") or {})
        event_type = str(event.get("event_type") or task.get("event_type") or "")
        as_of = _task_as_of(task)
        source_health_id, source_health_path = self._write_source_health_snapshot(task)
        report_id = f"event-scan-{str(task.get('event_id') or 'unknown')}"
        payload = {
            "schema_version": "event-triggered-scan.v1",
            "report_id": report_id,
            "as_of": as_of,
            "trigger_task_id": str(task.get("task_id") or ""),
            "event": event,
            "event_type": event_type,
            "affected_modules": list(_EVENT_MODULES.get(event_type, ("research_report",))),
            "status": "REVIEW_REQUIRED",
            "execution_mode": "LOCAL_ONLY",
            "directional_conclusion": False,
            "decision_snapshot_created": False,
            "read_only": True,
            "execution_enabled": False,
        }
        impact_queue = build_research_impact_queue(
            event,
            _load_research_versions(self.data_root / "research_versions"),
        )
        impact_path = JsonSnapshotStore(
            self.data_root / "research_impact_queues"
        ).write_immutable(impact_queue["queue_id"], impact_queue)
        payload["impact_queue_id"] = impact_queue["queue_id"]
        payload["impact_queue_status"] = impact_queue["review_status"]
        payload["automatic_incremental_update"] = self._run_automatic_incremental_update(
            event,
            as_of=as_of,
            source_health_id=source_health_id,
            source_health_path=source_health_path,
        )
        version = build_research_version(
            {
                "subject_type": "mixed",
                "subject_ids": [
                    str(event.get("company_id") or event.get("industry_id") or event_type)
                ],
                "research_as_of": as_of,
                "previous_version_id": _latest_previous_research_version_id(
                    self.data_root / "research_versions",
                    artifact_type="event_scan",
                    subject_ids=[
                        str(event.get("company_id") or event.get("industry_id") or event_type)
                    ],
                    as_of=as_of,
                    artifact_id=report_id,
                ),
                "execution_mode": "LOCAL_ONLY",
                "affected_modules": payload["affected_modules"],
                "artifact_refs": [{
                    "artifact_id": report_id,
                    "artifact_type": "event_scan",
                    "as_of": as_of,
                    "content_hash": _hash_payload(payload),
                }],
                "source_ids": [str(event.get("source") or "")],
                "source_health_snapshot_id": source_health_id,
                "version_status": "REVIEW_REQUIRED",
            },
            version_id=f"research-version-{report_id}",
        )
        payload["research_version_id"] = version["version_id"]
        path = JsonSnapshotStore(self.data_root / "scheduled_events").write_immutable(report_id, payload)
        version_path = JsonSnapshotStore(self.data_root / "research_versions").write_immutable(version["version_id"], version)
        return {
            "status": "SUCCESS",
            "artifact_path": str(path),
            "report_id": report_id,
            "affected_modules": payload["affected_modules"],
            "review_required": True,
            "research_version_id": version["version_id"],
            "research_version_path": str(version_path),
            "impact_queue_id": impact_queue["queue_id"],
            "impact_queue_status": impact_queue["review_status"],
            "impact_queue_path": str(impact_path),
            "source_health_snapshot_id": source_health_id,
            "source_health_snapshot_path": source_health_path,
            "automatic_incremental_update": payload["automatic_incremental_update"],
        }

    def _run_automatic_incremental_update(
        self,
        event: Mapping[str, Any],
        *,
        as_of: str,
        source_health_id: str,
        source_health_path: str,
    ) -> dict[str, Any]:
        """Refresh a saved company pipeline only when local inputs are explicit.

        Events without all three input references remain review-only. This keeps
        scheduling useful for continuous research while preventing a timer from
        inventing evidence or silently fetching an unbounded data set.
        """

        event_payload = event.get("payload")
        if not isinstance(event_payload, Mapping):
            return {"status": "NOT_REQUESTED", "reason": "no local incremental inputs"}
        input_keys = (
            "previous_pipeline_path",
            "previous_supplemental_path",
            "evidence_path",
        )
        supplied = [key for key in input_keys if str(event_payload.get(key) or "").strip()]
        if not supplied:
            return {"status": "NOT_REQUESTED", "reason": "no local incremental inputs"}
        missing = [key for key in input_keys if not str(event_payload.get(key) or "").strip()]
        if missing:
            return {
                "status": "BLOCKED",
                "reason": "missing local incremental input references",
                "missing_inputs": missing,
                "review_required": True,
            }

        try:
            previous_pipeline_path = self._resolve_input_path(
                str(event_payload["previous_pipeline_path"])
            )
            previous_supplemental_path = self._resolve_input_path(
                str(event_payload["previous_supplemental_path"])
            )
            evidence_path = self._resolve_input_path(str(event_payload["evidence_path"]))
            previous_pipeline = _read_json_object(previous_pipeline_path)
            previous_supplemental = _read_json_object(previous_supplemental_path)
            evidence_payload = _read_json_value(evidence_path)
            evidence_records = (
                evidence_payload.get("records")
                if isinstance(evidence_payload, Mapping)
                else evidence_payload
            )
            if not isinstance(evidence_records, list):
                raise IncrementalUpdateError("evidence input must be a records list")

            company_scope_reports = _read_optional_json(
                self._resolve_input_path(str(event_payload["company_scopes_path"]))
                if str(event_payload.get("company_scopes_path") or "").strip()
                else None
            )
            market_structure_report = _read_optional_json(
                self._resolve_input_path(str(event_payload["market_structure_path"]))
                if str(event_payload.get("market_structure_path") or "").strip()
                else None
            )
            evidence_bundle = _read_optional_json(
                self._resolve_input_path(str(event_payload["evidence_bundle_path"]))
                if str(event_payload.get("evidence_bundle_path") or "").strip()
                else None
            )
            execution_mode = str(event_payload.get("execution_mode") or "LOCAL_ONLY")
            update = build_incremental_update(
                previous_pipeline,
                previous_supplemental,
                evidence_records,
                as_of=str(event_payload.get("as_of") or as_of),
                snapshot_id=str(event_payload.get("snapshot_id") or ""),
                execution_mode=execution_mode,
                company_scope_reports=company_scope_reports,
                market_structure_report=market_structure_report,
                evidence_bundle=evidence_bundle,
            )
            updated_supplemental = dict(update["updated_supplemental"])
            updated_pipeline = dict(update["updated_pipeline"])
            updated_pipeline["source_health_snapshot_id"] = source_health_id
            version = build_research_version_from_pipeline(
                updated_pipeline,
                supplemental=updated_supplemental,
                evidence_bundle=evidence_bundle,
                previous_version_id=str(
                    event_payload.get("previous_version_id")
                    or previous_pipeline.get("research_version_id")
                    or ""
                ),
                execution_mode=execution_mode,
                affected_modules=update.get("deferred_review_modules") or (),
            )
            updated_pipeline["research_version_id"] = version["version_id"]
            update_id = str(update["update_id"])
            updated_supplemental_path = JsonSnapshotStore(
                self.data_root / "company_supplemental"
            ).write_immutable(updated_supplemental["report_id"], updated_supplemental)
            updated_pipeline_path = JsonSnapshotStore(
                self.data_root / "company_research_pipelines"
            ).write_immutable(updated_pipeline["pipeline_id"], updated_pipeline)
            version_path = JsonSnapshotStore(
                self.data_root / "research_versions"
            ).write_immutable(version["version_id"], version)
            update_payload = dict(update)
            update_payload["updated_supplemental"] = updated_supplemental
            update_payload["updated_pipeline"] = updated_pipeline
            update_payload["research_version_id"] = version["version_id"]
            update_payload["source_health_snapshot_id"] = source_health_id
            update_payload["source_health_snapshot_path"] = source_health_path
            update_path = JsonSnapshotStore(
                self.data_root / "company_incremental_updates"
            ).write_immutable(update_id, update_payload)
            return {
                "status": "UPDATED",
                "update_id": update_id,
                "update_path": str(update_path),
                "updated_supplemental_id": updated_supplemental["report_id"],
                "updated_supplemental_path": str(updated_supplemental_path),
                "updated_pipeline_id": updated_pipeline["pipeline_id"],
                "updated_pipeline_path": str(updated_pipeline_path),
                "research_version_id": version["version_id"],
                "research_version_path": str(version_path),
                "new_evidence_count": int(update.get("new_evidence_count") or 0),
                "affected_modules": list(update.get("deferred_review_modules") or []),
                "review_required": True,
            }
        except (
            OSError,
            UnicodeDecodeError,
            TypeError,
            ValueError,
            IncrementalUpdateError,
        ) as error:
            return {
                "status": "BLOCKED",
                "reason": f"automatic incremental update failed: {type(error).__name__}: {error}",
                "review_required": True,
            }

    def _resolve_input_path(self, value: str) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else self.data_root / path

    def _run_company_pool_refresh(self, task: Mapping[str, Any]) -> dict[str, Any]:
        event = dict(task.get("event") or {})
        event_payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
        source_health_id, source_health_path = self._write_source_health_snapshot(task)
        industry_id = str(event.get("industry_id") or event_payload.get("industry_id") or "").strip()
        industry_name = str(event_payload.get("industry_name") or event.get("industry_name") or industry_id).strip()
        if not industry_id:
            return {
                "status": "INSUFFICIENT",
                "reason": "event has no industry_id",
                "source_health_snapshot_id": source_health_id,
                "source_health_snapshot_path": source_health_path,
            }
        scope = task.get("scope") or {}
        limit = min(int(scope.get("company_pool_size") or 30), 30)
        as_of = _task_as_of(task)
        tonghuashun_industry_id = str(
            event_payload.get("tonghuashun_industry_id") or industry_id
        )
        industry = IndustryRadarSnapshot(
            industry_id=industry_id,
            display_name=industry_name,
            as_of=as_of,
            state=IndustryState.INSUFFICIENT,
            source_ids={"tonghuashun": tonghuashun_industry_id},
        )
        try:
            provider = self.company_pool_factory(limit)
            candidates = list(provider.candidates(industry, limit))
            candidates = list(
                self.company_data_factory().enrich(candidates, CompanyDataTier.LIGHT)
            )
        except (TonghuashunCompanyPoolError, OSError, TimeoutError) as error:
            raise RetryableTaskError(f"company pool source unavailable: {error}") from error
        if not candidates:
            return {"status": "INSUFFICIENT", "reason": "company pool returned no rows"}
        snapshot_id = f"scheduled-company-pool-{industry_id}-{as_of}"
        payload = {
            "schema_version": "industry-company-pool.v1",
            "snapshot_id": snapshot_id,
            "industry": industry.to_dict(),
            "source": _metadata(provider, as_of, "tonghuashun_company_pool"),
            "candidates": [candidate.to_dict() for candidate in candidates],
            "read_only": True,
            "full_industry_membership_loaded": False,
            "light_data": {"requested": True, "tier": "LIGHT"},
            "trigger_task_id": str(task.get("task_id") or ""),
            "resource_audit": {
                "company_pool_limit": limit,
                "company_deep_data_loaded": False,
                "full_market_deep_data": False,
            },
            "execution_enabled": False,
        }
        version = build_research_version(
            {
                "subject_type": "industry",
                "subject_ids": [industry_id],
                "research_as_of": as_of,
                "previous_version_id": _latest_previous_research_version_id(
                    self.data_root / "research_versions",
                    artifact_type="company_pool",
                    subject_ids=[industry_id],
                    as_of=as_of,
                    artifact_id=snapshot_id,
                ),
                "execution_mode": "LOCAL_ONLY",
                "affected_modules": ["company_pool", "company_screen"],
                "artifact_refs": [{
                    "artifact_id": snapshot_id,
                    "artifact_type": "company_pool",
                    "as_of": as_of,
                    "content_hash": _hash_payload(payload),
                }],
                "source_ids": ["tonghuashun_company_pool"],
                "source_health_snapshot_id": source_health_id,
                "version_status": "VALID",
            },
            version_id=f"research-version-{snapshot_id}",
        )
        payload["research_version_id"] = version["version_id"]
        path = JsonSnapshotStore(self.data_root / "company_pools").write_immutable(snapshot_id, payload)
        version_path = JsonSnapshotStore(self.data_root / "research_versions").write_immutable(version["version_id"], version)
        return {
            "status": "SUCCESS",
            "artifact_path": str(path),
            "snapshot_id": snapshot_id,
            "candidate_count": len(candidates),
            "light_data": True,
            "research_version_id": version["version_id"],
            "research_version_path": str(version_path),
            "source_health_snapshot_id": source_health_id,
            "source_health_snapshot_path": source_health_path,
        }

    def _write_source_health_snapshot(
        self,
        task: Mapping[str, Any],
        *,
        router: DataSourceRouter | None = None,
    ) -> tuple[str, str]:
        """Record adapter readiness for this task without replacing fetch evidence."""

        task_id = str(task.get("task_id") or "unknown-task").strip()
        attempt = int(task.get("attempts") or 1)
        snapshot_id = f"source-health-{task_id}-attempt-{attempt}"
        checked_at = str(
            task.get("started_at") or task.get("created_at") or ""
        ).strip()
        snapshot = build_source_health_snapshot(
            router or default_data_source_router(),
            checked_at=checked_at,
            snapshot_id=snapshot_id,
        )
        path = JsonSnapshotStore(self.data_root / "source_health").write_immutable(
            snapshot["snapshot_id"], snapshot
        )
        return snapshot["snapshot_id"], str(path)

    def _default_radar_factory(self, source: str, limit: int) -> Any:
        if source == "eastmoney":
            return EastmoneyIndustryRadar(page_size=limit)
        if source == "tonghuashun":
            return TonghuashunIndustryRadar(page_size=limit)
        try:
            registry = IndustryAliasRegistry.from_file(self.alias_file)
        except Exception as error:
            raise ScheduledTaskRunnerError(f"unable to load industry aliases: {error}") from error
        return CrossSourceIndustryRadar(
            EastmoneyIndustryRadar(page_size=limit),
            TonghuashunIndustryRadar(page_size=limit),
            primary_name="eastmoney",
            secondary_name="tonghuashun",
            alias_registry=registry,
        )


def _task_as_of(task: Mapping[str, Any]) -> str:
    scope = task.get("scope") or {}
    explicit = str(scope.get("as_of") or "").strip()
    if explicit:
        return explicit[:10]
    created = str(task.get("created_at") or "").strip()
    if created:
        return created[:10]
    return datetime.now(timezone.utc).date().isoformat()


def _metadata(provider: Any, as_of: str, fallback_provider: str) -> dict[str, Any]:
    metadata = {}
    if hasattr(provider, "metadata"):
        try:
            metadata = provider.metadata(as_of)
        except TypeError:
            metadata = provider.metadata()
    if not isinstance(metadata, Mapping):
        metadata = {}
    return {"provider": fallback_provider, **dict(metadata), "as_of": as_of, "read_only": True}


def _hash_payload(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _read_json_value(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_object(path: Path) -> dict[str, Any]:
    value = _read_json_value(path)
    if not isinstance(value, Mapping):
        raise IncrementalUpdateError(f"JSON input must be an object: {path}")
    return dict(value)


def _date_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if len(text) < 10:
        raise ValueError(f"{name} must be an ISO date")
    date_text = text[:10]
    try:
        datetime.fromisoformat(date_text)
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO date") from error
    return date_text


def _read_optional_json(path: Path | None) -> Any:
    return _read_json_value(path) if path is not None else None


def _load_research_versions(input_dir: Path) -> list[dict[str, Any]]:
    """Load only saved research manifests, never reports or replay artifacts."""

    versions: list[dict[str, Any]] = []
    if not input_dir.exists():
        return versions
    for path in sorted(input_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if payload.get("schema_version") == "research-version.v1":
            versions.append(payload)
    return versions


def _latest_previous_research_version_id(
    input_dir: Path,
    *,
    artifact_type: str,
    subject_ids: Sequence[str],
    as_of: str,
    artifact_id: str = "",
) -> str:
    """Find the latest compatible immutable version for a scheduled artifact.

    Scheduled jobs create a new manifest rather than overwriting the previous
    one.  Matching on artifact type and subject prevents a data-refresh or
    event version for an unrelated object from becoming a false predecessor.
    """

    wanted_type = str(artifact_type or "").strip()
    wanted_subjects = {str(value).strip() for value in subject_ids if str(value).strip()}
    cutoff = str(as_of or "").strip()[:10]
    current_artifact = str(artifact_id or "").strip()
    candidates: list[dict[str, Any]] = []
    if not wanted_type or not input_dir.exists():
        return ""
    for path in sorted(input_dir.glob("*.json")):
        try:
            version = validate_research_version(_read_json_object(path))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            continue
        if str(version.get("research_as_of") or "")[:10] > cutoff:
            continue
        refs = [
            ref
            for ref in version.get("artifact_refs") or []
            if isinstance(ref, Mapping) and str(ref.get("artifact_type") or "") == wanted_type
        ]
        if not refs:
            continue
        if current_artifact and any(str(ref.get("artifact_id") or "") == current_artifact for ref in refs):
            continue
        version_subjects = {
            str(value).strip()
            for value in version.get("subject_ids") or []
            if str(value).strip()
        }
        if wanted_subjects and version_subjects and not wanted_subjects.intersection(version_subjects):
            continue
        candidates.append(version)
    if not candidates:
        return ""
    selected = max(
        candidates,
        key=lambda item: (
            str(item.get("research_as_of") or ""),
            str(item.get("created_at") or ""),
            str(item.get("version_id") or ""),
        ),
    )
    return str(selected.get("version_id") or "")


def _candidate_queue_summary(
    input_dir: Path, *, candidate_capacity: int, watch_capacity: int
) -> dict[str, Any]:
    latest: tuple[str, dict[str, Any]] | None = None
    if input_dir.exists():
        for path in sorted(input_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if payload.get("schema_version") != "company-candidate-queue.v1":
                continue
            as_of = str(payload.get("as_of") or "")
            if latest is None or as_of > latest[0]:
                latest = (as_of, payload)
    if latest is None:
        return {
            "status": "NO_QUEUE",
            "candidate_count": 0,
            "candidate_capacity": candidate_capacity,
            "watch_capacity": watch_capacity,
            "items": [],
        }
    items = list(latest[1].get("items") or [])
    return {
        "status": "AVAILABLE",
        "as_of": latest[0],
        "candidate_count": len(items),
        "candidate_capacity": candidate_capacity,
        "watch_capacity": watch_capacity,
        "items": [
            {
                "company_id": str(item.get("company_id") or ""),
                "display_name": str(item.get("display_name") or ""),
                "candidate_state": str(item.get("candidate_state") or ""),
            }
            for item in items[:watch_capacity]
        ],
    }


def _latest_opportunity_scans(
    input_dir: Path, *, as_of: str
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return the two latest bounded candidate snapshots at or before ``as_of``."""

    snapshots: list[tuple[str, dict[str, Any]]] = []
    if not input_dir.exists():
        return None, None
    for path in sorted(input_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if payload.get("schema_version") not in {
            "opportunity-scan.v1",
            "industry-discovery.v1",
        }:
            continue
        snapshot_as_of = str(payload.get("as_of") or "")
        if snapshot_as_of and snapshot_as_of <= as_of:
            snapshots.append((snapshot_as_of, payload))
    snapshots.sort(key=lambda item: item[0])
    if not snapshots:
        return None, None
    current = snapshots[-1][1]
    previous = snapshots[-2][1] if len(snapshots) > 1 else None
    return current, previous
