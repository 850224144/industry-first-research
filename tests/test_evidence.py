import json
import sys

import pytest

from industry_first_research.evidence import (
    CROSS_VALIDATED,
    EvidenceError,
    build_evidence,
    build_evidence_bundle,
    build_model_assumption,
    build_research_artifact,
    build_research_candidate_set,
    build_scorecard_artifact,
    build_source_document,
    reconcile_evidence,
    validate_evidence_cutoff,
)
from industry_first_research.cli import main


def source(**overrides):
    payload = {
        "document_id": "doc-official-1",
        "source_name": "official_exchange",
        "source_type": "annual_report",
        "source_url": "https://example.test/annual-report",
        "subject_type": "listed_company",
        "subject_id": "600438",
        "issuer": "示例公司",
        "title": "2025年年度报告",
        "published_at": "2026-04-30T18:00:00+08:00",
        "captured_at": "2026-07-21T08:00:00+08:00",
        "research_as_of": "2026-07-21T23:59:00+08:00",
        "source_version": "exchange-v1",
        "parser_version": "parser-1",
        "raw_content": "official report body",
    }
    payload.update(overrides)
    return payload


def evidence(document, **overrides):
    payload = {
        "evidence_id": "ev-cash-1",
        "subject_type": "listed_company",
        "subject_id": "600438",
        "company_id": "600438",
        "metric": "cash_and_equivalents",
        "value": 123.45,
        "unit": "CNY_million",
        "period": "2025-12-31",
        "source_document_id": document["document_id"],
        "source_name": document["source_name"],
        "source_type": document["source_type"],
        "published_at": document["published_at"],
        "captured_at": document["captured_at"],
        "research_as_of": document["research_as_of"],
        "source_document_version": document["source_version"],
        "content_hash": document["content_hash"],
        "evidence_tier": "A",
        "evidence_status": "verified_fact",
        "verification_status": "VERIFIED",
        "page": 42,
        "table": "合并资产负债表",
        "field_path": "financials.cash_and_equivalents",
    }
    payload.update(overrides)
    return payload


def test_source_document_is_content_addressed_and_immutable():
    document = build_source_document(source())

    assert document["schema_version"] == "source-document.v1"
    assert len(document["content_hash"]) == 64
    assert document["available_before_as_of"] is True
    assert document["immutable"] is True
    assert document["policy"]["old_versions_preserved"] is True


def test_source_document_requires_new_version_for_correction_and_matching_hash():
    with pytest.raises(EvidenceError, match="supersedes_document_id"):
        build_source_document(source(correction_status="CORRECTED"))
    with pytest.raises(EvidenceError, match="content_hash"):
        build_source_document(source(content_hash="0" * 64))


def test_evidence_keeps_field_level_lineage_and_temporal_status():
    document = build_source_document(source())
    item = build_evidence(evidence(document), source_document=document)

    assert item["evidence_status"] == "verified_fact"
    assert item["verification_status"] == "VERIFIED"
    assert item["source_locator"] == {
        "page": 42,
        "table": "合并资产负债表",
        "field_path": "financials.cash_and_equivalents",
    }
    assert item["field_lineage"]["value"]["source_document_id"] == document["document_id"]
    assert item["temporal_status"] == "PRE_CUTOFF"


def test_future_evidence_is_excluded_without_backfilling_history():
    future = evidence(
        build_source_document(source()),
        evidence_id="ev-future",
        published_at="2026-07-22T09:00:00+08:00",
        research_as_of="2026-07-21T23:59:00+08:00",
    )
    result = validate_evidence_cutoff([future], research_as_of="2026-07-21")

    assert result["future_evidence_ids"] == ["ev-future"]
    assert result["eligible_evidence_ids"] == []
    assert result["historical_research_safe"] is False


def test_reconcile_cross_validates_independent_agreement_without_averaging():
    official_doc = build_source_document(source())
    market_doc = build_source_document(
        source(
            document_id="doc-eastmoney-1",
            source_name="eastmoney",
            source_type="market_data",
            source_url="https://example.test/eastmoney",
            raw_content="market snapshot",
        )
    )
    left = build_evidence(evidence(official_doc), source_document=official_doc)
    right = build_evidence(
        evidence(
            market_doc,
            evidence_id="ev-cash-2",
            source_name="eastmoney",
            source_type="market_data",
        ),
        source_document=market_doc,
    )

    result = reconcile_evidence([left, right], research_as_of="2026-07-21")

    group = result["groups"][0]
    assert group["status"] == CROSS_VALIDATED
    assert group["decision"] == "CROSS_VALIDATED"
    assert group["adopted_value"] == 123.45
    assert group["conflict_preserved"] is False
    assert result["conflict_count"] == 0


def test_reconcile_keeps_conflicting_values_and_uses_explicit_priority_only():
    official_doc = build_source_document(source())
    market_doc = build_source_document(
        source(
            document_id="doc-eastmoney-2",
            source_name="eastmoney",
            source_type="market_data",
            source_url="https://example.test/eastmoney-2",
            raw_content="market snapshot 2",
        )
    )
    left = build_evidence(evidence(official_doc), source_document=official_doc)
    right = build_evidence(
        evidence(
            market_doc,
            evidence_id="ev-cash-3",
            source_name="eastmoney",
            source_type="market_data",
            value=98.76,
        ),
        source_document=market_doc,
    )

    result = reconcile_evidence([left, right], research_as_of="2026-07-21")
    group = result["groups"][0]
    assert group["conflict_preserved"] is True
    assert {item["value"] for item in group["values"]} == {123.45, 98.76}
    assert group["decision"] == "RESOLVED_BY_SOURCE_PRIORITY"
    assert group["adopted_value"] == 123.45
    assert result["conflict_count"] == 0


def test_same_priority_conflict_is_not_silently_resolved():
    one = {
        **evidence(build_source_document(source()), evidence_id="ev-1"),
        "source_name": "provider_a",
        "source_type": "market_data",
        "value": 10,
    }
    two = {
        **evidence(build_source_document(source()), evidence_id="ev-2"),
        "source_name": "provider_b",
        "source_type": "market_data",
        "value": 20,
    }
    result = reconcile_evidence(
        [one, two],
        research_as_of="2026-07-21",
        source_priority={"market_data": 60},
    )

    assert result["groups"][0]["decision"] == "UNRESOLVED_CONFLICT"
    assert result["groups"][0]["status"] == "CONFLICTING"
    assert result["conflict_count"] == 1


def test_external_ai_cannot_be_promoted_without_explicit_override():
    document = build_source_document(
        source(
            document_id="doc-ai-1",
            source_name="DeepSeek Web",
            source_type="ai_web",
            source_url="https://example.test/ai-source",
            raw_content="ai answer with source",
        )
    )
    with pytest.raises(EvidenceError, match="cannot be promoted"):
        build_evidence(
            evidence(
                document,
                evidence_id="ev-ai",
                evidence_tier="C_external_ai_lead",
                evidence_status="verified_fact",
            ),
            source_document=document,
        )


def test_bundle_contains_all_research_objects_without_creating_conclusion():
    document = build_source_document(source())
    item = build_evidence(evidence(document), source_document=document)
    bundle = build_evidence_bundle(
        [item],
        source_documents=[document],
        model_assumptions=[
            {"name": "cash_cost", "value": 80, "unit": "CNY", "research_as_of": "2026-07-21"}
        ],
        research_artifacts=[
            {
                "source_project": "luopan",
                "research_as_of": "2026-07-20",
                "artifact_type": "profile",
                "content_hash": "1" * 64,
            }
        ],
        candidate_sets=[{"source_project": "luopan", "research_as_of": "2026-07-20", "candidates": []}],
        scorecards=[{"scorecard_type": "generic_power_screen", "research_as_of": "2026-07-21", "metrics": []}],
        research_as_of="2026-07-21",
    )

    assert bundle["status"] == "READY"
    assert len(bundle["model_assumptions"]) == 1
    assert len(bundle["research_artifacts"]) == 1
    assert bundle["research_candidate_sets"][0]["scope"]["bounded"] is True
    assert bundle["scorecard_artifacts"][0]["claims_are_verified"] is False
    assert bundle["investment_conclusion"] is False


def test_evidence_cli_builds_bundle_and_reconciliation(tmp_path, monkeypatch, capsys):
    document = source()
    payload = {
        "research_as_of": "2026-07-21",
        "subject_id": "600438",
        "source_documents": [document],
        "evidence": [evidence(build_source_document(document))],
    }
    input_path = tmp_path / "evidence-input.json"
    input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    output_dir = tmp_path / "evidence"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "evidence",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
            "--reconcile",
        ],
    )

    main()
    capsys.readouterr()

    bundle_path = output_dir / "evidence-bundle-evidence-input.json"
    reconciliation_path = output_dir / "evidence-reconciliation-evidence-input.json"
    assert bundle_path.exists()
    assert reconciliation_path.exists()
    assert json.loads(bundle_path.read_text(encoding="utf-8"))["status"] == "READY"
    assert json.loads(reconciliation_path.read_text(encoding="utf-8"))["group_count"] == 1


def test_evidence_cli_does_not_overwrite_an_existing_historical_bundle(
    tmp_path, monkeypatch, capsys
):
    document = source()
    payload = {
        "research_as_of": "2026-07-21",
        "source_documents": [document],
        "evidence": [evidence(build_source_document(document))],
    }
    input_path = tmp_path / "evidence-input.json"
    input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    argv = [
        "industry-first-research",
        "evidence",
        "--input",
        str(input_path),
        "--output-dir",
        str(tmp_path / "evidence"),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    main()
    capsys.readouterr()

    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit):
        main()
    assert "evidence-bundle-evidence-input.json" in {
        path.name for path in (tmp_path / "evidence").glob("*.json")
    }


def test_research_objects_reject_missing_cutoff():
    with pytest.raises(EvidenceError, match="research_as_of"):
        build_model_assumption({"name": "x", "value": 1})
    with pytest.raises(EvidenceError, match="research_as_of"):
        build_research_artifact({"source_project": "luopan"})
    with pytest.raises(EvidenceError, match="research_as_of"):
        build_research_candidate_set({"source_project": "luopan"})
    with pytest.raises(EvidenceError, match="research_as_of"):
        build_scorecard_artifact({"scorecard_type": "generic"})
