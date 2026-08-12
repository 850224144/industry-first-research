"""
投研系统 Web界面 - 使用Streamlit
"""

import streamlit as st
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from research_system.data_collector import DataCollector
from research_system.analyzer import InvestmentAnalyzer
from research_system.report_generator import ReportGenerator


# 页面配置
st.set_page_config(
    page_title="投研分析系统",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 自定义CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .success-box {
        background-color: #d4edda;
        border-left: 4px solid #28a745;
        padding: 1rem;
        margin: 1rem 0;
    }
    .warning-box {
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 1rem;
        margin: 1rem 0;
    }
    .danger-box {
        background-color: #f8d7da;
        border-left: 4px solid #dc3545;
        padding: 1rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)


def main():
    """主函数"""

    # 标题
    st.markdown('<h1 class="main-header">📊 投研分析系统</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">用"西红柿炒鸡蛋"的逻辑分析上市公司投资价值</p>', unsafe_allow_html=True)

    # 侧边栏
    with st.sidebar:
        st.header("⚙️ 设置")

        # 股票代码输入
        stock_code = st.text_input(
            "股票代码",
            value="600438",
            help="输入6位股票代码，如：600438（通威股份）",
            max_chars=6,
        )

        # 分析按钮
        analyze_button = st.button("🔍 开始分析", type="primary", use_container_width=True)

        st.divider()

        # 功能说明
        st.subheader("🎯 核心功能")
        st.markdown("""
        - ✓ 财务健康度评估
        - ✓ 行业对比分析
        - ✓ 历史趋势分析
        - ✓ 估值对比
        - ✓ 回本周期预测
        - ✓ 投资建议生成
        """)

        st.divider()

        st.caption("v2.2 | 100%基于实时API")

    # 主内容区域
    if not analyze_button or not stock_code:
        # 默认显示欢迎页面
        show_welcome_page()
        return

    if len(stock_code) != 6 or not stock_code.isdigit():
        st.error("❌ 请输入正确的6位股票代码")
        return

    # 显示加载状态
    with st.spinner(f"正在分析 {stock_code}..."):
        try:
            # 初始化组件
            collector = DataCollector()
            analyzer = InvestmentAnalyzer()

            # 数据采集
            with st.status("📡 数据采集中...", expanded=True) as status:
                st.write("获取股票信息...")
                stock_data = collector.get_all_data(stock_code)

                # 检查数据获取情况
                success_count = sum([
                    bool(stock_data.get('stock_info')),
                    bool(stock_data.get('realtime_price')),
                    bool(stock_data.get('financial')),
                    bool(stock_data.get('balance_sheet')),
                    bool(stock_data.get('cash_flow')),
                    bool(stock_data.get('income_statement')),
                ])

                if success_count == 0:
                    st.error("❌ 无法获取股票数据")
                    st.warning("""
                    **可能的原因**：
                    1. 股票代码错误（请确认是6位数字）
                    2. 网络连接不稳定
                    3. AKShare API暂时不可用

                    **建议**：
                    - 检查股票代码是否正确
                    - 稍后重试
                    - 尝试其他股票代码（如：600438）
                    """)
                    status.update(label="✗ 数据采集失败", state="error")
                    return

                if success_count < 3:
                    st.warning(f"⚠️ 部分数据获取失败（{success_count}/6），分析可能不完整")

                st.write(f"✓ 数据获取完成（{success_count}/6项）")
                status.update(label=f"✓ 数据采集完成（{success_count}/6）", state="complete")

            # 分析
            with st.status("🔬 投资分析中...", expanded=False) as status:
                report = analyzer.analyze(stock_data)
                status.update(label="✓ 分析完成", state="complete")

            # 显示结果
            display_report(report, stock_data)

        except Exception as e:
            st.error(f"❌ 分析失败: {str(e)}")
            with st.expander("查看详细错误信息"):
                st.exception(e)
            st.info("""
            **常见问题解决**：
            - 网络问题：请检查网络连接后重试
            - API限流：等待1-2分钟后重试
            - 数据缺失：尝试分析其他股票
            """)


def show_welcome_page():
    """显示欢迎页面"""

    col1, col2, col3 = st.columns(3)

    with col1:
        st.info("🎯 **精准分析**\n\n基于实时财务数据，8维度深度分析")

    with col2:
        st.success("🚀 **快速决策**\n\n三种情景预测，明确投资建议")

    with col3:
        st.warning("📊 **行业对比**\n\n与同行业公司对比，看清真实位置")

    st.divider()

    # 示例展示
    st.subheader("📌 分析示例")

    example_col1, example_col2 = st.columns(2)

    with example_col1:
        st.markdown("""
        **输入**：股票代码（如 600438）

        **输出**：
        - 市场地位：行业排名第3
        - 财务健康：B级（良好）
        - 估值水平：相对低估
        - 回本周期：预期2.8年
        - 投资建议：💡 可以买入
        """)

    with example_col2:
        st.markdown("""
        **核心理念**："西红柿炒鸡蛋"

        - A级（西红柿）：核心原料
        - B级（鸡蛋）：关键部件
        - C级（食用油）：重要辅料
        - D级（葱花）：加分项

        用做菜的逻辑理解产业链！
        """)

    st.divider()

    st.info("👈 在左侧输入股票代码，点击「开始分析」按钮")


def display_report(report: dict, stock_data: dict):
    """显示分析报告"""

    stock_name = report.get('stock_name', '')
    stock_code = report.get('stock_code', '')

    # 顶部摘要卡片
    st.markdown(f"## 📊 {stock_name}（{stock_code}）")
    st.markdown(f"**{report.get('summary', '')}**")

    st.divider()

    # 关键指标卡片
    col1, col2, col3, col4 = st.columns(4)

    market = report.get('market_position', {})
    financial = report.get('financial_health', {})
    valuation = report.get('valuation_comparison', {})
    payback = report.get('payback_analysis', {})

    with col1:
        st.metric(
            "市值排名",
            f"第{report.get('industry_comparison', {}).get('rankings', {}).get('market_cap', 'N/A')}名"
            if report.get('industry_comparison', {}).get('success') else "N/A",
            f"{market.get('market_cap', 0):.0f}亿"
        )

    with col2:
        grade = financial.get('grade', 'N/A')
        st.metric("财务健康", grade, f"ROE {financial.get('roe', 0)*100:.1f}%")

    with col3:
        if valuation.get('success'):
            st.metric(
                "估值水平",
                valuation.get('valuation_level', 'N/A'),
                f"PE {valuation.get('current_pe', 0):.1f}"
            )
        else:
            st.metric("估值水平", "N/A", "数据不足")

    with col4:
        expected_years = payback.get('expected_years', 0)
        expected_return = payback.get('expected_annual_return', 0)
        st.metric(
            "回本周期",
            f"{expected_years:.1f}年" if expected_years > 0 else "N/A",
            f"年化{expected_return:.1f}%" if expected_return > 0 else ""
        )

    st.divider()

    # 标签页
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "💡 投资建议",
        "📊 行业对比",
        "📈 估值分析",
        "💰 回本周期",
        "⚠️ 风险提示"
    ])

    # Tab 1: 投资建议
    with tab1:
        display_investment_advice(report)

    # Tab 2: 行业对比
    with tab2:
        display_industry_comparison(report)

    # Tab 3: 估值分析
    with tab3:
        display_valuation_analysis(report)

    # Tab 4: 回本周期
    with tab4:
        display_payback_analysis(report)

    # Tab 5: 风险提示
    with tab5:
        display_risks(report)


def display_investment_advice(report: dict):
    """显示投资建议"""
    advice = report.get('investment_advice', {})

    action = advice.get('action', '')
    score = advice.get('score', 0)

    # 根据建议显示不同颜色
    if '买入' in action:
        box_class = "success-box"
        icon = "✅"
    elif '观望' in action:
        box_class = "warning-box"
        icon = "⚠️"
    else:
        box_class = "danger-box"
        icon = "❌"

    st.markdown(f"""
    <div class="{box_class}">
        <h3>{icon} {action}</h3>
        <p><strong>综合评分</strong>：{score}/100</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📋 理由")
        for reason in advice.get('reasons', []):
            st.markdown(f"- {reason}")

    with col2:
        st.subheader("🎯 操作策略")
        st.markdown(f"**策略**：{advice.get('strategy', 'N/A')}")
        st.markdown(f"**止损线**：{advice.get('stop_loss', 'N/A')}")


def display_industry_comparison(report: dict):
    """显示行业对比"""
    industry_comp = report.get('industry_comparison', {})
    trends = report.get('historical_trends', {})

    if not industry_comp.get('success'):
        st.warning("行业对比数据获取失败")
        return

    # 基本信息
    col1, col2 = st.columns(2)

    with col1:
        st.metric("行业", industry_comp.get('industry', 'N/A'))
        st.metric("同行业公司数", f"{industry_comp.get('peer_count', 0)}家")

    with col2:
        rankings = industry_comp.get('rankings', {})
        st.metric("市值排名", f"第{rankings.get('market_cap', 'N/A')}名")
        st.metric("ROE排名", f"第{rankings.get('roe', 'N/A')}名")

    st.divider()

    # 对比分析
    st.subheader("📊 与行业平均对比")
    for comp in industry_comp.get('comparison', []):
        if '✓' in comp:
            st.success(comp)
        elif '✗' in comp:
            st.error(comp)
        else:
            st.info(comp)

    # 行业龙头
    leader = industry_comp.get('leader_by_market_cap', {})
    if leader:
        st.info(f"🏆 行业龙头（市值）：**{leader.get('name', 'N/A')}** ({leader.get('market_cap', 0):.0f}亿)")

    # 历史趋势
    if trends.get('success'):
        st.divider()
        st.subheader("📈 历史趋势")

        overall = trends.get('overall', '')
        if '改善' in overall:
            st.success(overall)
        elif '恶化' in overall:
            st.error(overall)
        else:
            st.info(overall)

        for detail in trends.get('details', []):
            st.markdown(f"- {detail}")


def display_valuation_analysis(report: dict):
    """显示估值分析"""
    valuation = report.get('valuation_comparison', {})

    if not valuation.get('success'):
        st.warning("估值数据获取失败")
        return

    # 估值水平
    level = valuation.get('valuation_level', 'N/A')
    if '低估' in level:
        st.success(f"## ✓ {level}")
    elif '高估' in level:
        st.error(f"## ✗ {level}")
    else:
        st.info(f"## ○ {level}")

    st.divider()

    # 估值指标
    col1, col2, col3 = st.columns(3)

    with col1:
        current_pe = valuation.get('current_pe', 0)
        avg_pe = valuation.get('avg_pe', 0)
        premium = valuation.get('pe_premium', 0)

        st.metric("PE（市盈率）", f"{current_pe:.1f}", f"行业{avg_pe:.1f}")
        if premium > 0:
            st.caption(f"溢价 +{premium:.0f}%")
        else:
            st.caption(f"折价 {premium:.0f}%")

    with col2:
        current_pb = valuation.get('current_pb', 0)
        avg_pb = valuation.get('avg_pb', 0)

        st.metric("PB（市净率）", f"{current_pb:.2f}", f"行业{avg_pb:.2f}")

    with col3:
        peg = valuation.get('peg', 0)
        st.metric("PEG", f"{peg:.2f}")
        if peg < 1:
            st.caption("✓ PEG<1，相对低估")
        elif peg > 2:
            st.caption("✗ PEG>2，相对高估")
        else:
            st.caption("○ PEG合理")

    st.divider()

    # 估值评价
    st.subheader("📋 估值评价")
    for analysis in valuation.get('analysis', []):
        if '✓' in analysis:
            st.success(analysis)
        elif '✗' in analysis:
            st.error(analysis)
        else:
            st.info(analysis)


def display_payback_analysis(report: dict):
    """显示回本周期分析"""
    payback = report.get('payback_analysis', {})

    buy_price = payback.get('buy_price', 0)
    if buy_price == 0:
        st.warning("回本周期数据不足")
        return

    st.markdown(f"### 💰 买入价：{buy_price:.2f} 元/股")

    st.divider()

    # 三种情景
    scenarios = payback.get('scenarios', [])

    for scenario in scenarios:
        name = scenario['name']
        prob = scenario['probability'] * 100
        years = scenario['years']
        annual_return = scenario['annual_return_pct']

        # 根据情景类型选择颜色
        if name == '悲观':
            color = "danger-box" if annual_return < 0 else "warning-box"
        elif name == '乐观':
            color = "success-box"
        else:
            color = "metric-card"

        st.markdown(f"""
        <div class="{color}">
            <h4>{name}情景（概率{prob:.0f}%）</h4>
            <p><strong>回本周期</strong>：{years}年</p>
            <p><strong>年化收益</strong>：{annual_return:.1f}%</p>
        </div>
        """, unsafe_allow_html=True)

        with st.expander(f"查看{name}情景假设"):
            st.markdown("**假设条件**：")
            for assumption in scenario['assumptions']:
                st.markdown(f"- {assumption}")

            st.markdown("**收益构成**：")
            st.markdown(f"- 累计分红：{scenario['dividend_total']:.2f}元")
            st.markdown(f"- 预期股价：{scenario['exit_price']:.2f}元")
            st.markdown(f"- 价格变动：{scenario['price_gain']:+.2f}元")

    st.divider()

    # 期望收益
    expected_return = payback.get('expected_return', 0)
    expected_years = payback.get('expected_years', 0)
    expected_annual = payback.get('expected_annual_return', 0)

    st.markdown("### 📊 概率加权期望")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("期望总回报", f"{expected_return:.1f}%")

    with col2:
        st.metric("期望回本周期", f"{expected_years:.1f}年")

    with col3:
        st.metric("期望年化收益", f"{expected_annual:.1f}%")

    conclusion = payback.get('conclusion', '')
    if '✓' in conclusion:
        st.success(conclusion)
    elif '✗' in conclusion:
        st.error(conclusion)
    else:
        st.info(conclusion)


def display_risks(report: dict):
    """显示风险提示"""
    risks = report.get('risks', [])

    st.subheader("⚠️ 风险提示")

    for risk in risks:
        if '✓' in risk:
            st.success(risk)
        elif '✗' in risk:
            st.error(risk)
        else:
            st.warning(risk)

    st.divider()

    st.info("""
    **重要提示**：
    - 本系统仅供参考，不构成投资建议
    - 投资有风险，决策需谨慎
    - 建议结合多方信息综合判断
    """)


if __name__ == "__main__":
    main()
