"""Audit local research references before they can support verified statuses."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


SOURCE_INTEGRITY_SCHEMA_VERSION = "source-integrity-report.v1"
SOURCE_INTEGRITY_RULE_VERSION = "source-integrity-rules.v2"
_VERIFIED_STATUSES = {"VERIFIED", "CROSS_VALIDATED"}
_UNAVAILABLE_LOCAL_STATUSES = {
    "EMPTY",
    "MISSING",
    "NOT_FILE",
    "OUTSIDE_PROJECT",
    "UNDECLARED",
    "UNREADABLE",
}


class SourceIntegrityError(ValueError):
    """Raised when a source-integrity report is invalid."""


def build_source_integrity_report(
    config: Mapping[str, Any],
    project_root: str | Path,
    *,
    report_id: str = "",
) -> dict[str, Any]:
    """Resolve configured sources and fail closed when local evidence is unusable."""

    if not isinstance(config, Mapping):
        raise SourceIntegrityError("industry config must be an object")
    industry_id = str(config.get("industry_id") or "").strip()
    as_of = str(config.get("as_of") or "").strip()
    if not industry_id or not as_of:
        raise SourceIntegrityError("industry_id and as_of are required")
    root = Path(project_root).resolve()

    signals = []
    for index, raw_signal in enumerate(_mapping_list(config.get("signals"), "signals")):
        source = str(raw_signal.get("source") or "").strip()
        declared = str(
            raw_signal.get("evidence_status") or "UNVERIFIED"
        ).strip().upper()
        reference = _inspect_reference(source, root)
        effective = declared
        reason = ""
        if (
            declared in _VERIFIED_STATUSES
            and reference["availability"] in _UNAVAILABLE_LOCAL_STATUSES
        ):
            effective = "UNVERIFIED"
            reason = "DECLARED_VERIFICATION_HAS_NO_AVAILABLE_SOURCE"
        signals.append(
            {
                "index": index,
                "name": str(raw_signal.get("name") or ""),
                "source": source,
                "declared_evidence_status": declared,
                "effective_evidence_status": effective,
                "downgraded": effective != declared,
                "reason": reason,
                **reference,
            }
        )

    source_documents = []
    for index, raw_document in enumerate(
        _mapping_list(config.get("source_documents"), "source_documents")
    ):
        path = str(raw_document.get("path") or "").strip()
        url = str(raw_document.get("url") or "").strip()
        local_reference = _inspect_reference(path, root)
        source_documents.append(
            {
                "index": index,
                "title": str(raw_document.get("title") or path or url),
                "path": path,
                "url": url,
                "local_reference": local_reference,
                "remote_reference": _inspect_reference(url, root),
                "availability": _document_availability(local_reference, url),
            }
        )

    company_assets = []
    company_summaries = []
    for company_index, company in enumerate(
        _mapping_list(config.get("companies"), "companies")
    ):
        company_id = str(company.get("company_id") or "").strip()
        assets = company.get("source_assets") or []
        if isinstance(assets, (str, bytes, bytearray)) or not isinstance(
            assets, Sequence
        ):
            raise SourceIntegrityError("company source_assets must be a string list")
        inspected_assets = []
        for asset_index, reference in enumerate(assets):
            inspected = {
                "company_id": company_id,
                "company_index": company_index,
                "asset_index": asset_index,
                **_inspect_reference(str(reference).strip(), root),
            }
            inspected_assets.append(inspected)
            company_assets.append(inspected)
        available_count = sum(
            1
            for item in inspected_assets
            if item.get("availability") == "AVAILABLE"
        )
        company_summaries.append(
            {
                "company_id": company_id,
                "company_index": company_index,
                "configured_count": len(inspected_assets),
                "available_count": available_count,
                "unavailable_count": len(inspected_assets) - available_count,
                "complete": bool(inspected_assets)
                and available_count == len(inspected_assets),
                "hard_gate_blocked": available_count == 0,
            }
        )

    local_references = [
        item
        for item in (
            [signal for signal in signals]
            + [document["local_reference"] for document in source_documents]
            + company_assets
        )
        if item.get("reference_kind") == "LOCAL_FILE"
    ]
    missing_count = sum(
        1 for item in local_references if item.get("availability") == "MISSING"
    )
    unavailable_count = sum(
        1
        for item in local_references
        if item.get("availability") != "AVAILABLE"
    )
    available_count = sum(
        1 for item in local_references if item.get("availability") == "AVAILABLE"
    )
    downgraded_count = sum(1 for signal in signals if signal["downgraded"])
    blocked_company_count = sum(
        1 for item in company_summaries if item["hard_gate_blocked"]
    )
    if (
        unavailable_count == 0
        and downgraded_count == 0
        and blocked_company_count == 0
    ):
        status = "READY"
    elif available_count:
        status = "PARTIAL"
    else:
        status = "INSUFFICIENT"

    normalized = {
        "schema_version": SOURCE_INTEGRITY_SCHEMA_VERSION,
        "report_id": str(report_id or "").strip(),
        "industry_id": industry_id,
        "as_of": as_of,
        "project_root": ".",
        "input_config_hash": _hash_payload(config),
        "status": status,
        "signals": signals,
        "source_documents": source_documents,
        "company_assets": company_assets,
        "company_summaries": company_summaries,
        "summary": {
            "signal_count": len(signals),
            "downgraded_signal_count": downgraded_count,
            "local_reference_count": len(local_references),
            "available_local_reference_count": available_count,
            "missing_local_reference_count": missing_count,
            "unavailable_local_reference_count": unavailable_count,
            "blocked_company_count": blocked_company_count,
        },
        "rule_version": SOURCE_INTEGRITY_RULE_VERSION,
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }
    normalized["report_id"] = normalized["report_id"] or (
        f"source-integrity-{_safe_id(industry_id)}-{_safe_id(as_of)}-"
        + _hash_payload(normalized)[:12]
    )
    normalized["content_hash"] = _hash_payload(normalized)
    return normalized


def apply_source_integrity(
    config: Mapping[str, Any],
    report: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a config copy with effective evidence and company gate statuses."""

    validated = validate_source_integrity_report(report)
    if str(config.get("industry_id") or "") != validated["industry_id"]:
        raise SourceIntegrityError("source integrity industry_id does not match config")
    if str(config.get("as_of") or "") != validated["as_of"]:
        raise SourceIntegrityError("source integrity as_of does not match config")
    if _hash_payload(config) != validated["input_config_hash"]:
        raise SourceIntegrityError(
            "source integrity input_config_hash does not match config"
        )
    adjusted = deepcopy(dict(config))
    raw_signals = adjusted.get("signals") or []
    for item in validated["signals"]:
        index = int(item["index"])
        if index >= len(raw_signals):
            raise SourceIntegrityError("source integrity signal index is out of range")
        signal = raw_signals[index]
        signal["declared_evidence_status"] = item["declared_evidence_status"]
        signal["evidence_status"] = item["effective_evidence_status"]
        signal["source_availability"] = item["availability"]
        if item["downgraded"]:
            note = str(signal.get("note") or "").strip()
            warning = "本地来源不可用，证据状态已自动降级。"
            signal["note"] = f"{note} {warning}".strip()

    raw_documents = adjusted.get("source_documents") or []
    for item in validated["source_documents"]:
        index = int(item["index"])
        if index >= len(raw_documents):
            raise SourceIntegrityError("source integrity document index is out of range")
        raw_documents[index]["availability_status"] = item["availability"]

    raw_companies = adjusted.get("companies") or []
    company_summaries = validated.get("company_summaries") or []
    if len(raw_companies) != len(company_summaries):
        raise SourceIntegrityError(
            "source integrity company count does not match config"
        )
    assets_by_company_index: dict[int, list[dict[str, Any]]] = {}
    for item in validated.get("company_assets") or []:
        assets_by_company_index.setdefault(int(item["company_index"]), []).append(
            dict(item)
        )
    for index, summary in enumerate(company_summaries):
        if int(summary.get("company_index", -1)) != index:
            raise SourceIntegrityError(
                "source integrity company index is out of order"
            )
        company = raw_companies[index]
        company["source_asset_status"] = sorted(
            assets_by_company_index.get(index, []),
            key=lambda item: int(item["asset_index"]),
        )
        company["source_asset_summary"] = dict(summary)
        if summary.get("hard_gate_blocked"):
            declared = str(company.get("hard_gate_status") or "PENDING").upper()
            company["declared_hard_gate_status"] = declared
            if declared not in {"BLOCKED", "REJECTED"}:
                company["hard_gate_status"] = "BLOCKED"
            blockers = list(company.get("source_integrity_blockers") or [])
            blocker = "NO_AVAILABLE_CONFIGURED_SOURCE_ASSET"
            if blocker not in blockers:
                blockers.append(blocker)
            company["source_integrity_blockers"] = blockers

    effective_verified = sum(
        1
        for item in validated["signals"]
        if item["effective_evidence_status"] in _VERIFIED_STATUSES
    )
    if validated["summary"]["downgraded_signal_count"]:
        adjusted["declared_evidence_completeness"] = str(
            adjusted.get("evidence_completeness") or "UNKNOWN"
        )
        adjusted["evidence_completeness"] = (
            "PARTIAL" if effective_verified else "INSUFFICIENT"
        )
    adjusted["source_integrity"] = {
        "report_id": validated["report_id"],
        "content_hash": validated["content_hash"],
        "status": validated["status"],
        **validated["summary"],
    }
    return adjusted


def validate_source_integrity_report(report: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(report, Mapping):
        raise SourceIntegrityError("source integrity report must be an object")
    if report.get("schema_version") != SOURCE_INTEGRITY_SCHEMA_VERSION:
        raise SourceIntegrityError(
            f"input must be {SOURCE_INTEGRITY_SCHEMA_VERSION}"
        )
    for field in (
        "report_id",
        "industry_id",
        "as_of",
        "input_config_hash",
        "rule_version",
        "content_hash",
    ):
        if not str(report.get(field) or "").strip():
            raise SourceIntegrityError(f"source integrity {field} is required")
    if report.get("immutable") is not True:
        raise SourceIntegrityError("source integrity report must be immutable")
    expected = _hash_payload(
        {key: value for key, value in report.items() if key != "content_hash"}
    )
    if str(report["content_hash"]) != expected:
        raise SourceIntegrityError("content_hash does not match source integrity report")
    return dict(report)


def _inspect_reference(reference: str, root: Path) -> dict[str, Any]:
    value = str(reference or "").strip()
    if not value:
        return {
            "reference": "",
            "reference_kind": "UNDECLARED",
            "availability": "UNDECLARED",
            "content_hash": "",
            "size_bytes": None,
        }
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"}:
        return {
            "reference": value,
            "reference_kind": "REMOTE_URL",
            "availability": "REMOTE_UNCHECKED",
            "content_hash": "",
            "size_bytes": None,
        }
    path = Path(value)
    try:
        resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    except (OSError, RuntimeError):
        return _unavailable_reference(value, "UNREADABLE")
    try:
        resolved.relative_to(root)
    except ValueError:
        return _unavailable_reference(value, "OUTSIDE_PROJECT")
    try:
        if not resolved.exists():
            return _unavailable_reference(value, "MISSING")
        if not resolved.is_file():
            return _unavailable_reference(value, "NOT_FILE")
        raw = resolved.read_bytes()
    except OSError:
        return _unavailable_reference(value, "UNREADABLE")
    if not raw:
        return _unavailable_reference(value, "EMPTY", size_bytes=0)
    return {
        "reference": value,
        "reference_kind": "LOCAL_FILE",
        "availability": "AVAILABLE",
        "content_hash": sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def _unavailable_reference(
    reference: str,
    availability: str,
    *,
    size_bytes: int | None = None,
) -> dict[str, Any]:
    return {
        "reference": reference,
        "reference_kind": "LOCAL_FILE",
        "availability": availability,
        "content_hash": "",
        "size_bytes": size_bytes,
    }


def _document_availability(local_reference: Mapping[str, Any], url: str) -> str:
    if local_reference.get("availability") == "AVAILABLE":
        return "AVAILABLE"
    if str(url or "").startswith(("http://", "https://")):
        return "REMOTE_UNCHECKED"
    return str(local_reference.get("availability") or "UNDECLARED")


def _mapping_list(value: Any, field: str) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise SourceIntegrityError(f"{field} must be an object list")
    if any(not isinstance(item, Mapping) for item in value):
        raise SourceIntegrityError(f"{field} must contain objects")
    return list(value)


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value).strip("-")


def _hash_payload(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return sha256(encoded.encode("utf-8")).hexdigest()
