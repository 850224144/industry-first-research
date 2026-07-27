"""Thin adapters for optional czsc/chan.py market-structure implementations.

The upstream projects have different APIs and structure definitions. This
module therefore exposes a small runner contract instead of importing private
upstream internals. A runner receives the validated market-structure input and
returns a JSON-like mapping with ``timeframes``. The two implementations are
kept separate and are never turned into a consensus trading signal.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from hashlib import sha256
import importlib.util
import json
from typing import Any

from .market_structure import (
    INPUT_SCHEMA_VERSION,
    build_market_structure_report,
)
from .market_data import MarketDataError, build_market_data_snapshot


MARKET_STRUCTURE_COMPARISON_SCHEMA_VERSION = "market-structure-comparison.v1"
ADAPTER_RULE_VERSION = "market-structure-adapter-rules.v1"

Runner = Callable[[Mapping[str, Any]], Mapping[str, Any]]


class MarketStructureAdapterError(ValueError):
    """Raised when a market-structure adapter contract is invalid."""


class OptionalMarketStructureAdapter:
    """Record one optional implementation without assuming its upstream API."""

    def __init__(
        self,
        name: str,
        module_name: str,
        *,
        runner: Runner | None = None,
    ) -> None:
        self.name = name
        self.module_name = module_name
        self.runner = runner

    def analyze(self, input_report: Mapping[str, Any]) -> dict[str, Any]:
        if self.runner is None:
            if importlib.util.find_spec(self.module_name) is None:
                return self._unavailable(
                    "PACKAGE_NOT_INSTALLED",
                    f"optional package {self.module_name!r} is not installed",
                )
            return self._unavailable(
                "RUNNER_NOT_CONFIGURED",
                "package is present but its API adapter runner is not configured",
            )
        try:
            raw = self.runner(input_report)
            report = _normalise_external_report(raw, self.name)
        except Exception as error:  # external package errors must not break local research
            return self._unavailable("FAILED", f"{type(error).__name__}: {error}")
        return {
            "implementation": self.name,
            "status": "AVAILABLE",
            "implementation_version": str(
                report.get("implementation_version") or "unknown"
            ),
            "report": report,
            "raw_output_hash": _payload_hash(raw),
            "error": None,
        }

    def _unavailable(self, status: str, reason: str) -> dict[str, Any]:
        return {
            "implementation": self.name,
            "status": status,
            "implementation_version": None,
            "report": None,
            "raw_output_hash": None,
            "error": reason,
        }


class CzscAdapter(OptionalMarketStructureAdapter):
    def __init__(self, *, runner: Runner | None = None, module_name: str = "czsc") -> None:
        super().__init__("czsc", module_name, runner=runner)


class ChanPyAdapter(OptionalMarketStructureAdapter):
    def __init__(self, *, runner: Runner | None = None, module_name: str = "chan") -> None:
        super().__init__("chan_py", module_name, runner=runner)


def build_market_structure_comparison(
    input_report: Mapping[str, Any],
    *,
    market_data_snapshot: Mapping[str, Any] | None = None,
    adapters: Sequence[OptionalMarketStructureAdapter] | None = None,
    include_local: bool = True,
    comparison_id: str = "",
) -> dict[str, Any]:
    """Run local and optional structure implementations side by side."""

    _validate_input(input_report)
    if market_data_snapshot is not None:
        try:
            snapshot = build_market_data_snapshot(market_data_snapshot)
        except MarketDataError as error:
            raise MarketStructureAdapterError(str(error)) from error
        input_report = {
            **input_report,
            "subject_type": snapshot["subject"]["subject_type"],
            "subject_id": snapshot["subject"]["subject_id"],
            "display_name": snapshot["subject"].get("display_name") or input_report.get("display_name"),
            "as_of": snapshot["research_as_of"],
            "price_series_id": snapshot["snapshot_id"],
            "adjustment": snapshot["adjustment"],
            "timeframes": snapshot["series"],
            "continuous_series_rule": snapshot.get("continuous_series_rule"),
            "market_data_snapshot_id": snapshot["snapshot_id"],
        }
    if adapters is None:
        adapters = (CzscAdapter(), ChanPyAdapter())

    implementations: dict[str, dict[str, Any]] = {}
    if include_local:
        local_report = build_market_structure_report(
            input_report,
            market_data_snapshot=market_data_snapshot,
        )
        implementations["local_deterministic"] = {
            "implementation": "local_deterministic",
            "status": "AVAILABLE",
            "implementation_version": local_report["implementation_version"],
            "report": local_report,
            "raw_output_hash": _payload_hash(local_report),
            "error": None,
        }
    for adapter in adapters:
        if not isinstance(adapter, OptionalMarketStructureAdapter):
            raise MarketStructureAdapterError(
                "adapters must contain OptionalMarketStructureAdapter objects"
            )
        if adapter.name in implementations:
            raise MarketStructureAdapterError(
                f"duplicate market-structure implementation: {adapter.name}"
            )
        implementations[adapter.name] = adapter.analyze(input_report)

    comparison = _compare_timeframes(implementations)
    available_count = sum(
        item["status"] == "AVAILABLE" for item in implementations.values()
    )
    if comparison["status"] == "DIVERGENT":
        confidence = "LOW"
    elif available_count >= 2 and comparison["status"] == "CONSISTENT":
        confidence = "MEDIUM"
    elif available_count == 1:
        confidence = "LOW"
    else:
        confidence = "NOT_EVALUABLE"

    subject = _subject(input_report)
    identifier = comparison_id.strip() or str(input_report.get("snapshot_id") or "")
    if not identifier:
        identifier = f"{subject['subject_id']}-{str(input_report['as_of']).replace(':', '').replace('+', 'plus')}"
    return {
        "schema_version": MARKET_STRUCTURE_COMPARISON_SCHEMA_VERSION,
        "comparison_id": f"market-structure-comparison-{identifier}",
        "subject": subject,
        "as_of": input_report["as_of"],
        "input_schema_version": INPUT_SCHEMA_VERSION,
        "input_hash": _payload_hash(input_report),
        "implementations": implementations,
        "comparison": comparison,
        "confidence": confidence,
        "rule_version": ADAPTER_RULE_VERSION,
        "interpretation": _interpretation(comparison, confidence),
        "policy": {
            "results_kept_separate": True,
            "definition_differences_visible": True,
            "disagreement_lowers_confidence": True,
            "trading_signal_included": False,
            "automatic_order_included": False,
            "investment_conclusion": False,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _normalise_external_report(raw: Mapping[str, Any], implementation: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise MarketStructureAdapterError("runner must return a JSON object")
    raw_timeframes = raw.get("timeframes")
    if not isinstance(raw_timeframes, Mapping) or not raw_timeframes:
        raise MarketStructureAdapterError("runner output has no timeframes object")
    timeframes = {}
    for name, value in raw_timeframes.items():
        if not isinstance(value, Mapping):
            raise MarketStructureAdapterError(f"timeframe {name} must be an object")
        timeframes[str(name)] = {
            "state": str(value.get("state") or "UNKNOWN").upper(),
            "volatility": str(value.get("volatility") or "UNKNOWN").upper(),
            "position": str(value.get("position") or "UNKNOWN").upper(),
            "confirmation": str(value.get("confirmation") or "UNCONFIRMED").upper(),
            "repaint_risk": str(value.get("repaint_risk") or "UNKNOWN").upper(),
            "structure_points": _string_list(value.get("structure_points")),
            "definition_notes": _string_list(value.get("definition_notes")),
        }
    return {
        "implementation": implementation,
        "implementation_version": str(raw.get("implementation_version") or "unknown"),
        "timeframes": timeframes,
        "confirmation": str(raw.get("confirmation") or "UNCONFIRMED").upper(),
        "repaint_risk": str(raw.get("repaint_risk") or "UNKNOWN").upper(),
        "definition_notes": _string_list(raw.get("definition_notes")),
        "signal": None,
    }


def _compare_timeframes(implementations: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    available = {
        name: item["report"]
        for name, item in implementations.items()
        if item.get("status") == "AVAILABLE" and item.get("report")
    }
    timeframe_names = sorted(
        {
            timeframe
            for report in available.values()
            for timeframe in report.get("timeframes", {})
        }
    )
    by_timeframe: dict[str, dict[str, Any]] = {}
    divergent = False
    comparable = 0
    for timeframe in timeframe_names:
        states = {
            name: str(report["timeframes"].get(timeframe, {}).get("state") or "MISSING")
            for name, report in available.items()
        }
        present_states = [state for state in states.values() if state != "MISSING"]
        present = set(present_states)
        if len(present_states) >= 2:
            comparable += 1
        status = (
            "DIVERGENT"
            if len(present) > 1
            else "CONSISTENT"
            if len(present_states) >= 2
            else "INSUFFICIENT"
        )
        if status == "DIVERGENT":
            divergent = True
        by_timeframe[timeframe] = {
            "status": status,
            "states": states,
            "definition_difference": status == "DIVERGENT",
        }
    if divergent:
        status = "DIVERGENT"
    elif comparable:
        status = "CONSISTENT"
    else:
        status = "INSUFFICIENT"
    return {
        "status": status,
        "comparable_timeframe_count": comparable,
        "timeframes": by_timeframe,
    }


def _interpretation(comparison: Mapping[str, Any], confidence: str) -> str:
    if comparison["status"] == "DIVERGENT":
        return "不同结构实现对至少一个周期的定义结果不一致，降低市场结构置信度；不改变基本面结论。"
    if comparison["status"] == "INSUFFICIENT":
        return "没有足够的可比较结构实现；市场结构仅作时点辅助，不构成自动交易信号。"
    return f"结构实现结果在可比较周期内一致，但置信度为 {confidence}；不构成自动交易信号。"


def _validate_input(value: Any) -> None:
    if not isinstance(value, Mapping) or value.get("schema_version") != INPUT_SCHEMA_VERSION:
        raise MarketStructureAdapterError(f"input must be {INPUT_SCHEMA_VERSION}")


def _subject(value: Mapping[str, Any]) -> dict[str, str]:
    subject_id = str(value.get("subject_id") or value.get("ticker") or "").strip()
    subject_type = str(value.get("subject_type") or "").strip().lower()
    if not subject_id or not subject_type:
        raise MarketStructureAdapterError("subject_id and subject_type are required")
    return {
        "subject_id": subject_id,
        "subject_type": subject_type,
        "display_name": str(value.get("display_name") or ""),
    }


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        raise MarketStructureAdapterError("expected a string list")
    return [str(item) for item in value if str(item).strip()]


def _payload_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()
