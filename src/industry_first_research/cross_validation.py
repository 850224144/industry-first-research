"""Conservative cross-source industry evidence reconciliation."""

from __future__ import annotations

from collections.abc import Iterable
import re
import unicodedata
from typing import TYPE_CHECKING, Any

from .adapters import IndustryRadarProvider
from .models import IndustryRadarSnapshot, IndustrySignal, IndustryState

if TYPE_CHECKING:
    from .industry_aliases import IndustryAliasRegistry


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
        alias_registry: IndustryAliasRegistry | None = None,
    ) -> None:
        self.primary = primary
        self.secondary = secondary
        self.primary_name = primary_name
        self.secondary_name = secondary_name
        self.alias_registry = alias_registry
        self._metadata: dict[str, Any] = {}

    def snapshots(self, as_of: str) -> Iterable[IndustryRadarSnapshot]:
        primary_items = list(self.primary.snapshots(as_of))
        secondary_items = list(self.secondary.snapshots(as_of))
        secondary_by_name: dict[str, list[IndustryRadarSnapshot]] = {}
        for item in secondary_items:
            key = self._resolve_key(self.secondary_name, item)
            if key:
                secondary_by_name.setdefault(key, []).append(item)

        matched = 0
        cross_validated = 0
        conflicting = 0
        single_source = 0
        alias_matches = 0
        exact_matches = 0
        ambiguous_matches = 0
        result: list[IndustryRadarSnapshot] = []
        for primary_item in primary_items:
            primary_key = self._resolve_key(self.primary_name, primary_item)
            candidates = secondary_by_name.get(primary_key, [])
            secondary_item = candidates[0] if len(candidates) == 1 else None
            if len(candidates) > 1:
                match_method = "AMBIGUOUS"
                ambiguous_matches += 1
            elif secondary_item is None:
                match_method = "UNMATCHED"
            else:
                match_method = self._match_method(primary_item, secondary_item)
                if match_method == "ALIAS":
                    alias_matches += 1
                else:
                    exact_matches += 1
            merged, match_type = _merge_items(primary_item, secondary_item, match_method)
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
            "alias_match_row_count": alias_matches,
            "exact_match_row_count": exact_matches,
            "ambiguous_match_row_count": ambiguous_matches,
            "alias_registry": (
                self.alias_registry.metadata() if self.alias_registry is not None else None
            ),
        }
        return result

    def _resolve_key(self, source: str, item: IndustryRadarSnapshot) -> str:
        if self.alias_registry is not None:
            return self.alias_registry.resolve(source, item.display_name, item.industry_id)
        return normalize_industry_name(item.display_name)

    def _match_method(
        self, primary: IndustryRadarSnapshot, secondary: IndustryRadarSnapshot
    ) -> str:
        if self.alias_registry is None:
            return "EXACT_NORMALIZED_NAME"
        primary_method = self.alias_registry.match_method(
            self.primary_name, primary.display_name, primary.industry_id
        )
        secondary_method = self.alias_registry.match_method(
            self.secondary_name, secondary.display_name, secondary.industry_id
        )
        return "ALIAS" if "ALIAS" in (primary_method, secondary_method) else "EXACT_NORMALIZED_NAME"

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
    match_method: str,
) -> tuple[IndustryRadarSnapshot, str]:
    if secondary is None:
        return (
            _replace_snapshot(
                primary,
                state=IndustryState.INSUFFICIENT,
                evidence_completeness="SINGLE_SOURCE",
                opportunity_types=(),
                match_method=match_method,
                source_ids=_merge_source_ids(primary, secondary),
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
                match_method=match_method,
                source_ids=_merge_source_ids(primary, secondary),
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
                match_method=match_method,
                source_ids=_merge_source_ids(primary, secondary),
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
            match_method=match_method,
            source_ids=_merge_source_ids(primary, secondary),
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
    match_method: str | None = None,
    source_ids: dict[str, str] | None = None,
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
        match_method=match_method if match_method is not None else snapshot.match_method,
        source_ids=source_ids if source_ids is not None else dict(snapshot.source_ids),
    )


def _merge_source_ids(
    primary: IndustryRadarSnapshot,
    secondary: IndustryRadarSnapshot | None,
) -> dict[str, str]:
    source_ids = dict(primary.source_ids)
    if secondary is not None:
        source_ids.update(secondary.source_ids)
    return source_ids


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
