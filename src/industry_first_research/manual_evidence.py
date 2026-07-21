"""Create explicit templates for manually verified company evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .application_mapping import DEFAULT_REQUIRED_FIELDS as APPLICATION_FIELDS
from .competitive_position import DEFAULT_REQUIRED_FIELDS as COMPETITIVE_FIELDS
from .cycle_reversal import DEFAULT_REQUIRED_FIELDS as CYCLE_FIELDS
from .demand_transmission import DEFAULT_REQUIRED_FIELDS as TRANSMISSION_FIELDS
from .industry_situation import DEFAULT_REQUIRED_FIELDS as INDUSTRY_FIELDS
from .product_profile import DEFAULT_REQUIRED_FIELDS as PRODUCT_FIELDS
from .survival_analysis import DEFAULT_REQUIRED_FIELDS as SURVIVAL_FIELDS
from .valuation_scenarios import DEFAULT_REQUIRED_FIELDS as VALUATION_FIELDS


class ManualEvidenceTemplateError(ValueError):
    """Raised when a manual evidence template cannot be generated."""


TEMPLATE_SCHEMA_VERSION = "company-manual-evidence-template.v1"
DEFAULT_FIELDS = ("listing_market",)
FIELD_PROFILES = {
    "listing-market": DEFAULT_FIELDS,
    "deep-company": tuple(
        dict.fromkeys(
            (
                "company_scope",
                "reporting_scope",
                "key_products",
                "key_risks",
                *PRODUCT_FIELDS,
                *APPLICATION_FIELDS,
                *TRANSMISSION_FIELDS,
                *INDUSTRY_FIELDS,
                *CYCLE_FIELDS,
                *COMPETITIVE_FIELDS,
                *SURVIVAL_FIELDS,
                *VALUATION_FIELDS,
                "counterevidence",
                "follow_up_checks",
                "next_check_at",
            )
        )
    ),
}


def build_manual_evidence_template(
    queue_report: Mapping[str, Any],
    *,
    fields: Sequence[str] | None = None,
    profile: str = "",
    company_ids: Sequence[str] | None = None,
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Build blank, auditable evidence records without asserting any facts."""

    if not isinstance(queue_report, Mapping):
        raise ManualEvidenceTemplateError("input queue must be a JSON object")
    if queue_report.get("schema_version") != "company-candidate-queue.v1":
        raise ManualEvidenceTemplateError(
            "input must be a company-candidate-queue.v1 report"
        )
    raw_items = queue_report.get("items")
    if not isinstance(raw_items, list):
        raise ManualEvidenceTemplateError("queue report has no items list")

    normalised_fields = _resolve_fields(fields, profile)
    requested_ids = _normalise_company_ids(company_ids)
    items = _normalise_items(raw_items, requested_ids)
    if not items:
        raise ManualEvidenceTemplateError("no matching queue items for template")

    input_queue_id = str(queue_report.get("queue_id") or "")
    template_id = snapshot_id or input_queue_id or "queue-input"
    records = [
        {
            "evidence_id": f"manual-{item['company_id']}-{field}",
            "company_id": item["company_id"],
            "field": field,
            "value": "",
            "source": "",
            "source_refs": [],
            "as_of": "",
            "evidence_tier": "",
            "verification_status": "UNVERIFIED",
            "note": (
                "待人工核验；禁止使用股票代码、市场常识或未经核验的网页 AI 回答填充。"
            ),
        }
        for item in items
        for field in normalised_fields
    ]
    return {
        "schema_version": TEMPLATE_SCHEMA_VERSION,
        "template_id": f"company-manual-evidence-template-{template_id}",
        "input_queue_id": input_queue_id,
        "input_snapshot_id": str(queue_report.get("input_snapshot_id") or ""),
        "as_of": str(queue_report.get("as_of") or ""),
        "source": str(queue_report.get("source") or ""),
        "field_profile": profile or "custom",
        "fields": list(normalised_fields),
        "company_ids": [item["company_id"] for item in items],
        "record_count": len(records),
        "records": records,
        "policy": {
            "blank_until_manually_verified": True,
            "stock_code_inference_forbidden": True,
            "web_ai_alone_is_insufficient": True,
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


def _resolve_fields(
    fields: Sequence[str] | None, profile: str
) -> tuple[str, ...]:
    profile_name = str(profile or "").strip()
    if profile_name and profile_name not in FIELD_PROFILES:
        raise ManualEvidenceTemplateError(
            "unsupported field profile: "
            + profile_name
            + "; supported profiles: "
            + ", ".join(sorted(FIELD_PROFILES))
        )
    base = FIELD_PROFILES[profile_name] if profile_name else DEFAULT_FIELDS
    if fields is None:
        return _normalise_fields(base)
    if isinstance(fields, (str, bytes, bytearray)):
        raise ManualEvidenceTemplateError("fields must be a string list")
    try:
        combined = (*base, *fields) if profile_name else tuple(fields)
    except TypeError as error:
        raise ManualEvidenceTemplateError("fields must be a string list") from error
    return _normalise_fields(combined)


def _normalise_fields(fields: Sequence[str]) -> tuple[str, ...]:
    if isinstance(fields, (str, bytes, bytearray)):
        raise ManualEvidenceTemplateError("fields must be a string list")
    try:
        normalised = tuple(dict.fromkeys(str(field).strip() for field in fields))
    except TypeError as error:
        raise ManualEvidenceTemplateError("fields must be a string list") from error
    if not normalised or any(not field for field in normalised):
        raise ManualEvidenceTemplateError("fields must contain non-empty names")
    return normalised


def _normalise_company_ids(company_ids: Sequence[str] | None) -> set[str] | None:
    if company_ids is None:
        return None
    if isinstance(company_ids, (str, bytes, bytearray)):
        raise ManualEvidenceTemplateError("company_ids must be a string list")
    try:
        normalised = {str(company_id).strip() for company_id in company_ids}
    except TypeError as error:
        raise ManualEvidenceTemplateError("company_ids must be a string list") from error
    if any(not company_id for company_id in normalised):
        raise ManualEvidenceTemplateError("company_ids must contain non-empty ids")
    return normalised


def _normalise_items(
    raw_items: list[Any], requested_ids: set[str] | None
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        if not isinstance(raw_item, Mapping):
            raise ManualEvidenceTemplateError("each queue item must be an object")
        company_id = str(raw_item.get("company_id") or "").strip()
        if not company_id:
            raise ManualEvidenceTemplateError("queue item company_id is required")
        if company_id in seen:
            raise ManualEvidenceTemplateError(f"duplicate queue company_id: {company_id}")
        seen.add(company_id)
        if requested_ids is not None and company_id not in requested_ids:
            continue
        items.append(
            {
                "company_id": company_id,
                "display_name": str(raw_item.get("display_name") or ""),
            }
        )
    if requested_ids is not None:
        unknown = requested_ids - seen
        if unknown:
            raise ManualEvidenceTemplateError(
                "company_ids are not in the input queue: " + ", ".join(sorted(unknown))
            )
    return items
