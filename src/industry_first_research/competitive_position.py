"""Build an evidence-only company business-model and competitive-position gate."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


class CompetitivePositionError(ValueError):
    """Raised when a competitive-position report cannot be derived safely."""


COMPETITIVE_POSITION_SCHEMA_VERSION = "company-competitive-position.v1"
RULE_VERSION = "company-competitive-position-rules.v1"
CYCLE_REVERSAL_SCHEMA_VERSION = "company-cycle-reversal.v1"
DEFAULT_REQUIRED_FIELDS = (
    "business_model",
    "revenue_structure",
    "cost_position",
    "technology_position",
    "customer_position",
    "channel_position",
    "capital_position",
    "market_share_position",
    "competitive_matrix",
    "substitution_risk",
    "delivery_quality",
    "profitability_quality",
)
_GATE_STATES = {"READY", "PARTIAL", "INSUFFICIENT", "BLOCKED"}
_UPSTREAM_STATES = {"READY", "PARTIAL", "INSUFFICIENT", "BLOCKED", "NOT_APPLICABLE"}
_QUEUE_STATES = {"WATCH", "REVIEW", "CANDIDATE", "INSUFFICIENT", "REJECTED"}
_MATRIX_FIELDS = (
    "cost",
    "performance",
    "yield",
    "certification",
    "delivery",
    "customers",
    "scale",
    "substitution_route",
)


def build_competitive_position_report(
    cycle_reversal_report: Mapping[str, Any],
    *,
    required_fields: Sequence[str] = DEFAULT_REQUIRED_FIELDS,
    rule_version: str = RULE_VERSION,
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Organise company-position evidence without inferring a durable moat."""

    _validate_report(cycle_reversal_report)
    fields = _normalise_fields(required_fields)
    if not rule_version.strip():
        raise CompetitivePositionError("rule_version must not be empty")

    items = [
        _build_item(item, required_fields=fields, rule_version=rule_version)
        for item in cycle_reversal_report["items"]
    ]
    counts = Counter(item["competitive_position_state"] for item in items)
    input_report_id = str(cycle_reversal_report.get("report_id") or "")
    report_id = snapshot_id or input_report_id or "cycle-reversal-input"
    return {
        "schema_version": COMPETITIVE_POSITION_SCHEMA_VERSION,
        "report_id": f"company-competitive-position-{report_id}",
        "input_cycle_reversal_id": input_report_id,
        "input_industry_situation_id": str(
            cycle_reversal_report.get("input_industry_situation_id") or ""
        ),
        "input_demand_transmission_id": str(
            cycle_reversal_report.get("input_demand_transmission_id") or ""
        ),
        "input_application_mapping_id": str(
            cycle_reversal_report.get("input_application_mapping_id") or ""
        ),
        "input_product_profile_id": str(
            cycle_reversal_report.get("input_product_profile_id") or ""
        ),
        "input_supplemental_id": str(
            cycle_reversal_report.get("input_supplemental_id") or ""
        ),
        "input_queue_id": str(cycle_reversal_report.get("input_queue_id") or ""),
        "input_snapshot_id": str(
            cycle_reversal_report.get("input_snapshot_id") or ""
        ),
        "rule_version": rule_version,
        "as_of": str(cycle_reversal_report.get("as_of") or ""),
        "source": str(cycle_reversal_report.get("source") or ""),
        "source_metadata": cycle_reversal_report.get("source_metadata") or {},
        "required_fields": list(fields),
        "candidate_count": len(items),
        "competitive_position_state_counts": dict(counts),
        "items": items,
        "policy": {
            "competitive_position_only": True,
            "evidence_only": True,
            "cycle_reversal_lineage_preserved": True,
            "candidate_state_preserved": True,
            "survival_analysis_included": False,
            "financial_analysis_included": False,
            "valuation_included": False,
            "investment_conclusion": False,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _validate_report(report: Any) -> None:
    if not isinstance(report, Mapping):
        raise CompetitivePositionError(
            "input cycle reversal report must be a JSON object"
        )
    if report.get("schema_version") != CYCLE_REVERSAL_SCHEMA_VERSION:
        raise CompetitivePositionError(
            "input must be a company-cycle-reversal.v1 report"
        )
    if not isinstance(report.get("items"), list):
        raise CompetitivePositionError("cycle reversal report has no items list")


def _build_item(
    item: Any,
    *,
    required_fields: Sequence[str],
    rule_version: str,
) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise CompetitivePositionError("each cycle reversal item must be an object")
    company_id = str(item.get("company_id") or "").strip()
    candidate_state = str(item.get("candidate_state") or "").upper()
    cycle_gate_state = str(item.get("cycle_reversal_gate_state") or "").upper()
    if not company_id:
        raise CompetitivePositionError("cycle reversal item company_id is required")
    if candidate_state not in _QUEUE_STATES:
        raise CompetitivePositionError(
            f"unsupported candidate_state: {candidate_state or '<empty>'}"
        )
    if cycle_gate_state not in _UPSTREAM_STATES:
        raise CompetitivePositionError(
            "unsupported cycle_reversal_gate_state: "
            f"{cycle_gate_state or '<empty>'}"
        )

    raw_fields = item.get("fields")
    if not isinstance(raw_fields, Mapping):
        raise CompetitivePositionError("cycle reversal item has no fields mapping")
    fields = {
        field: _normalise_field_summary(field, raw_fields.get(field))
        for field in _unique([*required_fields, *map(str, raw_fields.keys())])
    }
    verified_fields = [field for field in required_fields if _is_verified(fields[field])]
    unverified_fields = [
        field
        for field in required_fields
        if fields[field]["status"] in {"UNVERIFIED", "CONFLICTING"}
    ]
    unknowns = [
        field for field in required_fields if fields[field]["status"] == "MISSING"
    ]
    matrix = _competitive_matrix(fields["competitive_matrix"])
    position_state, reasons = _position_state(
        candidate_state=candidate_state,
        cycle_gate_state=cycle_gate_state,
        fields=fields,
        required_fields=required_fields,
        matrix=matrix,
    )
    evidence_ids = _unique(
        [
            *map(str, item.get("evidence_ids") or []),
            *(
                evidence_id
                for field in fields.values()
                for evidence_id in field["evidence_ids"]
            ),
        ]
    )
    return {
        "company_id": company_id,
        "company_scope": item.get("company_scope"),
        "display_name": str(item.get("display_name") or ""),
        "industry_id": str(item.get("industry_id") or ""),
        "candidate_state": candidate_state,
        "candidate_state_changed": False,
        "candidate_rule_version": str(item.get("candidate_rule_version") or ""),
        "cycle_reversal_gate_state": cycle_gate_state,
        "cycle_reversal_state": str(item.get("cycle_reversal_state") or ""),
        "competitive_position_state": position_state,
        "rule_version": rule_version,
        "fields": fields,
        "competitive_matrix": matrix,
        "business_model": _values(fields["business_model"]),
        "revenue_structure": _values(fields["revenue_structure"]),
        "position_dimensions": {
            field: _values(fields[field])
            for field in (
                "cost_position",
                "technology_position",
                "customer_position",
                "channel_position",
                "capital_position",
                "market_share_position",
                "substitution_risk",
                "delivery_quality",
                "profitability_quality",
            )
        },
        "verified_fields": verified_fields,
        "unverified_fields": unverified_fields,
        "unknowns": unknowns,
        "evidence_ids": evidence_ids,
        "reasons": reasons,
        "downstream_modules": {
            "survival_analysis": "READY_REQUIRED",
            "valuation": "READY_REQUIRED",
            "decision_snapshot": "READY_REQUIRED",
        },
        "allowed_actions": _allowed_actions(position_state),
        "prohibited_actions": [
            "moat_conclusion",
            "survival_analysis",
            "financial_analysis",
            "valuation",
            "investment_conclusion",
            "automatic_candidate_promotion",
            "execution",
        ],
        "review_only": True,
        "investment_conclusion": False,
    }


def _position_state(
    *,
    candidate_state: str,
    cycle_gate_state: str,
    fields: Mapping[str, Mapping[str, Any]],
    required_fields: Sequence[str],
    matrix: Sequence[Mapping[str, Any]],
) -> tuple[str, list[str]]:
    if candidate_state == "REJECTED" or cycle_gate_state == "BLOCKED":
        return "BLOCKED", ["UPSTREAM_CYCLE_EVIDENCE_BLOCKED"]
    if cycle_gate_state in {"PARTIAL", "INSUFFICIENT"}:
        return "BLOCKED", ["UPSTREAM_CYCLE_EVIDENCE_READY_REQUIRED"]
    if any(
        fields[field]["status"] == "CONFLICTING" for field in required_fields
    ):
        return "BLOCKED", ["COMPETITIVE_POSITION_EVIDENCE_CONFLICT"]
    if not matrix:
        return "INSUFFICIENT", ["COMPETITIVE_MATRIX_MISSING"]
    if any(not _is_verified(fields[field]) for field in required_fields):
        return "PARTIAL", ["COMPETITIVE_POSITION_EVIDENCE_INCOMPLETE"]
    return "READY", ["COMPETITIVE_POSITION_FIELDS_COVERED"]


def _competitive_matrix(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not _is_verified(summary):
        return []
    matrix: list[dict[str, Any]] = []
    for value in summary["values"]:
        if value == []:
            continue
        if not isinstance(value, Mapping):
            raise CompetitivePositionError(
                "competitive_matrix evidence values must be objects"
            )
        missing = [
            field
            for field in _MATRIX_FIELDS
            if not str(value.get(field) or "").strip()
        ]
        if missing:
            raise CompetitivePositionError(
                "competitive_matrix entry missing: " + ", ".join(missing)
            )
        matrix.append(
            {
                "competitor": str(value.get("competitor") or "").strip(),
                **{
                    field: str(value[field]).strip()
                    for field in _MATRIX_FIELDS
                },
            }
        )
    return matrix


def _normalise_fields(fields: Sequence[str]) -> tuple[str, ...]:
    if isinstance(fields, (str, bytes, bytearray)):
        raise CompetitivePositionError("required_fields must be a string list")
    try:
        normalised = tuple(dict.fromkeys(str(field).strip() for field in fields))
    except TypeError as error:
        raise CompetitivePositionError("required_fields must be a string list") from error
    if not normalised or any(not field for field in normalised):
        raise CompetitivePositionError("required_fields must contain non-empty names")
    if "competitive_matrix" not in normalised:
        return ("competitive_matrix", *normalised)
    return normalised


def _normalise_field_summary(field: str, raw_summary: Any) -> dict[str, Any]:
    if raw_summary is None:
        return {
            "status": "MISSING",
            "values": [],
            "evidence_ids": [],
            "sources": [],
            "as_of": [],
            "evidence_tiers": [],
        }
    if not isinstance(raw_summary, Mapping):
        raise CompetitivePositionError(f"field summary must be an object: {field}")
    status = str(raw_summary.get("status") or "MISSING").upper()
    if status not in {"MISSING", "VERIFIED", "UNVERIFIED", "CONFLICTING"}:
        raise CompetitivePositionError(f"unsupported field status: {status}")
    return {
        "status": status,
        "values": raw_summary.get("values") or [],
        "evidence_ids": _string_list(raw_summary.get("evidence_ids")),
        "sources": _string_list(raw_summary.get("sources")),
        "as_of": _string_list(raw_summary.get("as_of")),
        "evidence_tiers": _string_list(raw_summary.get("evidence_tiers")),
    }


def _is_verified(summary: Mapping[str, Any]) -> bool:
    return summary["status"] == "VERIFIED" and any(
        tier in {"A", "B"} for tier in summary["evidence_tiers"]
    )


def _values(summary: Mapping[str, Any]) -> list[Any]:
    return list(summary["values"]) if _is_verified(summary) else []


def _allowed_actions(state: str) -> list[str]:
    return {
        "READY": ["survival_analysis", "evidence_refresh"],
        "PARTIAL": ["competitive_gap_review", "evidence_refresh"],
        "INSUFFICIENT": ["competitive_evidence_collection", "evidence_refresh"],
        "BLOCKED": ["upstream_evidence_resolution", "evidence_refresh"],
    }[state]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise CompetitivePositionError("competitive position fields must be string lists")
    return [str(item) for item in value if str(item)]


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
