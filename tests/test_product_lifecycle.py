import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.product_lifecycle import (
    ProductLifecycleError,
    build_product_lifecycle_report,
    validate_product_lifecycle_report,
)


MARKET_FIELDS = (
    "price",
    "inventory",
    "supply",
    "demand",
    "utilization",
    "customer_capex",
    "competitor_expansion",
)


def field(value, *, status="VERIFIED", evidence_id="ev-1"):
    return {"value": value, "status": status, "evidence_ids": [evidence_id]}


def lifecycle_input(**overrides):
    payload = {
        "schema_version": "product-lifecycle-input.v1",
        "report_id": "lifecycle-input-001",
        "as_of": "2026-07-23",
        "items": [
            {
                "snapshot_item_id": "lifecycle-item-001",
                "company_id": "600438",
                "scope_id": "company-scope-600438",
                "product_id": "module-001",
                "product_name": "示例组件",
                "lifecycle_state": field("RAMP_UP", evidence_id="ev-life"),
                "next_stage_conditions": ["客户认证转为批量订单"],
                "substitution_factors": ["替代技术降价并通过客户认证"],
                "market_state": field("EXPANDING", evidence_id="ev-market"),
                "market_snapshot": {
                    name: field(name, evidence_id=f"ev-{name}")
                    for name in MARKET_FIELDS
                },
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_lifecycle_snapshot_preserves_explicit_stage_and_market_fields():
    report = build_product_lifecycle_report(lifecycle_input())

    item = report["items"][0]
    assert report["schema_version"] == "product-lifecycle-snapshot.v1"
    assert item["lifecycle_state"] == "RAMP_UP"
    assert item["market_state"] == "EXPANDING"
    assert item["next_stage_options"] == ["MATURE", "PRICE_DECLINE"]
    assert item["snapshot_state"] == "READY"
    assert item["transition_status"] == "EXPLICIT_STAGE_ONLY"
    assert item["scope_status"] == "UNVERIFIED"
    assert report["policy"]["no_stage_inference_from_price"] is True
    assert report["investment_conclusion"] is False


def test_missing_lifecycle_or_market_fields_degrade_without_inference():
    payload = lifecycle_input()
    item = payload["items"][0]
    item.pop("lifecycle_state")
    item["market_snapshot"].pop("inventory")
    item.pop("next_stage_conditions")
    item.pop("substitution_factors")

    report = build_product_lifecycle_report(payload)
    result = report["items"][0]
    assert result["lifecycle_state"] == "UNKNOWN"
    assert result["snapshot_state"] == "INSUFFICIENT"
    assert "lifecycle_state" in result["unknowns"]
    assert "inventory" in result["unknowns"]
    assert result["next_stage_options"] == []
    assert result["transition_status"] == "EXPLICIT_STAGE_ONLY"


def test_unverified_stage_is_partial_even_when_market_snapshot_is_complete():
    payload = lifecycle_input()
    payload["items"][0]["lifecycle_state"] = field(
        "MATURE", status="MODEL_ASSUMPTION", evidence_id=""
    )
    payload["items"][0]["lifecycle_state"]["evidence_ids"] = []

    result = build_product_lifecycle_report(payload)["items"][0]
    assert result["snapshot_state"] == "PARTIAL"
    assert result["evidence_status"] == "PARTIAL"
    assert any("formal evidence" in warning for warning in result["warnings"])


def test_future_market_field_is_not_allowed_to_backfill_snapshot():
    payload = lifecycle_input()
    payload["items"][0]["market_snapshot"]["price"]["as_of"] = "2026-07-24"

    result = build_product_lifecycle_report(payload)["items"][0]
    assert result["snapshot_state"] == "PARTIAL"
    assert result["market_snapshot"]["price"]["status"] == "UNKNOWN"


def test_scope_mismatch_blocks_lifecycle_snapshot():
    payload = lifecycle_input()
    scope_report = {
        "schema_version": "company-scope.v1",
        "scope_id": "company-scope-other",
        "company_id": "600438",
        "researchability_state": "READY",
    }
    result = build_product_lifecycle_report(
        payload,
        company_scope_reports={"600438": scope_report},
    )["items"][0]
    assert result["snapshot_state"] == "BLOCKED"
    assert result["scope_status"] == "CONFLICTING"


def test_invalid_state_and_cli_validation(tmp_path, monkeypatch, capsys):
    payload = lifecycle_input()
    payload["items"][0]["lifecycle_state"] = field("NOT_A_STAGE")
    with pytest.raises(ProductLifecycleError, match="unsupported lifecycle_state"):
        build_product_lifecycle_report(payload)

    input_path = tmp_path / "lifecycle.json"
    input_path.write_text(json.dumps(lifecycle_input(), ensure_ascii=False), encoding="utf-8")
    output_dir = tmp_path / "snapshots"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "product-lifecycle",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
    )
    main()
    capsys.readouterr()
    report_path = output_dir / "product-lifecycle-lifecycle-input-001.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert validate_product_lifecycle_report(report)["status"] == "VALID"
