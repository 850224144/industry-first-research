"""Separate research-quality dimensions from simulated return outcomes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


QUALITY_SCORECARD_SCHEMA_VERSION = "research-quality-scorecard.v1"
RULE_VERSION = "research-quality-scorecard-rules.v1"
_DIMENSIONS = (
    "fact_accuracy",
    "state_judgment",
    "model_assumptions",
    "risk_identification",
    "valuation_quality",
    "decision_process",
    "outcome_performance",
)
_ASSESSMENT_STATUSES = {"PASS", "PARTIAL", "FAIL", "NOT_EVALUABLE"}
_OUTCOME_LABELS = {
    "THESIS_WRONG",
    "PARTIALLY_CORRECT",
    "THESIS_RIGHT_TIMING_EARLY",
    "THESIS_RIGHT_PRICE_UNREALIZED",
    "OUTCOME_BETA_OR_EVENT",
    "NOT_EVALUABLE",
}


class QualityScorecardError(ValueError):
    """Raised when a quality scorecard input is invalid."""


def build_quality_scorecard(
    decision_snapshot: Mapping[str, Any],
    *,
    research_report: Mapping[str, Any] | None = None,
    attribution_report: Mapping[str, Any] | None = None,
    thesis_check: Mapping[str, Any] | None = None,
    freshness_report: Mapping[str, Any] | None = None,
    assessments: Mapping[str, Any] | None = None,
    opportunity_scan: Mapping[str, Any] | None = None,
    scorecard_id: str = "",
) -> dict[str, Any]:
    """Build a dimensioned, review-only quality scorecard.

    Manual or later evidence assessments are accepted as inputs, but the scorecard
    never infers factual correctness from a favorable return.
    """

    _validate_snapshot(decision_snapshot)
    if research_report is not None:
        _validate_schema(research_report, "company-research-report.v1", "research_report")
    if attribution_report is not None:
        _validate_schema(attribution_report, "attribution-result.v1", "attribution_report")
    if thesis_check is not None:
        _validate_schema(thesis_check, "holding-thesis-check.v1", "thesis_check")
    if freshness_report is not None:
        _validate_schema(freshness_report, "research-freshness.v1", "freshness_report")
    if assessments is not None and not isinstance(assessments, Mapping):
        raise QualityScorecardError("assessments must be an object")

    dimensions = {
        "fact_accuracy": _dimension(
            _manual_assessment(assessments, "fact_accuracy")
            or _fact_default(freshness_report),
            default_basis="No later fact verification package was supplied.",
        ),
        "state_judgment": _dimension(
            _manual_assessment(assessments, "state_judgment")
            or _state_default(thesis_check, research_report),
            default_basis="No later state validation package was supplied.",
        ),
        "model_assumptions": _dimension(
            _manual_assessment(assessments, "model_assumptions")
            or _model_default(decision_snapshot),
            default_basis="Model assumptions were not separately reviewed.",
        ),
        "risk_identification": _dimension(
            _manual_assessment(assessments, "risk_identification")
            or _risk_default(decision_snapshot),
            default_basis="The locked decision contains no complete risk/invalidator review.",
        ),
        "valuation_quality": _dimension(
            _manual_assessment(assessments, "valuation_quality")
            or _valuation_default(decision_snapshot),
            default_basis="Valuation assumptions were not separately reviewed.",
        ),
        "decision_process": _dimension(
            _manual_assessment(assessments, "decision_process")
            or {
                "status": "PASS",
                "basis": "Decision snapshot was user-confirmed and benchmark-locked.",
                "evidence_type": "OBSERVED_FACT",
                "evidence_refs": [str(decision_snapshot["snapshot_id"])],
            },
            default_basis="Decision-process validation is unavailable.",
        ),
        "outcome_performance": _outcome_dimension(attribution_report),
    }
    weakest = [
        name
        for name, item in dimensions.items()
        if item["status"] in {"FAIL", "NOT_EVALUABLE"}
    ]
    if any(item["status"] == "FAIL" for item in dimensions.values()):
        evaluation_state = "REVIEW_REQUIRED"
    elif any(item["status"] == "NOT_EVALUABLE" for item in dimensions.values()):
        evaluation_state = "PARTIAL_NOT_EVALUABLE"
    else:
        evaluation_state = "DIMENSIONS_REVIEWED"

    payload = {
        "schema_version": QUALITY_SCORECARD_SCHEMA_VERSION,
        "scorecard_id": "quality-scorecard-" + (
            scorecard_id.strip()
            or str(decision_snapshot["snapshot_id"]).removeprefix("decision-snapshot-")
        ),
        "rule_version": RULE_VERSION,
        "decision_snapshot_id": str(decision_snapshot["snapshot_id"]),
        "research_id": str(
            decision_snapshot.get("research_id")
            or (research_report or {}).get("research_id")
            or ""
        ),
        "research_version_id": str(
            decision_snapshot.get("research_version_id")
            or (research_report or {}).get("research_version_id")
            or ""
        ),
        "research_report_id": str(research_report.get("report_id") or "") if research_report else "",
        "attribution_id": str(attribution_report.get("attribution_id") or "") if attribution_report else "",
        "thesis_check_id": str(thesis_check.get("check_id") or "") if thesis_check else "",
        "freshness_report_id": str(freshness_report.get("report_id") or "") if freshness_report else "",
        "evaluation_state": evaluation_state,
        "weakest_dimensions": weakest,
        "dimensions": dimensions,
        "outcome_label": _outcome_label(attribution_report),
        "opportunity_discovery": _opportunity_metrics(opportunity_scan),
        "policy": {
            "dimensions_not_collapsed_to_total_score": True,
            "return_does_not_prove_fact_accuracy": True,
            "not_investment_conclusion": True,
            "decision_snapshot_unchanged": True,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }
    return payload


def _dimension(value: Mapping[str, Any], *, default_basis: str) -> dict[str, Any]:
    status = str(value.get("status") or "NOT_EVALUABLE").upper()
    if status not in _ASSESSMENT_STATUSES:
        raise QualityScorecardError(f"unsupported quality assessment status: {status}")
    score = value.get("score")
    if score is not None:
        try:
            score = float(score)
        except (TypeError, ValueError) as error:
            raise QualityScorecardError("quality score must be numeric") from error
        if not 0 <= score <= 100:
            raise QualityScorecardError("quality score must be between 0 and 100")
    return {
        "status": status,
        "score": score,
        "basis": str(value.get("basis") or default_basis),
        "evidence_type": str(value.get("evidence_type") or "OBSERVED_FACT"),
        "evidence_refs": _string_list(value.get("evidence_refs")),
    }


def _manual_assessment(assessments: Mapping[str, Any] | None, name: str) -> Mapping[str, Any] | None:
    if assessments is None:
        return None
    value = assessments.get(name)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise QualityScorecardError(f"assessment for {name} must be an object")
    return value


def _fact_default(freshness: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if freshness is None:
        return {"status": "NOT_EVALUABLE", "basis": "No later fact verification package was supplied."}
    if freshness.get("freshness_status") in {"EXPIRED", "FUTURE_DATA_BLOCKED", "UNKNOWN"}:
        return {"status": "NOT_EVALUABLE", "basis": "Evidence freshness is insufficient for factual evaluation.", "evidence_type": "OBSERVED_FACT"}
    return {"status": "NOT_EVALUABLE", "basis": "Freshness is known, but later factual confirmation is still absent.", "evidence_type": "OBSERVED_FACT"}


def _state_default(
    thesis_check: Mapping[str, Any] | None,
    research_report: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    if thesis_check is not None and thesis_check.get("proposed_status") in {"INTACT", "WEAKENING", "DAMAGED", "BROKEN", "EXPIRED"}:
        return {
            "status": "PARTIAL",
            "basis": "Local thesis rules produced a state check; semantic state accuracy still requires review.",
            "evidence_type": "OBSERVED_FACT",
            "evidence_refs": [str(thesis_check.get("check_id") or "")],
        }
    if research_report is not None:
        return {"status": "NOT_EVALUABLE", "basis": "A research report is not a later state validation."}
    return {"status": "NOT_EVALUABLE", "basis": "No later state validation package was supplied."}


def _model_default(snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    decision = snapshot.get("decision") or {}
    assumptions = decision.get("fundamental_assumptions")
    if isinstance(assumptions, list) and assumptions:
        return {
            "status": "PARTIAL",
            "basis": "Assumptions are recorded in the locked decision but have not been post-validated.",
            "evidence_type": "MODEL_ESTIMATE",
            "evidence_refs": [str(snapshot["snapshot_id"])],
        }
    return {"status": "NOT_EVALUABLE", "basis": "No locked model assumptions were supplied."}


def _risk_default(snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    decision = snapshot.get("decision") or {}
    risks = decision.get("risks")
    invalidators = decision.get("invalidators")
    if isinstance(risks, list) and risks and isinstance(invalidators, list) and invalidators:
        return {
            "status": "PASS",
            "basis": "Risks and invalidators were recorded before the simulation snapshot was locked.",
            "evidence_type": "OBSERVED_FACT",
            "evidence_refs": [str(snapshot["snapshot_id"])],
        }
    return {"status": "NOT_EVALUABLE", "basis": "Locked risk and invalidator lists are incomplete."}


def _valuation_default(snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    decision = snapshot.get("decision") or {}
    anchors = decision.get("value_or_price_range")
    if isinstance(anchors, Mapping) and all(anchors.get(key) for key in ("bear", "base", "bull")):
        return {
            "status": "PARTIAL",
            "basis": "Three valuation anchors were locked; later valuation validation is absent.",
            "evidence_type": "MODEL_ESTIMATE",
            "evidence_refs": [str(snapshot["snapshot_id"])],
        }
    return {"status": "NOT_EVALUABLE", "basis": "Three valuation anchors are incomplete."}


def _outcome_dimension(attribution: Mapping[str, Any] | None) -> dict[str, Any]:
    if attribution is None:
        return {
            "status": "NOT_EVALUABLE",
            "score": None,
            "basis": "No closed attribution report was supplied.",
            "evidence_type": "OBSERVED_FACT",
            "evidence_refs": [],
        }
    label = str(attribution.get("evaluation_label") or "NOT_EVALUABLE").upper()
    if label not in _OUTCOME_LABELS:
        raise QualityScorecardError(f"unsupported attribution evaluation label: {label}")
    status = {
        "THESIS_WRONG": "FAIL",
        "PARTIALLY_CORRECT": "PARTIAL",
        "THESIS_RIGHT_TIMING_EARLY": "PARTIAL",
        "THESIS_RIGHT_PRICE_UNREALIZED": "PARTIAL",
        "OUTCOME_BETA_OR_EVENT": "PARTIAL",
        "NOT_EVALUABLE": "NOT_EVALUABLE",
    }[label]
    return {
        "status": status,
        "score": None,
        "basis": f"Observed attribution label: {label}; this does not rewrite fact or model dimensions.",
        "evidence_type": "OBSERVED_FACT",
        "evidence_refs": [str(attribution.get("attribution_id") or "")],
    }


def _outcome_label(attribution: Mapping[str, Any] | None) -> str:
    return str(attribution.get("evaluation_label") or "NOT_EVALUABLE").upper() if attribution else "NOT_EVALUABLE"


def _opportunity_metrics(scan: Mapping[str, Any] | None) -> dict[str, Any]:
    if scan is None:
        return {"status": "NOT_EVALUABLE", "metrics": {}}
    if not isinstance(scan, Mapping):
        raise QualityScorecardError("opportunity_scan must be an object")
    metrics = {
        key: scan.get(key)
        for key in (
            "scan_coverage",
            "watch_to_candidate_rate",
            "candidate_to_deep_research_rate",
            "false_positive_sample",
            "false_negative_sample",
            "empty_scan_frequency",
            "state_dwell_time",
        )
        if key in scan
    }
    return {
        "status": "REVIEW_ONLY" if metrics else "NOT_EVALUABLE",
        "metrics": metrics,
        "selection_bias_warning": "保留空集、淘汰和全部已锁定样本，不能只统计盈利案例。",
    }


def _validate_snapshot(snapshot: Mapping[str, Any]) -> None:
    if not isinstance(snapshot, Mapping) or snapshot.get("schema_version") != "decision-snapshot.v1":
        raise QualityScorecardError("decision_snapshot must be decision-snapshot.v1")
    if str(snapshot.get("status") or "").upper() != "LOCKED":
        raise QualityScorecardError("quality scorecard requires a LOCKED decision snapshot")
    if snapshot.get("immutable") is not True or snapshot.get("simulation_only") is not True:
        raise QualityScorecardError("decision snapshot must be immutable and simulation-only")
    if not str(snapshot.get("snapshot_id") or "").strip():
        raise QualityScorecardError("decision snapshot_id is required")


def _validate_schema(value: Mapping[str, Any], schema: str, name: str) -> None:
    if not isinstance(value, Mapping) or value.get("schema_version") != schema:
        raise QualityScorecardError(f"{name} must be {schema}")


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        raise QualityScorecardError("evidence_refs must be a string list")
    return [str(item) for item in value if str(item).strip()]
