"""Discover and safely reuse local research assets.

The adapter indexes existing ``luopan`` and ``ai-berkshire`` files without
turning their claims into verified facts.  It keeps an auditable manifest for
each file and exposes narrow import methods for profiles, candidate sets,
scorecards, and reference-only research artifacts.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .models import CompanyCandidate, CompanyDataTier, IndustryRadarSnapshot


class ResearchAssetError(ValueError):
    """Raised when a research asset cannot be indexed or reused safely."""


class ResearchAssetCompanyPool:
    """Expose explicit upstream candidate sets through the bounded pool protocol.

    The caller declares which candidate-set imports belong to the selected
    industry. Unstructured reports are never parsed here, and unsupported
    markets are retained in metadata rather than entering the A/HK pool.
    """

    def __init__(
        self,
        candidate_sets: Sequence[Mapping[str, Any]] = (),
        *,
        fallback: Any | None = None,
    ) -> None:
        self.candidate_sets = tuple(candidate_sets)
        self.fallback = fallback
        self._last_metadata: dict[str, Any] = {}
        for candidate_set in self.candidate_sets:
            if not isinstance(candidate_set, Mapping):
                raise ResearchAssetError("candidate_sets must contain objects")
            if candidate_set.get("schema_version") != RESEARCH_CANDIDATE_SET_SCHEMA_VERSION:
                raise ResearchAssetError(
                    "candidate_sets must be research-asset-candidate-set.v1 imports"
                )

    def candidates(
        self, industry: IndustryRadarSnapshot, limit: int
    ) -> Sequence[CompanyCandidate]:
        if limit < 1:
            raise ResearchAssetError("candidate pool limit must be positive")
        selected: list[CompanyCandidate] = []
        rejected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for candidate_set in self.candidate_sets:
            for raw in candidate_set.get("candidates") or []:
                if not isinstance(raw, Mapping):
                    continue
                company_id = str(raw.get("candidate_id") or raw.get("company_id") or "").strip()
                display_name = str(raw.get("display_name") or raw.get("name") or company_id).strip()
                if not company_id:
                    continue
                if not _supported_initial_market(company_id):
                    rejected.append(
                        {
                            "company_id": company_id,
                            "display_name": display_name,
                            "reason": "INITIAL_MARKET_OUT_OF_SCOPE",
                            "source_project": str(candidate_set.get("source_project") or ""),
                        }
                    )
                    continue
                if company_id in seen:
                    continue
                seen.add(company_id)
                selected.append(
                    CompanyCandidate(
                        company_id=company_id,
                        display_name=display_name,
                        industry_id=str(industry.industry_id),
                        data_tier=CompanyDataTier.LIGHT,
                        source=(
                            "research_asset:"
                            + str(candidate_set.get("source_project") or "unknown")
                            + ":"
                            + str(candidate_set.get("source_path") or "")
                        ),
                        inclusion_reason="RESEARCH_ASSET_REUSE_BOUNDED_CANDIDATE_SET",
                        metadata={
                            "research_asset_import_id": str(candidate_set.get("import_id") or ""),
                            "research_asset_evidence_ids": list(candidate_set.get("evidence_ids") or []),
                            "research_asset_reuse_strategy": str(candidate_set.get("reuse_strategy") or ""),
                            "research_asset_scope": dict(candidate_set.get("scope") or {}),
                            "candidate_category": str(raw.get("category") or ""),
                            "candidate_metadata": dict(raw.get("metadata") or {}),
                        },
                    )
                )
                if len(selected) >= limit:
                    break
            if len(selected) >= limit:
                break
        if selected:
            provider = "research_assets"
        elif self.fallback is not None:
            selected = list(self.fallback.candidates(industry, limit))[:limit]
            provider = "fallback"
        else:
            provider = "research_assets_empty"
        self._last_metadata = {
            "provider": provider,
            "candidate_set_count": len(self.candidate_sets),
            "selected_count": len(selected),
            "rejected_count": len(rejected),
            "rejected": rejected[:limit],
            "bounded": True,
            "full_market_membership_loaded": False,
            "read_only": True,
        }
        return selected

    def metadata(self) -> dict[str, Any]:
        return dict(self._last_metadata)


RESEARCH_ASSET_CATALOG_SCHEMA_VERSION = "research-asset-catalog.v1"
RESEARCH_ASSET_IMPORT_SCHEMA_VERSION = "research-asset-import.v1"
RESEARCH_PROFILE_SCHEMA_VERSION = "research-asset-company-profile.v1"
RESEARCH_CANDIDATE_SET_SCHEMA_VERSION = "research-asset-candidate-set.v1"
RESEARCH_SCORECARD_SCHEMA_VERSION = "research-asset-scorecard.v1"
RULE_VERSION = "research-asset-adapter-rules.v1"
MAPPING_VERSION = "research-asset-field-mapping.v1"

DIRECT_REUSE = "DIRECT_REUSE"
REUSE_WITH_CHECK = "REUSE_WITH_CHECK"
METHOD_REUSE = "METHOD_REUSE"
REFERENCE_ONLY = "REFERENCE_ONLY"

_REUSE_STRATEGIES = {DIRECT_REUSE, REUSE_WITH_CHECK, METHOD_REUSE, REFERENCE_ONLY}
_VALIDATION_STATES = {
    "PENDING",
    "VERIFIED",
    "PARTIAL",
    "UNVERIFIED",
    "CONFLICTING",
    "TEMPORALLY_INVALID",
    "NOT_AVAILABLE",
}
_DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-_./]?(\d{2})[-_./]?(\d{2})(?!\d)")
_TICKER_RE = re.compile(r"(?<![A-Za-z0-9])(?:[0369]\d{5}(?:\.(?:SH|SZ|BJ))?|\d{4,5}\.HK|[A-Z]{1,6})(?![A-Za-z0-9])")
_COMPANY_ID_FIELDS = ("company_id", "ticker", "stock_code", "code", "symbol")
_NAME_FIELDS = ("name", "display_name", "company_name", "legal_name")
_MARKET_FIELDS = ("market", "exchange", "exchange_name")
_BUSINESS_FIELDS = ("primary_business", "main_business", "business", "business_description")
_PRODUCT_FIELDS = ("products", "product_list", "product_lines", "business_segments")


class ResearchAssetAdapter:
    """Local adapter for the checked-in upstream research work trees.

    ``root`` can be the repository's ``vendor`` directory or one of the two
    project directories.  The adapter intentionally does not make network
    calls and does not write into either upstream work tree.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        projects: Sequence[str] = ("luopan", "ai-berkshire"),
        rule_version: str = RULE_VERSION,
    ) -> None:
        self.root = Path(root)
        if not self.root.exists():
            raise ResearchAssetError(f"research asset root does not exist: {self.root}")
        self.rule_version = str(rule_version).strip()
        if not self.rule_version:
            raise ResearchAssetError("rule_version must not be empty")
        requested = tuple(str(item).strip() for item in projects if str(item).strip())
        if self.root.name in requested:
            self._project_roots = {self.root.name: self.root}
            self._manifest_root = self.root.parent
        elif (self.root / "vendor").is_dir():
            # Accept the repository root as a convenience for the CLI and
            # callers that do not want to spell out ``vendor``.
            vendor_root = self.root / "vendor"
            self._project_roots = {
                name: vendor_root / name
                for name in requested
                if (vendor_root / name).is_dir()
            }
            self._manifest_root = self.root
        else:
            self._project_roots = {
                name: self.root / name
                for name in requested
                if (self.root / name).is_dir()
            }
            self._manifest_root = self.root

    def discover(
        self,
        identifier: str = "",
        as_of: str | None = None,
        *,
        limit: int = 500,
    ) -> dict[str, Any]:
        """Find eligible assets by company, ticker, industry, or file path.

        Assets dated after ``as_of`` are kept in ``excluded_items`` for audit
        visibility but never enter the eligible result set.
        """

        if limit < 1:
            raise ResearchAssetError("limit must be positive")
        cutoff = _parse_date(as_of, "as_of") if as_of else None
        query = str(identifier or "").strip()
        records: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        for project, project_root in self._project_roots.items():
            for path in _iter_asset_files(project_root):
                record = self._inspect_path(path, project)
                match_score, match_reasons = _match_score(record, query)
                if query and match_score <= 0:
                    continue
                record.pop("_match_text", None)
                record["match_score"] = match_score
                record["match_reasons"] = match_reasons
                if cutoff and record["research_date"]:
                    research_date = _parse_date(record["research_date"], "research_date")
                    if research_date > cutoff:
                        record["temporal_status"] = "AFTER_CUTOFF"
                        record["exclusion_reason"] = "RESEARCH_DATE_AFTER_CUTOFF"
                        excluded.append(record)
                        continue
                    record["temporal_status"] = "BEFORE_OR_AT_CUTOFF"
                else:
                    record["temporal_status"] = "NO_DATE" if not record["research_date"] else "NO_CUTOFF"
                records.append(record)

        # A dated report is generally more useful than an old report when
        # match scores tie.
        records.sort(
            key=lambda item: (
                int(item.get("match_score") or 0),
                str(item.get("research_date") or "0000-00-00"),
                str(item.get("source_path") or ""),
            ),
            reverse=True,
        )
        excluded.sort(key=lambda item: str(item.get("source_path") or ""))
        if limit:
            records = records[:limit]
            excluded = excluded[:limit]
        counts = Counter(str(item.get("asset_type") or "UNKNOWN") for item in records)
        return {
            "schema_version": RESEARCH_ASSET_CATALOG_SCHEMA_VERSION,
            "catalog_id": f"research-assets-{_slug(query or 'all')}-{as_of or 'latest'}",
            "identifier": query,
            "as_of": as_of or "",
            "rule_version": self.rule_version,
            "mapping_version": MAPPING_VERSION,
            "source_projects": list(self._project_roots),
            "items": records,
            "excluded_items": excluded,
            "asset_count": len(records),
            "excluded_count": len(excluded),
            "asset_type_counts": dict(counts),
            "complete_project_membership": False,
            "read_only": True,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
            "policy": _policy(),
        }

    def map_company_profile(self, asset: Mapping[str, Any] | str | Path) -> dict[str, Any]:
        """Map only explicit identity/business candidates from one asset."""

        record, payload, text = self._resolve_asset(asset)
        company = payload.get("company") if isinstance(payload, Mapping) else None
        company = company if isinstance(company, Mapping) else {}
        fields: dict[str, dict[str, Any]] = {}

        def add_field(name: str, value: Any, strategy: str) -> None:
            normal = _normalise_value(value)
            if normal in (None, "", [], {}):
                return
            fields[name] = {
                "value": normal,
                "status": "CANDIDATE",
                "reuse_strategy": strategy,
                "source_path": record["source_path"],
                "evidence_ids": [record["asset_id"]],
            }

        name = _first_value(company, payload, _NAME_FIELDS)
        name_strategy = DIRECT_REUSE
        if not name and text:
            # A filename can suggest a subject, but it is not an identity fact.
            name = _name_from_filename(record["source_path"])
            name_strategy = REUSE_WITH_CHECK
        ticker = _first_value(company, payload, _COMPANY_ID_FIELDS)
        market = _first_value(company, payload, _MARKET_FIELDS)
        listing_status = _first_value(company, payload, ("status", "listing_status"))
        legal_name = _first_value(company, payload, ("legal_name",))
        industry = _first_value(company, payload, ("industry", "industry_name", "sector"))
        primary_business = _first_value(company, payload, _BUSINESS_FIELDS)
        products = _first_value(company, payload, _PRODUCT_FIELDS)

        add_field("company_name", name, name_strategy)
        add_field("legal_name", legal_name, DIRECT_REUSE)
        add_field("company_id", ticker, DIRECT_REUSE)
        add_field("market", market, DIRECT_REUSE)
        add_field("listing_status", listing_status, DIRECT_REUSE)
        add_field("industry", industry, REUSE_WITH_CHECK)
        add_field("primary_business", primary_business, REUSE_WITH_CHECK)
        add_field("products", products, REUSE_WITH_CHECK)

        identity_candidates = {
            field: fields[field]["value"]
            for field in ("company_id", "company_name", "legal_name", "market", "listing_status")
            if field in fields
        }
        identity_status = "PENDING" if identity_candidates else "UNVERIFIED"
        profile_status = "PARTIAL" if identity_candidates else "INSUFFICIENT"
        return {
            "schema_version": RESEARCH_PROFILE_SCHEMA_VERSION,
            "profile_id": f"research-profile-{record['asset_id']}",
            "source_project": record["source_project"],
            "source_path": record["source_path"],
            "raw_file_path": record["raw_file_path"],
            "file_hash": record["file_hash"],
            "file_modified_at": record["file_modified_at"],
            "research_date": record["research_date"],
            "asset_type": record["asset_type"],
            "asset_snapshot": record["asset_snapshot"],
            "source_version": record["source_version"],
            "mapping_version": MAPPING_VERSION,
            "validation_status": identity_status,
            "profile_status": profile_status,
            "claims_are_verified": False,
            "company_id": identity_candidates.get("company_id", ""),
            "display_name": identity_candidates.get("company_name", ""),
            "fields": fields,
            "identity_candidates": identity_candidates,
            "reuse_strategy": _profile_strategy(fields),
            "excluded_claims": {
                "valuation": REFERENCE_ONLY,
                "target_price": REFERENCE_ONLY,
                "buy_sell_view": REFERENCE_ONLY,
                "external_conclusion": REFERENCE_ONLY,
            },
            "evidence_ids": [record["asset_id"]],
            "source_manifest": record,
            "read_only": True,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
            "policy": _policy(),
        }

    def import_artifact(self, asset: Mapping[str, Any] | str | Path) -> dict[str, Any]:
        """Import an immutable manifest; report content remains reference-only."""

        record, payload, text = self._resolve_asset(asset)
        return {
            "schema_version": RESEARCH_ASSET_IMPORT_SCHEMA_VERSION,
            "import_id": f"research-artifact-{record['asset_id']}",
            "import_kind": "ARTIFACT",
            "source_project": record["source_project"],
            "source_path": record["source_path"],
            "raw_file_path": record["raw_file_path"],
            "file_hash": record["file_hash"],
            "file_modified_at": record["file_modified_at"],
            "research_date": record["research_date"],
            "asset_type": record["asset_type"],
            "asset_snapshot": record["asset_snapshot"],
            "source_version": record["source_version"],
            "mapping_version": MAPPING_VERSION,
            "validation_status": "UNVERIFIED",
            "reuse_strategy": (
                METHOD_REUSE
                if record["asset_type"] == "METHOD_GUIDE"
                else REFERENCE_ONLY
            ),
            "parse_status": record["parse_status"],
            "field_candidates": record["field_candidates"],
            "content_summary": _content_summary(payload, text),
            "evidence_ids": [record["asset_id"]],
            "claims_are_verified": False,
            "content_copied": False,
            "read_only": True,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
            "policy": _policy(),
        }

    def import_candidate_set(self, asset: Mapping[str, Any] | str | Path) -> dict[str, Any]:
        """Import only explicit candidate lists and preserve their bounded scope."""

        record, payload, text = self._resolve_asset(asset)
        candidates = _candidate_items(record, payload, text)
        available = bool(candidates)
        representative = record["source_project"] == "luopan"
        return {
            "schema_version": RESEARCH_CANDIDATE_SET_SCHEMA_VERSION,
            "import_id": f"research-candidates-{record['asset_id']}",
            "import_kind": "CANDIDATE_SET",
            "source_project": record["source_project"],
            "source_path": record["source_path"],
            "raw_file_path": record["raw_file_path"],
            "file_hash": record["file_hash"],
            "file_modified_at": record["file_modified_at"],
            "research_date": record["research_date"],
            "asset_type": record["asset_type"],
            "asset_snapshot": record["asset_snapshot"],
            "source_version": record["source_version"],
            "mapping_version": MAPPING_VERSION,
            "validation_status": "PENDING" if available else "NOT_AVAILABLE",
            "reuse_strategy": REUSE_WITH_CHECK if available else REFERENCE_ONLY,
            "status": "READY" if available else "NOT_AVAILABLE",
            "candidates": candidates,
            "candidate_count": len(candidates),
            "scope": {
                "bounded": True,
                "complete": False,
                "representative": representative,
                "semantic_boundary": (
                    "luopan representative candidate set"
                    if representative
                    else "upstream bounded watchlist or candidate set"
                ),
                "may_enter_security_master": False,
            },
            "evidence_ids": [record["asset_id"]],
            "read_only": True,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
            "policy": _policy(),
        }

    def import_scorecard(self, asset: Mapping[str, Any] | str | Path) -> dict[str, Any]:
        """Import explicit scorecards only; do not infer scores from prose."""

        record, payload, text = self._resolve_asset(asset)
        items, scoring_year, missing = _scorecard_items(record, payload)
        available = bool(items)
        return {
            "schema_version": RESEARCH_SCORECARD_SCHEMA_VERSION,
            "import_id": f"research-scorecard-{record['asset_id']}",
            "import_kind": "SCORECARD",
            "source_project": record["source_project"],
            "source_path": record["source_path"],
            "raw_file_path": record["raw_file_path"],
            "file_hash": record["file_hash"],
            "file_modified_at": record["file_modified_at"],
            "research_date": record["research_date"],
            "asset_type": record["asset_type"],
            "asset_snapshot": record["asset_snapshot"],
            "source_version": record["source_version"],
            "mapping_version": MAPPING_VERSION,
            "validation_status": "PENDING" if available else "NOT_AVAILABLE",
            "reuse_strategy": REUSE_WITH_CHECK if available else REFERENCE_ONLY,
            "status": "READY" if available else "NOT_AVAILABLE",
            "scorecard_type": "GENERAL_SCREEN" if available else "NONE",
            "scoring_year": scoring_year,
            "missing_items": missing,
            "industry_calibrated": False,
            "final_rating": False,
            "items": items,
            "evidence_ids": [record["asset_id"]],
            "read_only": True,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
            "policy": _policy(),
        }

    def validate_identity(
        self,
        mapped_profile: Mapping[str, Any],
        authoritative_sources: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    ) -> dict[str, Any]:
        """Lightly compare candidate identity fields with authoritative data."""

        if not isinstance(mapped_profile, Mapping):
            raise ResearchAssetError("mapped_profile must be an object")
        sources = _source_list(authoritative_sources)
        mapped_as_of = _parse_date(
            str(mapped_profile.get("research_date") or ""), "research_date", required=False
        )
        usable_sources = []
        temporal_exclusions = []
        for source in sources:
            source_date = _source_date(source)
            if mapped_as_of and source_date and source_date > mapped_as_of:
                temporal_exclusions.append(source)
                continue
            usable_sources.append(source)
        fields = mapped_profile.get("fields") or {}
        candidates = mapped_profile.get("identity_candidates") or {}
        if not candidates and isinstance(fields, Mapping):
            candidates = {
                str(key): value.get("value")
                for key, value in fields.items()
                if key in {"company_id", "company_name", "legal_name", "market", "listing_status"}
                and isinstance(value, Mapping)
            }
        candidates = {str(key): value for key, value in candidates.items() if _normalise_value(value) not in (None, "", [], {})}
        field_validation: dict[str, dict[str, Any]] = {}
        matching_source_ids: list[str] = []
        any_identity_match = False
        any_conflict = False
        for field, value in candidates.items():
            aliases = _authoritative_aliases(field)
            matches = []
            conflicts = []
            for index, source in enumerate(usable_sources):
                source_value = _first_value(source, source, aliases)
                if source_value in (None, "", [], {}):
                    continue
                if _same_identity_value(field, value, source_value):
                    matches.append(index)
                else:
                    conflicts.append(index)
            if matches and conflicts:
                status = "CONFLICTING"
                any_conflict = True
            elif matches:
                status = "VERIFIED"
                any_identity_match = any_identity_match or field in {"company_id", "company_name", "legal_name"}
                matching_source_ids.extend(_source_id(usable_sources[index], index) for index in matches)
            elif conflicts:
                status = "CONFLICTING"
                any_conflict = True
            else:
                status = "UNVERIFIED"
            field_validation[field] = {
                "value": value,
                "status": status,
                "authoritative_source_ids": [
                    _source_id(usable_sources[index], index) for index in matches
                ],
            }
        if not usable_sources:
            validation_status = "TEMPORALLY_INVALID" if temporal_exclusions else "UNVERIFIED"
            match_method = "NO_USABLE_AUTHORITATIVE_SOURCE"
        elif any_conflict:
            validation_status = "CONFLICTING"
            match_method = "FIELD_CONFLICT"
        elif any_identity_match:
            validation_status = "VERIFIED" if all(
                item["status"] in {"VERIFIED", "UNVERIFIED"}
                for item in field_validation.values()
            ) else "PARTIAL"
            match_method = "IDENTITY_FIELD_MATCH"
        else:
            validation_status = "UNVERIFIED"
            match_method = "NO_IDENTITY_FIELD_MATCH"
        result = dict(mapped_profile)
        result["validation_status"] = validation_status
        result["identity_match_method"] = match_method
        result["field_validation"] = field_validation
        result["authoritative_source_ids"] = sorted(set(matching_source_ids))
        result["temporal_excluded_source_ids"] = [
            _source_id(source, index) for index, source in enumerate(temporal_exclusions)
        ]
        result["claims_are_verified"] = validation_status == "VERIFIED"
        result["read_only"] = True
        result["review_only"] = True
        result["investment_conclusion"] = False
        result["execution_enabled"] = False
        result["policy"] = _policy()
        return result

    def _resolve_asset(
        self, asset: Mapping[str, Any] | str | Path
    ) -> tuple[dict[str, Any], Mapping[str, Any], str]:
        if isinstance(asset, Mapping) and asset.get("source_manifest"):
            source_manifest = asset["source_manifest"]
            if not isinstance(source_manifest, Mapping):
                raise ResearchAssetError("source_manifest must be an object")
            asset = source_manifest
        if isinstance(asset, Mapping):
            source_path = str(asset.get("source_path") or asset.get("path") or "").strip()
            if not source_path:
                raise ResearchAssetError("asset source_path is required")
            project = str(asset.get("source_project") or _project_from_path(source_path)).strip()
            path = self._path_for(project, source_path)
        else:
            path = Path(asset)
            if not path.is_absolute():
                if self.root.name in self._project_roots:
                    path = self.root / path
                elif self._manifest_root.name == "vendor" and str(path).startswith("vendor/"):
                    path = self._manifest_root / Path(str(path)[len("vendor/"):])
                else:
                    path = self._manifest_root / path
            try:
                relative_path = str(path.relative_to(self._manifest_root))
            except ValueError:
                relative_path = path.name
            project = (
                self.root.name
                if self.root.name in self._project_roots
                else _project_from_path(relative_path)
            )
        if not path.is_file():
            raise ResearchAssetError(f"research asset file does not exist: {path}")
        record = self._inspect_path(path, project)
        payload, text = _read_content(path)
        return record, payload, text

    def _path_for(self, project: str, source_path: str) -> Path:
        path = Path(source_path)
        if path.is_absolute():
            return path
        if source_path.startswith("vendor/"):
            if self._manifest_root.name == "vendor":
                return self._manifest_root / Path(source_path[len("vendor/"):])
            return self._manifest_root / source_path
        project_root = self._project_roots.get(project)
        if project_root is None:
            project_root = self._manifest_root / project
        if source_path.startswith(f"{project}/"):
            return self._manifest_root / source_path
        if source_path.startswith(str(project_root)):
            return Path(source_path)
        return project_root / source_path

    def _inspect_path(self, path: Path, project: str) -> dict[str, Any]:
        raw = path.read_bytes()
        digest = sha256(raw).hexdigest()
        payload, text = _read_content(path, raw=raw)
        try:
            relative = path.relative_to(self._manifest_root).as_posix()
        except ValueError:
            relative = path.name
        research_date = _research_date(path, payload)
        asset_type = _asset_type(project, relative, payload, text)
        return {
            "asset_id": f"{project}:{relative}:{digest[:16]}",
            "source_project": project,
            "source_path": relative,
            "raw_file_path": relative,
            "file_hash": digest,
            "sha256": digest,
            "file_size_bytes": len(raw),
            "file_modified_at": _mtime(path),
            "research_date": research_date,
            "asset_type": asset_type,
            "asset_snapshot": research_date or "NO_DATE",
            "source_version": self._source_version(project),
            "mapping_version": MAPPING_VERSION,
            "validation_status": "PENDING",
            "reuse_strategy": _default_reuse_strategy(asset_type),
            "parse_status": "PARSED" if payload is not None or text else "EMPTY",
            "field_candidates": _field_candidates(payload, text),
            # Kept only during discovery; never write the full report text into
            # the catalog manifest.
            "_match_text": _search_text(payload, text),
        }

    def _source_version(self, project: str) -> str:
        source_file = self._manifest_root / "vendor" / "SOURCES.md"
        if not source_file.is_file():
            source_file = self._manifest_root / "SOURCES.md"
        if not source_file.is_file():
            return "unknown"
        pattern = re.compile(rf"`{re.escape(project)}`\s*\|[^|]+\|[^|]+\|\s*`([^`]+)`")
        match = pattern.search(source_file.read_text(encoding="utf-8"))
        return match.group(1) if match else "unknown"


def discover_research_assets(
    root: str | Path, identifier: str = "", as_of: str | None = None, *, limit: int = 500
) -> dict[str, Any]:
    return ResearchAssetAdapter(root).discover(identifier, as_of, limit=limit)


def _iter_asset_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        if path.suffix.lower() not in {".json", ".md", ".html", ".txt"}:
            continue
        yield path


def _read_content(path: Path, *, raw: bytes | None = None) -> tuple[Mapping[str, Any] | None, str]:
    raw = path.read_bytes() if raw is None else raw
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, ""
    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None, text
        return (payload if isinstance(payload, Mapping) else None), text
    return None, text


def _asset_type(project: str, relative: str, payload: Mapping[str, Any] | None, text: str) -> str:
    lowered = relative.lower()
    if lowered.endswith("watchlist.json") or "/watchlist" in lowered:
        return "CANDIDATE_SET"
    if lowered.endswith("fundamentals.json") or "/fundamentals" in lowered:
        return "FUNDAMENTALS_DATASET"
    if "/review-output/" in lowered:
        return "COMPANY_REPORT"
    if "/skills/" in lowered or "/codex-prompts/" in lowered or lowered.endswith("skill.md"):
        return "METHOD_GUIDE"
    if "/test-output/" in lowered:
        return "INDUSTRY_REPORT"
    if "/reports/" in lowered:
        name = Path(relative).stem.lower()
        return "INDUSTRY_REPORT" if any(token in name for token in ("industry", "行业", "funnel", "bottleneck", "产业")) else "RESEARCH_REPORT"
    if payload and isinstance(payload.get("company"), Mapping):
        return "COMPANY_REPORT"
    if text and any(token in text[:1500].lower() for token in ("行业研究", "industry research", "产业链")):
        return "INDUSTRY_REPORT"
    return "RESEARCH_MATERIAL"


def _research_date(path: Path, payload: Mapping[str, Any] | None) -> str:
    if payload:
        for key in ("research_date", "as_of", "date", "generated_at", "captured_at"):
            value = str(payload.get(key) or "").strip()
            if value:
                parsed = _parse_date(value, key, required=False)
                if parsed:
                    return parsed.isoformat()
    match = _DATE_RE.search(path.name)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
        except ValueError:
            pass
    return ""


def _field_candidates(payload: Mapping[str, Any] | None, text: str) -> list[dict[str, str]]:
    if payload is not None:
        return [
            {"name": str(key), "status": "CANDIDATE", "value_type": type(value).__name__}
            for key, value in payload.items()
        ][:100]
    headings = re.findall(r"^#{1,4}\s+(.+?)\s*$", text, re.MULTILINE)
    return [
        {"name": heading.strip(), "status": "SECTION_PRESENT", "value_type": "text"}
        for heading in headings[:50]
    ]


def _match_score(record: Mapping[str, Any], query: str) -> tuple[int, list[str]]:
    if not query:
        return 1, ["NO_IDENTIFIER_FILTER"]
    needle = _norm_text(query)
    path = _norm_text(str(record.get("source_path") or ""))
    content = _norm_text(str(record.get("_match_text") or ""))
    reasons: list[str] = []
    score = 0
    if needle and needle in path:
        score += 5
        reasons.append("PATH_MATCH")
    if needle and needle in content:
        score += 3
        reasons.append("CONTENT_MATCH")
    source_project = _norm_text(str(record.get("source_project") or ""))
    if needle == source_project:
        score += 1
        reasons.append("PROJECT_MATCH")
    return score, reasons


def _search_text(payload: Mapping[str, Any] | None, text: str) -> str:
    if payload is not None:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return text[:200_000]


def _candidate_items(record: Mapping[str, Any], payload: Mapping[str, Any] | None, text: str) -> list[dict[str, Any]]:
    if not payload:
        return []
    candidates: list[dict[str, Any]] = []
    if record["asset_type"] == "CANDIDATE_SET" and "watchlist" in record["source_path"].lower():
        for category, values in payload.items():
            if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
                continue
            for value in values:
                if isinstance(value, Mapping):
                    candidate_id = _first_value(value, value, _COMPANY_ID_FIELDS)
                    display_name = _first_value(value, value, _NAME_FIELDS) or candidate_id
                    extra = dict(value)
                else:
                    candidate_id = str(value).strip()
                    display_name = candidate_id
                    extra = {}
                if not candidate_id:
                    continue
                candidates.append({
                    "candidate_id": str(candidate_id),
                    "display_name": str(display_name or candidate_id),
                    "category": str(category),
                    "identity_status": "CANDIDATE",
                    "reuse_strategy": REUSE_WITH_CHECK,
                    "metadata": extra,
                    "evidence_ids": [record["asset_id"]],
                })
        return candidates
    raw = None
    for key in ("candidates", "companies", "items", "watchlist"):
        if isinstance(payload.get(key), list):
            raw = payload[key]
            break
    if raw is None:
        return []
    for value in raw:
        if not isinstance(value, Mapping):
            continue
        candidate_id = _first_value(value, value, _COMPANY_ID_FIELDS)
        name = _first_value(value, value, _NAME_FIELDS) or candidate_id
        if not candidate_id:
            continue
        candidates.append({
            "candidate_id": str(candidate_id),
            "display_name": str(name or candidate_id),
            "category": str(value.get("category") or ""),
            "identity_status": "CANDIDATE",
            "reuse_strategy": REUSE_WITH_CHECK,
            "metadata": {key: val for key, val in value.items() if key not in _COMPANY_ID_FIELDS + _NAME_FIELDS},
            "evidence_ids": [record["asset_id"]],
        })
    return candidates


def _scorecard_items(record: Mapping[str, Any], payload: Mapping[str, Any] | None) -> tuple[list[dict[str, Any]], str, list[str]]:
    if not payload:
        return [], "", ["NO_STRUCTURED_SCORECARD"]
    raw = payload.get("scorecard") or payload.get("scorecards")
    if isinstance(raw, Mapping):
        raw = raw.get("items") or raw.get("companies") or raw.get("metrics")
    if not isinstance(raw, list):
        return [], str(payload.get("scoring_year") or payload.get("year") or ""), ["NO_STRUCTURED_SCORECARD"]
    items: list[dict[str, Any]] = []
    for value in raw:
        if not isinstance(value, Mapping):
            continue
        score = value.get("score")
        if score is None and not any(key in value for key in ("metrics", "dimensions", "indicators")):
            continue
        item = dict(value)
        item["status"] = "CANDIDATE"
        item["reuse_strategy"] = REUSE_WITH_CHECK
        item["evidence_ids"] = [record["asset_id"]]
        item["final_rating"] = False
        items.append(item)
    missing = [] if items else ["NO_EXPLICIT_SCORE_OR_METRICS"]
    return items, str(payload.get("scoring_year") or payload.get("year") or ""), missing


def _content_summary(payload: Mapping[str, Any] | None, text: str) -> dict[str, Any]:
    if payload is not None:
        return {"top_level_fields": list(payload)[:100], "structured": True}
    headings = re.findall(r"^#{1,4}\s+(.+?)\s*$", text, re.MULTILINE)
    return {"headings": [item.strip() for item in headings[:50]], "structured": False}


def _profile_strategy(fields: Mapping[str, Mapping[str, Any]]) -> str:
    strategies = {str(item.get("reuse_strategy")) for item in fields.values()}
    if REUSE_WITH_CHECK in strategies:
        return REUSE_WITH_CHECK
    if DIRECT_REUSE in strategies:
        return DIRECT_REUSE
    return REFERENCE_ONLY


def _default_reuse_strategy(asset_type: str) -> str:
    if asset_type in {"COMPANY_REPORT", "CANDIDATE_SET", "FUNDAMENTALS_DATASET"}:
        return REUSE_WITH_CHECK
    if asset_type == "METHOD_GUIDE":
        return METHOD_REUSE
    return REFERENCE_ONLY


def _first_value(primary: Mapping[str, Any], secondary: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for source in (primary, secondary):
        if not isinstance(source, Mapping):
            continue
        for key in keys:
            value = source.get(key)
            if value not in (None, "", [], {}):
                return value
    return None


def _normalise_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _normalise_value(val) for key, val in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalise_value(item) for item in value]
    return value


def _source_list(value: Sequence[Mapping[str, Any]] | Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        if isinstance(value.get("sources"), list):
            value = value["sources"]
        else:
            value = [value]
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ResearchAssetError("authoritative_sources must be an object or list")
    return [item for item in value if isinstance(item, Mapping)]


def _authoritative_aliases(field: str) -> tuple[str, ...]:
    return {
        "company_id": _COMPANY_ID_FIELDS,
        "company_name": _NAME_FIELDS,
        # A short display name is not evidence for the legal entity name.
        # Treating it as such creates false conflicts for sparse official data.
        "legal_name": ("legal_name",),
        "market": _MARKET_FIELDS,
        "listing_status": ("listing_status", "status"),
    }.get(field, (field,))


def _same_identity_value(field: str, left: Any, right: Any) -> bool:
    if field in {"company_id", "market"}:
        return _norm_identity(str(left)) == _norm_identity(str(right))
    return _norm_text(str(left)) == _norm_text(str(right))


def _source_id(source: Mapping[str, Any], index: int) -> str:
    return str(source.get("source_id") or source.get("id") or source.get("name") or f"authoritative-{index}")


def _source_date(source: Mapping[str, Any]) -> date | None:
    for key in ("as_of", "published_at", "source_date", "date"):
        parsed = _parse_date(str(source.get(key) or ""), key, required=False)
        if parsed:
            return parsed
    return None


def _parse_date(value: str | None, field: str, *, required: bool = True) -> date | None:
    text = str(value or "").strip()
    if not text:
        if required:
            raise ResearchAssetError(f"{field} is required")
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        match = _DATE_RE.search(text)
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                pass
    raise ResearchAssetError(f"invalid {field}: {value}")


def _mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _project_from_path(path: str) -> str:
    parts = Path(path).parts
    if "vendor" in parts:
        index = parts.index("vendor")
        if len(parts) > index + 1:
            return parts[index + 1]
    return parts[0] if parts else "unknown"


def _norm_text(value: str) -> str:
    return re.sub(r"[\s_./()（）\[\]【】：:，,\-]+", "", value).lower()


def _norm_identity(value: str) -> str:
    return _norm_text(value).replace("sh", "").replace("sz", "").replace("hk", "")


def _name_from_filename(path: str) -> str:
    stem = Path(path).stem
    stem = re.sub(r"[-_ ]?20\d{2}[-_]?\d{2}[-_]?\d{2}.*$", "", stem)
    stem = re.sub(r"[-_ ]?(公司调研|研究报告|research|investment|study).*$", "", stem, flags=re.I)
    return stem.strip("-_ ")


def _slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", value).strip("-")
    return slug or "all"


def _supported_initial_market(company_id: str) -> bool:
    value = str(company_id or "").strip().upper()
    return bool(
        re.fullmatch(r"\d{6}(?:\.(?:SH|SZ|BJ))?", value)
        or re.fullmatch(r"\d{4,5}\.HK", value)
    )


def _policy() -> dict[str, Any]:
    return {
        "identity_and_products_are_candidates": True,
        "industry_label_is_not_security_master": True,
        "luopan_candidate_set_is_representative_only": True,
        "external_claims_not_verified": True,
        "valuation_target_price_and_buy_sell_view_reference_only": True,
        "scorecard_not_cross_industry_final_rating": True,
        "future_information_not_backfilled": True,
        "source_file_not_copied_or_mutated": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }
