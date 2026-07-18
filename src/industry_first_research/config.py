"""Load industry-first configurations without embedding an industry in the core."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import (
    CompanyCandidate,
    IndustryRadarSnapshot,
    IndustrySignal,
    IndustryState,
)


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("industry config must be a JSON object")
    required_keys = ("industry_id", "display_name", "as_of", "state", "companies")
    for key in required_keys:
        if key not in payload:
            raise ValueError(f"industry config is missing {key!r}")
    return payload


def load_company_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("company config must be a JSON object")
    for key in ("company_id", "as_of"):
        if key not in payload:
            raise ValueError(f"company config is missing {key!r}")
    return payload


def radar_from_config(config: dict[str, Any]) -> IndustryRadarSnapshot:
    signals = tuple(
        IndustrySignal(
            name=item["name"],
            value=item.get("value"),
            as_of=item.get("as_of", config["as_of"]),
            source=item.get("source", "config"),
            evidence_status=item.get("evidence_status", "UNVERIFIED"),
            note=item.get("note", ""),
        )
        for item in config.get("signals", [])
    )
    return IndustryRadarSnapshot(
        industry_id=config["industry_id"],
        display_name=config["display_name"],
        as_of=config["as_of"],
        state=IndustryState(config["state"]),
        signals=signals,
        evidence_completeness=config.get("evidence_completeness", "UNKNOWN"),
        opportunity_types=tuple(config.get("opportunity_types", [])),
        reason=config.get("reason", ""),
    )


def candidates_from_config(config: dict[str, Any]) -> list[CompanyCandidate]:
    candidates: list[CompanyCandidate] = []
    for item in config["companies"]:
        candidates.append(
            CompanyCandidate(
                company_id=item["company_id"],
                display_name=item["display_name"],
                industry_id=config["industry_id"],
                source=item.get("source", "config"),
                inclusion_reason=item.get("inclusion_reason", ""),
                hard_gate_status=item.get("hard_gate_status", "PENDING"),
                score=item.get("score"),
                notes=tuple(item.get("notes", [])),
                metadata={
                    key: value
                    for key, value in item.items()
                    if key
                    not in {
                        "company_id",
                        "display_name",
                        "source",
                        "inclusion_reason",
                        "hard_gate_status",
                        "score",
                        "notes",
                    }
                },
            )
        )
    return candidates


def source_documents(config: dict[str, Any]) -> list[dict[str, Any]]:
    return list(config.get("source_documents", []))
