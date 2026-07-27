"""Immutable source, evidence, lineage, and reconciliation primitives.

This module is deliberately evidence-only.  It does not calculate a target
price, emit a trading signal, or overwrite an earlier research version.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Any


SOURCE_DOCUMENT_SCHEMA_VERSION = "source-document.v1"
EVIDENCE_SCHEMA_VERSION = "evidence.v1"
MODEL_ASSUMPTION_SCHEMA_VERSION = "model-assumption.v1"
RESEARCH_ARTIFACT_SCHEMA_VERSION = "research-artifact.v1"
RESEARCH_CANDIDATE_SET_SCHEMA_VERSION = "research-candidate-set.v1"
SCORECARD_ARTIFACT_SCHEMA_VERSION = "scorecard-artifact.v1"
EVIDENCE_BUNDLE_SCHEMA_VERSION = "evidence-bundle.v1"
EVIDENCE_RECONCILIATION_SCHEMA_VERSION = "evidence-reconciliation.v1"
EVIDENCE_CUTOFF_SCHEMA_VERSION = "evidence-cutoff-validation.v1"
RULE_VERSION = "evidence-lineage-rules.v1"

VERIFIED_FACT = "verified_fact"
CROSS_VALIDATED = "cross_validated"
COMPANY_CLAIM = "company_claim"
MARKET_SIGNAL = "market_signal"
MODEL_ASSUMPTION = "model_assumption"
UNKNOWN = "unknown"

EVIDENCE_STATUSES = {
    VERIFIED_FACT,
    CROSS_VALIDATED,
    COMPANY_CLAIM,
    MARKET_SIGNAL,
    MODEL_ASSUMPTION,
    UNKNOWN,
}
EVIDENCE_TIERS = {"A", "B", "C", "C_external_ai_lead", "D_unverified_model_claim"}
VERIFICATION_STATUSES = {
    "VERIFIED",
    "CROSS_VALIDATED",
    "UNVERIFIED",
    "CONFLICTING",
    "EXCLUDED_FUTURE",
    "SUPERSEDED",
}


class EvidenceError(ValueError):
    """Raised when an evidence object violates the lineage contract."""


def build_source_document(
    payload: Mapping[str, Any],
    *,
    raw_content: bytes | str | None = None,
    raw_content_uri: str = "",
    document_id: str = "",
) -> dict[str, Any]:
    """Create an immutable source manifest and compute its content hash."""

    if not isinstance(payload, Mapping):
        raise EvidenceError("source document input must be a JSON object")
    identifier = str(payload.get("document_id") or document_id).strip()
    if not identifier:
        raise EvidenceError("document_id is required")
    source_name = str(payload.get("source_name") or payload.get("source") or "").strip()
    source_type = str(payload.get("source_type") or "").strip()
    if not source_name:
        raise EvidenceError("source_name is required")
    if not source_type:
        raise EvidenceError("source_type is required")
    source_url = str(payload.get("source_url") or "").strip()
    uri = str(raw_content_uri or payload.get("raw_content_uri") or "").strip()
    if source_url and not source_url.startswith(("http://", "https://")):
        raise EvidenceError("source_url must be an http(s) URL")
    if not source_url and not uri:
        raise EvidenceError("source_url or raw_content_uri is required")

    published_at = _temporal_text(
        payload.get("published_at") or payload.get("available_at"),
        "published_at",
        required=True,
    )
    captured_at = _temporal_text(payload.get("captured_at"), "captured_at", required=True)
    research_as_of = _temporal_text(
        payload.get("research_as_of") or payload.get("as_of"),
        "research_as_of",
        required=True,
    )
    available = _instant(published_at) <= _instant(research_as_of)

    content = _content_bytes(raw_content, payload)
    expected_hash = str(payload.get("content_hash") or "").strip().lower()
    content_hash = sha256(content).hexdigest() if content is not None else expected_hash
    if content is not None and expected_hash and expected_hash != content_hash:
        raise EvidenceError("content_hash does not match raw content")
    if not content_hash:
        raise EvidenceError("raw content or content_hash is required")
    if len(content_hash) != 64 or any(ch not in "0123456789abcdef" for ch in content_hash):
        raise EvidenceError("content_hash must be a SHA-256 hex digest")

    correction_status = str(payload.get("correction_status") or "ORIGINAL").strip().upper()
    if correction_status not in {"ORIGINAL", "CORRECTED", "SUPPLEMENT", "WITHDRAWN"}:
        raise EvidenceError(f"unsupported correction_status: {correction_status}")
    supersedes = str(payload.get("supersedes_document_id") or "").strip()
    if correction_status == "ORIGINAL" and supersedes:
        raise EvidenceError("ORIGINAL source document cannot supersede another document")
    if correction_status != "ORIGINAL" and not supersedes:
        raise EvidenceError("a corrected source document requires supersedes_document_id")
    if supersedes == identifier:
        raise EvidenceError("a source document cannot supersede itself")

    return {
        "schema_version": SOURCE_DOCUMENT_SCHEMA_VERSION,
        "document_id": identifier,
        "source_name": source_name,
        "source_type": source_type,
        "source_url": source_url,
        "raw_content_uri": uri,
        "subject_type": str(payload.get("subject_type") or ""),
        "subject_id": str(payload.get("subject_id") or ""),
        "issuer": str(payload.get("issuer") or ""),
        "title": str(payload.get("title") or ""),
        "published_at": published_at,
        "captured_at": captured_at,
        "research_as_of": research_as_of,
        "available_before_as_of": available,
        "source_version": str(payload.get("source_version") or "unknown"),
        "parser_version": str(payload.get("parser_version") or "manual-1"),
        "content_hash": content_hash,
        "content_size_bytes": len(content) if content is not None else None,
        "content_encoding": str(payload.get("content_encoding") or "utf-8"),
        "correction_status": correction_status,
        "supersedes_document_id": supersedes or None,
        "correction_reason": str(payload.get("correction_reason") or ""),
        "metadata": dict(payload.get("metadata") or {}),
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "rule_version": RULE_VERSION,
        "policy": _policy(),
    }


def validate_source_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a previously built source manifest without changing it."""

    if not isinstance(document, Mapping):
        raise EvidenceError("source document must be a JSON object")
    if document.get("schema_version") != SOURCE_DOCUMENT_SCHEMA_VERSION:
        raise EvidenceError(f"input must be {SOURCE_DOCUMENT_SCHEMA_VERSION}")
    if document.get("immutable") is not True:
        raise EvidenceError("source document must be immutable")
    for field in ("document_id", "source_name", "source_type", "content_hash"):
        if not str(document.get(field) or "").strip():
            raise EvidenceError(f"source document {field} is required")
    digest = str(document["content_hash"]).lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise EvidenceError("source document content_hash must be SHA-256")
    for field in ("published_at", "captured_at", "research_as_of"):
        _temporal_text(document.get(field), field, required=True)
    return dict(document)


def build_evidence(
    payload: Mapping[str, Any],
    *,
    source_document: Mapping[str, Any] | None = None,
    evidence_id: str = "",
) -> dict[str, Any]:
    """Extract one immutable, field-located fact from a source document."""

    if not isinstance(payload, Mapping):
        raise EvidenceError("evidence input must be a JSON object")
    document = None
    if source_document is not None:
        document = validate_source_document(source_document)
    elif isinstance(payload.get("source_document"), Mapping):
        document = validate_source_document(payload["source_document"])

    metric = str(payload.get("metric") or payload.get("field") or "").strip()
    if not metric:
        raise EvidenceError("metric is required")
    subject_id = str(
        payload.get("subject_id")
        or payload.get("company_id")
        or payload.get("industry_id")
        or payload.get("futures_variety_id")
        or ""
    ).strip()
    if not subject_id:
        raise EvidenceError("subject_id, company_id, industry_id, or futures_variety_id is required")

    published_at = _temporal_text(
        payload.get("published_at") or (document or {}).get("published_at"),
        "published_at",
        required=True,
    )
    captured_at = _temporal_text(
        payload.get("captured_at") or (document or {}).get("captured_at"),
        "captured_at",
        required=True,
    )
    research_as_of = _temporal_text(
        payload.get("research_as_of")
        or payload.get("as_of")
        or (document or {}).get("research_as_of"),
        "research_as_of",
        required=True,
    )
    available = _instant(published_at) <= _instant(research_as_of)

    tier = _normalise_tier(payload.get("evidence_tier") or payload.get("confidence") or "A")
    status = _normalise_evidence_status(
        payload.get("evidence_status") or payload.get("status") or ""
    )
    if not status:
        status = VERIFIED_FACT if tier == "A" else UNKNOWN
    if tier in {"C_external_ai_lead", "D_unverified_model_claim"} and status in {
        VERIFIED_FACT,
        CROSS_VALIDATED,
    } and not str(payload.get("manual_override_id") or "").strip():
        raise EvidenceError("external AI evidence cannot be promoted without manual_override_id")

    source_document_id = str(
        payload.get("source_document_id")
        or (document or {}).get("document_id")
        or payload.get("source_id")
        or ""
    ).strip()
    source_name = str(
        payload.get("source_name")
        or payload.get("source")
        or (document or {}).get("source_name")
        or ""
    ).strip()
    source_type = str(payload.get("source_type") or (document or {}).get("source_type") or "").strip()
    source_url = str(payload.get("source_url") or (document or {}).get("source_url") or "").strip()
    source_version = str(
        payload.get("source_document_version")
        or payload.get("source_version")
        or (document or {}).get("source_version")
        or "unknown"
    ).strip()
    content_hash = str(
        payload.get("content_hash")
        or (document or {}).get("content_hash")
        or ""
    ).strip().lower()
    if not source_name and not source_document_id:
        raise EvidenceError("source_name or source_document_id is required")
    if content_hash and (
        len(content_hash) != 64
        or any(ch not in "0123456789abcdef" for ch in content_hash)
    ):
        raise EvidenceError("content_hash must be a SHA-256 hex digest")
    if document and source_document_id and source_document_id != document["document_id"]:
        raise EvidenceError("source_document_id does not match source_document")
    if document and content_hash and content_hash != document["content_hash"]:
        raise EvidenceError("evidence content_hash does not match source document")

    location = _location(payload)
    lineage = dict(payload.get("field_lineage") or payload.get("lineage") or {})
    for field in ("subject_id", "metric", "value", "unit", "period"):
        lineage.setdefault(
            field,
            {
                "source_document_id": source_document_id or None,
                "source_document_version": source_version,
                "source_locator": location or None,
                "source_field": str(payload.get("source_field") or field),
            },
        )

    value = payload.get("value") if "value" in payload else payload.get("raw_value")
    period = str(payload.get("period") or "").strip()
    identifier = str(payload.get("evidence_id") or evidence_id).strip()
    if not identifier:
        fingerprint = _digest(
            {
                "source_document_id": source_document_id,
                "content_hash": content_hash,
                "subject_id": subject_id,
                "metric": metric,
                "period": period,
                "value": value,
            }
        )
        identifier = f"ev-{fingerprint[:20]}"
    correction_status = str(
        payload.get("correction_status") or (document or {}).get("correction_status") or "ORIGINAL"
    ).strip().upper()
    if correction_status not in {"ORIGINAL", "CORRECTED", "SUPPLEMENT", "WITHDRAWN"}:
        raise EvidenceError(f"unsupported correction_status: {correction_status}")
    supersedes_evidence_id = str(payload.get("supersedes_evidence_id") or "").strip()
    if correction_status == "ORIGINAL" and supersedes_evidence_id:
        raise EvidenceError("ORIGINAL evidence cannot supersede another evidence item")
    if correction_status != "ORIGINAL" and not supersedes_evidence_id:
        raise EvidenceError("a corrected evidence item requires supersedes_evidence_id")
    if supersedes_evidence_id == identifier:
        raise EvidenceError("an evidence item cannot supersede itself")

    verification_status = _normalise_verification_status(payload.get("verification_status"))
    if not verification_status:
        verification_status = {
            VERIFIED_FACT: "VERIFIED",
            CROSS_VALIDATED: "CROSS_VALIDATED",
        }.get(status, "UNVERIFIED")
    if status == CROSS_VALIDATED and verification_status not in {"CROSS_VALIDATED", "VERIFIED"}:
        raise EvidenceError("cross_validated evidence must have a verified status")
    if status == VERIFIED_FACT and verification_status == "CONFLICTING":
        raise EvidenceError("verified_fact cannot have CONFLICTING verification_status")
    if not available:
        temporal_status = "POST_CUTOFF"
        effective_verification = "EXCLUDED_FUTURE"
    else:
        temporal_status = (
            "AT_CUTOFF"
            if _instant(published_at) == _instant(research_as_of)
            else "PRE_CUTOFF"
        )
        effective_verification = verification_status

    output = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "evidence_id": identifier,
        "subject_type": str(payload.get("subject_type") or (document or {}).get("subject_type") or ""),
        "subject_id": subject_id,
        "company_id": str(payload.get("company_id") or ""),
        "industry_id": str(payload.get("industry_id") or ""),
        "futures_variety_id": str(payload.get("futures_variety_id") or ""),
        "issuer": str(payload.get("issuer") or (document or {}).get("issuer") or ""),
        "metric": metric,
        "value": value,
        "unit": str(payload.get("unit") or ""),
        "currency": str(payload.get("currency") or ""),
        "period": period,
        "published_at": published_at,
        "captured_at": captured_at,
        "research_as_of": research_as_of,
        "as_of": research_as_of,
        "available_before_as_of": available,
        "temporal_status": temporal_status,
        "source_name": source_name,
        "source_type": source_type,
        "source_url": source_url,
        "source_document_id": source_document_id,
        "source_document_version": source_version,
        "content_hash": content_hash,
        "parser_version": str(payload.get("parser_version") or (document or {}).get("parser_version") or "manual-1"),
        "extraction_method": str(payload.get("extraction_method") or "manual_verified"),
        "source_locator": location,
        "page": payload.get("page"),
        "paragraph": str(payload.get("paragraph") or ""),
        "table": str(payload.get("table") or ""),
        "field_path": str(payload.get("field_path") or ""),
        "evidence_tier": tier,
        "confidence": tier,
        "evidence_status": status,
        "verification_status": effective_verification,
        "supersedes_evidence_id": supersedes_evidence_id or None,
        "correction_status": correction_status,
        "manual_override_id": str(payload.get("manual_override_id") or "") or None,
        "conflict_group_id": str(payload.get("conflict_group_id") or "") or None,
        "field_lineage": lineage,
        "metadata": dict(payload.get("metadata") or {}),
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "rule_version": RULE_VERSION,
        "policy": _policy(),
    }
    return output


def build_model_assumption(
    payload: Mapping[str, Any], *, assumption_id: str = ""
) -> dict[str, Any]:
    """Store an explicit model input without presenting it as a fact."""

    if not isinstance(payload, Mapping):
        raise EvidenceError("model assumption input must be a JSON object")
    name = str(payload.get("name") or payload.get("metric") or "").strip()
    if not name:
        raise EvidenceError("model assumption name is required")
    as_of = _temporal_text(
        payload.get("research_as_of") or payload.get("as_of"),
        "research_as_of",
        required=True,
    )
    identifier = str(payload.get("assumption_id") or assumption_id).strip() or f"assumption-{_digest(payload)[:20]}"
    return {
        "schema_version": MODEL_ASSUMPTION_SCHEMA_VERSION,
        "assumption_id": identifier,
        "subject_id": str(payload.get("subject_id") or ""),
        "name": name,
        "value": payload.get("value"),
        "unit": str(payload.get("unit") or ""),
        "research_as_of": as_of,
        "rationale": str(payload.get("rationale") or ""),
        "evidence_ids": _string_list(payload.get("evidence_ids")),
        "status": MODEL_ASSUMPTION,
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "rule_version": RULE_VERSION,
        "policy": _policy(),
    }


def build_research_artifact(
    payload: Mapping[str, Any], *, artifact_id: str = ""
) -> dict[str, Any]:
    """Wrap an upstream research result while keeping it reference-only."""

    if not isinstance(payload, Mapping):
        raise EvidenceError("research artifact input must be a JSON object")
    project = str(payload.get("source_project") or payload.get("project") or "").strip()
    if not project:
        raise EvidenceError("source_project is required")
    as_of = _temporal_text(
        payload.get("research_as_of") or payload.get("research_date") or payload.get("as_of"),
        "research_as_of",
        required=True,
    )
    identifier = str(payload.get("artifact_id") or artifact_id).strip() or f"artifact-{_digest(payload)[:20]}"
    strategy = str(payload.get("reuse_strategy") or "REFERENCE_ONLY").strip().upper()
    if strategy not in {"DIRECT_REUSE", "REUSE_WITH_CHECK", "METHOD_REUSE", "REFERENCE_ONLY"}:
        raise EvidenceError(f"unsupported research artifact reuse_strategy: {strategy}")
    content_hash = str(payload.get("content_hash") or payload.get("file_hash") or "").strip().lower()
    if not content_hash:
        raise EvidenceError("content_hash or file_hash is required")
    if len(content_hash) != 64 or any(ch not in "0123456789abcdef" for ch in content_hash):
        raise EvidenceError("research artifact content_hash must be a SHA-256 hex digest")
    return {
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "artifact_id": identifier,
        "source_project": project,
        "artifact_type": str(payload.get("artifact_type") or "research_output"),
        "source_path": str(payload.get("source_path") or ""),
        "source_url": str(payload.get("source_url") or ""),
        "source_version": str(payload.get("source_version") or "unknown"),
        "mapping_version": str(payload.get("mapping_version") or "unknown"),
        "content_hash": content_hash,
        "research_as_of": as_of,
        "generated_at": str(payload.get("generated_at") or payload.get("file_modified_at") or ""),
        "reuse_strategy": strategy,
        "validation_status": str(payload.get("validation_status") or "UNVERIFIED"),
        "evidence_ids": _string_list(payload.get("evidence_ids")),
        "field_lineage": dict(payload.get("field_lineage") or payload.get("lineage") or {}),
        "claims_are_verified": False,
        "content_copied": False,
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "rule_version": RULE_VERSION,
        "policy": _policy(),
    }


def build_research_candidate_set(
    payload: Mapping[str, Any], *, candidate_set_id: str = ""
) -> dict[str, Any]:
    """Store a bounded candidate set without claiming full-market coverage."""

    if not isinstance(payload, Mapping):
        raise EvidenceError("research candidate set input must be a JSON object")
    source_project = str(payload.get("source_project") or payload.get("project") or "").strip()
    if not source_project:
        raise EvidenceError("source_project is required")
    as_of = _temporal_text(
        payload.get("research_as_of") or payload.get("as_of"),
        "research_as_of",
        required=True,
    )
    candidates = payload.get("candidates") or payload.get("items") or []
    if not isinstance(candidates, list):
        raise EvidenceError("candidates must be a list")
    identifier = str(payload.get("candidate_set_id") or candidate_set_id).strip() or f"candidates-{_digest(payload)[:20]}"
    return {
        "schema_version": RESEARCH_CANDIDATE_SET_SCHEMA_VERSION,
        "candidate_set_id": identifier,
        "research_id": str(payload.get("research_id") or ""),
        "source_project": source_project,
        "research_as_of": as_of,
        "scope": {
            "bounded": True,
            "complete": bool(payload.get("complete", False)),
            "representative": bool(payload.get("representative", True)),
            "boundary": str(payload.get("boundary") or "industry_selected_pool"),
        },
        "candidates": [dict(item) if isinstance(item, Mapping) else {"value": item} for item in candidates],
        "candidate_count": len(candidates),
        "evidence_ids": _string_list(payload.get("evidence_ids")),
        "source_version": str(payload.get("source_version") or "unknown"),
        "mapping_version": str(payload.get("mapping_version") or "unknown"),
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "rule_version": RULE_VERSION,
        "policy": {
            **_policy(),
            "candidate_set_not_security_master": True,
            "full_market_coverage_not_claimed": not bool(payload.get("complete", False)),
        },
    }


def build_scorecard_artifact(
    payload: Mapping[str, Any], *, scorecard_id: str = ""
) -> dict[str, Any]:
    """Store a scorecard with its metric definitions and evidence coverage."""

    if not isinstance(payload, Mapping):
        raise EvidenceError("scorecard input must be a JSON object")
    scorecard_type = str(payload.get("scorecard_type") or payload.get("type") or "").strip()
    if not scorecard_type:
        raise EvidenceError("scorecard_type is required")
    as_of = _temporal_text(
        payload.get("research_as_of") or payload.get("as_of"),
        "research_as_of",
        required=True,
    )
    metrics = payload.get("metrics") or payload.get("items") or []
    if not isinstance(metrics, list):
        raise EvidenceError("metrics must be a list")
    identifier = str(payload.get("scorecard_id") or scorecard_id).strip() or f"scorecard-{_digest(payload)[:20]}"
    return {
        "schema_version": SCORECARD_ARTIFACT_SCHEMA_VERSION,
        "scorecard_id": identifier,
        "scorecard_type": scorecard_type,
        "subject_id": str(payload.get("subject_id") or ""),
        "research_as_of": as_of,
        "rule_version": str(payload.get("rule_version") or RULE_VERSION),
        "metrics": [dict(item) if isinstance(item, Mapping) else {"value": item} for item in metrics],
        "metric_definitions": dict(payload.get("metric_definitions") or {}),
        "evidence_ids": _string_list(payload.get("evidence_ids")),
        "evidence_completeness": str(payload.get("evidence_completeness") or "UNKNOWN"),
        "missing_items": _string_list(payload.get("missing_items")),
        "final_rating": payload.get("final_rating") if "final_rating" in payload else None,
        "claims_are_verified": False,
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "policy": {
            **_policy(),
            "industry_specific_scorecard_required": True,
            "scorecard_is_not_an_investment_conclusion": True,
        },
    }


def build_evidence_bundle(
    evidence: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    *,
    source_documents: Sequence[Mapping[str, Any]] | None = None,
    model_assumptions: Sequence[Mapping[str, Any]] | None = None,
    research_artifacts: Sequence[Mapping[str, Any]] | None = None,
    candidate_sets: Sequence[Mapping[str, Any]] | None = None,
    scorecards: Sequence[Mapping[str, Any]] | None = None,
    research_as_of: str = "",
    subject_id: str = "",
    bundle_id: str = "",
) -> dict[str, Any]:
    """Assemble a bounded evidence package with active and excluded IDs."""

    if isinstance(evidence, Mapping):
        source_documents = source_documents if source_documents is not None else evidence.get("source_documents")
        model_assumptions = model_assumptions if model_assumptions is not None else evidence.get("model_assumptions")
        research_artifacts = research_artifacts if research_artifacts is not None else evidence.get("research_artifacts")
        candidate_sets = candidate_sets if candidate_sets is not None else evidence.get("research_candidate_sets", evidence.get("candidate_sets"))
        scorecards = scorecards if scorecards is not None else evidence.get("scorecard_artifacts", evidence.get("scorecards"))
        research_as_of = research_as_of or str(evidence.get("research_as_of") or evidence.get("as_of") or "")
        subject_id = subject_id or str(evidence.get("subject_id") or "")
        evidence = evidence.get("evidence") or []
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes, bytearray)):
        raise EvidenceError("evidence must be a list")

    raw_documents = list(source_documents or [])
    documents: list[dict[str, Any]] = []
    for item in raw_documents:
        if not isinstance(item, Mapping):
            raise EvidenceError("each source document must be an object")
        documents.append(
            validate_source_document(item)
            if item.get("schema_version") == SOURCE_DOCUMENT_SCHEMA_VERSION
            else build_source_document(item)
        )
    documents_by_id = {item["document_id"]: item for item in documents}

    evidence_items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in evidence:
        if not isinstance(item, Mapping):
            raise EvidenceError("each evidence item must be an object")
        if item.get("schema_version") == EVIDENCE_SCHEMA_VERSION:
            built = dict(item)
            if built.get("immutable") is not True:
                raise EvidenceError("evidence must be immutable")
        else:
            reference = documents_by_id.get(str(item.get("source_document_id") or ""))
            built = build_evidence(
                item,
                source_document=reference,
            )
        if built["evidence_id"] in seen_ids:
            raise EvidenceError(f"duplicate evidence_id: {built['evidence_id']}")
        seen_ids.add(built["evidence_id"])
        evidence_items.append(built)

    if not research_as_of:
        dates = [str(item.get("research_as_of") or "") for item in evidence_items if item.get("research_as_of")]
        dates.extend(str(item.get("research_as_of") or "") for item in documents if item.get("research_as_of"))
        research_as_of = min(dates) if dates else ""
    if not research_as_of:
        raise EvidenceError("research_as_of is required")
    _temporal_text(research_as_of, "research_as_of", required=True)

    assumptions = _build_collection(
        model_assumptions, build_model_assumption, MODEL_ASSUMPTION_SCHEMA_VERSION
    )
    artifacts = _build_collection(
        research_artifacts, build_research_artifact, RESEARCH_ARTIFACT_SCHEMA_VERSION
    )
    candidate_items = _build_collection(
        candidate_sets, build_research_candidate_set, RESEARCH_CANDIDATE_SET_SCHEMA_VERSION
    )
    scorecard_items = _build_collection(
        scorecards, build_scorecard_artifact, SCORECARD_ARTIFACT_SCHEMA_VERSION
    )
    cutoff = validate_evidence_cutoff(evidence_items, research_as_of=research_as_of)
    known_document_ids = set(documents_by_id)
    referenced_ids = {
        str(item.get("source_document_id") or "")
        for item in evidence_items
        if str(item.get("source_document_id") or "")
    }
    unresolved = sorted(referenced_ids - known_document_ids)
    identifier = str(bundle_id).strip() or f"bundle-{_digest({'as_of': research_as_of, 'ids': sorted(seen_ids)})[:20]}"
    status = "READY"
    if cutoff["unknown_count"] or cutoff["future_count"]:
        status = "PARTIAL"
    if not evidence_items:
        status = "INSUFFICIENT"
    return {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "bundle_id": identifier,
        "subject_id": subject_id,
        "research_as_of": research_as_of,
        "source_documents": documents,
        "source_document_ids": [item["document_id"] for item in documents],
        "evidence": evidence_items,
        "evidence_ids": [item["evidence_id"] for item in evidence_items],
        "model_assumptions": assumptions,
        "research_artifacts": artifacts,
        "research_candidate_sets": candidate_items,
        "scorecard_artifacts": scorecard_items,
        "active_evidence_ids": cutoff["eligible_evidence_ids"],
        "excluded_future_evidence_ids": cutoff["future_evidence_ids"],
        "unknown_temporal_evidence_ids": cutoff["unknown_evidence_ids"],
        "unresolved_source_document_ids": unresolved,
        "evidence_status_counts": dict(Counter(item["evidence_status"] for item in evidence_items)),
        "verification_status_counts": dict(Counter(item["verification_status"] for item in evidence_items)),
        "status": status,
        "cutoff_validation": cutoff,
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "rule_version": RULE_VERSION,
        "policy": {
            **_policy(),
            "historical_versions_are_append_only": True,
            "future_information_not_backfilled": True,
            "conflicts_must_be_reconciled_explicitly": True,
        },
    }


def validate_evidence_cutoff(
    evidence: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    research_as_of: str = "",
) -> dict[str, Any]:
    """Classify evidence by information availability at a research cutoff."""

    if isinstance(evidence, Mapping):
        research_as_of = research_as_of or str(evidence.get("research_as_of") or evidence.get("as_of") or "")
        evidence = evidence.get("evidence") or []
    if not research_as_of:
        raise EvidenceError("research_as_of is required")
    cutoff = _temporal_text(research_as_of, "research_as_of", required=True)
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes, bytearray)):
        raise EvidenceError("evidence must be a list")
    eligible: list[str] = []
    future: list[str] = []
    unknown: list[str] = []
    relations: list[dict[str, Any]] = []
    for index, item in enumerate(evidence):
        if not isinstance(item, Mapping):
            raise EvidenceError("each evidence item must be an object")
        identifier = str(item.get("evidence_id") or f"item-{index}")
        published = str(item.get("published_at") or "").strip()
        if not published:
            relation = "UNKNOWN"
            unknown.append(identifier)
            reason = "PUBLISHED_AT_MISSING"
        else:
            _temporal_text(published, "published_at", required=True)
            published_instant = _instant(published)
            cutoff_instant = _instant(cutoff)
            if published_instant > cutoff_instant:
                relation = "POST_CUTOFF"
                future.append(identifier)
                reason = "PUBLISHED_AFTER_RESEARCH_AS_OF"
            elif published_instant == cutoff_instant:
                relation = "AT_CUTOFF"
                eligible.append(identifier)
                reason = "AVAILABLE_AT_CUTOFF"
            else:
                relation = "PRE_CUTOFF"
                eligible.append(identifier)
                reason = "AVAILABLE_BEFORE_CUTOFF"
        relations.append(
            {
                "evidence_id": identifier,
                "published_at": published,
                "research_as_of": cutoff,
                "temporal_relation": relation,
                "eligible": identifier in eligible,
                "reason": reason,
            }
        )
    return {
        "schema_version": EVIDENCE_CUTOFF_SCHEMA_VERSION,
        "research_as_of": cutoff,
        "evidence_count": len(evidence),
        "eligible_evidence_ids": eligible,
        "future_evidence_ids": future,
        "unknown_evidence_ids": unknown,
        "future_count": len(future),
        "unknown_count": len(unknown),
        "historical_research_safe": not future and not unknown,
        "relations": relations,
        "policy": {
            "future_information_excluded": True,
            "unknown_publication_time_excluded": True,
            "old_research_not_overwritten": True,
        },
    }


def reconcile_evidence(
    evidence: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    research_as_of: str = "",
    group_by: Sequence[str] = ("subject_id", "metric", "period", "unit"),
    source_priority: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Reconcile independent evidence without averaging conflicting values."""

    if isinstance(evidence, Mapping):
        research_as_of = research_as_of or str(evidence.get("research_as_of") or evidence.get("as_of") or "")
        evidence = evidence.get("evidence") or []
    if not research_as_of:
        raise EvidenceError("research_as_of is required")
    _temporal_text(research_as_of, "research_as_of", required=True)
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes, bytearray)):
        raise EvidenceError("evidence must be a list")
    fields = tuple(str(item).strip() for item in group_by if str(item).strip())
    if not fields:
        raise EvidenceError("group_by must contain at least one field")
    priorities = dict(source_priority or {})
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for item in evidence:
        if not isinstance(item, Mapping):
            raise EvidenceError("each evidence item must be an object")
        if str(item.get("published_at") or "").strip() and _instant(str(item["published_at"])) > _instant(research_as_of):
            continue
        if not str(item.get("published_at") or "").strip():
            continue
        key_values = {field: item.get(field) for field in fields}
        key = _digest(key_values)[:20]
        groups.setdefault(key, []).append(item)

    reconciled: list[dict[str, Any]] = []
    conflict_groups: list[str] = []
    status_counts: Counter[str] = Counter()
    for key, records in groups.items():
        values: dict[str, list[Mapping[str, Any]]] = {}
        for record in records:
            signature = _value_signature(record.get("value"), record.get("unit"), record.get("currency"))
            values.setdefault(signature, []).append(record)
        sources = {_source_identity(record) for record in records}
        formal = [record for record in records if _formal_evidence(record)]
        group_id = str(records[0].get("conflict_group_id") or f"conflict-{key}")
        selected = None
        decision = "SINGLE_SOURCE"
        status = UNKNOWN
        reason = "no eligible evidence"
        if len(values) == 1:
            same_value_records = next(iter(values.values()))
            ranked = sorted(same_value_records, key=lambda item: _source_rank(item, priorities), reverse=True)
            selected = ranked[0]
            if len({_source_identity(item) for item in same_value_records if _formal_evidence(item)}) >= 2:
                status = CROSS_VALIDATED
                decision = "CROSS_VALIDATED"
                reason = "independent eligible sources agree on the normalized value"
            else:
                status = _canonical_status(selected)
                decision = "SINGLE_SOURCE" if len(sources) <= 1 else "SAME_VALUE_NOT_INDEPENDENT"
                reason = "one formal source supports the adopted value"
        else:
            ranked = sorted(
                records,
                key=lambda item: _source_sort_key(item, priorities),
                reverse=True,
            )
            top_key = _source_sort_key(ranked[0], priorities)
            top = [
                item
                for item in ranked
                if _source_sort_key(item, priorities) == top_key
            ]
            manual = [item for item in records if str(item.get("manual_override_id") or "").strip()]
            if len(manual) == 1:
                selected = manual[0]
                status = _canonical_status(selected)
                decision = "RESOLVED_BY_MANUAL_OVERRIDE"
                reason = "explicit manual override selected one immutable evidence version"
            elif len(top) == 1 and top_key[0] >= 80:
                selected = top[0]
                status = _canonical_status(selected)
                decision = "RESOLVED_BY_SOURCE_PRIORITY"
                reason = "highest-priority source selected; all conflicting values remain preserved"
            else:
                status = "CONFLICTING"
                decision = "UNRESOLVED_CONFLICT"
                reason = "different values remain after source and independence checks"
        if status == UNKNOWN and selected is not None:
            status = _canonical_status(selected)
        if status == "CONFLICTING":
            conflict_groups.append(group_id)
        status_counts[status] += 1
        reconciled.append(
            {
                "conflict_group_id": group_id,
                "key": {field: records[0].get(field) for field in fields},
                "evidence_ids": [str(item.get("evidence_id") or "") for item in records],
                "eligible_evidence_ids": [str(item.get("evidence_id") or "") for item in records],
                "source_identities": sorted(sources),
                "independent_source_count": len(sources),
                "values": [
                    {
                        "value": records_for_value[0].get("value"),
                        "unit": records_for_value[0].get("unit", ""),
                        "currency": records_for_value[0].get("currency", ""),
                        "evidence_ids": [
                            str(entry.get("evidence_id") or "")
                            for entry in records_for_value
                        ],
                    }
                    for records_for_value in values.values()
                ],
                "status": status,
                "decision": decision,
                "decision_reason": reason,
                "selected_evidence_id": str(selected.get("evidence_id") or "") if selected else None,
                "adopted_value": selected.get("value") if selected else None,
                "adopted_unit": selected.get("unit", "") if selected else "",
                "adopted_evidence_ids": (
                    [str(item.get("evidence_id") or "") for item in next(iter(values.values()))]
                    if selected is not None and decision in {"CROSS_VALIDATED", "SINGLE_SOURCE", "SAME_VALUE_NOT_INDEPENDENT"}
                    else ([str(selected.get("evidence_id") or "")] if selected else [])
                ),
                "source_priority": {
                    str(item.get("evidence_id") or ""): _source_rank(item, priorities)
                    for item in records
                },
                "conflict_preserved": len(values) > 1,
            }
        )
    return {
        "schema_version": EVIDENCE_RECONCILIATION_SCHEMA_VERSION,
        "reconciliation_id": f"reconciliation-{_digest({'as_of': research_as_of, 'groups': sorted(groups)})[:20]}",
        "research_as_of": research_as_of,
        "group_by": list(fields),
        "group_count": len(reconciled),
        "groups": reconciled,
        "conflict_groups": conflict_groups,
        "conflict_count": len(conflict_groups),
        "status_counts": dict(status_counts),
        "policy": {
            "conflicting_values_not_averaged": True,
            "all_source_values_preserved": True,
            "manual_override_is_explicit": True,
            "future_information_excluded": True,
            "no_investment_conclusion": True,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "rule_version": RULE_VERSION,
    }


def build_evidence_input_bundle(payload: Mapping[str, Any], *, bundle_id: str = "") -> dict[str, Any]:
    """Build a bundle from the CLI's compact raw-input contract."""

    if not isinstance(payload, Mapping):
        raise EvidenceError("evidence input must be a JSON object")
    documents = []
    for item in payload.get("source_documents") or []:
        if not isinstance(item, Mapping):
            raise EvidenceError("each source document must be an object")
        documents.append(
            item
            if item.get("schema_version") == SOURCE_DOCUMENT_SCHEMA_VERSION
            else build_source_document(item)
        )
    by_id = {item["document_id"]: item for item in documents}
    records = []
    for item in payload.get("evidence") or []:
        if not isinstance(item, Mapping):
            raise EvidenceError("each evidence item must be an object")
        if item.get("schema_version") == EVIDENCE_SCHEMA_VERSION:
            records.append(item)
        else:
            records.append(
                build_evidence(
                    item,
                    source_document=by_id.get(str(item.get("source_document_id") or "")),
                )
            )
    return build_evidence_bundle(
        records,
        source_documents=documents,
        model_assumptions=payload.get("model_assumptions"),
        research_artifacts=payload.get("research_artifacts"),
        candidate_sets=payload.get("research_candidate_sets") or payload.get("candidate_sets"),
        scorecards=payload.get("scorecard_artifacts") or payload.get("scorecards"),
        research_as_of=str(payload.get("research_as_of") or payload.get("as_of") or ""),
        subject_id=str(payload.get("subject_id") or ""),
        bundle_id=bundle_id,
    )


def _build_collection(
    items: Sequence[Mapping[str, Any]] | None,
    builder: Any,
    schema_version: str,
) -> list[dict[str, Any]]:
    result = []
    for item in items or []:
        if not isinstance(item, Mapping):
            raise EvidenceError("collection item must be an object")
        result.append(
            dict(item)
            if str(item.get("schema_version") or "") == schema_version
            else builder(item)
        )
    return result


def _normalise_tier(value: Any) -> str:
    tier = str(value or "").strip()
    aliases = {"D": "D_unverified_model_claim", "C_EXTERNAL_AI": "C_external_ai_lead"}
    tier = aliases.get(tier.upper(), tier)
    if tier not in EVIDENCE_TIERS:
        raise EvidenceError(f"unsupported evidence_tier: {tier}")
    return tier


def _normalise_evidence_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "verified": VERIFIED_FACT,
        "fact": VERIFIED_FACT,
        "cross-validated": CROSS_VALIDATED,
        "cross_validated": CROSS_VALIDATED,
        "claim": COMPANY_CLAIM,
        "signal": MARKET_SIGNAL,
        "assumption": MODEL_ASSUMPTION,
        "unverified": UNKNOWN,
    }
    text = aliases.get(text, text)
    if text and text not in EVIDENCE_STATUSES:
        raise EvidenceError(f"unsupported evidence_status: {text}")
    return text


def _normalise_verification_status(value: Any) -> str:
    text = str(value or "").strip().upper().replace("-", "_")
    aliases = {"VALIDATED": "VERIFIED", "CROSSVALIDATED": "CROSS_VALIDATED"}
    text = aliases.get(text, text)
    if text and text not in VERIFICATION_STATUSES:
        raise EvidenceError(f"unsupported verification_status: {text}")
    return text


def _location(payload: Mapping[str, Any]) -> dict[str, Any]:
    location = payload.get("source_locator") or payload.get("location") or {}
    if not isinstance(location, Mapping):
        raise EvidenceError("source_locator must be an object")
    result = dict(location)
    for key in ("page", "paragraph", "table", "field_path"):
        if key in payload and payload[key] not in (None, ""):
            result[key] = payload[key]
    return result


def _content_bytes(raw_content: bytes | str | None, payload: Mapping[str, Any]) -> bytes | None:
    if raw_content is not None:
        if isinstance(raw_content, bytes):
            return raw_content
        if isinstance(raw_content, str):
            return raw_content.encode(str(payload.get("content_encoding") or "utf-8"))
        raise EvidenceError("raw_content must be bytes or string")
    inline = payload.get("raw_content")
    if inline is None:
        return None
    if not isinstance(inline, str):
        raise EvidenceError("raw_content must be a string")
    return inline.encode(str(payload.get("content_encoding") or "utf-8"))


def _temporal_text(value: Any, field: str, *, required: bool) -> str:
    text = str(value or "").strip()
    if not text:
        if required:
            raise EvidenceError(f"{field} is required")
        return ""
    _instant(text)
    return text


def _instant(value: str) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.combine(date.fromisoformat(text), datetime.min.time())
        except ValueError as error:
            raise EvidenceError(f"invalid datetime: {value}") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise EvidenceError("expected a string list")
    return [str(item) for item in value if str(item).strip()]


def _policy() -> dict[str, Any]:
    return {
        "raw_source_immutable": True,
        "old_versions_preserved": True,
        "historical_research_not_overwritten": True,
        "future_information_not_backfilled": True,
        "source_lineage_required": True,
        "no_investment_conclusion": True,
        "read_only": True,
        "review_only": True,
        "execution_enabled": False,
    }


def _value_signature(value: Any, unit: Any, currency: Any) -> str:
    numeric = value
    if isinstance(value, (int, float)) or (isinstance(value, str) and _looks_numeric(value)):
        try:
            numeric = str(Decimal(str(value)).normalize())
        except InvalidOperation:
            numeric = value
    return json.dumps(
        {"value": numeric, "unit": str(unit or ""), "currency": str(currency or "")},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def _looks_numeric(value: str) -> bool:
    try:
        Decimal(value.strip())
    except InvalidOperation:
        return False
    return True


def _source_identity(item: Mapping[str, Any]) -> str:
    return str(
        item.get("source_name")
        or item.get("source_document_id")
        or item.get("source_type")
        or "unknown_source"
    ).strip()


def _source_rank(item: Mapping[str, Any], explicit: Mapping[str, int]) -> int:
    keys = (
        str(item.get("source_name") or ""),
        str(item.get("source_type") or ""),
        str(item.get("evidence_tier") or ""),
    )
    for key in keys:
        if key in explicit:
            return int(explicit[key])
    source_type = str(item.get("source_type") or "").lower()
    source_name = str(item.get("source_name") or "").lower()
    if any(token in source_type or token in source_name for token in ("exchange", "annual_report", "quarterly_report", "audit", "official", "government")):
        return 100
    if any(token in source_type or token in source_name for token in ("association", "company_disclosure", "roadshow")):
        return 85
    if any(token in source_type or token in source_name for token in ("eastmoney", "akshare", "baostock", "market_data")):
        return 60
    if "research" in source_type or "media" in source_type:
        return 30
    if "ai" in source_type:
        return 10
    return {"A": 70, "B": 50, "C": 25}.get(str(item.get("evidence_tier") or ""), 10)


def _source_sort_key(item: Mapping[str, Any], explicit: Mapping[str, int]) -> tuple[int, int, float]:
    """Rank source level, definition clarity, then information availability."""

    clarity = str(item.get("definition_clarity") or "").strip().upper()
    clarity_rank = {
        "EXPLICIT": 3,
        "CLEAR": 3,
        "DEFINED": 3,
        "PARTIAL": 2,
        "AMBIGUOUS": 1,
    }.get(clarity, 0)
    published = str(item.get("published_at") or "").strip()
    timestamp = _instant(published).timestamp() if published else float("-inf")
    return (_source_rank(item, explicit), clarity_rank, timestamp)


def _formal_evidence(item: Mapping[str, Any]) -> bool:
    return str(item.get("evidence_status") or "").lower() in {VERIFIED_FACT, CROSS_VALIDATED}


def _canonical_status(item: Mapping[str, Any]) -> str:
    status = str(item.get("evidence_status") or UNKNOWN).lower()
    return status if status in EVIDENCE_STATUSES else UNKNOWN
