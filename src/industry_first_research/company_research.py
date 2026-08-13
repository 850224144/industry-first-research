"""Bounded company-research input assembly.

This module assembles a small, auditable company snapshot from the source
router. It does not infer valuation or investment advice from incomplete data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
from typing import Any

from .data_sources import (
    DataSourceExhaustedError,
    DataSourceRouter,
    RoutedDataResult,
)
from .company_scope import CompanyScopeError, scope_item_for_company


@dataclass(frozen=True)
class CompanyResearchQuery:
    company_id: str
    display_name: str = ""
    industry_id: str = ""
    business_scope: tuple[str, ...] = ()
    products: tuple[dict[str, Any], ...] = ()
    as_of: str = ""
    identity_query: dict[str, Any] = field(default_factory=dict)
    financial_query: dict[str, Any] = field(default_factory=dict)
    quote_query: dict[str, Any] = field(default_factory=dict)
    source_names: tuple[str, ...] = ()
    company_scope: dict[str, Any] | None = None


@dataclass
class CompanyResearchSnapshot:
    company_id: str
    display_name: str
    industry_id: str
    business_scope: tuple[str, ...]
    products: tuple[dict[str, Any], ...]
    as_of: str
    research_status: str
    identity: dict[str, Any] | None = None
    financials: dict[str, Any] | None = None
    quote: dict[str, Any] | None = None
    source_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    company_scope: dict[str, Any] | None = None
    industry_chain: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CompanyResearchAssembler:
    def __init__(self, router: DataSourceRouter) -> None:
        self.router = router

    def collect(self, query: CompanyResearchQuery) -> CompanyResearchSnapshot:
        snapshot = CompanyResearchSnapshot(
            company_id=query.company_id,
            display_name=query.display_name,
            industry_id=query.industry_id,
            business_scope=query.business_scope,
            products=query.products,
            as_of=query.as_of,
            research_status="INSUFFICIENT",
            company_scope=None,
            industry_chain=_load_industry_chain_profile(query.company_id),
        )
        if query.company_scope is not None:
            try:
                snapshot.company_scope = scope_item_for_company(
                    query.company_scope, query.company_id
                )
                if snapshot.company_scope is None:
                    snapshot.errors.append("company_scope: company_id does not match scope report")
                elif snapshot.company_scope["researchability_state"] == "BLOCKED":
                    snapshot.research_status = "BLOCKED"
                elif snapshot.company_scope["researchability_state"] == "INSUFFICIENT":
                    snapshot.research_status = "INSUFFICIENT"
            except CompanyScopeError as error:
                snapshot.errors.append(f"company_scope: {error}")
                snapshot.research_status = "BLOCKED"
        self._collect_section(snapshot, "identity", query.identity_query, query)
        self._collect_section(snapshot, "financials", query.financial_query, query)
        self._collect_section(snapshot, "quote", query.quote_query, query)
        section_count = sum(
            value is not None
            for value in (snapshot.identity, snapshot.financials, snapshot.quote)
        )
        section_status = (
            "READY" if section_count == 3 else "PARTIAL" if section_count else "INSUFFICIENT"
        )
        scope_status = str((snapshot.company_scope or {}).get("researchability_state") or "").upper()
        if scope_status == "BLOCKED" or snapshot.research_status == "BLOCKED":
            snapshot.research_status = "BLOCKED"
        elif scope_status == "INSUFFICIENT" or snapshot.research_status == "INSUFFICIENT" and not section_count:
            snapshot.research_status = "INSUFFICIENT"
        elif scope_status == "PARTIAL" or section_status != "READY":
            snapshot.research_status = "PARTIAL"
        else:
            snapshot.research_status = section_status
        return snapshot

    def _collect_section(
        self,
        snapshot: CompanyResearchSnapshot,
        section: str,
        query: dict[str, Any],
        company_query: CompanyResearchQuery,
    ) -> None:
        if not query:
            snapshot.missing_fields.append(f"{section}.query")
            return
        try:
            result = self.router.fetch(
                query,
                company_query.as_of,
                subject_type="listed_company",
                source_names=company_query.source_names or None,
            )
        except Exception as error:
            if isinstance(error, DataSourceExhaustedError):
                snapshot.source_results[section] = {
                    "source": None,
                    "data": None,
                    "attempts": [attempt.to_dict() for attempt in error.attempts],
                    "requested_sources": list(error.requested_sources),
                }
            snapshot.errors.append(f"{section}: {type(error).__name__}: {error}")
            return
        value = result.data
        setattr(snapshot, section, value)
        snapshot.source_results[section] = result.to_dict()


def snapshot_from_config(config: dict[str, Any]) -> CompanyResearchQuery:
    return CompanyResearchQuery(
        company_id=config["company_id"],
        display_name=config.get("display_name", ""),
        industry_id=config.get("industry_id", ""),
        business_scope=tuple(config.get("business_scope", [])),
        products=tuple(config.get("products", [])),
        as_of=config["as_of"],
        identity_query=dict(config.get("identity_query", {})),
        financial_query=dict(config.get("financial_query", {})),
        quote_query=dict(config.get("quote_query", {})),
        source_names=tuple(config.get("source_names", [])),
        company_scope=dict(config["company_scope"]) if isinstance(config.get("company_scope"), dict) else None,
    )


def _load_industry_chain_profile(company_id: str) -> dict[str, Any] | None:
    """Load the shared V2 company/product graph for the formal CLI path.

    The legacy ``research_system`` analyzer and the package CLI now consume
    the same JSON records.  Missing local data is represented as ``None`` so
    the source router can still produce a bounded company snapshot.
    """
    raw_code = str(company_id or "").strip().upper()
    code = raw_code.split(".", 1)[0]
    if not code:
        return None
    configured_dir = os.environ.get("INDUSTRY_CHAIN_DATA_DIR", "").strip()
    data_dir = Path(configured_dir) if configured_dir else (
        Path(__file__).resolve().parents[2] / "data" / "industry_chains"
    )
    try:
        products = json.loads((data_dir / "products.json").read_text(encoding="utf-8"))
        relations = json.loads((data_dir / "product_relations.json").read_text(encoding="utf-8"))
        companies = json.loads((data_dir / "company_products.json").read_text(encoding="utf-8"))
        metadata_path = data_dir / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(products, list) or not isinstance(relations, list) or not isinstance(companies, list):
        return None
    metadata_is_object = isinstance(metadata, dict)
    if not metadata_is_object:
        metadata = {}
    company = next(
        (
            item
            for item in companies
            if isinstance(item, dict)
            and str(item.get("stock_code") or "").split(".", 1)[0] == code
        ),
        None,
    )
    if not isinstance(company, dict):
        return None
    product_by_name = {
        str(item.get("name")): item for item in products if isinstance(item, dict) and item.get("name")
    }
    names = [name for name in company.get("products") or [] if name in product_by_name]
    actual_counts = {
        "products": len(products),
        "relations": len(relations),
        "companies": len(companies),
    }
    validation_errors: list[str] = []
    if not metadata_is_object:
        validation_errors.append("metadata must be an object")
    if metadata.get("schema_version") != "industry-chain.v2":
        validation_errors.append("unsupported or missing schema_version")
    if metadata.get("relation_semantics") != "directed_supply_edge":
        validation_errors.append("unsupported or missing relation_semantics")
    if metadata.get("counts") != actual_counts:
        validation_errors.append("metadata counts do not match loaded records")
    unknown_company_products = [
        name for name in company.get("products") or [] if name not in product_by_name
    ]
    if unknown_company_products:
        validation_errors.append("company references unknown products")
    upstream: dict[str, dict[str, Any]] = {}
    downstream: dict[str, dict[str, Any]] = {}
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        if relation.get("relation") != "upstream":
            continue
        source = str(relation.get("from") or "")
        target = str(relation.get("to") or "")
        if target in names and source in product_by_name:
            upstream[source] = product_by_name[source]
        if source in names and target in product_by_name:
            downstream[target] = product_by_name[target]
    return {
        "data_version": str(metadata.get("schema_version") or "industry-chain.v2"),
        "source": str(metadata.get("source") or "industry_chain_v2"),
        "source_status": str(metadata.get("source_status") or "UNKNOWN"),
        "license_status": str(metadata.get("license_status") or "UNVERIFIED"),
        "validation_status": "VALID" if not validation_errors else "INVALID",
        "validation_errors": validation_errors,
        "company": company,
        "products": [product_by_name[name] for name in names],
        "upstream_products": list(upstream.values()),
        "downstream_products": list(downstream.values()),
    }
