"""Small, serialisable domain objects for the industry-first workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class IndustryState(StrEnum):
    DETERIORATING = "DETERIORATING"
    CLEARING = "CLEARING"
    INFLECTION_CANDIDATE = "INFLECTION_CANDIDATE"
    REVERSAL_CONFIRMED = "REVERSAL_CONFIRMED"
    MATURE = "MATURE"
    RELAPSE = "RELAPSE"
    INSUFFICIENT = "INSUFFICIENT"


class CompanyDataTier(StrEnum):
    LIGHT = "LIGHT"
    SUPPLEMENTAL = "SUPPLEMENTAL"
    DEEP = "DEEP"
    AI_DEEP = "AI_DEEP"


@dataclass(frozen=True)
class IndustrySignal:
    """One industry-level observation; it does not imply a company conclusion."""

    name: str
    value: Any
    as_of: str
    source: str
    evidence_status: str = "UNVERIFIED"
    note: str = ""


@dataclass(frozen=True)
class IndustryRadarSnapshot:
    industry_id: str
    display_name: str
    as_of: str
    state: IndustryState
    signals: tuple[IndustrySignal, ...] = ()
    evidence_completeness: str = "UNKNOWN"
    opportunity_types: tuple[str, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload


@dataclass(frozen=True)
class CompanyCandidate:
    company_id: str
    display_name: str
    industry_id: str
    data_tier: CompanyDataTier = CompanyDataTier.LIGHT
    source: str = ""
    inclusion_reason: str = ""
    hard_gate_status: str = "PENDING"
    score: float | None = None
    notes: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def with_tier(self, tier: CompanyDataTier) -> "CompanyCandidate":
        return CompanyCandidate(
            company_id=self.company_id,
            display_name=self.display_name,
            industry_id=self.industry_id,
            data_tier=tier,
            source=self.source,
            inclusion_reason=self.inclusion_reason,
            hard_gate_status=self.hard_gate_status,
            score=self.score,
            notes=self.notes,
            metadata=self.metadata,
        )

    def with_metadata(self, metadata: dict[str, Any]) -> "CompanyCandidate":
        return CompanyCandidate(
            company_id=self.company_id,
            display_name=self.display_name,
            industry_id=self.industry_id,
            data_tier=self.data_tier,
            source=self.source,
            inclusion_reason=self.inclusion_reason,
            hard_gate_status=self.hard_gate_status,
            score=self.score,
            notes=self.notes,
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["data_tier"] = self.data_tier.value
        return payload


@dataclass(frozen=True)
class ResourcePolicy:
    """Limits that prevent opportunity discovery from becoming a full-market download."""

    max_selected_industries: int = 10
    company_pool_size: int = 30
    supplemental_company_limit: int = 10
    deep_company_limit: int = 5
    ai_deep_company_limit: int = 3
    allow_full_market_deep_data: bool = False

    def validate(self) -> None:
        limits = (
            self.max_selected_industries,
            self.company_pool_size,
            self.supplemental_company_limit,
            self.deep_company_limit,
            self.ai_deep_company_limit,
        )
        if any(value < 1 for value in limits):
            raise ValueError("resource limits must be positive")
        if not (
            self.ai_deep_company_limit
            <= self.deep_company_limit
            <= self.supplemental_company_limit
            <= self.company_pool_size
        ):
            raise ValueError("company data tiers must narrow at every stage")
        if self.allow_full_market_deep_data:
            raise ValueError(
                "full-market deep data is opt-in and must use a separate approved workflow"
            )


@dataclass
class ScanResult:
    scan_id: str
    as_of: str
    selected_industries: list[IndustryRadarSnapshot] = field(default_factory=list)
    company_pools: dict[str, list[CompanyCandidate]] = field(default_factory=dict)
    rejected_industries: list[str] = field(default_factory=list)
    rejected_companies: list[CompanyCandidate] = field(default_factory=list)
    industry_opportunity_assessments: dict[str, dict[str, Any]] = field(default_factory=dict)
    resource_audit: dict[str, int | bool] = field(default_factory=dict)
    empty_result: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "as_of": self.as_of,
            "selected_industries": [item.to_dict() for item in self.selected_industries],
            "company_pools": {
                key: [candidate.to_dict() for candidate in candidates]
                for key, candidates in self.company_pools.items()
            },
            "rejected_industries": self.rejected_industries,
            "rejected_companies": [item.to_dict() for item in self.rejected_companies],
            "industry_opportunity_assessments": self.industry_opportunity_assessments,
            "resource_audit": self.resource_audit,
            "empty_result": self.empty_result,
        }
