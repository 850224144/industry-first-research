"""One-way public-draft generation with explicit human-review boundaries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import hashlib
import json
import re
from typing import Any

from .report_rendering import render_research_markdown


PUBLIC_DRAFT_SCHEMA_VERSION = "public-draft.v1"
PUBLIC_DRAFT_RULE_VERSION = "public-draft-rules.v1"
_LOCKED_STATUSES = {"LOCKED", "USER_CONFIRMED"}
_FORBIDDEN_TERMS = (
    "目标价",
    "预期收益",
    "仓位",
    "买入",
    "卖出",
    "建仓",
    "减仓",
    "止损",
    "账户",
    "实盘",
    "模拟仓",
)
_PRIVATE_KEY_PARTS = (
    "target_price",
    "target_value",
    "expected_return",
    "position",
    "simulated_price",
    "simulated_quantity",
    "executed_at",
    "decision_snapshot",
    "simulation_record",
    "account",
    "private_note",
    "personal_note",
    "broker",
    "order",
    "trade_time",
    "buy_price",
    "sell_price",
    "目标价",
    "预期收益",
    "仓位",
    "账户",
    "个人备注",
    "模拟仓",
)


class PublicDraftError(ValueError):
    """Raised when a public draft cannot be safely generated or validated."""


def build_public_draft(
    source_report: Mapping[str, Any],
    source_lock: Mapping[str, Any],
    *,
    channel: str = "wechat_public_draft",
    title: str = "",
    draft_version: int = 1,
    public_draft_id: str = "",
) -> dict[str, Any]:
    """Create a redacted, non-publishable draft from a hash-locked report."""

    if not isinstance(source_report, Mapping):
        raise PublicDraftError("source_report must be an object")
    if not isinstance(source_lock, Mapping):
        raise PublicDraftError("source_lock must be an object")
    _validate_lock(source_report, source_lock)
    if not str(channel).strip():
        raise PublicDraftError("channel must not be empty")
    if int(draft_version) <= 0:
        raise PublicDraftError("draft_version must be positive")

    source_hash = _hash(source_report)
    redacted, removed = _redact(source_report)
    rendered = render_research_markdown(redacted, title=title)
    compliance = _compliance_check(rendered)
    source_check = _source_check(source_report)
    copyright_check = {
        "status": "MANUAL_REVIEW_REQUIRED",
        "reason": "来源图片、表格、第三方文本和平台版权不能由本地规则自动授权",
    }
    safe_title = title.strip() or _default_title(source_report)
    overall_status = "BLOCKED" if compliance["status"] == "BLOCKED" else "READY_FOR_HUMAN_REVIEW"
    identifier = (
        str(public_draft_id).strip()
        or "public-draft-"
        + _hash({"source": source_hash, "channel": channel, "version": draft_version, "title": safe_title})[:20]
    )
    draft = {
        "schema_version": PUBLIC_DRAFT_SCHEMA_VERSION,
        "public_draft_id": identifier,
        "rule_version": PUBLIC_DRAFT_RULE_VERSION,
        "source_research_id": str(
            source_lock.get("source_research_id")
            or source_report.get("research_version_id")
            or source_report.get("report_id")
            or source_report.get("tracking_id")
            or ""
        ),
        "source_report_hash": source_hash,
        "source_lock_status": str(source_lock.get("status") or "").upper(),
        "channel": str(channel),
        "draft_version": int(draft_version),
        "title": safe_title,
        "content": rendered,
        "content_hash": _hash(rendered),
        "removed_private_fields": removed,
        "compliance_check": compliance,
        "source_check": source_check,
        "copyright_check": copyright_check,
        "review_status": "NEEDS_HUMAN_REVIEW" if overall_status != "BLOCKED" else "BLOCKED",
        "reviewed_by": "",
        "reviewed_at": "",
        "publication_status": "NOT_PUBLISHED",
        "status": overall_status,
        "policy": {
            "one_way_from_locked_report": True,
            "private_fields_removed": True,
            "human_review_required": True,
            "publication_api_called": False,
            "automatic_publication": False,
            "source_report_unchanged": True,
            "research_conclusion_changed": False,
            "decision_snapshot_changed": False,
            "read_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "execution_enabled": False,
    }
    return draft


def validate_public_draft(draft: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a generated draft and ensure its content hash is intact."""

    if not isinstance(draft, Mapping) or draft.get("schema_version") != PUBLIC_DRAFT_SCHEMA_VERSION:
        raise PublicDraftError(f"input must be {PUBLIC_DRAFT_SCHEMA_VERSION}")
    if not str(draft.get("public_draft_id") or "").strip():
        raise PublicDraftError("public_draft_id is required")
    content = str(draft.get("content") or "")
    if str(draft.get("content_hash") or "") != _hash(content):
        raise PublicDraftError("content_hash does not match content")
    if draft.get("publication_status") != "NOT_PUBLISHED":
        raise PublicDraftError("public draft validator does not accept published status")
    policy = draft.get("policy")
    if not isinstance(policy, Mapping):
        raise PublicDraftError("policy must be an object")
    if policy.get("publication_api_called") is not False:
        raise PublicDraftError("publication_api_called must remain false")
    if policy.get("automatic_publication") is not False:
        raise PublicDraftError("automatic_publication must remain false")
    if policy.get("source_report_unchanged") is not True:
        raise PublicDraftError("source_report_unchanged must remain true")
    if policy.get("research_conclusion_changed") is not False:
        raise PublicDraftError("research_conclusion_changed must remain false")
    if policy.get("decision_snapshot_changed") is not False:
        raise PublicDraftError("decision_snapshot_changed must remain false")
    if draft.get("read_only") is not True or draft.get("execution_enabled") is not False:
        raise PublicDraftError("public draft must remain read-only and execution-disabled")
    return dict(draft)


def _validate_lock(report: Mapping[str, Any], lock: Mapping[str, Any]) -> None:
    status = str(lock.get("status") or lock.get("review_status") or "").upper()
    if status not in _LOCKED_STATUSES:
        raise PublicDraftError("source report must have an explicit LOCKED or USER_CONFIRMED lock")
    expected = str(lock.get("source_report_hash") or lock.get("content_hash") or "")
    if not expected:
        raise PublicDraftError("source lock must include source_report_hash")
    actual = _hash(report)
    if expected != actual:
        raise PublicDraftError("source lock hash does not match source report")


def _redact(value: Any, path: str = "source") -> tuple[Any, list[str]]:
    removed: list[str] = []
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_private_key(key_text):
                removed.append(f"{path}.{key_text}")
                continue
            cleaned, nested = _redact(item, f"{path}.{key_text}")
            output[key_text] = cleaned
            removed.extend(nested)
        return output, removed
    if isinstance(value, list):
        output = []
        for index, item in enumerate(value):
            cleaned, nested = _redact(item, f"{path}[{index}]")
            output.append(cleaned)
            removed.extend(nested)
        return output, removed
    return deepcopy(value), removed


def _is_private_key(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", value.casefold()).strip("_")
    segments = set(filter(None, normalized.split("_")))
    for part in _PRIVATE_KEY_PARTS:
        normalized_part = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", part.casefold()).strip("_")
        if any("\u4e00" <= char <= "\u9fff" for char in normalized_part):
            if normalized_part in value:
                return True
        elif "_" in normalized_part:
            if normalized == normalized_part or normalized.startswith(normalized_part + "_"):
                return True
        elif normalized_part in segments:
            return True
    return False


def _compliance_check(content: str) -> dict[str, Any]:
    hits = sorted({term for term in _FORBIDDEN_TERMS if term in content})
    return {
        "status": "BLOCKED" if hits else "PASS",
        "forbidden_terms": hits,
        "reason": "公开稿含私人交易或收益表达，必须人工修改" if hits else "未发现规则禁止表达；仍需人工审核",
    }


def _source_check(report: Mapping[str, Any]) -> dict[str, Any]:
    sources = _collect_sources(report)
    return {
        "status": "PASS" if sources else "REVIEW_REQUIRED",
        "source_count": len(sources),
        "sources": sources,
        "reason": "来源字段已保留" if sources else "没有结构化来源字段，必须人工补充公开来源",
    }


def _collect_sources(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).casefold() in {"source", "source_url", "source_urls", "sources", "source_refs"}:
                values = item if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)) else [item]
                found.extend(str(candidate) for candidate in values if str(candidate).strip())
            else:
                found.extend(_collect_sources(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_collect_sources(item))
    return list(dict.fromkeys(found))


def _default_title(report: Mapping[str, Any]) -> str:
    schema = str(report.get("schema_version") or "")
    if schema == "futures-fundamentals-report.v1":
        return f"{report.get('variety_name') or report.get('variety_id') or '期货'}研究摘要"
    if schema == "futures-fundamentals-tracking.v1":
        return f"{report.get('subject', {}).get('variety_id') or '期货'}跟踪摘要"
    return "研究摘要"


def _hash(value: Any) -> str:
    if isinstance(value, str):
        encoded = value.encode("utf-8")
    else:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
