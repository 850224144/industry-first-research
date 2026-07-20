"""Protocols for data and research assets.

The first implementation accepts local providers. Network integrations are deliberately
outside the core so a missing API or web AI session cannot change the research rules.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

from .models import CompanyCandidate, CompanyDataTier, IndustryRadarSnapshot


class IndustryRadarProvider(Protocol):
    def snapshots(self, as_of: str) -> Iterable[IndustryRadarSnapshot]: ...


class CompanyPoolProvider(Protocol):
    def candidates(
        self, industry: IndustryRadarSnapshot, limit: int
    ) -> Sequence[CompanyCandidate]: ...


class CompanyDataProvider(Protocol):
    def enrich(
        self, candidates: Sequence[CompanyCandidate], tier: CompanyDataTier
    ) -> Sequence[CompanyCandidate]: ...


class ChainedCompanyData:
    """Apply bounded company-data providers in order while preserving profiles."""

    def __init__(self, providers: Sequence[CompanyDataProvider]) -> None:
        if not providers:
            raise ValueError("providers must not be empty")
        self.providers = tuple(providers)

    def enrich(
        self, candidates: Sequence[CompanyCandidate], tier: CompanyDataTier
    ) -> Sequence[CompanyCandidate]:
        enriched = list(candidates)
        for provider in self.providers:
            enriched = list(provider.enrich(enriched, tier))
        return enriched


class DeepResearchProvider(Protocol):
    def research(self, candidates: Sequence[CompanyCandidate]) -> Sequence[CompanyCandidate]: ...
