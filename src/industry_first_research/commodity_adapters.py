"""Configuration-driven commodity futures adapter registry.

Commodity adapters describe the questions and data contract for a variety;
they do not fetch market data or decide a direction.  This keeps a copper,
steel, chemical, agricultural, or new-energy-material adapter small and
replaceable while the evidence, futures identity, and report layers remain
shared.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any


class CommodityAdapterError(ValueError):
    """Raised when a commodity adapter definition or validation input is invalid."""


COMMODITY_ADAPTER_SCHEMA_VERSION = "commodity-adapter.v1"
ADAPTER_VALIDATION_SCHEMA_VERSION = "commodity-adapter-validation.v1"
COMMODITY_ADAPTER_REGISTRY_SCHEMA_VERSION = "commodity-adapter-registry.v1"
FUTURES_REPORT_SCHEMA_VERSION = "futures-fundamentals-report.v1"
FUTURES_INPUT_SCHEMA_VERSION = "futures-fundamentals-input.v1"
RULE_VERSION = "commodity-adapter-rules.v1"

REQUIRED_FUNDAMENTAL_FIELDS = (
    "supply_demand_balance",
    "production_and_utilization",
    "imports_exports",
    "inventory_by_location",
    "exchange_inventory_and_warrants",
    "spot_benchmark",
    "production_and_import_cost",
    "industry_margin",
    "basis_and_calendar_spread",
    "term_structure",
    "seasonality",
    "open_interest_and_available_member_positions",
    "delivery_rules_and_warrant_expiry",
)

_REQUIRED_TOP_LEVEL = (
    "adapter_id",
    "display_name",
    "aliases",
    "exchanges",
    "variety_ids",
    "commodity_category",
    "quote_unit",
    "trading_unit",
    "spot_benchmarks",
    "indicator_groups",
    "inventory_locations",
    "cost_components",
    "margin_components",
    "seasonality",
    "delivery_rules",
    "scenario_method",
    "acceptance_samples",
)


@dataclass(frozen=True)
class CommodityAdapterDefinition:
    """An immutable, validated description of one commodity variety family."""

    adapter_id: str
    display_name: str
    aliases: tuple[str, ...]
    exchanges: tuple[str, ...]
    variety_ids: tuple[str, ...]
    commodity_category: str
    quote_unit: str
    trading_unit: str
    spot_benchmarks: tuple[dict[str, Any], ...]
    indicator_groups: dict[str, tuple[str, ...]]
    inventory_locations: tuple[str, ...]
    cost_components: tuple[str, ...]
    margin_components: tuple[str, ...]
    seasonality: dict[str, Any]
    delivery_rules: dict[str, Any]
    scenario_method: dict[str, Any]
    acceptance_samples: tuple[dict[str, Any], ...]
    rule_version: str = RULE_VERSION

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CommodityAdapterDefinition":
        _validate_definition_shape(payload)
        adapter_id = _text(payload["adapter_id"], "adapter_id")
        display_name = _text(payload["display_name"], "display_name")
        aliases = _text_list(payload["aliases"], "aliases")
        exchanges = tuple(value.upper() for value in _text_list(payload["exchanges"], "exchanges"))
        variety_ids = tuple(value.upper() for value in _text_list(payload["variety_ids"], "variety_ids"))
        category = _text(payload["commodity_category"], "commodity_category")
        quote_unit = _text(payload["quote_unit"], "quote_unit")
        trading_unit = _text(payload["trading_unit"], "trading_unit")
        benchmarks = _normalise_benchmarks(payload["spot_benchmarks"])
        indicator_groups = _normalise_indicator_groups(payload["indicator_groups"])
        inventory_locations = tuple(
            _text_list(payload["inventory_locations"], "inventory_locations")
        )
        cost_components = tuple(_text_list(payload["cost_components"], "cost_components"))
        margin_components = tuple(_text_list(payload["margin_components"], "margin_components"))
        seasonality = _object(payload["seasonality"], "seasonality")
        delivery_rules = _object(payload["delivery_rules"], "delivery_rules")
        scenario_method = _object(payload["scenario_method"], "scenario_method")
        samples = _normalise_samples(payload["acceptance_samples"])
        rule_version = _text(payload.get("rule_version") or RULE_VERSION, "rule_version")

        _validate_definition_values(
            adapter_id=adapter_id,
            aliases=aliases,
            exchanges=exchanges,
            variety_ids=variety_ids,
            indicator_groups=indicator_groups,
            benchmarks=benchmarks,
            inventory_locations=inventory_locations,
            cost_components=cost_components,
            margin_components=margin_components,
            seasonality=seasonality,
            delivery_rules=delivery_rules,
            scenario_method=scenario_method,
            samples=samples,
        )
        return cls(
            adapter_id=adapter_id,
            display_name=display_name,
            aliases=aliases,
            exchanges=exchanges,
            variety_ids=variety_ids,
            commodity_category=category,
            quote_unit=quote_unit,
            trading_unit=trading_unit,
            spot_benchmarks=tuple(benchmarks),
            indicator_groups={key: tuple(value) for key, value in indicator_groups.items()},
            inventory_locations=inventory_locations,
            cost_components=cost_components,
            margin_components=margin_components,
            seasonality=seasonality,
            delivery_rules=delivery_rules,
            scenario_method=scenario_method,
            acceptance_samples=tuple(samples),
            rule_version=rule_version,
        )

    @property
    def required_fields(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                field
                for group in self.indicator_groups.values()
                for field in group
            )
        )

    def matches(self, identifier: str) -> bool:
        key = _normalise_key(identifier)
        return key in {
            _normalise_key(value)
            for value in (self.adapter_id, *self.aliases, *self.variety_ids)
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": COMMODITY_ADAPTER_SCHEMA_VERSION,
            "adapter_id": self.adapter_id,
            "display_name": self.display_name,
            "aliases": list(self.aliases),
            "exchanges": list(self.exchanges),
            "variety_ids": list(self.variety_ids),
            "commodity_category": self.commodity_category,
            "quote_unit": self.quote_unit,
            "trading_unit": self.trading_unit,
            "spot_benchmarks": [dict(value) for value in self.spot_benchmarks],
            "indicator_groups": {
                key: list(value) for key, value in self.indicator_groups.items()
            },
            "inventory_locations": list(self.inventory_locations),
            "cost_components": list(self.cost_components),
            "margin_components": list(self.margin_components),
            "seasonality": dict(self.seasonality),
            "delivery_rules": dict(self.delivery_rules),
            "scenario_method": dict(self.scenario_method),
            "acceptance_samples": [dict(value) for value in self.acceptance_samples],
            "rule_version": self.rule_version,
        }


class CommodityAdapterRegistry:
    """Resolve commodity adapters by ID, alias, or variety code."""

    def __init__(self, definitions: Sequence[CommodityAdapterDefinition] = ()) -> None:
        self._definitions: dict[str, CommodityAdapterDefinition] = {}
        self._lookup: dict[str, str] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: CommodityAdapterDefinition) -> None:
        if not isinstance(definition, CommodityAdapterDefinition):
            raise CommodityAdapterError("registry accepts CommodityAdapterDefinition objects")
        adapter_key = _normalise_key(definition.adapter_id)
        if adapter_key in self._definitions:
            raise CommodityAdapterError(f"duplicate adapter_id: {definition.adapter_id}")
        for identifier in (definition.adapter_id, *definition.aliases, *definition.variety_ids):
            key = _normalise_key(identifier)
            existing = self._lookup.get(key)
            if existing is not None:
                raise CommodityAdapterError(
                    f"adapter identifier is ambiguous: {identifier} -> {existing}"
                )
        self._definitions[adapter_key] = definition
        for identifier in (definition.adapter_id, *definition.aliases, *definition.variety_ids):
            self._lookup[_normalise_key(identifier)] = adapter_key

    def resolve(self, identifier: str) -> CommodityAdapterDefinition:
        key = _normalise_key(identifier)
        adapter_key = self._lookup.get(key)
        if adapter_key is None:
            raise CommodityAdapterError(f"commodity adapter not found: {identifier}")
        return self._definitions[adapter_key]

    def list(self) -> list[CommodityAdapterDefinition]:
        return [self._definitions[key] for key in sorted(self._definitions)]

    @classmethod
    def from_directory(cls, directory: str | Path) -> "CommodityAdapterRegistry":
        root = Path(directory)
        if not root.exists():
            raise CommodityAdapterError(f"commodity adapter directory does not exist: {root}")
        if not root.is_dir():
            raise CommodityAdapterError(f"commodity adapter path is not a directory: {root}")
        paths = sorted(root.glob("*.json"))
        if not paths:
            raise CommodityAdapterError(f"commodity adapter directory has no JSON files: {root}")
        definitions = []
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise CommodityAdapterError(f"unable to read adapter {path}: {error}") from error
            try:
                definitions.append(CommodityAdapterDefinition.from_mapping(payload))
            except CommodityAdapterError as error:
                raise CommodityAdapterError(f"invalid adapter {path}: {error}") from error
        return cls(definitions)


def build_commodity_adapter_registry_report(
    registry: CommodityAdapterRegistry,
    *,
    registry_id: str = "",
) -> dict[str, Any]:
    """Render a read-only registry manifest without running any market logic."""

    if not isinstance(registry, CommodityAdapterRegistry):
        raise CommodityAdapterError("registry must be a CommodityAdapterRegistry")
    identifier = registry_id.strip() or "default"
    adapters = registry.list()
    return {
        "schema_version": COMMODITY_ADAPTER_REGISTRY_SCHEMA_VERSION,
        "registry_id": f"commodity-adapter-registry-{identifier}",
        "adapter_count": len(adapters),
        "adapters": [adapter.to_dict() for adapter in adapters],
        "policy": {
            "configuration_only": True,
            "data_fetched": False,
            "directional_conclusion": False,
            "investment_conclusion": False,
            "decision_snapshot_created": False,
            "automatic_order_included": False,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def build_commodity_adapter_validation_report(
    adapter: CommodityAdapterDefinition,
    *,
    futures_report: Mapping[str, Any] | None = None,
    fundamentals_input: Mapping[str, Any] | None = None,
    validation_id: str = "",
) -> dict[str, Any]:
    """Validate an adapter against an optional identity/report/input package."""

    if not isinstance(adapter, CommodityAdapterDefinition):
        raise CommodityAdapterError("adapter must be a CommodityAdapterDefinition")
    if futures_report is not None:
        _validate_futures_report(futures_report)
    if fundamentals_input is not None:
        _validate_fundamentals_input(fundamentals_input)
    if futures_report is not None and fundamentals_input is not None:
        if _date(fundamentals_input["as_of"]) > _date(futures_report["as_of"]):
            raise CommodityAdapterError(
                "fundamentals input as_of cannot exceed futures report as_of"
            )

    findings: list[dict[str, Any]] = []
    compatibility = {
        "variety_match": None,
        "exchange_match": None,
        "quote_unit_match": None,
        "spot_benchmark_match": None,
    }
    field_coverage: dict[str, dict[str, Any]] = {}
    if futures_report is None:
        findings.append({"severity": "INFO", "type": "CONFIG_ONLY", "message": "仅校验适配器配置。"})
    else:
        variety_id = str(futures_report.get("variety_id") or "").upper()
        exchange = str(futures_report.get("exchange") or "").upper()
        compatibility["variety_match"] = variety_id in adapter.variety_ids
        compatibility["exchange_match"] = not adapter.exchanges or exchange in adapter.exchanges
        if not compatibility["variety_match"]:
            findings.append({"severity": "BLOCKER", "type": "VARIETY_MISMATCH", "message": "期货报告品种不在适配器范围内。"})
        if not compatibility["exchange_match"]:
            findings.append({"severity": "BLOCKER", "type": "EXCHANGE_MISMATCH", "message": "期货报告交易所不在适配器范围内。"})
        if fundamentals_input is None:
            findings.append({"severity": "REVIEW", "type": "FUNDAMENTALS_INPUT_NOT_SUPPLIED", "message": "未提供期货基本面输入，无法检查字段覆盖。"})
        else:
            raw_fields = fundamentals_input.get("fields") or {}
            if not isinstance(raw_fields, Mapping):
                raise CommodityAdapterError("fundamentals input fields must be an object")
            for field in adapter.required_fields:
                raw = raw_fields.get(field)
                status = str(raw.get("status") if isinstance(raw, Mapping) else "MISSING").upper()
                field_coverage[field] = {
                    "status": status,
                    "required_by_adapter": True,
                    "evidence_ids": _string_list(raw.get("evidence_ids")) if isinstance(raw, Mapping) else [],
                }
                if status == "MISSING":
                    findings.append({"severity": "REVIEW", "type": "REQUIRED_FIELD_MISSING", "field": field, "message": f"缺少适配器要求字段: {field}"})
                elif status in {"CONFLICTING", "UNVERIFIED"}:
                    findings.append({"severity": "REVIEW", "type": "REQUIRED_FIELD_NOT_VERIFIED", "field": field, "message": f"适配器要求字段未被可靠验证: {field}"})
            compatibility["quote_unit_match"] = _quote_unit_matches(adapter, futures_report)
            compatibility["spot_benchmark_match"] = _spot_benchmark_matches(adapter, futures_report, fundamentals_input)
            if compatibility["quote_unit_match"] is False:
                findings.append({"severity": "REVIEW", "type": "QUOTE_UNIT_UNCONFIRMED", "message": "报价单位未能与适配器配置确认一致。"})
            if compatibility["spot_benchmark_match"] is False:
                findings.append({"severity": "REVIEW", "type": "SPOT_BENCHMARK_UNCONFIRMED", "message": "现货基准未能与适配器配置确认一致。"})

    status = _validation_status(findings, futures_report, fundamentals_input)
    report_id = validation_id.strip() or adapter.adapter_id
    return {
        "schema_version": ADAPTER_VALIDATION_SCHEMA_VERSION,
        "validation_id": f"commodity-adapter-validation-{report_id}",
        "adapter_id": adapter.adapter_id,
        "adapter_version": adapter.rule_version,
        "status": status,
        "definition": adapter.to_dict(),
        "input_futures_report_id": str(futures_report.get("report_id") or "") if futures_report else "",
        "input_fundamentals_report_id": str(fundamentals_input.get("report_id") or "") if fundamentals_input else "",
        "compatibility": compatibility,
        "field_coverage": field_coverage,
        "findings": findings,
        "acceptance_samples": list(adapter.acceptance_samples),
        "policy": {
            "configuration_only": futures_report is None,
            "data_fetched": False,
            "directional_conclusion": False,
            "investment_conclusion": False,
            "decision_snapshot_created": False,
            "automatic_order_included": False,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _validate_definition_shape(payload: Any) -> None:
    if not isinstance(payload, Mapping):
        raise CommodityAdapterError("commodity adapter definition must be an object")
    if payload.get("schema_version") != COMMODITY_ADAPTER_SCHEMA_VERSION:
        raise CommodityAdapterError(
            f"input must be {COMMODITY_ADAPTER_SCHEMA_VERSION}"
        )
    missing = [field for field in _REQUIRED_TOP_LEVEL if field not in payload]
    if missing:
        raise CommodityAdapterError("adapter definition missing: " + ", ".join(missing))


def _validate_definition_values(**values: Any) -> None:
    if any(not value for value in (values["aliases"], values["exchanges"], values["variety_ids"])):
        raise CommodityAdapterError("aliases, exchanges, and variety_ids must not be empty")
    required_groups = set(values["indicator_groups"])
    missing_groups = set(_GROUPS) - required_groups
    if missing_groups:
        raise CommodityAdapterError(
            "indicator_groups missing: " + ", ".join(sorted(missing_groups))
        )
    all_fields = {
        field for group in values["indicator_groups"].values() for field in group
    }
    missing_fields = set(REQUIRED_FUNDAMENTAL_FIELDS) - all_fields
    if missing_fields:
        raise CommodityAdapterError(
            "indicator_groups missing fundamental fields: "
            + ", ".join(sorted(missing_fields))
        )
    if not values["benchmarks"]:
        raise CommodityAdapterError("spot_benchmarks must not be empty")
    if not values["inventory_locations"]:
        raise CommodityAdapterError("inventory_locations must not be empty")
    if not values["cost_components"] or not values["margin_components"]:
        raise CommodityAdapterError("cost_components and margin_components must not be empty")
    for name in ("required_drivers", "invalidators", "method"):
        if not values["scenario_method"].get(name):
            raise CommodityAdapterError(f"scenario_method.{name} is required")
    if not values["samples"]:
        raise CommodityAdapterError("acceptance_samples must not be empty")


_GROUPS = (
    "supply_demand",
    "production",
    "trade",
    "inventory",
    "pricing",
    "cost_margin",
    "structure",
    "seasonality",
    "position",
    "delivery",
)


def _normalise_indicator_groups(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, Mapping):
        raise CommodityAdapterError("indicator_groups must be an object")
    result: dict[str, list[str]] = {}
    for key, fields in value.items():
        group = _text(key, "indicator_groups key")
        result[group] = _text_list(fields, f"indicator_groups.{group}")
    return result


def _normalise_benchmarks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise CommodityAdapterError("spot_benchmarks must be a list")
    result = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        item = _object(raw, f"spot_benchmarks[{index}]")
        benchmark_id = _text(item.get("benchmark_id"), f"spot_benchmarks[{index}].benchmark_id")
        if benchmark_id in seen:
            raise CommodityAdapterError(f"duplicate spot benchmark: {benchmark_id}")
        seen.add(benchmark_id)
        for key in ("name", "unit", "region", "comparability_rule"):
            _text(item.get(key), f"spot_benchmarks[{index}].{key}")
        result.append(dict(item))
    return result


def _normalise_samples(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise CommodityAdapterError("acceptance_samples must be a list")
    result = []
    for index, raw in enumerate(value):
        item = _object(raw, f"acceptance_samples[{index}]")
        _text(item.get("sample_id"), f"acceptance_samples[{index}].sample_id")
        _text(item.get("description"), f"acceptance_samples[{index}].description")
        result.append(dict(item))
    return result


def _validate_futures_report(report: Mapping[str, Any]) -> None:
    if report.get("schema_version") != FUTURES_REPORT_SCHEMA_VERSION:
        raise CommodityAdapterError("futures report must be futures-fundamentals-report.v1")
    if not str(report.get("as_of") or "").strip():
        raise CommodityAdapterError("futures report as_of is required")
    if not str(report.get("variety_id") or "").strip():
        raise CommodityAdapterError("futures report variety_id is required")


def _validate_fundamentals_input(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != FUTURES_INPUT_SCHEMA_VERSION:
        raise CommodityAdapterError("fundamentals input must be futures-fundamentals-input.v1")
    if not str(payload.get("as_of") or "").strip():
        raise CommodityAdapterError("fundamentals input as_of is required")


def _quote_unit_matches(adapter: CommodityAdapterDefinition, report: Mapping[str, Any]) -> bool | None:
    values = [
        str((report.get("contract") or {}).get("quote_unit") or "").strip(),
        str((report.get("contract_view") or {}).get("quote_unit") or "").strip(),
    ]
    values = [value for value in values if value]
    return None if not values else any(value == adapter.quote_unit for value in values)


def _spot_benchmark_matches(
    adapter: CommodityAdapterDefinition,
    report: Mapping[str, Any],
    fundamentals_input: Mapping[str, Any],
) -> bool | None:
    configured = {_normalise_key(item["benchmark_id"]) for item in adapter.spot_benchmarks}
    configured.update(_normalise_key(item["name"]) for item in adapter.spot_benchmarks)
    field = (fundamentals_input.get("fields") or {}).get("spot_benchmark")
    if not isinstance(field, Mapping):
        return None
    value = field.get("value")
    if not isinstance(value, Mapping):
        return None
    candidate = value.get("benchmark_id") or value.get("benchmark") or value.get("name")
    if not candidate:
        return None
    return _normalise_key(candidate) in configured


def _validation_status(
    findings: Sequence[Mapping[str, Any]],
    futures_report: Mapping[str, Any] | None,
    fundamentals_input: Mapping[str, Any] | None,
) -> str:
    if any(item.get("severity") == "BLOCKER" for item in findings):
        return "BLOCKED"
    if futures_report is None:
        return "CONFIG_READY"
    if str(futures_report.get("status") or "INSUFFICIENT").upper() != "READY":
        return "PARTIAL"
    if fundamentals_input is None:
        return "PARTIAL"
    if any(item.get("severity") == "REVIEW" for item in findings):
        return "PARTIAL"
    return "READY"


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise CommodityAdapterError(f"{field} must be a non-empty object")
    return dict(value)


def _text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise CommodityAdapterError(f"{field} must be non-empty")
    return text


def _text_list(value: Any, field: str) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        values = list(value)
    else:
        raise CommodityAdapterError(f"{field} must be a string list")
    result = [_text(item, field) for item in values]
    if not result:
        raise CommodityAdapterError(f"{field} must not be empty")
    return list(dict.fromkeys(result))


def _normalise_key(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _date(value: Any):
    text = str(value or "").strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text)
        except ValueError as error:
            raise CommodityAdapterError(f"invalid ISO date: {value}") from error


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise CommodityAdapterError("expected a string or string list")
    return [str(item) for item in value if str(item).strip()]
