"""Immutable, source-aware market-data snapshots used by research modules."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from hashlib import sha256
import json
from typing import Any

from .market_registry import (
    MARKET_REFERENCE_SCHEMA_VERSION,
    MarketRegistry,
    MarketRegistryError,
    validate_market_reference,
)


class MarketDataError(ValueError):
    """Raised when a market-data snapshot is incomplete or temporally unsafe."""


MARKET_DATA_SCHEMA_VERSION = "market-data-snapshot.v1"
INPUT_SCHEMA_VERSION = "market-data-input.v1"
RULE_VERSION = "market-data-snapshot-rules.v1"
SUBJECT_TYPES = {"listed_company", "futures_contract", "continuous_series", "index", "benchmark"}
MISSING_STATES = {"COMPLETE", "PARTIAL", "UNKNOWN"}
CORPORATE_ACTION_STATES = {"NONE", "APPLIED", "PENDING", "UNKNOWN", "NOT_APPLICABLE"}


def build_market_data_snapshot(
    payload: Mapping[str, Any],
    *,
    rule_version: str = RULE_VERSION,
    snapshot_id: str = "",
    market_registry: MarketRegistry | None = None,
) -> dict[str, Any]:
    """Normalize OHLCV series and lock every market-data interpretation."""

    if not isinstance(payload, Mapping):
        raise MarketDataError("market data input must be an object")
    if payload.get("schema_version") not in {INPUT_SCHEMA_VERSION, MARKET_DATA_SCHEMA_VERSION}:
        raise MarketDataError("input must be market-data-input.v1 or market-data-snapshot.v1")
    subject = payload.get("subject") if isinstance(payload.get("subject"), Mapping) else {}
    subject_type = str(payload.get("subject_type") or subject.get("subject_type") or "").strip().lower()
    subject_id = str(payload.get("subject_id") or payload.get("ticker") or subject.get("subject_id") or "").strip()
    if subject_type not in SUBJECT_TYPES:
        raise MarketDataError(f"unsupported subject_type: {subject_type}")
    if not subject_id:
        raise MarketDataError("subject_id is required")
    research_as_of = _parse_datetime(payload.get("research_as_of") or payload.get("as_of"), "research_as_of")
    last_market_at = _parse_datetime(payload.get("last_market_at") or payload.get("as_of"), "last_market_at")
    if last_market_at > research_as_of:
        raise MarketDataError("last_market_at cannot be after research_as_of")
    source = str(payload.get("source") or "").strip()
    source_version = str(payload.get("source_version") or payload.get("provider_version") or "").strip()
    market = str(payload.get("market") or payload.get("exchange") or "").strip()
    timeframe = str(payload.get("timeframe") or "daily").strip()
    raw_uri = str(payload.get("raw_file_uri") or payload.get("source_uri") or "").strip()
    content_hash = str(payload.get("content_hash") or "").strip()
    if not source or not source_version or not market or not raw_uri or not content_hash:
        raise MarketDataError("source, source_version, market, raw_file_uri, and content_hash are required")
    missing = str(payload.get("missing_data_status") or "UNKNOWN").upper()
    if missing not in MISSING_STATES:
        raise MarketDataError(f"unsupported missing_data_status: {missing}")
    actions = str(payload.get("corporate_action_status") or "NOT_APPLICABLE").upper()
    if actions not in CORPORATE_ACTION_STATES:
        raise MarketDataError(f"unsupported corporate_action_status: {actions}")
    adjustment = str(payload.get("adjustment") or payload.get("adjustment_type") or "NONE").upper()
    calendar_version = str(payload.get("trading_calendar_version") or payload.get("calendar_version") or "").strip()
    if not calendar_version:
        raise MarketDataError("trading_calendar_version is required")

    market_reference = payload.get("market_reference")
    if market_registry is not None:
        try:
            expected_reference = market_registry.reference(market)
        except MarketRegistryError as error:
            raise MarketDataError(str(error)) from error
        if market_reference is not None and market_reference != expected_reference:
            raise MarketDataError("market_reference does not match the supplied market registry")
        market_reference = expected_reference
    elif market_reference is not None:
        if not isinstance(market_reference, Mapping):
            raise MarketDataError("market_reference must be an object")
        if market_reference.get("schema_version") != MARKET_REFERENCE_SCHEMA_VERSION:
            raise MarketDataError("market_reference must be market-reference.v1")
        reference_market = market_reference.get("market")
        if not isinstance(reference_market, Mapping):
            raise MarketDataError("market_reference has no market definition")
        if str(reference_market.get("market_id") or "").upper() != market.upper():
            raise MarketDataError("market_reference market_id does not match market")
        if str(reference_market.get("currency") or "").upper() != str(payload.get("currency") or "CNY").upper():
            raise MarketDataError("market_reference currency does not match market data")
        if str(reference_market.get("calendar_version") or "") != calendar_version:
            raise MarketDataError("market_reference calendar_version does not match market data")

    continuous_rule = payload.get("continuous_series_rule")
    segments = payload.get("segments") or []
    if subject_type == "continuous_series":
        if not isinstance(continuous_rule, Mapping):
            raise MarketDataError("continuous_series_rule is required for continuous_series")
        for field in ("rule_version", "selection_rule", "roll_rule", "adjustment_rule"):
            if not str(continuous_rule.get(field) or "").strip():
                raise MarketDataError(f"continuous_series_rule.{field} is required")
        segments = _normalise_segments(segments, research_as_of)
    elif segments:
        segments = _normalise_segments(segments, research_as_of)
    series = _normalise_series(payload.get("series") or payload.get("timeframes") or {timeframe: payload.get("bars") or payload.get("rows") or []}, research_as_of)
    effective_id = snapshot_id.strip() or str(payload.get("snapshot_id") or "").strip() or f"{subject_id}-{_compact(research_as_of)}"
    effective_id = effective_id.removeprefix("market-data-")
    return {
        "schema_version": MARKET_DATA_SCHEMA_VERSION,
        "snapshot_id": f"market-data-{effective_id}",
        "subject": {
            "subject_type": subject_type,
            "subject_id": subject_id,
            "display_name": str(payload.get("display_name") or subject.get("display_name") or ""),
        },
        "market": market,
        "currency": str(payload.get("currency") or "CNY"),
        "source": source,
        "source_version": source_version,
        "timeframe": timeframe,
        "adjustment": adjustment,
        "sequence_rule": payload.get("sequence_rule"),
        "trading_calendar_version": calendar_version,
        "market_reference": dict(market_reference) if isinstance(market_reference, Mapping) else None,
        "market_registry_id": str((market_reference or {}).get("registry_id") or "") if isinstance(market_reference, Mapping) else "",
        "market_registry_version": str((market_reference or {}).get("registry_version") or "") if isinstance(market_reference, Mapping) else "",
        "market_registry_hash": str((market_reference or {}).get("registry_hash") or "") if isinstance(market_reference, Mapping) else "",
        "research_as_of": research_as_of.isoformat(),
        "last_market_at": last_market_at.isoformat(),
        "raw_file_uri": raw_uri,
        "content_hash": content_hash,
        "missing_data_status": missing,
        "corporate_action_status": actions,
        "continuous_series_rule": dict(continuous_rule) if isinstance(continuous_rule, Mapping) else None,
        "segments": segments,
        "series": series,
        "row_count": sum(len(rows) for rows in series.values()),
        "rule_version": rule_version,
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "policy": {
            "source_and_version_locked": True,
            "as_of_locked": True,
            "future_rows_rejected": True,
            "continuous_series_not_tradeable": subject_type == "continuous_series",
            "specific_contract_required_for_simulation": subject_type == "continuous_series",
            "read_only": True,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
            "market_registry_locked": isinstance(market_reference, Mapping),
        },
        "snapshot_content_hash": _hash_payload({
            "subject": {"subject_type": subject_type, "subject_id": subject_id},
            "research_as_of": research_as_of.isoformat(),
            "series": series,
            "segments": segments,
        }),
    }


def validate_market_data_snapshot(
    snapshot: Mapping[str, Any],
    *,
    market_registry: MarketRegistry | None = None,
) -> dict[str, Any]:
    if not isinstance(snapshot, Mapping) or snapshot.get("schema_version") != MARKET_DATA_SCHEMA_VERSION:
        raise MarketDataError("input must be market-data-snapshot.v1")
    errors: list[str] = []
    for field in ("snapshot_id", "source", "source_version", "market", "raw_file_uri", "content_hash", "research_as_of", "last_market_at"):
        if not str(snapshot.get(field) or "").strip():
            errors.append(f"missing {field}")
    subject = snapshot.get("subject")
    if not isinstance(subject, Mapping) or str(subject.get("subject_id") or "").strip() == "":
        errors.append("subject is missing subject_id")
    if snapshot.get("immutable") is not True:
        errors.append("snapshot must be immutable")
    reference = snapshot.get("market_reference")
    if reference is not None:
        if not isinstance(reference, Mapping) or reference.get("schema_version") != MARKET_REFERENCE_SCHEMA_VERSION:
            errors.append("market_reference must be market-reference.v1")
        else:
            reference_market = reference.get("market")
            if not isinstance(reference_market, Mapping):
                errors.append("market_reference has no market definition")
            else:
                if str(reference_market.get("market_id") or "").upper() != str(snapshot.get("market") or "").upper():
                    errors.append("market_reference market_id does not match snapshot market")
                if str(reference_market.get("currency") or "").upper() != str(snapshot.get("currency") or "").upper():
                    errors.append("market_reference currency does not match snapshot currency")
            if market_registry is not None:
                try:
                    reference_validation = validate_market_reference(reference, market_registry)
                    errors.extend(
                        f"market_reference: {item}"
                        for item in reference_validation["errors"]
                    )
                except MarketRegistryError as error:
                    errors.append(f"market_reference: {error}")
    try:
        rebuilt = build_market_data_snapshot(
            {**snapshot, "schema_version": MARKET_DATA_SCHEMA_VERSION},
            market_registry=market_registry,
        )
        if snapshot.get("snapshot_content_hash") != rebuilt.get("snapshot_content_hash"):
            errors.append("snapshot_content_hash does not match normalized series")
    except MarketDataError as error:
        errors.append(str(error))
    return {
        "schema_version": "market-data-validation.v1",
        "snapshot_id": str(snapshot.get("snapshot_id") or ""),
        "status": "VALID" if not errors else "INVALID",
        "error_count": len(errors),
        "errors": errors,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def extract_market_data_series(
    snapshot: Mapping[str, Any],
    *,
    timeframe: str = "",
    market_registry: MarketRegistry | None = None,
) -> list[dict[str, Any]]:
    """Return one normalized series from a validated market-data snapshot."""

    validate_market_data_snapshot(snapshot, market_registry=market_registry)
    series = snapshot.get("series")
    if not isinstance(series, Mapping) or not series:
        raise MarketDataError("snapshot has no series")
    key = timeframe.strip() or str(snapshot.get("timeframe") or "")
    if key and isinstance(series.get(key), list):
        return [dict(item) for item in series[key]]
    first = next(iter(series.values()))
    if not isinstance(first, list):
        raise MarketDataError("snapshot series is not a list")
    return [dict(item) for item in first]


def _normalise_series(raw: Any, as_of: datetime) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(raw, Mapping) or not raw:
        raise MarketDataError("series must be a non-empty object")
    result: dict[str, list[dict[str, Any]]] = {}
    for key, rows in raw.items():
        name = str(key).strip()
        if not name:
            raise MarketDataError("series timeframe must not be empty")
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
            raise MarketDataError(f"series[{name}] must be a list")
        normalized: list[dict[str, Any]] = []
        previous: datetime | None = None
        seen: set[datetime] = set()
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                raise MarketDataError(f"series[{name}][{index}] must be an object")
            timestamp = _parse_datetime(row.get("timestamp") or row.get("date"), f"series[{name}][{index}].timestamp")
            if timestamp > as_of:
                raise MarketDataError(f"future row exceeds research_as_of: {name}[{index}]")
            if timestamp in seen:
                raise MarketDataError(f"duplicate timestamp in series: {name}")
            if previous is not None and timestamp <= previous:
                raise MarketDataError(f"series must be strictly ascending: {name}")
            seen.add(timestamp)
            previous = timestamp
            item = {"timestamp": timestamp.isoformat()}
            for field in ("open", "high", "low", "close", "volume", "value", "settlement", "open_interest"):
                if row.get(field) is not None:
                    try:
                        item[field] = float(row[field])
                    except (TypeError, ValueError) as error:
                        raise MarketDataError(f"non-numeric {field}: {name}[{index}]") from error
            if not any(field in item for field in ("close", "value", "settlement")):
                raise MarketDataError(f"series row requires close, value, or settlement: {name}[{index}]")
            normalized.append(item)
        result[name] = normalized
    return result


def _normalise_segments(raw: Any, as_of: datetime) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise MarketDataError("continuous-series segments must be a non-empty list")
    result: list[dict[str, Any]] = []
    previous_end: datetime | None = None
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise MarketDataError("each continuous-series segment must be an object")
        contract_id = str(item.get("contract_id") or item.get("real_contract") or "").strip()
        start = _parse_datetime(item.get("start") or item.get("from"), f"segments[{index}].start")
        end = _parse_datetime(item.get("end") or item.get("to") or as_of.isoformat(), f"segments[{index}].end")
        if not contract_id or start >= end or end > as_of:
            raise MarketDataError(f"invalid continuous-series segment: {index}")
        if not _string_list(item.get("selection_evidence_ids")):
            raise MarketDataError(
                f"continuous-series segment requires selection_evidence_ids: {index}"
            )
        if previous_end is not None and start < previous_end:
            raise MarketDataError("continuous-series segments overlap")
        previous_end = end
        result.append({
            "contract_id": contract_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "selection_evidence_ids": _string_list(item.get("selection_evidence_ids")),
        })
    return result


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise MarketDataError("value must be a string list")
    return [str(item).strip() for item in value if str(item).strip()]


def _parse_datetime(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise MarketDataError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        try:
            parsed = datetime.combine(date.fromisoformat(text[:10]), datetime.min.time())
        except ValueError:
            raise MarketDataError(f"{field} must be an ISO datetime or date") from error
    if parsed.tzinfo is None:
        from datetime import timezone
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _compact(value: datetime) -> str:
    return value.isoformat().replace("-", "").replace(":", "").replace("+", "plus")


def _hash_payload(payload: Mapping[str, Any]) -> str:
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
