from industry_first_research.cross_validation import CrossSourceIndustryRadar
from industry_first_research.models import IndustryRadarSnapshot, IndustrySignal, IndustryState


class StaticRadar:
    def __init__(self, items, provider):
        self.items = items
        self.provider = provider

    def snapshots(self, as_of):
        return self.items

    def metadata(self, as_of):
        return {"provider": self.provider, "as_of": as_of, "read_only": True}


def item(code, name, state, source):
    return IndustryRadarSnapshot(
        industry_id=code,
        display_name=name,
        as_of="2026-07-19",
        state=state,
        signals=(IndustrySignal("change_pct", 1.0, "2026-07-19", source, "VERIFIED"),),
        evidence_completeness="SINGLE_SOURCE",
        opportunity_types=("market_strength_signal",),
    )


def test_same_direction_is_cross_validated():
    radar = CrossSourceIndustryRadar(
        StaticRadar([item("BK1", "\u7535\u529b\u884c\u4e1a", IndustryState.CLEARING, "eastmoney")], "eastmoney"),
        StaticRadar([item("881145", "电力", IndustryState.CLEARING, "https://q.10jqka.com.cn")], "tonghuashun"),
    )

    result = list(radar.snapshots("2026-07-19"))[0]

    assert result.state == IndustryState.CLEARING
    assert result.evidence_completeness == "CROSS_VALIDATED"
    assert len(result.signals) == 2
    assert radar.metadata("2026-07-19")["matched_row_count"] == 1


def test_conflicting_direction_is_held_out():
    radar = CrossSourceIndustryRadar(
        StaticRadar([item("BK1", "电力", IndustryState.CLEARING, "eastmoney")], "eastmoney"),
        StaticRadar([item("881145", "电力", IndustryState.DETERIORATING, "https://q.10jqka.com.cn")], "tonghuashun"),
    )

    result = list(radar.snapshots("2026-07-19"))[0]

    assert result.state == IndustryState.INSUFFICIENT
    assert result.evidence_completeness == "CONFLICTING"
    assert result.opportunity_types == ()


def test_missing_match_is_single_source_and_held_out():
    radar = CrossSourceIndustryRadar(
        StaticRadar([item("BK1", "电力", IndustryState.CLEARING, "eastmoney")], "eastmoney"),
        StaticRadar([item("881145", "银行", IndustryState.CLEARING, "https://q.10jqka.com.cn")], "tonghuashun"),
    )

    result = list(radar.snapshots("2026-07-19"))[0]

    assert result.state == IndustryState.INSUFFICIENT
    assert result.evidence_completeness == "SINGLE_SOURCE"
    assert result.opportunity_types == ()
