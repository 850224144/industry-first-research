import pytest

from industry_first_research.manual_evidence import (
    ManualEvidenceTemplateError,
    build_manual_evidence_template,
)
from industry_first_research.supplemental_evidence import (
    SupplementalEvidenceError,
    build_supplemental_evidence_report,
)


def queue_report():
    return {
        "schema_version": "company-candidate-queue.v1",
        "queue_id": "queue-001",
        "input_snapshot_id": "screen-001",
        "as_of": "2026-07-19",
        "source": "tonghuashun",
        "items": [
            {"company_id": "300317", "display_name": "珈伟新能"},
            {"company_id": "000001", "display_name": "平安银行"},
        ],
    }


def test_manual_template_is_blank_and_traceable():
    template = build_manual_evidence_template(
        queue_report(), company_ids=["300317"], fields=["listing_market"]
    )

    assert template["schema_version"] == "company-manual-evidence-template.v1"
    assert template["input_queue_id"] == "queue-001"
    assert template["company_ids"] == ["300317"]
    record = template["records"][0]
    assert record["company_id"] == "300317"
    assert record["field"] == "listing_market"
    assert record["value"] == ""
    assert record["verification_status"] == "UNVERIFIED"
    assert template["policy"]["stock_code_inference_forbidden"] is True


def test_manual_template_rejects_unknown_company():
    with pytest.raises(ManualEvidenceTemplateError, match="not in the input queue"):
        build_manual_evidence_template(queue_report(), company_ids=["999999"])


def test_supplemental_rejects_empty_evidence_values():
    record = {
        "evidence_id": "ev-1",
        "company_id": "300317",
        "field": "listing_market",
        "value": "",
        "source": "https://example.test/official",
        "source_refs": [],
        "as_of": "2026-07-19",
        "evidence_tier": "A",
        "verification_status": "VERIFIED",
    }
    with pytest.raises(SupplementalEvidenceError, match="value must be non-empty"):
        build_supplemental_evidence_report(queue_report(), [record])


def test_supplemental_requires_string_listing_market_value():
    record = {
        "evidence_id": "ev-1",
        "company_id": "300317",
        "field": "listing_market",
        "value": {"name": "深圳证券交易所"},
        "source": "https://example.test/official",
        "source_refs": [],
        "as_of": "2026-07-19",
        "evidence_tier": "A",
        "verification_status": "VERIFIED",
    }
    with pytest.raises(
        SupplementalEvidenceError, match="listing_market evidence value must be a string"
    ):
        build_supplemental_evidence_report(queue_report(), [record])
