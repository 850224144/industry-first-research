"""Evaluate opportunity-discovery process quality from preserved snapshots.

The module measures the process, not investment success. False-positive and
false-negative labels must be supplied by a later review sample; returns are
never used to rewrite historical candidate states.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from hashlib import sha256
import json
from typing import Any


OPPORTUNITY_QUALITY_INPUT_SCHEMA_VERSION = "opportunity-quality-input.v1"
OPPORTUNITY_QUALITY_SCHEMA_VERSION = "opportunity-quality-report.v1"
RULE_VERSION = "opportunity-quality-rules.v1"
_SCAN_SCHEMAS = {"opportunity-scan.v1", "industry-discovery.v1"}
_STATES = {"DISCOVERED", "WATCH", "CANDIDATE", "REVIEWABLE", "REJECTED", "EXPIRED"}


class OpportunityQualityError(ValueError):
    """Raised when an opportunity-quality package is invalid."""


def build_opportunity_quality_report(
    payload: Mapping[str, Any], *, quality_id: str = ""
) -> dict[str, Any]:
    """Aggregate preserved opportunity scans and explicit later review labels."""

    if not isinstance(payload, Mapping):
        raise OpportunityQualityError("opportunity quality input must be an object")
    scans = payload.get("scans") or payload.get("snapshots") or []
    if not isinstance(scans, list):
        raise OpportunityQualityError("scans must be a list")
    normalized_scans = [_validate_scan(item) for item in scans]
    normalized_scans.sort(key=lambda item: (_day(item["as_of"], "scan.as_of"), item["scan_id"]))
    hard_gate_samples = _samples(payload.get("hard_gate_samples"), "hard_gate_samples")
    false_positive_samples = _samples(payload.get("false_positive_samples"), "false_positive_samples")
    false_negative_samples = _samples(payload.get("false_negative_samples"), "false_negative_samples")
    all_review_samples = [*hard_gate_samples, *false_positive_samples, *false_negative_samples]
    as_of = str(payload.get("as_of") or (normalized_scans[-1]["as_of"] if normalized_scans else "")).strip()
    if not as_of:
        raise OpportunityQualityError("as_of is required when scans are empty")
    _day(as_of, "as_of")

    candidates_by_scan = [_candidate_map(scan) for scan in normalized_scans]
    candidate_ids = sorted({candidate_id for group in candidates_by_scan for candidate_id in group})
    transition_rows, dwell_rows = _transitions_and_dwell(normalized_scans, candidates_by_scan)
    state_counts = _state_counts(candidates_by_scan)
    scan_count = len(normalized_scans)
    empty_count = sum(
        1
        for scan, candidates in zip(normalized_scans, candidates_by_scan)
        if scan.get("empty_result") is True
        or ("empty_result" not in scan and not candidates)
    )
    watch_count = sum(counts.get("WATCH", 0) for counts in state_counts)
    candidate_count = sum(counts.get("CANDIDATE", 0) for counts in state_counts)
    deep_research_count = sum(
        1
        for sample in _all_items(normalized_scans)
        if _has_deep_research(sample)
    )
    reviewable_count = sum(counts.get("REVIEWABLE", 0) for counts in state_counts)
    metrics = {
        "scan_count": scan_count,
        "candidate_universe_count": len(candidate_ids),
        "scan_coverage": _coverage(normalized_scans),
        "hard_gate_accuracy_sample": _sample_rate(hard_gate_samples),
        "watch_to_candidate_rate": _rate(candidate_count, watch_count),
        "candidate_to_deep_research_rate": _rate(deep_research_count, candidate_count),
        "candidate_to_reviewable_rate": _rate(reviewable_count, candidate_count),
        "false_positive_sample": _sample_summary(false_positive_samples),
        "false_negative_sample": _sample_summary(false_negative_samples),
        "state_dwell_time": {
            "observations": dwell_rows,
            "average_days_by_state": _average_dwell(dwell_rows),
        },
        "empty_scan_frequency": (empty_count / scan_count) if scan_count else None,
        "empty_scan_count": empty_count,
        "state_counts": state_counts,
    }
    identifier = str(payload.get("quality_id") or quality_id).strip() or f"opportunity-quality-{_hash_payload({'as_of': as_of, 'scans': [item['scan_id'] for item in normalized_scans]})[:20]}"
    return {
        "schema_version": OPPORTUNITY_QUALITY_SCHEMA_VERSION,
        "quality_id": identifier,
        "as_of": as_of,
        "scan_ids": [item["scan_id"] for item in normalized_scans],
        "scan_count": scan_count,
        "candidate_ids": candidate_ids,
        "metrics": metrics,
        "transitions": transition_rows,
        "review_samples": {
            "hard_gate_samples": hard_gate_samples,
            "false_positive_samples": false_positive_samples,
            "false_negative_samples": false_negative_samples,
            "review_sample_count": len(all_review_samples),
        },
        "selection_bias_warning": "历史扫描、淘汰对象和空集均保留；未提供人工复核标签的误报/漏报不被自动推断。",
        "rule_version": RULE_VERSION,
        "policy": {
            "historical_scans_immutable": True,
            "returns_do_not_rewrite_candidate_state": True,
            "false_positive_requires_later_review": True,
            "false_negative_requires_later_review": True,
            "empty_result_is_valid": True,
            "not_investment_conclusion": True,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _validate_scan(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise OpportunityQualityError("each scan must be an object")
    schema = str(value.get("schema_version") or "")
    if schema not in _SCAN_SCHEMAS:
        raise OpportunityQualityError("scan must be opportunity-scan.v1 or industry-discovery.v1")
    scan_id = str(value.get("scan_id") or value.get("discovery_id") or "").strip()
    as_of = str(value.get("as_of") or "").strip()
    if not scan_id or not as_of:
        raise OpportunityQualityError("each scan requires scan_id and as_of")
    _day(as_of, "scan.as_of")
    items = value.get("items")
    if items is None:
        items = value.get("opportunity_candidates")
    if not isinstance(items, list):
        raise OpportunityQualityError(f"scan {scan_id} has no candidate items")
    for item in items:
        if not isinstance(item, Mapping):
            raise OpportunityQualityError(f"scan {scan_id} has a non-object candidate")
        candidate_id = str(item.get("candidate_id") or "").strip()
        status = str(item.get("status") or item.get("candidate_state") or "").strip().upper()
        if not candidate_id:
            raise OpportunityQualityError(f"scan {scan_id} candidate_id is required")
        if status and status not in _STATES:
            raise OpportunityQualityError(f"unsupported candidate state: {status}")
    return {
        **dict(value),
        "scan_id": scan_id,
        "as_of": as_of,
        "items": [dict(item) for item in items],
    }


def _candidate_map(scan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for item in scan["items"]:
        candidate_id = str(item["candidate_id"])
        if candidate_id in result:
            raise OpportunityQualityError(f"duplicate candidate_id in scan {scan['scan_id']}: {candidate_id}")
        result[candidate_id] = item
    return result


def _state_counts(groups: Sequence[Mapping[str, Mapping[str, Any]]]) -> list[dict[str, int]]:
    result = []
    for group in groups:
        counts = {state: 0 for state in sorted(_STATES)}
        for item in group.values():
            status = str(item.get("status") or item.get("candidate_state") or "UNKNOWN").upper()
            counts[status] = counts.get(status, 0) + 1
        result.append(counts)
    return result


def _transitions_and_dwell(
    scans: Sequence[Mapping[str, Any]],
    groups: Sequence[Mapping[str, Mapping[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    observations: dict[str, list[tuple[date, str]]] = defaultdict(list)
    for scan, group in zip(scans, groups):
        day = _day(scan["as_of"], "scan.as_of")
        for candidate_id, item in group.items():
            status = str(item.get("status") or item.get("candidate_state") or "UNKNOWN").upper()
            observations[candidate_id].append((day, status))
    transitions = []
    dwell = []
    for candidate_id, rows in sorted(observations.items()):
        rows.sort()
        for previous, current in zip(rows, rows[1:]):
            if previous[1] != current[1]:
                transitions.append(
                    {
                        "candidate_id": candidate_id,
                        "from_state": previous[1],
                        "to_state": current[1],
                        "from_as_of": previous[0].isoformat(),
                        "to_as_of": current[0].isoformat(),
                        "dwell_days": (current[0] - previous[0]).days,
                    }
                )
        for index, (start, state) in enumerate(rows):
            end = rows[index + 1][0] if index + 1 < len(rows) else start
            dwell.append(
                {
                    "candidate_id": candidate_id,
                    "state": state,
                    "start_as_of": start.isoformat(),
                    "end_as_of": end.isoformat(),
                    "observed_dwell_days": max(0, (end - start).days),
                    "open_interval": index + 1 == len(rows),
                }
            )
    return transitions, dwell


def _average_dwell(rows: Sequence[Mapping[str, Any]]) -> dict[str, float | None]:
    values: dict[str, list[int]] = defaultdict(list)
    for item in rows:
        values[str(item["state"])].append(int(item["observed_dwell_days"]))
    return {
        state: (sum(days) / len(days) if days else None)
        for state, days in sorted(values.items())
    }


def _coverage(scans: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    industry_ids: set[str] = set()
    scope_items = []
    for scan in scans:
        scope = scan.get("scan_scope") or scan.get("resource_audit") or {}
        if isinstance(scope, Mapping):
            declared = scope.get("industry_count") or scope.get("industry_universe_count")
            if declared is not None:
                scope_items.append(float(declared))
            for item in scan["items"]:
                industry_id = str(item.get("industry_id") or "").strip()
                if industry_id:
                    industry_ids.add(industry_id)
    return {
        "observed_industry_count": len(industry_ids),
        "declared_industry_counts": scope_items,
        "declared_coverage_ratio": (
            len(industry_ids) / max(scope_items) if scope_items and max(scope_items) else None
        ),
        "coverage_basis": "declared scan_scope/resource_audit only; no full-market claim inferred",
    }


def _samples(value: Any, field: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise OpportunityQualityError(f"{field} must be a list")
    result = []
    for item in value:
        if not isinstance(item, Mapping):
            raise OpportunityQualityError(f"{field} items must be objects")
        if not str(item.get("candidate_id") or "").strip():
            raise OpportunityQualityError(f"{field} candidate_id is required")
        if not any(
            key in item for key in ("correct", "confirmed", "label")
        ):
            raise OpportunityQualityError(f"{field} requires correct or label")
        result.append(dict(item))
    return result


def _sample_rate(samples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {"status": "NOT_EVALUABLE", "sample_count": 0, "correct_count": 0, "rate": None}
    correct = sum(1 for item in samples if _is_correct(item))
    return {"status": "REVIEWED", "sample_count": len(samples), "correct_count": correct, "rate": correct / len(samples)}


def _sample_summary(samples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {"status": "NOT_EVALUABLE", "sample_count": 0, "confirmed_count": 0, "rate": None, "items": []}
    confirmed = sum(1 for item in samples if _is_confirmed(item))
    return {
        "status": "REVIEWED",
        "sample_count": len(samples),
        "confirmed_count": confirmed,
        "rate": confirmed / len(samples),
        "items": [dict(item) for item in samples],
    }


def _is_correct(item: Mapping[str, Any]) -> bool:
    return bool(item.get("correct") is True or str(item.get("label") or "").upper() in {"CORRECT", "TRUE", "CONFIRMED"})


def _is_confirmed(item: Mapping[str, Any]) -> bool:
    return bool(item.get("confirmed") is True or str(item.get("label") or "").upper() in {"CONFIRMED", "TRUE", "FP", "FN"})


def _all_items(scans: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [item for scan in scans for item in scan["items"]]


def _has_deep_research(item: Mapping[str, Any]) -> bool:
    deep = item.get("deep_research")
    return bool(
        isinstance(deep, Mapping)
        and (
            deep.get("complete") is True
            or deep.get("product_profit_source_review") is True
            or str(item.get("data_tier") or "").upper() in {"DEEP", "AI_DEEP"}
        )
    )


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "status": "REVIEWED" if denominator else "NOT_EVALUABLE",
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator if denominator else None,
    }


def _day(value: str, field: str) -> date:
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError as error:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError as nested:
            raise OpportunityQualityError(f"{field} must be an ISO date or datetime") from nested


def _hash_payload(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()
