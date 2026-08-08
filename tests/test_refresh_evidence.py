import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.data_refresh import build_data_source_refresh
from industry_first_research.data_sources import (
    DataSourceHealth,
    DataSourceRouter,
    FreeDataSourcePolicy,
)
from industry_first_research.refresh_evidence import (
    RefreshEvidenceError,
    build_refresh_evidence_gate,
    validate_refresh_evidence_gate,
)


class Adapter:
    name = "eastmoney"
    source_type = "test"

    def health_check(self):
        return DataSourceHealth(self.name, self.source_type, True, capabilities=("cn_stock",))

    def fetch(self, _query, as_of):
        return {
            "source": self.name,
            "source_type": self.source_type,
            "url": "https://example.test/market",
            "retrieved_at": f"{as_of}T09:00:00+08:00",
            "data": [{"close": 10}],
        }

    def normalize(self, value):
        return value


def refresh_report():
    router = DataSourceRouter(
        [Adapter()],
        FreeDataSourcePolicy(listed_company_sources=("eastmoney",)),
    )
    return build_data_source_refresh(
        {
            "schema_version": "data-source-refresh-input.v1",
            "as_of": "2026-07-25",
            "queries": [
                {
                    "query_id": "company-600438-quote",
                    "subject_type": "listed_company",
                    "subject_id": "600438.SH",
                    "source_names": ["eastmoney"],
                    "request": {"required_fields": ["data"]},
                }
            ],
        },
        router,
    )


def records():
    return [
        {
            "query_id": "company-600438-quote",
            "metric": "close",
            "value": 10,
            "unit": "CNY/share",
            "period": "2026-07-25",
            "published_at": "2026-07-25T08:00:00+08:00",
            "captured_at": "2026-07-25T09:00:00+08:00",
            "evidence_tier": "C",
            "evidence_status": "market_signal",
            "verification_status": "VERIFIED",
            "manual_override_id": "review-001",
            "source_field": "close",
        }
    ]


def test_refresh_evidence_requires_manual_confirmation_before_promotion(tmp_path):
    report = build_refresh_evidence_gate(
        refresh_report(),
        records(),
        refresh_uri=str(tmp_path / "refresh.json"),
    )

    assert report["status"] == "REVIEW_REQUIRED"
    assert report["evidence_bundle"] is None
    assert report["policy"]["fact_promotion"] is False
    assert report["candidate_records"][0]["source_document_id"]
    assert validate_refresh_evidence_gate(report)["gate_id"] == report["gate_id"]


def test_refresh_evidence_promotes_only_with_audited_user_confirmation(tmp_path):
    report = build_refresh_evidence_gate(
        refresh_report(),
        records(),
        refresh_uri=str(tmp_path / "refresh.json"),
        user_confirmed=True,
        reviewer_id="researcher",
        reviewed_at="2026-07-25T10:00:00+08:00",
        review_reason="人工核对来源和字段口径",
    )

    assert report["status"] == "PROMOTED"
    assert report["policy"]["fact_promotion"] is True
    assert report["evidence_bundle"]["schema_version"] == "evidence-bundle.v1"
    assert report["evidence_bundle"]["evidence"][0]["source_document_id"]


def test_refresh_evidence_rejects_confirmation_without_audit_fields():
    with pytest.raises(RefreshEvidenceError, match="reviewer_id"):
        build_refresh_evidence_gate(
            refresh_report(),
            records(),
            user_confirmed=True,
            reviewed_at="2026-07-25T10:00:00+08:00",
            review_reason="missing reviewer",
        )
    missing_override = records()
    missing_override[0].pop("manual_override_id")
    with pytest.raises(RefreshEvidenceError, match="manual_override_id"):
        build_refresh_evidence_gate(
            refresh_report(),
            missing_override,
            user_confirmed=True,
            reviewer_id="researcher",
            reviewed_at="2026-07-25T10:00:00+08:00",
            review_reason="missing override",
        )


def test_refresh_evidence_validation_rejects_tampering(tmp_path):
    report = build_refresh_evidence_gate(
        refresh_report(),
        records(),
        refresh_uri=str(tmp_path / "refresh.json"),
    )
    report["candidate_records"][0]["value"] = 11
    with pytest.raises(RefreshEvidenceError, match="content_hash"):
        validate_refresh_evidence_gate(report)


def test_evidence_from_refresh_cli_can_stop_at_review_gate(tmp_path, monkeypatch, capsys):
    refresh_path = tmp_path / "refresh.json"
    records_path = tmp_path / "records.json"
    refresh_path.write_text(json.dumps(refresh_report(), ensure_ascii=False), encoding="utf-8")
    records_path.write_text(json.dumps({"records": records()}, ensure_ascii=False), encoding="utf-8")
    output_dir = tmp_path / "gates"
    monkeypatch.setattr(sys, "argv", [
        "industry-first-research",
        "evidence-from-refresh",
        "--refresh",
        str(refresh_path),
        "--records",
        str(records_path),
        "--output-dir",
        str(output_dir),
    ])

    main()
    result = json.loads(capsys.readouterr().out)
    assert result["report"]["status"] == "REVIEW_REQUIRED"
    assert result["evidence_bundle"] == ""
    assert len(list(output_dir.glob("*.json"))) == 1
