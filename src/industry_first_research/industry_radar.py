"""Industry-level signal collection with bounded source routing.

The collector deliberately stops before company research. A configuration can
define only the indicators needed for one industry; each indicator gets its own
source fallback chain and lineage. Collection is not verification or an
investment conclusion.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .config import radar_from_config
from .data_sources import DataSourceExhaustedError, DataSourceRouter
from .models import IndustryRadarSnapshot, IndustrySignal


@dataclass
class IndustryRadarCollection:
    snapshot: IndustryRadarSnapshot
    collection_status: str
    source_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    missing_signals: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    configured_query_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot": self.snapshot.to_dict(),
            "collection_status": self.collection_status,
            "source_results": self.source_results,
            "missing_signals": self.missing_signals,
            "errors": self.errors,
            "resource_audit": {
                "industry_signal_query_count": self.configured_query_count,
                "company_pool_loaded": False,
                "company_deep_data_loaded": False,
                "full_market_deep_data": False,
            },
        }


class IndustryRadarCollector:
    """Collect configured industry indicators without loading companies."""

    def __init__(self, router: DataSourceRouter) -> None:
        self.router = router

    def collect(
        self,
        config: Mapping[str, Any],
        as_of: str | None = None,
    ) -> IndustryRadarCollection:
        if not isinstance(config, Mapping):
            raise ValueError("industry radar config must be an object")
        base_config = dict(config)
        if as_of:
            base_config["as_of"] = as_of
        snapshot = radar_from_config(base_config)
        queries = base_config.get("radar_queries", [])
        if not isinstance(queries, Sequence) or isinstance(queries, (str, bytes)):
            raise ValueError("radar_queries must be an array")

        signals = list(snapshot.signals)
        signal_indexes = {signal.name: index for index, signal in enumerate(signals)}
        source_results: dict[str, dict[str, Any]] = {}
        missing_signals: list[str] = []
        errors: list[str] = []
        successful = 0
        required_failures = 0

        for item in queries:
            if not isinstance(item, Mapping):
                raise ValueError("each radar query must be an object")
            name = str(item.get("name", "")).strip()
            if not name:
                raise ValueError("each radar query requires name")
            query = item.get("query", {})
            if not isinstance(query, Mapping):
                raise ValueError(f"query for {name} must be an object")
            required = bool(item.get("required", True))
            try:
                result = self.router.fetch(
                    query,
                    str(base_config["as_of"]),
                    subject_type="industry",
                    source_names=tuple(item.get("source_names", ())) or None,
                )
                source_results[name] = result.to_dict()
                value = _value_at_path(result.data, str(item.get("value_path", "")))
                if value is _MISSING:
                    raise ValueError(
                        "configured value_path was not found: "
                        + str(item.get("value_path", ""))
                    )
                signal = IndustrySignal(
                    name=name,
                    value=value,
                    as_of=str(base_config["as_of"]),
                    source=result.source,
                    evidence_status=str(item.get("evidence_status", "UNVERIFIED")),
                    note=str(item.get("note", "")),
                )
                if name in signal_indexes:
                    signals[signal_indexes[name]] = signal
                else:
                    signal_indexes[name] = len(signals)
                    signals.append(signal)
                successful += 1
            except DataSourceExhaustedError as error:
                source_results[name] = {
                    "source": None,
                    "data": None,
                    "attempts": [attempt.to_dict() for attempt in error.attempts],
                    "requested_sources": list(error.requested_sources),
                }
                errors.append(f"{name}: {type(error).__name__}: {error}")
                missing_signals.append(name)
                required_failures += int(required)
            except Exception as error:
                errors.append(f"{name}: {type(error).__name__}: {error}")
                missing_signals.append(name)
                required_failures += int(required)

        if not queries:
            status = "STATIC_ONLY"
        elif required_failures == 0 and successful == len(queries):
            status = "READY"
        elif successful:
            status = "PARTIAL"
        else:
            status = "INSUFFICIENT"

        collected_snapshot = IndustryRadarSnapshot(
            industry_id=snapshot.industry_id,
            display_name=snapshot.display_name,
            as_of=snapshot.as_of,
            state=snapshot.state,
            signals=tuple(signals),
            evidence_completeness=snapshot.evidence_completeness,
            opportunity_types=snapshot.opportunity_types,
            reason=snapshot.reason,
        )
        return IndustryRadarCollection(
            snapshot=collected_snapshot,
            collection_status=status,
            source_results=source_results,
            missing_signals=missing_signals,
            errors=errors,
            configured_query_count=len(queries),
        )


_MISSING = object()


def _value_at_path(value: Any, path: str) -> Any:
    """Extract a configured field without guessing provider-specific shape."""

    if not path:
        return value
    current = value
    for part in path.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        elif isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return _MISSING
        else:
            return _MISSING
    return current
