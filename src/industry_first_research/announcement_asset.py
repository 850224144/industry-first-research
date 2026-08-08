"""Store immutable original-announcement manifests and review impacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from hashlib import sha256
import json
from typing import Any


ANNOUNCEMENT_INPUT_SCHEMA_VERSION = "original-announcement-input.v1"
ANNOUNCEMENT_SCHEMA_VERSION = "original-announcement-asset.v1"
ANNOUNCEMENT_IMPACT_SCHEMA_VERSION = "announcement-impact.v1"
RULE_VERSION = "original-announcement-rules.v1"

_CORRECTION_STATUSES = {"ORIGINAL", "CORRECTED", "SUPPLEMENT", "WITHDRAWN"}
_SUBJECT_TYPES = {"listed_company", "industry", "futures_variety", "futures_contract"}
_DOCUMENT_TYPES = {
    "announcement",
    "annual_report",
    "quarterly_report",
    "audit_report",
    "earnings_preview",
    "major_contract",
    "customer_certification",
    "merger_acquisition",
    "buyback",
    "rights_issue_or_placement",
    "shutdown_or_bankruptcy",
    "policy_change",
    "industry_data_release",
    "futures_rule",
    "correction_notice",
    "withdrawal_notice",
}
_DOCUMENT_MODULES = {
    "annual_report": ("company_scope", "competitive_position", "survival_analysis", "valuation_scenarios"),
    "quarterly_report": ("survival_analysis", "valuation_scenarios", "research_report"),
    "audit_report": ("company_scope", "survival_analysis", "adversarial_review"),
    "earnings_preview": ("survival_analysis", "valuation_scenarios", "research_report"),
    "major_contract": ("application_mapping", "demand_transmission", "competitive_position"),
    "customer_certification": ("product_profile", "application_mapping", "demand_transmission"),
    "merger_acquisition": ("company_scope", "competitive_position", "valuation_scenarios"),
    "buyback": ("valuation_scenarios", "adversarial_review"),
    "rights_issue_or_placement": ("survival_analysis", "valuation_scenarios", "adversarial_review"),
    "shutdown_or_bankruptcy": ("industry_situation", "survival_analysis", "thesis_check"),
    "policy_change": ("industry_situation", "cycle_reversal", "adversarial_review"),
    "industry_data_release": ("industry_situation", "cycle_reversal"),
    "futures_rule": ("futures_contract", "market_structure", "attribution"),
}


class AnnouncementAssetError(ValueError):
    """Raised when an original announcement manifest is unsafe to store."""


def build_announcement_asset(
    payload: Mapping[str, Any],
    *,
    raw_content: bytes | str | None = None,
    raw_content_uri: str = "",
    asset_id: str = "",
) -> dict[str, Any]:
    """Create a content-addressed, immutable announcement manifest."""

    _validate_input(payload)
    document_id = str(payload.get("document_id") or asset_id).strip()
    if not document_id:
        raise AnnouncementAssetError("document_id is required")
    subject_id = str(payload.get("subject_id") or "").strip()
    if not subject_id:
        raise AnnouncementAssetError("subject_id is required")

    subject_type = str(payload.get("subject_type") or "").strip().lower()
    if subject_type not in _SUBJECT_TYPES:
        raise AnnouncementAssetError(
            "subject_type must be listed_company, industry, futures_variety, or futures_contract"
        )
    document_type = str(payload.get("document_type") or "announcement").strip().lower()
    if document_type not in _DOCUMENT_TYPES:
        raise AnnouncementAssetError(f"unsupported document_type: {document_type}")
    correction_status = str(payload.get("correction_status") or "ORIGINAL").strip().upper()
    if correction_status not in _CORRECTION_STATUSES:
        raise AnnouncementAssetError(f"unsupported correction_status: {correction_status}")

    published_at = _parse_datetime(payload.get("published_at"), "published_at")
    captured_at = _parse_datetime(payload.get("captured_at"), "captured_at")
    if published_at > captured_at:
        raise AnnouncementAssetError("published_at cannot be after captured_at")

    supersedes = str(payload.get("supersedes_document_id") or "").strip()
    if correction_status == "ORIGINAL" and supersedes:
        raise AnnouncementAssetError("ORIGINAL announcement cannot supersede another document")
    if correction_status != "ORIGINAL" and not supersedes:
        raise AnnouncementAssetError(
            "CORRECTED, SUPPLEMENT, and WITHDRAWN announcements require supersedes_document_id"
        )
    if supersedes == document_id:
        raise AnnouncementAssetError("an announcement cannot supersede itself")

    content_bytes = _content_bytes(raw_content, payload)
    content_hash = sha256(content_bytes).hexdigest() if content_bytes is not None else ""
    expected_hash = str(payload.get("content_hash") or "").strip().lower()
    if expected_hash and content_hash and expected_hash != content_hash:
        raise AnnouncementAssetError("content_hash does not match raw content")
    if not content_hash:
        content_hash = expected_hash
    if not content_hash:
        raise AnnouncementAssetError("raw content or content_hash is required")

    version = _positive_int(payload.get("version", 1), "version")
    if correction_status == "ORIGINAL" and version != 1:
        raise AnnouncementAssetError("ORIGINAL announcement must have version 1")
    if correction_status != "ORIGINAL" and version <= 1:
        raise AnnouncementAssetError("a corrected announcement must increment version")

    explicit_modules = _string_list(payload.get("affected_modules"))
    derived_modules = list(_DOCUMENT_MODULES.get(document_type, ()))
    if correction_status != "ORIGINAL":
        derived_modules.extend(("evidence_freshness", "research_version_comparison"))
    modules = list(dict.fromkeys([*explicit_modules, *derived_modules]))
    source = str(payload.get("source") or "").strip()
    source_url = str(payload.get("source_url") or "").strip()
    if not source:
        raise AnnouncementAssetError("source is required")
    if not source_url.startswith(("http://", "https://")):
        raise AnnouncementAssetError("source_url must be an http(s) URL")

    return {
        "schema_version": ANNOUNCEMENT_SCHEMA_VERSION,
        "document_id": document_id,
        "version": version,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "issuer": str(payload.get("issuer") or ""),
        "document_type": document_type,
        "title": str(payload.get("title") or ""),
        "source": source,
        "source_url": source_url,
        "published_at": payload["published_at"],
        "captured_at": payload["captured_at"],
        "as_of": str(payload.get("as_of") or payload["published_at"]),
        "source_version": str(payload.get("source_version") or "unknown"),
        "parser_version": str(payload.get("parser_version") or "manual-1"),
        "correction_status": correction_status,
        "supersedes_document_id": supersedes or None,
        "correction_reason": str(payload.get("correction_reason") or ""),
        "raw_content_uri": str(raw_content_uri or payload.get("raw_content_uri") or "").strip(),
        "content_hash": content_hash or expected_hash,
        "content_size_bytes": (
            len(content_bytes)
            if content_bytes is not None
            else payload.get("content_size_bytes")
        ),
        "content_encoding": str(payload.get("content_encoding") or "utf-8"),
        "affected_modules": modules,
        "evidence_type": "OBSERVED_FACT",
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "rule_version": RULE_VERSION,
        "policy": {
            "raw_content_immutable": True,
            "old_versions_preserved": True,
            "correction_creates_new_asset": True,
            "historical_research_not_overwritten": True,
            "affected_modules_require_review": True,
            "not_investment_conclusion": True,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
    }


def build_announcement_impact(
    asset: Mapping[str, Any],
    *,
    research_cutoff: str = "",
    impact_id: str = "",
) -> dict[str, Any]:
    """Turn an immutable announcement into a review-only impact record."""

    _validate_asset(asset)
    published = _parse_datetime(asset["published_at"], "published_at")
    cutoff = _parse_datetime(research_cutoff, "research_cutoff") if research_cutoff else None
    if cutoff is None:
        temporal_relation = "UNKNOWN"
    elif published <= cutoff:
        temporal_relation = "PRE_CUTOFF"
    else:
        temporal_relation = "POST_CUTOFF"
    status = str(asset["correction_status"]).upper()
    event_type = "announcement_correction" if status != "ORIGINAL" else str(asset["document_type"])
    identifier = impact_id.strip() or f"{asset['document_id']}-v{asset['version']}"
    return {
        "schema_version": ANNOUNCEMENT_IMPACT_SCHEMA_VERSION,
        "impact_id": f"announcement-impact-{identifier}",
        "document_id": asset["document_id"],
        "document_version": asset["version"],
        "subject_type": asset["subject_type"],
        "subject_id": asset["subject_id"],
        "event_type": event_type,
        "correction_status": status,
        "supersedes_document_id": asset.get("supersedes_document_id"),
        "published_at": asset["published_at"],
        "research_cutoff": research_cutoff,
        "temporal_relation": temporal_relation,
        "affected_modules": list(asset["affected_modules"]),
        "evidence_refs": [asset["document_id"]],
        "review_status": "REVIEW_REQUIRED" if asset["affected_modules"] else "NO_MODULE_MAPPED",
        "directional_conclusion": False,
        "decision_snapshot_changed": False,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "policy": {
            "asset_unchanged": True,
            "old_research_preserved": True,
            "future_information_not_backfilled": temporal_relation != "PRE_CUTOFF",
            "not_investment_conclusion": True,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
    }


def _validate_input(value: Any) -> None:
    if not isinstance(value, Mapping) or value.get("schema_version") != ANNOUNCEMENT_INPUT_SCHEMA_VERSION:
        raise AnnouncementAssetError(f"input must be {ANNOUNCEMENT_INPUT_SCHEMA_VERSION}")


def _validate_asset(value: Any) -> None:
    if not isinstance(value, Mapping) or value.get("schema_version") != ANNOUNCEMENT_SCHEMA_VERSION:
        raise AnnouncementAssetError(f"input must be {ANNOUNCEMENT_SCHEMA_VERSION}")
    if value.get("immutable") is not True or not str(value.get("content_hash") or "").strip():
        raise AnnouncementAssetError("announcement asset must be immutable and hashed")


def _content_bytes(raw_content: bytes | str | None, payload: Mapping[str, Any]) -> bytes | None:
    if raw_content is not None:
        if isinstance(raw_content, bytes):
            return raw_content
        if isinstance(raw_content, str):
            return raw_content.encode(str(payload.get("content_encoding") or "utf-8"))
        raise AnnouncementAssetError("raw_content must be bytes or string")
    inline = payload.get("raw_content")
    if inline is None:
        return None
    if not isinstance(inline, str):
        raise AnnouncementAssetError("raw_content in input must be a string")
    return inline.encode(str(payload.get("content_encoding") or "utf-8"))


def _parse_datetime(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise AnnouncementAssetError(f"{field} is required")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise AnnouncementAssetError(f"{field} must be ISO datetime") from error


def _positive_int(value: Any, field: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise AnnouncementAssetError(f"{field} must be a positive integer") from error
    if number < 1:
        raise AnnouncementAssetError(f"{field} must be a positive integer")
    return number


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        raise AnnouncementAssetError("expected a string list")
    return [str(item) for item in value if str(item).strip()]
