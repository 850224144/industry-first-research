"""Versioned, explicit industry aliases for cross-source evidence matching."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .cross_validation import normalize_industry_name


class IndustryAliasError(ValueError):
    """Raised when an alias registry is missing or internally ambiguous."""


@dataclass(frozen=True)
class IndustryAlias:
    canonical_id: str
    canonical_name: str
    aliases: dict[str, tuple[str, ...]]
    note: str


class IndustryAliasRegistry:
    """Resolve only explicit source aliases; unknown names remain exact-match only."""

    def __init__(self, schema_version: str, entries: tuple[IndustryAlias, ...], source_path: str = "") -> None:
        self.schema_version = schema_version
        self.entries = entries
        self.source_path = source_path
        self._lookup: dict[tuple[str, str], str] = {}
        for entry in entries:
            for source, values in entry.aliases.items():
                for value in (entry.canonical_name, *values):
                    key = (source, normalize_industry_name(value))
                    if key[1] in {"", normalize_industry_name(entry.canonical_id)}:
                        continue
                    previous = self._lookup.get(key)
                    if previous is not None and previous != entry.canonical_id:
                        raise IndustryAliasError(
                            f"alias {value!r} for {source!r} maps to multiple canonical industries"
                        )
                    self._lookup[key] = entry.canonical_id

    @classmethod
    def from_file(cls, path: str | Path) -> "IndustryAliasRegistry":
        target = Path(path)
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise IndustryAliasError(f"unable to read alias registry {target}: {error}") from error
        if not isinstance(payload, dict):
            raise IndustryAliasError("alias registry must be a JSON object")
        return cls.from_dict(payload, source_path=str(target))

    @classmethod
    def from_dict(
        cls, payload: dict[str, Any], *, source_path: str = ""
    ) -> "IndustryAliasRegistry":
        schema_version = payload.get("schema_version")
        raw_entries = payload.get("mappings")
        if schema_version != "industry-aliases.v1":
            raise IndustryAliasError("unsupported alias registry schema")
        if not isinstance(raw_entries, list):
            raise IndustryAliasError("alias registry mappings must be a list")

        entries: list[IndustryAlias] = []
        canonical_ids: set[str] = set()
        for raw in raw_entries:
            if not isinstance(raw, dict):
                raise IndustryAliasError("each alias mapping must be an object")
            canonical_id = _required_text(raw, "canonical_id")
            canonical_name = _required_text(raw, "canonical_name")
            note = str(raw.get("note") or "")
            if canonical_id in canonical_ids:
                raise IndustryAliasError(f"duplicate canonical_id: {canonical_id}")
            canonical_ids.add(canonical_id)
            raw_aliases = raw.get("aliases")
            if not isinstance(raw_aliases, dict) or not raw_aliases:
                raise IndustryAliasError(f"aliases are required for {canonical_id}")
            aliases: dict[str, tuple[str, ...]] = {}
            for source, values in raw_aliases.items():
                if not isinstance(source, str) or not source.strip():
                    raise IndustryAliasError("alias source names must be non-empty strings")
                if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
                    raise IndustryAliasError(f"aliases for {source!r} must be a string list")
                aliases[source] = tuple(value for value in values if value.strip())
            entries.append(IndustryAlias(canonical_id, canonical_name, aliases, note))
        return cls(schema_version, tuple(entries), source_path)

    def resolve(self, source: str, display_name: str, industry_id: str = "") -> str:
        """Return a canonical id for an explicit alias, otherwise exact normalized name."""

        for value in (industry_id, display_name):
            key = (source, normalize_industry_name(value))
            canonical_id = self._lookup.get(key)
            if canonical_id is not None:
                return canonical_id
        return normalize_industry_name(display_name)

    def match_method(self, source: str, display_name: str, industry_id: str = "") -> str:
        resolved = self.resolve(source, display_name, industry_id)
        exact = normalize_industry_name(display_name)
        return "ALIAS" if resolved != exact else "EXACT_NORMALIZED_NAME"

    def metadata(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mapping_count": len(self.entries),
            "source_path": self.source_path,
            "read_only": True,
        }


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise IndustryAliasError(f"{field} must be a non-empty string")
    return value.strip()
