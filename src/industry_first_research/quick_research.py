"""Create a bounded, evidence-only quick company research snapshot."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class QuickResearchError(ValueError):
    """Raised when readiness and supplemental inputs cannot be combined safely."""


QUICK_RESEARCH_SCHEMA_VERSION = "company-quick-research.v1"
RULE_VERSION = "company-quick-research-rules.v1"
_READINESS_SCHEMA_VERSION = "company-researchability.v1"
_SUPPLEMENTAL_SCHEMA_VERSION = "company-supplemental-evidence.v1"


def build_quick_research_report(
    readiness_report: Mapping[str, Any],
    supplemental_report: Mapping[str, Any],
    *,
    rule_version: str = RULE_VERSION,
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Organise only source-bound facts; do not infer company quality or value."""

    _validate_report(readiness_report, _READINESS_SCHEMA_VERSION, "readiness")
    _validate_report(supplemental_report, _SUPPLEMENTAL_SCHEMA_VERSION, "supplemental")
    if not rule_version.strip():
        raise QuickResearchError("rule_version must not be empty")

    readiness_items = _index_items(readiness_report, "readiness")
    supplemental_items = _index_items(supplemental_report, "supplemental")
    if set(readiness_items) != set(supplemental_items):
        raise QuickResearchError("readiness and supplemental company sets do not match")
    if readiness_report.get("input_report_id") != supplemental_report.get("report_id"):
        raise QuickResearchError(
            "readiness input_report_id does not match supplemental report_id"
        )

    items = [
        _build_item(
            readiness_items[company_id],
            supplemental_items[company_id],
            supplemental_report,
            rule_version=rule_version,
        )
        for company_id in readiness_items
    ]
    report_id = snapshot_id or str(readiness_report.get("report_id") or "quick-input")
    return {
        "schema_version": QUICK_RESEARCH_SCHEMA_VERSION,
        "report_id": f"company-quick-research-{report_id}",
        "input_readiness_id": str(readiness_report.get("report_id") or ""),
        "input_supplemental_id": str(supplemental_report.get("report_id") or ""),
        "input_queue_id": str(readiness_report.get("input_queue_id") or ""),
        "input_snapshot_id": str(readiness_report.get("input_snapshot_id") or ""),
        "rule_version": rule_version,
        "research_mode": "LOCAL_ONLY",
        "research_depth": "QUICK",
        "as_of": str(readiness_report.get("as_of") or ""),
        "source": str(readiness_report.get("source") or ""),
        "source_metadata": readiness_report.get("source_metadata") or {},
        "candidate_count": len(items),
        "items": items,
        "policy": {
            "evidence_only": True,
            "local_only": True,
            "financial_analysis_included": False,
            "valuation_included": False,
            "investment_conclusion": False,
            "candidate_state_preserved": True,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _validate_report(report: Any, schema_version: str, label: str) -> None:
    if not isinstance(report, Mapping):
        raise QuickResearchError(f"{label} report must be a JSON object")
    if report.get("schema_version") != schema_version:
        raise QuickResearchError(f"input {label} report has wrong schema_version")
    if not isinstance(report.get("items"), list):
        raise QuickResearchError(f"{label} report has no items list")


def _index_items(report: Mapping[str, Any], label: str) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for item in report["items"]:
        if not isinstance(item, Mapping):
            raise QuickResearchError(f"each {label} item must be an object")
        company_id = str(item.get("company_id") or "").strip()
        if not company_id:
            raise QuickResearchError(f"{label} item company_id is required")
        if company_id in indexed:
            raise QuickResearchError(f"duplicate {label} company_id: {company_id}")
        indexed[company_id] = item
    return indexed


def _build_item(
    readiness_item: Mapping[str, Any],
    supplemental_item: Mapping[str, Any],
    supplemental_report: Mapping[str, Any],
    *,
    rule_version: str,
) -> dict[str, Any]:
    company_id = str(readiness_item["company_id"])
    if str(supplemental_item.get("candidate_state") or "") != str(
        readiness_item.get("candidate_state") or ""
    ):
        raise QuickResearchError(
            f"candidate state changed between reports for company {company_id}"
        )
    records = _records_for_company(supplemental_report, company_id)
    required_fields = _string_list(supplemental_item.get("required_fields"))
    fields = {
        field: _field_summary(field, records)
        for field in _unique(
            [*required_fields, *(str(record["field"]) for record in records)]
        )
    }
    known_facts = {
        field: summary
        for field, summary in fields.items()
        if summary["status"] == "VERIFIED"
    }
    unverified_claims = {
        field: summary
        for field, summary in fields.items()
        if summary["status"] in {"UNVERIFIED", "CONFLICTING"}
    }
    missing_fields = [
        field for field in required_fields if fields[field]["status"] == "MISSING"
    ]
    evidence_gaps = _unique(
        [
            *_string_list(readiness_item.get("evidence_gaps")),
            *_string_list(supplemental_item.get("evidence_gaps")),
            *missing_fields,
        ]
    )

    return {
        "company_id": company_id,
        "display_name": str(readiness_item.get("display_name") or ""),
        "industry_id": str(readiness_item.get("industry_id") or ""),
        "candidate_state": str(readiness_item.get("candidate_state") or ""),
        "candidate_state_changed": False,
        "research_readiness": str(readiness_item.get("research_readiness") or ""),
        "research_depth": "QUICK",
        "rule_version": rule_version,
        "candidate_rule_version": str(
            readiness_item.get("candidate_rule_version") or ""
        ),
        "candidate_field_sources": dict(
            readiness_item.get("candidate_field_sources") or {}
        ),
        "candidate_additional_sources": _string_list(
            readiness_item.get("candidate_additional_sources")
        ),
        "known_facts": known_facts,
        "unverified_claims": unverified_claims,
        "unknowns": missing_fields,
        "evidence_gaps": evidence_gaps,
        "evidence_ids": [str(record["evidence_id"]) for record in records],
        "limitations": [
            "FINANCIAL_DATA_NOT_INCLUDED",
            "VALUATION_NOT_INCLUDED",
            "INVESTMENT_CONCLUSION_NOT_INCLUDED",
        ],
        "allowed_actions": ["gap_review", "evidence_refresh"],
        "prohibited_actions": [
            "complete_valuation",
            "investment_conclusion",
            "automatic_candidate_promotion",
            "execution",
        ],
        "review_only": True,
        "investment_conclusion": False,
    }


def _records_for_company(
    supplemental_report: Mapping[str, Any], company_id: str
) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    for record in supplemental_report.get("records") or []:
        if not isinstance(record, Mapping):
            raise QuickResearchError("supplemental records must be objects")
        if str(record.get("company_id") or "") == company_id:
            records.append(record)
    return records


def _field_summary(field: str, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    field_records = [
        record for record in records if str(record.get("field") or "") == field
    ]
    if not field_records:
        return {
            "status": "MISSING",
            "values": [],
            "evidence_ids": [],
            "sources": [],
            "as_of": [],
        }
    if any(record.get("verification_status") == "CONFLICTING" for record in field_records):
        status = "CONFLICTING"
    elif any(
        record.get("verification_status") == "VERIFIED"
        and record.get("evidence_tier") in {"A", "B"}
        for record in field_records
    ):
        status = "VERIFIED"
    else:
        status = "UNVERIFIED"
    return {
        "status": status,
        "values": [record.get("value") for record in field_records],
        "evidence_ids": [str(record.get("evidence_id") or "") for record in field_records],
        "sources": [str(record.get("source") or "") for record in field_records],
        "as_of": [str(record.get("as_of") or "") for record in field_records],
        "evidence_tiers": [str(record.get("evidence_tier") or "") for record in field_records],
    }


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise QuickResearchError("quick research fields must be string lists")
    return [str(item) for item in value if str(item)]


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
