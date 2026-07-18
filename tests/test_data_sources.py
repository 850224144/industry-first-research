from types import SimpleNamespace

import pytest

from industry_first_research.data_sources import (
    AkshareDataSourceAdapter,
    BaoStockDataSourceAdapter,
    FreeDataSourcePolicy,
)


def test_free_data_policy_has_no_broker_terminal_dependency():
    policy = FreeDataSourcePolicy()
    policy.validate()
    assert policy.sources_for("listed_company")[0] == "akshare"
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
