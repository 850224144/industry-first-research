"""Create user-confirmed, immutable holding-thesis versions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import hashlib
import json
from typing import Any


HOLDING_THESIS_SCHEMA_VERSION = "holding-thesis.v1"
RULE_VERSION = "holding-thesis-rules.v1"
_STATUSES = {"INTACT", "WEAKENING", "DAMAGED", "BROKEN", "EXPIRED"}
_SEVERITIES = {"WARNING", "SEVERE", "FATAL"}


class HoldingThesisError(ValueError):
    """Raised when a thesis cannot be safely drafted or locked."""


def build_holding_thesis(
    thesis: Mapping[str, Any],
    *,
    user_confirmed: bool = False,
    previous_thesis: Mapping[str, Any] | None = None,
    rule_version: str = RULE_VERSION,
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Build a draft or lock a new immutable thesis version.

    A draft is useful while the user is composing a thesis. Only an explicit
    confirmation creates the immutable version used by later checks.
    """

    _validate_input(thesis)
    if not rule_version.strip():
        raise HoldingThesisError("rule_version must not be empty")
    if previous_thesis is not None:
        _validate_input(previous_thesis)

    company_id = str(thesis.get("company_id") or thesis.get("subject_id") or "").strip()
    thesis_id = str(thesis.get("thesis_id") or "").strip()
    version = int(thesis.get("version") or 1)
    supersedes = str(thesis.get("supersedes_thesis_id") or "").strip()
    revision_reason = str(thesis.get("revision_reason") or "").strip()
    if supersedes:
        if not revision_reason:
            raise HoldingThesisError(
                "revision_reason is required when supersedes_thesis_id is supplied"
            )
        if previous_thesis is not None:
            previous_id = str(previous_thesis.get("thesis_id") or "")
            previous_version = int(previous_thesis.get("version") or 1)
            if supersedes != previous_id:
                raise HoldingThesisError("supersedes_thesis_id does not match previous thesis")
            if version <= previous_version:
                raise HoldingThesisError("thesis revision version must increase")
    if not thesis_id:
        thesis_id = f"{company_id}-thesis"

    raw_hypotheses = (
        thesis["hypotheses"]
        if "hypotheses" in thesis
        else thesis.get("testable_hypotheses")
    )
    hypotheses = _normalise_hypotheses(raw_hypotheses)
    red_lines = _normalise_red_lines(thesis.get("red_lines"))
    core_thesis = str(thesis.get("core_thesis") or "").strip()
    normal_volatility = thesis.get("normal_volatility")
    valuation_anchors = thesis.get("valuation_anchors")
    timebox = thesis.get("timebox")
    relative_opportunity = thesis.get("relative_opportunity")
    if not core_thesis or len(core_thesis) > 200:
        raise HoldingThesisError("core_thesis must contain 1-200 characters")
    if not isinstance(normal_volatility, Mapping) or not normal_volatility:
        raise HoldingThesisError("normal_volatility must be a non-empty object")
    if not isinstance(valuation_anchors, Mapping):
        raise HoldingThesisError("valuation_anchors must be an object")
    _require_anchor_keys(valuation_anchors)
    if not isinstance(timebox, Mapping) or not timebox:
        raise HoldingThesisError("timebox must be a non-empty object")
    for key in ("expected_horizon", "next_check_at"):
        if not str(timebox.get(key) or "").strip():
            raise HoldingThesisError(f"timebox.{key} must be non-empty")
    if not isinstance(relative_opportunity, Mapping) or not relative_opportunity:
        raise HoldingThesisError("relative_opportunity must be a non-empty object")

    status = str(thesis.get("status") or "INTACT").upper()
    if status not in _STATUSES:
        raise HoldingThesisError(f"unsupported thesis status: {status}")
    if not user_confirmed and status != "INTACT":
        raise HoldingThesisError("only an INTACT thesis can be drafted without confirmation")

    normalized = {
        "schema_version": HOLDING_THESIS_SCHEMA_VERSION,
        "thesis_id": thesis_id,
        "company_id": company_id,
        "subject_id": str(thesis.get("subject_id") or company_id).strip(),
        "version": version,
        "status": status,
        "core_thesis": core_thesis,
        "hypotheses": hypotheses,
        "red_lines": red_lines,
        "normal_volatility": deepcopy(dict(normal_volatility)),
        "valuation_anchors": deepcopy(dict(valuation_anchors)),
        "timebox": deepcopy(dict(timebox)),
        "relative_opportunity": deepcopy(dict(relative_opportunity)),
        "source_opportunity_id": str(thesis.get("source_opportunity_id") or ""),
        "source_research_id": str(thesis.get("source_research_id") or ""),
        "source_decision_id": str(thesis.get("source_decision_id") or ""),
        "supersedes_thesis_id": supersedes or None,
        "revision_reason": revision_reason or None,
        "rule_version": rule_version,
    }
    lock_status = "LOCKED" if user_confirmed else "DRAFT"
    normalized.update(
        {
            "lock_status": lock_status,
            "user_confirmed": bool(user_confirmed),
            "immutable": bool(user_confirmed),
            "content_hash": _digest(normalized),
            "policy": {
                "simulation_only": True,
                "locked_before_simulation": bool(user_confirmed),
                "original_version_not_overwritable": bool(user_confirmed),
                "revision_requires_new_version": True,
                "semantic_status_requires_confirmation": True,
                "price_alone_cannot_break_thesis": True,
                "decision_snapshot_created": False,
                "execution_enabled": False,
                "read_only": True,
                "review_only": True,
            },
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        }
    )
    generated_id = snapshot_id or f"{company_id}-{thesis_id}-v{version}"
    normalized["snapshot_id"] = f"holding-thesis-{generated_id}"
    return normalized


def _validate_input(thesis: Mapping[str, Any]) -> None:
    if not isinstance(thesis, Mapping):
        raise HoldingThesisError("thesis input must be an object")
    schema_version = str(thesis.get("schema_version") or HOLDING_THESIS_SCHEMA_VERSION)
    if schema_version != HOLDING_THESIS_SCHEMA_VERSION:
        raise HoldingThesisError("thesis must be holding-thesis.v1")
    company_id = str(thesis.get("company_id") or thesis.get("subject_id") or "").strip()
    if not company_id:
        raise HoldingThesisError("thesis company_id or subject_id is required")
    version = int(thesis.get("version") or 1)
    if version < 1:
        raise HoldingThesisError("thesis version must be positive")


def _normalise_hypotheses(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise HoldingThesisError("hypotheses must be a list")
    if not 3 <= len(raw) <= 7:
        raise HoldingThesisError("hypotheses must contain 3-7 items")
    result = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, Mapping):
            raise HoldingThesisError("each hypothesis must be an object")
        hypothesis_id = str(item.get("hypothesis_id") or item.get("id") or f"H{index}").strip()
        statement = str(item.get("statement") or "").strip()
        field = str(item.get("field") or item.get("metric") or "").strip()
        frequency = str(item.get("validation_frequency") or item.get("frequency") or "").strip()
        if not hypothesis_id or hypothesis_id in seen:
            raise HoldingThesisError(f"duplicate or empty hypothesis_id: {hypothesis_id}")
        if not statement or not field or not frequency:
            raise HoldingThesisError(
                f"hypothesis {hypothesis_id} requires statement, field, and validation_frequency"
            )
        if not item.get("expected_direction") and not item.get("operator"):
            raise HoldingThesisError(
                f"hypothesis {hypothesis_id} requires expected_direction or operator"
            )
        evidence_ids = _string_list(item.get("evidence_ids"))
        result.append(
            {
                **dict(item),
                "hypothesis_id": hypothesis_id,
                "statement": statement,
                "field": field,
                "validation_frequency": frequency,
                "evidence_ids": evidence_ids,
                "current_status": str(item.get("current_status") or "PENDING").upper(),
            }
        )
        seen.add(hypothesis_id)
    return result


def _normalise_red_lines(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)) or not raw:
        raise HoldingThesisError("red_lines must be a non-empty list")
    result = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, Mapping):
            raise HoldingThesisError("each red line must be an object")
        red_line_id = str(item.get("red_line_id") or item.get("id") or f"R{index}").strip()
        field = str(item.get("field") or item.get("metric") or "").strip()
        severity = str(item.get("severity") or "WARNING").upper()
        action = str(item.get("action") or "").strip()
        if not red_line_id or red_line_id in seen:
            raise HoldingThesisError(f"duplicate or empty red_line_id: {red_line_id}")
        if not field or severity not in _SEVERITIES or not action:
            raise HoldingThesisError(
                f"red line {red_line_id} requires field, valid severity, and action"
            )
        if not item.get("operator") and not item.get("expected_direction"):
            raise HoldingThesisError(
                f"red line {red_line_id} requires operator or expected_direction"
            )
        result.append({**dict(item), "red_line_id": red_line_id, "field": field, "severity": severity, "action": action})
        seen.add(red_line_id)
    return result


def _require_anchor_keys(anchors: Mapping[str, Any]) -> None:
    names = set(anchors)
    valid = ({"bear", "base", "bull"}, {"pessimistic", "base", "optimistic"})
    if not any(required <= names for required in valid):
        raise HoldingThesisError("valuation_anchors requires bear/base/bull or pessimistic/base/optimistic")
    if any(not anchors.get(name) for name in names if name in {"bear", "base", "bull", "pessimistic", "optimistic"}):
        raise HoldingThesisError("valuation_anchors values must be non-empty")


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise HoldingThesisError("evidence_ids must be a string list")
    return [str(item).strip() for item in value if str(item).strip()]


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
