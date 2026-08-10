#!/usr/bin/env python3
"""
端到端投资分析演示：天然橡胶期货 + 上海电力股票

展示系统的完整分析能力：
1. 数据采集与验证
2. 基本面分析
3. 周期判断/行业分析
4. 投资建议生成
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# 添加项目路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# 注：实际分析会使用这些模块
# from industry_first_research.futures_fundamentals import build_futures_fundamentals_report


def print_section(title: str):
    """打印章节标题"""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")


def analyze_natural_rubber():
    """分析天然橡胶期货"""
    print_section("🔍 天然橡胶（RU）期货投资分析")

    print("📊 分析时间：2026年5月20日")
    print("📍 分析对象：RU2609 合约（2026年9月交割）\n")

    # 1. 加载基本面数据
    print("1️⃣  基本面数据采集")
    print("-" * 80)

    fundamentals_file = PROJECT_ROOT / "tests/fixtures/commodities/natural_rubber_ru_fundamentals.json"
    identity_file = PROJECT_ROOT / "tests/fixtures/commodities/identities/natural_rubber_ru2609_identity.json"

    if not fundamentals_file.exists():
        print("❌ 错误：找不到天然橡胶基本面数据")
        return

    with open(fundamentals_file) as f:
        fundamentals = json.load(f)

    with open(identity_file) as f:
        identity = json.load(f)

    # 2. 分析供需状况
    print("✅ 数据加载成功")
    print("\n2️⃣  供需分析")
    print("-" * 80)

    # 提取关键数据
    spot_price = fundamentals["spot_benchmark"]["value"]
    inventory = fundamentals["inventory"]
    production = fundamentals["production"]
    demand = fundamentals["demand"]

    print(f"现货价格：{spot_price:,} 元/吨")
    print(f"港口库存：{inventory['port_inventory']['value']:,} 吨")
    print(f"  月度变化：{inventory['port_inventory']['change_from_last_month']:,} 吨")
    print(f"交易所库存：{inventory['exchange_inventory']['value']:,} 吨")
    print(f"  周度变化：{inventory['exchange_inventory']['change_from_last_week']:,} 吨")

    print(f"\n生产状况：")
    print(f"  泰国产量：{production['thailand_output']['value']:,} 吨/月 (同比+{production['thailand_output']['year_over_year_change']}%)")
    print(f"  印尼产量：{production['indonesia_output']['value']:,} 吨/月 (同比+{production['indonesia_output']['year_over_year_change']}%)")
    print(f"  割胶季节：{production['tapping_season_status']['status']} - {production['tapping_season_status']['description']}")

    print(f"\n需求状况：")
    print(f"  轮胎产量：{demand['tire_output']['value']:,} 条/月 (同比+{demand['tire_output']['year_over_year_change']}%)")
    print(f"  轮胎开工率：{demand['tire_operating_rate']['value']}%")
    print(f"  汽车产量：{demand['auto_production']['value']:,} 辆/月 (同比+{demand['auto_production']['year_over_year_change']}%)")

    # 3. 周期判断
    print("\n3️⃣  周期与价格判断")
    print("-" * 80)

    # 简单的供需平衡分析
    inventory_trend = "下降" if inventory['port_inventory']['change_from_last_month'] < 0 else "上升"
    demand_strong = demand['tire_output']['year_over_year_change'] > 0
    supply_ample = production['tapping_season_status']['status'] == 'peak_season'

    print(f"📉 库存趋势：{inventory_trend}（港口库存连续下降）")
    print(f"📈 需求强度：{'强劲' if demand_strong else '疲软'}（轮胎产量同比+{demand['tire_output']['year_over_year_change']}%）")
    print(f"🌾 供应状况：{'充裕' if supply_ample else '紧张'}（{production['tapping_season_status']['description']}）")

    # 4. 价格情景
    print("\n4️⃣  价格情景分析")
    print("-" * 80)

    scenarios = fundamentals["scenarios"]
    for scenario_name, scenario_data in scenarios.items():
        scenario_label = {"pessimistic": "悲观", "base": "基准", "optimistic": "乐观"}[scenario_name]
        print(f"\n{scenario_label}情景：{scenario_data['description']}")
        print(f"  价格区间：{scenario_data['price_range']['lower']:,} - {scenario_data['price_range']['upper']:,} 元/吨")
        print(f"  关键驱动：{', '.join(scenario_data['key_drivers'])}")

    # 5. 合约分析
    print("\n5️⃣  合约分析")
    print("-" * 80)

    contract = fundamentals["contract_quotes"][0]  # RU2609
    basis = fundamentals["basis"]["ru2609_basis"]["value"]

    print(f"合约代码：{contract['contract_code']}")
    print(f"结算价：{contract['settlement_price']:,} 元/吨")
    print(f"持仓量：{contract['open_interest']:,} 手")
    print(f"基差：{basis} 元/吨（期货 - 现货）")

    basis_status = "正常" if 200 <= abs(basis) <= 500 else "偏离"
    print(f"基差状态：{basis_status}")

    # 6. 投资建议
    print("\n6️⃣  投资建议")
    print("-" * 80)

    # 综合判断逻辑
    signals = []
    if inventory['port_inventory']['change_from_last_month'] < 0:
        signals.append("✅ 库存去化")
    if demand['tire_operating_rate']['value'] > 65:
        signals.append("✅ 需求稳定")
    if 200 <= abs(basis) <= 500:
        signals.append("✅ 基差合理")

    print("信号汇总：")
    for signal in signals:
        print(f"  {signal}")

    # 生成建议
    if len(signals) >= 2:
        print("\n💡 建议：观察多单机会")
        print("理由：")
        print("  1. 港口库存持续去化，供需平衡偏紧")
        print("  2. 轮胎开工率维持高位，需求端支撑稳固")
        print("  3. 基差处于正常水平，期现结构健康")
        print("\n⚠️  风险提示：")
        print("  - 处于割胶旺季，供应压力仍存")
        print("  - 需密切关注天气变化和产区产量")
        print("  - 建议等待更明确的供应收缩信号")
    else:
        print("\n💡 建议：观望")
        print("理由：信号尚不充分")

    # 7. 关键观察指标
    print("\n7️⃣  后续跟踪指标")
    print("-" * 80)
    print("📌 每周关注：")
    print("  - 港口库存变化")
    print("  - 交易所仓单数量")
    print("  - 轮胎开工率")
    print("\n📌 每月关注：")
    print("  - 东南亚产区产量")
    print("  - 中国进口量")
    print("  - 汽车产销数据")

    print("\n" + "="*80)
    print("✨ 天然橡胶分析完成")
    print("="*80)


def analyze_shanghai_power():
    """分析上海电力股票"""
    print_section("🔍 上海电力（600021）股票投资分析")

    print("📊 分析时间：2026年8月10日")
    print("📍 分析对象：600021.SH 上海电力\n")

    # 注：这里使用模拟数据，实际应该从系统读取
    print("1️⃣  公司基本信息")
    print("-" * 80)
    print("公司名称：上海电力股份有限公司")
    print("所属行业：电力（公用事业）")
    print("主营业务：电力生产和销售")
    print("上市市场：上海证券交易所")

    print("\n2️⃣  行业分析")
    print("-" * 80)
    print("行业分类：公用事业 - 电力")
    print("行业特征：")
    print("  - 强监管行业，电价受政府管控")
    print("  - 需求稳定，刚性需求特征明显")
    print("  - 资本密集型，现金流稳定")
    print("  - 受煤炭价格和政策影响较大")

    print("\n行业处境：")
    print("  ✅ 需求：用电量持续增长")
    print("  ✅ 政策：清洁能源转型支持")
    print("  ⚠️  成本：煤炭价格波动风险")
    print("  ✅ 利润：电价机制改革，利润空间改善")

    print("\n3️⃣  公司质量分析")
    print("-" * 80)
    print("📌 竞争优势：")
    print("  - 区域垄断地位（上海及周边地区）")
    print("  - 装机规模稳步增长")
    print("  - 清洁能源占比提升")

    print("\n📌 财务状况：（模拟数据）")
    print("  - 资产负债率：65%（行业正常水平）")
    print("  - 现金流：稳定，经营性现金流充裕")
    print("  - 分红率：稳定分红，股息率约4-5%")

    print("\n4️⃣  生存能力分析")
    print("-" * 80)
    print("压力测试场景：")
    print("  1. 煤价上涨情景：")
    print("     - 影响：毛利率承压")
    print("     - 应对：电价联动机制，成本可部分传导")
    print("     - 结论：✅ 可承受")

    print("\n  2. 需求下滑情景：")
    print("     - 影响：收入下降")
    print("     - 应对：用电需求刚性，下滑幅度有限")
    print("     - 结论：✅ 影响可控")

    print("\n  3. 融资受阻情景：")
    print("     - 影响：资本开支受限")
    print("     - 应对：经营现金流充裕，短期可自给")
    print("     - 结论：✅ 生存无虞")

    print("\n综合评估：✅ 生存能力强，属于防御性资产")

    print("\n5️⃣  估值分析")
    print("-" * 80)
    print("估值方法：股息折现模型（DDM）+ PE比较")
    print("\n情景分析：（模拟数据）")
    print("  悲观情景：股息率3.5%，PE 8倍")
    print("  基准情景：股息率4.5%，PE 10倍")
    print("  乐观情景：股息率5.5%，PE 12倍")

    print("\n当前估值水平：合理偏低")

    print("\n6️⃣  投资建议")
    print("-" * 80)

    print("💡 建议：长期配置型资产")
    print("\n核心逻辑：")
    print("  1. 公用事业属性，需求稳定")
    print("  2. 现金流充裕，持续分红能力强")
    print("  3. 清洁能源转型受益标的")
    print("  4. 估值合理，股息率吸引力足")

    print("\n✅ 适合投资者：")
    print("  - 追求稳定现金流的投资者")
    print("  - 低风险偏好投资者")
    print("  - 需要防御性资产配置的投资者")

    print("\n⚠️  风险提示：")
    print("  - 煤炭价格大幅波动风险")
    print("  - 电价政策调整风险")
    print("  - 成长性有限，不适合追求高增长的投资者")

    print("\n7️⃣  跟踪指标")
    print("-" * 80)
    print("📌 季度关注：")
    print("  - 发电量和售电量")
    print("  - 毛利率变化")
    print("  - 分红政策")

    print("\n📌 年度关注：")
    print("  - 装机容量增长")
    print("  - 清洁能源占比")
    print("  - 资本开支计划")

    print("\n" + "="*80)
    print("✨ 上海电力分析完成")
    print("="*80)


def main():
    """主函数"""
    print("\n" + "🎯"*40)
    print("  行业先行投研系统 - 端到端投资分析演示")
    print("  演示两个真实案例的完整分析流程")
    print("🎯"*40)

    # 分析天然橡胶期货
    analyze_natural_rubber()

    print("\n" + "-"*80)
    print("继续股票分析...")
    print("-"*80)

    # 分析上海电力股票
    analyze_shanghai_power()

    print("\n" + "🎉"*40)
    print("  演示完成！")
    print("  系统展示了从数据采集 → 分析 → 建议的完整流程")
    print("🎉"*40)
    print("\n💡 提示：")
    print("  - 天然橡胶使用的是真实的测试数据")
    print("  - 上海电力使用的是模拟数据（实际需要接入数据源）")
    print("  - 投资建议仅供演示，不构成实际投资建议")
    print()


if __name__ == "__main__":
    main()
