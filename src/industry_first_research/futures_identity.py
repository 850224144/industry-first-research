"""Identify domestic futures varieties, contracts, and research-only series."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
import re
from typing import Any


FUTURES_INPUT_SCHEMA_VERSION = "futures-object-input.v1"
FUTURES_IDENTITY_SCHEMA_VERSION = "futures-object-identity.v1"
RULE_VERSION = "futures-object-identity-rules.v1"

_EXCHANGES = {"SHFE", "DCE", "CZCE", "INE", "GFEX"}
_OBJECT_TYPES = {
    "futures_variety",
    "futures_contract",
    "continuous_series",
    "spot_benchmark",
}
_REQUIRED_CONTRACT_FIELDS = (
    "contract_code",
    "contract_month",
    "last_trade_date",
    "contract_multiplier",
    "tick_size",
    "settlement_basis",
)
_RULE_FIELDS = (
    "main_contract_rule",
    "roll_rule",
    "stitching_rule",
    "adjustment_rule",
    "components",
)


class FuturesIdentityError(ValueError):
    """Raised when a futures identity input cannot be classified safely."""


def identify_futures_object(
    payload: Mapping[str, Any],
    *,
    identity_id: str = "",
) -> dict[str, Any]:
    """Validate a futures object without inferring missing exchange metadata."""

    _validate_input(payload)
    object_type = str(payload.get("object_type") or "").strip().lower()
    if object_type not in _OBJECT_TYPES:
        raise FuturesIdentityError(
            "object_type must be futures_variety, futures_contract, continuous_series, or spot_benchmark"
        )
    as_of = _parse_date(payload.get("as_of"), "as_of")
    exchange = str(payload.get("exchange") or "").strip().upper()
    variety_id = str(payload.get("variety_id") or "").strip()
    variety_name = str(payload.get("variety_name") or "").strip()
    if not exchange:
        return _blocked(payload, object_type, "exchange is required")
    if exchange not in _EXCHANGES:
        return _blocked(payload, object_type, f"unsupported domestic futures exchange: {exchange}")
    if not variety_id and not variety_name:
        return _blocked(payload, object_type, "variety_id or variety_name is required")

    missing: list[str] = []
    warnings: list[str] = []
    identity_key = str(identity_id or payload.get("identity_id") or "").strip()
    contract = payload.get("contract") or {}
    if not isinstance(contract, Mapping):
        raise FuturesIdentityError("contract must be an object")
    series_rule = payload.get("continuous_series_rule")
    if series_rule is not None and not isinstance(series_rule, Mapping):
        raise FuturesIdentityError("continuous_series_rule must be an object")

    if object_type == "futures_contract":
        missing.extend(field for field in _REQUIRED_CONTRACT_FIELDS if not contract.get(field))
        contract_code = str(contract.get("contract_code") or payload.get("contract_code") or "").strip().upper()
        if not contract_code:
            missing.append("contract_code")
        if contract_code in {"CONTINUOUS", "MAIN", "主力"}:
            return _blocked(payload, object_type, "continuous or main symbols cannot be a simulated contract")
        if contract_code and not _looks_like_contract_code(contract_code):
            warnings.append("contract_code format is unverified; exchange master data must confirm it")
        if contract.get("last_trade_date"):
            last_trade_date = _parse_date(contract["last_trade_date"], "contract.last_trade_date")
            if last_trade_date < as_of:
                warnings.append("contract is expired at as_of")
        if not contract.get("rule_version"):
            missing.append("contract.rule_version")
    elif object_type == "continuous_series":
        if not isinstance(series_rule, Mapping):
            return _blocked(payload, object_type, "continuous_series_rule is required")
        missing.extend(field for field in _RULE_FIELDS if not series_rule.get(field))
        if isinstance(series_rule.get("components"), Sequence) and not isinstance(
            series_rule["components"], (str, bytes, bytearray)
        ):
            _validate_components(series_rule["components"], as_of)
        if series_rule.get("rule_published_at"):
            if _parse_datetime(series_rule["rule_published_at"], "rule_published_at").date() > as_of:
                return _blocked(payload, object_type, "continuous series rule was not public at as_of")
        warnings.append("continuous series is research-only and cannot bind a simulation order")
    elif object_type == "spot_benchmark":
        if not payload.get("spot_unit"):
            missing.append("spot_unit")
        if not payload.get("spot_region"):
            warnings.append("spot_region is missing; comparability may be limited")
        warnings.append("spot benchmark is not a futures contract and cannot be simulated")
    else:
        if not payload.get("industry_chain"):
            missing.append("industry_chain")

    if missing:
        status = "PARTIAL" if object_type in {"futures_variety", "spot_benchmark"} else "INSUFFICIENT"
    else:
        status = "READY"
    if not identity_key:
        identity_key = _default_identity_key(object_type, exchange, variety_id, variety_name, contract, series_rule)
    simulation_allowed = object_type == "futures_contract" and status == "READY"
    return {
        "schema_version": FUTURES_IDENTITY_SCHEMA_VERSION,
        "identity_id": f"futures-identity-{identity_key}",
        "object_type": object_type,
        "status": status,
        "as_of": str(payload["as_of"]),
        "exchange": exchange,
        "variety_id": variety_id,
        "variety_name": variety_name,
        "contract": dict(contract),
        "continuous_series_rule": dict(series_rule) if isinstance(series_rule, Mapping) else None,
        "industry_chain": payload.get("industry_chain"),
        "missing_fields": list(dict.fromkeys(missing)),
        "warnings": list(dict.fromkeys(warnings)),
        "research_only": object_type in {"continuous_series", "spot_benchmark"},
        "simulation_allowed": simulation_allowed,
        "rule_version": RULE_VERSION,
        "policy": {
            "exchange_not_inferred": True,
            "continuous_series_not_tradeable": object_type == "continuous_series",
            "specific_contract_required_for_simulation": True,
            "future_rule_data_rejected": True,
            "read_only": True,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _blocked(payload: Mapping[str, Any], object_type: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": FUTURES_IDENTITY_SCHEMA_VERSION,
        "identity_id": "futures-identity-blocked",
        "object_type": object_type,
        "status": "BLOCKED",
        "as_of": str(payload.get("as_of") or ""),
        "exchange": str(payload.get("exchange") or "").upper(),
        "variety_id": str(payload.get("variety_id") or ""),
        "variety_name": str(payload.get("variety_name") or ""),
        "contract": dict(payload.get("contract") or {}) if isinstance(payload.get("contract") or {}, Mapping) else {},
        "continuous_series_rule": None,
        "missing_fields": [],
        "warnings": [],
        "blockers": [reason],
        "research_only": object_type != "futures_contract",
        "simulation_allowed": False,
        "rule_version": RULE_VERSION,
        "policy": {
            "specific_contract_required_for_simulation": True,
            "continuous_series_not_tradeable": object_type == "continuous_series",
            "read_only": True,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _validate_input(value: Any) -> None:
    if not isinstance(value, Mapping) or value.get("schema_version") != FUTURES_INPUT_SCHEMA_VERSION:
        raise FuturesIdentityError(f"input must be {FUTURES_INPUT_SCHEMA_VERSION}")


def _validate_components(value: Sequence[Any], as_of: date) -> None:
    if not value:
        raise FuturesIdentityError("continuous series components must not be empty")
    for index, component in enumerate(value):
        if not isinstance(component, Mapping):
            raise FuturesIdentityError(f"continuous component {index} must be an object")
        if not component.get("contract_code") and not component.get("contract_id"):
            raise FuturesIdentityError(f"continuous component {index} has no contract identity")
        if component.get("valid_from"):
            valid_from = _parse_date(component["valid_from"], f"components[{index}].valid_from")
            if valid_from > as_of:
                raise FuturesIdentityError(
                    f"continuous component valid_from is after as_of: {valid_from.isoformat()}"
                )
        if component.get("valid_to"):
            _parse_date(component["valid_to"], f"components[{index}].valid_to")


def _default_identity_key(
    object_type: str,
    exchange: str,
    variety_id: str,
    variety_name: str,
    contract: Mapping[str, Any],
    series_rule: Mapping[str, Any] | None,
) -> str:
    if object_type == "futures_contract":
        suffix = str(contract.get("contract_code") or "unknown").strip().upper()
    elif object_type == "continuous_series":
        suffix = str((series_rule or {}).get("rule_version") or "rule-unknown")
    else:
        suffix = variety_id or variety_name
    return "-".join(item for item in (exchange, suffix) if item).replace(" ", "-")


def _looks_like_contract_code(value: str) -> bool:
    # Covers SHFE/DCE/INE/GFEX codes and CZCE's one-digit year convention;
    # exact contract validity still belongs to exchange master data.
    return bool(re.fullmatch(r"[A-Z]{1,4}\d{3,4}", value))


def _parse_datetime(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise FuturesIdentityError(f"{field} is required")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise FuturesIdentityError(f"{field} must be ISO datetime") from error


def _parse_date(value: Any, field: str) -> date:
    text = str(value or "").strip()
    if not text:
        raise FuturesIdentityError(f"{field} is required")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text)
        except ValueError as error:
            raise FuturesIdentityError(f"{field} must be ISO date/datetime") from error
