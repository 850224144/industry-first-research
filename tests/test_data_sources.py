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
