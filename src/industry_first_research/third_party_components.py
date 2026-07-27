"""Optional third-party component registry and isolated adapters.

The research core must remain usable when optional packages are not installed.
This module therefore keeps component discovery local, never fetches a remote
resource, and turns external results into auditable intermediate artifacts.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from hashlib import sha256
from importlib import import_module, util
import json
from pathlib import Path
import tempfile
from typing import Any

from .third_party_candidate_review import (
    CANDIDATE_REVIEW_PROJECTION_SCHEMA_VERSION,
    CANDIDATE_REVIEW_SCHEMA_VERSION,
    ThirdPartyCandidateReviewError,
    validate_candidate_review,
    validate_candidate_review_projection,
)


COMPONENT_REGISTRY_INPUT_SCHEMA_VERSION = "third-party-component-registry-input.v1"
COMPONENT_REGISTRY_SCHEMA_VERSION = "third-party-component-registry.v1"
COMPONENT_HEALTH_SCHEMA_VERSION = "third-party-component-health.v1"
DOCUMENT_PARSE_SCHEMA_VERSION = "third-party-document-parse-result.v1"
PERFORMANCE_INPUT_SCHEMA_VERSION = "third-party-performance-input.v1"
PERFORMANCE_SCHEMA_VERSION = "third-party-performance-result.v1"
RULE_VERSION = "third-party-components-rules.v1"

COMPONENT_DECISIONS = {
    "DIRECT_REUSE",
    "ADAPTER_REUSE",
    "FORK_AND_MODIFY",
    "REFERENCE_ONLY",
    "LICENSE_REVIEW_REQUIRED",
    "DISABLED",
}
HEALTH_STATUSES = {"READY", "UNAVAILABLE", "DISABLED", "REJECTED", "PARTIAL"}
PARSER_KINDS = {"document_parser", "performance_metrics", "trigger_runtime", "analytical_query"}
ACTIVE_COMPONENT_DECISIONS = {"DIRECT_REUSE", "ADAPTER_REUSE", "FORK_AND_MODIFY"}


class ThirdPartyComponentError(ValueError):
    """Raised when a component registry or adapter result is unsafe."""


class ThirdPartyComponentRegistry:
    """Resolve registered optional components without importing them eagerly."""

    def __init__(self, report: Mapping[str, Any]) -> None:
        self.report = validate_component_registry(report)
        self._components = {
            str(item["component_id"]): dict(item)
            for item in self.report["components"]
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ThirdPartyComponentRegistry":
        return cls(build_component_registry(payload))

    def get(self, component_id: str) -> dict[str, Any]:
        identifier = str(component_id or "").strip()
        if identifier not in self._components:
            raise ThirdPartyComponentError(f"component is not registered: {component_id}")
        return dict(self._components[identifier])

    def components(self) -> list[dict[str, Any]]:
        return [dict(self._components[key]) for key in sorted(self._components)]


def build_component_registry(
    payload: Mapping[str, Any],
    *,
    registry_id: str = "",
) -> dict[str, Any]:
    """Validate a checked-in component registry and normalize its records."""

    if not isinstance(payload, Mapping):
        raise ThirdPartyComponentError("component registry must be an object")
    schema = payload.get("schema_version")
    if schema not in {
        COMPONENT_REGISTRY_INPUT_SCHEMA_VERSION,
        COMPONENT_REGISTRY_SCHEMA_VERSION,
    }:
        raise ThirdPartyComponentError(
            f"input must be {COMPONENT_REGISTRY_INPUT_SCHEMA_VERSION} or {COMPONENT_REGISTRY_SCHEMA_VERSION}"
        )
    raw_components = payload.get("components")
    if not isinstance(raw_components, list) or not raw_components:
        raise ThirdPartyComponentError("component registry must contain components")
    components: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_components:
        component = _normalize_component(raw)
        identifier = component["component_id"]
        if identifier in seen:
            raise ThirdPartyComponentError(f"duplicate component_id: {identifier}")
        seen.add(identifier)
        components.append(component)
    identifier = str(payload.get("registry_id") or registry_id).strip()
    if not identifier:
        identifier = f"third-party-components-{_hash_payload(components)[:16]}"
    version = str(payload.get("version") or "").strip()
    if not version:
        raise ThirdPartyComponentError("registry version is required")
    report = {
        "schema_version": COMPONENT_REGISTRY_SCHEMA_VERSION,
        "registry_id": identifier,
        "version": version,
        "as_of": str(payload.get("as_of") or ""),
        "components": sorted(components, key=lambda item: item["component_id"]),
        "component_count": len(components),
        "content_hash": _hash_payload(components),
        "rule_version": RULE_VERSION,
        "policy": {
            "optional_dependencies_only": True,
            "no_remote_health_checks": True,
            "adapter_required": True,
            "license_review_required": True,
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
    return report


def validate_component_registry(report: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a previously built component registry without changing it."""

    if not isinstance(report, Mapping) or report.get("schema_version") != COMPONENT_REGISTRY_SCHEMA_VERSION:
        raise ThirdPartyComponentError(
            f"input must be {COMPONENT_REGISTRY_SCHEMA_VERSION}"
        )
    rebuilt = build_component_registry(report)
    errors: list[str] = []
    for field in ("registry_id", "version", "content_hash"):
        if not str(report.get(field) or "").strip():
            errors.append(f"missing {field}")
    if report.get("immutable") is not True:
        errors.append("registry must be immutable")
    if report.get("content_hash") != rebuilt.get("content_hash"):
        errors.append("content_hash does not match components")
    if len(report.get("components") or []) != rebuilt["component_count"]:
        errors.append("component_count does not match components")
    if errors:
        raise ThirdPartyComponentError("invalid component registry: " + "; ".join(errors))
    return dict(report)


def validate_component_registry_links(
    registry: Mapping[str, Any],
    candidate_reviews: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Verify registry entries against immutable candidate review records."""

    report = validate_component_registry(registry)
    if not isinstance(candidate_reviews, Sequence) or isinstance(candidate_reviews, (str, bytes, bytearray)):
        raise ThirdPartyComponentError("candidate_reviews must be a list")
    indexed: dict[str, Mapping[str, Any]] = {}
    for candidate in candidate_reviews:
        if not isinstance(candidate, Mapping):
            raise ThirdPartyComponentError("each candidate review must be an object")
        schema = candidate.get("schema_version")
        try:
            if schema == CANDIDATE_REVIEW_SCHEMA_VERSION:
                normalized = validate_candidate_review(candidate)
                review_id = str(normalized["review_id"])
                state = str(normalized["state"])
                source_review = normalized
            elif schema == CANDIDATE_REVIEW_PROJECTION_SCHEMA_VERSION:
                normalized_projection = validate_candidate_review_projection(candidate)
                review_id = str(normalized_projection["review_id"])
                state = str(normalized_projection["current_state"])
                source_review = normalized_projection["review"]
            else:
                raise ThirdPartyComponentError("candidate review must be a review or projection")
        except ThirdPartyCandidateReviewError as error:
            raise ThirdPartyComponentError(str(error)) from error
        if review_id in indexed:
            raise ThirdPartyComponentError(f"duplicate candidate review_id: {review_id}")
        indexed[review_id] = {"review": source_review, "state": state}

    errors: list[str] = []
    for component in report["components"]:
        component_id = str(component["component_id"])
        review_id = str(component.get("candidate_review_id") or "").strip()
        if not review_id:
            errors.append(f"{component_id}: candidate_review_id is required")
            continue
        linked = indexed.get(review_id)
        if not linked:
            errors.append(f"{component_id}: candidate review is not supplied: {review_id}")
            continue
        review = linked["review"]
        state = str(linked["state"]).upper()
        if str(component.get("candidate_review_state") or "").upper() != state:
            errors.append(f"{component_id}: candidate_review_state does not match review")
        if str(component.get("capability_slice") or "") != str(review.get("capability_slice") or ""):
            errors.append(f"{component_id}: capability_slice does not match review")
        if component["enabled"] and state not in {"ACCEPTED", "CONDITIONAL"}:
            errors.append(f"{component_id}: enabled component requires ACCEPTED or CONDITIONAL review")
        if component["enabled"]:
            for field, review_field in (
                ("validation_fixture_ids", "fixture_ids"),
                ("baseline_id", "baseline_id"),
                ("adapter_registration_id", "adapter_id"),
                ("fallback_component", "fallback_id"),
            ):
                expected = component.get(field)
                actual = review.get(review_field)
                if field == "validation_fixture_ids":
                    if list(expected or []) != list(actual or []):
                        errors.append(f"{component_id}: {field} does not match review")
                elif str(expected or "") != str(actual or ""):
                    errors.append(f"{component_id}: {field} does not match review")
    if errors:
        raise ThirdPartyComponentError("invalid component/review links: " + "; ".join(errors))
    return report


def build_component_registration_from_candidate(
    candidate_review: Mapping[str, Any],
    *,
    component_id: str,
    package_name: str,
    adapter_kind: str,
    project_url: str = "",
    import_name: str = "",
    adapter_name: str = "",
    decision: str = "ADAPTER_REUSE",
    enabled: bool = True,
    modification_log: Sequence[str] = (),
) -> dict[str, Any]:
    """Build one registry entry from an accepted candidate review/projection."""

    try:
        if candidate_review.get("schema_version") == CANDIDATE_REVIEW_PROJECTION_SCHEMA_VERSION:
            projection = validate_candidate_review_projection(candidate_review)
            review = projection["review"]
            state = str(projection["current_state"])
        elif candidate_review.get("schema_version") == CANDIDATE_REVIEW_SCHEMA_VERSION:
            review = validate_candidate_review(candidate_review)
            state = str(review["state"])
        else:
            raise ThirdPartyComponentError("candidate review must be a review or projection")
    except ThirdPartyCandidateReviewError as error:
        raise ThirdPartyComponentError(str(error)) from error
    state = state.upper()
    if state not in {"ACCEPTED", "CONDITIONAL"}:
        raise ThirdPartyComponentError(
            "only ACCEPTED or CONDITIONAL reviews can create a component registration"
        )
    identifier = str(component_id or "").strip()
    package = str(package_name or "").strip()
    kind = str(adapter_kind or "").strip()
    if not identifier or not package or not kind:
        raise ThirdPartyComponentError("component_id, package_name, and adapter_kind are required")
    raw = {
        "component_id": identifier,
        "project_url": str(project_url or review.get("project_url") or "").strip(),
        "package_name": package,
        "import_name": str(import_name or package).strip(),
        "version_or_commit": str(review.get("version_or_commit") or "").strip(),
        "license_snapshot": str(review.get("license_snapshot") or ""),
        "license_status": str(review.get("license_status") or ""),
        "adapter_name": str(adapter_name or f"{identifier}-adapter"),
        "adapter_kind": kind,
        "capability_scope": [str(review.get("capability_slice") or "")],
        "python_and_os_requirements": _dependency_requirements(review.get("dependency_manifest")),
        "network_required": bool(review.get("network_required", False)),
        "token_required": bool(review.get("token_required", False)),
        "temporal_cutoff_support": str(review.get("temporal_cutoff_support") or ""),
        "future_function_risk": str(review.get("future_function_risk") or ""),
        "validation_fixture_ids": review.get("fixture_ids") or [],
        "regression_status": str(review.get("regression_status") or ""),
        "fallback_component": str(review.get("fallback_id") or ""),
        "candidate_review_id": str(review.get("review_id") or ""),
        "capability_slice": str(review.get("capability_slice") or ""),
        "candidate_review_state": state,
        "adapter_registration_id": str(review.get("adapter_id") or ""),
        "baseline_id": str(review.get("baseline_id") or ""),
        "enable_conditions": review.get("enable_conditions") or {},
        "decision": decision,
        "enabled": enabled,
        "modification_log": list(modification_log),
    }
    return _normalize_component(raw)


def build_component_health_snapshot(
    registry: Mapping[str, Any] | ThirdPartyComponentRegistry,
    *,
    checked_at: str = "",
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Check local package readiness without importing optional code eagerly."""

    report = registry.report if isinstance(registry, ThirdPartyComponentRegistry) else validate_component_registry(registry)
    checked = _parse_datetime(checked_at, "checked_at") if checked_at else datetime.now().astimezone()
    items: list[dict[str, Any]] = []
    for component in report["components"]:
        decision = str(component["decision"])
        package_name = str(component["package_name"])
        import_name = str(component.get("import_name") or package_name)
        if decision in {"REFERENCE_ONLY", "LICENSE_REVIEW_REQUIRED", "DISABLED"} or component.get("enabled") is False:
            status = "DISABLED" if decision not in {"LICENSE_REVIEW_REQUIRED", "REFERENCE_ONLY"} else "REJECTED"
            reason = "component is not enabled for the default runtime"
            available = False
            installed_version = ""
        else:
            available = util.find_spec(import_name) is not None
            installed_version = _installed_version(package_name) if available else ""
            status = "READY" if available else "UNAVAILABLE"
            reason = "" if available else f"optional package is not installed: {package_name}"
        items.append(
            {
                "component_id": component["component_id"],
                "package_name": package_name,
                "import_name": import_name,
                "decision": decision,
                "adapter_kind": component["adapter_kind"],
                "status": status,
                "available": available,
                "installed_version": installed_version,
                "registered_version": component["version_or_commit"],
                "license_status": component["license_status"],
                "reason": reason,
                "network_required": component["network_required"],
                "token_required": component["token_required"],
                "checked_at": checked.isoformat(),
            }
        )
    effective_id = str(snapshot_id or "").strip() or f"health-{_compact(checked.isoformat())}"
    return {
        "schema_version": COMPONENT_HEALTH_SCHEMA_VERSION,
        "snapshot_id": f"third-party-health-{effective_id.removeprefix('third-party-health-')}",
        "registry_id": report["registry_id"],
        "registry_version": report["version"],
        "registry_hash": report["content_hash"],
        "checked_at": checked.isoformat(),
        "components": items,
        "component_count": len(items),
        "ready_count": sum(item["status"] == "READY" for item in items),
        "unavailable_count": sum(item["status"] == "UNAVAILABLE" for item in items),
        "rule_version": RULE_VERSION,
        "policy": {
            "local_only_check": True,
            "remote_endpoint_not_tested": True,
            "health_is_not_fetch_success": True,
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


def validate_component_health_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(snapshot, Mapping) or snapshot.get("schema_version") != COMPONENT_HEALTH_SCHEMA_VERSION:
        raise ThirdPartyComponentError(f"input must be {COMPONENT_HEALTH_SCHEMA_VERSION}")
    if snapshot.get("immutable") is not True:
        raise ThirdPartyComponentError("health snapshot must be immutable")
    if not str(snapshot.get("registry_hash") or "").strip():
        raise ThirdPartyComponentError("health snapshot registry_hash is required")
    if not isinstance(snapshot.get("components"), list):
        raise ThirdPartyComponentError("health snapshot components must be a list")
    invalid = [
        str(item.get("status") or "")
        for item in snapshot["components"]
        if not isinstance(item, Mapping) or str(item.get("status") or "") not in HEALTH_STATUSES
    ]
    if invalid:
        raise ThirdPartyComponentError("health snapshot contains unsupported status")
    return dict(snapshot)


class DocumentParserAdapter:
    """Base contract for local document extraction adapters."""

    component_id = ""

    def health_check(self) -> dict[str, Any]:
        raise NotImplementedError

    def parse(
        self,
        raw_content: bytes,
        *,
        document_id: str,
        research_as_of: str,
        source_uri: str = "",
    ) -> dict[str, Any]:
        raise NotImplementedError


class PypdfDocumentParser(DocumentParserAdapter):
    component_id = "pypdf"

    def health_check(self) -> dict[str, Any]:
        return _module_health("pypdf", "pypdf")

    def parse(self, raw_content: bytes, *, document_id: str, research_as_of: str, source_uri: str = "") -> dict[str, Any]:
        module = _require_module("pypdf", "pypdf")
        try:
            reader = module.PdfReader(_bytes_stream(raw_content))
        except Exception as error:
            raise ThirdPartyComponentError(f"pypdf could not open document: {error}") from error
        pages: list[dict[str, Any]] = []
        warnings: list[str] = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                text = str(page.extract_text() or "")
            except Exception as error:
                text = ""
                warnings.append(f"page {page_number} text extraction failed: {error}")
            pages.append(_page_record(page_number, text, locator={"page": page_number}))
        return _document_result(
            self.component_id,
            raw_content,
            document_id=document_id,
            research_as_of=research_as_of,
            source_uri=source_uri,
            pages=pages,
            tables=[],
            warnings=warnings,
        )


class PdfplumberDocumentParser(DocumentParserAdapter):
    component_id = "pdfplumber"

    def health_check(self) -> dict[str, Any]:
        return _module_health("pdfplumber", "pdfplumber")

    def parse(self, raw_content: bytes, *, document_id: str, research_as_of: str, source_uri: str = "") -> dict[str, Any]:
        module = _require_module("pdfplumber", "pdfplumber")
        pages: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []
        warnings: list[str] = []
        try:
            with module.open(_bytes_stream(raw_content)) as pdf:
                for page_number, page in enumerate(pdf.pages, start=1):
                    try:
                        text = str(page.extract_text() or "")
                        pages.append(
                            _page_record(
                                page_number,
                                text,
                                locator={"page": page_number, "bbox": list(page.bbox)},
                            )
                        )
                        for table_number, table in enumerate(page.extract_tables() or [], start=1):
                            tables.append(
                                {
                                    "page": page_number,
                                    "table": table_number,
                                    "rows": table,
                                    "locator": {"page": page_number, "table": table_number},
                                }
                            )
                    except Exception as error:
                        warnings.append(f"page {page_number} extraction failed: {error}")
        except Exception as error:
            raise ThirdPartyComponentError(f"pdfplumber could not open document: {error}") from error
        return _document_result(
            self.component_id,
            raw_content,
            document_id=document_id,
            research_as_of=research_as_of,
            source_uri=source_uri,
            pages=pages,
            tables=tables,
            warnings=warnings,
        )


class CamelotDocumentParser(DocumentParserAdapter):
    component_id = "camelot"

    def health_check(self) -> dict[str, Any]:
        return _module_health("camelot", "camelot")

    def parse(self, raw_content: bytes, *, document_id: str, research_as_of: str, source_uri: str = "") -> dict[str, Any]:
        module = _require_module("camelot", "camelot")
        tables: list[dict[str, Any]] = []
        warnings: list[str] = []
        with tempfile.NamedTemporaryFile(suffix=".pdf") as temporary:
            temporary.write(raw_content)
            temporary.flush()
            try:
                extracted = module.read_pdf(temporary.name, pages="all")
                for order, table in enumerate(extracted, start=1):
                    try:
                        rows = table.df.to_dict(orient="records")
                    except Exception as error:
                        rows = []
                        warnings.append(f"table {order} conversion failed: {error}")
                    report = getattr(table, "parsing_report", {}) or {}
                    tables.append(
                        {
                            "page": str(report.get("page") or ""),
                            "table": order,
                            "rows": rows,
                            "parsing_report": dict(report),
                            "locator": {"page": str(report.get("page") or ""), "table": order},
                        }
                    )
            except Exception as error:
                raise ThirdPartyComponentError(f"Camelot could not parse document: {error}") from error
        return _document_result(
            self.component_id,
            raw_content,
            document_id=document_id,
            research_as_of=research_as_of,
            source_uri=source_uri,
            pages=[],
            tables=tables,
            warnings=warnings,
        )


def parse_local_document(
    component_id: str,
    raw_content: bytes,
    *,
    document_id: str,
    research_as_of: str,
    source_uri: str = "",
) -> dict[str, Any]:
    """Parse a local document through one of the explicitly selected adapters."""

    if not isinstance(raw_content, (bytes, bytearray)) or not raw_content:
        raise ThirdPartyComponentError("raw_content must be non-empty bytes")
    if not str(document_id or "").strip():
        raise ThirdPartyComponentError("document_id is required")
    _parse_datetime(research_as_of, "research_as_of")
    parser = {
        "pypdf": PypdfDocumentParser(),
        "pdfplumber": PdfplumberDocumentParser(),
        "camelot": CamelotDocumentParser(),
    }.get(str(component_id or "").strip().lower())
    if parser is None:
        raise ThirdPartyComponentError(f"unsupported document parser component: {component_id}")
    return parser.parse(bytes(raw_content), document_id=document_id, research_as_of=research_as_of, source_uri=source_uri)


def build_performance_metrics_report(
    payload: Mapping[str, Any],
    *,
    result_id: str = "",
) -> dict[str, Any]:
    """Calculate observable performance metrics with an optional quantstats backend."""

    if not isinstance(payload, Mapping) or payload.get("schema_version") != PERFORMANCE_INPUT_SCHEMA_VERSION:
        raise ThirdPartyComponentError(f"input must be {PERFORMANCE_INPUT_SCHEMA_VERSION}")
    as_of = _parse_datetime(payload.get("as_of"), "as_of")
    asset = _series(payload.get("asset_series"), "asset_series", as_of)
    benchmark = _series(payload.get("benchmark_series"), "benchmark_series", as_of)
    if len(asset) != len(benchmark) or [row["day"] for row in asset] != [row["day"] for row in benchmark]:
        raise ThirdPartyComponentError("asset_series and benchmark_series must share dates")
    periods_per_year = _positive_number(payload.get("periods_per_year") or 252, "periods_per_year")
    asset_returns = _returns(asset)
    benchmark_returns = _returns(benchmark)
    asset_total = asset[-1]["value"] / asset[0]["value"] - 1.0
    benchmark_total = benchmark[-1]["value"] / benchmark[0]["value"] - 1.0
    asset_annualized = _annualized(asset_total, len(asset_returns), periods_per_year)
    benchmark_annualized = _annualized(benchmark_total, len(benchmark_returns), periods_per_year)
    backend = _quantstats_metrics(asset_returns, benchmark_returns, periods_per_year)
    effective_id = str(result_id or payload.get("result_id") or "performance").strip()
    return {
        "schema_version": PERFORMANCE_SCHEMA_VERSION,
        "result_id": f"third-party-performance-{effective_id.removeprefix('third-party-performance-')}",
        "as_of": as_of.isoformat(),
        "asset_return": asset_total,
        "benchmark_return": benchmark_total,
        "excess_return": asset_total - benchmark_total,
        "asset_annualized_return": asset_annualized,
        "benchmark_annualized_return": benchmark_annualized,
        "asset_max_drawdown": _max_drawdown([row["value"] for row in asset]),
        "benchmark_max_drawdown": _max_drawdown([row["value"] for row in benchmark]),
        "asset_volatility": _volatility(asset_returns, periods_per_year),
        "benchmark_volatility": _volatility(benchmark_returns, periods_per_year),
        "periods_per_year": periods_per_year,
        "observation_count": len(asset),
        "backend": "quantstats" if backend is not None else "local",
        "backend_metrics": backend or {},
        "policy": {
            "observable_statistics_only": True,
            "does_not_replace_locked_benchmark": True,
            "does_not_perform_causal_attribution": True,
            "does_not_create_decision_snapshot": True,
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


def validate_performance_metrics_report(report: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(report, Mapping) or report.get("schema_version") != PERFORMANCE_SCHEMA_VERSION:
        raise ThirdPartyComponentError(f"input must be {PERFORMANCE_SCHEMA_VERSION}")
    for field in ("result_id", "as_of", "asset_return", "benchmark_return", "excess_return"):
        if field not in report:
            raise ThirdPartyComponentError(f"performance result is missing {field}")
    if report.get("immutable") is not True:
        raise ThirdPartyComponentError("performance result must be immutable")
    return dict(report)


def _dependency_requirements(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        values: list[str] = []
        for key, item in value.items():
            if isinstance(item, (list, tuple)):
                values.extend(f"{key}: {entry}" for entry in item)
            else:
                values.append(f"{key}: {item}")
        return values
    return _string_list(value)


def _normalize_component(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ThirdPartyComponentError("each component must be an object")
    identifier = str(raw.get("component_id") or "").strip()
    project_url = str(raw.get("project_url") or "").strip()
    package_name = str(raw.get("package_name") or "").strip()
    version = str(raw.get("version_or_commit") or "").strip()
    adapter_kind = str(raw.get("adapter_kind") or "").strip()
    decision = str(raw.get("decision") or "").strip().upper()
    license_status = str(raw.get("license_status") or "").strip()
    capability_scope = _string_list(raw.get("capability_scope"))
    if not identifier or not project_url.startswith(("http://", "https://")) or not package_name or not version:
        raise ThirdPartyComponentError("component_id, project_url, package_name, and version_or_commit are required")
    if adapter_kind not in PARSER_KINDS:
        raise ThirdPartyComponentError(f"unsupported adapter_kind: {adapter_kind}")
    if decision not in COMPONENT_DECISIONS:
        raise ThirdPartyComponentError(f"unsupported component decision: {decision or '<empty>'}")
    if not license_status:
        raise ThirdPartyComponentError(f"{identifier}: license_status is required")
    if not capability_scope:
        raise ThirdPartyComponentError(f"{identifier}: capability_scope is required")
    if decision == "FORK_AND_MODIFY" and not _string_list(raw.get("modification_log")):
        raise ThirdPartyComponentError(f"{identifier}: FORK_AND_MODIFY requires modification_log")
    enabled = bool(raw.get("enabled", True))
    candidate_review_id = str(raw.get("candidate_review_id") or "").strip()
    capability_slice = str(raw.get("capability_slice") or "").strip()
    candidate_review_state = str(raw.get("candidate_review_state") or "DISCOVERED").strip().upper()
    adapter_registration_id = str(raw.get("adapter_registration_id") or "").strip()
    baseline_id = str(raw.get("baseline_id") or "").strip()
    enable_conditions = raw.get("enable_conditions") or {}
    if not isinstance(enable_conditions, (Mapping, list, tuple)):
        raise ThirdPartyComponentError(f"{identifier}: enable_conditions must be an object or list")
    if enabled and decision in ACTIVE_COMPONENT_DECISIONS:
        if not candidate_review_id or not capability_slice or not adapter_registration_id:
            raise ThirdPartyComponentError(
                f"{identifier}: enabled component requires candidate_review_id, capability_slice, and adapter_registration_id"
            )
        if candidate_review_state not in {"ACCEPTED", "CONDITIONAL"}:
            raise ThirdPartyComponentError(
                f"{identifier}: enabled component requires ACCEPTED or CONDITIONAL candidate review"
            )
        if not _string_list(raw.get("validation_fixture_ids")):
            raise ThirdPartyComponentError(f"{identifier}: enabled component requires validation_fixture_ids")
        if not baseline_id:
            raise ThirdPartyComponentError(f"{identifier}: enabled component requires baseline_id")
        if str(raw.get("regression_status") or "").strip().upper() not in {"PASS", "PASSED"}:
            raise ThirdPartyComponentError(f"{identifier}: enabled component requires regression_status PASS")
        if not str(raw.get("fallback_component") or "").strip():
            raise ThirdPartyComponentError(f"{identifier}: enabled component requires fallback_component")
        if candidate_review_state == "CONDITIONAL" and not enable_conditions:
            raise ThirdPartyComponentError(f"{identifier}: CONDITIONAL component requires enable_conditions")
    return {
        "component_id": identifier,
        "project_url": project_url,
        "package_name": package_name,
        "import_name": str(raw.get("import_name") or package_name).strip(),
        "version_or_commit": version,
        "license_snapshot": str(raw.get("license_snapshot") or ""),
        "license_status": license_status,
        "additional_terms": _string_list(raw.get("additional_terms")),
        "adapter_name": str(raw.get("adapter_name") or f"{identifier}-adapter"),
        "adapter_kind": adapter_kind,
        "capability_scope": capability_scope,
        "python_and_os_requirements": _string_list(raw.get("python_and_os_requirements")),
        "network_required": bool(raw.get("network_required", False)),
        "token_required": bool(raw.get("token_required", False)),
        "temporal_cutoff_support": str(raw.get("temporal_cutoff_support") or "UNKNOWN"),
        "future_function_risk": str(raw.get("future_function_risk") or "UNKNOWN"),
        "validation_fixture_ids": _string_list(raw.get("validation_fixture_ids")),
        "regression_status": str(raw.get("regression_status") or "NOT_RUN"),
        "fallback_component": str(raw.get("fallback_component") or ""),
        "candidate_review_id": candidate_review_id,
        "capability_slice": capability_slice,
        "candidate_review_state": candidate_review_state,
        "adapter_registration_id": adapter_registration_id,
        "baseline_id": baseline_id,
        "enable_conditions": dict(enable_conditions) if isinstance(enable_conditions, Mapping) else list(enable_conditions),
        "decision": decision,
        "enabled": enabled,
        "modification_log": _string_list(raw.get("modification_log")),
    }


def _document_result(
    component_id: str,
    raw_content: bytes,
    *,
    document_id: str,
    research_as_of: str,
    source_uri: str,
    pages: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    extracted = "\n".join(str(page.get("text") or "") for page in pages)
    status = "READY" if (pages or tables) and not warnings else "PARTIAL" if pages or tables else "BLOCKED"
    return {
        "schema_version": DOCUMENT_PARSE_SCHEMA_VERSION,
        "result_id": f"document-parse-{component_id}-{_hash_bytes(raw_content)[:16]}",
        "component_id": component_id,
        "adapter_version": RULE_VERSION,
        "document_id": document_id,
        "research_as_of": research_as_of,
        "source_uri": source_uri,
        "raw_content_hash": _hash_bytes(raw_content),
        "raw_content_size_bytes": len(raw_content),
        "status": status,
        "pages": pages,
        "tables": tables,
        "page_count": len(pages),
        "table_count": len(tables),
        "extracted_text_hash": _hash_bytes(extracted.encode("utf-8")),
        "warnings": warnings,
        "policy": {
            "local_input_only": True,
            "extraction_is_not_fact_verification": True,
            "requires_source_document_and_evidence_review": True,
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


def _page_record(page_number: int, text: str, *, locator: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "page": page_number,
        "text": text,
        "text_hash": _hash_bytes(text.encode("utf-8")),
        "locator": dict(locator),
    }


def _series(value: Any, field: str, as_of: datetime) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or len(value) < 2:
        raise ThirdPartyComponentError(f"{field} must contain at least two points")
    output: list[dict[str, Any]] = []
    previous: date | None = None
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise ThirdPartyComponentError(f"{field}[{index}] must be an object")
        day = _parse_datetime(raw.get("date") or raw.get("timestamp"), f"{field}[{index}].date")
        number = _positive_number(raw.get("value") or raw.get("price") or raw.get("close"), f"{field}[{index}].value")
        if day.date() > as_of.date():
            raise ThirdPartyComponentError(f"{field}[{index}] is after as_of")
        if previous is not None and day.date() <= previous:
            raise ThirdPartyComponentError(f"{field} dates must be strictly increasing")
        previous = day.date()
        output.append({"day": day, "value": number})
    return output


def _returns(series: Sequence[Mapping[str, Any]]) -> list[float]:
    return [float(series[index]["value"]) / float(series[index - 1]["value"]) - 1.0 for index in range(1, len(series))]


def _quantstats_metrics(asset: Sequence[float], benchmark: Sequence[float], periods_per_year: float) -> dict[str, Any] | None:
    try:
        qs = import_module("quantstats")
        pandas = import_module("pandas")
        asset_series = pandas.Series(asset)
        benchmark_series = pandas.Series(benchmark)
        return {
            "max_drawdown": float(qs.stats.max_drawdown(asset_series)),
            "volatility": float(qs.stats.volatility(asset_series, periods=int(periods_per_year))),
            "sharpe": float(qs.stats.sharpe(asset_series, periods=int(periods_per_year))),
            "benchmark_volatility": float(qs.stats.volatility(benchmark_series, periods=int(periods_per_year))),
        }
    except Exception:
        return None


def _module_health(package_name: str, import_name: str) -> dict[str, Any]:
    available = util.find_spec(import_name) is not None
    return {
        "package_name": package_name,
        "import_name": import_name,
        "available": available,
        "status": "READY" if available else "UNAVAILABLE",
        "reason": "" if available else f"optional package is not installed: {package_name}",
        "local_only": True,
    }


def _require_module(package_name: str, import_name: str) -> Any:
    if util.find_spec(import_name) is None:
        raise ThirdPartyComponentError(f"optional package is not installed: {package_name}")
    try:
        return import_module(import_name)
    except Exception as error:
        raise ThirdPartyComponentError(f"optional package cannot be imported: {package_name}: {error}") from error


def _installed_version(package_name: str) -> str:
    try:
        from importlib import metadata

        return str(metadata.version(package_name))
    except Exception:
        return "unknown"


def _bytes_stream(value: bytes):
    from io import BytesIO

    return BytesIO(value)


def _positive_number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ThirdPartyComponentError(f"{field} must be numeric") from error
    if number <= 0:
        raise ThirdPartyComponentError(f"{field} must be positive")
    return number


def _annualized(total: float, periods: int, periods_per_year: float) -> float:
    if periods <= 0:
        return 0.0
    return -1.0 if 1.0 + total <= 0 else (1.0 + total) ** (periods_per_year / periods) - 1.0


def _max_drawdown(values: Sequence[float]) -> float:
    peak = float(values[0])
    maximum = 0.0
    for value in values:
        peak = max(peak, float(value))
        maximum = max(maximum, 1.0 - float(value) / peak)
    return -maximum


def _volatility(values: Sequence[float], periods_per_year: float) -> float:
    if not values:
        return 0.0
    average = sum(values) / len(values)
    variance = sum((value - average) ** 2 for value in values) / len(values)
    return variance**0.5 * periods_per_year**0.5


def _parse_datetime(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ThirdPartyComponentError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        try:
            parsed = datetime.combine(date.fromisoformat(text), datetime.min.time())
        except ValueError:
            raise ThirdPartyComponentError(f"{field} must be ISO date or datetime") from error
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone()


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise ThirdPartyComponentError("expected a string list")
    return [str(item).strip() for item in value if str(item).strip()]


def _hash_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _hash_payload(value: Any) -> str:
    return _hash_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))


def _compact(value: str) -> str:
    return str(value).replace(":", "").replace("+", "plus").replace("/", "-").replace(" ", "_")
