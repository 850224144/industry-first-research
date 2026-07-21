import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.futures_identity import (
    FuturesIdentityError,
    identify_futures_object,
)


def base(object_type="futures_contract"):
    return {
        "schema_version": "futures-object-input.v1",
        "object_type": object_type,
        "as_of": "2026-07-21",
        "exchange": "SHFE",
        "variety_id": "RB",
        "variety_name": "螺纹钢",
        "industry_chain": {"role": "steel"},
        "contract": {
            "contract_code": "RB2610",
            "contract_month": "2026-10",
            "last_trade_date": "2026-10-15",
            "contract_multiplier": 10,
            "tick_size": 1,
            "settlement_basis": "daily_settlement",
            "rule_version": "shfe-rb-v1",
        },
    }


def test_specific_contract_is_ready_and_simulation_allowed():
    report = identify_futures_object(base())
    assert report["status"] == "READY"
    assert report["simulation_allowed"] is True
    assert report["contract"]["contract_code"] == "RB2610"
    assert report["policy"]["specific_contract_required_for_simulation"] is True


def test_continuous_series_requires_complete_rule_and_is_research_only():
    payload = base("continuous_series")
    payload["continuous_series_rule"] = {
        "main_contract_rule": "highest_open_interest_as_of",
        "roll_rule": "five_days_before_expiry",
        "stitching_rule": "back_adjusted",
        "adjustment_rule": "backward_ratio",
        "components": [
            {
                "contract_code": "RB2609",
                "valid_from": "2026-01-01",
                "valid_to": "2026-09-30",
            }
        ],
    }
    report = identify_futures_object(payload)
    assert report["status"] == "READY"
    assert report["research_only"] is True
    assert report["simulation_allowed"] is False
    assert report["policy"]["continuous_series_not_tradeable"] is True


def test_continuous_series_without_rule_is_blocked():
    report = identify_futures_object(base("continuous_series"))
    assert report["status"] == "BLOCKED"
    assert "continuous_series_rule" in report["blockers"][0]


def test_contract_missing_exchange_or_expired_contract_is_not_ready():
    payload = base()
    payload["exchange"] = ""
    report = identify_futures_object(payload)
    assert report["status"] == "BLOCKED"

    payload = base()
    payload["contract"]["last_trade_date"] = "2026-07-20"
    report = identify_futures_object(payload)
    assert report["status"] == "READY"
    assert "expired" in report["warnings"][0]


def test_main_or_continuous_contract_symbol_cannot_be_simulated():
    payload = base()
    payload["contract"]["contract_code"] = "CONTINUOUS"
    report = identify_futures_object(payload)
    assert report["status"] == "BLOCKED"
    assert report["simulation_allowed"] is False


def test_futures_identity_cli_writes_snapshot(tmp_path, monkeypatch, capsys):
    input_path = tmp_path / "futures.json"
    output_dir = tmp_path / "identities"
    input_path.write_text(json.dumps(base()), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "futures-identify",
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
    assert report["simulation_allowed"] is True


def test_invalid_component_is_rejected():
    payload = base("continuous_series")
    payload["continuous_series_rule"] = {"components": [{}]}
    with pytest.raises(FuturesIdentityError, match="component 0"):
        identify_futures_object(payload)
