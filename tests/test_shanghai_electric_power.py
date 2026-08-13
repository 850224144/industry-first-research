"""Test Shanghai Electric Power (600021) research pipeline."""

import json
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = PROJECT_ROOT / "tests/fixtures/companies"


def test_shanghai_electric_power_supplemental_data_structure():
    """验证上海电力补充证据数据结构"""
    supplemental_file = FIXTURES_DIR / "shanghai_electric_power_600021_supplemental.json"

    assert supplemental_file.exists(), "上海电力补充证据文件不存在"

    with open(supplemental_file) as f:
        data = json.load(f)

    # 验证schema
    assert data["schema_version"] == "company-supplemental-evidence.v1"
    assert data["company_id"] == "600021"
    assert data["display_name"] == "上海电力"

    # 验证核心字段
    assert "fields" in data
    fields = data["fields"]

    # 验证公司基本信息
    assert "listing_market" in fields
    assert fields["listing_market"]["status"] == "VERIFIED"
    assert "SH" in fields["listing_market"]["values"]

    # 验证行业分类
    assert "industry_name" in fields
    assert "电力" in fields["industry_name"]["values"]

    # 验证财务数据
    assert "revenue" in fields
    assert "net_profit" in fields
    assert "operating_cashflow" in fields

    # 验证公用事业特有指标
    assert "installed_capacity" in fields
    assert "power_generation" in fields
    assert "dividend" in fields

    # 验证证据追溯
    assert "evidence_ids" in data
    assert len(data["evidence_ids"]) > 0

    # 验证覆盖状态
    assert data["coverage_state"] == "READY"

    print(f"✅ 上海电力数据结构验证通过")
    print(f"   - 公司: {data['display_name']}")
    print(f"   - 行业: {fields['industry_name']['values'][0]}")
    print(f"   - 覆盖状态: {data['coverage_state']}")
    print(f"   - 验证字段: {data['coverage_summary']['verified_fields']}/{data['coverage_summary']['total_fields']}")


def test_shanghai_electric_power_config_exists():
    """验证上海电力配置文件存在"""
    config_file = PROJECT_ROOT / "config/companies/600021.json"

    assert config_file.exists(), "上海电力配置文件不存在"

    with open(config_file) as f:
        config = json.load(f)

    assert config["company_id"] == "600021"
    assert config["display_name"] == "上海电力"
    assert config["industry_category"] == "公用事业"

    # 验证分析配置
    assert "analysis_config" in config
    analysis = config["analysis_config"]
    assert analysis["industry_adapter"] == "utility"
    assert analysis["cycle_applicable"] is False  # 公用事业不适用周期分析

    print(f"✅ 上海电力配置验证通过")
    print(f"   - 行业适配器: {analysis['industry_adapter']}")
    print(f"   - 周期分析: {'不适用' if not analysis['cycle_applicable'] else '适用'}")


def test_utility_adapter_exists():
    """验证公用事业行业适配器存在"""
    adapter_file = PROJECT_ROOT / "config/industries/adapters/utilities.json"

    assert adapter_file.exists(), "公用事业适配器文件不存在"

    with open(adapter_file) as f:
        adapter = json.load(f)

    assert adapter["schema_version"] == "industry-adapter.v1"
    assert adapter["adapter_id"] == "utilities"
    assert "utility" in adapter["supported_industry_ids"]
    assert "电力" in adapter["supported_industry_names"]
    assert adapter["classification_attributes"]["cyclicality"] == "REGULATED_OR_DEFENSIVE"

    # 验证估值方法
    valuation = adapter["valuation_methods"]
    assert "dividend_discount" in valuation

    print(f"✅ 公用事业适配器验证通过")
    print(f"   - 主要估值方法: {valuation[0]}")
    print(f"   - 适用行业: {', '.join(adapter['supported_industry_names'])}")


def test_shanghai_electric_power_risk_factors():
    """验证上海电力风险因素"""
    supplemental_file = FIXTURES_DIR / "shanghai_electric_power_600021_supplemental.json"

    with open(supplemental_file) as f:
        data = json.load(f)

    risks = data["fields"]["key_risks"]["values"]

    # 验证关键风险识别
    risk_types = [r["risk_type"] for r in risks]
    assert "regulatory_risk" in risk_types  # 监管风险
    assert "fuel_cost_risk" in risk_types   # 燃料成本风险

    print(f"✅ 风险因素识别完整")
    print(f"   - 识别风险数: {len(risks)}")
    for risk in risks:
        print(f"   - {risk['risk_type']}: {risk['description']}")


def test_shanghai_electric_power_financial_health():
    """验证上海电力财务健康指标"""
    supplemental_file = FIXTURES_DIR / "shanghai_electric_power_600021_supplemental.json"

    with open(supplemental_file) as f:
        data = json.load(f)

    fields = data["fields"]

    # 验证现金流充裕
    cashflow = fields["operating_cashflow"]["values"][0]
    net_profit = fields["net_profit"]["values"][0]

    cash_conversion = cashflow["value"] / net_profit["value"]
    assert cash_conversion > 2.0, "现金转换率应该较高"

    # 验证负债水平合理
    liabilities = fields["total_liabilities"]["values"][0]
    debt_ratio = liabilities["debt_to_asset_ratio"]
    assert 0.6 <= debt_ratio <= 0.7, "资产负债率应在合理范围"

    # 验证分红稳定
    dividend = fields["dividend"]["values"][0]
    assert dividend["payout_ratio"] > 0.3, "分红率应较高"

    print(f"✅ 财务健康指标验证通过")
    print(f"   - 现金转换率: {cash_conversion:.2f}x")
    print(f"   - 资产负债率: {debt_ratio:.1%}")
    print(f"   - 分红率: {dividend['payout_ratio']:.1%}")
    print(f"   - 股息率: {dividend['dividend_yield']:.1%}")


def test_shanghai_electric_power_utility_characteristics():
    """验证上海电力公用事业特征"""
    supplemental_file = FIXTURES_DIR / "shanghai_electric_power_600021_supplemental.json"

    with open(supplemental_file) as f:
        data = json.load(f)

    fields = data["fields"]

    # 验证装机容量数据
    capacity = fields["installed_capacity"]["values"][0]
    assert "thermal_power" in capacity
    assert "renewable_energy" in capacity
    assert capacity["renewable_ratio"] > 0.2, "清洁能源占比应逐步提升"

    # 验证发电量数据
    generation = fields["power_generation"]["values"][0]
    assert "utilization_rate" in generation

    # 验证行业地位
    position = fields["industry_position"]["values"][0]
    assert position["market"] == "华东地区"

    print(f"✅ 公用事业特征验证通过")
    print(f"   - 总装机容量: {capacity['total']} MW")
    print(f"   - 清洁能源占比: {capacity['renewable_ratio']:.1%}")
    print(f"   - 设备利用率: {generation['utilization_rate']:.1%}")
    print(f"   - 区域定位: {position['market']}")
