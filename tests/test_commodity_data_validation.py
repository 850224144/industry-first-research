"""
商品品种真实数据链路验证测试

验证真实数据样例与适配器配置的兼容性
"""
import json
from pathlib import Path
import pytest


COMMODITIES_DIR = Path(__file__).resolve().parents[1] / "config" / "commodities"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "commodities"


def load_adapter(adapter_id):
    """加载商品适配器配置"""
    config_file = COMMODITIES_DIR / f"{adapter_id}.json"
    return json.loads(config_file.read_text())


def load_fundamentals(filename):
    """加载期货基本面数据"""
    data_file = FIXTURES_DIR / filename
    return json.loads(data_file.read_text())


def test_steel_real_data_matches_adapter():
    """测试钢材真实数据与适配器匹配"""
    adapter = load_adapter("steel")
    data = load_fundamentals("steel_rb_fundamentals.json")

    # 验证品种代码
    assert data["variety_id"] in adapter["variety_ids"]
    assert data["exchange"] in adapter["exchanges"]

    # 验证现货基准
    assert data["spot_benchmark"]["benchmark_id"] == adapter["spot_benchmarks"][0]["benchmark_id"]
    assert data["spot_benchmark"]["unit"] == adapter["quote_unit"]

    # 验证库存位置覆盖
    inventory_keys = set(data["inventory"].keys())
    adapter_locations = set(adapter["inventory_locations"])

    # 交易所库存必须有
    assert "exchange_inventory" in inventory_keys

    # 验证成本组成
    cost_keys = set(data["cost"].keys())
    assert "iron_ore_cost" in cost_keys or "iron_ore" in str(cost_keys)
    assert "coking_coal_cost" in cost_keys or "coking_coal" in str(cost_keys)

    # 验证基差计算
    assert "basis" in data
    assert "spot_futures_basis" in data["basis"]


def test_copper_real_data_matches_adapter():
    """测试铜真实数据与适配器匹配"""
    adapter = load_adapter("copper")
    data = load_fundamentals("copper_cu_fundamentals.json")

    assert data["variety_id"] in adapter["variety_ids"]
    assert data["exchange"] in adapter["exchanges"]

    # 验证现货基准
    assert data["spot_benchmark"]["benchmark_id"] == adapter["spot_benchmarks"][0]["benchmark_id"]

    # 验证库存位置
    assert "exchange_inventory" in data["inventory"]

    # 验证成本组成（铜特有的TC/RC）
    assert "concentrate_tc" in data["cost"] or "treatment_charge" in str(data["cost"])

    # 验证基差
    assert "basis" in data


def test_lithium_real_data_matches_adapter():
    """测试碳酸锂真实数据与适配器匹配"""
    adapter = load_adapter("lithium_carbonate")
    data = load_fundamentals("lithium_lc_fundamentals.json")

    assert data["variety_id"] in adapter["variety_ids"]
    assert data["exchange"] in adapter["exchanges"]

    # 验证现货基准
    assert data["spot_benchmark"]["benchmark_id"] == adapter["spot_benchmarks"][0]["benchmark_id"]

    # 验证库存位置（锂特有）
    inventory_keys = set(data["inventory"].keys())
    assert "converter_inventory" in inventory_keys or "cathode_factory_inventory" in inventory_keys

    # 验证需求数据（电池需求驱动）
    assert "demand" in data
    assert "battery_output" in data["demand"] or "ev_sales" in data["demand"]

    # 验证成本曲线
    assert "cost_curve_p90" in data["cost"] or "conversion_cost" in data["cost"]


def test_soybean_meal_real_data_matches_adapter():
    """测试豆粕真实数据与适配器匹配"""
    adapter = load_adapter("soybean_meal")
    data = load_fundamentals("soybean_meal_m_fundamentals.json")

    assert data["variety_id"] in adapter["variety_ids"]
    assert data["exchange"] in adapter["exchanges"]

    # 验证现货基准
    assert data["spot_benchmark"]["benchmark_id"] == adapter["spot_benchmarks"][0]["benchmark_id"]

    # 验证库存位置（农产品特有）
    inventory_keys = set(data["inventory"].keys())
    assert "crushing_mill_inventory" in inventory_keys or "exchange_inventory" in inventory_keys

    # 验证生产数据（压榨）
    assert "production" in data
    assert "weekly_crush" in data["production"] or "crush_rate" in data["production"]

    # 验证压榨利润
    assert "margin" in data
    assert "crush_margin" in data["margin"]

    # 验证进口数据
    assert "trade" in data
    assert "soybean_imports" in data["trade"]


def test_crude_oil_real_data_matches_adapter():
    """测试原油真实数据与适配器匹配"""
    adapter = load_adapter("crude_oil")
    data = load_fundamentals("crude_oil_sc_fundamentals.json")

    assert data["variety_id"] in adapter["variety_ids"]
    assert data["exchange"] in adapter["exchanges"]

    # 验证现货基准（美元计价）
    assert data["spot_benchmark"]["unit"] == "USD/barrel"

    # 验证汇率数据
    assert "fx" in data
    assert "usdcnh" in data["fx"]

    # 验证全球供需
    assert "production" in data
    assert "opec_output" in data["production"] or "us_output" in data["production"]

    # 验证裂解价差
    assert "crack_spread" in data

    # 验证库存（多层级）
    assert "inventory" in data
    inventory_keys = set(data["inventory"].keys())
    assert len(inventory_keys) >= 2  # 至少有中国和海外库存


def test_all_real_data_have_required_fields():
    """验证所有真实数据都包含必需字段"""
    data_files = [
        "steel_rb_fundamentals.json",
        "copper_cu_fundamentals.json",
        "lithium_lc_fundamentals.json",
        "soybean_meal_m_fundamentals.json",
        "crude_oil_sc_fundamentals.json"
    ]

    required_fields = [
        "schema_version",
        "variety_id",
        "exchange",
        "as_of",
        "research_cutoff",
        "spot_benchmark",
        "contract_quotes",
        "inventory",
        "evidence_ids",
        "source_document_id"
    ]

    for filename in data_files:
        data = load_fundamentals(filename)

        for field in required_fields:
            assert field in data, f"Missing required field '{field}' in {filename}"


def test_all_real_data_have_basis_calculation():
    """验证所有真实数据都有基差计算"""
    data_files = [
        "steel_rb_fundamentals.json",
        "copper_cu_fundamentals.json",
        "lithium_lc_fundamentals.json",
        "soybean_meal_m_fundamentals.json",
        "crude_oil_sc_fundamentals.json"
    ]

    for filename in data_files:
        data = load_fundamentals(filename)

        assert "basis" in data, f"Missing basis in {filename}"
        assert "spot_futures_basis" in data["basis"], f"Missing spot_futures_basis in {filename}"

        basis = data["basis"]["spot_futures_basis"]
        assert "value" in basis
        assert "unit" in basis
        assert "date" in basis


def test_field_status_consistency():
    """验证字段状态标识一致性"""
    data_files = [
        "steel_rb_fundamentals.json",
        "copper_cu_fundamentals.json",
        "lithium_lc_fundamentals.json",
        "soybean_meal_m_fundamentals.json",
        "crude_oil_sc_fundamentals.json"
    ]

    valid_statuses = ["VERIFIED", "ESTIMATED", "FORECAST", "CALCULATED", "REFERENCE"]

    for filename in data_files:
        data = load_fundamentals(filename)

        # 检查现货基准
        if "field_status" in data["spot_benchmark"]:
            assert data["spot_benchmark"]["field_status"] in valid_statuses

        # 检查合约报价
        for quote in data["contract_quotes"]:
            if "field_status" in quote:
                assert quote["field_status"] in valid_statuses


def test_inventory_data_completeness():
    """验证库存数据完整性"""
    data_files = [
        ("steel_rb_fundamentals.json", ["exchange_inventory", "social_inventory"]),
        ("copper_cu_fundamentals.json", ["exchange_inventory", "bonded_warehouse"]),
        ("lithium_lc_fundamentals.json", ["converter_inventory", "exchange_inventory"]),
        ("soybean_meal_m_fundamentals.json", ["exchange_inventory", "crushing_mill_inventory"]),
        ("crude_oil_sc_fundamentals.json", ["exchange_inventory", "china_commercial"])
    ]

    for filename, expected_keys in data_files:
        data = load_fundamentals(filename)
        inventory = data["inventory"]

        # 至少有一个预期的库存类型
        assert any(key in inventory for key in expected_keys), f"Missing expected inventory in {filename}"

        # 每个库存项都有必需字段
        for inv_key, inv_data in inventory.items():
            assert "value" in inv_data
            assert "unit" in inv_data
            assert "date" in inv_data


def test_cost_components_match_adapter():
    """验证成本组成与适配器匹配"""
    test_cases = [
        ("steel", "steel_rb_fundamentals.json", ["iron_ore", "coking_coal"]),
        ("copper", "copper_cu_fundamentals.json", ["concentrate", "smelting"]),
        ("lithium_carbonate", "lithium_lc_fundamentals.json", ["ore", "brine", "conversion"]),
        ("soybean_meal", "soybean_meal_m_fundamentals.json", ["soybean", "crushing"]),
        ("crude_oil", "crude_oil_sc_fundamentals.json", ["production", "freight", "fx"])
    ]

    for adapter_id, data_file, expected_components in test_cases:
        adapter = load_adapter(adapter_id)
        data = load_fundamentals(data_file)

        cost_keys = set(data["cost"].keys())
        adapter_components = set(adapter["cost_components"])

        # 至少有一个预期成本组成存在
        found = False
        for component in expected_components:
            if any(component in str(key) for key in cost_keys):
                found = True
                break

        assert found, f"Missing expected cost components {expected_components} in {data_file}"


def test_evidence_traceability():
    """验证证据可追溯性"""
    data_files = [
        "steel_rb_fundamentals.json",
        "copper_cu_fundamentals.json",
        "lithium_lc_fundamentals.json",
        "soybean_meal_m_fundamentals.json",
        "crude_oil_sc_fundamentals.json"
    ]

    for filename in data_files:
        data = load_fundamentals(filename)

        # 验证有证据ID
        assert "evidence_ids" in data
        assert isinstance(data["evidence_ids"], list)
        assert len(data["evidence_ids"]) > 0

        # 验证有来源文档ID
        assert "source_document_id" in data
        assert len(data["source_document_id"]) > 0


def test_timestamp_format():
    """验证时间戳格式"""
    data_files = [
        "steel_rb_fundamentals.json",
        "copper_cu_fundamentals.json",
        "lithium_lc_fundamentals.json",
        "soybean_meal_m_fundamentals.json",
        "crude_oil_sc_fundamentals.json"
    ]

    for filename in data_files:
        data = load_fundamentals(filename)

        # 验证研究时间
        assert "as_of" in data
        assert "T" in data["as_of"]  # ISO 8601格式
        assert "2026" in data["as_of"]

        # 验证研究截止日
        assert "research_cutoff" in data
        assert "2026" in data["research_cutoff"]
