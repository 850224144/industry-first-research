"""Local research-asset providers for the first vertical slice.

The provider records where an asset came from, but it never upgrades a report or
an AI-generated claim into a verified fact by itself.
"""

from __future__ import annotations

from collections.abc import Sequence
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .models import CompanyCandidate, CompanyDataTier, IndustryRadarSnapshot


class LocalResearchAssetCatalog:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()

    def inspect(self, references: Sequence[str]) -> list[dict[str, Any]]:
        assets: list[dict[str, Any]] = []
        for reference in references:
            normalized = str(reference or "").strip()
            item = {
                "path": normalized,
                "asset_type": self._asset_type(normalized),
            }
            if not normalized:
                item.update(
                    {
                        "exists": False,
                        "available": False,
                        "parse_status": "UNDECLARED",
                        "fields": [],
                    }
                )
                assets.append(item)
                continue
            try:
                path = (self.project_root / normalized).resolve()
                path.relative_to(self.project_root)
            except (OSError, RuntimeError, ValueError):
                item.update(
                    {
                        "exists": False,
                        "available": False,
                        "parse_status": "OUTSIDE_PROJECT",
                        "fields": [],
                    }
                )
                assets.append(item)
                continue
            if not path.exists():
                item.update(
                    {
                        "exists": False,
                        "available": False,
                        "parse_status": "MISSING",
                        "fields": [],
                    }
                )
            elif not path.is_file():
                item.update(
                    {
                        "exists": False,
                        "available": False,
                        "parse_status": "NOT_FILE",
                        "fields": [],
                    }
                )
            else:
                item["exists"] = True
                item.update(self._parse_asset(path))
            assets.append(item)
        return assets

    @staticmethod
    def _parse_asset(path: Path) -> dict[str, Any]:
        """Extract auditable metadata and conservative field candidates.

        This is an asset index, not a fact extractor. Content-derived fields stay
        marked as candidates until an official source adapter verifies them.
        """

        try:
            raw = path.read_bytes()
        except OSError:
            return {
                "available": False,
                "parse_status": "UNREADABLE",
                "fields": [],
            }
        if not raw:
            return {
                "available": False,
                "parse_status": "EMPTY",
                "bytes": 0,
                "fields": [],
            }
        digest = hashlib.sha256(raw).hexdigest()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return {
                "available": True,
                "parse_status": "BINARY_UNSUPPORTED",
                "bytes": len(raw),
                "sha256": digest,
                "fields": [],
            }
        fields: list[dict[str, str]] = []
        if path.suffix.lower() == ".json":
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                return {
                    "available": True,
                    "parse_status": "INVALID_JSON",
                    "bytes": len(raw),
                    "sha256": digest,
                    "fields": [],
                }
            if isinstance(payload, dict):
                fields = [
                    {"name": key, "status": "CANDIDATE", "value_type": type(value).__name__}
                    for key, value in payload.items()
                ]
        else:
            headings = re.findall(r"^#{1,4}\s+(.+?)\s*$", text, re.MULTILINE)
            fields = [
                {"name": heading.strip(), "status": "SECTION_PRESENT", "value_type": "text"}
                for heading in headings[:30]
            ]
            for label in (
                "主营业务",
                "商业模式",
                "产品",
                "竞争",
                "替代",
                "现金流",
                "库存",
                "价格",
                "周期",
                "风险",
            ):
                if label in text and not any(item["name"] == label for item in fields):
                    fields.append(
                        {"name": label, "status": "KEYWORD_PRESENT", "value_type": "text"}
                    )
        return {
            "available": True,
            "parse_status": "PARSED",
            "bytes": len(raw),
            "sha256": digest,
            "fields": fields,
        }

    @staticmethod
    def _asset_type(reference: str) -> str:
        lowered = reference.lower()
        if "luopan" in lowered or "罗盘" in reference:
            return "luopan_research_artifact"
        if "ai-berkshire" in lowered or "berkshire" in lowered:
            return "ai_berkshire_research_artifact"
        return "local_research_material"


class ConfigCompanyPool:
    def __init__(
        self,
        candidates: Sequence[CompanyCandidate],
        catalog: LocalResearchAssetCatalog | None = None,
    ) -> None:
        self._candidates = tuple(candidates)
        self.catalog = catalog

    def candidates(
        self, industry: IndustryRadarSnapshot, limit: int
    ) -> Sequence[CompanyCandidate]:
        matches = [
            candidate
            for candidate in self._candidates
            if candidate.industry_id == industry.industry_id
        ]
        matches.sort(key=lambda item: item.score if item.score is not None else -1, reverse=True)
        if self.catalog is None:
            return matches[:limit]

        enriched: list[CompanyCandidate] = []
        for candidate in matches[:limit]:
            references = candidate.metadata.get("source_assets", [])
            metadata = dict(candidate.metadata)
            metadata["asset_status"] = self.catalog.inspect(references)
            metadata["asset_summary"] = _summarize_assets(metadata["asset_status"])
            enriched.append(candidate.with_metadata(metadata))
        return enriched


class LocalAssetDataProvider:
    """A no-network provider used until free-data adapters are connected."""

    def enrich(
        self, candidates: Sequence[CompanyCandidate], tier: CompanyDataTier
    ) -> Sequence[CompanyCandidate]:
        return [candidate.with_tier(tier) for candidate in candidates]


def _summarize_assets(assets: Sequence[dict[str, Any]]) -> dict[str, int | bool]:
    return {
        "configured": len(assets),
        "existing": sum(1 for asset in assets if asset.get("exists")),
        "available": sum(1 for asset in assets if asset.get("available")),
        "parsed": sum(1 for asset in assets if asset.get("parse_status") == "PARSED"),
        "missing": sum(1 for asset in assets if not asset.get("available")),
        "complete": bool(assets) and all(asset.get("available") for asset in assets),
    }
