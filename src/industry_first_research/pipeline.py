"""Industry-first opportunity discovery orchestration."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from uuid import uuid4

from .adapters import CompanyDataProvider, CompanyPoolProvider, DeepResearchProvider, IndustryRadarProvider
from .models import (
    CompanyCandidate,
    CompanyDataTier,
    IndustryRadarSnapshot,
    IndustryState,
    ResourcePolicy,
    ScanResult,
)
from .screening import assess_company_opportunities, assess_industry_opportunities


_ELIGIBLE_STATES = {
    IndustryState.CLEARING,
    IndustryState.INFLECTION_CANDIDATE,
    IndustryState.REVERSAL_CONFIRMED,
}


class IndustryFirstDiscovery:
    """Run a bounded opportunity scan without downloading all company deep data."""

    def __init__(
        self,
        radar: IndustryRadarProvider,
        company_pool: CompanyPoolProvider,
        company_data: CompanyDataProvider,
        deep_research: DeepResearchProvider | None = None,
        policy: ResourcePolicy | None = None,
    ) -> None:
        self.radar = radar
        self.company_pool = company_pool
        self.company_data = company_data
        self.deep_research = deep_research
        self.policy = policy or ResourcePolicy()
        self.policy.validate()

    def run(self, as_of: str) -> ScanResult:
        snapshots = list(self.radar.snapshots(as_of))
        selected = [item for item in snapshots if item.state in _ELIGIBLE_STATES]
        selected.sort(key=self._priority, reverse=True)
        selected = selected[: self.policy.max_selected_industries]

        result = ScanResult(
            scan_id=f"scan-{uuid4().hex[:12]}",
            as_of=as_of,
            selected_industries=selected,
            rejected_industries=[
                item.industry_id for item in snapshots if item not in selected
            ],
            resource_audit={
                "radar_industry_count": len(snapshots),
                "selected_industry_count": len(selected),
                "full_market_deep_data": False,
                "company_pool_limit": self.policy.company_pool_size,
                "deep_company_limit": self.policy.deep_company_limit,
                "ai_deep_company_limit": self.policy.ai_deep_company_limit,
            },
        )
        result.industry_opportunity_assessments = {
            industry.industry_id: assess_industry_opportunities(industry)
            for industry in selected
        }

        light_data_company_count = 0
        for industry in selected:
            pool = list(self.company_pool.candidates(industry, self.policy.company_pool_size))
            pool = pool[: self.policy.company_pool_size]
            light_data_company_count += len(pool)
            industry_assessments = result.industry_opportunity_assessments.get(
                industry.industry_id, {}
            )
            pool = [
                candidate.with_metadata(
                    {
                        **candidate.metadata,
                        "opportunity_assessments": assess_company_opportunities(
                            candidate, industry_assessments
                        ),
                    }
                )
                for candidate in pool
            ]
            result.rejected_companies.extend(
                candidate
                for candidate in pool
                if candidate.hard_gate_status in {"REJECTED", "BLOCKED"}
            )
            pool = [
                candidate
                for candidate in pool
                if candidate.hard_gate_status not in {"REJECTED", "BLOCKED"}
            ]
            light = list(self.company_data.enrich(pool, CompanyDataTier.LIGHT))
            supplemental = list(
                self.company_data.enrich(
                    light[: self.policy.supplemental_company_limit],
                    CompanyDataTier.SUPPLEMENTAL,
                )
            )
            deep = list(
                self.company_data.enrich(
                    supplemental[: self.policy.deep_company_limit],
                    CompanyDataTier.DEEP,
                )
            )
            if self.deep_research is not None:
                deep = list(
                    self.deep_research.research(
                        deep[: self.policy.ai_deep_company_limit]
                    )
                )
                deep = [candidate.with_tier(CompanyDataTier.AI_DEEP) for candidate in deep]
            result.company_pools[industry.industry_id] = deep

        result.empty_result = not bool(
            result.selected_industries
            and any(result.company_pools.values())
        )
        result.resource_audit.update(
            {
                "light_data_company_count": light_data_company_count,
                "deep_data_company_count": sum(len(items) for items in result.company_pools.values()),
                "ai_deep_research_count": sum(
                    1 for items in result.company_pools.values() for item in items
                    if item.data_tier == CompanyDataTier.AI_DEEP
                ),
                "rejected_company_count": len(result.rejected_companies),
            }
        )
        return result

    @staticmethod
    def _priority(snapshot: IndustryRadarSnapshot) -> tuple[int, int, int]:
        state_priority = {
            IndustryState.REVERSAL_CONFIRMED: 3,
            IndustryState.INFLECTION_CANDIDATE: 2,
            IndustryState.CLEARING: 1,
        }
        evidence_priority = {"CROSS_VALIDATED": 2, "VERIFIED": 1}
        return (
            state_priority.get(snapshot.state, 0),
            evidence_priority.get(snapshot.evidence_completeness, 0),
            len(snapshot.signals),
        )


class InMemoryRadar:
    def __init__(self, snapshots: Iterable[IndustryRadarSnapshot]) -> None:
        self._snapshots = tuple(snapshots)

    def snapshots(self, as_of: str) -> Iterable[IndustryRadarSnapshot]:
        return self._snapshots


class InMemoryCompanyPool:
    def __init__(self, candidates_by_industry: dict[str, Sequence[CompanyCandidate]]) -> None:
        self._candidates = candidates_by_industry

    def candidates(self, industry: IndustryRadarSnapshot, limit: int) -> Sequence[CompanyCandidate]:
        return self._candidates.get(industry.industry_id, ())[:limit]


class PassThroughCompanyData:
    def enrich(
        self, candidates: Sequence[CompanyCandidate], tier: CompanyDataTier
    ) -> Sequence[CompanyCandidate]:
        return [candidate.with_tier(tier) for candidate in candidates]


class PassThroughDeepResearch:
    def research(self, candidates: Sequence[CompanyCandidate]) -> Sequence[CompanyCandidate]:
        return candidates


def current_as_of() -> str:
    """Return a timezone-aware ISO date for demo and CLI usage."""

    return datetime.now(timezone.utc).date().isoformat()
