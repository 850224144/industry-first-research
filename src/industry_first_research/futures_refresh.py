"""Map bounded source refreshes into explicit futures fundamentals inputs.

The mapping is deliberately explicit and review-first.  A refresh contains
raw responses from the primary/fallback data route; this module only selects
declared paths and carries their lineage forward.  It never promotes a raw
value to a verified fact, fills missing fields, or makes a directional
conclusion.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
import hashlib
import json
from typing import Any

from .data_refresh import DataRefreshError, validate_data_source_refresh
from .futures_fundamentals import (
    FUNDAMENTAL_FIELDS,
    FUTURES_FUNDAMENTALS_INPUT_SCHEMA_VERSION,
)


FUTURES_REFRESH_MAPPING_SCHEMA_VERSION = "futures-fundamentals-refresh-mapping.v1"
FUTURES_REFRESH_MAPPING_RULE_VERSION = "futures-fundamentals-refresh-mapping-rules.v1"
_VALID_QUERY_STATUSES = {"SUCCESS", "PARTIAL"}
_MAX_FIELD_MAPPINGS = 50
_MAX_OBSERVATION_MAPPINGS = 30


class FuturesRefreshMappingError(ValueError):
    """Raised when a refresh mapping cannot be applied safely."""


def build_futures_fundamentals_input_from_refresh(
    refresh_report: Mapping[str, Any],
    mapping: Mapping[str, Any],
    *,
    input_id: str = "",
) -> dict[str, Any]:
    """Build a review-only fundamentals input from an immutable refresh.

    Every mapped field is marked ``UNVERIFIED`` even when the source returned
    successfully.  Human confirmation belongs to the existing evidence gate;
    this function is a lineage-preserving projection, not a fact-promotion
    shortcut.
    """

    try:
        refresh = validate_data_source_refresh(refresh_report)
    except DataRefreshError as error:
        raise FuturesRefreshMappingError(str(error)) from error
    _validate_mapping(mapping)

    refresh_as_of = _as_of(refresh["as_of"], "refresh.as_of")
    mapping_as_of = _as_of(mapping.get("as_of") or refresh["as_of"], "mapping.as_of")
    if mapping_as_of > refresh_as_of:
        raise FuturesRefreshMappingError(
            "mapping.as_of cannot exceed refresh.as_of"
        )

    mapping_id = str(mapping.get("mapping_id") or "").strip()
    if not mapping_id:
        mapping_id = "futures-refresh-mapping-" + _hash_payload(
            {
                "refresh_id": refresh["refresh_id"],
                "refresh_content_hash": refresh["content_hash"],
                "mapping": mapping,
            }
        )[:20]

    rows = {
        str(row["query_id"]): row
        for row in refresh.get("queries", [])
        if isinstance(row, Mapping)
    }
    fields: dict[str, dict[str, Any]] = {}
    mapped_queries: set[str] = set()
    for index, raw_mapping in enumerate(mapping.get("field_mappings", [])):
        item = _normalise_field_mapping(raw_mapping, index)
        if item["target"] in fields:
            raise FuturesRefreshMappingError(
                f"duplicate field mapping: {item['target']}"
            )
        row = _successful_row(
            rows,
            item["query_id"],
            index,
            expected_subject_id=str(mapping["variety_id"]),
        )
        mapped_queries.add(item["query_id"])
        value = _path_value(row.get("data"), item["value_path"])
        note = (
            "mapped from bounded refresh; awaiting manual evidence confirmation"
            if value is not None
            else "declared path did not produce a value; no inference performed"
        )
        fields[item["target"]] = {
            "status": "UNVERIFIED" if value is not None else "MISSING",
            "value": value,
            "unit": item["unit"] or _infer_unit(row.get("data")),
            "evidence_ids": [],
            "sources": [str(row.get("source") or "")],
            "as_of": [str(item["observed_at"] or mapping.get("as_of") or refresh["as_of"])],
            "evidence_tiers": [],
            "notes": [note],
            "metadata": _lineage(refresh, row, item, mapping_id),
        }

    observations: dict[str, list[dict[str, Any]]] = {}
    for index, raw_mapping in enumerate(mapping.get("observation_mappings", [])):
        item = _normalise_observation_mapping(raw_mapping, index)
        row = _successful_row(
            rows,
            item["query_id"],
            index,
            expected_subject_id=str(mapping["variety_id"]),
        )
        mapped_queries.add(item["query_id"])
        raw_rows = _path_value(row.get("data"), item["rows_path"])
        if not isinstance(raw_rows, Sequence) or isinstance(
            raw_rows, (str, bytes, bytearray)
        ):
            raise FuturesRefreshMappingError(
                f"observation mapping {item['target']} rows_path must resolve to a list"
            )
        output_rows: list[dict[str, Any]] = []
        for row_index, raw_observation in enumerate(raw_rows):
            if not isinstance(raw_observation, Mapping):
                raise FuturesRefreshMappingError(
                    f"observation mapping {item['target']} row {row_index} must be an object"
                )
            observed_at = _path_value(raw_observation, item["date_path"])
            value = _path_value(raw_observation, item["value_path"])
            if observed_at in (None, "") or value in (None, ""):
                continue
            parsed_observed_at = _as_of(
                observed_at,
                f"observation_mappings[{index}].date_path",
            )
            if parsed_observed_at > mapping_as_of:
                raise FuturesRefreshMappingError(
                    f"future observation exceeds mapping.as_of: {item['target']}"
                )
            output_rows.append(
                {
                    "date": str(observed_at),
                    "value": value,
                    "unit": item["unit"] or _infer_unit(raw_observation),
                    "source": str(row.get("source") or ""),
                    "query_id": item["query_id"],
                    "metadata": _lineage(refresh, row, item, mapping_id),
                }
            )
        observations[item["target"]] = output_rows

    effective_input_id = str(input_id or mapping.get("input_id") or "").strip()
    if not effective_input_id:
        effective_input_id = f"{mapping_id}-{mapping.get('variety_id')}"

    result = {
        "schema_version": FUTURES_FUNDAMENTALS_INPUT_SCHEMA_VERSION,
        "report_id": effective_input_id,
        "variety_id": str(mapping["variety_id"]).upper(),
        "as_of": str(mapping.get("as_of") or refresh["as_of"]),
        "source": "data-source-refresh",
        "source_metadata": {
            "refresh_id": str(refresh["refresh_id"]),
            "refresh_content_hash": str(refresh["content_hash"]),
            "mapping_id": mapping_id,
            "mapping_schema_version": FUTURES_REFRESH_MAPPING_SCHEMA_VERSION,
            "mapped_query_ids": sorted(mapped_queries),
            "refresh_status": str(refresh.get("status") or ""),
        },
        "fields": fields,
        "observations": observations,
        "price_scenarios": {},
        "assessments": {},
        "policy": {
            "source_refresh_only": True,
            "manual_evidence_confirmation_required": True,
            "automatic_fact_promotion": False,
            "directional_conclusion": False,
            "decision_snapshot_created": False,
            "execution_enabled": False,
        },
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "rule_version": FUTURES_REFRESH_MAPPING_RULE_VERSION,
    }
    result["content_hash"] = _hash_payload(result)
    return result


def validate_futures_refresh_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a mapping manifest without reading or fetching any data."""

    _validate_mapping(mapping)
    return dict(mapping)


def _validate_mapping(mapping: Mapping[str, Any]) -> None:
    if not isinstance(mapping, Mapping):
        raise FuturesRefreshMappingError("mapping must be an object")
    if mapping.get("schema_version") != FUTURES_REFRESH_MAPPING_SCHEMA_VERSION:
        raise FuturesRefreshMappingError(
            f"mapping must be {FUTURES_REFRESH_MAPPING_SCHEMA_VERSION}"
        )
    if not str(mapping.get("variety_id") or "").strip():
        raise FuturesRefreshMappingError("mapping.variety_id is required")
    for key, limit in (
        ("field_mappings", _MAX_FIELD_MAPPINGS),
        ("observation_mappings", _MAX_OBSERVATION_MAPPINGS),
    ):
        value = mapping.get(key, [])
        if not isinstance(value, list):
            raise FuturesRefreshMappingError(f"mapping.{key} must be a list")
        if len(value) > limit:
            raise FuturesRefreshMappingError(f"mapping.{key} exceeds limit {limit}")


def _normalise_field_mapping(value: Any, index: int) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise FuturesRefreshMappingError(f"field_mappings[{index}] must be an object")
    target = str(value.get("target") or value.get("field") or "").strip()
    query_id = str(value.get("query_id") or "").strip()
    path = str(value.get("value_path") or "").strip()
    if target not in FUNDAMENTAL_FIELDS:
        raise FuturesRefreshMappingError(
            f"field_mappings[{index}].target is not a required fundamentals field"
        )
    if not query_id or not path:
        raise FuturesRefreshMappingError(
            f"field_mappings[{index}] requires query_id and value_path"
        )
    requested_status = str(value.get("status") or "UNVERIFIED").upper()
    if requested_status not in {"UNVERIFIED", "MISSING"}:
        raise FuturesRefreshMappingError(
            "refresh mapping cannot mark a field VERIFIED or CONFLICTING"
        )
    return {
        "target": target,
        "query_id": query_id,
        "value_path": path,
        "unit": str(value.get("unit") or ""),
        "observed_at": str(value.get("observed_at") or ""),
    }


def _normalise_observation_mapping(value: Any, index: int) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise FuturesRefreshMappingError(
            f"observation_mappings[{index}] must be an object"
        )
    target = str(value.get("target") or "").strip()
    query_id = str(value.get("query_id") or "").strip()
    rows_path = str(value.get("rows_path") or "").strip()
    date_path = str(value.get("date_path") or "").strip()
    value_path = str(value.get("value_path") or "").strip()
    if not target or not query_id or not rows_path or not date_path or not value_path:
        raise FuturesRefreshMappingError(
            f"observation_mappings[{index}] requires target, query_id, rows_path, date_path, and value_path"
        )
    return {
        "target": target,
        "query_id": query_id,
        "rows_path": rows_path,
        "date_path": date_path,
        "value_path": value_path,
        "unit": str(value.get("unit") or ""),
    }


def _successful_row(
    rows: Mapping[str, Mapping[str, Any]],
    query_id: str,
    index: int,
    *,
    expected_subject_id: str,
) -> Mapping[str, Any]:
    row = rows.get(query_id)
    if row is None:
        raise FuturesRefreshMappingError(
            f"mapping[{index}] query_id is not present in refresh: {query_id}"
        )
    if str(row.get("status") or "") not in _VALID_QUERY_STATUSES:
        raise FuturesRefreshMappingError(
            f"mapping[{index}] cannot use refresh query {query_id} with status {row.get('status')}"
        )
    actual_subject_id = str(row.get("subject_id") or "").strip().upper()
    if actual_subject_id != expected_subject_id.strip().upper():
        raise FuturesRefreshMappingError(
            f"mapping[{index}] query {query_id} subject_id {actual_subject_id} "
            f"does not match variety_id {expected_subject_id}"
        )
    return row


def _lineage(
    refresh: Mapping[str, Any],
    row: Mapping[str, Any],
    mapping: Mapping[str, str],
    mapping_id: str,
) -> dict[str, Any]:
    return {
        "refresh_id": str(refresh["refresh_id"]),
        "refresh_content_hash": str(refresh["content_hash"]),
        "query_id": str(row["query_id"]),
        "source": str(row.get("source") or ""),
        "source_data_hash": str(row.get("data_hash") or ""),
        "path": mapping.get("value_path") or mapping.get("rows_path") or "",
        "mapping_id": mapping_id,
        "review_status": "REVIEW_REQUIRED",
    }


def _path_value(value: Any, path: str) -> Any:
    current = value
    normalised = str(path or "").strip()
    if normalised.startswith("$."):
        normalised = normalised[2:]
    elif normalised.startswith("$"):
        normalised = normalised[1:]
    normalised = normalised.replace("[", ".").replace("]", "")
    for part in (item for item in normalised.split(".") if item):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        elif isinstance(current, Sequence) and not isinstance(
            current, (str, bytes, bytearray)
        ) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def _infer_unit(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("unit", "quote_unit", "price_unit"):
            if str(value.get(key) or "").strip():
                return str(value[key])
    return ""


def _as_of(value: Any, field: str) -> date:
    text = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise FuturesRefreshMappingError(f"{field} must be an ISO date") from error


def _hash_payload(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
