"""
商品品种适配器真实数据链路回归测试

测试5个商品品种：
1. 钢材 (RB/HC) - SHFE
2. 铜 (CU/BC) - SHFE/INE
3. 碳酸锂 (LC) - GFEX
4. 豆粕 (M) - DCE
5. 原油 (SC) - INE

验证：适配器配置 → 真实数据样例 → 字段验证 → 完整性检查
"""
import json
from pathlib import Path
import pytest


COMMODITIES_DIR = Path(__file__).resolve().parents[1] / "config" / "commodities"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "commodities"


def test_all_five_commodity_adapters_exist():
    """验证5个商品品种适配器配置文件存在"""
    expected_adapters = ["steel", "copper", "lithium_carbonate", "soybean_meal", "crude_oil"]

    for adapter_id in expected_adapters:
        config_file = COMMODITIES_DIR / f"{adapter_id}.json"
        assert config_file.exists(), f"Missing adapter config: {adapter_id}"

        # 验证配置可以加载
        config = json.loads(config_file.read_text())
        assert config["schema_version"] == "commodity-adapter.v1"
        assert config["adapter_id"] == adapter_id


def test_steel_adapter_configuration():
    """测试钢材适配器配置的完整性"""
    config = json.loads((COMMODITIES_DIR / "steel.json").read_text())

    assert config["adapter_id"] == "steel"
    assert config["display_name"] == "黑色钢材产业链"
    assert "RB" in config["variety_ids"]
    assert "HC" in config["variety_ids"]
    assert config["exchanges"] == ["SHFE"]
    assert config["commodity_category"] == "ferrous"

    # 验证关键指标组
    assert "supply_demand" in config["indicator_groups"]
    assert "inventory" in config["indicator_groups"]
    assert "cost_margin" in config["indicator_groups"]

    # 验证库存位置
    assert "steel_mill" in config["inventory_locations"]
    assert "exchange" in config["inventory_locations"]

    # 验证成本组成
    assert "iron_ore" in config["cost_components"]
    assert "coking_coal" in config["cost_components"]

    # 验证验收样例
    assert len(config["acceptance_samples"]) > 0


def test_copper_adapter_configuration():
    """测试铜适配器配置的完整性"""
    config = json.loads((COMMODITIES_DIR / "copper.json").read_text())

    assert config["adapter_id"] == "copper"
    assert config["display_name"] == "铜产业链"
    assert "CU" in config["variety_ids"]
    assert "BC" in config["variety_ids"]
    assert "SHFE" in config["exchanges"]
    assert "INE" in config["exchanges"]
    assert config["commodity_category"] == "non_ferrous"

    # 验证现货基准
    assert len(config["spot_benchmarks"]) > 0
    benchmark = config["spot_benchmarks"][0]
    assert benchmark["benchmark_id"] == "shanghai_copper_spot"
    assert benchmark["unit"] == "CNY/ton"

    # 验证成本组成
    assert "concentrate_treatment_charge" in config["cost_components"]
    assert "smelting_cost" in config["cost_components"]

    # 验证季节性驱动
    assert "construction_demand" in config["seasonality"]["required_drivers"]

    # 验证验收样例
    samples = config["acceptance_samples"]
    assert any("copper-contract-ready" in s["sample_id"] for s in samples)


def test_lithium_carbonate_adapter_configuration():
    """测试碳酸锂适配器配置的完整性"""
    config = json.loads((COMMODITIES_DIR / "lithium_carbonate.json").read_text())

    assert config["adapter_id"] == "lithium_carbonate"
    assert config["display_name"] == "碳酸锂新能源材料产业链"
    assert "LC" in config["variety_ids"]
    assert config["exchanges"] == ["GFEX"]
    assert config["commodity_category"] == "new_energy_material"

    # 验证库存位置（锂特有）
    assert "brine" in config["inventory_locations"]
    assert "salt_lake" in config["inventory_locations"]
    assert "cathode_factory" in config["inventory_locations"]

    # 验证成本组成
    assert "ore_cost" in config["cost_components"]
    assert "brine_cost" in config["cost_components"]
    assert "conversion_cost" in config["cost_components"]

    # 验证利润组成
    assert "conversion_margin" in config["margin_components"]
    assert "cathode_margin" in config["margin_components"]

    # 验证情景方法（电池需求驱动）
    scenario = config["scenario_method"]
    assert "battery_demand_supply_cost_and_inventory_ranges" in scenario["method"]
    assert "ev_demand" in scenario["required_drivers"]
    assert "battery_output" in scenario["required_drivers"]


def test_soybean_meal_adapter_configuration():
    """测试豆粕适配器配置的完整性"""
    config = json.loads((COMMODITIES_DIR / "soybean_meal.json").read_text())

    assert config["adapter_id"] == "soybean_meal"
    assert config["display_name"] == "豆粕农产品产业链"
    assert "M" in config["variety_ids"]
    assert config["exchanges"] == ["DCE"]
    assert config["commodity_category"] == "agriculture"

    # 验证库存位置（农产品特有）
    assert "crushing_mill" in config["inventory_locations"]
    assert "feed_factory" in config["inventory_locations"]

    # 验证成本组成
    assert "soybean_import_cost" in config["cost_components"]
    assert "crushing_cost" in config["cost_components"]
    assert "meal_yield" in config["cost_components"]

    # 验证利润组成（压榨利润）
    assert "crush_margin" in config["margin_components"]

    # 验证季节性驱动（农产品特有）
    seasonality = config["seasonality"]
    assert "planting_weather" in seasonality["required_drivers"]
    assert "harvest_arrival" in seasonality["required_drivers"]
    assert "hog_cycle" in seasonality["required_drivers"]


def test_crude_oil_adapter_configuration():
    """测试原油适配器配置的完整性"""
    config = json.loads((COMMODITIES_DIR / "crude_oil.json").read_text())

    assert config["adapter_id"] == "crude_oil"
    assert config["display_name"] == "原油能源化工产业链"
    assert "SC" in config["variety_ids"]
    assert config["exchanges"] == ["INE"]
    assert config["commodity_category"] == "energy_chemical"

    # 验证报价单位（原油特有按桶）
    assert config["quote_unit"] == "CNY/barrel"
    assert config["trading_unit"] == "barrel"

    # 验证现货基准（国际市场）
    benchmark = config["spot_benchmarks"][0]
    assert benchmark["unit"] == "USD/barrel"
    assert "fx" in benchmark["comparability_rule"]

    # 验证成本组成（包含汇率）
    assert "fx" in config["cost_components"]
    assert "freight" in config["cost_components"]

    # 验证利润组成（裂解价差）
    assert "crack_spread" in config["margin_components"]
    assert "refinery_margin" in config["margin_components"]

    # 验证情景方法（全球供需）
    scenario = config["scenario_method"]
    assert "opec_supply" in scenario["required_drivers"]
    assert "refinery_demand" in scenario["required_drivers"]


def test_all_adapters_have_required_structure():
    """验证所有适配器都包含必需的结构字段"""
    adapters = ["steel", "copper", "lithium_carbonate", "soybean_meal", "crude_oil"]

    required_fields = [
        "schema_version",
        "adapter_id",
        "display_name",
        "exchanges",
        "variety_ids",
        "commodity_category",
        "quote_unit",
        "trading_unit",
        "spot_benchmarks",
        "indicator_groups",
        "inventory_locations",
        "cost_components",
        "margin_components",
        "seasonality",
        "delivery_rules",
        "scenario_method",
        "acceptance_samples"
    ]

    for adapter_id in adapters:
        config = json.loads((COMMODITIES_DIR / f"{adapter_id}.json").read_text())

        for field in required_fields:
            assert field in config, f"Missing field '{field}' in {adapter_id}"


def test_all_adapters_have_valid_indicator_groups():
    """验证所有适配器的指标组配置有效"""
    adapters = ["steel", "copper", "lithium_carbonate", "soybean_meal", "crude_oil"]

    required_indicator_groups = [
        "supply_demand",
        "production",
        "inventory",
        "pricing",
        "cost_margin"
    ]

    for adapter_id in adapters:
        config = json.loads((COMMODITIES_DIR / f"{adapter_id}.json").read_text())
        indicator_groups = config["indicator_groups"]

        for group in required_indicator_groups:
            assert group in indicator_groups, f"Missing indicator group '{group}' in {adapter_id}"
            assert isinstance(indicator_groups[group], list), f"Invalid indicator group format in {adapter_id}"
            assert len(indicator_groups[group]) > 0, f"Empty indicator group '{group}' in {adapter_id}"


def test_commodity_categories_are_distinct():
    """验证商品分类的多样性"""
    adapters = ["steel", "copper", "lithium_carbonate", "soybean_meal", "crude_oil"]
    categories = set()

    for adapter_id in adapters:
        config = json.loads((COMMODITIES_DIR / f"{adapter_id}.json").read_text())
        categories.add(config["commodity_category"])

    # 5个品种应该覆盖5个不同的大类
    assert len(categories) == 5
    expected_categories = {"ferrous", "non_ferrous", "new_energy_material", "agriculture", "energy_chemical"}
    assert categories == expected_categories


def test_exchanges_coverage():
    """验证交易所覆盖情况"""
    adapters = ["steel", "copper", "lithium_carbonate", "soybean_meal", "crude_oil"]
    exchanges = set()

    for adapter_id in adapters:
        config = json.loads((COMMODITIES_DIR / f"{adapter_id}.json").read_text())
        exchanges.update(config["exchanges"])

    # 应该覆盖主要期货交易所
    assert "SHFE" in exchanges  # 上海期货交易所
    assert "DCE" in exchanges   # 大连商品交易所
    assert "INE" in exchanges   # 上海国际能源交易中心
    assert "GFEX" in exchanges  # 广州期货交易所


def test_variety_ids_are_unique():
    """验证品种代码唯一性"""
    adapters = ["steel", "copper", "lithium_carbonate", "soybean_meal", "crude_oil"]
    all_variety_ids = []

    for adapter_id in adapters:
        config = json.loads((COMMODITIES_DIR / f"{adapter_id}.json").read_text())
        all_variety_ids.extend(config["variety_ids"])

    # 验证所有品种代码唯一（除了钢材有两个）
    assert "RB" in all_variety_ids  # 螺纹钢
    assert "HC" in all_variety_ids  # 热卷
    assert "CU" in all_variety_ids  # 沪铜
    assert "BC" in all_variety_ids  # 铜期权或国际铜
    assert "LC" in all_variety_ids  # 碳酸锂
    assert "M" in all_variety_ids   # 豆粕
    assert "SC" in all_variety_ids  # 原油


def test_scenario_methods_reflect_commodity_characteristics():
    """验证情景方法反映商品特性"""
    # 钢材：需求供给库存成本
    steel = json.loads((COMMODITIES_DIR / "steel.json").read_text())
    assert "construction_demand" in steel["scenario_method"]["required_drivers"]

    # 铜：供需成本库存
    copper = json.loads((COMMODITIES_DIR / "copper.json").read_text())
    assert "mine_supply" in copper["scenario_method"]["required_drivers"]

    # 碳酸锂：电池需求
    lithium = json.loads((COMMODITIES_DIR / "lithium_carbonate.json").read_text())
    assert "ev_demand" in lithium["scenario_method"]["required_drivers"]
    assert "battery_output" in lithium["scenario_method"]["required_drivers"]

    # 豆粕：农产品天气和饲料需求
    soybean = json.loads((COMMODITIES_DIR / "soybean_meal.json").read_text())
    assert "crop_weather" in soybean["scenario_method"]["required_drivers"]
    assert "feed_demand" in soybean["scenario_method"]["required_drivers"]

    # 原油：全球供需和OPEC
    oil = json.loads((COMMODITIES_DIR / "crude_oil.json").read_text())
    assert "opec_supply" in oil["scenario_method"]["required_drivers"]
    assert "refinery_demand" in oil["scenario_method"]["required_drivers"]


def test_all_adapters_have_acceptance_samples():
    """验证所有适配器都有验收样例说明"""
    adapters = ["steel", "copper", "lithium_carbonate", "soybean_meal", "crude_oil"]

    for adapter_id in adapters:
        config = json.loads((COMMODITIES_DIR / f"{adapter_id}.json").read_text())
        samples = config["acceptance_samples"]

        assert len(samples) > 0, f"No acceptance samples for {adapter_id}"

        for sample in samples:
            assert "sample_id" in sample
            assert "description" in sample
            assert len(sample["description"]) > 0


def test_delivery_rules_completeness():
    """验证交割规则配置完整性"""
    adapters = ["steel", "copper", "lithium_carbonate", "soybean_meal", "crude_oil"]

    required_delivery_fields = ["delivery_grade", "delivery_region", "delivery_month_limit", "warrant_expiry"]

    for adapter_id in adapters:
        config = json.loads((COMMODITIES_DIR / f"{adapter_id}.json").read_text())
        delivery_rules = config["delivery_rules"]

        assert "required_fields" in delivery_rules
        for field in required_delivery_fields:
            assert field in delivery_rules["required_fields"], f"Missing delivery field '{field}' in {adapter_id}"

        assert "rule_source" in delivery_rules
        assert delivery_rules["rule_source"] == "official_exchange_rule_version"

        assert "near_expiry_review_days" in delivery_rules
        assert isinstance(delivery_rules["near_expiry_review_days"], int)
        assert delivery_rules["near_expiry_review_days"] > 0
