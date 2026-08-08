"""Map immutable events to immutable research versions and review actions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
import hashlib
import json
from typing import Any

from .research_version import ResearchVersionError, validate_research_version


RESEARCH_IMPACT_QUEUE_SCHEMA_VERSION = "research-impact-queue.v1"
RESEARCH_IMPACT_RULE_VERSION = "research-impact-queue-rules.v1"

_EVENT_MODULES = {
    "announcement_correction": ("evidence_freshness", "research_version_comparison"),
    "annual_report": ("company_scope", "survival_analysis", "valuation_scenarios"),
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
    "price_shock": ("market_structure", "valuation_scenarios", "thesis_check"),
}


class ResearchImpactError(ValueError):
    """Raised when an event cannot be mapped without weakening time safety."""


def build_research_impact_queue(
    event: Mapping[str, Any],
    research_versions: Sequence[Mapping[str, Any]],
    *,
    queue_id: str = "",
) -> dict[str, Any]:
    """Create a review queue from one event and saved version manifests."""

    normalized_event = _normalize_event(event)
    if isinstance(research_versions, (str, bytes, bytearray)) or not isinstance(
        research_versions, Sequence
    ):
        raise ResearchImpactError("research_versions must be a list")
    versions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for version in research_versions:
        try:
            validated = validate_research_version(version)
        except ResearchVersionError as error:
            raise ResearchImpactError(str(error)) from error
        version_id = str(validated["version_id"])
        if version_id in seen:
            raise ResearchImpactError(f"duplicate research version: {version_id}")
        seen.add(version_id)
        versions.append(validated)

    impacted: list[dict[str, Any]] = []
    for version in versions:
        if not _subject_matches(normalized_event, version):
            continue
        relation = _temporal_relation(
            normalized_event.get("event_at"), str(version.get("research_as_of") or "")
        )
        action = {
            "PRE_CUTOFF": "CREATE_REVISED_VERSION",
            "POST_CUTOFF": "CREATE_NEXT_VERSION_DO_NOT_BACKFILL",
            "UNKNOWN": "REVIEW_TEMPORAL_SCOPE",
        }[relation]
        impacted.append(
            {
                "version_id": str(version["version_id"]),
                "subject_type": str(version["subject_type"]),
                "subject_ids": list(version.get("subject_ids") or []),
                "research_as_of": str(version["research_as_of"]),
                "temporal_relation": relation,
                "action": action,
                "affected_modules": list(normalized_event["affected_modules"]),
                "previous_version_id": str(version.get("previous_version_id") or ""),
                "review_status": "REVIEW_REQUIRED",
            }
        )

    normalized_id = str(
        queue_id or normalized_event["event_id"] or "research-impact"
    ).strip()
    if not normalized_id:
        raise ResearchImpactError("queue_id cannot be empty")
    return {
        "schema_version": RESEARCH_IMPACT_QUEUE_SCHEMA_VERSION,
        "queue_id": f"research-impact-{normalized_id}",
        "event_id": normalized_event["event_id"],
        "event_type": normalized_event["event_type"],
        "event_subject_type": normalized_event["subject_type"],
        "event_subject_id": normalized_event["subject_id"],
        "event_at": normalized_event["event_at"],
        "event_source": normalized_event["source"],
        "event_asset_id": normalized_event["asset_id"],
        "evidence_ids": normalized_event["evidence_ids"],
        "affected_modules": normalized_event["affected_modules"],
        "candidate_version_count": len(versions),
        "impacted_version_count": len(impacted),
        "review_status": "REVIEW_REQUIRED" if impacted else "NO_MATCHING_VERSION",
        "impacted_versions": impacted,
        "unmatched_reason": "" if impacted else "NO_SUBJECT_MATCHING_RESEARCH_VERSION",
        "content_hash": _hash_payload(
            {
                "event": normalized_event,
                "impacted_versions": impacted,
                "candidate_version_count": len(versions),
            }
        ),
        "rule_version": RESEARCH_IMPACT_RULE_VERSION,
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "policy": {
            "old_versions_preserved": True,
            "future_evidence_not_backfilled": True,
            "event_only_creates_review": True,
            "automatic_directional_conclusion": False,
            "automatic_decision_snapshot": False,
            "read_only": True,
            "review_only": True,
        },
    }


def validate_research_impact_queue(queue: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a saved queue without resolving or changing its versions."""

    if not isinstance(queue, Mapping):
        raise ResearchImpactError("impact queue must be a JSON object")
    if queue.get("schema_version") != RESEARCH_IMPACT_QUEUE_SCHEMA_VERSION:
        raise ResearchImpactError(
            f"input must be {RESEARCH_IMPACT_QUEUE_SCHEMA_VERSION}"
        )
    if queue.get("immutable") is not True:
        raise ResearchImpactError("impact queue must be immutable")
    for field in ("queue_id", "event_id", "event_type", "review_status", "content_hash"):
        if not str(queue.get(field) or "").strip():
            raise ResearchImpactError(f"impact queue {field} is required")
    expected = _hash_payload(
        {
            "event": {
                "event_id": queue["event_id"],
                "event_type": queue["event_type"],
                "subject_type": queue.get("event_subject_type") or "",
                "subject_id": queue.get("event_subject_id") or "",
                "event_at": queue.get("event_at") or "",
                "source": queue.get("event_source") or "",
                "asset_id": queue.get("event_asset_id") or "",
                "evidence_ids": queue.get("evidence_ids") or [],
                "affected_modules": queue.get("affected_modules") or [],
            },
            "impacted_versions": queue.get("impacted_versions") or [],
            "candidate_version_count": queue.get("candidate_version_count") or 0,
        }
    )
    if str(queue["content_hash"]) != expected:
        raise ResearchImpactError("content_hash does not match impact queue")
    return dict(queue)


def _normalize_event(event: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(event, Mapping):
        raise ResearchImpactError("event must be a JSON object")
    event_type = str(event.get("event_type") or event.get("document_type") or "").strip().lower()
    if not event_type:
        raise ResearchImpactError("event_type or document_type is required")
    subject_type = str(event.get("subject_type") or "").strip().lower()
    subject_id = str(
        event.get("subject_id")
        or event.get("company_id")
        or event.get("industry_id")
        or event.get("futures_variety_id")
        or ""
    ).strip()
    if not subject_id:
        raise ResearchImpactError("event subject_id, company_id, or industry_id is required")
    event_at = str(
        event.get("published_at")
        or event.get("occurred_at")
        or event.get("event_at")
        or ""
    ).strip()
    if event_at:
        _parse_datetime(event_at, "event_at")
    source = str(event.get("source") or event.get("event_source") or "").strip()
    if not source:
        raise ResearchImpactError("event source is required")
    event_id = str(
        event.get("event_id")
        or event.get("impact_id")
        or event.get("document_id")
        or ""
    ).strip()
    if not event_id:
        event_id = "event-" + _hash_payload(
            {"type": event_type, "subject": subject_id, "at": event_at, "source": source}
        )[:20]
    modules = _string_list(event.get("affected_modules"))
    if not modules:
        modules = list(_EVENT_MODULES.get(event_type, ("research_report",)))
    return {
        "event_id": event_id,
        "event_type": event_type,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "event_at": event_at,
        "source": source,
        "asset_id": str(
            event.get("event_asset_id")
            or event.get("asset_id")
            or event.get("document_id")
            or event.get("impact_id")
            or ""
        ).strip(),
        "evidence_ids": _string_list(event.get("evidence_ids") or event.get("evidence_refs")),
        "affected_modules": modules,
    }


def _subject_matches(event: Mapping[str, Any], version: Mapping[str, Any]) -> bool:
    event_id = str(event.get("subject_id") or "")
    version_ids = {str(value) for value in version.get("subject_ids") or []}
    if event_id not in version_ids:
        return False
    event_type = str(event.get("subject_type") or "")
    return (
        not event_type
        or event_type == str(version.get("subject_type") or "")
        or str(version.get("subject_type")) == "mixed"
    )


def _temporal_relation(event_at: str | None, research_as_of: str) -> str:
    if not event_at:
        return "UNKNOWN"
    event_date = _parse_datetime(event_at, "event_at").date()
    cutoff = _parse_date(research_as_of, "research_as_of")
    return "PRE_CUTOFF" if event_date <= cutoff else "POST_CUTOFF"


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise ResearchImpactError("expected a string list")
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError as error:
        raise ResearchImpactError(f"{field} must be an ISO date or datetime") from error


def _parse_datetime(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ResearchImpactError(f"{field} must be an ISO datetime") from error


def _hash_payload(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
