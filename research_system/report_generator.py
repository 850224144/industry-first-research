"""
报告生成模块 - 生成可读的投研报告
"""

from typing import Dict
from datetime import datetime


class ReportGenerator:
    """报告生成器 - 将分析结果转换为可读报告"""

    def generate_markdown(self, report: Dict) -> str:
        """生成Markdown格式报告"""
        md = []

        # 标题
        md.append(f"# 📊 {report['stock_name']}（{report['stock_code']}）投资分析报告")
        md.append(f"\n**生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        md.append("---\n")

        # 1. 一句话总结
        md.append("## 📌 一句话总结\n")
        md.append(f"{report['summary']}\n")
        md.append("---\n")

        # 2. 产品分析
        md.append("## 1. 产品分析（西红柿炒鸡蛋逻辑）\n")
        product = report.get('product_analysis', {})

        if product.get('has_config'):
            # 有完整配置
            md.append(f"### 行业：{product.get('industry', '未知')}\n")

            md.append("### 产业链全景\n")
            md.append(f"```")
            md.append(f"{product.get('chain_flow', '')}")
            md.append(f"     ↑")
            md.append(f"  【{product.get('company_position', '')}】")
            md.append(f"```")
            if product.get('chain_description'):
                md.append(f"\n*{product['chain_description']}*\n")

            md.append(f"### 核心产品：{product.get('main_product', '')}\n")

            md.append(f"**重要性等级**：{product.get('importance_level_name', '')}")
            md.append(f"- **评分**：{product.get('importance_score', 0)}/100")
            md.append(f"- **理由**：{product.get('importance_reason', '')}")
            md.append(f"- **类比**：{product.get('analogy', '')}\n")

            md.append(f"**价值占比**：{product.get('value_ratio', 0)*100:.0f}%")
            md.append(f"- {product.get('value_ratio_desc', '')}\n")

            md.append(f"**可替代性**：{product.get('substitutability', 'medium')}")
            md.append(f"- {product.get('substitutability_desc', '')}\n")

            md.append(f"**技术壁垒**：{product.get('tech_barrier', 'medium')}")
            md.append(f"- {product.get('tech_barrier_desc', '')}\n")

            md.append(f"**市场集中度**：{product.get('market_concentration', 'medium')}")
            md.append(f"- {product.get('market_concentration_desc', '')}\n")

            # 如果有多个产品
            all_products = product.get('all_products', [])
            if len(all_products) > 1:
                md.append(f"### 其他产品\n")
                for p in all_products[1:]:
                    # 兼容V1和V2的字段名
                    p_name = p.get('name') or p.get('product_name', '未知产品')
                    p_level = p.get('level_name') or f"{p.get('level', 'B')}级"
                    p_score = p.get('importance_score', 0)
                    p_analogy = p.get('analogy', '')

                    md.append(f"**{p_name}**")
                    md.append(f"- 等级：{p_level}")
                    md.append(f"- 评分：{p_score}/100")
                    if p_analogy:
                        md.append(f"- 类比：{p_analogy}")
                    md.append("")

        else:
            # 没有配置，显示基本信息
            md.append(f"- **所属行业**：{product.get('industry', '未知')}")
            md.append(f"- **产品重要性**：{product.get('importance_level', 'B')}级")
            md.append(f"- **产业链位置**：{product.get('company_position', '需要配置')}")
            md.append(f"\n⚠️ *该行业暂无详细产业链配置*\n")
            md.append(f"*建议：在 industry_chain_knowledge.py 中补充该行业配置*\n")

        # 3. 市场地位
        md.append("## 2. 市场地位\n")
        market = report.get('market_position', {})
        md.append(f"- **总市值**：{market.get('market_cap', 0):.1f}亿元")
        md.append(f"- **地位判断**：{market.get('position_type', '未知')}")
        md.append(f"- **市场份额**：{market.get('market_share', '需要数据')}")
        md.append(f"- **是否龙头**：{'✓ 是' if market.get('is_leader') else '✗ 否'}")
        md.append(f"\n*{market.get('description', '')}*\n")

        # 3.5 行业对比（新增）
        industry_comp = report.get('industry_comparison', {})
        if industry_comp.get('success'):
            md.append("### 行业对比分析\n")
            md.append(f"- **行业**：{industry_comp.get('industry', '')}")
            md.append(f"- **同行业公司数**：{industry_comp.get('peer_count', 0)}家")

            rankings = industry_comp.get('rankings', {})
            md.append(f"- **市值排名**：第{rankings.get('market_cap', 'N/A')}名")
            md.append(f"- **营收排名**：第{rankings.get('revenue', 'N/A')}名")
            md.append(f"- **ROE排名**：第{rankings.get('roe', 'N/A')}名")

            md.append("\n**与行业平均对比**：")
            for comp in industry_comp.get('comparison', []):
                md.append(f"- {comp}")

            leader_mc = industry_comp.get('leader_by_market_cap', {})
            md.append(f"\n*行业龙头（市值）：{leader_mc.get('name', 'N/A')} ({leader_mc.get('market_cap', 0):.0f}亿)*")
            md.append("")

        # 3.6 历史趋势
        trends = report.get('historical_trends', {})
        if trends.get('success'):
            md.append("### 历史趋势分析\n")
            md.append(f"**{trends.get('overall', '')}**\n")
            md.append("**最近4期变化**：")
            for detail in trends.get('details', []):
                md.append(f"- {detail}")
            md.append("")

        # 3.7 估值对比（新增）
        valuation = report.get('valuation_comparison', {})
        if valuation.get('success'):
            md.append("### 估值对比分析\n")
            md.append(f"**估值水平**：{valuation.get('valuation_level', 'N/A')}\n")

            md.append("**估值指标**：")
            md.append(f"- **PE（市盈率）**：{valuation.get('current_pe', 0):.1f} | 行业平均：{valuation.get('avg_pe', 0):.1f}")
            pe_premium = valuation.get('pe_premium', 0)
            if pe_premium > 0:
                md.append(f"  - 溢价：+{pe_premium:.0f}%")
            else:
                md.append(f"  - 折价：{pe_premium:.0f}%")

            md.append(f"- **PB（市净率）**：{valuation.get('current_pb', 0):.2f} | 行业平均：{valuation.get('avg_pb', 0):.2f}")
            md.append(f"- **PEG**：{valuation.get('peg', 0):.2f} (PE/成长率)")

            md.append("\n**估值评价**：")
            for analysis in valuation.get('analysis', []):
                md.append(f"- {analysis}")
            md.append("")

        # 4. 财务健康度
        md.append("## 3. 财务健康度\n")
        financial = report.get('financial_health', {})
        md.append(f"### 评级：{financial.get('grade', 'N/A')} （{financial.get('health_score', 0)}分）\n")
        md.append("**关键指标**：")
        md.append(f"- ROE（净资产收益率）：{financial.get('roe', 0)*100:.1f}%")
        md.append(f"- 毛利率：{financial.get('gross_margin', 0)*100:.1f}%")
        md.append(f"- 净利率：{financial.get('net_margin', 0)*100:.1f}%")
        md.append(f"- 资产负债率：{financial.get('debt_ratio', 0)*100:.1f}%")
        md.append("\n**评估因素**：")
        for factor in financial.get('factors', []):
            md.append(f"- {factor}")
        md.append("")

        # 5. 行业周期
        md.append("## 4. 行业周期分析\n")
        cycle = report.get('cycle_analysis', {})
        md.append(f"- **当前位置**：{cycle.get('position', '需要数据')}")
        md.append(f"- **置信度**：{cycle.get('confidence', 'low')}")
        if cycle.get('signals'):
            md.append("\n**信号**：")
            for signal in cycle['signals']:
                md.append(f"- {signal}")
        md.append(f"\n*{cycle.get('description', '')}*\n")

        # 6. 生存能力
        md.append("## 5. 生存能力分析\n")
        survival = report.get('survival_analysis', {})
        md.append(f"### 评级：{survival.get('grade', 'N/A')}\n")
        md.append("**关键数据**：")
        md.append(f"- 货币资金：{survival.get('cash', 0):.1f}亿元")
        md.append(f"- 净现金：{survival.get('net_cash', 0):.1f}亿元")
        md.append(f"- 利息覆盖倍数：{survival.get('interest_coverage', 0):.1f}倍")
        md.append(f"- 自由现金流：{survival.get('free_cash_flow', 0):.1f}亿元")
        survival_years = survival.get('survival_years', 0)
        if survival_years < 999:
            md.append(f"- **能撑时间**：{survival_years:.0f}年（极端情况）")
        md.append("\n**评估**：")
        for note in survival.get('notes', []):
            md.append(f"- {note}")
        md.append(f"\n**结论**：{survival.get('conclusion', '')}\n")

        # 7. 回本周期预测（核心）
        md.append("## 6. 回本周期预测 ⭐⭐⭐\n")
        payback = report.get('payback_analysis', {})
        buy_price = payback.get('buy_price', 0)
        md.append(f"**买入价**：{buy_price:.2f}元/股\n")

        md.append("### 三种情景：\n")
        for scenario in payback.get('scenarios', []):
            md.append(f"#### {scenario['name']}情景（概率{scenario['probability']*100:.0f}%）\n")
            md.append("**假设**：")
            for assumption in scenario['assumptions']:
                md.append(f"- {assumption}")
            md.append(f"\n**收益**：")
            md.append(f"- 回本周期：{scenario['years']}年")
            md.append(f"- 总回报：{scenario['total_return_pct']:.1f}%")
            md.append(f"- 年化回报：{scenario['annual_return_pct']:.1f}%")
            md.append(f"- 累计分红：{scenario['dividend_total']:.2f}元")
            md.append(f"- 预期股价：{scenario['exit_price']:.2f}元（{'↑' if scenario['price_gain'] > 0 else '↓'}{abs(scenario['price_gain']):.2f}元）")
            md.append("")

        md.append("### 概率加权期望：\n")
        md.append(f"- **期望总回报**：{payback.get('expected_return', 0):.1f}%")
        md.append(f"- **期望回本周期**：{payback.get('expected_years', 0):.1f}年")
        md.append(f"- **期望年化收益**：{payback.get('expected_annual_return', 0):.1f}%")
        md.append(f"\n**结论**：{payback.get('conclusion', '')}\n")

        # 8. 投资建议
        md.append("## 7. 投资建议\n")
        advice = report.get('investment_advice', {})
        md.append(f"### {advice.get('action', '')}\n")
        md.append(f"**综合评分**：{advice.get('score', 0)}/100\n")
        md.append("**理由**：")
        for reason in advice.get('reasons', []):
            md.append(f"- {reason}")
        md.append(f"\n**操作策略**：{advice.get('strategy', '')}")
        md.append(f"\n**止损线**：{advice.get('stop_loss', 'N/A')}\n")

        # 9. 风险提示
        md.append("## 8. 风险提示\n")
        for risk in report.get('risks', []):
            md.append(f"- {risk}")
        md.append("")

        # 10. 核心假设
        md.append("## 9. 核心假设与失效条件\n")
        md.append("### 基准情景需要满足：")
        md.append("- ✓ 行业需求持续增长")
        md.append("- ✓ 公司市场份额不下降")
        md.append("- ✓ 没有重大技术替代")
        md.append("- ✓ 财务状况不恶化")
        md.append("\n### 如果出现以下情况，立即重新评估：")
        md.append("- ✗ 需求大幅下滑")
        md.append("- ✗ 市场份额持续下降")
        md.append("- ✗ 出现重大财务问题")
        md.append("- ✗ 行业出现颠覆性技术")
        md.append("")

        # 11. 数据来源说明
        md.append("---\n")
        md.append("## 📝 说明\n")
        md.append("- **数据来源**：AKShare API（实时数据）")
        md.append('- **分析方法**：基于"西红柿炒鸡蛋"产业链逻辑')
        md.append("- **重要提示**：本报告仅供参考，不构成投资建议")
        md.append("- **产业链数据**：部分产业链信息需要人工配置或专业数据源")
        md.append("\n*投资有风险，决策需谨慎*")

        return '\n'.join(md)

    def generate_console(self, report: Dict) -> str:
        """生成终端友好的简化报告"""
        lines = []

        # 标题
        lines.append("=" * 60)
        lines.append(f"  📊 {report['stock_name']}（{report['stock_code']}) 投资分析")
        lines.append("=" * 60)

        # 一句话总结
        lines.append(f"\n【总结】{report['summary']}\n")

        # 产品分析（简化）
        product = report.get('product_analysis', {})
        if product.get('has_config'):
            lines.append(f"【产品】{product.get('main_product', '')} | {product.get('importance_level_name', '')} ({product.get('importance_score', 0)}分)")
            lines.append(f"  {product.get('analogy', '')}")
        else:
            lines.append(f"【产品】{product.get('industry', '')} | {product.get('importance_level', 'B')}级 (暂无详细配置)")

        # 市场地位
        market = report.get('market_position', {})
        industry_comp = report.get('industry_comparison', {})

        position_text = f"【市场地位】{market.get('position_type', '未知')} | 市值{market.get('market_cap', 0):.0f}亿"
        if industry_comp.get('success'):
            rankings = industry_comp.get('rankings', {})
            position_text += f" | 行业排名第{rankings.get('market_cap', 'N/A')}名"
        lines.append(position_text)

        # 财务健康
        financial = report.get('financial_health', {})
        lines.append(f"【财务健康】{financial.get('grade', 'N/A')} | ROE {financial.get('roe', 0)*100:.1f}% | 毛利率 {financial.get('gross_margin', 0)*100:.1f}%")

        # 历史趋势
        trends = report.get('historical_trends', {})
        if trends.get('success'):
            lines.append(f"【历史趋势】{trends.get('overall', '')}")

        # 估值水平
        valuation = report.get('valuation_comparison', {})
        if valuation.get('success'):
            lines.append(f"【估值水平】{valuation.get('valuation_level', 'N/A')} | PE {valuation.get('current_pe', 0):.1f} vs 行业{valuation.get('avg_pe', 0):.1f}")

        # 生存能力
        survival = report.get('survival_analysis', {})
        lines.append(f"【生存能力】{survival.get('grade', 'N/A')} | {survival.get('conclusion', '')}")

        # 回本周期
        lines.append("\n" + "-" * 60)
        lines.append("  ⭐ 回本周期预测")
        lines.append("-" * 60)
        payback = report.get('payback_analysis', {})
        lines.append(f"买入价：{payback.get('buy_price', 0):.2f}元")
        lines.append("")

        for scenario in payback.get('scenarios', []):
            lines.append(f"  {scenario['name']}（{scenario['probability']*100:.0f}%）：{scenario['years']}年 | 年化{scenario['annual_return_pct']:.1f}%")

        lines.append(f"\n  期望：{payback.get('expected_years', 0):.1f}年 | 年化{payback.get('expected_annual_return', 0):.1f}%")
        lines.append(f"  {payback.get('conclusion', '')}")

        # 投资建议
        lines.append("\n" + "-" * 60)
        advice = report.get('investment_advice', {})
        lines.append(f"  【投资建议】{advice.get('action', '')} ({advice.get('score', 0)}分)")
        lines.append("-" * 60)
        lines.append(f"  策略：{advice.get('strategy', '')}")
        lines.append(f"  止损：{advice.get('stop_loss', '')}")

        # 风险
        lines.append("\n【风险提示】")
        for risk in report.get('risks', [])[:3]:  # 只显示前3个
            lines.append(f"  {risk}")

        lines.append("\n" + "=" * 60)
        lines.append(f"  生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 60)

        return '\n'.join(lines)

    def save_report(self, report: Dict, output_path: str, format: str = 'markdown') -> bool:
        """
        保存报告到文件

        Args:
            report: 分析报告
            output_path: 输出路径
            format: 格式（markdown/console）

        Returns:
            是否成功
        """
        try:
            if format == 'markdown':
                content = self.generate_markdown(report)
            else:
                content = self.generate_console(report)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)

            return True
        except Exception as e:
            print(f"保存报告失败: {e}")
            return False


# 测试代码
if __name__ == "__main__":
    # 模拟报告数据
    mock_report = {
        'stock_code': '600438',
        'stock_name': '通威股份',
        'analysis_date': datetime.now().isoformat(),
        'summary': '通威股份，行业龙头候选，可能处于底部，预期2.8年回本，💡 可以买入',
        'product_analysis': {
            'industry': '光伏设备',
            'importance_level': 'A',
            'supply_chain_position': '上游-硅料',
            'substitutability': 'low',
            'description': '光伏产业链核心原料供应商',
            'analogy': '西红柿炒鸡蛋里的"西红柿"',
        },
        'market_position': {
            'market_cap': 1050,
            'position_type': '行业龙头候选',
            'market_share': '预估>10%',
            'is_leader': True,
            'description': '总市值1050.0亿，初步判断为行业龙头候选',
        },
        'financial_health': {
            'roe': 0.08,
            'gross_margin': 0.15,
            'net_margin': 0.05,
            'debt_ratio': 0.55,
            'health_score': 65,
            'grade': 'B-良好',
            'factors': ['○ ROE一般(10-15%)', '✗ 毛利率低(<20%)', '○ 净利率一般(5-10%)', '✓ 负债率安全(<60%)'],
        },
        'cycle_analysis': {
            'position': '可能处于底部',
            'signals': ['盈利能力低迷', '股价处于低位'],
            'confidence': 'low',
            'description': '周期判断需要补充行业数据',
        },
        'survival_analysis': {
            'cash': 100,
            'net_cash': 30,
            'interest_coverage': 5.0,
            'free_cash_flow': 10,
            'survival_years': 15,
            'grade': 'A',
            'notes': ['✓ 净现金30.0亿', '✓ 利息覆盖良好', '✓ 自由现金流为正'],
            'conclusion': '✓ 龙头公司，能熬过周期底部',
        },
        'payback_analysis': {
            'buy_price': 15.50,
            'scenarios': [
                {
                    'name': '悲观',
                    'probability': 0.20,
                    'years': 3,
                    'assumptions': ['周期持续低迷', '公司微利或小亏', '分红大幅减少'],
                    'dividend_total': 0.5,
                    'exit_price': 13.2,
                    'price_gain': -2.3,
                    'total_return': -1.8,
                    'total_return_pct': -11.6,
                    'annual_return_pct': -3.9,
                },
                {
                    'name': '基准',
                    'probability': 0.60,
                    'years': 3,
                    'assumptions': ['2年内周期反转', '盈利逐步恢复', '分红恢复到历史水平'],
                    'dividend_total': 1.5,
                    'exit_price': 21.7,
                    'price_gain': 6.2,
                    'total_return': 7.7,
                    'total_return_pct': 49.7,
                    'annual_return_pct': 16.6,
                },
                {
                    'name': '乐观',
                    'probability': 0.20,
                    'years': 2,
                    'assumptions': ['快速反转', '市场份额提升', '盈利超预期'],
                    'dividend_total': 1.2,
                    'exit_price': 26.4,
                    'price_gain': 10.9,
                    'total_return': 12.1,
                    'total_return_pct': 78.1,
                    'annual_return_pct': 39.0,
                },
            ],
            'expected_return': 45.5,
            'expected_years': 2.8,
            'expected_annual_return': 16.2,
            'conclusion': '✓ 期望年化16.2%，值得投资',
        },
        'investment_advice': {
            'score': 75,
            'action': '💡 可以买入',
            'strategy': '分3批建仓，每批间隔1-2周',
            'stop_loss': '设置-20%止损线',
            'reasons': ['✓ 预期回报高', '✓ 财务安全', '○ 财务良好'],
        },
        'risks': [
            '⚠ 周期底部，反转时间不确定',
            '⚠ 部分财务数据缺失，分析可能不完整',
        ],
    }

    generator = ReportGenerator()

    print("生成终端报告：")
    print(generator.generate_console(mock_report))

    print("\n\n保存Markdown报告...")
    generator.save_report(mock_report, '/tmp/test_report.md', format='markdown')
    print("已保存到 /tmp/test_report.md")
