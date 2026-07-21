import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.opportunity_candidate import (
    OpportunityCandidateError,
    build_opportunity_candidate,
    build_opportunity_scan,
)


def candidate_input(**overrides):
    payload = {
        "schema_version": "opportunity-candidate-input.v1",
        "as_of": "2026-07-21",
        "candidate": {
            "candidate_id": "candidate-cycle-600438",
            "company_id": "600438",
            "display_name": "示例公司",
            "industry_id": "photovoltaic",
        },
        "opportunity_types": ["cycle_reversal"],
        "dimensions": {
            "downside_protection": {
                "status": "PASS",
                "survival_gate_pass": True,
                "evidence_refs": ["cash-001"],
            },
            "inflection_evidence": {
                "status": "PASS",
                "independent_signal_types": 2,
                "normal_update_cycles": 2,
                "evidence_refs": ["inventory-001", "price-001"],
            },
            "profit_convexity": {"status": "PARTIAL", "evidence_refs": ["model-001"]},
            "expectation_gap": {
                "status": "PASS",
                "not_obviously_overpriced": True,
                "evidence_refs": ["valuation-001"],
            },
        },
        "hard_gates": {
            "identity": {"status": "PASS", "evidence_refs": ["company-001"]},
            "survival": {"status": "PASS", "evidence_refs": ["cash-001"]},
            "governance": {"status": "PASS", "evidence_refs": ["annual-001"]},
        },
        "clocks": {
            "industry_clock": {"state": "INFLECTION_CANDIDATE"},
            "company_clock": {"state": "SURVIVAL_SECURE"},
            "market_clock": {"state": "PESSIMISM_PRICED"},
        },
        "evidence_refs": ["cash-001", "inventory-001", "valuation-001"],
    }
    payload.update(overrides)
    return payload


def test_candidate_preserves_four_dimensions_and_does_not_make_a_total_score():
    report = build_opportunity_candidate(candidate_input())

    assert report["status"] == "CANDIDATE"
    assert set(report["dimensions"]) == {
        "downside_protection",
        "inflection_evidence",
        "profit_convexity",
        "expectation_gap",
    }
    assert "score" not in report
    assert report["hard_gate"]["status"] == "PASS"
    assert report["industry_clock"]["state"] == "INFLECTION_CANDIDATE"
    assert report["policy"]["price_or_volume_cannot_upgrade_state"] is True


def test_candidate_becomes_reviewable_only_after_deep_research_gates():
    payload = candidate_input(
        deep_research={
            "complete": True,
            "product_profit_source_review": True,
            "survival_stress_test": True,
            "reverse_valuation": True,
            "adversarial_review_passed": True,
        }
    )
    report = build_opportunity_candidate(payload)
    assert report["status"] == "REVIEWABLE"


def test_hard_rejection_and_reentry_are_retained():
    payload = candidate_input(
        hard_gates={
            "identity": {"status": "PASS"},
            "survival": {"status": "BLOCKED", "reason": "unfunded refinancing gap"},
        },
        reentry_conditions=["new audited financing plan", "cash runway verified"],
    )
    report = build_opportunity_candidate(payload)
    assert report["status"] == "REJECTED"
    assert report["rejection"]["status"] == "RECORDED"
    assert "survival" in report["hard_gate"]["blocked_gates"]
    assert report["rejection"]["reentry_conditions"] == [
        "new audited financing plan",
        "cash runway verified",
    ]


def test_scan_keeps_empty_result_and_rejections_visible():
    scan = build_opportunity_scan(
        {
            "schema_version": "opportunity-scan-input.v1",
            "scan_id": "scan-001",
            "as_of": "2026-07-21",
            "candidates": [candidate_input(), candidate_input(
                candidate={"candidate_id": "candidate-bad", "company_id": "000001"},
                hard_gates={"identity": {"status": "BLOCKED"}},
            )],
        }
    )
    assert scan["empty_result"] is False
    assert scan["state_counts"]["CANDIDATE"] == 1
    assert len(scan["rejections"]) == 1

    empty = build_opportunity_scan(
        {
            "schema_version": "opportunity-scan-input.v1",
            "scan_id": "scan-empty",
            "as_of": "2026-07-21",
            "candidates": [],
        }
    )
    assert empty["empty_result"] is True
    assert empty["candidate_count"] == 0


def test_candidate_cli_writes_a_state_snapshot(tmp_path, monkeypatch, capsys):
    input_path = tmp_path / "candidate.json"
    output_dir = tmp_path / "candidates"
    input_path.write_text(json.dumps(candidate_input()), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "opportunity-candidate",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
    )
    main()
    capsys.readouterr()

    report = json.loads(
        (output_dir / "candidate-cycle-600438.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "CANDIDATE"
    assert report["investment_conclusion"] is False


def test_invalid_dimension_status_is_rejected():
    payload = candidate_input()
    payload["dimensions"]["profit_convexity"]["status"] = "GOOD"
    with pytest.raises(OpportunityCandidateError, match="unsupported dimension"):
        build_opportunity_candidate(payload)


def test_rejected_candidate_needs_new_reentry_evidence_before_reconsideration():
    payload = candidate_input(
        previous={"status": "REJECTED"},
        reentry_conditions=["new audited evidence"],
    )
    report = build_opportunity_candidate(payload)
    assert report["status"] == "DISCOVERED"
    assert "reentry_conditions_met" in report["missing"]

    payload["reentry_conditions_met"] = True
    report = build_opportunity_candidate(payload)
    assert report["status"] == "CANDIDATE"
