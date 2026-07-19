"""Conservative cross-source industry evidence reconciliation."""

from __future__ import annotations

from collections.abc import Iterable
import re
import unicodedata
from typing import Any

from .adapters import IndustryRadarProvider
from .models import IndustryRadarSnapshot, IndustrySignal, IndustryState


_DIRECTIONAL_STATES = {IndustryState.CLEARING, IndustryState.DETERIORATING}


class CrossSourceIndustryRadar:
    """Combine two independent industry radars without inventing matches.

    A primary row becomes ``CROSS_VALIDATED`` only when an exact normalized name
    match exists and both sources report the same direction for the same date.
    Missing matches are marked ``SINGLE_SOURCE`` and ``INSUFFICIENT``; opposing
    directions are marked ``CONFLICTING`` and ``INSUFFICIENT``.
    """

    def __init__(
        self,
        primary: IndustryRadarProvider,
        secondary: IndustryRadarProvider,
        *,
        primary_name: str = "primary",
        secondary_name: str = "secondary",
    ) -> None:
        self.primary = primary
        self.secondary = secondary
        self.primary_name = primary_name
        self.secondary_name = secondary_name
        self._metadata: dict[str, Any] = {}

    def snapshots(self, as_of: str) -> Iterable[IndustryRadarSnapshot]:
        primary_items = list(self.primary.snapshots(as_of))
        secondary_items = list(self.secondary.snapshots(as_of))
        secondary_by_name = {
            normalize_industry_name(item.display_name): item
            for item in secondary_items
            if normalize_industry_name(item.display_name)
        }

        matched = 0
        cross_validated = 0
        conflicting = 0
        single_source = 0
        result: list[IndustryRadarSnapshot] = []
        for primary_item in primary_items:
            secondary_item = secondary_by_name.get(
                normalize_industry_name(primary_item.display_name)
            )
            merged, match_type = _merge_items(primary_item, secondary_item)
            result.append(merged)
            if secondary_item is not None:
                matched += 1
            if match_type == "CROSS_VALIDATED":
                cross_validated += 1
            elif match_type == "CONFLICTING":
                conflicting += 1
            else:
                single_source += 1

        self._metadata = {
            "provider": "cross_source",
            "as_of": as_of,
            "read_only": True,
            "primary": _provider_metadata(self.primary, as_of, self.primary_name),
            "secondary": _provider_metadata(self.secondary, as_of, self.secondary_name),
            "primary_row_count": len(primary_items),
            "secondary_row_count": len(secondary_items),
            "matched_row_count": matched,
            "cross_validated_row_count": cross_validated,
            "conflicting_row_count": conflicting,
            "single_source_row_count": single_source,
            "secondary_only_row_count": max(0, len(secondary_items) - matched),
        }
        return result

    def metadata(self, as_of: str) -> dict[str, Any]:
        return self._metadata or {
            "provider": "cross_source",
            "as_of": as_of,
            "read_only": True,
            "primary": _provider_metadata(self.primary, as_of, self.primary_name),
            "secondary": _provider_metadata(self.secondary, as_of, self.secondary_name),
        }


def normalize_industry_name(value: str) -> str:
    """Normalize only presentation noise; do not use fuzzy matching for evidence."""

    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    normalized = re.sub(r"[\s\-_/,，。·&()（）]+", "", normalized)
    for suffix in ("行业", "板块"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
    return normalized


def _merge_items(
    primary: IndustryRadarSnapshot,
    secondary: IndustryRadarSnapshot | None,
) -> tuple[IndustryRadarSnapshot, str]:
    if secondary is None:
        return (
            _replace_snapshot(
                primary,
                state=IndustryState.INSUFFICIENT,
                evidence_completeness="SINGLE_SOURCE",
                opportunity_types=(),
                reason=(
                    f"No exact normalized-name match in the {primary.display_name} "
                    "secondary source; held out of confirmation screening."
                ),
            ),
            "SINGLE_SOURCE",
        )

    merged_signals = primary.signals + tuple(
        IndustrySignal(
            f"{secondary_provider_prefix(secondary)}_{signal.name}",
            signal.value,
            signal.as_of,
            signal.source,
            signal.evidence_status,
            signal.note,
        )
        for signal in secondary.signals
    )
    if (
        primary.state in _DIRECTIONAL_STATES
        and secondary.state in _DIRECTIONAL_STATES
        and primary.state == secondary.state
    ):
        return (
            _replace_snapshot(
                primary,
                signals=merged_signals,
                evidence_completeness="CROSS_VALIDATED",
                reason=(
                    f"{primary.display_name} has the same daily direction in both "
                    "independent sources; this remains a strength clue, not a cycle confirmation."
                ),
            ),
            "CROSS_VALIDATED",
        )
    if primary.state in _DIRECTIONAL_STATES and secondary.state in _DIRECTIONAL_STATES:
        return (
            _replace_snapshot(
                primary,
                signals=merged_signals,
                state=IndustryState.INSUFFICIENT,
                evidence_completeness="CONFLICTING",
                opportunity_types=(),
                reason=(
                    f"{primary.display_name} has conflicting daily directions across "
                    "the two sources; held out of confirmation screening."
                ),
            ),
            "CONFLICTING",
        )
    return (
        _replace_snapshot(
            primary,
            signals=merged_signals,
            state=IndustryState.INSUFFICIENT,
            evidence_completeness="SINGLE_SOURCE",
            opportunity_types=(),
            reason=(
                f"{primary.display_name} has no usable direction in both sources; "
                "held out of confirmation screening."
            ),
        ),
        "SINGLE_SOURCE",
    )


def _replace_snapshot(
    snapshot: IndustryRadarSnapshot,
    *,
    state: IndustryState | None = None,
    signals: tuple[IndustrySignal, ...] | None = None,
    evidence_completeness: str | None = None,
    opportunity_types: tuple[str, ...] | None = None,
    reason: str | None = None,
) -> IndustryRadarSnapshot:
    return IndustryRadarSnapshot(
        industry_id=snapshot.industry_id,
        display_name=snapshot.display_name,
        as_of=snapshot.as_of,
        state=state or snapshot.state,
        signals=signals if signals is not None else snapshot.signals,
        evidence_completeness=evidence_completeness or snapshot.evidence_completeness,
        opportunity_types=(
            opportunity_types if opportunity_types is not None else snapshot.opportunity_types
        ),
        reason=reason if reason is not None else snapshot.reason,
    )


def secondary_provider_prefix(snapshot: IndustryRadarSnapshot) -> str:
    """Keep merged signal names stable without assuming a vendor-specific model."""

    if any("10jqka" in signal.source for signal in snapshot.signals):
        return "tonghuashun"
    return "secondary"


def _provider_metadata(
    provider: IndustryRadarProvider, as_of: str, label: str
) -> dict[str, Any]:
    metadata = getattr(provider, "metadata", None)
    if callable(metadata):
        value = metadata(as_of)
        if isinstance(value, dict):
            return value
    return {"provider": label, "as_of": as_of, "read_only": True}
