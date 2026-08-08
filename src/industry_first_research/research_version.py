"""Immutable research-version manifests and read-only replay helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
import hashlib
import json
from typing import Any


RESEARCH_VERSION_SCHEMA_VERSION = "research-version.v1"
RESEARCH_VERSION_RULE_VERSION = "research-version-rules.v1"
VERSION_COMPARISON_SCHEMA_VERSION = "research-version-manifest-comparison.v1"
VERSION_REPLAY_SCHEMA_VERSION = "research-version-replay.v1"

_SUBJECT_TYPES = {
    "listed_company",
    "industry",
    "futures_variety",
    "futures_contract",
    "opportunity_scan",
    "mixed",
}
_EXECUTION_MODES = {"LOCAL_ONLY", "LLM_ASSISTED", "MANUAL_WEB_AI"}
_VERSION_STATUSES = {"DRAFT", "REVIEW_REQUIRED", "VALID", "SUPERSEDED", "BLOCKED"}
_REVIEW_STATUSES = {"NOT_REVIEWED", "REVIEW_REQUIRED", "REVIEWED", "USER_CONFIRMED"}


class ResearchVersionError(ValueError):
    """Raised when a research-version manifest cannot be trusted."""


def build_research_version(
    payload: Mapping[str, Any],
    *,
    version_id: str = "",
    created_at: str = "",
) -> dict[str, Any]:
    """Build one immutable manifest without copying the referenced artifacts."""

    if not isinstance(payload, Mapping):
        raise ResearchVersionError("research version input must be a JSON object")
    subject_type = str(payload.get("subject_type") or "").strip().lower()
    if subject_type not in _SUBJECT_TYPES:
        raise ResearchVersionError(
            f"unsupported subject_type: {subject_type or '<empty>'}"
        )
    subject_ids = _string_list(payload.get("subject_ids"))
    if not subject_ids and str(payload.get("subject_id") or "").strip():
        subject_ids = [str(payload["subject_id"]).strip()]
    if not subject_ids:
        raise ResearchVersionError("subject_ids or subject_id is required")
    research_as_of = str(
        payload.get("research_as_of") or payload.get("as_of") or ""
    ).strip()
    if not research_as_of:
        raise ResearchVersionError("research_as_of is required")
    _parse_date(research_as_of, "research_as_of")

    execution_mode = str(payload.get("execution_mode") or "LOCAL_ONLY").strip().upper()
    if execution_mode not in _EXECUTION_MODES:
        raise ResearchVersionError(
            "execution_mode must be LOCAL_ONLY, LLM_ASSISTED, or MANUAL_WEB_AI"
        )
    status = str(payload.get("version_status") or "REVIEW_REQUIRED").strip().upper()
    if status not in _VERSION_STATUSES:
        raise ResearchVersionError(f"unsupported version_status: {status}")
    review_status = str(payload.get("review_status") or "NOT_REVIEWED").strip().upper()
    if review_status not in _REVIEW_STATUSES:
        raise ResearchVersionError(f"unsupported review_status: {review_status}")

    previous_version_id = str(payload.get("previous_version_id") or "").strip()
    if previous_version_id and previous_version_id == str(version_id or "").strip():
        raise ResearchVersionError("a research version cannot point to itself")
    normalized_created_at = str(created_at or payload.get("created_at") or "").strip()
    if not normalized_created_at:
        normalized_created_at = datetime.now(timezone.utc).isoformat()
    _parse_datetime(normalized_created_at, "created_at")

    artifact_refs = _artifact_refs(payload.get("artifact_refs"))
    normalized = {
        "schema_version": RESEARCH_VERSION_SCHEMA_VERSION,
        "version_id": str(version_id or "").strip(),
        "previous_version_id": previous_version_id,
        "subject_type": subject_type,
        "subject_ids": subject_ids,
        "research_as_of": research_as_of,
        "created_at": normalized_created_at,
        "execution_mode": execution_mode,
        "affected_modules": _string_list(payload.get("affected_modules")),
        "pipeline_id": str(payload.get("pipeline_id") or "").strip(),
        "supplemental_id": str(payload.get("supplemental_id") or "").strip(),
        "evidence_bundle_id": str(payload.get("evidence_bundle_id") or "").strip(),
        "evidence_manifest_hash": str(
            payload.get("evidence_manifest_hash") or ""
        ).strip(),
        "source_health_snapshot_id": str(
            payload.get("source_health_snapshot_id") or ""
        ).strip(),
        "company_scope_ids": _string_list(payload.get("company_scope_ids")),
        "market_data_snapshot_ids": _string_list(
            payload.get("market_data_snapshot_ids")
        ),
        "artifact_refs": artifact_refs,
        "source_ids": _string_list(payload.get("source_ids")),
        "rule_versions": _string_mapping(payload.get("rule_versions")),
        "version_status": status,
        "review_status": review_status,
        "review_reason": str(payload.get("review_reason") or ""),
        "replayable": bool(payload.get("replayable", True)),
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "rule_version": RESEARCH_VERSION_RULE_VERSION,
    }
    normalized["version_id"] = normalized["version_id"] or _version_id(normalized)
    if previous_version_id and previous_version_id == normalized["version_id"]:
        raise ResearchVersionError("a research version cannot point to itself")
    normalized["content_hash"] = _content_hash(normalized)
    return normalized


def validate_research_version(version: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an existing manifest, including its content hash."""

    if not isinstance(version, Mapping):
        raise ResearchVersionError("research version must be a JSON object")
    if version.get("schema_version") != RESEARCH_VERSION_SCHEMA_VERSION:
        raise ResearchVersionError(
            f"input must be {RESEARCH_VERSION_SCHEMA_VERSION}"
        )
    if not str(version.get("version_id") or "").strip():
        raise ResearchVersionError("version_id is required")
    if version.get("immutable") is not True:
        raise ResearchVersionError("research version must be immutable")
    rebuilt = build_research_version(
        version,
        version_id=str(version["version_id"]),
        created_at=str(version.get("created_at") or ""),
    )
    if str(version.get("content_hash") or "") != rebuilt["content_hash"]:
        raise ResearchVersionError("content_hash does not match research version")
    if str(version.get("version_id")) != rebuilt["version_id"]:
        raise ResearchVersionError("version_id does not match normalized research version")
    return dict(version)


def build_research_version_from_pipeline(
    pipeline: Mapping[str, Any],
    *,
    supplemental: Mapping[str, Any] | None = None,
    evidence_bundle: Mapping[str, Any] | None = None,
    product_profit_bridge_report: Mapping[str, Any] | None = None,
    product_lifecycle_report: Mapping[str, Any] | None = None,
    financial_model_report: Mapping[str, Any] | None = None,
    previous_version_id: str = "",
    execution_mode: str = "LOCAL_ONLY",
    affected_modules: Sequence[str] = (),
    version_id: str = "",
    created_at: str = "",
) -> dict[str, Any]:
    """Create a manifest for a company pipeline and its optional evidence inputs."""

    _validate_pipeline(pipeline)
    pipeline_id = str(pipeline.get("pipeline_id") or "").strip()
    supplemental_id = str(
        supplemental.get("report_id") if isinstance(supplemental, Mapping) else ""
    ).strip() or str(pipeline.get("input_supplemental_id") or "").strip()
    subject_ids = _pipeline_subject_ids(pipeline)
    if not subject_ids:
        raise ResearchVersionError("pipeline has no company subjects")
    artifact_refs = [
        _artifact_ref(
            "pipeline",
            pipeline_id,
            pipeline,
            as_of=str(pipeline.get("as_of") or ""),
        )
    ]
    if isinstance(supplemental, Mapping):
        artifact_refs.append(
            _artifact_ref(
                "supplemental",
                supplemental_id or "supplemental-input",
                supplemental,
                as_of=str(supplemental.get("as_of") or ""),
            )
        )
    if isinstance(evidence_bundle, Mapping):
        bundle_id = str(evidence_bundle.get("bundle_id") or "").strip()
        if bundle_id:
            artifact_refs.append(
                _artifact_ref(
                    "evidence_bundle",
                    bundle_id,
                    evidence_bundle,
                    as_of=str(evidence_bundle.get("research_as_of") or ""),
                )
            )
    if isinstance(product_profit_bridge_report, Mapping):
        bridge_id = str(product_profit_bridge_report.get("report_id") or "").strip()
        if bridge_id:
            artifact_refs.append(
                _artifact_ref(
                    "product_profit_bridge",
                    bridge_id,
                    product_profit_bridge_report,
                    as_of=str(product_profit_bridge_report.get("as_of") or ""),
                )
            )
    if isinstance(product_lifecycle_report, Mapping):
        lifecycle_id = str(product_lifecycle_report.get("report_id") or "").strip()
        if lifecycle_id:
            artifact_refs.append(
                _artifact_ref(
                    "product_lifecycle",
                    lifecycle_id,
                    product_lifecycle_report,
                    as_of=str(product_lifecycle_report.get("as_of") or ""),
                )
            )
    if isinstance(financial_model_report, Mapping):
        financial_id = str(financial_model_report.get("report_id") or "").strip()
        if financial_id:
            artifact_refs.append(
                _artifact_ref(
                    "financial_model",
                    financial_id,
                    financial_model_report,
                    as_of=str(financial_model_report.get("as_of") or ""),
                )
            )
    subject_type = str(pipeline.get("subject_type") or "listed_company").lower()
    if subject_type not in _SUBJECT_TYPES:
        subject_type = "listed_company"
    return build_research_version(
        {
            "subject_type": subject_type,
            "subject_ids": subject_ids,
            "research_as_of": str(pipeline.get("as_of") or ""),
            "previous_version_id": previous_version_id,
            "execution_mode": execution_mode,
            "affected_modules": list(affected_modules),
            "pipeline_id": pipeline_id,
            "supplemental_id": supplemental_id,
            "evidence_bundle_id": str(pipeline.get("evidence_bundle_id") or ""),
            "evidence_manifest_hash": str(
                pipeline.get("evidence_manifest_hash") or ""
            ),
            "source_health_snapshot_id": str(
                pipeline.get("source_health_snapshot_id") or ""
            ),
            "company_scope_ids": pipeline.get("company_scope_ids") or [],
            "market_data_snapshot_ids": [
                str(pipeline.get("market_data_snapshot_id") or "")
            ]
            if str(pipeline.get("market_data_snapshot_id") or "")
            else [],
            "artifact_refs": artifact_refs,
            "source_ids": [str(pipeline.get("source") or "")]
            if str(pipeline.get("source") or "")
            else [],
            "rule_versions": {"pipeline": str(pipeline.get("rule_version") or "")},
            "version_status": "REVIEW_REQUIRED",
            "review_status": "NOT_REVIEWED",
            "replayable": True,
        },
        version_id=version_id,
        created_at=created_at,
    )


def build_research_version_comparison(
    previous: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, Any]:
    """Compare manifests without rewriting either historical version."""

    validate_research_version(previous)
    validate_research_version(current)
    changed_fields = []
    for field in sorted(set(previous) | set(current)):
        if field in {"version_id", "created_at", "content_hash"}:
            continue
        if _stable_digest(previous.get(field)) != _stable_digest(current.get(field)):
            changed_fields.append(field)
    reference_changes = _reference_changes(previous, current)
    status_changes = []
    for field in ("version_status", "review_status", "execution_mode"):
        old = previous.get(field)
        new = current.get(field)
        if old != new:
            status_changes.append({"field": field, "old": old, "current": new})
    return {
        "schema_version": VERSION_COMPARISON_SCHEMA_VERSION,
        "comparison_id": "research-version-comparison-"
        + _stable_digest([previous["version_id"], current["version_id"]])[:16],
        "previous_version_id": str(previous["version_id"]),
        "current_version_id": str(current["version_id"]),
        "previous_as_of": str(previous.get("research_as_of") or ""),
        "current_as_of": str(current.get("research_as_of") or ""),
        "changed_fields": changed_fields,
        "status_changes": status_changes,
        "reference_changes": reference_changes,
        "requires_review": bool(changed_fields or status_changes or reference_changes),
        "policy": {
            "old_version_preserved": True,
            "automatic_directional_conclusion": False,
            "automatic_decision_snapshot": False,
            "read_only": True,
            "review_only": True,
        },
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def build_research_version_replay(
    version: Mapping[str, Any],
    artifacts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Resolve a manifest for deterministic local replay; never fetches or mutates."""

    validated = validate_research_version(version)
    supplied = _supplied_artifacts(artifacts)
    checks = []
    blocked = False
    for reference in validated.get("artifact_refs") or []:
        artifact_id = str(reference["artifact_id"])
        artifact = supplied.get(artifact_id)
        if artifact is None:
            checks.append(
                {
                    "artifact_id": artifact_id,
                    "artifact_type": reference["artifact_type"],
                    "status": "NOT_SUPPLIED",
                }
            )
            continue
        expected_hash = str(reference.get("content_hash") or "")
        actual_hash = str(artifact.get("content_hash") or "")
        if not actual_hash and isinstance(artifact.get("payload"), Mapping):
            actual_hash = _stable_digest(
                _artifact_payload(reference["artifact_type"], artifact["payload"])
            )
        status = "VERIFIED" if not expected_hash or expected_hash == actual_hash else "CONFLICTING"
        if status == "CONFLICTING":
            blocked = True
        artifact_as_of = str(artifact.get("as_of") or "")
        if artifact_as_of and _parse_date(artifact_as_of, "artifact.as_of") > _parse_date(
            str(validated["research_as_of"]), "research_as_of"
        ):
            status = "FUTURE_DATA_BLOCKED"
            blocked = True
        checks.append(
            {
                "artifact_id": artifact_id,
                "artifact_type": reference["artifact_type"],
                "status": status,
                "expected_content_hash": expected_hash,
                "actual_content_hash": actual_hash,
            }
        )
    supplied_extra = sorted(set(supplied) - {str(ref["artifact_id"]) for ref in validated.get("artifact_refs") or []})
    return {
        "schema_version": VERSION_REPLAY_SCHEMA_VERSION,
        "replay_id": "research-version-replay-" + str(validated["version_id"]),
        "version_id": str(validated["version_id"]),
        "research_as_of": str(validated["research_as_of"]),
        "execution_mode": "LOCAL_ONLY",
        "status": "BLOCKED" if blocked else "READY" if supplied else "REFERENCE_ONLY",
        "artifact_checks": checks,
        "unspecified_artifacts": supplied_extra,
        "replay_steps": [
            "load_manifest",
            "resolve_referenced_artifacts",
            "validate_content_hashes_and_cutoff",
            "rerun_only_deterministic_local_modules",
            "compare_replayed_output_with_locked_version",
        ],
        "model_calls": 0,
        "network_calls": 0,
        "mutated_historical_objects": False,
        "policy": {
            "read_only": True,
            "no_external_fetch": True,
            "no_model_call": True,
            "no_directional_conclusion": True,
            "no_decision_snapshot": True,
        },
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _validate_pipeline(pipeline: Mapping[str, Any]) -> None:
    if not isinstance(pipeline, Mapping):
        raise ResearchVersionError("pipeline must be a JSON object")
    if pipeline.get("schema_version") != "company-research-pipeline.v1":
        raise ResearchVersionError("pipeline must be company-research-pipeline.v1")
    if not str(pipeline.get("pipeline_id") or "").strip():
        raise ResearchVersionError("pipeline_id is required")
    if not str(pipeline.get("as_of") or "").strip():
        raise ResearchVersionError("pipeline.as_of is required")
    _parse_date(str(pipeline["as_of"]), "pipeline.as_of")
    if not isinstance(pipeline.get("stages"), Mapping):
        raise ResearchVersionError("pipeline.stages must be an object")


def _pipeline_subject_ids(pipeline: Mapping[str, Any]) -> list[str]:
    ids: set[str] = set()
    for stage in (pipeline.get("stages") or {}).values():
        if not isinstance(stage, Mapping):
            continue
        for item in stage.get("items") or []:
            if isinstance(item, Mapping) and str(item.get("company_id") or "").strip():
                ids.add(str(item["company_id"]).strip())
    return sorted(ids)


def _artifact_refs(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ResearchVersionError("artifact_refs must be a list")
    result = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ResearchVersionError("each artifact_ref must be an object")
        artifact_id = str(raw.get("artifact_id") or "").strip()
        artifact_type = str(raw.get("artifact_type") or "").strip()
        if not artifact_id or not artifact_type:
            raise ResearchVersionError("artifact_ref requires artifact_id and artifact_type")
        if artifact_id in seen:
            raise ResearchVersionError(f"duplicate artifact_id: {artifact_id}")
        seen.add(artifact_id)
        ref = {
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "as_of": str(raw.get("as_of") or ""),
            "content_hash": str(raw.get("content_hash") or ""),
            "uri": str(raw.get("uri") or raw.get("path") or ""),
        }
        if ref["as_of"]:
            _parse_date(ref["as_of"], f"artifact_refs[{artifact_id}].as_of")
        if ref["content_hash"] and not _is_sha256(ref["content_hash"]):
            raise ResearchVersionError(f"artifact content_hash must be SHA-256: {artifact_id}")
        result.append(ref)
    return result


def _artifact_ref(artifact_type: str, artifact_id: str, payload: Mapping[str, Any], *, as_of: str) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "as_of": as_of,
        "content_hash": _stable_digest(_artifact_payload(artifact_type, payload)),
        "uri": "",
    }


def _artifact_payload(artifact_type: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Exclude the back-reference that is added after the manifest is built."""

    return {
        key: value for key, value in payload.items() if key != "research_version_id"
    }


def _supplied_artifacts(artifacts: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    if isinstance(artifacts, (str, bytes, bytearray)):
        raise ResearchVersionError("artifacts must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            raise ResearchVersionError("each supplied artifact must be an object")
        artifact_id = str(artifact.get("artifact_id") or "").strip()
        if not artifact_id:
            raise ResearchVersionError("supplied artifact_id is required")
        if artifact_id in result:
            raise ResearchVersionError(f"duplicate supplied artifact_id: {artifact_id}")
        result[artifact_id] = artifact
    return result


def _reference_changes(previous: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    old = {str(item["artifact_id"]): item for item in previous.get("artifact_refs") or []}
    new = {str(item["artifact_id"]): item for item in current.get("artifact_refs") or []}
    return {
        "added": sorted(set(new) - set(old)),
        "removed": sorted(set(old) - set(new)),
        "modified": sorted(
            artifact_id
            for artifact_id in set(old) & set(new)
            if _stable_digest(old[artifact_id]) != _stable_digest(new[artifact_id])
        ),
    }


def _version_id(value: Mapping[str, Any]) -> str:
    return "research-version-" + _stable_digest(
        {
            key: item
            for key, item in value.items()
            if key not in {"version_id", "content_hash", "created_at"}
        }
    )[:20]


def _content_hash(value: Mapping[str, Any]) -> str:
    return _stable_digest(
        {key: item for key, item in value.items() if key not in {"content_hash"}}
    )


def _stable_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ResearchVersionError("expected a string list")
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _string_mapping(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ResearchVersionError("rule_versions must be an object")
    return {
        str(key).strip(): str(item).strip()
        for key, item in value.items()
        if str(key).strip() and str(item).strip()
    }


def _parse_date(value: str, field: str) -> date:
    text = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise ResearchVersionError(f"{field} must be an ISO date or datetime") from error


def _parse_datetime(value: str, field: str) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError as error:
        raise ResearchVersionError(f"{field} must be an ISO datetime") from error


def _is_sha256(value: str) -> bool:
    text = str(value).lower()
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)
