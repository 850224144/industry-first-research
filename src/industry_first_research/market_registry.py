"""Versioned market, currency, timezone, and calendar contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
from typing import Any


class MarketRegistryError(ValueError):
    """Raised when a market registry or reference cannot be resolved."""


MARKET_REGISTRY_SCHEMA_VERSION = "market-registry.v1"
MARKET_REFERENCE_SCHEMA_VERSION = "market-reference.v1"
RULE_VERSION = "market-registry-rules.v1"
_REQUIRED = ("market_id", "display_name", "asset_class", "currency", "timezone", "calendar_version")
_ASSET_CLASSES = {"EQUITY", "INDEX", "FUTURES", "SPOT", "OTHER"}


class MarketRegistry:
    """Resolve only explicitly configured market references."""

    def __init__(self, markets: Sequence[Mapping[str, Any]], *, registry_id: str = "default", version: str = "") -> None:
        if isinstance(markets, (str, bytes, bytearray)) or not isinstance(markets, Sequence) or not markets:
            raise MarketRegistryError("markets must be a non-empty list")
        self.registry_id = str(registry_id or "default").strip()
        self.version = str(version or "").strip()
        if not self.registry_id or not self.version:
            raise MarketRegistryError("registry_id and version are required")
        self._markets: dict[str, dict[str, Any]] = {}
        for raw in markets:
            normalized = _normalize_market(raw)
            market_id = normalized["market_id"]
            if market_id in self._markets:
                raise MarketRegistryError(f"duplicate market_id: {market_id}")
            self._markets[market_id] = normalized
        self.content_hash = _hash_payload({"registry_id": self.registry_id, "version": self.version, "markets": self._markets})

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "MarketRegistry":
        if not isinstance(payload, Mapping) or payload.get("schema_version") != MARKET_REGISTRY_SCHEMA_VERSION:
            raise MarketRegistryError("input must be market-registry.v1")
        return cls(
            payload.get("markets") or [],
            registry_id=str(payload.get("registry_id") or "default"),
            version=str(payload.get("version") or ""),
        )

    def resolve(self, market_id: str) -> dict[str, Any]:
        key = str(market_id or "").strip().upper()
        if key not in self._markets:
            raise MarketRegistryError(f"market is not configured: {market_id}")
        return dict(self._markets[key])

    def reference(self, market_id: str, *, reference_id: str = "") -> dict[str, Any]:
        market = self.resolve(market_id)
        return {
            "schema_version": MARKET_REFERENCE_SCHEMA_VERSION,
            "reference_id": reference_id.strip() or f"market-reference-{market['market_id']}-{self.version}",
            "market": market,
            "registry_id": self.registry_id,
            "registry_version": self.version,
            "registry_hash": self.content_hash,
            "immutable": True,
            "read_only": True,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
        }

    def to_report(self) -> dict[str, Any]:
        return {
            "schema_version": MARKET_REGISTRY_SCHEMA_VERSION,
            "registry_id": self.registry_id,
            "version": self.version,
            "market_count": len(self._markets),
            "markets": [dict(self._markets[key]) for key in sorted(self._markets)],
            "content_hash": self.content_hash,
            "rule_version": RULE_VERSION,
            "immutable": True,
            "read_only": True,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
        }


def build_market_registry_report(payload: Mapping[str, Any]) -> dict[str, Any]:
    return MarketRegistry.from_payload(payload).to_report()


def validate_market_reference(
    reference: Mapping[str, Any],
    registry: MarketRegistry,
) -> dict[str, Any]:
    if not isinstance(reference, Mapping) or reference.get("schema_version") != MARKET_REFERENCE_SCHEMA_VERSION:
        raise MarketRegistryError("input must be market-reference.v1")
    errors: list[str] = []
    try:
        expected = registry.reference(str((reference.get("market") or {}).get("market_id") or ""))
        if reference.get("registry_id") != expected["registry_id"]:
            errors.append("registry_id does not match")
        if reference.get("registry_version") != expected["registry_version"]:
            errors.append("registry_version does not match")
        if reference.get("registry_hash") != expected["registry_hash"]:
            errors.append("registry_hash does not match")
        if reference.get("market") != expected["market"]:
            errors.append("market definition does not match registry")
    except MarketRegistryError as error:
        errors.append(str(error))
    return {
        "schema_version": "market-reference-validation.v1",
        "reference_id": str(reference.get("reference_id") or ""),
        "status": "VALID" if not errors else "INVALID",
        "errors": errors,
        "error_count": len(errors),
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _normalize_market(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise MarketRegistryError("each market must be an object")
    missing = [field for field in _REQUIRED if not str(raw.get(field) or "").strip()]
    if missing:
        raise MarketRegistryError("market missing fields: " + ", ".join(missing))
    market_id = str(raw["market_id"]).strip().upper()
    asset_class = str(raw["asset_class"]).strip().upper()
    if asset_class not in _ASSET_CLASSES:
        raise MarketRegistryError(f"unsupported asset_class: {asset_class}")
    timezone = str(raw["timezone"]).strip()
    currency = str(raw["currency"]).strip().upper()
    return {
        "market_id": market_id,
        "display_name": str(raw["display_name"]).strip(),
        "asset_class": asset_class,
        "currency": currency,
        "timezone": timezone,
        "calendar_version": str(raw["calendar_version"]).strip(),
        "exchange_code": str(raw.get("exchange_code") or market_id).strip().upper(),
        "price_conventions": dict(raw.get("price_conventions") or {}),
        "corporate_action_conventions": dict(raw.get("corporate_action_conventions") or {}),
        "source_evidence_ids": _string_list(raw.get("source_evidence_ids")),
    }


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise MarketRegistryError("source_evidence_ids must be a string list")
    return [str(item).strip() for item in value if str(item).strip()]


def _hash_payload(payload: Mapping[str, Any]) -> str:
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
