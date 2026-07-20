import json

import pytest

from industry_first_research.eastmoney import EastmoneyAPIError, EastmoneyIndustryRadar
from industry_first_research.models import IndustryState


def response_payload() -> bytes:
    return json.dumps(
        {
            "rc": 0,
            "data": {
                "total": 496,
                "diff": [
                    {
                        "f2": 1067.55,
                        "f3": 3.88,
                        "f6": 123456.0,
                        "f12": "BK1565",
                        "f14": "Example Industry",
                        "f62": 37973169.0,
                        "f104": 8,
                        "f105": 2,
                        "f106": 0,
                    },
                    {
                        "f2": 100.0,
                        "f3": -1.2,
                        "f6": 456.0,
                        "f12": "BK0001",
                        "f14": "Weak Industry",
                        "f62": -1000.0,
                        "f104": 2,
                        "f105": 8,
                        "f106": 1,
                    },
                ],
            },
        }
    ).encode()


def test_eastmoney_rows_become_traceable_industry_snapshots():
    radar = EastmoneyIndustryRadar(page_size=2, fetcher=lambda url: response_payload())

    items = list(radar.snapshots("2026-07-19"))

    assert [item.industry_id for item in items] == ["BK1565", "BK0001"]
    assert items[0].state == IndustryState.CLEARING
    assert items[1].state == IndustryState.DETERIORATING
    assert items[0].evidence_completeness == "SINGLE_SOURCE"
    assert items[0].signals[0].value == 3.88
    assert items[0].signals[0].source.startswith("https://push2.eastmoney.com/")
    assert radar.metadata("2026-07-19")["market_total_rows"] == 496


def test_eastmoney_url_is_bounded_to_industry_rows():
    radar = EastmoneyIndustryRadar(page_size=7)

    url = radar.build_url()

    assert "pz=7" in url
    assert "fs=m:90+t:2" in url
    assert "fields=f12,f14,f2,f3,f5,f6,f62,f104,f105,f106" in url


def test_eastmoney_rejects_empty_or_failed_responses():
    failed = EastmoneyIndustryRadar(fetcher=lambda url: b'{"rc":-1}')
    empty = EastmoneyIndustryRadar(fetcher=lambda url: b'{"rc":0,"data":{"diff":[]}}')

    with pytest.raises(EastmoneyAPIError):
        list(failed.snapshots("2026-07-19"))
    with pytest.raises(EastmoneyAPIError):
        list(empty.snapshots("2026-07-19"))
