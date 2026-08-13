"""
分析模块 - 实现"西红柿炒鸡蛋"的投研逻辑
"""

from typing import Dict, List, Tuple
from datetime import datetime
from .config import ANALYSIS_CONFIG
from .industry_analyzer import IndustryComparator, HistoricalTrendAnalyzer, CommodityPriceMonitor, ValuationComparator
from .industry_chain_knowledge import get_industry_chain_analysis
from .industry_chain_v2 import IndustryChainV2
from .cycle_analyzer import CycleAnalyzer
from .business_model_analyzer import BusinessModelAnalyzer


class InvestmentAnalyzer:
    """投资分析器 - 实现核心分析逻辑"""

    def __init__(self):
        self.config = ANALYSIS_CONFIG
        self.industry_comparator = IndustryComparator()
        self.trend_analyzer = HistoricalTrendAnalyzer()
        self.commodity_monitor = CommodityPriceMonitor()
        self.valuation_comparator = ValuationComparator()
        self.cycle_analyzer = CycleAnalyzer()
        self.chain_v2 = IndustryChainV2()  # V2产业链知识库
        self.business_model_analyzer = BusinessModelAnalyzer()  # 商业模式分析器

    def analyze(self, stock_data: Dict) -> Dict:
        """
        完整分析流程

        Args:
            stock_data: 从DataCollector获取的数据

        Returns:
            分析报告字典
        """
        report = {
            'stock_code': stock_data.get('stock_info', {}).get('stock_code', ''),
            'stock_name': stock_data.get('stock_info', {}).get('stock_name', ''),
            'analysis_date': datetime.now().isoformat(),
            'summary': '',
            'product_analysis': {},
            'market_position': {},
            'cycle_analysis': {},
            'survival_analysis': {},
            'payback_analysis': {},
            'investment_advice': {},
            'risks': [],
            'industry_comparison': {},  # 行业对比
            'historical_trends': {},    # 历史趋势
            'valuation_comparison': {}, # 估值对比（新增）
        }

        # 1. 产品分析（需要人工输入产业链信息）
        report['product_analysis'] = self._analyze_product(stock_data)

        # 2. 市场地位分析
        report['market_position'] = self._analyze_market_position(stock_data)

        # 3. 行业对比分析
        print("  正在进行行业对比...")
        report['industry_comparison'] = self.industry_comparator.compare_with_peers(
            report['stock_code'], stock_data
        )

        # 3.5 成本对比分析（从行业对比中提取）
        report['cost_comparison'] = self._analyze_cost_comparison(
            stock_data, report['industry_comparison']
        )

        # 4. 历史趋势分析
        print("  正在分析历史趋势...")
        report['historical_trends'] = self.trend_analyzer.analyze_trends(report['stock_code'])

        # 5. 估值对比分析（新增）
        print("  正在进行估值对比...")
        report['valuation_comparison'] = self.valuation_comparator.compare_valuation(
            report['stock_code'], stock_data, report['industry_comparison']
        )

        # 6. 财务健康度分析
        report['financial_health'] = self._analyze_financial_health(stock_data)

        # 7. 商业模式分析（新增）
        print("  正在分析商业模式...")
        report['business_model'] = self.business_model_analyzer.analyze(
            stock_data,
            report['industry_comparison']
        )

        # 8. 周期分析（增强版）
        print("  正在分析行业周期...")
        report['cycle_analysis'] = self.cycle_analyzer.analyze_cycle(
            stock_data,
            report['industry_comparison'],
            report['historical_trends'],
            report['valuation_comparison']
        )

        # 9. 生存能力分析
        report['survival_analysis'] = self._analyze_survival(stock_data)

        # 9. 回本周期预测
        report['payback_analysis'] = self._calculate_payback(stock_data)

        # 10. 核心假设和失效条件（新增）
        report['core_assumptions'] = self._generate_core_assumptions(report)
        report['failure_conditions'] = self._generate_failure_conditions(report)

        # 11. 投资建议
        report['investment_advice'] = self._generate_advice(report)

        # 12. 风险提示
        report['risks'] = self._identify_risks(stock_data, report)

        # 13. 一句话总结
        report['summary'] = self._generate_summary(report)

        return report

    def _analyze_product(self, stock_data: Dict) -> Dict:
        """
        产品分析 - "西红柿炒鸡蛋"逻辑

        优先从V2知识库查询，如果没有则回退到V1
        """
        stock_info = stock_data.get('stock_info', {})
        stock_code = stock_info.get('stock_code', '')
        industry = stock_info.get('industry', '未知')

        # 1. 先尝试从V2获取
        products_data = self.chain_v2.get_products_by_company(stock_code)

        if products_data and products_data['products']:
            # V2数据可用
            company = products_data['company']
            products = products_data['products']

            # 取最重要的产品
            main_product = max(products, key=lambda p: p.get('importance_score', 0))

            # 获取产业链关系
            chain = self.chain_v2.get_product_chain(main_product['name'], max_depth=2)

            return {
                'data_version': chain.get('data_version', 'industry-chain.v2'),
                'source_status': chain.get('source_status', 'UNKNOWN'),
                'license_status': chain.get('license_status', 'UNVERIFIED'),
                'validation_status': chain.get('validation_status', 'UNKNOWN'),
                'industry': main_product.get('industry', industry),
                'company_position': company.get('position', '需要配置'),
                'chain_flow': self._build_chain_flow_from_v2(chain),
                'chain_description': '',

                'main_product': main_product['name'],
                'importance_level': main_product['level'],
                'importance_level_name': main_product['level_name'],
                'importance_score': main_product['importance_score'],
                'importance_reason': main_product['reason'],

                'value_ratio': main_product['value_ratio'],
                'value_ratio_desc': main_product['value_ratio_desc'],

                'substitutability': main_product['substitutability'],
                'substitutability_desc': main_product['substitutability_desc'],

                'tech_barrier': main_product['tech_barrier'],
                'tech_barrier_desc': main_product['tech_barrier_desc'],

                'market_concentration': main_product['market_concentration'],
                'market_concentration_desc': main_product['market_concentration_desc'],

                'analogy': main_product['analogy'],

                'all_products': products,
                'upstream_products': chain.get('upstream', []),
                'downstream_products': chain.get('downstream', []),

                'has_config': True,
                'source': chain.get('source', company.get('source', 'industry_chain_v2')),
                'confidence': company.get('confidence', 0.9),
            }

        # 2. 回退到V1
        chain_analysis = get_industry_chain_analysis(stock_code, industry)

        if chain_analysis:
            # V1数据
            products = chain_analysis.get('products', [])

            if products:
                main_product = max(products, key=lambda p: p.get('importance_score', 0))

                return {
                    'data_version': 'v1',
                    'industry': chain_analysis['industry'],
                    'company_position': chain_analysis['position'],
                    'chain_flow': chain_analysis['chain_flow'],
                    'chain_description': chain_analysis['description'],

                    'main_product': main_product['product_name'],
                    'importance_level': main_product['level'],
                    'importance_level_name': main_product['level_name'],
                    'importance_score': main_product['importance_score'],
                    'importance_reason': main_product['reason'],

                    'value_ratio': main_product['value_ratio'],
                    'value_ratio_desc': main_product['value_ratio_desc'],

                    'substitutability': main_product['substitutability'],
                    'substitutability_desc': main_product['substitutability_desc'],

                    'tech_barrier': main_product['tech_barrier'],
                    'tech_barrier_desc': main_product['tech_barrier_desc'],

                    'market_concentration': main_product['market_concentration'],
                    'market_concentration_desc': main_product['market_concentration_desc'],

                    'analogy': main_product['analogy'],

                    'all_products': products,

                    'has_config': True,
                }

        # 3. 没有配置
        return {
            'data_version': 'none',
            'industry': industry,
            'company_position': '需要配置',
            'chain_flow': '需要配置完整产业链',
            'chain_description': '',

            'main_product': '需要配置',
            'importance_level': 'B',
            'importance_level_name': 'B级-需要配置',
            'importance_score': 0,
            'importance_reason': '需要补充产业链数据',

            'value_ratio': 0,
            'value_ratio_desc': '需要配置',

            'substitutability': 'medium',
            'substitutability_desc': '需要配置',

            'tech_barrier': 'medium',
            'tech_barrier_desc': '需要配置',

            'market_concentration': 'medium',
            'market_concentration_desc': '需要配置',

            'analogy': '',

            'all_products': [],

            'has_config': False,
        }

    def _build_chain_flow_from_v2(self, chain: Dict) -> str:
        """从V2产业链数据构建流程字符串"""
        if 'error' in chain:
            return '产业链数据不完整'

        parts = []

        # 上游
        upstream = chain.get('upstream', [])
        if upstream:
            for item in reversed(upstream):  # 反转显示
                parts.append(item['product']['name'])

        # 当前
        current = chain.get('current', {})
        if current:
            parts.append(f"【{current['name']}】")  # 用括号标记当前

        # 下游
        downstream = chain.get('downstream', [])
        if downstream:
            for item in downstream:
                parts.append(item['product']['name'])

        return ' → '.join(parts) if parts else '完整产业链待配置'

    def _analyze_market_position(self, stock_data: Dict) -> Dict:
        """
        市场地位分析（结合行业对比数据）
        """
        stock_info = stock_data.get('stock_info', {})
        industry = stock_info.get('industry', '')
        market_cap = stock_info.get('total_market_cap', 0)

        # 基本判断
        if market_cap > 500:
            position_type = '行业龙头候选'
            market_share_estimate = '预估>10%'
        elif market_cap > 200:
            position_type = '重要参与者'
            market_share_estimate = '预估5-10%'
        elif market_cap > 50:
            position_type = '追随者'
            market_share_estimate = '预估<5%'
        else:
            position_type = '小型企业'
            market_share_estimate = '预估<1%'

        return {
            'industry': industry,
            'market_cap': market_cap,
            'position_type': position_type,
            'market_share': market_share_estimate,
            'is_leader': market_cap > 500,
            'ranking': '见行业对比',
            'concentration': '见行业对比',
            'description': f'总市值{market_cap:.1f}亿，初步判断为{position_type}',
        }

    def _analyze_financial_health(self, stock_data: Dict) -> Dict:
        """财务健康度分析"""
        financial = stock_data.get('financial', {})
        balance = stock_data.get('balance_sheet', {})
        income = stock_data.get('income_statement', {})

        roe = financial.get('roe', 0)
        gross_margin = financial.get('gross_margin', 0)
        net_margin = financial.get('net_margin', 0)
        debt_ratio = financial.get('debt_ratio', 0)

        # 健康度评分
        health_score = 0
        factors = []

        # ROE评分
        if roe > 0.15:
            health_score += 25
            factors.append('✓ ROE良好(>15%)')
        elif roe > 0.10:
            health_score += 15
            factors.append('○ ROE一般(10-15%)')
        else:
            factors.append('✗ ROE偏低(<10%)')

        # 毛利率评分
        if gross_margin > 0.30:
            health_score += 25
            factors.append('✓ 毛利率高(>30%)')
        elif gross_margin > 0.20:
            health_score += 15
            factors.append('○ 毛利率中等(20-30%)')
        else:
            factors.append('✗ 毛利率低(<20%)')

        # 净利率评分
        if net_margin > 0.10:
            health_score += 25
            factors.append('✓ 净利率健康(>10%)')
        elif net_margin > 0.05:
            health_score += 15
            factors.append('○ 净利率一般(5-10%)')
        else:
            factors.append('✗ 净利率低(<5%)')

        # 负债率评分
        if debt_ratio < 0.60:
            health_score += 25
            factors.append('✓ 负债率安全(<60%)')
        elif debt_ratio < 0.80:
            health_score += 15
            factors.append('○ 负债率中等(60-80%)')
        else:
            factors.append('✗ 负债率高(>80%)')

        # 评级
        if health_score >= 80:
            grade = 'A-优秀'
        elif health_score >= 60:
            grade = 'B-良好'
        elif health_score >= 40:
            grade = 'C-一般'
        else:
            grade = 'D-较差'

        return {
            'roe': roe,
            'gross_margin': gross_margin,
            'net_margin': net_margin,
            'debt_ratio': debt_ratio,
            'health_score': health_score,
            'grade': grade,
            'factors': factors,
        }

    def _analyze_cycle(self, stock_data: Dict) -> Dict:
        """
        行业周期分析（简化版）

        注：完整的周期分析需要行业数据（价格、产能、库存等）
        """
        financial = stock_data.get('financial', {})
        historical_prices = stock_data.get('historical_prices')

        # 基于盈利能力判断
        roe = financial.get('roe', 0)
        net_margin = financial.get('net_margin', 0)

        # 基于股价判断周期位置
        cycle_position = '需要行业数据'
        signals = []

        if roe < 0.05 and net_margin < 0.03:
            cycle_position = '可能处于底部'
            signals.append('盈利能力低迷')

        if not historical_prices.empty and len(historical_prices) > 60:
            # 计算价格相对位置
            latest_price = historical_prices['close'].iloc[-1]
            year_high = historical_prices['close'].tail(252).max()
            year_low = historical_prices['close'].tail(252).min()

            price_position = (latest_price - year_low) / (year_high - year_low) if year_high > year_low else 0.5

            if price_position < 0.3:
                signals.append('股价处于低位')
            elif price_position > 0.7:
                signals.append('股价处于高位')

        return {
            'position': cycle_position,
            'signals': signals,
            'confidence': 'low',  # 没有完整行业数据，置信度低
            'description': '周期判断需要补充行业数据（价格、产能、库存）',
        }

    def _analyze_survival(self, stock_data: Dict) -> Dict:
        """生存能力分析"""
        balance = stock_data.get('balance_sheet', {})
        cash_flow = stock_data.get('cash_flow', {})
        income = stock_data.get('income_statement', {})

        cash = balance.get('cash', 0)
        total_assets = balance.get('total_assets', 0)
        total_liabilities = balance.get('total_liabilities', 0)
        short_term_debt = balance.get('short_term_debt', 0)
        long_term_debt = balance.get('long_term_debt', 0)

        net_profit = income.get('net_profit', 0)
        interest_expense = income.get('interest_expense', 0)
        ebit = income.get('ebit', 0)

        operating_cf = cash_flow.get('operating_cash_flow', 0)
        capex = cash_flow.get('capex', 0)
        free_cf = cash_flow.get('free_cash_flow', 0)

        # 净现金
        total_debt = short_term_debt + long_term_debt
        net_cash = cash - total_debt

        # 利息覆盖倍数
        interest_coverage = ebit / interest_expense if interest_expense > 0 else 999

        # 能撑多久（极端情况：持续亏损）
        annual_loss_estimate = abs(net_profit) if net_profit < 0 else 0
        survival_years = cash / annual_loss_estimate if annual_loss_estimate > 0 else 999

        # 评估
        survival_grade = 'A'
        survival_notes = []

        if net_cash > 0:
            survival_notes.append(f'✓ 净现金{net_cash:.1f}亿')
        else:
            survival_notes.append(f'✗ 净负债{-net_cash:.1f}亿')
            survival_grade = 'B'

        if interest_coverage > 3:
            survival_notes.append('✓ 利息覆盖良好')
        elif interest_coverage > 1:
            survival_notes.append('○ 利息覆盖一般')
            survival_grade = 'C'
        else:
            survival_notes.append('✗ 利息覆盖不足')
            survival_grade = 'D'

        if free_cf > 0:
            survival_notes.append('✓ 自由现金流为正')
        else:
            survival_notes.append('✗ 自由现金流为负')
            if survival_grade == 'A':
                survival_grade = 'B'

        return {
            'cash': cash,
            'net_cash': net_cash,
            'interest_coverage': interest_coverage,
            'free_cash_flow': free_cf,
            'survival_years': min(survival_years, 999),
            'grade': survival_grade,
            'notes': survival_notes,
            'conclusion': self._survival_conclusion(survival_grade, survival_years),
        }

    def _survival_conclusion(self, grade: str, years: float) -> str:
        """生存能力结论"""
        if grade == 'A' and years > 10:
            return '✓ 龙头公司，能熬过周期底部'
        elif grade in ['A', 'B'] and years > 5:
            return '○ 财务稳健，短期无忧'
        elif grade == 'C' or years < 3:
            return '⚠ 存在压力，需密切关注'
        else:
            return '✗ 生存压力大，风险较高'

    def _calculate_payback(self, stock_data: Dict) -> Dict:
        """
        回本周期计算（三种情景）

        注：这是核心输出，需要基于详细假设
        """
        price_info = stock_data.get('realtime_price', {})
        financial = stock_data.get('financial', {})
        dividend_history = stock_data.get('dividend_history', [])

        current_price = price_info.get('current_price', 0)
        if current_price == 0:
            return {
                'buy_price': 0,
                'scenarios': [],
                'expected_return': 0,
                'expected_years': 0,
                'conclusion': '无法计算：缺少价格数据',
            }

        # 历史分红
        avg_dividend = 0
        if dividend_history:
            dividends = [d.get('dividend_per_share', 0) for d in dividend_history]
            avg_dividend = sum(dividends) / len(dividends)

        # 当前ROE
        roe = financial.get('roe', 0)

        # 三种情景
        scenarios = [
            self._scenario_pessimistic(current_price, roe, avg_dividend),
            self._scenario_base(current_price, roe, avg_dividend),
            self._scenario_optimistic(current_price, roe, avg_dividend),
        ]

        # 概率加权
        expected_return = sum(s['total_return_pct'] * s['probability'] for s in scenarios)
        weighted_years = sum(s['years'] * s['probability'] for s in scenarios)

        return {
            'buy_price': current_price,
            'scenarios': scenarios,
            'expected_return': expected_return,
            'expected_years': weighted_years,
            'expected_annual_return': expected_return / weighted_years if weighted_years > 0 else 0,
            'conclusion': self._payback_conclusion(expected_return, weighted_years),
        }

    def _scenario_pessimistic(self, buy_price: float, roe: float, avg_dividend: float) -> Dict:
        """悲观情景（20%概率）"""
        years = 3
        # 假设周期不反转，微利或小亏
        annual_dividend = avg_dividend * 0.3  # 分红大幅减少
        total_dividend = annual_dividend * years
        exit_price = buy_price * 0.85  # 股价下跌15%
        price_gain = exit_price - buy_price
        total_return = total_dividend + price_gain

        return {
            'name': '悲观',
            'probability': 0.20,
            'years': years,
            'assumptions': ['周期持续低迷', '公司微利或小亏', '分红大幅减少'],
            'dividend_total': total_dividend,
            'exit_price': exit_price,
            'price_gain': price_gain,
            'total_return': total_return,
            'total_return_pct': (total_return / buy_price * 100) if buy_price > 0 else 0,
            'annual_return_pct': (total_return / buy_price / years * 100) if buy_price > 0 and years > 0 else 0,
        }

    def _scenario_base(self, buy_price: float, roe: float, avg_dividend: float) -> Dict:
        """基准情景（60%概率）"""
        years = 3
        # 假设周期反转，盈利恢复
        annual_dividend = avg_dividend * 0.8  # 分红部分恢复
        total_dividend = annual_dividend * years
        exit_price = buy_price * 1.4  # 股价上涨40%
        price_gain = exit_price - buy_price
        total_return = total_dividend + price_gain

        return {
            'name': '基准',
            'probability': 0.60,
            'years': years,
            'assumptions': ['2年内周期反转', '盈利逐步恢复', '分红恢复到历史水平'],
            'dividend_total': total_dividend,
            'exit_price': exit_price,
            'price_gain': price_gain,
            'total_return': total_return,
            'total_return_pct': (total_return / buy_price * 100) if buy_price > 0 else 0,
            'annual_return_pct': (total_return / buy_price / years * 100) if buy_price > 0 and years > 0 else 0,
        }

    def _scenario_optimistic(self, buy_price: float, roe: float, avg_dividend: float) -> Dict:
        """乐观情景（20%概率）"""
        years = 2
        # 假设强力反转，份额提升
        annual_dividend = avg_dividend * 1.2  # 分红超历史水平
        total_dividend = annual_dividend * years
        exit_price = buy_price * 1.7  # 股价上涨70%
        price_gain = exit_price - buy_price
        total_return = total_dividend + price_gain

        return {
            'name': '乐观',
            'probability': 0.20,
            'years': years,
            'assumptions': ['快速反转', '市场份额提升', '盈利超预期'],
            'dividend_total': total_dividend,
            'exit_price': exit_price,
            'price_gain': price_gain,
            'total_return': total_return,
            'total_return_pct': (total_return / buy_price * 100) if buy_price > 0 else 0,
            'annual_return_pct': (total_return / buy_price / years * 100) if buy_price > 0 and years > 0 else 0,
        }

    def _payback_conclusion(self, expected_return: float, expected_years: float) -> str:
        """回本周期结论"""
        annual_return = expected_return / expected_years if expected_years > 0 else 0

        if annual_return > 15:
            return f'✓ 期望年化{annual_return:.1f}%，值得投资'
        elif annual_return > 10:
            return f'○ 期望年化{annual_return:.1f}%，可以考虑'
        elif annual_return > 5:
            return f'⚠ 期望年化{annual_return:.1f}%，回报一般'
        else:
            return f'✗ 期望年化{annual_return:.1f}%，回报偏低'

    def _generate_advice(self, report: Dict) -> Dict:
        """生成投资建议"""
        payback = report.get('payback_analysis', {})
        survival = report.get('survival_analysis', {})
        financial = report.get('financial_health', {})

        expected_return = payback.get('expected_annual_return', 0)
        survival_grade = survival.get('grade', 'D')
        financial_grade = financial.get('grade', 'D-较差')

        # 综合评分
        score = 0
        reasons = []

        # 回报评分
        if expected_return > 15:
            score += 40
            reasons.append('✓ 预期回报高')
        elif expected_return > 10:
            score += 25
            reasons.append('○ 预期回报中等')
        else:
            reasons.append('✗ 预期回报低')

        # 生存能力评分
        if survival_grade == 'A':
            score += 30
            reasons.append('✓ 财务安全')
        elif survival_grade == 'B':
            score += 20
            reasons.append('○ 财务一般')
        else:
            reasons.append('✗ 财务风险')

        # 财务健康度评分
        if financial_grade.startswith('A'):
            score += 30
            reasons.append('✓ 财务优秀')
        elif financial_grade.startswith('B'):
            score += 20
            reasons.append('○ 财务良好')
        else:
            reasons.append('✗ 财务欠佳')

        # 建议
        if score >= 70:
            action = '💡 可以买入'
            strategy = '分3批建仓，每批间隔1-2周'
            stop_loss = '设置-20%止损线'
        elif score >= 50:
            action = '○ 谨慎观望'
            strategy = '等待更明确信号'
            stop_loss = '如买入，设置-15%止损线'
        else:
            action = '✗ 不建议买入'
            strategy = '风险较高，等待基本面改善'
            stop_loss = 'N/A'

        return {
            'score': score,
            'action': action,
            'strategy': strategy,
            'stop_loss': stop_loss,
            'reasons': reasons,
        }

    def _identify_risks(self, stock_data: Dict, report: Dict) -> List[str]:
        """识别风险"""
        risks = []

        # 周期风险
        cycle = report.get('cycle_analysis', {})
        if '底部' in cycle.get('position', ''):
            risks.append('⚠ 周期底部，反转时间不确定')

        # 财务风险
        financial = report.get('financial_health', {})
        if financial.get('grade', '').startswith('D'):
            risks.append('⚠ 财务健康度较差')

        # 生存风险
        survival = report.get('survival_analysis', {})
        if survival.get('grade') in ['C', 'D']:
            risks.append('⚠ 现金流或债务压力')

        # 估值风险（新增）
        valuation = report.get('valuation_comparison', {})
        if valuation.get('success'):
            if valuation.get('valuation_level') == '相对高估':
                risks.append('⚠ 估值相对行业偏高')
            if valuation.get('pe_premium', 0) > 50:
                risks.append('⚠ PE溢价超过50%，估值压力大')

        # 历史趋势风险（新增）
        trends = report.get('historical_trends', {})
        if trends.get('success'):
            if '恶化' in trends.get('overall', ''):
                risks.append('⚠ 财务指标呈恶化趋势')

        # 估值风险
        stock_info = stock_data.get('stock_info', {})
        pe = stock_info.get('pe_ratio', 0)
        if pe > 50 and pe < 999:
            risks.append('⚠ 估值偏高（PE>50）')

        # 数据缺失风险
        if not stock_data.get('financial'):
            risks.append('⚠ 部分财务数据缺失，分析可能不完整')

        if not risks:
            risks.append('✓ 暂无明显重大风险')

        return risks

    def _generate_summary(self, report: Dict) -> str:
        """生成一句话总结"""
        stock_name = report.get('stock_name', '')
        position = report.get('market_position', {}).get('position_type', '')
        cycle = report.get('cycle_analysis', {}).get('position', '')
        expected_years = report.get('payback_analysis', {}).get('expected_years', 0)
        action = report.get('investment_advice', {}).get('action', '')

        summary = f"{stock_name}，{position}，{cycle}，"
        if expected_years > 0:
            summary += f"预期{expected_years:.1f}年回本，{action}"
        else:
            summary += f"{action}"

        return summary

    def _generate_core_assumptions(self, report: Dict) -> Dict:
        """生成核心假设列表"""
        payback = report.get('payback_analysis', {})
        financial = report.get('financial_health', {})
        cycle = report.get('cycle_analysis', {})
        product = report.get('product_analysis', {})
        market = report.get('market_position', {})
        valuation = report.get('valuation_comparison', {})

        # 基准情景的假设
        base_scenario = None
        for scenario in payback.get('scenarios', []):
            if scenario['name'] == '基准':
                base_scenario = scenario
                break

        assumptions = {'category': '基准情景假设', 'items': []}
        if base_scenario:
            assumptions['items'] = base_scenario.get('assumptions', [])

        # 补充关键假设
        additional = []

        # 行业周期假设
        if '底部' in cycle.get('position', ''):
            additional.append('✓ 行业周期在2-3年内反转向上')
        else:
            additional.append('✓ 行业需求保持稳定增长')

        # 市场地位假设
        if market.get('is_leader'):
            additional.append('✓ 保持行业龙头地位，市场份额不下降')
        else:
            additional.append('✓ 市场份额保持稳定或小幅提升')

        # 产品竞争力假设
        if product.get('has_config'):
            level = product.get('importance_level', 'B')
            if level == 'A':
                additional.append('✓ 核心产品保持不可替代性，技术路线不变')
            else:
                additional.append('✓ 产品保持竞争力，无重大技术替代')

        # 盈利能力假设
        roe = financial.get('roe', 0)
        if roe > 0.15:
            additional.append('✓ ROE保持在15%以上')
        elif roe > 0.10:
            additional.append('✓ ROE逐步恢复到15%左右')
        else:
            additional.append('✓ 盈利能力从低点恢复，ROE回升到10%+')

        # 估值假设
        if valuation.get('success'):
            level = valuation.get('valuation_level', '')
            if '低估' in level:
                additional.append('✓ 估值修复，PE回归行业平均水平')
            elif '高估' in level:
                additional.append('⚠ 估值维持，盈利增长消化估值')

        assumptions['additional'] = additional
        return assumptions

    def _generate_failure_conditions(self, report: Dict) -> Dict:
        """生成失效条件列表"""
        product = report.get('product_analysis', {})
        financial = report.get('financial_health', {})
        market = report.get('market_position', {})

        conditions = {'category': '假设失效条件', 'critical': [], 'warning': []}

        # 致命条件
        industry = product.get('industry', '所在行业')
        conditions['critical'].append(f'✗ {industry}需求断崖式下跌（政策转向/技术颠覆）')

        level = product.get('importance_level', 'B')
        if level == 'A':
            main_product = product.get('main_product', '核心产品')
            conditions['critical'].append(f'✗ {main_product}被新技术完全替代')
        else:
            conditions['critical'].append('✗ 关键产品技术路线被颠覆')

        if market.get('is_leader'):
            conditions['critical'].append('✗ 市场份额下降超过30%（失去龙头地位）')
        else:
            conditions['critical'].append('✗ 市场份额持续下降，沦为边缘企业')

        conditions['critical'].append('✗ 出现重大财务危机（债务违约、资不抵债）')
        conditions['critical'].append('✗ 连续2年以上亏损，且看不到扭亏希望')

        # 警示条件
        conditions['warning'].append('⚠ 行业周期持续低迷超过预期时间（3年+）')
        conditions['warning'].append('⚠ 行业竞争白热化，毛利率持续下降超过30%')
        conditions['warning'].append('⚠ 市场份额连续2年下降（降幅10-20%）')
        
        roe = financial.get('roe', 0)
        if roe > 0.15:
            conditions['warning'].append('⚠ ROE从高位持续下降，跌破10%')
        else:
            conditions['warning'].append('⚠ ROE持续低于8%，无改善迹象')

        conditions['warning'].append('⚠ 估值持续高位，盈利增长无法消化估值')
        conditions['warning'].append('⚠ 现金流持续恶化，生存压力加大')
        conditions['warning'].append('⚠ 管理层重大变动或出现治理问题')
        conditions['warning'].append('⚠ 出现重大不利政策（如补贴取消、监管收紧）')

        return conditions

    def _analyze_cost_comparison(self, stock_data: Dict, industry_comparison: Dict) -> Dict:
        """
        成本对比分析（公司 vs 行业）
        
        从行业对比数据中提取，单独展示成本优势
        """
        if not industry_comparison.get('success'):
            return {
                'has_data': False,
                'message': '行业对比数据不足',
            }

        financial = stock_data.get('financial', {})
        
        # 公司数据
        company_roe = financial.get('roe', 0)
        company_gross_margin = financial.get('gross_margin', 0)
        company_net_margin = financial.get('net_margin', 0)

        # 行业平均数据
        peer_avg = industry_comparison.get('peer_average', {})
        avg_roe = peer_avg.get('roe', 0)
        avg_gross_margin = peer_avg.get('gross_margin', 0)
        avg_net_margin = peer_avg.get('net_margin', 0)

        # 计算差异
        roe_diff = company_roe - avg_roe
        gross_margin_diff = company_gross_margin - avg_gross_margin
        net_margin_diff = company_net_margin - avg_net_margin

        # 判断成本优势
        advantages = []
        disadvantages = []

        # ROE对比
        if roe_diff > 0.05:  # 高5个百分点以上
            advantages.append({
                'indicator': 'ROE',
                'company': f'{company_roe*100:.1f}%',
                'industry': f'{avg_roe*100:.1f}%',
                'diff': f'+{roe_diff*100:.1f}%',
                'description': 'ROE显著高于行业，资本使用效率优秀',
            })
        elif roe_diff > 0.02:
            advantages.append({
                'indicator': 'ROE',
                'company': f'{company_roe*100:.1f}%',
                'industry': f'{avg_roe*100:.1f}%',
                'diff': f'+{roe_diff*100:.1f}%',
                'description': 'ROE高于行业平均',
            })
        elif roe_diff < -0.05:
            disadvantages.append({
                'indicator': 'ROE',
                'company': f'{company_roe*100:.1f}%',
                'industry': f'{avg_roe*100:.1f}%',
                'diff': f'{roe_diff*100:.1f}%',
                'description': 'ROE显著低于行业，盈利能力较弱',
            })
        elif roe_diff < -0.02:
            disadvantages.append({
                'indicator': 'ROE',
                'company': f'{company_roe*100:.1f}%',
                'industry': f'{avg_roe*100:.1f}%',
                'diff': f'{roe_diff*100:.1f}%',
                'description': 'ROE低于行业平均',
            })

        # 毛利率对比
        if gross_margin_diff > 0.10:
            advantages.append({
                'indicator': '毛利率',
                'company': f'{company_gross_margin*100:.1f}%',
                'industry': f'{avg_gross_margin*100:.1f}%',
                'diff': f'+{gross_margin_diff*100:.1f}%',
                'description': '毛利率显著高于行业，产品溢价能力强或成本控制优秀',
            })
        elif gross_margin_diff > 0.05:
            advantages.append({
                'indicator': '毛利率',
                'company': f'{company_gross_margin*100:.1f}%',
                'industry': f'{avg_gross_margin*100:.1f}%',
                'diff': f'+{gross_margin_diff*100:.1f}%',
                'description': '毛利率高于行业，有一定成本优势',
            })
        elif gross_margin_diff < -0.10:
            disadvantages.append({
                'indicator': '毛利率',
                'company': f'{company_gross_margin*100:.1f}%',
                'industry': f'{avg_gross_margin*100:.1f}%',
                'diff': f'{gross_margin_diff*100:.1f}%',
                'description': '毛利率显著低于行业，成本劣势明显或竞争激烈',
            })
        elif gross_margin_diff < -0.05:
            disadvantages.append({
                'indicator': '毛利率',
                'company': f'{company_gross_margin*100:.1f}%',
                'industry': f'{avg_gross_margin*100:.1f}%',
                'diff': f'{gross_margin_diff*100:.1f}%',
                'description': '毛利率低于行业，成本压力较大',
            })

        # 净利率对比
        if net_margin_diff > 0.05:
            advantages.append({
                'indicator': '净利率',
                'company': f'{company_net_margin*100:.1f}%',
                'industry': f'{avg_net_margin*100:.1f}%',
                'diff': f'+{net_margin_diff*100:.1f}%',
                'description': '净利率显著高于行业，综合成本控制优秀',
            })
        elif net_margin_diff > 0.02:
            advantages.append({
                'indicator': '净利率',
                'company': f'{company_net_margin*100:.1f}%',
                'industry': f'{avg_net_margin*100:.1f}%',
                'diff': f'+{net_margin_diff*100:.1f}%',
                'description': '净利率高于行业',
            })
        elif net_margin_diff < -0.05:
            disadvantages.append({
                'indicator': '净利率',
                'company': f'{company_net_margin*100:.1f}%',
                'industry': f'{avg_net_margin*100:.1f}%',
                'diff': f'{net_margin_diff*100:.1f}%',
                'description': '净利率显著低于行业，费用控制或税负较高',
            })
        elif net_margin_diff < -0.02:
            disadvantages.append({
                'indicator': '净利率',
                'company': f'{company_net_margin*100:.1f}%',
                'industry': f'{avg_net_margin*100:.1f}%',
                'diff': f'{net_margin_diff*100:.1f}%',
                'description': '净利率低于行业',
            })

        # 综合判断
        advantage_count = len(advantages)
        disadvantage_count = len(disadvantages)

        if advantage_count > disadvantage_count:
            conclusion = '✓ 成本优势明显'
            level = 'advantage'
        elif advantage_count < disadvantage_count:
            conclusion = '✗ 成本劣势明显'
            level = 'disadvantage'
        else:
            conclusion = '○ 成本与行业持平'
            level = 'neutral'

        return {
            'has_data': True,
            'conclusion': conclusion,
            'level': level,
            'advantages': advantages,
            'disadvantages': disadvantages,
            'company_metrics': {
                'roe': f'{company_roe*100:.1f}%',
                'gross_margin': f'{company_gross_margin*100:.1f}%',
                'net_margin': f'{company_net_margin*100:.1f}%',
            },
            'industry_metrics': {
                'roe': f'{avg_roe*100:.1f}%',
                'gross_margin': f'{avg_gross_margin*100:.1f}%',
                'net_margin': f'{avg_net_margin*100:.1f}%',
            },
        }
