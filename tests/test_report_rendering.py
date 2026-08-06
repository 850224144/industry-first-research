import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.report_rendering import (
    ReportRenderingError,
    render_research_html,
    render_research_markdown,
    write_rendered_reports,
)


def company_report():
    return {
        "schema_version": "company-research-report.v1",
        "report_id": "company-report-001",
        "as_of": "2026-07-21",
        "items": [
            {
                "company_id": "600519",
                "report_state": "REVIEWABLE",
                "conclusion_state": "CONDITIONAL_REVIEW_ONLY",
                "sections": {
                    "business": {
                        "facts": {
                            "key_products": {
                                "status": "VERIFIED",
                                "values": ["白酒"],
                                "evidence_ids": ["evidence-1"],
                            }
                        },
                        "unknowns": ["customer_concentration"],
                    }
                },
                "tracking_checklist": {
                    "status": "READY",
                    "next_check_at": "2026-08-21",
                },
                "simulation_recommendation": {
                    "state": "USER_CONFIRMATION_REQUIRED",
                    "recommended_action": "USER_CONFIRMATION_REQUIRED",
                    "direction": "NEUTRAL",
                    "next_check_at": "2026-08-21",
                    "reasons": ["证据已整理"],
                    "data_gaps": [],
                    "invalidators": ["现金流转负"],
                },
            }
        ],
        "policy": {"execution_enabled": False},
    }


def futures_report():
    return {
        "schema_version": "futures-fundamentals-report.v1",
        "report_id": "futures-report-001",
        "as_of": "2026-07-21",
        "status": "READY",
        "exchange": "SHFE",
        "variety_id": "CU",
        "variety_name": "沪铜",
        "object_type": "futures_contract",
        "identity_status": "READY",
        "derived_metrics": {"spot_latest": {"value": 101}},
        "price_scenarios": {"scenarios": {}},
        "policy": {"execution_enabled": False},
    }


def test_company_markdown_and_html_preserve_evidence_and_boundary():
    markdown = render_research_markdown(company_report())
    html = render_research_html(company_report())

    assert "600519" in markdown
    assert "customer_concentration" in markdown
    assert "evidence-1" in markdown
    assert "USER_CONFIRMATION_REQUIRED" in markdown
    assert "现金流转负" in markdown
    assert "自动交易：`false`" in markdown
    assert "company-report-001" not in markdown
    assert "execution_enabled" in html
    assert "REVIEWABLE" in html
    assert "USER_CONFIRMATION_REQUIRED" in html


def test_render_report_cli_writes_markdown_and_html(tmp_path, monkeypatch, capsys):
    input_path = tmp_path / "report.json"
    input_path.write_text(json.dumps(futures_report(), ensure_ascii=False), encoding="utf-8")
    output_dir = tmp_path / "rendered"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "render-report",
            "--input",
            str(input_path),
            "--format",
            "markdown",
            "--format",
            "html",
            "--output-dir",
            str(output_dir),
        ],
    )
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "research-report-render.v1"
    assert (output_dir / "futures-report-001.md").exists()
    assert (output_dir / "futures-report-001.html").exists()


def test_rendered_reports_are_an_atomic_immutable_bundle(tmp_path):
    output_dir = tmp_path / "rendered"
    output_dir.mkdir()
    existing = output_dir / "futures-report-001.html"
    existing.write_text("existing", encoding="utf-8")

    with pytest.raises(ReportRenderingError, match="already exists"):
        write_rendered_reports(futures_report(), output_dir)

    assert not (output_dir / "futures-report-001.md").exists()
    assert existing.read_text(encoding="utf-8") == "existing"
