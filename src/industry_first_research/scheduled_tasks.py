"""Local handlers for the bounded scheduler task types."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
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
    and event review records. It does not start deep company research or create a
    decision snapshot on behalf of a timer.
    """

    def __init__(
        self,
        *,
        data_root: str | Path = "data",
        alias_file: str | Path = "docs/industry_aliases.v1.json",
        radar_factory: RadarFactory | None = None,
        company_pool_factory: CompanyPoolFactory | None = None,
        company_data_factory: CompanyDataFactory | None = None,
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

    def handlers(self) -> dict[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]]:
        return {
            "industry_radar_refresh": self._run_industry_radar_refresh,
            "daily_delta_scan": self._run_daily_delta_scan,
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
        try:
            provider = self.radar_factory(source, limit)
            items = list(provider.snapshots(as_of))
        except (EastmoneyAPIError, TonghuashunAPIError, OSError, TimeoutError) as error:
            raise RetryableTaskError(f"industry radar source unavailable: {error}") from error
        if not items:
            return {"status": "INSUFFICIENT", "reason": "radar returned no industry rows"}
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
        path = JsonSnapshotStore(self.data_root / "radar").write(snapshot_id, payload)
        return {
            "status": "SUCCESS",
            "artifact_path": str(path),
            "snapshot_id": snapshot_id,
            "item_count": len(items),
            "source": source,
        }

    def _run_daily_delta_scan(self, task: Mapping[str, Any]) -> dict[str, Any]:
        scope = task.get("scope") or {}
        source = str(scope.get("radar_source") or "cross")
        as_of = _task_as_of(task)
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
            return {"status": "INSUFFICIENT", "reason": str(error)}
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
        path = JsonSnapshotStore(self.data_root / "scheduled_deltas").write(report_id, report)
        status = "SUCCESS" if report["data_quality"]["status"] == "OK" else "INSUFFICIENT"
        return {
            "status": status,
            "artifact_path": str(path),
            "report_id": report_id,
            "candidate_count": candidate_summary["candidate_count"],
            "reason": report["data_quality"]["reason"],
        }

    def _run_event_triggered_scan(self, task: Mapping[str, Any]) -> dict[str, Any]:
        event = dict(task.get("event") or {})
        event_type = str(event.get("event_type") or task.get("event_type") or "")
        as_of = _task_as_of(task)
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
        path = JsonSnapshotStore(self.data_root / "scheduled_events").write(report_id, payload)
        return {
            "status": "SUCCESS",
            "artifact_path": str(path),
            "report_id": report_id,
            "affected_modules": payload["affected_modules"],
            "review_required": True,
        }

    def _run_company_pool_refresh(self, task: Mapping[str, Any]) -> dict[str, Any]:
        event = dict(task.get("event") or {})
        event_payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
        industry_id = str(event.get("industry_id") or event_payload.get("industry_id") or "").strip()
        industry_name = str(event_payload.get("industry_name") or event.get("industry_name") or industry_id).strip()
        if not industry_id:
            return {"status": "INSUFFICIENT", "reason": "event has no industry_id"}
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
        path = JsonSnapshotStore(self.data_root / "company_pools").write(snapshot_id, payload)
        return {
            "status": "SUCCESS",
            "artifact_path": str(path),
            "snapshot_id": snapshot_id,
            "candidate_count": len(candidates),
            "light_data": True,
        }

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
