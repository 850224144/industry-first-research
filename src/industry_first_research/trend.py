"""Read-only historical trend summaries for saved industry radar snapshots."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from typing import Any

from .cross_validation import normalize_industry_name
from .storage import JsonSnapshotStore


_DIRECTIONAL_STATES = {"CLEARING", "DETERIORATING"}


class RadarTrendError(ValueError):
    """Raised when radar snapshots cannot form a valid historical report."""


def build_trend_report(
    input_dir: str | Path,
    *,
    source: str = "cross",
    as_of: str | None = None,
    window: int = 10,
    min_observations: int = 3,
    min_direction_ratio: float = 2 / 3,
) -> dict[str, Any]:
    """Summarise repeated directional observations without creating decisions."""

    _validate_options(window, min_observations, min_direction_ratio)
    payloads = list(_load_payloads(Path(input_dir), source))
    if as_of is not None:
        payloads = [item for item in payloads if item["as_of"] <= as_of]
    payloads = payloads[-window:]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    display_names: dict[str, str] = {}
    industry_ids: dict[str, str] = {}

    for payload in payloads:
        for item in payload["items"]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("display_name", "")).strip()
            key = normalize_industry_name(name)
            state = item.get("state")
            if not key or state not in _DIRECTIONAL_STATES:
                continue
            grouped[key].append(
                {
                    "as_of": str(item.get("as_of") or payload["as_of"]),
                    "state": state,
                    "evidence_completeness": str(
                        item.get("evidence_completeness") or "UNKNOWN"
                    ),
                }
            )
            display_names[key] = name
            industry_ids[key] = str(item.get("industry_id") or key)

    summaries = [
        _summarize(
            key,
            display_names[key],
            industry_ids[key],
            observations,
            min_observations=min_observations,
            min_direction_ratio=min_direction_ratio,
        )
        for key, observations in grouped.items()
    ]
    summaries.sort(key=lambda item: (item["trend_state"], item["display_name"]))
    report_as_of = as_of or (payloads[-1]["as_of"] if payloads else None)
    return {
        "schema_version": "industry-radar-trend.v1",
        "report_id": f"{source}-industry-trend-{report_as_of or 'empty'}",
        "source": source,
        "as_of": report_as_of,
        "window": window,
        "input_snapshot_count": len(payloads),
        "minimum_observations": min_observations,
        "minimum_direction_ratio": min_direction_ratio,
        "read_only": True,
        "proposal_only": True,
        "execution_enabled": False,
        "data_quality": {
            "status": "OK" if payloads else "INSUFFICIENT_DATA",
            "reason": (
                "Historical trend requires repeated saved snapshots; no matching snapshots were found."
                if not payloads
                else "Directional observations are summarized without company or execution conclusions."
            ),
        },
        "items": summaries,
    }


def write_trend_report(report: dict[str, Any], output_dir: str | Path) -> Path:
    return JsonSnapshotStore(output_dir).write(str(report["report_id"]), report)


def _load_payloads(input_dir: Path, source: str) -> tuple[dict[str, Any], ...]:
    prefix = f"{source}-industry-"
    payloads: dict[str, dict[str, Any]] = {}
    if not input_dir.exists():
        return ()
    for path in sorted(input_dir.glob(f"{prefix}*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RadarTrendError(f"invalid radar snapshot {path.name}: {error}") from error
        if payload.get("schema_version") != "industry-radar.v1":
            continue
        source_meta = payload.get("source")
        items = payload.get("items")
        if not isinstance(source_meta, dict) or not isinstance(items, list):
            raise RadarTrendError(f"invalid radar snapshot shape: {path.name}")
        snapshot_as_of = source_meta.get("as_of") or _date_from_name(path.name, prefix)
        if not snapshot_as_of:
            raise RadarTrendError(f"snapshot date is missing: {path.name}")
        payloads[str(snapshot_as_of)] = {"as_of": str(snapshot_as_of), "items": items}
    return tuple(payloads[key] for key in sorted(payloads))


def _date_from_name(name: str, prefix: str) -> str | None:
    suffix = name.removeprefix(prefix).removesuffix(".json")
    return suffix if len(suffix) == 10 else None


def _summarize(
    key: str,
    display_name: str,
    industry_id: str,
    observations: list[dict[str, Any]],
    *,
    min_observations: int,
    min_direction_ratio: float,
) -> dict[str, Any]:
    by_date = {observation["as_of"]: observation for observation in observations}
    ordered = [by_date[date] for date in sorted(by_date)]
    counts = {
        "CLEARING": sum(item["state"] == "CLEARING" for item in ordered),
        "DETERIORATING": sum(item["state"] == "DETERIORATING" for item in ordered),
    }
    total = len(ordered)
    dominant_state = max(counts, key=counts.get)
    dominant_count = counts[dominant_state]
    ratio = dominant_count / total if total else 0.0
    cross_validated_days = sum(
        item["evidence_completeness"] == "CROSS_VALIDATED" for item in ordered
    )
    if total < min_observations:
        trend_state = "INSUFFICIENT"
        direction = None
        reason = f"Only {total} distinct directional observation(s); at least {min_observations} are required."
    elif ratio < min_direction_ratio:
        trend_state = "MIXED"
        direction = None
        reason = f"Dominant direction covers {ratio:.1%} of observations, below the {min_direction_ratio:.1%} threshold."
    elif dominant_state == "CLEARING":
        trend_state = "PERSISTENT_STRENGTH"
        direction = "CLEARING"
        reason = "Repeated daily strength observations are directionally consistent; review only."
    else:
        trend_state = "PERSISTENT_WEAKNESS"
        direction = "DETERIORATING"
        reason = "Repeated daily weakness observations are directionally consistent; review only."
    return {
        "industry_key": key,
        "industry_id": industry_id,
        "display_name": display_name,
        "trend_state": trend_state,
        "direction": direction,
        "observation_count": total,
        "direction_counts": counts,
        "direction_ratio": round(ratio, 6),
        "cross_validated_days": cross_validated_days,
        "evidence_completeness": (
            "CROSS_VALIDATED_TREND"
            if cross_validated_days == total and total
            else "MIXED_SOURCE_TREND"
            if cross_validated_days
            else "SINGLE_SOURCE_TREND"
        ),
        "observations": ordered,
        "reason": reason,
        "review_only": True,
    }


def _validate_options(window: int, min_observations: int, min_direction_ratio: float) -> None:
    if window < 1:
        raise RadarTrendError("window must be positive")
    if min_observations < 1:
        raise RadarTrendError("min_observations must be positive")
    if not 0.5 <= min_direction_ratio <= 1:
        raise RadarTrendError("min_direction_ratio must be between 0.5 and 1")
