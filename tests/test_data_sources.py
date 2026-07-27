import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from industry_first_research.data_sources import (
    AkshareDataSourceAdapter,
    BaoStockDataSourceAdapter,
    DataSourceExhaustedError,
    DataSourceRouter,
    EastmoneyDataSourceAdapter,
    FreeDataSourcePolicy,
    PublicHttpDataSourceAdapter,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "data_sources"


def fixture_json(name):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


class FixtureResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.headers = {"Content-Type": "application/json"}

    def read(self):
        return self._payload

    def close(self):
        pass


def test_free_data_policy_has_no_broker_terminal_dependency():
    policy = FreeDataSourcePolicy()
    policy.validate()
    assert policy.sources_for("listed_company") == (
        "official_exchange",
        "company_disclosure",
        "eastmoney",
        "akshare",
        "baostock",
    )
    assert policy.sources_for("futures_contract")[0] == "official_exchange"
    assert "qmt" not in policy.sources_for("listed_company")


def test_free_data_policy_rejects_qmt_if_explicitly_added():
    with pytest.raises(ValueError, match="QMT"):
        FreeDataSourcePolicy(listed_company_sources=("qmt",)).validate()


def test_akshare_adapter_preserves_endpoint_and_time_lineage():
    module = SimpleNamespace(
        __version__="test-version",
        stock_test=lambda **kwargs: [{"code": kwargs["code"], "close": 10}],
    )
    adapter = AkshareDataSourceAdapter(module)
    health = adapter.health_check()
    payload = adapter.fetch(
        {"endpoint": "stock_test", "params": {"code": "600438"}},
        "2026-07-18",
    )
    assert health.available is True
    assert health.version == "test-version"
    assert payload["endpoint"] == "stock_test"
    assert payload["as_of"] == "2026-07-18"
    assert payload["data"] == [{"code": "600438", "close": 10}]


def test_fixed_public_source_fixtures_match_exchange_and_eastmoney_shapes():
    official = PublicHttpDataSourceAdapter(
        "official_exchange",
        ("exchange_disclosure",),
        lambda _request, timeout: FixtureResponse(
            fixture_json("official_exchange_disclosure.json")
        ),
    )
    eastmoney = EastmoneyDataSourceAdapter(
        lambda _request, timeout: FixtureResponse(fixture_json("eastmoney_quote.json"))
    )

    official_payload = official.fetch(
        {"url": "https://fixture.test/official"}, "2026-07-25"
    )
    eastmoney_payload = eastmoney.fetch(
        {"url": "https://fixture.test/eastmoney"}, "2026-07-25"
    )

    assert official_payload["data"]["data"]["symbol"] == "600438.SH"
    assert eastmoney_payload["data"]["data"]["diff"][0]["f12"] == "600438"


def test_fixed_optional_source_fixtures_match_akshare_and_baostock_shapes():
    akshare_module = SimpleNamespace(
        __version__="fixture-akshare",
        stock_zh_a_hist=lambda **_kwargs: fixture_json("akshare_history.json"),
    )
    akshare = AkshareDataSourceAdapter(akshare_module)
    akshare_payload = akshare.fetch(
        {"endpoint": "stock_zh_a_hist", "params": {"symbol": "600438"}},
        "2026-07-25",
    )

    class Session:
        error_code = "0"
        error_msg = ""

    class BaoStockFixture:
        __version__ = "fixture-baostock"

        def login(self):
            return Session()

        def query_history_k_data_plus(self, *_args, **_kwargs):
            return fixture_json("baostock_history.json")

        def logout(self):
            pass

    baostock = BaoStockDataSourceAdapter(BaoStockFixture())
    baostock_payload = baostock.fetch(
        {"query_type": "history", "code": "sh.600438"}, "2026-07-25"
    )

    assert akshare_payload["data"][0]["股票代码"] == "600438"
    assert baostock_payload["data"][1]["close"] == "21.55"


def test_baostock_adapter_health_check_is_lazy():
    adapter = BaoStockDataSourceAdapter(SimpleNamespace(__version__="test-version"))
    health = adapter.health_check()
    assert health.available is True
    assert health.capabilities == ("cn_stock_history",)


def test_eastmoney_adapter_preserves_url_and_payload():
    class Response:
        def read(self):
            return b'{"data": {"diff": [{"f57": "600438"}]}}'

        def close(self):
            pass

    seen = {}

    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return Response()

    adapter = EastmoneyDataSourceAdapter(opener)
    payload = adapter.fetch(
        {
            "url": "https://example.test/api",
            "params": {"secid": "1.600438"},
            "timeout": 3,
        },
        "2026-07-18",
    )
    assert "secid=1.600438" in seen["url"]
    assert seen["timeout"] == 3
    assert payload["data"]["data"]["diff"][0]["f57"] == "600438"


def test_public_http_adapter_can_fetch_official_text_payload():
    class Response:
        headers = {"Content-Type": "text/plain"}

        def read(self):
            return b"official disclosure"

        def close(self):
            pass

    adapter = PublicHttpDataSourceAdapter(
        "official_exchange", ("exchange_disclosure",), lambda request, timeout: Response()
    )
    payload = adapter.fetch({"url": "https://example.test/disclosure"}, "2026-07-18")
    assert payload["source"] == "official_exchange"
    assert payload["data"] == "official disclosure"


def test_router_falls_back_and_records_failed_source():
    class FakeAdapter:
        def __init__(self, name, result=None, error=None):
            self.name = name
            self.result = result
            self.error = error

        def health_check(self):
            from industry_first_research.data_sources import DataSourceHealth

            return DataSourceHealth(self.name, "test", True)

        def fetch(self, query, as_of):
            if self.error:
                raise self.error
            return {"source": self.name, "data": self.result, "as_of": as_of}

        def normalize(self, value):
            return value

    router = DataSourceRouter(
        [
            FakeAdapter("exchange", error=TimeoutError("timeout")),
            FakeAdapter("eastmoney", result=[{"close": 10}]),
        ],
        FreeDataSourcePolicy(listed_company_sources=("exchange", "eastmoney")),
    )
    result = router.fetch({}, "2026-07-18", subject_type="listed_company")
    assert result.source == "eastmoney"
    assert [attempt.status for attempt in result.attempts] == ["FAILED", "SUCCESS"]
    assert result.attempts[0].reason.startswith("TimeoutError")


def test_router_falls_back_when_required_field_is_missing():
    class FakeAdapter:
        def __init__(self, name, payload):
            self.name = name
            self.payload = payload

        def health_check(self):
            from industry_first_research.data_sources import DataSourceHealth

            return DataSourceHealth(self.name, "test", True)

        def fetch(self, query, as_of):
            return self.payload

        def normalize(self, value):
            return value

    router = DataSourceRouter(
        [
            FakeAdapter("eastmoney", {"data": [{"close": 10}]}),
            FakeAdapter("akshare", {"data": [{"close": 10, "volume": 20}]}),
        ],
        FreeDataSourcePolicy(listed_company_sources=("eastmoney", "akshare")),
    )
    result = router.fetch(
        {"required_fields": ("volume",)},
        "2026-07-18",
        subject_type="listed_company",
    )
    assert result.source == "akshare"
    assert result.attempts[0].status == "FAILED"
    assert "volume" in result.attempts[0].reason


def test_router_raises_only_after_all_sources_fail():
    class BrokenAdapter:
        name = "broken"

        def health_check(self):
            from industry_first_research.data_sources import DataSourceHealth

            return DataSourceHealth("broken", "test", False, reason="offline")

        def fetch(self, query, as_of):
            raise AssertionError("unavailable source must not be fetched")

        def normalize(self, value):
            return value

    router = DataSourceRouter(
        [BrokenAdapter()],
        FreeDataSourcePolicy(listed_company_sources=("broken",)),
    )
    with pytest.raises(DataSourceExhaustedError) as error:
        router.fetch({}, "2026-07-18", subject_type="listed_company")
    assert error.value.attempts[0].status == "SKIPPED"


def test_router_captures_noisy_adapter_output_without_leaking_to_caller(capsys):
    class NoisyAdapter:
        name = "akshare"

        def health_check(self):
            print("health diagnostic")
            return SimpleNamespace(
                name=self.name,
                source_type="test",
                available=False,
                capabilities=(),
                reason="offline",
                version="test",
            )

        def fetch(self, query, as_of):
            raise AssertionError("unavailable source must not be fetched")

        def normalize(self, value):
            return value

    router = DataSourceRouter(
        [NoisyAdapter()],
        FreeDataSourcePolicy(listed_company_sources=("akshare",)),
    )
    with pytest.raises(DataSourceExhaustedError):
        router.fetch({}, "2026-07-18", subject_type="listed_company")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_router_health_check_exception_is_recorded_as_unavailable():
    class BrokenHealthAdapter:
        name = "broken-health"
        source_type = "test"

        def health_check(self):
            raise RuntimeError("health endpoint crashed")

    router = DataSourceRouter([BrokenHealthAdapter()])
    health = router.health()
    assert health[0].available is False
    assert "health check failed" in health[0].reason
