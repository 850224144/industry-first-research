"""Bounded company-research input assembly.

This module assembles a small, auditable company snapshot from the source
router. It does not infer valuation or investment advice from incomplete data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
