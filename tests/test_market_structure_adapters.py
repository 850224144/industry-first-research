import json
import sys

from industry_first_research.cli import main
from industry_first_research.market_structure_adapters import (
    ChanPyAdapter,
    CzscAdapter,
    build_market_structure_comparison,
)


def bars(count=25, *, start=100.0, step=1.0):
    return [
        {
            "timestamp": f"2026-07-{index + 1:02d}T15:00:00+08:00",
            "open": start + index * step - 0.5,
            "high": start + index * step + 1,
            "low": start + index * step - 1,
            "close": start + index * step,
            "volume": 1000 + index,
        }
        for index in range(count)
    ]


def input_report():
    return {
        "schema_version": "market-structure-input.v1",
        "subject_type": "listed_company",
        "subject_id": "600438",
        "display_name": "测试标的",
        "as_of": "2026-07-25T15:00:00+08:00",
        "price_series_id": "600438-daily",
        "adjustment": "qfq",
        "timeframes": {"daily": bars()},
    }


def external_report(state="UPTREND", implementation_version="fixture-1"):
    return {
        "implementation_version": implementation_version,
        "timeframes": {
            "daily": {
                "state": state,
                "volatility": "MEDIUM",
                "position": "MIDDLE",
                "confirmation": "CONFIRMED_UNTIL_AS_OF",
                "repaint_risk": "MEDIUM",
                "structure_points": ["P1"],
                "definition_notes": ["fixture definition"],
            }
        },
        "confirmation": "CONFIRMED_UNTIL_AS_OF",
        "repaint_risk": "MEDIUM",
    }


def test_optional_packages_are_degraded_without_breaking_local_structure():
    report = build_market_structure_comparison(input_report())

    assert report["implementations"]["local_deterministic"]["status"] == "AVAILABLE"
    assert report["implementations"]["czsc"]["status"] in {
        "PACKAGE_NOT_INSTALLED",
        "RUNNER_NOT_CONFIGURED",
    }
    assert report["implementations"]["chan_py"]["status"] in {
        "PACKAGE_NOT_INSTALLED",
        "RUNNER_NOT_CONFIGURED",
    }
    assert report["confidence"] == "LOW"
    assert report["policy"]["trading_signal_included"] is False


def test_external_results_are_kept_separate_and_disagreement_lowers_confidence():
    report = build_market_structure_comparison(
        input_report(),
        adapters=(
            CzscAdapter(runner=lambda _: external_report("UPTREND")),
            ChanPyAdapter(runner=lambda _: external_report("DOWNTREND")),
        ),
    )

    assert report["comparison"]["status"] == "DIVERGENT"
    assert report["confidence"] == "LOW"
    assert report["comparison"]["timeframes"]["daily"]["definition_difference"] is True
    assert report["implementations"]["czsc"]["report"]["implementation"] == "czsc"
    assert report["implementations"]["chan_py"]["report"]["implementation"] == "chan_py"


def test_matching_external_results_are_consistent_but_not_a_trading_signal():
    report = build_market_structure_comparison(
        input_report(),
        adapters=(
            CzscAdapter(runner=lambda _: external_report("UPTREND")),
            ChanPyAdapter(runner=lambda _: external_report("UPTREND")),
        ),
    )

    assert report["comparison"]["status"] == "CONSISTENT"
    assert report["confidence"] == "MEDIUM"
    assert report["implementations"]["czsc"]["report"]["signal"] is None
    assert report["implementations"]["chan_py"]["report"]["signal"] is None


def test_adapter_failure_is_recorded_not_raised():
    report = build_market_structure_comparison(
        input_report(),
        adapters=(
            CzscAdapter(runner=lambda _: (_ for _ in ()).throw(RuntimeError("broken"))),
        ),
    )
    assert report["implementations"]["czsc"]["status"] == "FAILED"
    assert "broken" in report["implementations"]["czsc"]["error"]


def test_market_structure_compare_cli_writes_comparison(tmp_path, monkeypatch, capsys):
    input_path = tmp_path / "market-structure.json"
    output_dir = tmp_path / "comparisons"
    input_path.write_text(json.dumps(input_report()), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "market-structure-compare",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
    )
    main()
    capsys.readouterr()

    files = list(output_dir.glob("*.json"))
    assert len(files) == 1
    report = json.loads(files[0].read_text(encoding="utf-8"))
    assert report["schema_version"] == "market-structure-comparison.v1"
