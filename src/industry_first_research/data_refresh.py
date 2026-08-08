"""Bounded, source-routed data refreshes for explicit research subjects."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import hashlib
import json
from typing import Any

from .data_sources import DataSourceExhaustedError, DataSourceRouter


DATA_REFRESH_INPUT_SCHEMA_VERSION = "data-source-refresh-input.v1"
DATA_REFRESH_SCHEMA_VERSION = "data-source-refresh.v1"
DATA_REFRESH_RULE_VERSION = "data-source-refresh-rules.v1"
_MAX_QUERIES = 20
_MAX_ROWS_PER_QUERY = 5000
_SUBJECT_TYPES = {
    "listed_company",
    "company",
    "industry",
    "industry_radar",
    "futures_variety",
    "futures_contract",
    "continuous_series",
    "announcement",
    "financial_statement",
}
_SECRET_PARTS = {
    "authorization",
    "api_key",
    "apikey",
    "cookie",
    "password",
    "secret",
    "token",
}


class DataRefreshError(ValueError):
    """Raised when an explicit refresh manifest is unsafe or invalid."""


def build_data_source_refresh(
    payload: Mapping[str, Any],
    router: DataSourceRouter,
    *,
    as_of: str = "",
    refresh_id: str = "",
    max_queries: int = _MAX_QUERIES,
    max_rows_per_query: int = 500,
    source_health_snapshot_id: str = "",
) -> dict[str, Any]:
    """Fetch a bounded explicit manifest through the configured primary/fallback route."""

    if not isinstance(payload, Mapping):
        raise DataRefreshError("refresh input must be an object")
    if not isinstance(router, DataSourceRouter):
        raise DataRefreshError("router must be a DataSourceRouter")
    schema = str(payload.get("schema_version") or "")
    if schema != DATA_REFRESH_INPUT_SCHEMA_VERSION:
        raise DataRefreshError(f"input must be {DATA_REFRESH_INPUT_SCHEMA_VERSION}")
    effective_as_of = _normalise_as_of(as_of or payload.get("as_of"))
    query_limit = _positive_limit(max_queries, _MAX_QUERIES, "max_queries")
    row_limit = _positive_limit(
        max_rows_per_query, _MAX_ROWS_PER_QUERY, "max_rows_per_query"
    )
    raw_queries = payload.get("queries")
    if not isinstance(raw_queries, list) or not raw_queries:
        raise DataRefreshError("queries must be a non-empty list")
    if len(raw_queries) > query_limit:
        raise DataRefreshError(
            f"queries exceed bounded max_queries={query_limit}"
        )

    normalised_queries = [
        _normalise_query(item, index) for index, item in enumerate(raw_queries)
    ]
    rows: list[dict[str, Any]] = []
    for query in normalised_queries:
        rows.append(
            _fetch_one(
                query,
                router,
                effective_as_of,
                row_limit,
            )
        )

    successful = sum(
        row["status"] in {"SUCCESS", "PARTIAL"} for row in rows
    )
    truncated = sum(bool(row.get("truncated")) for row in rows)
    if successful == 0:
        status = "INSUFFICIENT"
    elif successful < len(rows) or truncated:
        status = "PARTIAL"
    else:
        status = "SUCCESS"
    effective_id = str(refresh_id or payload.get("refresh_id") or "").strip()
    if not effective_id:
        effective_id = "source-refresh-" + _hash_payload(
            {
                "as_of": effective_as_of,
                "queries": normalised_queries,
            }
        )[:20]
    report = {
        "schema_version": DATA_REFRESH_SCHEMA_VERSION,
        "refresh_id": effective_id,
        "rule_version": DATA_REFRESH_RULE_VERSION,
        "as_of": effective_as_of,
        "source_health_snapshot_id": str(source_health_snapshot_id or ""),
        "queries": rows,
        "query_count": len(rows),
        "successful_query_count": successful,
        "truncated_query_count": truncated,
        "status": status,
        "review_required": True,
        "resource_audit": {
            "max_queries": query_limit,
            "max_rows_per_query": row_limit,
            "explicit_query_manifest": True,
            "full_market_deep_data": False,
            "full_market_query": False,
        },
        "policy": {
            "primary_fallback_route_used": True,
            "attempts_preserved": True,
            "raw_response_preserved_with_row_bound": True,
            "fact_promotion": False,
            "investment_conclusion": False,
            "decision_snapshot_created": False,
            "read_only": True,
            "execution_enabled": False,
        },
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }
    report["content_hash"] = _hash_payload(_hashable_report(report))
    return report


def validate_data_source_refresh(report: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a saved refresh without making another network request."""

    if not isinstance(report, Mapping):
        raise DataRefreshError("refresh report must be an object")
    if report.get("schema_version") != DATA_REFRESH_SCHEMA_VERSION:
        raise DataRefreshError(f"input must be {DATA_REFRESH_SCHEMA_VERSION}")
    for field in ("refresh_id", "as_of", "content_hash", "rule_version"):
        if not str(report.get(field) or "").strip():
            raise DataRefreshError(f"{field} is required")
    _normalise_as_of(report["as_of"])
    if report.get("immutable") is not True:
        raise DataRefreshError("refresh report must be immutable")
    if report.get("read_only") is not True or report.get("execution_enabled") is not False:
        raise DataRefreshError("refresh report must remain read-only and execution-disabled")
    policy = report.get("policy")
    if not isinstance(policy, Mapping) or policy.get("fact_promotion") is not False:
        raise DataRefreshError("fact_promotion must remain false")
    if not isinstance(report.get("queries"), list):
        raise DataRefreshError("queries must be a list")
    expected = _hash_payload(_hashable_report(report))
    if str(report.get("content_hash")) != expected:
        raise DataRefreshError("content_hash does not match refresh report")
    return dict(report)


def _fetch_one(
    query: Mapping[str, Any],
    router: DataSourceRouter,
    as_of: str,
    row_limit: int,
) -> dict[str, Any]:
    query_id = str(query["query_id"])
    try:
        result = router.fetch(
            query["request"],
            as_of,
            subject_type=str(query["subject_type"]),
            source_names=query.get("source_names") or None,
        )
        bounded_data, was_truncated = _bound_value(result.data, row_limit)
        status = "PARTIAL" if was_truncated else "SUCCESS"
        return {
            "query_id": query_id,
            "subject_type": query["subject_type"],
            "subject_id": query["subject_id"],
            "status": status,
            "source": result.source,
            "requested_sources": list(result.requested_sources),
            "request": dict(query["request"]),
            "data": bounded_data,
            "data_hash": _hash_payload(_stable_data_for_hash(bounded_data)),
            "truncated": was_truncated,
            "attempts": [attempt.to_dict() for attempt in result.attempts],
            "reason": "row limit applied" if was_truncated else "",
        }
    except DataSourceExhaustedError as error:
        return {
            "query_id": query_id,
            "subject_type": query["subject_type"],
            "subject_id": query["subject_id"],
            "status": "FAILED",
            "source": "",
            "requested_sources": list(error.requested_sources),
            "request": dict(query["request"]),
            "data": None,
            "data_hash": "",
            "truncated": False,
            "attempts": [attempt.to_dict() for attempt in error.attempts],
            "reason": str(error),
        }
    except Exception as error:
        return {
            "query_id": query_id,
            "subject_type": query["subject_type"],
            "subject_id": query["subject_id"],
            "status": "FAILED",
            "source": "",
            "requested_sources": list(query.get("source_names") or []),
            "request": dict(query["request"]),
            "data": None,
            "data_hash": "",
            "truncated": False,
            "attempts": [],
            "reason": f"{type(error).__name__}: {error}",
        }


def _normalise_query(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DataRefreshError(f"queries[{index}] must be an object")
    query_id = str(value.get("query_id") or "").strip()
    subject_type = str(value.get("subject_type") or "").strip().lower()
    subject_id = str(value.get("subject_id") or "").strip()
    request = value.get("request")
    if not query_id:
        raise DataRefreshError(f"queries[{index}].query_id is required")
    if subject_type not in _SUBJECT_TYPES:
        raise DataRefreshError(
            f"queries[{index}].subject_type is unsupported: {subject_type or '<empty>'}"
        )
    if not subject_id:
        raise DataRefreshError(f"queries[{index}].subject_id is required")
    if not isinstance(request, Mapping) or not request:
        raise DataRefreshError(f"queries[{index}].request must be a non-empty object")
    _reject_secrets(request, f"queries[{index}].request")
    source_names = _string_list(value.get("source_names"), f"queries[{index}].source_names")
    if any(name.lower() == "qmt" for name in source_names):
        raise DataRefreshError("QMT is not an allowed refresh source")
    return {
        "query_id": query_id,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "source_names": source_names,
        "request": dict(request),
    }


def _bound_value(value: Any, row_limit: int) -> tuple[Any, bool]:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        truncated = False
        for key, item in value.items():
            result[str(key)], item_truncated = _bound_value(item, row_limit)
            truncated = truncated or item_truncated
        return result, truncated
    if isinstance(value, list):
        truncated = len(value) > row_limit
        values = value[:row_limit]
        bounded: list[Any] = []
        nested_truncated = False
        for item in values:
            bounded_item, item_truncated = _bound_value(item, row_limit)
            bounded.append(bounded_item)
            nested_truncated = nested_truncated or item_truncated
        return bounded, truncated or nested_truncated
    if isinstance(value, tuple):
        bounded, truncated = _bound_value(list(value), row_limit)
        return bounded, truncated
    return value, False


def _reject_secrets(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if any(part in normalized for part in _SECRET_PARTS):
                raise DataRefreshError(f"{path}.{key} cannot contain credentials")
            _reject_secrets(item, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _reject_secrets(item, f"{path}[{index}]")


def _string_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise DataRefreshError(f"{field} must be a string list")
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _positive_limit(value: int, maximum: int, field: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise DataRefreshError(f"{field} must be an integer") from error
    if result <= 0 or result > maximum:
        raise DataRefreshError(f"{field} must be between 1 and {maximum}")
    return result


def _normalise_as_of(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise DataRefreshError("as_of is required")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError as error:
        raise DataRefreshError("as_of must be an ISO date or datetime") from error


def _hashable_report(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in report.items()
        if key not in {"content_hash", "research_version_id", "trigger_task_id"}
    }


def _stable_data_for_hash(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _stable_data_for_hash(item)
            for key, item in value.items()
            if str(key).casefold() not in {"retrieved_at", "captured_at", "as_of"}
        }
    if isinstance(value, list):
        return [_stable_data_for_hash(item) for item in value]
    return value


def _hash_payload(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
