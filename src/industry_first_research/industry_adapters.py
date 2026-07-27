"""Configuration-driven industry classification and analysis contracts.

An industry adapter selects the questions and evidence contract for a company
or industry.  It does not invent a classification from a concept label, fetch
market data, calculate valuation, or produce an investment conclusion.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from collections.abc import Mapping, Sequence
from typing import Any


class IndustryAdapterError(ValueError):
    """Raised when an industry adapter or profile contract is invalid."""


INDUSTRY_ADAPTER_SCHEMA_VERSION = "industry-adapter.v1"
INDUSTRY_ADAPTER_REGISTRY_SCHEMA_VERSION = "industry-adapter-registry.v1"
INDUSTRY_PROFILE_INPUT_SCHEMA_VERSION = "industry-profile-input.v1"
INDUSTRY_PROFILE_SCHEMA_VERSION = "industry-profile.v1"
INDUSTRY_CYCLE_CONTRACT_SCHEMA_VERSION = "industry-cycle-model-contract.v1"
INDUSTRY_APPLICATION_MAP_SCHEMA_VERSION = "industry-adapter-application-map.v1"
INDUSTRY_TRANSMISSION_SCHEMA_VERSION = "industry-adapter-demand-transmission.v1"
RULE_VERSION = "industry-adapter-rules.v1"

_CLASSIFICATION_DIMENSIONS = (
    "industry_family",
    "segment",
    "value_chain_position",
    "cyclicality",
    "asset_intensity",
    "demand_rigidity",
    "competition_type",
    "technology_risk",
    "policy_sensitivity",
)
_LIFECYCLE_STATUSES = {"ACTIVE", "DRAFT", "DEPRECATED"}
_CLASSIFICATION_STATES = {"READY", "PARTIAL", "INSUFFICIENT", "NO_MATCH"}
_CONFIDENCE = {"HIGH", "MEDIUM", "LOW", "UNVERIFIED"}
_CYCLELESS_VALUES = {
    "NON_CYCLICAL",
    "NONE",
    "NON-CYCLICAL",
    "NOT_APPLICABLE",
    "MACRO_SENSITIVE_NON_PHYSICAL",
    "REGULATED_OR_DEFENSIVE",
}
_DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-_./]?(\d{2})[-_./]?(\d{2})(?!\d)")
_REQUIRED_TOP_LEVEL = (
    "adapter_id",
    "display_name",
    "aliases",
    "supported_industry_ids",
    "supported_industry_names",
    "supported_industry_families",
    "business_models",
    "classification_attributes",
    "required_metrics",
    "valuation_methods",
    "survival_questions",
    "product_application_questions",
    "demand_transmission_stages",
    "lifecycle_status",
    "acceptance_samples",
)


@dataclass(frozen=True)
class IndustryAdapterDefinition:
    """Validated, immutable description of one industry analysis contract."""

    adapter_id: str
    display_name: str
    aliases: tuple[str, ...]
    supported_industry_ids: tuple[str, ...]
    supported_industry_names: tuple[str, ...]
    supported_industry_families: tuple[str, ...]
    business_models: tuple[str, ...]
    classification_attributes: dict[str, Any]
    required_metrics: tuple[str, ...]
    valuation_methods: tuple[str, ...]
    survival_questions: tuple[str, ...]
    product_application_questions: tuple[str, ...]
    demand_transmission_stages: tuple[str, ...]
    lifecycle_status: str
    acceptance_samples: tuple[dict[str, Any], ...]
    fallback: bool = False
    rule_version: str = RULE_VERSION

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "IndustryAdapterDefinition":
        _validate_definition_shape(payload)
        adapter_id = _text(payload["adapter_id"], "adapter_id")
        display_name = _text(payload["display_name"], "display_name")
        aliases = _text_list(payload["aliases"], "aliases")
        industry_ids = _text_list(payload["supported_industry_ids"], "supported_industry_ids")
        industry_names = _text_list(payload["supported_industry_names"], "supported_industry_names")
        families = _text_list(payload["supported_industry_families"], "supported_industry_families")
        business_models = _text_list(payload["business_models"], "business_models")
        attributes = _object(payload["classification_attributes"], "classification_attributes")
        required_metrics = _text_list(payload["required_metrics"], "required_metrics")
        valuation_methods = _text_list(payload["valuation_methods"], "valuation_methods")
        survival_questions = _text_list(payload["survival_questions"], "survival_questions")
        product_questions = _text_list(
            payload["product_application_questions"], "product_application_questions"
        )
        transmission_stages = _text_list(
            payload["demand_transmission_stages"], "demand_transmission_stages"
        )
        lifecycle_status = _text(payload["lifecycle_status"], "lifecycle_status").upper()
        samples = _samples(payload["acceptance_samples"])
        fallback = bool(payload.get("fallback", False))
        rule_version = _text(payload.get("rule_version") or RULE_VERSION, "rule_version")
        _validate_definition_values(
            adapter_id=adapter_id,
            aliases=aliases,
            industry_ids=industry_ids,
            industry_names=industry_names,
            families=families,
            business_models=business_models,
            attributes=attributes,
            required_metrics=required_metrics,
            valuation_methods=valuation_methods,
            survival_questions=survival_questions,
            product_questions=product_questions,
            transmission_stages=transmission_stages,
            lifecycle_status=lifecycle_status,
            samples=samples,
            fallback=fallback,
        )
        return cls(
            adapter_id=adapter_id,
            display_name=display_name,
            aliases=tuple(aliases),
            supported_industry_ids=tuple(industry_ids),
            supported_industry_names=tuple(industry_names),
            supported_industry_families=tuple(families),
            business_models=tuple(business_models),
            classification_attributes=attributes,
            required_metrics=tuple(required_metrics),
            valuation_methods=tuple(valuation_methods),
            survival_questions=tuple(survival_questions),
            product_application_questions=tuple(product_questions),
            demand_transmission_stages=tuple(transmission_stages),
            lifecycle_status=lifecycle_status,
            acceptance_samples=tuple(samples),
            fallback=fallback,
            rule_version=rule_version,
        )

    def matches(
        self,
        identifier: str = "",
        *,
        industry_id: str = "",
        industry_name: str = "",
        industry_family: str = "",
        business_model: str = "",
    ) -> tuple[bool, str]:
        """Match only explicit IDs, names, family, or business-model values."""

        values = (
            (industry_id, self.supported_industry_ids, "INDUSTRY_ID_EXACT"),
            (industry_name, self.supported_industry_names, "INDUSTRY_NAME_EXACT"),
            (identifier, (self.adapter_id, *self.aliases), "ADAPTER_ALIAS_EXACT"),
            (industry_family, self.supported_industry_families, "INDUSTRY_FAMILY_EXACT"),
            (business_model, self.business_models, "BUSINESS_MODEL_EXACT"),
        )
        for value, candidates, method in values:
            key = _normalise(value)
            if key and key in {_normalise(item) for item in candidates}:
                return True, method
        return False, "NO_EXPLICIT_MATCH"

    def classify(self, company_profile: Mapping[str, Any]) -> dict[str, Any]:
        """Return a classification contract without promoting it to fact."""

        if not isinstance(company_profile, Mapping):
            raise IndustryAdapterError("company_profile must be an object")
        industry_id = str(company_profile.get("industry_id") or "").strip()
        industry_name = str(
            company_profile.get("industry_name")
            or company_profile.get("display_name")
            or ""
        ).strip()
        industry_family = str(company_profile.get("industry_family") or "").strip()
        business_model = str(company_profile.get("business_model") or "").strip()
        matched, match_method = self.matches(
            str(company_profile.get("adapter_id") or ""),
            industry_id=industry_id,
            industry_name=industry_name,
            industry_family=industry_family,
            business_model=business_model,
        )
        if matched and match_method in {"INDUSTRY_ID_EXACT", "INDUSTRY_NAME_EXACT", "ADAPTER_ALIAS_EXACT"}:
            status, confidence = "READY", "HIGH"
        elif matched:
            status, confidence = "PARTIAL", "MEDIUM"
        elif self.fallback:
            status, confidence, match_method = "PARTIAL", "LOW", "FALLBACK_GENERIC"
        else:
            status, confidence = "NO_MATCH", "UNVERIFIED"
        missing = [
            field
            for field in ("industry_id", "industry_name", "industry_family", "business_model")
            if not str(company_profile.get(field) or "").strip()
        ]
        return {
            "adapter_id": self.adapter_id,
            "display_name": self.display_name,
            "classification_state": status,
            "confidence": confidence,
            "match_method": match_method,
            "input": {
                "industry_id": industry_id,
                "industry_name": industry_name,
                "industry_family": industry_family,
                "business_model": business_model,
            },
            "configured_attributes": dict(self.classification_attributes),
            "missing_classification_fields": missing,
            "claims_are_verified": False,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
        }

    def required_metrics_for(self, company_profile: Mapping[str, Any]) -> list[str]:
        """Return the metric contract; values must be collected elsewhere."""

        if not isinstance(company_profile, Mapping):
            raise IndustryAdapterError("company_profile must be an object")
        return list(self.required_metrics)

    def build_cycle_model(self, evidence_set: Mapping[str, Any]) -> dict[str, Any] | None:
        """Return a cycle-model contract, never a cycle direction."""

        if not isinstance(evidence_set, Mapping):
            raise IndustryAdapterError("evidence_set must be an object")
        cyclicality = str(self.classification_attributes.get("cyclicality") or "").upper()
        if cyclicality in _CYCLELESS_VALUES:
            return None
        return {
            "schema_version": INDUSTRY_CYCLE_CONTRACT_SCHEMA_VERSION,
            "adapter_id": self.adapter_id,
            "applies": True,
            "status": "CONTRACT_ONLY",
            "cyclicality": cyclicality or "UNKNOWN",
            "required_metrics": list(self.required_metrics),
            "evidence_fields_present": sorted(
                str(key) for key in evidence_set if str(key) in self.required_metrics
            ),
            "cycle_state": "NOT_EVALUATED",
            "directional_conclusion": False,
            "investment_conclusion": False,
            "review_only": True,
        }

    def survival_questions_for(self, company_profile: Mapping[str, Any]) -> list[str]:
        if not isinstance(company_profile, Mapping):
            raise IndustryAdapterError("company_profile must be an object")
        return list(self.survival_questions)

    def map_product_applications(
        self,
        company_profile: Mapping[str, Any],
        evidence_set: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Map only explicit product/application records; never infer exposure."""

        if not isinstance(company_profile, Mapping) or not isinstance(evidence_set, Mapping):
            raise IndustryAdapterError("company_profile and evidence_set must be objects")
        raw_products = company_profile.get("products") or company_profile.get("product_list") or []
        if not isinstance(raw_products, Sequence) or isinstance(raw_products, (str, bytes, bytearray)):
            raise IndustryAdapterError("company profile products must be a list")
        raw_maps = evidence_set.get("product_applications") or evidence_set.get("application_mappings") or []
        if not isinstance(raw_maps, Sequence) or isinstance(raw_maps, (str, bytes, bytearray)):
            raise IndustryAdapterError("product application evidence must be a list")
        by_product: dict[str, list[Mapping[str, Any]]] = {}
        for raw_map in raw_maps:
            if not isinstance(raw_map, Mapping):
                continue
            product_key = str(raw_map.get("product_id") or raw_map.get("product_name") or "").strip()
            if product_key:
                by_product.setdefault(_normalise(product_key), []).append(raw_map)
        items: list[dict[str, Any]] = []
        for raw_product in raw_products:
            if isinstance(raw_product, Mapping):
                product_id = str(raw_product.get("product_id") or raw_product.get("id") or "").strip()
                product_name = str(raw_product.get("product_name") or raw_product.get("name") or "").strip()
            else:
                product_id = ""
                product_name = str(raw_product).strip()
            if not product_name:
                continue
            records = by_product.get(_normalise(product_id or product_name), [])
            applications = [_normalise_application(item) for item in records]
            items.append(
                {
                    "product_id": product_id,
                    "product_name": product_name,
                    "applications": applications,
                    "mapping_state": "MAPPED" if applications else "MISSING_APPLICATION_EVIDENCE",
                    "inferred": False,
                    "evidence_ids": _unique(
                        str(item.get("evidence_id") or item.get("source_evidence_id") or "")
                        for item in records
                    ),
                }
            )
        return {
            "schema_version": INDUSTRY_APPLICATION_MAP_SCHEMA_VERSION,
            "adapter_id": self.adapter_id,
            "items": items,
            "mapping_state": "READY" if items and all(item["applications"] for item in items) else "PARTIAL" if items else "INSUFFICIENT",
            "questions": list(self.product_application_questions),
            "industry_adapter_inference": False,
            "investment_conclusion": False,
            "review_only": True,
        }

    def assess_demand_transmission(
        self,
        product_application_map: Mapping[str, Any],
        evidence_set: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Report explicit transmission-stage coverage without forecasting."""

        if not isinstance(product_application_map, Mapping) or not isinstance(evidence_set, Mapping):
            raise IndustryAdapterError("product_application_map and evidence_set must be objects")
        raw_evidence = evidence_set.get("demand_transmission") or evidence_set.get("transmission_evidence") or []
        if not isinstance(raw_evidence, Sequence) or isinstance(raw_evidence, (str, bytes, bytearray)):
            raise IndustryAdapterError("demand transmission evidence must be a list")
        by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
        for record in raw_evidence:
            if not isinstance(record, Mapping):
                continue
            key = (
                _normalise(str(record.get("product_id") or record.get("product_name") or "")),
                _normalise(str(record.get("stage") or "")),
            )
            if key[0] and key[1]:
                by_key[key] = record
        items: list[dict[str, Any]] = []
        for product in product_application_map.get("items") or []:
            if not isinstance(product, Mapping):
                continue
            product_key = _normalise(str(product.get("product_id") or product.get("product_name") or ""))
            stages: list[dict[str, Any]] = []
            for stage in self.demand_transmission_stages:
                record = by_key.get((product_key, _normalise(stage)))
                if record is None:
                    stages.append({"stage": stage, "status": "MISSING", "evidence_ids": []})
                else:
                    stages.append(
                        {
                            "stage": stage,
                            "status": str(record.get("status") or "UNVERIFIED").upper(),
                            "value": record.get("value"),
                            "evidence_ids": _unique(
                                str(item)
                                for item in (record.get("evidence_ids") or [record.get("evidence_id") or ""])
                                if str(item)
                            ),
                        }
                    )
            items.append(
                {
                    "product_id": product.get("product_id") or "",
                    "product_name": product.get("product_name") or "",
                    "stages": stages,
                    "transmission_state": _transmission_state(stages),
                }
            )
        states = [str(item["transmission_state"]) for item in items]
        overall = "READY" if states and all(state == "PROFIT_VALIDATED" for state in states) else "PARTIAL" if any(state != "INSUFFICIENT" for state in states) else "INSUFFICIENT"
        return {
            "schema_version": INDUSTRY_TRANSMISSION_SCHEMA_VERSION,
            "adapter_id": self.adapter_id,
            "required_stages": list(self.demand_transmission_stages),
            "items": items,
            "transmission_gate_state": overall,
            "directional_conclusion": False,
            "investment_conclusion": False,
            "review_only": True,
        }

    def validate_conclusion(self, draft_report: Mapping[str, Any]) -> list[str]:
        """Return adapter-specific omissions; does not rewrite a conclusion."""

        if not isinstance(draft_report, Mapping):
            raise IndustryAdapterError("draft_report must be an object")
        issues: list[str] = []
        for field in ("industry_profile", "product_profile", "evidence", "counterevidence"):
            if field not in draft_report:
                issues.append(f"MISSING_SECTION:{field}")
        if self.required_metrics and not draft_report.get("required_metrics_coverage"):
            issues.append("MISSING_REQUIRED_METRICS_COVERAGE")
        if "valuation" in draft_report and not draft_report.get("valuation_method"):
            issues.append("VALUATION_METHOD_NOT_DECLARED")
        issues.append("CONCLUSION_REMAINS_REVIEW_ONLY")
        return issues

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": INDUSTRY_ADAPTER_SCHEMA_VERSION,
            "adapter_id": self.adapter_id,
            "display_name": self.display_name,
            "aliases": list(self.aliases),
            "supported_industry_ids": list(self.supported_industry_ids),
            "supported_industry_names": list(self.supported_industry_names),
            "supported_industry_families": list(self.supported_industry_families),
            "business_models": list(self.business_models),
            "classification_attributes": dict(self.classification_attributes),
            "required_metrics": list(self.required_metrics),
            "valuation_methods": list(self.valuation_methods),
            "survival_questions": list(self.survival_questions),
            "product_application_questions": list(self.product_application_questions),
            "demand_transmission_stages": list(self.demand_transmission_stages),
            "lifecycle_status": self.lifecycle_status,
            "acceptance_samples": [dict(item) for item in self.acceptance_samples],
            "fallback": self.fallback,
            "rule_version": self.rule_version,
        }
        payload["configuration_hash"] = _object_hash(payload)
        return payload


class IndustryAdapterRegistry:
    """Resolve industry adapters by explicit ID, alias, family, or model."""

    def __init__(self, definitions: Sequence[IndustryAdapterDefinition] = ()) -> None:
        self._definitions: dict[str, IndustryAdapterDefinition] = {}
        self._lookup: dict[str, str] = {}
        self._fallback: IndustryAdapterDefinition | None = None
        for definition in definitions:
            self.register(definition)

    def register(self, definition: IndustryAdapterDefinition) -> None:
        if not isinstance(definition, IndustryAdapterDefinition):
            raise IndustryAdapterError("registry accepts IndustryAdapterDefinition objects")
        adapter_key = _normalise(definition.adapter_id)
        if adapter_key in self._definitions:
            raise IndustryAdapterError(f"duplicate adapter_id: {definition.adapter_id}")
        identifiers = (
            definition.adapter_id,
            *definition.aliases,
            *definition.supported_industry_ids,
            *definition.supported_industry_names,
        )
        for identifier in identifiers:
            key = _normalise(identifier)
            if not key:
                continue
            existing = self._lookup.get(key)
            if existing is not None and existing != adapter_key:
                raise IndustryAdapterError(f"adapter identifier is ambiguous: {identifier}")
        self._definitions[adapter_key] = definition
        if definition.fallback:
            if self._fallback is not None:
                raise IndustryAdapterError("only one fallback generic adapter is allowed")
            self._fallback = definition
        for identifier in identifiers:
            key = _normalise(identifier)
            if key:
                self._lookup[key] = adapter_key

    def resolve(self, identifier: str) -> IndustryAdapterDefinition:
        key = _normalise(identifier)
        adapter_key = self._lookup.get(key)
        if adapter_key is None:
            raise IndustryAdapterError(f"industry adapter not found: {identifier}")
        definition = self._definitions[adapter_key]
        if definition.lifecycle_status == "DEPRECATED":
            raise IndustryAdapterError(f"industry adapter is deprecated: {identifier}")
        return definition

    def resolve_for_profile(
        self,
        profile: Mapping[str, Any],
        *,
        adapter_id: str = "",
        allow_fallback: bool = True,
    ) -> tuple[IndustryAdapterDefinition, dict[str, Any]]:
        if not isinstance(profile, Mapping):
            raise IndustryAdapterError("profile must be an object")
        if adapter_id.strip():
            adapter = self.resolve(adapter_id)
            return adapter, adapter.classify(profile)
        candidates: list[tuple[IndustryAdapterDefinition, dict[str, Any]]] = []
        for adapter in self.list():
            if adapter.fallback:
                continue
            result = adapter.classify(profile)
            if result["classification_state"] != "NO_MATCH":
                candidates.append((adapter, result))
        if len(candidates) > 1:
            raise IndustryAdapterError(
                "industry profile matches multiple adapters: "
                + ", ".join(item[0].adapter_id for item in candidates)
            )
        if candidates:
            return candidates[0]
        if allow_fallback and self._fallback is not None:
            return self._fallback, self._fallback.classify(profile)
        raise IndustryAdapterError("no industry adapter matches profile")

    def list(self) -> list[IndustryAdapterDefinition]:
        return [self._definitions[key] for key in sorted(self._definitions)]

    @classmethod
    def from_directory(cls, directory: str | Path) -> "IndustryAdapterRegistry":
        root = Path(directory)
        if not root.is_dir():
            raise IndustryAdapterError(f"industry adapter directory does not exist: {root}")
        paths = sorted(root.glob("*.json"))
        if not paths:
            raise IndustryAdapterError(f"industry adapter directory has no JSON files: {root}")
        definitions: list[IndustryAdapterDefinition] = []
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                definitions.append(IndustryAdapterDefinition.from_mapping(payload))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, IndustryAdapterError) as error:
                raise IndustryAdapterError(f"invalid industry adapter {path}: {error}") from error
        return cls(definitions)


def build_industry_profile_report(
    payload: Mapping[str, Any],
    registry: IndustryAdapterRegistry,
    *,
    adapter_id: str = "",
    profile_id: str = "",
) -> dict[str, Any]:
    """Build an evidence-bound industry profile and adapter contract."""

    if not isinstance(payload, Mapping):
        raise IndustryAdapterError("industry profile input must be an object")
    if payload.get("schema_version") != INDUSTRY_PROFILE_INPUT_SCHEMA_VERSION:
        raise IndustryAdapterError(f"input must be {INDUSTRY_PROFILE_INPUT_SCHEMA_VERSION}")
    if not isinstance(registry, IndustryAdapterRegistry):
        raise IndustryAdapterError("registry must be an IndustryAdapterRegistry")
    as_of = _parse_date(str(payload.get("as_of") or ""), "as_of")
    adapter, classification = registry.resolve_for_profile(payload, adapter_id=adapter_id)
    fields: dict[str, dict[str, Any]] = {}
    raw_attributes = payload.get("attributes") or {}
    if not isinstance(raw_attributes, Mapping):
        raise IndustryAdapterError("attributes must be an object")
    for field in _CLASSIFICATION_DIMENSIONS:
        value = raw_attributes.get(field, payload.get(field))
        if value not in (None, "", [], {}):
            fields[field] = {
                "value": value,
                "status": "CANDIDATE_INPUT",
                "source_evidence_ids": _string_list(payload.get("evidence_ids")),
                "read_only": True,
            }
        elif field in adapter.classification_attributes:
            fields[field] = {
                "value": adapter.classification_attributes[field],
                "status": "CONFIGURED_SCOPE",
                "source_evidence_ids": [],
                "read_only": True,
            }
        else:
            fields[field] = {
                "value": None,
                "status": "MISSING",
                "source_evidence_ids": [],
                "read_only": True,
            }
    key = profile_id.strip() or str(payload.get("profile_id") or "") or (
        f"{payload.get('subject_id') or payload.get('industry_id') or 'industry'}-{as_of.isoformat()}"
    )
    return {
        "schema_version": INDUSTRY_PROFILE_SCHEMA_VERSION,
        "profile_id": f"industry-profile-{_safe_id(key)}",
        "subject_type": str(payload.get("subject_type") or "industry"),
        "subject_id": str(payload.get("subject_id") or payload.get("industry_id") or ""),
        "industry_id": str(payload.get("industry_id") or ""),
        "industry_name": str(payload.get("industry_name") or payload.get("display_name") or ""),
        "industry_segment": str(payload.get("industry_segment") or ""),
        "value_chain_position": str(payload.get("value_chain_position") or ""),
        "as_of": as_of.isoformat(),
        "data_cutoff_at": as_of.isoformat(),
        "source": str(payload.get("source") or ""),
        "source_project": str(payload.get("source_project") or ""),
        "evidence_ids": _string_list(payload.get("evidence_ids")),
        "adapter_id": adapter.adapter_id,
        "adapter_version": adapter.rule_version,
        "configuration_hash": adapter.to_dict()["configuration_hash"],
        "classification": classification,
        "classification_fields": fields,
        "required_metrics": adapter.required_metrics_for(payload),
        "valuation_methods": list(adapter.valuation_methods),
        "survival_questions": adapter.survival_questions_for(payload),
        "product_application_questions": list(adapter.product_application_questions),
        "demand_transmission_stages": list(adapter.demand_transmission_stages),
        "cycle_model_available": adapter.build_cycle_model({}) is not None,
        "industry_profile_state": classification["classification_state"],
        "claims_are_verified": False,
        "investment_conclusion": False,
        "review_only": True,
        "execution_enabled": False,
        "policy": _policy(adapter),
    }


def build_industry_adapter_registry_report(
    registry: IndustryAdapterRegistry,
    *,
    registry_id: str = "default",
) -> dict[str, Any]:
    if not isinstance(registry, IndustryAdapterRegistry):
        raise IndustryAdapterError("registry must be an IndustryAdapterRegistry")
    adapters = registry.list()
    return {
        "schema_version": INDUSTRY_ADAPTER_REGISTRY_SCHEMA_VERSION,
        "registry_id": f"industry-adapter-registry-{_safe_id(registry_id)}",
        "adapter_count": len(adapters),
        "adapters": [item.to_dict() for item in adapters],
        "policy": {
            "configuration_only": True,
            "data_fetched": False,
            "classification_is_candidate": True,
            "non_cyclical_returns_no_cycle_model": True,
            "investment_conclusion": False,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
        "investment_conclusion": False,
        "read_only": True,
        "review_only": True,
        "execution_enabled": False,
    }


def _validate_definition_shape(payload: Any) -> None:
    if not isinstance(payload, Mapping):
        raise IndustryAdapterError("industry adapter definition must be an object")
    if payload.get("schema_version") != INDUSTRY_ADAPTER_SCHEMA_VERSION:
        raise IndustryAdapterError(f"input must be {INDUSTRY_ADAPTER_SCHEMA_VERSION}")
    missing = [field for field in _REQUIRED_TOP_LEVEL if field not in payload]
    if missing:
        raise IndustryAdapterError("adapter definition missing: " + ", ".join(missing))


def _validate_definition_values(**values: Any) -> None:
    if not values["adapter_id"]:
        raise IndustryAdapterError("adapter_id must not be empty")
    if not values["aliases"] and not values["industry_ids"] and not values["industry_names"] and not values["fallback"]:
        raise IndustryAdapterError("adapter requires aliases, supported industry IDs/names, or fallback=true")
    if not values["attributes"]:
        raise IndustryAdapterError("classification_attributes must not be empty")
    unknown = set(values["attributes"]) - set(_CLASSIFICATION_DIMENSIONS)
    if unknown:
        raise IndustryAdapterError("unsupported classification attributes: " + ", ".join(sorted(unknown)))
    if values["lifecycle_status"] not in _LIFECYCLE_STATUSES:
        raise IndustryAdapterError("lifecycle_status must be ACTIVE, DRAFT, or DEPRECATED")
    if not values["required_metrics"]:
        raise IndustryAdapterError("required_metrics must not be empty")
    if not values["valuation_methods"]:
        raise IndustryAdapterError("valuation_methods must not be empty")
    if not values["survival_questions"] or not values["product_questions"]:
        raise IndustryAdapterError("survival and product application questions are required")
    if not values["transmission_stages"]:
        raise IndustryAdapterError("demand_transmission_stages must not be empty")
    if not values["samples"]:
        raise IndustryAdapterError("acceptance_samples must not be empty")


def _normalise_application(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "application_id": str(value.get("application_id") or value.get("id") or ""),
        "application_name": str(value.get("application_name") or value.get("name") or ""),
        "system_layer": str(value.get("system_layer") or ""),
        "criticality": str(value.get("criticality") or ""),
        "substitution_risk": str(value.get("substitution_risk") or ""),
        "evidence_ids": _unique(
            str(item)
            for item in (value.get("evidence_ids") or [value.get("evidence_id") or ""])
            if str(item)
        ),
        "status": str(value.get("status") or "UNVERIFIED").upper(),
        "inferred": False,
    }


def _transmission_state(stages: Sequence[Mapping[str, Any]]) -> str:
    if not stages or all(str(stage.get("status") or "MISSING").upper() == "MISSING" for stage in stages):
        return "INSUFFICIENT"
    statuses = [str(stage.get("status") or "UNVERIFIED").upper() for stage in stages]
    if all(status == "VERIFIED" for status in statuses):
        return "PROFIT_VALIDATED"
    if any(status == "VERIFIED" for status in statuses):
        return "PARTIAL"
    return "UNVERIFIED"


def _policy(adapter: IndustryAdapterDefinition) -> dict[str, Any]:
    return {
        "configuration_driven": True,
        "adapter_id": adapter.adapter_id,
        "classification_is_not_verified_fact": True,
        "product_exposure_requires_explicit_product": True,
        "application_mapping_requires_explicit_evidence": True,
        "non_cyclical_industry_does_not_get_cycle_model": True,
        "valuation_method_is_contract_only": True,
        "investment_conclusion": False,
        "read_only": True,
        "review_only": True,
        "execution_enabled": False,
    }


def _samples(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise IndustryAdapterError("acceptance_samples must be a list")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise IndustryAdapterError(f"acceptance_samples[{index}] must be an object")
        sample_id = _text(item.get("sample_id"), f"acceptance_samples[{index}].sample_id")
        description = _text(item.get("description"), f"acceptance_samples[{index}].description")
        result.append({**dict(item), "sample_id": sample_id, "description": description})
    return result


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise IndustryAdapterError(f"{field} must be an object")
    return dict(value)


def _text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise IndustryAdapterError(f"{field} must be non-empty")
    return text


def _text_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise IndustryAdapterError(f"{field} must be a string list")
    result = [str(item).strip() for item in value if str(item).strip()]
    return list(dict.fromkeys(result))


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise IndustryAdapterError("evidence_ids must be a string list")
    return [str(item) for item in value if str(item)]


def _unique(values: Sequence[str] | Any) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


def _normalise(value: Any) -> str:
    return re.sub(r"[\s_./()（）\[\]【】：:，,\-]+", "", str(value or "")).lower()


def _parse_date(value: str, field: str) -> date:
    text = str(value or "").strip()
    if not text:
        raise IndustryAdapterError(f"{field} is required")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        match = _DATE_RE.search(text)
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                pass
    raise IndustryAdapterError(f"invalid {field}: {value}")


def _object_hash(value: Any) -> str:
    return sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_.-]+", "-", str(value)).strip("-")
    return cleaned or "profile"
