"""Manual evidence promotion gate for bounded data-source refreshes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import hashlib
import json
from typing import Any

from .data_refresh import (
    DATA_REFRESH_SCHEMA_VERSION,
    DataRefreshError,
    validate_data_source_refresh,
)
from .evidence import (
    EvidenceError,
    build_evidence,
    build_evidence_bundle,
    build_source_document,
)


REFRESH_EVIDENCE_INPUT_SCHEMA_VERSION = "data-source-refresh-evidence-input.v1"
REFRESH_EVIDENCE_SCHEMA_VERSION = "data-source-refresh-evidence-gate.v1"
REFRESH_EVIDENCE_RULE_VERSION = "data-source-refresh-evidence-rules.v1"
_ALLOWED_GATE_STATUSES = {"REVIEW_REQUIRED", "PROMOTED", "PARTIAL", "BLOCKED"}


class RefreshEvidenceError(ValueError):
    """Raised when a refresh-to-evidence promotion request is unsafe."""


def build_refresh_evidence_gate(
    refresh_report: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    *,
    refresh_uri: str = "",
    research_as_of: str = "",
    user_confirmed: bool = False,
    reviewer_id: str = "",
    reviewed_at: str = "",
    review_reason: str = "",
    bundle_id: str = "",
    gate_id: str = "",
) -> dict[str, Any]:
    """Validate field mappings and promote only after explicit human confirmation."""

    try:
        validated_refresh = validate_data_source_refresh(refresh_report)
    except DataRefreshError as error:
        raise RefreshEvidenceError(str(error)) from error
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)):
        raise RefreshEvidenceError("records must be a list")
    if not records:
        raise RefreshEvidenceError("records must not be empty")
    effective_as_of = _normalise_datetime(
        research_as_of or validated_refresh.get("as_of"),
        "research_as_of",
    )
    normalized_reviewer = str(reviewer_id or "").strip()
    normalized_reviewed_at = str(reviewed_at or "").strip()
    if user_confirmed:
        if not normalized_reviewer:
            raise RefreshEvidenceError("reviewer_id is required for user confirmation")
        _normalise_datetime(normalized_reviewed_at, "reviewed_at")
        if not str(review_reason or "").strip():
            raise RefreshEvidenceError("review_reason is required for user confirmation")

    rows = {
        str(row.get("query_id") or ""): row
        for row in validated_refresh.get("queries") or []
        if isinstance(row, Mapping)
    }
    if len(rows) != len(validated_refresh.get("queries") or []):
        raise RefreshEvidenceError("refresh queries contain duplicate or empty query_id")

    source_documents: list[dict[str, Any]] = []
    source_by_query: dict[str, dict[str, Any]] = {}
    evidence_inputs: list[dict[str, Any]] = []
    candidate_records: list[dict[str, Any]] = []
    for index, raw_record in enumerate(records):
        record = _normalise_record(raw_record, index)
        if user_confirmed and not record["manual_override_id"]:
            raise RefreshEvidenceError(
                f"records[{index}].manual_override_id is required for promotion"
            )
        row = rows.get(record["query_id"])
        if row is None:
            raise RefreshEvidenceError(
                f"records[{index}].query_id is not present in refresh report"
            )
        if row.get("status") not in {"SUCCESS", "PARTIAL"}:
            raise RefreshEvidenceError(
                f"records[{index}] cannot use failed refresh query {record['query_id']}"
            )
        source_document = source_by_query.get(record["query_id"])
        if source_document is None:
            source_document = _source_document_for_row(
                validated_refresh,
                row,
                record,
                refresh_uri=refresh_uri,
                research_as_of=effective_as_of,
            )
            source_by_query[record["query_id"]] = source_document
            source_documents.append(source_document)

        evidence_input = {
            **record,
            "subject_type": row["subject_type"],
            "subject_id": row["subject_id"],
            "source_document_id": source_document["document_id"],
            "source_name": source_document["source_name"],
            "source_type": source_document["source_type"],
            "source_url": source_document["source_url"],
            "source_version": source_document["source_version"],
            "content_hash": source_document["content_hash"],
            "research_as_of": effective_as_of,
        }
        candidate_records.append(
            {
                "query_id": record["query_id"],
                "metric": record["metric"],
                "subject_id": row["subject_id"],
                "source_document_id": source_document["document_id"],
                "value": record["value"],
                "evidence_tier": record["evidence_tier"],
                "evidence_status": record["evidence_status"],
                "verification_status": record["verification_status"],
                "manual_override_id": record["manual_override_id"],
            }
        )
        evidence_inputs.append(evidence_input)

    status = "REVIEW_REQUIRED"
    evidence_bundle: dict[str, Any] | None = None
    if user_confirmed:
        built_evidence: list[dict[str, Any]] = []
        try:
            for item in evidence_inputs:
                built_evidence.append(build_evidence(item))
            evidence_bundle = build_evidence_bundle(
                built_evidence,
                source_documents=source_documents,
                research_as_of=effective_as_of,
                subject_id=str(
                    validated_refresh.get("refresh_id") or "refresh-evidence"
                ),
                bundle_id=bundle_id,
            )
        except EvidenceError as error:
            raise RefreshEvidenceError(str(error)) from error
        status = "PROMOTED" if evidence_bundle["status"] == "READY" else "PARTIAL"

    report = {
        "schema_version": REFRESH_EVIDENCE_SCHEMA_VERSION,
        "gate_id": str(gate_id or "").strip(),
        "rule_version": REFRESH_EVIDENCE_RULE_VERSION,
        "refresh_id": str(validated_refresh["refresh_id"]),
        "refresh_content_hash": str(validated_refresh["content_hash"]),
        "research_as_of": effective_as_of,
        "candidate_records": candidate_records,
        "source_documents": source_documents,
        "evidence_bundle": evidence_bundle,
        "status": status,
        "review": {
            "user_confirmed": bool(user_confirmed),
            "reviewer_id": normalized_reviewer,
            "reviewed_at": normalized_reviewed_at,
            "review_reason": str(review_reason or ""),
        },
        "policy": {
            "manual_field_mapping_required": True,
            "fact_promotion": bool(user_confirmed),
            "automatic_fact_promotion": False,
            "refresh_report_unchanged": True,
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
    report["gate_id"] = report["gate_id"] or "refresh-evidence-" + _hash_payload(
        {
            "refresh_id": report["refresh_id"],
            "refresh_content_hash": report["refresh_content_hash"],
            "candidate_records": candidate_records,
            "review": report["review"],
        }
    )[:20]
    report["content_hash"] = _hash_payload(_hashable_report(report))
    return report


def validate_refresh_evidence_gate(
    report: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a promotion gate without re-promoting or fetching data."""

    if not isinstance(report, Mapping):
        raise RefreshEvidenceError("gate report must be an object")
    if report.get("schema_version") != REFRESH_EVIDENCE_SCHEMA_VERSION:
        raise RefreshEvidenceError(
            f"input must be {REFRESH_EVIDENCE_SCHEMA_VERSION}"
        )
    for field in ("gate_id", "refresh_id", "refresh_content_hash", "content_hash"):
        if not str(report.get(field) or "").strip():
            raise RefreshEvidenceError(f"{field} is required")
    if report.get("status") not in _ALLOWED_GATE_STATUSES:
        raise RefreshEvidenceError("unsupported gate status")
    if report.get("immutable") is not True:
        raise RefreshEvidenceError("gate report must be immutable")
    if report.get("read_only") is not True or report.get("execution_enabled") is not False:
        raise RefreshEvidenceError("gate report must remain read-only and execution-disabled")
    review = report.get("review")
    policy = report.get("policy")
    if not isinstance(review, Mapping) or not isinstance(policy, Mapping):
        raise RefreshEvidenceError("review and policy must be objects")
    if policy.get("automatic_fact_promotion") is not False:
        raise RefreshEvidenceError("automatic_fact_promotion must remain false")
    if report.get("status") == "PROMOTED":
        if review.get("user_confirmed") is not True or policy.get("fact_promotion") is not True:
            raise RefreshEvidenceError("PROMOTED gate requires explicit confirmation")
        if not isinstance(report.get("evidence_bundle"), Mapping):
            raise RefreshEvidenceError("PROMOTED gate must contain an evidence bundle")
    expected = _hash_payload(_hashable_report(report))
    if str(report["content_hash"]) != expected:
        raise RefreshEvidenceError("content_hash does not match gate report")
    return dict(report)


def _normalise_record(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RefreshEvidenceError(f"records[{index}] must be an object")
    query_id = str(value.get("query_id") or "").strip()
    metric = str(value.get("metric") or value.get("field") or "").strip()
    if not query_id or not metric:
        raise RefreshEvidenceError(
            f"records[{index}] requires query_id and metric"
        )
    for field in ("published_at", "captured_at", "period"):
        if not str(value.get(field) or "").strip():
            raise RefreshEvidenceError(f"records[{index}].{field} is required")
    evidence_tier = str(value.get("evidence_tier") or "").strip()
    evidence_status = str(value.get("evidence_status") or "").strip()
    verification_status = str(value.get("verification_status") or "").strip()
    if not evidence_tier or not evidence_status or not verification_status:
        raise RefreshEvidenceError(
            f"records[{index}] requires evidence_tier, evidence_status, and verification_status"
        )
    return {
        "query_id": query_id,
        "metric": metric,
        "value": value.get("value"),
        "unit": str(value.get("unit") or ""),
        "currency": str(value.get("currency") or ""),
        "period": str(value["period"]),
        "published_at": _normalise_datetime(value["published_at"], f"records[{index}].published_at"),
        "captured_at": _normalise_datetime(value["captured_at"], f"records[{index}].captured_at"),
        "evidence_tier": evidence_tier,
        "evidence_status": evidence_status,
        "verification_status": verification_status,
        "manual_override_id": str(value.get("manual_override_id") or ""),
        "source_url": str(value.get("source_url") or ""),
        "source_locator": str(value.get("source_locator") or value.get("field_path") or ""),
        "source_field": str(value.get("source_field") or metric),
        "metadata": dict(value.get("metadata") or {}),
    }


def _source_document_for_row(
    refresh: Mapping[str, Any],
    row: Mapping[str, Any],
    record: Mapping[str, Any],
    *,
    refresh_uri: str,
    research_as_of: str,
) -> dict[str, Any]:
    data = row.get("data") if isinstance(row.get("data"), Mapping) else {}
    source_url = str(record.get("source_url") or data.get("url") or "").strip()
    raw_uri = str(refresh_uri or "").strip() or (
        f"data/data_source_refreshes/{refresh['refresh_id']}.json"
    )
    try:
        return build_source_document(
            {
                "document_id": f"{refresh['refresh_id']}-{row['query_id']}",
                "source_name": str(row.get("source") or "unknown"),
                "source_type": str(data.get("source_type") or "refreshed_public_data"),
                "source_url": source_url,
                "raw_content_uri": raw_uri,
                "subject_type": str(row["subject_type"]),
                "subject_id": str(row["subject_id"]),
                "published_at": str(record["published_at"]),
                "captured_at": str(record["captured_at"]),
                "research_as_of": research_as_of,
                "source_version": str(
                    data.get("package_version")
                    or data.get("endpoint")
                    or row.get("source")
                    or "unknown"
                ),
                "parser_version": "data-source-refresh-rules.v1",
                "content_hash": str(row.get("data_hash") or ""),
                "metadata": {
                    "refresh_id": str(refresh["refresh_id"]),
                    "query_id": str(row["query_id"]),
                    "truncated": bool(row.get("truncated")),
                    "request": dict(row.get("request") or {}),
                },
            }
        )
    except EvidenceError as error:
        raise RefreshEvidenceError(str(error)) from error


def _normalise_datetime(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise RefreshEvidenceError(f"{field} is required")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError as error:
        raise RefreshEvidenceError(f"{field} must be an ISO datetime") from error


def _hashable_report(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in report.items()
        if key not in {"content_hash", "created_at"}
    }


def _hash_payload(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
