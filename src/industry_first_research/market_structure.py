"""Build deterministic, non-trading market-structure snapshots from OHLCV bars."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from math import sqrt
from statistics import mean
from typing import Any


class MarketStructureError(ValueError):
    """Raised when a market-structure input cannot be checked safely."""


MARKET_STRUCTURE_SCHEMA_VERSION = "market-structure-snapshot.v1"
INPUT_SCHEMA_VERSION = "market-structure-input.v1"
RULE_VERSION = "market-structure-local-rules.v1"
IMPLEMENTATION = "local_deterministic"
IMPLEMENTATION_VERSION = "local-deterministic-1.0"
MIN_CONFIRMATION_BARS = 20
_TIMEFRAME_STATES = {"UPTREND", "DOWNTREND", "RANGE", "INSUFFICIENT_DATA"}
_VOLATILITY_STATES = {"LOW", "MEDIUM", "HIGH", "UNKNOWN"}
_POSITION_STATES = {"UPPER_HALF", "MIDDLE", "LOWER_HALF", "UNKNOWN"}


def build_market_structure_report(
    input_report: Mapping[str, Any],
    *,
    rule_version: str = RULE_VERSION,
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Describe price structure only; never emit trading signals or orders."""

    if not isinstance(input_report, Mapping):
        raise MarketStructureError("market structure input must be a JSON object")
    if input_report.get("schema_version") != INPUT_SCHEMA_VERSION:
        raise MarketStructureError(
            "input must be a market-structure-input.v1 report"
        )
    if not rule_version.strip():
        raise MarketStructureError("rule_version must not be empty")

    subject = _normalise_subject(input_report)
    as_of = _parse_datetime(input_report.get("as_of"), "as_of")
    raw_timeframes = input_report.get("timeframes")
    if not isinstance(raw_timeframes, Mapping) or not raw_timeframes:
        raise MarketStructureError("timeframes must be a non-empty object")

    timeframes: dict[str, dict[str, Any]] = {}
    all_bars = 0
    for timeframe, raw_bars in raw_timeframes.items():
        name = str(timeframe).strip()
        if not name:
            raise MarketStructureError("timeframe names must not be empty")
        bars = _normalise_bars(raw_bars, as_of=as_of, timeframe=name)
        timeframes[name] = _analyse_timeframe(name, bars)
        all_bars += len(bars)

    report_id = snapshot_id or str(input_report.get("snapshot_id") or "")
    if not report_id:
        report_id = f"{subject['subject_id']}-{_compact_datetime(as_of)}"
    confirmation = (
        "CONFIRMED_UNTIL_AS_OF"
        if all(
            item["bars"] >= MIN_CONFIRMATION_BARS
            for item in timeframes.values()
        )
        else "UNCONFIRMED"
    )
    repaint_risk = (
        "LOW" if confirmation == "CONFIRMED_UNTIL_AS_OF" else "MEDIUM"
    )
    return {
        "schema_version": MARKET_STRUCTURE_SCHEMA_VERSION,
        "report_id": f"market-structure-{report_id}",
        "subject": subject,
        "as_of": input_report["as_of"],
        "price_series_id": str(input_report.get("price_series_id") or ""),
        "data_cutoff": input_report["as_of"],
        "adjustment": str(input_report.get("adjustment") or "NONE"),
        "continuous_series_rule": input_report.get("continuous_series_rule"),
        "timeframes": timeframes,
        "implementation": str(input_report.get("implementation") or IMPLEMENTATION),
        "implementation_version": str(
            input_report.get("implementation_version") or IMPLEMENTATION_VERSION
        ),
        "rule_version": rule_version,
        "confirmation": confirmation,
        "repaint_risk": repaint_risk,
        "bar_count": all_bars,
        "interpretation": _interpretation(timeframes, confirmation),
        "policy": {
            "market_structure_only": True,
            "read_only": True,
            "closed_bars_only": True,
            "future_bars_rejected": True,
            "trading_signal_included": False,
            "automatic_order_included": False,
            "investment_conclusion": False,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _normalise_subject(report: Mapping[str, Any]) -> dict[str, str]:
    subject_type = str(report.get("subject_type") or "").strip().lower()
    subject_id = str(report.get("subject_id") or report.get("ticker") or "").strip()
    if subject_type not in {"listed_company", "futures_contract", "continuous_series"}:
        raise MarketStructureError(
            "subject_type must be listed_company, futures_contract, or continuous_series"
        )
    if not subject_id:
        raise MarketStructureError("subject_id or ticker is required")
    if subject_type == "continuous_series" and not report.get("continuous_series_rule"):
        raise MarketStructureError(
            "continuous_series_rule is required for continuous_series"
        )
    return {
        "subject_type": subject_type,
        "subject_id": subject_id,
        "display_name": str(report.get("display_name") or ""),
    }


def _normalise_bars(
    raw_bars: Any,
    *,
    as_of: datetime,
    timeframe: str,
) -> list[dict[str, Any]]:
    if not isinstance(raw_bars, Sequence) or isinstance(
        raw_bars, (str, bytes, bytearray)
    ):
        raise MarketStructureError(f"bars must be a list: {timeframe}")
    bars: list[dict[str, Any]] = []
    seen: set[datetime] = set()
    previous: datetime | None = None
    for index, raw_bar in enumerate(raw_bars):
        if not isinstance(raw_bar, Mapping):
            raise MarketStructureError(f"bar {index} must be an object: {timeframe}")
        timestamp = _parse_datetime(
            raw_bar.get("timestamp", raw_bar.get("date")),
            f"{timeframe}[{index}].timestamp",
        )
        if timestamp > as_of:
            raise MarketStructureError(
                f"future bar exceeds as_of in timeframe {timeframe}: {timestamp.isoformat()}"
            )
        if timestamp in seen:
            raise MarketStructureError(
                f"duplicate bar timestamp in timeframe {timeframe}: {timestamp.isoformat()}"
            )
        if previous is not None and timestamp <= previous:
            raise MarketStructureError(
                f"bars must be strictly ascending in timeframe {timeframe}"
            )
        seen.add(timestamp)
        previous = timestamp
        values = {
            key: _number(raw_bar.get(key), f"{timeframe}[{index}].{key}")
            for key in ("open", "high", "low", "close", "volume")
        }
        if values["high"] < max(values["open"], values["close"]):
            raise MarketStructureError(f"high is below open/close: {timeframe}[{index}]")
        if values["low"] > min(values["open"], values["close"]):
            raise MarketStructureError(f"low is above open/close: {timeframe}[{index}]")
        if values["high"] < values["low"]:
            raise MarketStructureError(f"high is below low: {timeframe}[{index}]")
        bars.append({"timestamp": timestamp, **values})
    if not bars:
        raise MarketStructureError(f"timeframe has no bars: {timeframe}")
    return bars


def _analyse_timeframe(timeframe: str, bars: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    closes = [float(bar["close"]) for bar in bars]
    returns = [closes[index] / closes[index - 1] - 1 for index in range(1, len(closes))]
    volatility = _volatility(returns)
    position = _position(closes)
    if len(closes) < MIN_CONFIRMATION_BARS:
        state = "INSUFFICIENT_DATA"
        reversal_risk = "UNKNOWN"
    else:
        first = mean(closes[: max(5, len(closes) // 3)])
        last = mean(closes[-max(5, len(closes) // 3) :])
        slope = last / first - 1 if first else 0.0
        threshold = max(0.05, volatility["value"] * 2.5 if volatility["value"] is not None else 0.05)
        if slope >= threshold and closes[-1] >= mean(closes[-20:]):
            state = "UPTREND"
            reversal_risk = "MEDIUM" if position["state"] == "UPPER_HALF" else "LOW"
        elif slope <= -threshold and closes[-1] <= mean(closes[-20:]):
            state = "DOWNTREND"
            reversal_risk = "MEDIUM" if position["state"] == "LOWER_HALF" else "LOW"
        else:
            state = "RANGE"
            reversal_risk = "MEDIUM"
    return {
        "timeframe": timeframe,
        "bars": len(bars),
        "last_bar_as_of": bars[-1]["timestamp"].isoformat(),
        "last_close": closes[-1],
        "state": state,
        "volatility": volatility["state"],
        "volatility_value": volatility["value"],
        "position": position["state"],
        "position_ratio": position["ratio"],
        "reversal_risk": reversal_risk,
        "confirmation": (
            "CONFIRMED_UNTIL_AS_OF"
            if len(bars) >= MIN_CONFIRMATION_BARS
            else "UNCONFIRMED"
        ),
        "signal": None,
    }


def _volatility(returns: Sequence[float]) -> dict[str, Any]:
    if not returns:
        return {"state": "UNKNOWN", "value": None}
    value = sqrt(mean([(item - mean(returns)) ** 2 for item in returns]))
    if value < 0.01:
        state = "LOW"
    elif value < 0.03:
        state = "MEDIUM"
    else:
        state = "HIGH"
    return {"state": state, "value": round(value, 8)}


def _position(closes: Sequence[float]) -> dict[str, Any]:
    low = min(closes)
    high = max(closes)
    if high == low:
        return {"state": "MIDDLE", "ratio": 0.5}
    ratio = (closes[-1] - low) / (high - low)
    if ratio >= 2 / 3:
        state = "UPPER_HALF"
    elif ratio <= 1 / 3:
        state = "LOWER_HALF"
    else:
        state = "MIDDLE"
    return {"state": state, "ratio": round(ratio, 8)}


def _interpretation(timeframes: Mapping[str, Mapping[str, Any]], confirmation: str) -> str:
    states = [str(item["state"]) for item in timeframes.values()]
    if confirmation == "UNCONFIRMED":
        return "数据不足以确认全部周期结构；市场结构仅作时点辅助，不改变基本面结论。"
    if "DOWNTREND" in states:
        return "至少一个周期处于下行结构；市场结构仅影响模拟研究时点，不构成自动交易信号。"
    if "UPTREND" in states and all(state != "RANGE" for state in states):
        return "各已确认周期偏向上行；市场结构仅作时点辅助，不构成自动交易信号。"
    return "价格结构包含盘整或多周期差异；市场结构仅作时点辅助，不构成自动交易信号。"


def _parse_datetime(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise MarketStructureError(f"{field} is required")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise MarketStructureError(f"{field} must be ISO datetime/date") from error


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or value is None:
        raise MarketStructureError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise MarketStructureError(f"{field} must be numeric") from error
    if number != number or number in {float("inf"), float("-inf")}:
        raise MarketStructureError(f"{field} must be finite")
    return number


def _compact_datetime(value: datetime) -> str:
    return value.isoformat().replace(":", "").replace("+", "plus")
