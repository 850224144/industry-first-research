import hashlib
import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.public_draft import (
    PublicDraftError,
    build_public_draft,
    validate_public_draft,
)


def company_report(*, forbidden=False, with_public_source=True):
    facts = {
        "key_products": {
            "status": "VERIFIED",
            "values": ["核心产品"],
            "evidence_ids": ["ev-1"],
        },
        "positioning": {
            "status": "VERIFIED",
            "values": ["产品定位"],
        },
    }
    if with_public_source:
        facts["source_url"] = "https://example.com/report"
    if forbidden:
        facts["conclusion"] = {"status": "REVIEW", "values": "建议买入"}
    return {
        "schema_version": "company-research-report.v1",
        "report_id": "company-report-001",
        "research_version_id": "research-version-001",
        "as_of": "2026-07-21",
        "items": [
            {
                "company_id": "600519",
                "report_state": "REVIEWABLE",
                "conclusion_state": "CONDITIONAL_REVIEW_ONLY",
                "target_price": 200,
                "position": {"quantity": 10},
                "private_note": "仅供个人记录",
                "sections": {"business": {"facts": facts}},
            }
        ],
        "policy": {"execution_enabled": False},
    }


def payload_hash(payload):
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def lock_for(report, status="LOCKED"):
    return {
        "status": status,
        "source_research_id": "research-version-001",
        "source_report_hash": payload_hash(report),
    }


def test_public_draft_redacts_private_fields_and_requires_review():
    report = company_report()
    draft = build_public_draft(report, lock_for(report))

    assert draft["schema_version"] == "public-draft.v1"
    assert draft["review_status"] == "NEEDS_HUMAN_REVIEW"
    assert draft["status"] == "READY_FOR_HUMAN_REVIEW"
    assert draft["publication_status"] == "NOT_PUBLISHED"
    assert draft["policy"]["publication_api_called"] is False
    assert "target_price" in " ".join(draft["removed_private_fields"])
    assert "position" in " ".join(draft["removed_private_fields"])
    assert "positioning" not in " ".join(draft["removed_private_fields"])
    assert draft["source_check"]["status"] == "PASS"
    assert validate_public_draft(draft)["content_hash"] == draft["content_hash"]


def test_public_draft_rejects_unlocked_or_mismatched_report():
    report = company_report()
    with pytest.raises(PublicDraftError, match="LOCKED or USER_CONFIRMED"):
        build_public_draft(report, lock_for(report, status="DRAFT"))
    wrong_lock = lock_for(report)
    wrong_lock["source_report_hash"] = "wrong-hash"
    with pytest.raises(PublicDraftError, match="does not match"):
        build_public_draft(report, wrong_lock)


def test_sensitive_expression_blocks_public_draft():
    report = company_report(forbidden=True)
    draft = build_public_draft(report, lock_for(report))

    assert draft["status"] == "BLOCKED"
    assert draft["review_status"] == "BLOCKED"
    assert "买入" in draft["compliance_check"]["forbidden_terms"]


def test_public_draft_validation_rejects_tampered_content_and_publish_flags():
    report = company_report()
    draft = build_public_draft(report, lock_for(report))
    draft["content"] += "\nchanged"
    with pytest.raises(PublicDraftError, match="content_hash"):
        validate_public_draft(draft)

    clean_report = company_report()
    clean = build_public_draft(clean_report, lock_for(clean_report))
    clean["policy"]["publication_api_called"] = True
    with pytest.raises(PublicDraftError, match="publication_api_called"):
        validate_public_draft(clean)


def test_public_draft_without_public_url_stays_review_required():
    report = company_report(with_public_source=False)
    draft = build_public_draft(report, lock_for(report))

    assert draft["source_check"]["status"] == "REVIEW_REQUIRED"
    assert draft["source_check"]["source_count"] == 0


def test_public_draft_cli_writes_json_and_markdown(tmp_path, monkeypatch, capsys):
    report = company_report()
    report_path = tmp_path / "report.json"
    lock_path = tmp_path / "lock.json"
    output_dir = tmp_path / "public_drafts"
    report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    lock_path.write_text(json.dumps(lock_for(report), ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", [
        "industry-first-research",
        "public-draft",
        "--input",
        str(report_path),
        "--source-lock",
        str(lock_path),
        "--output-dir",
        str(output_dir),
    ])
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["draft"]["publication_status"] == "NOT_PUBLISHED"
    assert result["draft"]["policy"]["publication_api_called"] is False
    assert len(list(output_dir.glob("*.json"))) == 1
    assert len(list(output_dir.glob("*.md"))) == 1

    draft_path = next(output_dir.glob("*.json"))
    monkeypatch.setattr(sys, "argv", [
        "industry-first-research",
        "validate-public-draft",
        "--input",
        str(draft_path),
    ])
    main()
    validation = json.loads(capsys.readouterr().out)
    assert validation["valid"] is True
