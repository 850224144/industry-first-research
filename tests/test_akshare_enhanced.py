from types import SimpleNamespace

import pandas as pd

import research_system.akshare_enhanced as enhanced_module
from research_system.akshare_enhanced import AKShareEnhanced


def test_get_all_industries_uses_distinct_cninfo_standards(monkeypatch, tmp_path):
    requested = []

    fake = SimpleNamespace(
        stock_board_industry_name_em=lambda: pd.DataFrame([{"板块名称": "光伏设备"}]),
        stock_industry_category_cninfo=lambda symbol: (
            requested.append(symbol) or pd.DataFrame([{"类目名称": symbol}])
        ),
        stock_board_concept_name_em=lambda: pd.DataFrame([{"板块名称": "储能"}]),
    )
    monkeypatch.setattr(enhanced_module, "ak", fake)

    result = AKShareEnhanced(tmp_path).get_all_industries()

    assert requested == [
        "证监会行业分类标准",
        "巨潮行业分类标准",
        "申银万国行业分类标准",
    ]
    assert set(result) == {"eastmoney", "csrc", "cninfo", "shenwan", "concept"}


def test_membership_index_fetches_each_industry_once(monkeypatch, tmp_path):
    calls = []

    def constituents(symbol):
        calls.append(symbol)
        if symbol == "光伏设备":
            return pd.DataFrame({"代码": [600438.0, "601012.SH"]})
        return pd.DataFrame({"代码": [1]})

    monkeypatch.setattr(
        enhanced_module,
        "ak",
        SimpleNamespace(stock_board_industry_cons_em=constituents),
    )
    industries = pd.DataFrame({"板块名称": ["光伏设备", "电池"]})

    membership = AKShareEnhanced(tmp_path)._build_industry_membership_index(industries)

    assert calls == ["光伏设备", "电池"]
    assert membership == {
        "600438": "光伏设备",
        "601012": "光伏设备",
        "000001": "电池",
    }


def test_stock_code_normalization_handles_exchange_prefixes_and_suffixes(tmp_path):
    enhancer = AKShareEnhanced(tmp_path)

    assert enhancer._normalize_stock_code("SH.600438") == "600438"
    assert enhancer._normalize_stock_code("000001.SZ") == "000001"
    assert enhancer._normalize_stock_code(1) == "000001"
    assert enhancer._normalize_stock_code(600438.0) == "600438"
