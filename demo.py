#!/usr/bin/env python
"""
投研系统演示 - 使用模拟数据
因为实时API可能不稳定，这里用模拟数据展示完整流程
"""

import pandas as pd
from datetime import datetime, timedelta

from research_system.analyzer import InvestmentAnalyzer
from research_system.report_generator import ReportGenerator


def create_mock_data(stock_code: str = "600438", stock_name: str = "通威股份") -> dict:
    """创建模拟数据"""
    return {
        'stock_info': {
            'stock_code': stock_code,
            'stock_name': stock_name,
            'industry': '光伏设备',
            'total_market_cap': 1050.5,  # 1050亿
            'circulating_market_cap': 980.2,
            'pe_ratio': 18.5,
            'pb_ratio': 2.3,
            'total_shares': 4500000000,  # 45亿股
            'circulating_shares': 4200000000,
            'fetch_time': datetime.now().isoformat(),
        },
        'realtime_price': {
            'stock_code': stock_code,
            'current_price': 15.50,
            'change_pct': -1.2,
            'change_amount': -0.19,
            'volume': 125000000,
            'turnover': 1937500000,
            'high': 15.88,
            'low': 15.35,
            'open': 15.75,
            'prev_close': 15.69,
            'fetch_time': datetime.now().isoformat(),
        },
        'financial': {
            'stock_code': stock_code,
            'report_date': '2024-09-30',
            'revenue': 68500000000,  # 685亿
            'net_profit': 2500000000,  # 25亿
            'gross_margin': 0.15,  # 15%
            'net_margin': 0.036,  # 3.6%
            'roe': 0.075,  # 7.5%
            'total_assets': 120000000000,  # 1200亿
            'total_liabilities': 66000000000,  # 660亿
            'debt_ratio': 0.55,  # 55%
            'current_ratio': 1.8,
            'operating_cash_flow': 8500000000,  # 85亿
            'fetch_time': datetime.now().isoformat(),
        },
        'balance_sheet': {
            'stock_code': stock_code,
            'report_date': '2024-09-30',
            'cash': 10000000000,  # 100亿现金
            'accounts_receivable': 8500000000,
            'inventory': 12000000000,
            'total_current_assets': 45000000000,
            'fixed_assets': 55000000000,
            'total_assets': 120000000000,
            'short_term_debt': 15000000000,  # 150亿短期债
            'long_term_debt': 25000000000,  # 250亿长期债
            'total_liabilities': 66000000000,
            'shareholders_equity': 54000000000,
            'fetch_time': datetime.now().isoformat(),
        },
        'cash_flow': {
            'stock_code': stock_code,
            'report_date': '2024-09-30',
            'operating_cash_flow': 8500000000,  # 85亿经营现金流
            'investing_cash_flow': -6000000000,  # -60亿投资现金流
            'financing_cash_flow': -1500000000,  # -15亿筹资现金流
            'capex': 6000000000,  # 60亿资本开支
            'free_cash_flow': 2500000000,  # 25亿自由现金流
            'fetch_time': datetime.now().isoformat(),
        },
        'income_statement': {
            'stock_code': stock_code,
            'report_date': '2024-09-30',
            'revenue': 68500000000,
            'operating_cost': 58225000000,
            'gross_profit': 10275000000,
            'operating_profit': 3200000000,
            'total_profit': 3000000000,
            'net_profit': 2500000000,
            'interest_expense': 800000000,  # 8亿利息费用
            'ebit': 4000000000,  # 40亿EBIT
            'fetch_time': datetime.now().isoformat(),
        },
        'dividend_history': [
            {'year': '2023', 'dividend_per_share': 0.35, 'dividend_ratio': 0.40},
            {'year': '2022', 'dividend_per_share': 0.80, 'dividend_ratio': 0.45},
            {'year': '2021', 'dividend_per_share': 1.20, 'dividend_ratio': 0.50},
            {'year': '2020', 'dividend_per_share': 0.65, 'dividend_ratio': 0.42},
            {'year': '2019', 'dividend_per_share': 0.50, 'dividend_ratio': 0.38},
        ],
        'historical_prices': pd.DataFrame({
            'date': pd.date_range(end=datetime.now(), periods=252, freq='D'),
            'close': [20.5 - i * 0.02 for i in range(252)],  # 模拟下跌趋势
            'volume': [100000000 + i * 50000 for i in range(252)],
        }),
    }


def main():
    """演示完整流程"""
    print("\n" + "="*70)
    print("  投研分析系统演示 - \"西红柿炒鸡蛋\"逻辑")
    print("  (使用模拟数据)")
    print("="*70 + "\n")

    # 创建模拟数据
    print("📊 创建模拟数据...")
    stock_data = create_mock_data("600438", "通威股份")
    print("  ✓ 模拟数据已生成\n")

    # 分析
    print("🔬 开始投资分析...")
    analyzer = InvestmentAnalyzer()
    report = analyzer.analyze(stock_data)
    print("  ✓ 分析完成\n")

    # 生成报告
    print("📄 生成分析报告...\n")
    generator = ReportGenerator()

    # 终端报告
    console_report = generator.generate_console(report)
    print(console_report)

    # 保存Markdown报告
    from pathlib import Path
    output_dir = Path("reports")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"demo_report_{timestamp}.md"

    success = generator.save_report(report, str(output_path), format='markdown')
    if success:
        print(f"\n✓ 详细报告已保存到：{output_path}")

    print("\n" + "="*70)
    print("  演示完成！")
    print("="*70)

    # 显示关键要点
    print("\n💡 系统核心功能：")
    print("  1. ✓ 产品分析 - \"西红柿炒鸡蛋\"逻辑（A/B/C/D级）")
    print("  2. ✓ 市场地位 - 龙头判断、市场份额")
    print("  3. ✓ 行业对比 - 与同行业公司对比（v2.1）")
    print("  4. ✓ 历史趋势 - 多期财报趋势分析（v2.1）")
    print("  5. ✓ 估值对比 - PE/PB/PEG行业对比（v2.2）")
    print("  6. ✓ 财务健康 - ROE、毛利率、负债率等")
    print("  7. ✓ 周期分析 - 判断底部/顶部位置")
    print("  8. ✓ 生存能力 - 现金流、能撑多久")
    print("  9. ✓ 回本周期 - 三种情景预测（核心！）")
    print("  10. ✓ 投资建议 - 明确的买入/观望/不买建议")
    print("  11. ✓ 风险提示 - 识别关键风险")

    print("\n⚠️  说明：")
    print("  • 本演示使用模拟数据")
    print("  • 实际使用时会调用AKShare API获取真实数据")
    print("  • 行业对比和历史趋势分析完全基于API（100%自动化）")
    print("  • 产业链数据需要专业数据源或人工补充")
    print("  • 投资有风险，本系统仅供参考")

    print("\n🆕 v2.2 更新：")
    print("  • ✅ 估值对比：PE/PB/PEG与行业平均对比")
    print("  • ✅ 估值水平判断：相对高估/低估/合理")
    print("  • ✅ PEG指标：衡量估值相对成长性")
    print("  • ✅ 100%基于API：无需手动维护数据")


if __name__ == "__main__":
    main()
