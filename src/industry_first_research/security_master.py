"""Lightweight security master and effective-dated industry membership history.

This module deliberately owns only identity and classification metadata.  It
does not fetch or store daily prices, financial statements, valuation data,
technical indicators, or announcement text.  A bounded company pool can seed
light candidates, but its coverage is never presented as a full-market master.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


class SecurityMasterError(ValueError):
    """Raised when a lightweight master or membership snapshot is invalid."""


SECURITY_MASTER_INPUT_SCHEMA_VERSION = "security-master-input.v1"
SECURITY_MASTER_SNAPSHOT_SCHEMA_VERSION = "security-master-snapshot.v1"
INDUSTRY_COMPANY_POOL_SCHEMA_VERSION = "industry-company-pool.v1"
RESEARCH_CANDIDATE_SET_SCHEMA_VERSION = "research-asset-candidate-set.v1"
RULE_VERSION = "security-master-rules.v1"
MEMBERSHIP_RULE_VERSION = "industry-membership-history-rules.v1"

_RECORD_SCOPES = {"MASTER", "LIGHT_CANDIDATE", "RESEARCH_REPRESENTATIVE"}
_COVERAGE_CLAIMS = {"FULL_MARKET", "BOUNDED", "REPRESENTATIVE", "UNKNOWN"}
_MEMBERSHIP_TYPES = {"PRIMARY", "SECONDARY"}
_CONFIDENCE = {"HIGH", "MEDIUM", "LOW", "UNVERIFIED"}
_LISTING_STATUSES = {"LISTED", "SUSPENDED", "DELISTING", "DELISTED", "UNKNOWN"}
_DEEP_FIELDS = {
    "price",
    "prices",
    "daily_prices",
    "quotes",
    "quote",
    "financials",
    "financial_data",
    "valuation",
    "valuation_data",
    "technical_indicators",
    "indicators",
    "announcements",
    "announcement_text",
    "raw_announcements",
    "fundamentals",
    "income_statement",
    "balance_sheet",
    "cash_flow",
}
_DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-_./]?(\d{2})[-_./]?(\d{2})(?!\d)")


def build_security_master_snapshot(
    payload: Mapping[str, Any],
    *,
    previous_snapshot: Mapping[str, Any] | None = None,
    snapshot_id: str = "",
    rule_version: str = RULE_VERSION,
) -> dict[str, Any]:
    """Build a new immutable snapshot from explicit light records.

    The input accepts either ``security-master-input.v1`` or an existing
    bounded ``industry-company-pool.v1`` snapshot.  A research candidate set
    is intentionally rejected from the master projection and retained in the
    report's boundary log.
    """

    if not isinstance(payload, Mapping):
        raise SecurityMasterError("security master input must be an object")
    if not str(rule_version).strip():
        raise SecurityMasterError("rule_version must not be empty")
    input_schema = str(payload.get("schema_version") or "")
    pool_industry = payload.get("industry") if isinstance(payload.get("industry"), Mapping) else {}
    as_of_value = (
        payload.get("as_of")
        or payload.get("research_as_of")
        or (pool_industry.get("as_of") if isinstance(pool_industry, Mapping) else "")
        or _date_from_snapshot_id(str(payload.get("snapshot_id") or ""))
    )
    as_of = _parse_date(str(as_of_value or ""), "as_of")
    previous = _validate_previous(previous_snapshot, as_of)

    if input_schema == SECURITY_MASTER_INPUT_SCHEMA_VERSION:
        raw_records = payload.get("records")
        if not isinstance(raw_records, list):
            raise SecurityMasterError("security-master input records must be a list")
        coverage_claim = str(
            (payload.get("scope") or {}).get("coverage_claim")
            if isinstance(payload.get("scope"), Mapping)
            else payload.get("coverage_claim") or "UNKNOWN"
        ).upper()
        input_scope = str(
            (payload.get("scope") or {}).get("scope_type")
            if isinstance(payload.get("scope"), Mapping)
            else payload.get("scope_type") or "EXPLICIT"
        ).upper()
        source_metadata = payload.get("source_metadata") or {}
        source_project = str(payload.get("source_project") or "").strip()
    elif input_schema == INDUSTRY_COMPANY_POOL_SCHEMA_VERSION:
        raw_records = _records_from_company_pool(payload)
        coverage_claim = "BOUNDED"
        input_scope = "BOUNDED_POOL"
        source_metadata = payload.get("source") or {}
        source_project = str(
            (source_metadata.get("provider") if isinstance(source_metadata, Mapping) else "")
            or "company_pool"
        )
    elif input_schema == RESEARCH_CANDIDATE_SET_SCHEMA_VERSION:
        return _empty_candidate_boundary_report(
            payload,
            as_of=as_of,
            previous=previous,
            snapshot_id=snapshot_id,
            rule_version=rule_version,
        )
    else:
        raise SecurityMasterError(
            "input must be security-master-input.v1, industry-company-pool.v1, "
            "or research-asset-candidate-set.v1"
        )

    if coverage_claim not in _COVERAGE_CLAIMS:
        raise SecurityMasterError(f"unsupported coverage_claim: {coverage_claim}")
    normalised_records: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_company_ids: set[str] = set()
    for index, raw in enumerate(raw_records):
        raw_company_id = (
            str(raw.get("company_id") or raw.get("security_id") or raw.get("ticker") or "").strip()
            if isinstance(raw, Mapping)
            else ""
        )
        if raw_company_id and raw_company_id in seen_company_ids:
            rejected.append(
                {
                    "record_index": index,
                    "company_id": raw_company_id,
                    "reason": "DUPLICATE_COMPANY_ID_IN_INPUT",
                    "record": _safe_record_summary(raw),
                    "read_only": True,
                }
            )
            continue
        if raw_company_id:
            seen_company_ids.add(raw_company_id)
        try:
            record = _normalise_company_record(
                raw,
                as_of=as_of,
                input_scope=input_scope,
                source_project=source_project,
                coverage_claim=coverage_claim,
            )
        except SecurityMasterError as error:
            rejected.append(
                {
                    "record_index": index,
                    "reason": str(error),
                    "record": _safe_record_summary(raw),
                    "read_only": True,
                }
            )
            continue
        if record["company_id"] in seen_company_ids and record["company_id"] != raw_company_id:
            rejected.append(
                {
                    "record_index": index,
                    "company_id": record["company_id"],
                    "reason": "DUPLICATE_COMPANY_ID_IN_INPUT",
                    "record": _safe_record_summary(raw),
                    "read_only": True,
                }
            )
            continue
        seen_company_ids.add(record["company_id"])
        normalised_records.append(record)

    companies = _merge_company_projection(previous.get("companies", []), normalised_records)
    history, current_memberships, changes = _update_membership_history(
        previous.get("industry_membership_history", []),
        normalised_records,
        as_of=as_of,
        coverage_claim=coverage_claim,
    )
    status_counts = Counter(str(item["master_record_status"]) for item in companies)
    membership_counts = Counter(str(item["membership_state"]) for item in current_memberships)
    report_key = snapshot_id.strip() or str(payload.get("snapshot_id") or "")
    report_key = report_key or f"{as_of.isoformat()}-{_digest_ids(seen_company_ids)}"
    source_manifest = {
        "input_schema_version": input_schema,
        "source_project": source_project,
        "source_metadata": source_metadata,
        "input_snapshot_id": str(payload.get("snapshot_id") or ""),
        "input_as_of": str(payload.get("as_of") or payload.get("research_as_of") or ""),
        "previous_snapshot_id": str(previous.get("snapshot_id") or "") if previous else "",
    }
    return {
        "schema_version": SECURITY_MASTER_SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": f"security-master-{_safe_id(report_key)}",
        "as_of": as_of.isoformat(),
        "research_as_of": as_of.isoformat(),
        "data_cutoff_at": as_of.isoformat(),
        "rule_version": str(rule_version),
        "membership_rule_version": MEMBERSHIP_RULE_VERSION,
        "coverage_claim": coverage_claim,
        "input_scope": input_scope,
        "source_manifest": source_manifest,
        "companies": companies,
        "company_count": len(companies),
        "company_status_counts": dict(status_counts),
        "industry_membership_history": history,
        "current_memberships": current_memberships,
        "current_membership_count": len(current_memberships),
        "membership_state_counts": dict(membership_counts),
        "membership_changes": changes,
        "rejected_records": rejected,
        "rejected_record_count": len(rejected),
        "scope": {
            "light_security_master_only": True,
            "full_market_membership_loaded": coverage_claim == "FULL_MARKET",
            "full_market_deep_data_loaded": False,
            "deep_data_loaded": False,
            "bounded_pool_input": input_scope == "BOUNDED_POOL",
            "representative_research_candidates_in_master": False,
        },
        "policy": _policy(coverage_claim=coverage_claim),
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def validate_security_master_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Return a read-only validation report for a saved master snapshot."""

    if not isinstance(snapshot, Mapping):
        raise SecurityMasterError("snapshot must be an object")
    if snapshot.get("schema_version") != SECURITY_MASTER_SNAPSHOT_SCHEMA_VERSION:
        raise SecurityMasterError("input must be security-master-snapshot.v1")
    companies = snapshot.get("companies")
    history = snapshot.get("industry_membership_history")
    if not isinstance(companies, list) or not isinstance(history, list):
        raise SecurityMasterError("snapshot companies and history must be lists")
    as_of = _parse_date(str(snapshot.get("as_of") or ""), "snapshot.as_of")
    errors: list[str] = []
    company_ids = set()
    for index, company in enumerate(companies):
        if not isinstance(company, Mapping):
            errors.append(f"company[{index}] is not an object")
            continue
        company_id = str(company.get("company_id") or "").strip()
        if not company_id:
            errors.append(f"company[{index}] missing company_id")
        if company_id in company_ids:
            errors.append(f"duplicate company_id: {company_id}")
        company_ids.add(company_id)
        if company.get("deep_data_loaded") is True:
            errors.append(f"company[{index}] contains deep data")
    open_memberships: dict[tuple[str, str], int] = {}
    for index, membership in enumerate(history):
        if not isinstance(membership, Mapping):
            errors.append(f"membership[{index}] is not an object")
            continue
        company_id = str(membership.get("company_id") or "").strip()
        industry_id = str(membership.get("industry_id") or "").strip()
        start = _parse_date(
            str(membership.get("effective_from") or ""),
            f"membership[{index}].effective_from",
        )
        end_text = str(membership.get("effective_to") or "").strip()
        end = _parse_date(end_text, f"membership[{index}].effective_to", required=False)
        if end and start >= end:
            errors.append(f"membership[{index}] has non-positive effective interval")
        if end and end > as_of:
            errors.append(f"membership[{index}] ends after snapshot as_of")
        if not company_id or not industry_id:
            errors.append(f"membership[{index}] missing company_id or industry_id")
        if not end:
            key = (company_id, str(membership.get("membership_type") or ""))
            open_memberships[key] = open_memberships.get(key, 0) + 1
    duplicate_open = [key for key, count in open_memberships.items() if count > 1]
    errors.extend(
        f"multiple open memberships for company/type: {company_id}/{membership_type}"
        for company_id, membership_type in duplicate_open
        if membership_type == "PRIMARY"
    )
    return {
        "schema_version": "security-master-validation.v1",
        "snapshot_id": str(snapshot.get("snapshot_id") or ""),
        "as_of": as_of.isoformat(),
        "company_count": len(companies),
        "membership_count": len(history),
        "error_count": len(errors),
        "errors": errors,
        "status": "VALID" if not errors else "INVALID",
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def lookup_security_master_company(
    snapshot: Mapping[str, Any], identifier: str
) -> dict[str, Any]:
    """Perform an exact local identity lookup without treating bounded absence as exit."""

    if not isinstance(snapshot, Mapping):
        raise SecurityMasterError("security master snapshot must be an object")
    if snapshot.get("schema_version") != SECURITY_MASTER_SNAPSHOT_SCHEMA_VERSION:
        raise SecurityMasterError("input must be security-master-snapshot.v1")
    companies = snapshot.get("companies")
    if not isinstance(companies, list):
        raise SecurityMasterError("security master companies must be a list")
    query = _identity_key(identifier)
    if not query:
        raise SecurityMasterError("identifier must not be empty")
    exact: list[Mapping[str, Any]] = []
    code_matches: list[Mapping[str, Any]] = []
    for company in companies:
        if not isinstance(company, Mapping):
            continue
        identity_values = (
            company.get("company_id"),
            company.get("display_name"),
            company.get("legal_name"),
        )
        normalized_values = {_identity_key(value) for value in identity_values if _identity_key(value)}
        if query in normalized_values:
            exact.append(company)
        if _code_without_market(query) and _code_without_market(query) in {
            _code_without_market(value) for value in normalized_values
        }:
            code_matches.append(company)
    matches = exact or code_matches
    coverage = str(snapshot.get("coverage_claim") or "UNKNOWN").upper()
    if len(matches) == 1:
        company = dict(matches[0])
        return {
            "status": "MATCHED",
            "match_method": "EXACT" if exact else "CODE_WITHOUT_MARKET_UNIQUE",
            "company": company,
            "coverage_claim": coverage,
            "snapshot_id": str(snapshot.get("snapshot_id") or ""),
        }
    if len(matches) > 1:
        return {
            "status": "AMBIGUOUS",
            "match_method": "MULTIPLE_EXACT_MATCHES",
            "candidates": [
                {
                    "company_id": str(item.get("company_id") or ""),
                    "display_name": str(item.get("display_name") or ""),
                    "market": str(item.get("market") or ""),
                }
                for item in matches
            ],
            "coverage_claim": coverage,
            "snapshot_id": str(snapshot.get("snapshot_id") or ""),
        }
    return {
        "status": "NOT_FOUND",
        "match_method": "NO_EXACT_MATCH",
        "coverage_claim": coverage,
        "absence_is_not_exit": coverage != "FULL_MARKET",
        "snapshot_id": str(snapshot.get("snapshot_id") or ""),
    }


def _normalise_company_record(
    raw: Any,
    *,
    as_of: date,
    input_scope: str,
    source_project: str,
    coverage_claim: str,
) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise SecurityMasterError("company record must be an object")
    deep_fields = sorted(_DEEP_FIELDS.intersection(str(key).lower() for key in raw))
    if deep_fields:
        raise SecurityMasterError(
            "deep data fields are not allowed in lightweight security master: "
            + ", ".join(deep_fields)
        )
    company_id = str(
        raw.get("company_id") or raw.get("security_id") or raw.get("ticker") or ""
    ).strip()
    display_name = str(raw.get("display_name") or raw.get("short_name") or raw.get("name") or "").strip()
    market = str(raw.get("market") or raw.get("market_or_exchange") or raw.get("listing_market") or "").strip()
    if not company_id:
        raise SecurityMasterError("company_id is required")
    if not display_name:
        raise SecurityMasterError(f"display_name is required: {company_id}")
    if not market:
        raise SecurityMasterError(f"market is required and cannot be inferred: {company_id}")
    record_scope = str(raw.get("record_scope") or ("LIGHT_CANDIDATE" if input_scope == "BOUNDED_POOL" else "MASTER")).upper()
    if record_scope not in _RECORD_SCOPES:
        raise SecurityMasterError(f"unsupported record_scope: {record_scope}")
    if record_scope == "RESEARCH_REPRESENTATIVE":
        raise SecurityMasterError("RESEARCH_REPRESENTATIVE cannot enter security master")
    listing_status = str(raw.get("listing_status") or "UNKNOWN").upper()
    if listing_status not in _LISTING_STATUSES:
        raise SecurityMasterError(f"unsupported listing_status: {listing_status}")
    source_evidence_id = str(raw.get("source_evidence_id") or raw.get("evidence_id") or "").strip()
    source = str(raw.get("source") or raw.get("source_url") or "").strip()
    if not source_evidence_id:
        if not source:
            raise SecurityMasterError(f"source_evidence_id or source is required: {company_id}")
        source_evidence_id = "derived-source-" + sha256(
            f"{source}|{as_of.isoformat()}".encode("utf-8")
        ).hexdigest()[:20]
    industry_memberships = raw.get("industry_memberships")
    if industry_memberships is None:
        industry = raw.get("industry")
        industry_memberships = [industry] if isinstance(industry, Mapping) else []
    if not isinstance(industry_memberships, list):
        raise SecurityMasterError(f"industry_memberships must be a list: {company_id}")
    memberships = [
        _normalise_membership(
            item,
            company_id=company_id,
            as_of=as_of,
            default_evidence_id=source_evidence_id,
            default_source_project=source_project,
        )
        for item in industry_memberships
    ]
    primary_count = sum(item["membership_type"] == "PRIMARY" for item in memberships)
    if primary_count > 1:
        raise SecurityMasterError(f"multiple PRIMARY memberships: {company_id}")
    identity_complete = bool(company_id and display_name and market and listing_status != "UNKNOWN")
    return {
        "company_id": company_id,
        "display_name": display_name,
        "legal_name": str(raw.get("legal_name") or ""),
        "market": market,
        "listing_status": listing_status,
        "trading_status": str(raw.get("trading_status") or "UNKNOWN").upper(),
        "suspension_status": str(raw.get("suspension_status") or "UNKNOWN").upper(),
        "delisting_status": str(raw.get("delisting_status") or "UNKNOWN").upper(),
        "primary_industry_id": next(
            (item["industry_id"] for item in memberships if item["membership_type"] == "PRIMARY"),
            "",
        ),
        "industry_count": len(memberships),
        "industry_memberships": memberships,
        "membership_complete": bool(raw.get("membership_complete", False)),
        "record_scope": record_scope,
        "master_record_status": "READY" if identity_complete else "PARTIAL",
        "identity_status": "READY" if identity_complete else "PARTIAL",
        "source_evidence_id": source_evidence_id,
        "source": source,
        "source_project": str(raw.get("source_project") or source_project),
        "as_of": as_of.isoformat(),
        "retrieved_at": str(raw.get("retrieved_at") or ""),
        "deep_data_loaded": False,
        "field_lineage": _field_lineage(raw, source_evidence_id, source_project),
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "coverage_claim": coverage_claim,
    }


def _normalise_membership(
    raw: Any,
    *,
    company_id: str,
    as_of: date,
    default_evidence_id: str,
    default_source_project: str,
) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise SecurityMasterError(f"industry membership must be an object: {company_id}")
    industry_id = str(raw.get("industry_id") or raw.get("canonical_id") or "").strip()
    industry_name = str(raw.get("industry_name") or raw.get("display_name") or "").strip()
    if not industry_id:
        raise SecurityMasterError(f"industry_id is required: {company_id}")
    membership_type = str(raw.get("membership_type") or "PRIMARY").upper()
    if membership_type not in _MEMBERSHIP_TYPES:
        raise SecurityMasterError(f"unsupported membership_type: {membership_type}")
    confidence = str(raw.get("confidence") or "UNVERIFIED").upper()
    if confidence not in _CONFIDENCE:
        raise SecurityMasterError(f"unsupported confidence: {confidence}")
    source_evidence_id = str(raw.get("source_evidence_id") or default_evidence_id).strip()
    if not source_evidence_id:
        raise SecurityMasterError(f"membership source_evidence_id is required: {company_id}")
    effective_from = _parse_date(
        str(raw.get("effective_from") or as_of.isoformat()),
        f"membership {company_id}.effective_from",
    )
    if effective_from > as_of:
        raise SecurityMasterError(f"membership effective_from is after as_of: {company_id}")
    return {
        "company_id": company_id,
        "industry_id": industry_id,
        "industry_name": industry_name,
        "membership_type": membership_type,
        "effective_from": effective_from.isoformat(),
        "effective_to": "",
        "source_evidence_id": source_evidence_id,
        "source_project": str(raw.get("source_project") or default_source_project),
        "classification_source": str(raw.get("classification_source") or raw.get("source") or "").strip(),
        "classification_version": str(raw.get("classification_version") or "unknown"),
        "confidence": confidence,
        "manual_override_id": str(raw.get("manual_override_id") or "") or None,
        "membership_state": "ACTIVE",
        "membership_rule_version": MEMBERSHIP_RULE_VERSION,
        "read_only": True,
        "review_only": True,
    }


def _merge_company_projection(
    previous: Any,
    incoming: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    previous_items = previous if isinstance(previous, list) else []
    by_id: dict[str, dict[str, Any]] = {}
    for item in previous_items:
        if isinstance(item, Mapping) and str(item.get("company_id") or "").strip():
            by_id[str(item["company_id"])] = dict(item)
    for item in incoming:
        old = by_id.get(str(item["company_id"]))
        if old:
            merged = dict(old)
            merged.update(item)
            merged["previous_record_hash"] = _object_hash(old)
            by_id[str(item["company_id"])] = merged
        else:
            by_id[str(item["company_id"])] = dict(item)
    return [by_id[key] for key in sorted(by_id)]


def _update_membership_history(
    previous_history: Any,
    incoming_records: Sequence[Mapping[str, Any]],
    *,
    as_of: date,
    coverage_claim: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    history: list[dict[str, Any]] = [dict(item) for item in previous_history if isinstance(item, Mapping)]
    changes = Counter(opened=0, unchanged=0, closed=0, reopened=0, ignored_absence=0)
    incoming_by_company: dict[str, list[Mapping[str, Any]]] = {}
    complete_by_company: dict[str, bool] = {}
    for record in incoming_records:
        incoming_by_company[str(record["company_id"])] = list(record["industry_memberships"])
        complete_by_company[str(record["company_id"])] = bool(record.get("membership_complete"))
    for company_id, memberships in incoming_by_company.items():
        incoming_keys = {
            (str(item["industry_id"]), str(item["membership_type"])) for item in memberships
        }
        for membership in memberships:
            key = (company_id, str(membership["industry_id"]), str(membership["membership_type"]))
            open_index = _open_history_index(history, key)
            if open_index is not None:
                old = history[open_index]
                if old.get("source_evidence_id") != membership["source_evidence_id"]:
                    old["latest_source_evidence_id"] = membership["source_evidence_id"]
                    old["latest_classification_version"] = membership["classification_version"]
                    old["latest_confidence"] = membership["confidence"]
                    old["last_observed_at"] = as_of.isoformat()
                changes["unchanged"] += 1
            else:
                closed_index = _closed_history_index(history, key, as_of)
                item = dict(membership)
                item["membership_id"] = _membership_id(key, membership["effective_from"], membership["source_evidence_id"])
                if closed_index is not None:
                    changes["reopened"] += 1
                else:
                    changes["opened"] += 1
                history.append(item)
        # A company's explicit current primary classification supersedes its
        # prior primary relationship even when the overall feed is bounded.
        primary_ids = {key[0] for key in incoming_keys if key[1] == "PRIMARY"}
        for index, old in enumerate(history):
            if str(old.get("company_id") or "") != company_id or old.get("effective_to"):
                continue
            membership_type = str(old.get("membership_type") or "")
            old_key = (str(old.get("industry_id") or ""), membership_type)
            should_close = old_key not in incoming_keys and (
                membership_type == "PRIMARY" and bool(primary_ids)
            )
            if should_close:
                history[index] = _close_membership(old, as_of)
                changes["closed"] += 1
        if complete_by_company.get(company_id, False):
            for index, old in enumerate(history):
                if (
                    str(old.get("company_id") or "") == company_id
                    and not old.get("effective_to")
                    and (str(old.get("industry_id") or ""), str(old.get("membership_type") or "")) not in incoming_keys
                ):
                    history[index] = _close_membership(old, as_of)
                    changes["closed"] += 1

    if coverage_claim == "FULL_MARKET":
        incoming_ids = set(incoming_by_company)
        for index, old in enumerate(history):
            if not old.get("effective_to") and str(old.get("company_id") or "") not in incoming_ids:
                history[index] = _close_membership(old, as_of)
                changes["closed"] += 1
    else:
        changes["ignored_absence"] = max(0, len({str(item.get("company_id") or "") for item in history if not item.get("effective_to")}) - len(incoming_by_company))

    history.sort(key=lambda item: (str(item.get("company_id") or ""), str(item.get("effective_from") or ""), str(item.get("membership_type") or ""), str(item.get("industry_id") or "")))
    current = [
        dict(item)
        for item in history
        if not str(item.get("effective_to") or "").strip()
    ]
    return history, current, dict(changes)


def _records_from_company_pool(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise SecurityMasterError("company pool candidates must be a list")
    industry = payload.get("industry") or {}
    if not isinstance(industry, Mapping):
        industry = {}
    source = payload.get("source") or {}
    source_url = str(source.get("endpoint") or source.get("provider") or "company_pool") if isinstance(source, Mapping) else "company_pool"
    output: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            output.append(candidate)
            continue
        profile = candidate.get("light_profile") or {}
        if not isinstance(profile, Mapping):
            profile = {}
        reported_industry = str(profile.get("reported_industry") or "").strip()
        industry_name = reported_industry or str(industry.get("display_name") or "").strip()
        output.append(
            {
                "company_id": candidate.get("company_id"),
                "display_name": candidate.get("display_name") or profile.get("legal_name"),
                "legal_name": profile.get("legal_name"),
                "market": profile.get("listing_market"),
                "listing_status": "UNKNOWN",
                "record_scope": "LIGHT_CANDIDATE",
                "source": profile.get("source") or candidate.get("source") or source_url,
                "source_project": str((source.get("provider") if isinstance(source, Mapping) else "") or "company_pool"),
                "source_evidence_id": str(profile.get("evidence_id") or ""),
                "retrieved_at": str(profile.get("retrieved_at") or ""),
                "industry_memberships": [
                    {
                        "industry_id": str(industry.get("industry_id") or candidate.get("industry_id") or ""),
                        "industry_name": industry_name,
                        "membership_type": "PRIMARY",
                        "classification_source": str(profile.get("field_sources", {}).get("reported_industry") or profile.get("source") or ""),
                        "classification_version": str(industry.get("classification_version") or "unknown"),
                        "confidence": "MEDIUM" if profile.get("status") == "VERIFIED" else "UNVERIFIED",
                    }
                ],
            }
        )
    return output


def _empty_candidate_boundary_report(
    payload: Mapping[str, Any],
    *,
    as_of: date,
    previous: Mapping[str, Any],
    snapshot_id: str,
    rule_version: str,
) -> dict[str, Any]:
    previous_companies = list(previous.get("companies") or [])
    previous_history = list(previous.get("industry_membership_history") or [])
    key = snapshot_id.strip() or str(payload.get("import_id") or as_of.isoformat())
    return {
        "schema_version": SECURITY_MASTER_SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": f"security-master-{_safe_id(key)}",
        "as_of": as_of.isoformat(),
        "research_as_of": as_of.isoformat(),
        "data_cutoff_at": as_of.isoformat(),
        "rule_version": rule_version,
        "membership_rule_version": MEMBERSHIP_RULE_VERSION,
        "coverage_claim": "UNKNOWN",
        "input_scope": "RESEARCH_CANDIDATE_SET",
        "source_manifest": {"input_schema_version": RESEARCH_CANDIDATE_SET_SCHEMA_VERSION, "input_import_id": str(payload.get("import_id") or "")},
        "companies": previous_companies,
        "company_count": len(previous_companies),
        "company_status_counts": dict(Counter(str(item.get("master_record_status") or "UNKNOWN") for item in previous_companies if isinstance(item, Mapping))),
        "industry_membership_history": previous_history,
        "current_memberships": [item for item in previous_history if isinstance(item, Mapping) and not item.get("effective_to")],
        "current_membership_count": sum(1 for item in previous_history if isinstance(item, Mapping) and not item.get("effective_to")),
        "membership_state_counts": {},
        "membership_changes": {"opened": 0, "unchanged": 0, "closed": 0, "reopened": 0, "ignored_absence": 0},
        "rejected_records": [{"reason": "RESEARCH_CANDIDATE_SET_NOT_SECURITY_MASTER", "source_project": payload.get("source_project"), "import_id": payload.get("import_id")}],
        "rejected_record_count": 1,
        "scope": {"light_security_master_only": True, "full_market_membership_loaded": False, "full_market_deep_data_loaded": False, "deep_data_loaded": False, "bounded_pool_input": False, "representative_research_candidates_in_master": False},
        "policy": _policy(coverage_claim="UNKNOWN"),
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _validate_previous(previous: Mapping[str, Any] | None, as_of: date) -> Mapping[str, Any]:
    if previous is None:
        return {}
    if not isinstance(previous, Mapping) or previous.get("schema_version") != SECURITY_MASTER_SNAPSHOT_SCHEMA_VERSION:
        raise SecurityMasterError("previous snapshot must be security-master-snapshot.v1")
    previous_as_of = _parse_date(str(previous.get("as_of") or ""), "previous.as_of")
    if previous_as_of > as_of:
        raise SecurityMasterError("previous snapshot as_of cannot be after current as_of")
    if not isinstance(previous.get("companies"), list) or not isinstance(previous.get("industry_membership_history"), list):
        raise SecurityMasterError("previous snapshot companies and history must be lists")
    return previous


def _open_history_index(history: Sequence[Mapping[str, Any]], key: tuple[str, str, str]) -> int | None:
    company_id, industry_id, membership_type = key
    for index, item in enumerate(history):
        if (
            str(item.get("company_id") or "") == company_id
            and str(item.get("industry_id") or "") == industry_id
            and str(item.get("membership_type") or "") == membership_type
            and not str(item.get("effective_to") or "").strip()
        ):
            return index
    return None


def _closed_history_index(history: Sequence[Mapping[str, Any]], key: tuple[str, str, str], as_of: date) -> int | None:
    company_id, industry_id, membership_type = key
    for index, item in enumerate(history):
        if (
            str(item.get("company_id") or "") == company_id
            and str(item.get("industry_id") or "") == industry_id
            and str(item.get("membership_type") or "") == membership_type
            and str(item.get("effective_to") or "") == as_of.isoformat()
        ):
            return index
    return None


def _close_membership(item: Mapping[str, Any], as_of: date) -> dict[str, Any]:
    closed = dict(item)
    closed["effective_to"] = as_of.isoformat()
    closed["membership_state"] = "CLOSED"
    closed["closed_at"] = as_of.isoformat()
    return closed


def _membership_id(key: tuple[str, str, str], effective_from: str, source_evidence_id: str) -> str:
    value = "|".join((*key, effective_from, source_evidence_id))
    return "membership-" + sha256(value.encode("utf-8")).hexdigest()[:20]


def _field_lineage(raw: Mapping[str, Any], evidence_id: str, source_project: str) -> dict[str, Any]:
    fields = ("company_id", "display_name", "legal_name", "market", "listing_status", "trading_status", "suspension_status", "delisting_status")
    return {
        field: {
            "source_field": field,
            "value_hash": _value_hash(raw.get(field)),
            "source_evidence_id": evidence_id,
            "source_project": str(raw.get("source_project") or source_project),
            "reuse_strategy": "REUSE_WITH_CHECK" if field in {"market", "listing_status"} else "DIRECT_REUSE",
            "validation_status": "CANDIDATE",
        }
        for field in fields
        if raw.get(field) not in (None, "", [], {})
    }


def _safe_record_summary(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        return {"type": type(raw).__name__}
    return {key: raw.get(key) for key in ("company_id", "display_name", "market", "record_scope") if key in raw}


def _policy(*, coverage_claim: str) -> dict[str, Any]:
    return {
        "light_fields_only": True,
        "coverage_claim": coverage_claim,
        "full_market_deep_data_forbidden": True,
        "market_not_inferred_from_code": True,
        "industry_membership_effective_dated": True,
        "bounded_pool_absence_does_not_close_membership": True,
        "research_representative_not_security_master": True,
        "previous_snapshot_preserved": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _identity_key(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", str(value or "").strip()).upper()


def _code_without_market(value: str) -> str:
    return re.sub(r"\.?(?:SH|SZ|BJ|HK)$", "", str(value or "").upper())


def _parse_date(value: str, field: str, *, required: bool = True) -> date | None:
    text = str(value or "").strip()
    if not text:
        if required:
            raise SecurityMasterError(f"{field} is required")
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        match = _DATE_RE.search(text)
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                pass
    raise SecurityMasterError(f"invalid {field}: {value}")


def _value_hash(value: Any) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _object_hash(value: Any) -> str:
    return _value_hash(value)[:20]


def _digest_ids(values: Sequence[str] | set[str]) -> str:
    return sha256("|".join(sorted(values)).encode("utf-8")).hexdigest()[:12] if values else "empty"


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_.-]+", "-", str(value)).strip("-")
    return cleaned or "snapshot"


def _date_from_snapshot_id(value: str) -> str:
    match = _DATE_RE.search(value)
    return "-".join(match.groups()) if match else ""
