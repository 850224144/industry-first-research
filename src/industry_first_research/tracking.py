"""Deterministic freshness, version-diff, and holding-thesis checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
import hashlib
import json
from typing import Any


FRESHNESS_SCHEMA_VERSION = "research-freshness.v1"
VERSION_COMPARISON_SCHEMA_VERSION = "research-version-comparison.v1"
THESIS_CHECK_SCHEMA_VERSION = "holding-thesis-check.v1"
TRACKING_RULE_VERSION = "research-tracking-rules.v1"

THESIS_STATUSES = ("INTACT", "WEAKENING", "DAMAGED", "BROKEN", "EXPIRED")
_VERIFIED_STATUSES = {"VERIFIED"}
_FRESHNESS_STATUSES = {"FRESH", "DUE", "EXPIRED", "UNKNOWN", "FUTURE"}
_DEFAULT_MAX_AGE_DAYS = 90
_FIELD_MAX_AGE_DAYS = {
    "current_price": 7,
    "current_price_as_of": 7,
    "market_state": 7,
    "market_structure": 7,
    "change_pct": 7,
    "spot_price": 14,
    "contract_price": 7,
    "price_state": 14,
    "inventory_level": 30,
    "inventory_state": 30,
    "capacity_utilization": 45,
    "utilization_state": 45,
    "supply_demand_state": 45,
    "industry_cashflow": 120,
    "historical_financials": 120,
    "financials": 120,
    "quarterly_financials": 120,
    "annual_financials": 400,
    "company_scope": 400,
    "reporting_scope": 400,
    "key_products": 400,
    "competitors": 180,
    "business_model": 180,
    "product_list": 180,
    "product_application": 180,
    "counterevidence": 90,
    "invalidators": 90,
}
_STATE_KEYS = {
    "candidate_state",
    "report_state",
    "audit_state",
    "conclusion_state",
    "final_state",
    "status",
}
_VOLATILE_VERSION_KEYS = {
    "pipeline_id",
    "report_id",
    "input_adversarial_review_id",
    "input_valuation_scenarios_id",
    "input_survival_analysis_id",
    "input_competitive_position_id",
    "input_cycle_reversal_id",
    "input_industry_situation_id",
    "input_demand_transmission_id",
    "input_application_mapping_id",
    "input_product_profile_id",
    "input_supplemental_id",
    "input_queue_id",
    "input_snapshot_id",
}
_OPERATORS = {
    "equals",
    "not_equals",
    "gt",
    "gte",
    "lt",
    "lte",
    "contains",
    "not_contains",
    "in",
    "exists",
}


class TrackingError(ValueError):
    """Raised when a tracking input cannot be evaluated safely."""


def build_evidence_freshness_report(
    supplemental_report: Mapping[str, Any],
    *,
    as_of: str = "",
    max_age_days: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Classify evidence age without changing evidence or research conclusions."""

    _validate_supplemental(supplemental_report)
    cutoff = _parse_date(as_of or str(supplemental_report.get("as_of") or ""))
    rules = dict(_FIELD_MAX_AGE_DAYS)
    if max_age_days is not None:
        for field, days in max_age_days.items():
            value = int(days)
            if value <= 0:
                raise TrackingError(f"max_age_days must be positive: {field}")
            rules[str(field)] = value

    records = list(supplemental_report.get("records") or [])
    evidence = []
    counts: dict[str, int] = {}
    for record in records:
        field = str(record.get("field") or "")
        evidence_as_of = str(record.get("as_of") or "")
        max_age = int(rules.get(field, _DEFAULT_MAX_AGE_DAYS))
        item = _freshness_one(record, cutoff, max_age)
        evidence.append(item)
        counts[item["freshness_status"]] = counts.get(item["freshness_status"], 0) + 1

    overall = _overall_freshness(counts)
    return {
        "schema_version": FRESHNESS_SCHEMA_VERSION,
        "report_id": "research-freshness-" + _digest(
            [str(supplemental_report.get("report_id") or ""), cutoff.isoformat()]
        )[:16],
        "rule_version": TRACKING_RULE_VERSION,
        "input_supplemental_id": str(supplemental_report.get("report_id") or ""),
        "as_of": cutoff.isoformat(),
        "freshness_status": overall,
        "status_counts": counts,
        "record_count": len(evidence),
        "expired_evidence_ids": [
            item["evidence_id"] for item in evidence if item["freshness_status"] == "EXPIRED"
        ],
        "future_evidence_ids": [
            item["evidence_id"] for item in evidence if item["freshness_status"] == "FUTURE"
        ],
        "evidence": evidence,
        "rules": {
            "default_max_age_days": _DEFAULT_MAX_AGE_DAYS,
            "field_max_age_days": rules,
            "due_ratio": 0.8,
        },
        "policy": {
            "facts_unchanged": True,
            "research_conclusion_changed": False,
            "decision_snapshot_created": False,
            "read_only": True,
            "review_only": True,
        },
    }


def build_research_version_comparison(
    previous_pipeline: Mapping[str, Any],
    current_pipeline: Mapping[str, Any],
    previous_supplemental: Mapping[str, Any] | None = None,
    current_supplemental: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare two immutable research versions and explain changes only."""

    _validate_pipeline(previous_pipeline)
    _validate_pipeline(current_pipeline)
    if previous_supplemental is not None:
        _validate_supplemental(previous_supplemental)
    if current_supplemental is not None:
        _validate_supplemental(current_supplemental)

    stage_diffs = []
    all_company_ids: set[str] = set()
    previous_stages = previous_pipeline.get("stages") or {}
    current_stages = current_pipeline.get("stages") or {}
    for stage in sorted(set(previous_stages) | set(current_stages)):
        old_stage = previous_stages.get(stage) or {}
        new_stage = current_stages.get(stage) or {}
        old_items = _items_by_company(old_stage)
        new_items = _items_by_company(new_stage)
        all_company_ids.update(old_items)
        all_company_ids.update(new_items)
        company_diffs = []
        for company_id in sorted(set(old_items) | set(new_items)):
            old_item = old_items.get(company_id)
            new_item = new_items.get(company_id)
            changed_fields, state_changes = _item_diff(old_item, new_item)
            if changed_fields or state_changes or (old_item is None) != (new_item is None):
                company_diffs.append(
                    {
                        "company_id": company_id,
                        "changed_fields": changed_fields,
                        "state_changes": state_changes,
                        "old_present": old_item is not None,
                        "current_present": new_item is not None,
                    }
                )
        old_summary = _summary_state(old_stage)
        new_summary = _summary_state(new_stage)
        if company_diffs or old_summary != new_summary:
            stage_diffs.append(
                {
                    "stage": stage,
                    "old_summary": old_summary,
                    "current_summary": new_summary,
                    "company_diffs": company_diffs,
                }
            )

    evidence_diff = _evidence_diff(previous_supplemental, current_supplemental)
    old_final = str(previous_pipeline.get("final_state") or "")
    current_final = str(current_pipeline.get("final_state") or "")
    state_changes = []
    if old_final != current_final:
        state_changes.append(
            {"path": "final_state", "old": old_final, "current": current_final}
        )
    for stage_diff in stage_diffs:
        for company_diff in stage_diff["company_diffs"]:
            for change in company_diff["state_changes"]:
                state_changes.append(
                    {
                        "path": f"{stage_diff['stage']}.{company_diff['company_id']}.{change['field']}",
                        "old": change["old"],
                        "current": change["current"],
                    }
                )

    return {
        "schema_version": VERSION_COMPARISON_SCHEMA_VERSION,
        "comparison_id": "version-comparison-" + _digest(
            [str(previous_pipeline.get("pipeline_id") or ""), str(current_pipeline.get("pipeline_id") or "")]
        )[:16],
        "rule_version": TRACKING_RULE_VERSION,
        "previous_pipeline_id": str(previous_pipeline.get("pipeline_id") or ""),
        "current_pipeline_id": str(current_pipeline.get("pipeline_id") or ""),
        "previous_as_of": str(previous_pipeline.get("as_of") or ""),
        "current_as_of": str(current_pipeline.get("as_of") or ""),
        "candidate_count": len(all_company_ids),
        "changed_stage_count": len(stage_diffs),
        "changed_state_count": len(state_changes),
        "stage_diffs": stage_diffs,
        "state_changes": state_changes,
        "evidence_diff": evidence_diff,
        "conclusion_change": {
            "changed": bool(state_changes),
            "old_final_state": old_final,
            "current_final_state": current_final,
            "directional_conclusion_changed": False,
            "requires_review": bool(stage_diffs or evidence_diff["changed"]),
        },
        "policy": {
            "old_version_preserved": True,
            "facts_not_rewritten": True,
            "automatic_directional_conclusion": False,
            "automatic_decision_snapshot": False,
            "read_only": True,
            "review_only": True,
        },
    }


def build_holding_thesis_check(
    thesis: Mapping[str, Any],
    supplemental_report: Mapping[str, Any],
    *,
    as_of: str = "",
    previous_supplemental: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate local hypothesis/red-line rules without changing a thesis version."""

    _validate_thesis(thesis)
    _validate_supplemental(supplemental_report)
    if previous_supplemental is not None:
        _validate_supplemental(previous_supplemental)
    cutoff = _parse_date(as_of or str(supplemental_report.get("as_of") or ""))
    freshness = build_evidence_freshness_report(supplemental_report, as_of=cutoff.isoformat())
    freshness_by_id = {item["evidence_id"]: item for item in freshness["evidence"]}
    thesis_company_id = str(thesis.get("company_id") or thesis.get("subject_id") or "")
    current_records = _latest_records(supplemental_report, cutoff, thesis_company_id)
    previous_records = (
        _latest_records(previous_supplemental, cutoff, thesis_company_id)
        if previous_supplemental is not None
        else {}
    )

    hypothesis_checks = [
        _check_hypothesis(
            item,
            current_records,
            previous_records,
            freshness_by_id,
            thesis_company_id,
        )
        for item in thesis.get("hypotheses") or thesis.get("testable_hypotheses") or []
    ]
    red_line_checks = [
        _check_red_line(item, current_records, freshness_by_id, thesis_company_id)
        for item in thesis.get("red_lines") or []
    ]
    expired = _thesis_expired(thesis, cutoff)
    fatal = any(item["status"] == "TRIGGERED" and item["severity"] == "FATAL" for item in red_line_checks)
    severe = any(item["status"] == "TRIGGERED" and item["severity"] in {"FATAL", "SEVERE"} for item in red_line_checks)
    failed = any(item["status"] == "FAILED" for item in hypothesis_checks)
    unknown = any(item["status"] in {"UNKNOWN", "STALE", "CONFLICTING"} for item in hypothesis_checks + red_line_checks)
    if expired:
        proposed_status = "EXPIRED"
    elif fatal:
        proposed_status = "BROKEN"
    elif severe:
        proposed_status = "DAMAGED"
    elif failed or unknown:
        proposed_status = "WEAKENING"
    else:
        proposed_status = "INTACT"
    current_status = str(thesis.get("status") or "INTACT").upper()
    proposed_status, status_downgrade_blocked = _preserve_thesis_status(
        current_status, proposed_status
    )
    return {
        "schema_version": THESIS_CHECK_SCHEMA_VERSION,
        "check_id": "thesis-check-" + _digest(
            [str(thesis["thesis_id"]), str(thesis.get("version") or 1), cutoff.isoformat()]
        )[:16],
        "rule_version": TRACKING_RULE_VERSION,
        "thesis_id": str(thesis["thesis_id"]),
        "thesis_version": int(thesis.get("version") or 1),
        "company_id": thesis_company_id,
        "as_of": cutoff.isoformat(),
        "current_status": current_status,
        "proposed_status": proposed_status,
        "status_changed": current_status != proposed_status,
        "status_change_requires_confirmation": current_status != proposed_status,
        "status_downgrade_blocked": status_downgrade_blocked,
        "hypothesis_checks": hypothesis_checks,
        "red_line_checks": red_line_checks,
        "freshness_status": freshness["freshness_status"],
        "expired_evidence_ids": freshness["expired_evidence_ids"],
        "review_required": bool(
            current_status != proposed_status
            or unknown
            or freshness["freshness_status"] != "FRESH"
        ),
        "policy": {
            "thesis_version_unchanged": True,
            "semantic_status_not_auto_committed": True,
            "price_alone_cannot_break_thesis": True,
            "decision_snapshot_created": False,
            "read_only": True,
            "review_only": True,
        },
    }


def _freshness_one(record: Mapping[str, Any], cutoff: date, max_age: int) -> dict[str, Any]:
    evidence_id = str(record.get("evidence_id") or "")
    raw_date = str(record.get("as_of") or "")
    if not raw_date:
        status = "UNKNOWN"
        age_days = None
        expires_at = None
    else:
        record_date = _parse_date(raw_date)
        age_days = (cutoff - record_date).days
        if age_days < 0:
            status = "FUTURE"
        elif age_days > max_age:
            status = "EXPIRED"
        elif age_days >= max(1, int(max_age * 0.8)):
            status = "DUE"
        else:
            status = "FRESH"
        expires_at = record_date.fromordinal(record_date.toordinal() + max_age).isoformat()
    return {
        "evidence_id": evidence_id,
        "company_id": str(record.get("company_id") or ""),
        "field": str(record.get("field") or ""),
        "as_of": raw_date,
        "age_days": age_days,
        "max_age_days": max_age,
        "expires_at": expires_at,
        "freshness_status": status,
        "verification_status": str(record.get("verification_status") or ""),
        "source": str(record.get("source") or ""),
    }


def _overall_freshness(counts: Mapping[str, int]) -> str:
    if not counts:
        return "UNKNOWN"
    if counts.get("FUTURE"):
        return "FUTURE_DATA_BLOCKED"
    if counts.get("EXPIRED"):
        return "EXPIRED"
    if counts.get("UNKNOWN"):
        return "UNKNOWN"
    if counts.get("DUE"):
        return "REFRESH_DUE"
    return "FRESH"


def _evidence_diff(previous: Mapping[str, Any] | None, current: Mapping[str, Any] | None) -> dict[str, Any]:
    if previous is None or current is None:
        return {
            "available": False,
            "changed": False,
            "added_evidence_ids": [],
            "removed_evidence_ids": [],
            "modified_evidence_ids": [],
            "field_changes": [],
        }
    old = {str(item["evidence_id"]): item for item in previous.get("records") or []}
    new = {str(item["evidence_id"]): item for item in current.get("records") or []}
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    modified = sorted(
        evidence_id
        for evidence_id in set(old) & set(new)
        if _digest(old[evidence_id]) != _digest(new[evidence_id])
    )
    old_fields = _latest_records(previous, _parse_date(str(previous.get("as_of") or "")), None)
    new_fields = _latest_records(current, _parse_date(str(current.get("as_of") or "")), None)
    field_changes = []
    for key in sorted(set(old_fields) | set(new_fields)):
        old_record = old_fields.get(key)
        new_record = new_fields.get(key)
        old_value = old_record.get("value") if old_record is not None else None
        new_value = new_record.get("value") if new_record is not None else None
        old_exists = old_record is not None
        new_exists = new_record is not None
        if not old_exists and new_exists:
            continue
        if _digest(old_value) != _digest(new_value):
            field_changes.append(
                {
                    "company_id": key[0],
                    "field": key[1],
                    "old_value": old_value,
                    "current_value": new_value,
                }
            )
    return {
        "available": True,
        "changed": bool(added or removed or modified or field_changes),
        "added_evidence_ids": added,
        "removed_evidence_ids": removed,
        "modified_evidence_ids": modified,
        "field_changes": field_changes,
    }


def _items_by_company(stage: Any) -> dict[str, Mapping[str, Any]]:
    items = stage.get("items") if isinstance(stage, Mapping) else []
    if not isinstance(items, list):
        return {}
    return {
        str(item["company_id"]): item
        for item in items
        if isinstance(item, Mapping) and str(item.get("company_id") or "")
    }


def _item_diff(old: Mapping[str, Any] | None, new: Mapping[str, Any] | None) -> tuple[list[str], list[dict[str, Any]]]:
    if old is None or new is None:
        return ["<item>"], []
    changed: list[str] = []
    state_changes: list[dict[str, Any]] = []
    for key in sorted(set(old) | set(new)):
        if key in _VOLATILE_VERSION_KEYS:
            continue
        old_value = old.get(key)
        new_value = new.get(key)
        if key == "fields" and isinstance(old_value, Mapping) and isinstance(new_value, Mapping):
            for field in sorted(set(old_value) | set(new_value)):
                if _digest(old_value.get(field)) != _digest(new_value.get(field)):
                    changed.append(f"fields.{field}")
            continue
        if _digest(old_value) != _digest(new_value):
            changed.append(key)
            if key in _STATE_KEYS or key.endswith("_state") or key.endswith("_status"):
                state_changes.append({"field": key, "old": old_value, "current": new_value})
    return changed, state_changes


def _summary_state(stage: Any) -> dict[str, Any]:
    if not isinstance(stage, Mapping):
        return {}
    return {
        key: stage[key]
        for key in sorted(stage)
        if key.endswith("_counts") or key in {"schema_version", "as_of"}
    }


def _latest_records(
    supplemental: Mapping[str, Any] | None, cutoff: date, company_id: Any
) -> dict[tuple[str, str], Mapping[str, Any]]:
    if supplemental is None:
        return {}
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for record in supplemental.get("records") or []:
        record_company = str(record.get("company_id") or "")
        if company_id and record_company != str(company_id):
            continue
        raw_date = str(record.get("as_of") or "")
        if not raw_date:
            continue
        record_date = _parse_date(raw_date)
        if record_date > cutoff:
            continue
        key = (record_company, str(record.get("field") or ""))
        old = result.get(key)
        if old is None or _parse_date(str(old.get("as_of") or "")) <= record_date:
            result[key] = record
    return result


def _check_hypothesis(
    hypothesis: Mapping[str, Any],
    current_records: Mapping[tuple[str, str], Mapping[str, Any]],
    previous_records: Mapping[tuple[str, str], Mapping[str, Any]],
    freshness_by_id: Mapping[str, Mapping[str, Any]],
    thesis_company_id: str,
) -> dict[str, Any]:
    field = str(hypothesis.get("field") or hypothesis.get("metric") or "")
    company_id = str(hypothesis.get("company_id") or thesis_company_id)
    key = (company_id, field)
    current = current_records.get(key) or _find_field(current_records, field, company_id)
    previous = previous_records.get(key) or _find_field(previous_records, field, company_id)
    base = {
        "hypothesis_id": str(hypothesis.get("hypothesis_id") or hypothesis.get("id") or field),
        "statement": str(hypothesis.get("statement") or ""),
        "field": field,
        "evidence_id": str(current.get("evidence_id") or "") if current else "",
        "evidence_status": str(current.get("verification_status") or "UNKNOWN") if current else "UNKNOWN",
    }
    if current is None:
        return {**base, "status": "UNKNOWN", "reason": "no current evidence"}
    freshness = freshness_by_id.get(str(current.get("evidence_id") or ""), {})
    if freshness.get("freshness_status") in {"EXPIRED", "FUTURE"}:
        return {**base, "status": "STALE", "reason": freshness.get("freshness_status")}
    if str(current.get("verification_status") or "") not in _VERIFIED_STATUSES:
        return {**base, "status": str(current.get("verification_status") or "UNKNOWN"), "reason": "evidence is not verified"}
    passed, reason = _evaluate_rule(hypothesis, current.get("value"), previous.get("value") if previous else None)
    return {**base, "status": "PASSED" if passed else "FAILED", "reason": reason, "value": current.get("value")}


def _check_red_line(
    red_line: Mapping[str, Any],
    current_records: Mapping[tuple[str, str], Mapping[str, Any]],
    freshness_by_id: Mapping[str, Mapping[str, Any]],
    thesis_company_id: str,
) -> dict[str, Any]:
    field = str(red_line.get("field") or red_line.get("metric") or "")
    company_id = str(red_line.get("company_id") or thesis_company_id)
    current = _find_field(current_records, field, company_id)
    severity = str(red_line.get("severity") or "WARNING").upper()
    if severity not in {"WARNING", "SEVERE", "FATAL"}:
        severity = "WARNING"
    base = {
        "red_line_id": str(red_line.get("red_line_id") or red_line.get("id") or field),
        "statement": str(red_line.get("statement") or red_line.get("condition_text") or ""),
        "field": field,
        "severity": severity,
        "evidence_id": str(current.get("evidence_id") or "") if current else "",
    }
    if current is None:
        return {**base, "status": "UNKNOWN", "reason": "no current evidence"}
    freshness = freshness_by_id.get(str(current.get("evidence_id") or ""), {})
    if freshness.get("freshness_status") in {"EXPIRED", "FUTURE"}:
        return {**base, "status": "STALE", "reason": freshness.get("freshness_status")}
    if str(current.get("verification_status") or "") not in _VERIFIED_STATUSES:
        return {**base, "status": "CONFLICTING", "reason": "evidence is not verified"}
    triggered, reason = _evaluate_rule(red_line, current.get("value"), None)
    return {**base, "status": "TRIGGERED" if triggered else "CLEAR", "reason": reason, "value": current.get("value")}


def _evaluate_rule(rule: Mapping[str, Any], value: Any, previous_value: Any) -> tuple[bool, str]:
    operator = str(rule.get("operator") or "").lower()
    expected = rule.get("expected_value", rule.get("value"))
    if not operator and rule.get("expected_direction"):
        direction = str(rule["expected_direction"]).upper()
        if previous_value is None:
            return False, "previous value unavailable for direction check"
        try:
            observed = "UP" if value > previous_value else "DOWN" if value < previous_value else "STABLE"
        except TypeError:
            return False, "values are not comparable"
        accepted = {
            "UP": {"UP", "IMPROVING", "INCREASING"},
            "DOWN": {"DOWN", "DETERIORATING", "DECREASING"},
            "STABLE": {"STABLE", "UNCHANGED"},
        }.get(observed, set())
        return direction in accepted, f"observed direction={observed}, expected={direction}"
    if operator not in _OPERATORS:
        return bool(value), "verified evidence present" if value else "empty value"
    try:
        if operator == "equals":
            result = value == expected
        elif operator == "not_equals":
            result = value != expected
        elif operator == "gt":
            result = value > expected
        elif operator == "gte":
            result = value >= expected
        elif operator == "lt":
            result = value < expected
        elif operator == "lte":
            result = value <= expected
        elif operator == "contains":
            result = expected in value
        elif operator == "not_contains":
            result = expected not in value
        elif operator == "in":
            result = value in expected
        else:
            result = value is not None
    except (TypeError, ValueError):
        return False, "rule and evidence value are not comparable"
    return bool(result), f"operator={operator}, expected={expected!r}, observed={value!r}"


def _find_field(
    records: Mapping[tuple[str, str], Mapping[str, Any]],
    field: str,
    company_id: str = "",
) -> Mapping[str, Any] | None:
    matches = [
        record
        for (record_company_id, metric), record in records.items()
        if metric == field and (not company_id or record_company_id == company_id)
    ]
    return matches[-1] if matches else None


def _thesis_expired(thesis: Mapping[str, Any], cutoff: date) -> bool:
    for key in ("expires_at", "maximum_extension_until"):
        value = str(thesis.get(key) or "")
        if value and cutoff > _parse_date(value):
            return True
    timebox = thesis.get("timebox")
    if isinstance(timebox, Mapping):
        value = str(timebox.get("maximum_extension_until") or "")
        if value and cutoff > _parse_date(value):
            return True
    return False


def _preserve_thesis_status(current: str, proposed: str) -> tuple[str, bool]:
    rank = {status: index for index, status in enumerate(THESIS_STATUSES)}
    if rank[proposed] < rank[current]:
        return current, True
    return proposed, False


def _validate_pipeline(report: Mapping[str, Any]) -> None:
    if not isinstance(report, Mapping) or report.get("schema_version") != "company-research-pipeline.v1":
        raise TrackingError("input must be a company-research-pipeline.v1 report")
    if not isinstance(report.get("stages"), Mapping):
        raise TrackingError("pipeline has no stages")


def _validate_supplemental(report: Mapping[str, Any]) -> None:
    if not isinstance(report, Mapping) or report.get("schema_version") != "company-supplemental-evidence.v1":
        raise TrackingError("input must be a company-supplemental-evidence.v1 report")
    if not isinstance(report.get("records"), list):
        raise TrackingError("supplemental report has no records")


def _validate_thesis(thesis: Mapping[str, Any]) -> None:
    if not isinstance(thesis, Mapping):
        raise TrackingError("thesis must be an object")
    if str(thesis.get("schema_version") or "holding-thesis.v1") != "holding-thesis.v1":
        raise TrackingError("thesis must be holding-thesis.v1")
    if not str(thesis.get("thesis_id") or "").strip():
        raise TrackingError("thesis_id is required")
    if not str(thesis.get("company_id") or thesis.get("subject_id") or "").strip():
        raise TrackingError("thesis company_id or subject_id is required")
    status = str(thesis.get("status") or "INTACT").upper()
    if status not in THESIS_STATUSES:
        raise TrackingError(f"unsupported thesis status: {status}")
    for key in ("hypotheses", "testable_hypotheses", "red_lines"):
        if key in thesis and not isinstance(thesis[key], list):
            raise TrackingError(f"thesis {key} must be a list")


def _parse_date(value: str) -> date:
    text = value.strip()
    if not text:
        raise TrackingError("as_of must not be empty")
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise TrackingError(f"invalid date: {value}") from error


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
