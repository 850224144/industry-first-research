"""Validate and assemble traceable company supplemental evidence."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


class SupplementalEvidenceError(ValueError):
    """Raised when a supplemental evidence package is invalid."""


EVIDENCE_SCHEMA_VERSION = "company-supplemental-evidence.v1"
RULE_VERSION = "company-supplemental-evidence-rules.v1"
DEFAULT_REQUIRED_FIELDS = (
    "company_scope",
    "reporting_scope",
    "key_products",
    "key_risks",
)
_EVIDENCE_TIERS = {"A", "B", "C", "D"}
_VERIFICATION_STATUSES = {"VERIFIED", "UNVERIFIED", "CONFLICTING"}


def build_supplemental_evidence_report(
    queue_report: Mapping[str, Any],
    evidence_records: Sequence[Mapping[str, Any]],
    *,
    required_fields: Sequence[str] = DEFAULT_REQUIRED_FIELDS,
    rule_version: str = RULE_VERSION,
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Build a bounded evidence package without promoting a queue item."""

    if not isinstance(queue_report, Mapping):
        raise SupplementalEvidenceError("input queue must be a JSON object")
    if queue_report.get("schema_version") != "company-candidate-queue.v1":
        raise SupplementalEvidenceError(
            "input must be a company-candidate-queue.v1 report"
        )
    raw_items = queue_report.get("items")
    if not isinstance(raw_items, list):
        raise SupplementalEvidenceError("queue report has no items list")
    fields = _normalise_required_fields(required_fields)
    if not rule_version.strip():
        raise SupplementalEvidenceError("rule_version must not be empty")

    queue_items = _normalise_queue_items(raw_items)
    company_ids = {item["company_id"] for item in queue_items}
    records = _normalise_records(evidence_records, company_ids)
    grouped: dict[str, list[dict[str, Any]]] = {
        company_id: [] for company_id in company_ids
    }
    for record in records:
        grouped[record["company_id"]].append(record)

    items = [
        _build_item(
            item,
            grouped[item["company_id"]],
            required_fields=fields,
            rule_version=rule_version,
        )
        for item in queue_items
    ]
    counts = Counter(item["supplemental_state"] for item in items)
    input_queue_id = str(queue_report.get("queue_id") or "")
    report_id = snapshot_id or input_queue_id or "queue-input"

    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "report_id": f"company-supplemental-evidence-{report_id}",
        "input_queue_id": input_queue_id,
        "input_snapshot_id": str(queue_report.get("input_snapshot_id") or ""),
        "rule_version": rule_version,
        "as_of": str(queue_report.get("as_of") or ""),
        "source": str(queue_report.get("source") or ""),
        "source_metadata": queue_report.get("source_metadata") or {},
        "required_fields": list(fields),
        "record_count": len(records),
        "status_counts": dict(counts),
        "records": records,
        "items": items,
        "policy": {
            "evidence_only": True,
            "candidate_state_preserved": True,
            "supplemental_evidence_can_promote": False,
            "read_only": True,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _normalise_required_fields(fields: Sequence[str]) -> tuple[str, ...]:
    if isinstance(fields, (str, bytes, bytearray)):
        raise SupplementalEvidenceError("required_fields must be a string list")
    try:
        normalised = tuple(dict.fromkeys(str(field).strip() for field in fields))
    except TypeError as error:
        raise SupplementalEvidenceError("required_fields must be a string list") from error
    if not normalised or any(not field for field in normalised):
        raise SupplementalEvidenceError("required_fields must contain non-empty names")
    return normalised


def _normalise_queue_items(raw_items: list[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        if not isinstance(raw_item, Mapping):
            raise SupplementalEvidenceError("each queue item must be an object")
        company_id = str(raw_item.get("company_id") or "").strip()
        if not company_id:
            raise SupplementalEvidenceError("queue item company_id is required")
        if company_id in seen:
            raise SupplementalEvidenceError(f"duplicate queue company_id: {company_id}")
        seen.add(company_id)
        items.append(
            {
                "company_id": company_id,
                "display_name": str(raw_item.get("display_name") or ""),
                "industry_id": str(raw_item.get("industry_id") or ""),
                "candidate_state": str(raw_item.get("candidate_state") or ""),
                "candidate_rule_version": str(raw_item.get("rule_version") or ""),
                "candidate_reasons": _string_list(raw_item.get("reasons")),
                "candidate_blockers": _string_list(raw_item.get("blockers")),
                "candidate_evidence_gaps": _string_list(
                    raw_item.get("evidence_gaps")
                ),
            }
        )
    return items


def _normalise_records(
    raw_records: Sequence[Mapping[str, Any]], company_ids: set[str]
) -> list[dict[str, Any]]:
    if not isinstance(raw_records, Sequence) or isinstance(
        raw_records, (str, bytes, bytearray)
    ):
        raise SupplementalEvidenceError("evidence_records must be a list")
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_record in raw_records:
        if not isinstance(raw_record, Mapping):
            raise SupplementalEvidenceError("each evidence record must be an object")
        record = _normalise_record(raw_record)
        if record["evidence_id"] in seen_ids:
            raise SupplementalEvidenceError(
                f"duplicate evidence_id: {record['evidence_id']}"
            )
        if record["company_id"] not in company_ids:
            raise SupplementalEvidenceError(
                f"evidence company_id is not in the input queue: {record['company_id']}"
            )
        seen_ids.add(record["evidence_id"])
        records.append(record)
    return records


def _normalise_record(raw_record: Mapping[str, Any]) -> dict[str, Any]:
    required = ("evidence_id", "company_id", "field", "value", "source", "as_of")
    missing = [name for name in required if name not in raw_record]
    if missing:
        raise SupplementalEvidenceError(
            f"evidence record missing required fields: {', '.join(missing)}"
        )
    evidence_id = str(raw_record.get("evidence_id") or "").strip()
    company_id = str(raw_record.get("company_id") or "").strip()
    field = str(raw_record.get("field") or "").strip()
    source = str(raw_record.get("source") or "").strip()
    as_of = str(raw_record.get("as_of") or "").strip()
    tier = str(raw_record.get("evidence_tier") or "").strip().upper()
    status = str(raw_record.get("verification_status") or "").strip().upper()
    if not all((evidence_id, company_id, field, source, as_of)):
        raise SupplementalEvidenceError(
            "evidence_id, company_id, field, source, and as_of must be non-empty"
        )
    if _is_empty_value(raw_record["value"]):
        raise SupplementalEvidenceError("evidence value must be non-empty")
    if field == "listing_market" and not isinstance(raw_record["value"], str):
        raise SupplementalEvidenceError("listing_market evidence value must be a string")
    if tier not in _EVIDENCE_TIERS:
        raise SupplementalEvidenceError(f"unsupported evidence_tier: {tier or '<empty>'}")
    if status not in _VERIFICATION_STATUSES:
        raise SupplementalEvidenceError(
            f"unsupported verification_status: {status or '<empty>'}"
        )
    source_refs = raw_record.get("source_refs") or []
    if not isinstance(source_refs, list) or any(
        not str(value).strip() for value in source_refs
    ):
        raise SupplementalEvidenceError("source_refs must be a string list")
    source_refs = [str(value).strip() for value in source_refs]
    if tier == "B" and len(source_refs) < 2:
        raise SupplementalEvidenceError(
            "evidence tier B requires at least two source_refs"
        )
    return {
        "evidence_id": evidence_id,
        "company_id": company_id,
        "field": field,
        "value": raw_record["value"],
        "source": source,
        "source_refs": source_refs,
        "as_of": as_of,
        "evidence_tier": tier,
        "verification_status": status,
        "note": str(raw_record.get("note") or ""),
    }


def _build_item(
    queue_item: Mapping[str, str],
    records: Sequence[Mapping[str, Any]],
    *,
    required_fields: Sequence[str],
    rule_version: str,
) -> dict[str, Any]:
    available_fields = sorted({str(record["field"]) for record in records})
    verified_fields = sorted(
        {
            str(record["field"])
            for record in records
            if record["verification_status"] == "VERIFIED"
            and record["evidence_tier"] in {"A", "B"}
        }
    )
    conflicting_fields = sorted(
        {
            str(record["field"])
            for record in records
            if record["verification_status"] == "CONFLICTING"
        }
    )
    unverified_fields = sorted(
        {
            str(record["field"])
            for record in records
            if record["verification_status"] == "UNVERIFIED"
            or record["evidence_tier"] in {"C", "D"}
        }
    )
    evidence_gaps = sorted(set(required_fields) - set(verified_fields))
    queue_state = queue_item["candidate_state"]
    if queue_state == "REJECTED":
        supplemental_state = "BLOCKED"
        blockers = ["QUEUE_ITEM_REJECTED"]
    elif queue_state == "INSUFFICIENT":
        supplemental_state = "INSUFFICIENT"
        blockers = ["QUEUE_ITEM_INSUFFICIENT"]
    elif conflicting_fields:
        supplemental_state = "BLOCKED"
        blockers = ["EVIDENCE_CONFLICT"]
    elif not records:
        supplemental_state = "INSUFFICIENT"
        blockers = ["SUPPLEMENTAL_EVIDENCE_MISSING"]
    elif not evidence_gaps:
        supplemental_state = "READY"
        blockers = []
    else:
        supplemental_state = "PARTIAL"
        blockers = []

    return {
        "company_id": queue_item["company_id"],
        "display_name": queue_item["display_name"],
        "industry_id": queue_item["industry_id"],
        "candidate_state": queue_state,
        "candidate_rule_version": queue_item["candidate_rule_version"],
        "candidate_reasons": queue_item["candidate_reasons"],
        "candidate_blockers": queue_item["candidate_blockers"],
        "candidate_evidence_gaps": queue_item["candidate_evidence_gaps"],
        "supplemental_state": supplemental_state,
        "rule_version": rule_version,
        "required_fields": list(required_fields),
        "available_fields": available_fields,
        "verified_fields": verified_fields,
        "unverified_fields": unverified_fields,
        "conflicting_fields": conflicting_fields,
        "evidence_gaps": evidence_gaps,
        "blockers": blockers,
        "evidence_ids": [str(record["evidence_id"]) for record in records],
        "review_only": True,
        "investment_conclusion": False,
        "candidate_state_changed": False,
    }


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise SupplementalEvidenceError("queue reason fields must be string lists")
    return [str(item) for item in value if str(item)]


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return not value
    return False
