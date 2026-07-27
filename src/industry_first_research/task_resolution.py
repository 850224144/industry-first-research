"""Resolve user research input into a safe, serialisable task envelope.

The resolver classifies input locally. It does not query a remote security
master, infer a listing market from a bare code, call a model, or enable
execution. An explicitly supplied local security-master snapshot may provide
an exact identity match; all other confirmation remains the responsibility of
the appropriate research adapter and its evidence sources.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
import hashlib
import json
import re
from typing import Any

from .security_master import SecurityMasterError, lookup_security_master_company


TASK_RESOLUTION_SCHEMA_VERSION = "research-task-resolution.v1"
TASK_RESOLUTION_RULE_VERSION = "research-task-resolution-rules.v1"

_TASK_TYPES = {
    "company_research",
    "industry_research",
    "futures_research",
    "opportunity_discovery",
    "thesis_check",
    "public_draft",
    "unresolved",
}
_SUBJECT_TYPES = {
    "listed_company",
    "industry",
    "opportunity_scan",
    "futures_variety",
    "futures_contract",
    "continuous_series",
    "unknown",
}
_DEPTHS = {"QUICK", "STANDARD", "DEEP"}
_STATUSES = {"READY", "PARTIAL", "NEEDS_CONFIRMATION", "BLOCKED"}
_COMPANY_CODE_RE = re.compile(r"^(?:\d{6}(?:\.(?:SH|SZ|BJ))?|\d{4,5}\.HK)$", re.I)
_FUTURES_CONTRACT_RE = re.compile(r"^[A-Z]{1,4}\d{3,4}$", re.I)
_FUTURES_CONTINUOUS_RE = re.compile(
    r"(?:主力|连续|continuous|main|888|999)$", re.I
)


class TaskResolutionError(ValueError):
    """Raised when a research task cannot be normalised safely."""


def resolve_research_task(
    payload: Mapping[str, Any] | str,
    *,
    task_type: str = "",
    subject_type: str = "",
    research_as_of: str = "",
    requested_depth: str = "STANDARD",
    simulation_mode: bool = True,
    risk_preference: str = "",
    confirmed: bool = False,
    task_id: str = "",
    security_master: Mapping[str, Any] | None = None,
    commodity_definitions: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Resolve one input without making network, model, or execution calls."""

    raw = _normalise_payload(payload)
    input_text = str(
        raw.get("input")
        or raw.get("identifier")
        or raw.get("query")
        or raw.get("text")
        or ""
    ).strip()
    explicit_task = str(task_type or raw.get("task_type") or "").strip().lower()
    explicit_subject = str(subject_type or raw.get("subject_type") or "").strip().lower()
    depth = str(requested_depth or raw.get("requested_depth") or "STANDARD").strip().upper()
    if depth not in _DEPTHS:
        raise TaskResolutionError("requested_depth must be QUICK, STANDARD, or DEEP")
    if raw.get("execution_enabled") is True:
        raise TaskResolutionError("execution_enabled is permanently false")

    commodity_match = _match_commodity(input_text, commodity_definitions)
    resolved_task_type = _task_type(explicit_task, input_text, commodity_match)
    if resolved_task_type not in _TASK_TYPES:
        raise TaskResolutionError(f"unsupported task_type: {resolved_task_type}")
    normalized_input = _normalise_identifier(input_text)
    security_master_match = None
    if (
        security_master is not None
        and resolved_task_type in {"company_research", "thesis_check"}
        and normalized_input
    ):
        try:
            security_master_match = lookup_security_master_company(
                security_master, normalized_input
            )
        except SecurityMasterError as error:
            raise TaskResolutionError(str(error)) from error
    resolved_subject, identity = _resolve_subject(
        resolved_task_type,
        normalized_input,
        explicit_subject,
        raw,
        confirmed=confirmed or bool(raw.get("confirmed")),
        security_master_match=security_master_match,
        commodity_match=commodity_match,
    )
    if resolved_subject not in _SUBJECT_TYPES:
        raise TaskResolutionError(f"unsupported subject_type: {resolved_subject}")

    status, reasons, missing = _status_for(
        resolved_task_type,
        resolved_subject,
        identity,
        raw,
    )
    if confirmed and status == "NEEDS_CONFIRMATION" and identity.get("resolution_state") == "NAME_MATCH_REQUIRED":
        reasons.append("用户已标记确认，但本地没有可核验的候选身份")

    as_of = _as_of(research_as_of or raw.get("research_as_of") or raw.get("as_of"))
    normalized = {
        "schema_version": TASK_RESOLUTION_SCHEMA_VERSION,
        "task_id": str(task_id or "").strip(),
        "task_type": resolved_task_type,
        "subject_type": resolved_subject,
        "identifier": normalized_input,
        "display_name": str(raw.get("display_name") or "").strip(),
        "research_as_of": as_of,
        "simulation_mode": bool(simulation_mode if "simulation_mode" not in raw else raw["simulation_mode"]),
        "execution_enabled": False,
        "requested_depth": depth,
        "risk_preference": str(risk_preference or raw.get("risk_preference") or "").strip(),
        "status": status,
        "identity_resolution": identity,
        "security_master_match": security_master_match,
        "commodity_match": commodity_match,
        "candidates": _candidate_list(raw.get("candidates")),
        "reasons": list(dict.fromkeys(reasons)),
        "missing_fields": list(dict.fromkeys(missing)),
        "rule_version": TASK_RESOLUTION_RULE_VERSION,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "local_classification_only": True,
            "security_master_lookup_performed": security_master is not None,
            "bare_code_market_not_inferred": True,
            "execution_enabled_fixed_false": True,
            "model_calls": 0,
            "network_calls": 0,
            "read_only": True,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
        },
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }
    normalized["task_id"] = normalized["task_id"] or (
        "research-task-" + _hash_payload(_hashable_payload(normalized))[:20]
    )
    normalized["content_hash"] = _hash_payload(
        {key: value for key, value in normalized.items() if key != "content_hash"}
    )
    return normalized


def validate_research_task(task: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an immutable task envelope and its content hash."""

    if not isinstance(task, Mapping):
        raise TaskResolutionError("research task must be an object")
    if task.get("schema_version") != TASK_RESOLUTION_SCHEMA_VERSION:
        raise TaskResolutionError(f"input must be {TASK_RESOLUTION_SCHEMA_VERSION}")
    for field in ("task_id", "task_type", "subject_type", "research_as_of", "content_hash"):
        if not str(task.get(field) or "").strip():
            raise TaskResolutionError(f"research task {field} is required")
    if task.get("immutable") is not True or task.get("execution_enabled") is not False:
        raise TaskResolutionError("research task safety flags are invalid")
    if task.get("task_type") not in _TASK_TYPES:
        raise TaskResolutionError("research task has unsupported task_type")
    if task.get("subject_type") not in _SUBJECT_TYPES:
        raise TaskResolutionError("research task has unsupported subject_type")
    _parse_date(str(task["research_as_of"]), "research_as_of")
    expected = _hash_payload(
        {key: value for key, value in task.items() if key != "content_hash"}
    )
    if str(task["content_hash"]) != expected:
        raise TaskResolutionError("content_hash does not match research task")
    return dict(task)


def _normalise_payload(payload: Mapping[str, Any] | str) -> dict[str, Any]:
    if isinstance(payload, str):
        return {"input": payload}
    if not isinstance(payload, Mapping):
        raise TaskResolutionError("task input must be text or an object")
    return dict(payload)


def _task_type(
    explicit: str, text: str, commodity_match: Mapping[str, Any] | None = None
) -> str:
    if explicit:
        aliases = {
            "company": "company_research",
            "industry": "industry_research",
            "futures": "futures_research",
            "opportunity": "opportunity_discovery",
            "discover": "opportunity_discovery",
            "thesis": "thesis_check",
        }
        return aliases.get(explicit, explicit)
    lower = text.lower()
    if any(token in lower for token in ("发现机会", "主动发现", "机会扫描", "opportunity")):
        return "opportunity_discovery"
    if any(token in lower for token in ("持有论文", "论文检查", "thesis", "复查论文")):
        return "thesis_check"
    if commodity_match is not None:
        return "futures_research"
    if any(token in lower for token in ("行业", "产业链")):
        return "industry_research"
    if _COMPANY_CODE_RE.match(_normalise_identifier(text)):
        return "company_research"
    if _FUTURES_CONTRACT_RE.match(_normalise_identifier(text)) or _FUTURES_CONTINUOUS_RE.search(text):
        return "futures_research"
    return "unresolved"


def _resolve_subject(
    task_type: str,
    identifier: str,
    explicit_subject: str,
    raw: Mapping[str, Any],
    *,
    confirmed: bool,
    security_master_match: Mapping[str, Any] | None,
    commodity_match: Mapping[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    subject_aliases = {
        "company": "listed_company",
        "stock": "listed_company",
        "industry_research": "industry",
        "futures": "futures_variety",
        "contract": "futures_contract",
        "continuous": "continuous_series",
        "opportunity": "opportunity_scan",
    }
    subject = subject_aliases.get(explicit_subject, explicit_subject)
    if task_type == "opportunity_discovery":
        return "opportunity_scan", {
            "resolution_state": "NOT_APPLICABLE",
            "market_confirmation_required": False,
        }
    if task_type == "industry_research" and not subject:
        subject = "industry"
    if task_type in {"company_research", "thesis_check"} and not subject:
        subject = "listed_company"
    if task_type == "futures_research" and not subject:
        object_type = str(raw.get("object_type") or "").strip().lower()
        if object_type in {"futures_variety", "futures_contract", "continuous_series"}:
            subject = object_type
        elif _FUTURES_CONTINUOUS_RE.search(identifier):
            subject = "continuous_series"
        elif _FUTURES_CONTRACT_RE.match(identifier):
            subject = "futures_contract"
        else:
            subject = "futures_variety"
    if not subject:
        subject = "unknown"

    if subject == "listed_company":
        if security_master_match is not None:
            match_status = str(security_master_match.get("status") or "")
            if match_status == "MATCHED":
                company = security_master_match.get("company")
                company = company if isinstance(company, Mapping) else {}
                return subject, {
                    "resolution_state": "READY",
                    "market": str(company.get("market") or "").strip(),
                    "canonical_identifier": str(company.get("company_id") or "").strip(),
                    "canonical_display_name": str(company.get("display_name") or "").strip(),
                    "market_confirmation_required": False,
                    "identifier_kind": "security_master_match",
                    "match_method": str(security_master_match.get("match_method") or ""),
                }
            if match_status == "AMBIGUOUS":
                return subject, {
                    "resolution_state": "AMBIGUOUS",
                    "market_confirmation_required": True,
                    "identifier_kind": "security_master_ambiguous",
                    "candidates": list(security_master_match.get("candidates") or []),
                }
        if _COMPANY_CODE_RE.match(identifier):
            market = _market_suffix(identifier)
            return subject, {
                "resolution_state": "READY" if market else "MARKET_CONFIRMATION_REQUIRED",
                "market": market,
                "market_confirmation_required": not bool(market),
                "identifier_kind": "security_code",
            }
        if identifier:
            return subject, {
                "resolution_state": "IDENTITY_CONFIRMED" if confirmed and raw.get("company_id") else "NAME_MATCH_REQUIRED",
                "market": str(raw.get("market") or "").strip().upper(),
                "market_confirmation_required": not bool(raw.get("market")),
                "identifier_kind": "company_name_or_alias",
            }
        return subject, {
            "resolution_state": "MISSING_IDENTIFIER",
            "market_confirmation_required": True,
            "identifier_kind": "missing",
        }
    if subject == "industry":
        return subject, {
            "resolution_state": "READY" if identifier else "MISSING_IDENTIFIER",
            "market_confirmation_required": False,
            "identifier_kind": "industry_name",
        }
    if subject in {"futures_variety", "futures_contract", "continuous_series"}:
        has_exchange = bool(str(raw.get("exchange") or "").strip())
        if subject == "futures_contract":
            state = "READY" if identifier and has_exchange else "CONTRACT_MASTER_CONFIRMATION_REQUIRED"
        elif subject == "continuous_series":
            state = "READY" if identifier and has_exchange else "SERIES_RULE_CONFIRMATION_REQUIRED"
        else:
            state = "READY" if identifier and has_exchange else "EXCHANGE_CONFIRMATION_REQUIRED"
        return subject, {
            "resolution_state": state if identifier else "MISSING_IDENTIFIER",
            "exchange": str(raw.get("exchange") or "").strip().upper(),
            "commodity_adapter_id": str(
                (commodity_match or {}).get("adapter_id") or ""
            ),
            "commodity_exchanges": list(
                (commodity_match or {}).get("exchanges") or []
            ),
            "market_confirmation_required": not has_exchange,
            "identifier_kind": "futures_identifier",
        }
    return "unknown", {
        "resolution_state": "INPUT_TYPE_AMBIGUOUS",
        "market_confirmation_required": True,
        "identifier_kind": "unknown",
    }


def _status_for(
    task_type: str,
    subject_type: str,
    identity: Mapping[str, Any],
    raw: Mapping[str, Any],
) -> tuple[str, list[str], list[str]]:
    state = str(identity.get("resolution_state") or "")
    reasons: list[str] = []
    missing: list[str] = []
    if task_type == "unresolved" or subject_type == "unknown":
        return "NEEDS_CONFIRMATION", ["无法从输入安全识别研究对象类型"], ["task_type", "subject_type", "identifier"]
    if state == "MISSING_IDENTIFIER":
        return "BLOCKED", ["研究对象标识不能为空"], ["identifier"]
    if task_type in {"company_research", "thesis_check"} and state in {
        "NAME_MATCH_REQUIRED",
        "MARKET_CONFIRMATION_REQUIRED",
        "AMBIGUOUS",
    }:
        reasons.append("需要证券主数据确认公司身份和上市市场")
        missing.append("security_master_confirmation")
        return "NEEDS_CONFIRMATION", reasons, missing
    if task_type == "futures_research" and state != "READY":
        reasons.append("需要交易所合约主数据确认品种、交易所或连续序列规则")
        missing.append("futures_master_confirmation")
        return "NEEDS_CONFIRMATION", reasons, missing
    if task_type == "public_draft":
        reasons.append("公开稿任务必须绑定已锁定研究版本")
        missing.append("locked_research_version")
        return "PARTIAL", reasons, missing
    if raw.get("input") and isinstance(raw.get("input"), str):
        reasons.append("研究对象已完成本地语法分类，事实和身份仍由后续来源核验")
    return "READY", reasons, missing


def _normalise_identifier(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^(?:请|帮我|请帮我)?\s*(?:研究一下|分析一下|研究|分析|更新|检查)\s*", "", text, flags=re.I)
    text = text.rstrip("。！？?! ")
    return text.upper() if re.fullmatch(r"[A-Za-z0-9_.-]+", text) else text


def _market_suffix(identifier: str) -> str:
    upper = identifier.upper()
    if upper.endswith(".SH"):
        return "SSE"
    if upper.endswith(".SZ"):
        return "SZSE"
    if upper.endswith(".BJ"):
        return "BSE"
    if upper.endswith(".HK"):
        return "HKEX"
    return ""


def _candidate_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [dict(value)]
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TaskResolutionError("candidates must be an object list")
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _match_commodity(
    identifier: str, definitions: Sequence[Mapping[str, Any]]
) -> dict[str, Any] | None:
    if isinstance(definitions, (str, bytes, bytearray)) or not isinstance(
        definitions, Sequence
    ):
        raise TaskResolutionError("commodity_definitions must be an object list")
    query = _commodity_key(identifier)
    if not query:
        return None
    matches: list[dict[str, Any]] = []
    for definition in definitions:
        if not isinstance(definition, Mapping):
            raise TaskResolutionError("each commodity definition must be an object")
        values = (
            definition.get("adapter_id"),
            definition.get("display_name"),
            *(definition.get("aliases") or []),
            *(definition.get("variety_ids") or []),
        )
        if query in {_commodity_key(value) for value in values if _commodity_key(value)}:
            matches.append(
                {
                    "adapter_id": str(definition.get("adapter_id") or ""),
                    "display_name": str(definition.get("display_name") or ""),
                    "exchanges": [str(value).upper() for value in definition.get("exchanges") or []],
                    "match_method": "EXACT_CONFIG_ALIAS",
                }
            )
    if len(matches) > 1:
        raise TaskResolutionError(
            f"commodity identifier is ambiguous: {identifier}"
        )
    return matches[0] if matches else None


def _commodity_key(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", str(value or "").strip()).upper()


def _as_of(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return date.today().isoformat()
    return _parse_date(text, "research_as_of").isoformat()


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError as error:
        raise TaskResolutionError(f"{field} must be an ISO date or datetime") from error


def _hashable_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key not in {"task_id", "content_hash", "resolved_at"}
    }


def _hash_payload(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
