"""
商业模式分析模块
从CEO/股东视角分析公司商业模式
"""

from typing import Dict, List, Optional
from datetime import datetime


class BusinessModelAnalyzer:
    """商业模式分析器"""

    def __init__(self):
        pass

    def analyze(self, stock_data: Dict, industry_analysis: Dict = None) -> Dict:
        """
        完整商业模式分析

        Args:
            stock_data: 公司财务和基本数据
            industry_analysis: 行业分析数据（可选）

        Returns:
            商业模式分析报告
        """
        financial = stock_data.get('financial', {})
        stock_info = stock_data.get('stock_info', {})

        report = {
            'stock_code': stock_info.get('stock_code', ''),
            'stock_name': stock_info.get('stock_name', ''),
            'analysis_date': datetime.now().isoformat(),

            # 1. 盈利来源分析
            'earnings_sources': self._analyze_earnings_sources(stock_data),

            # 2. 客户价值分析
            'customer_value': self._analyze_customer_value(stock_data),

            # 3. 护城河分析
            'moat': self._analyze_moat(stock_data, industry_analysis),

            # 4. 定价能力分析
            'pricing_power': self._analyze_pricing_power(stock_data, industry_analysis),

            # 5. 盈利模式分析
            'profit_model': self._analyze_profit_model(stock_data),

            # 6. CEO视角
            'ceo_perspective': self._from_ceo_perspective(stock_data),

            # 7. 股东视角
            'shareholder_perspective': self._from_shareholder_perspective(stock_data),
        }

        return report

    def _analyze_earnings_sources(self, stock_data: Dict) -> List[Dict]:
        """
        盈利来源分析

        回答：公司靠什么赚钱？
        """
        financial = stock_data.get('financial', {})
        stock_info = stock_data.get('stock_info', {})

        # TODO: 需要从财报获取分产品收入数据
        # 当前用主营业务代替
        main_business = stock_info.get('主营业务', '暂无数据')

        sources = []

        # 主要产品/业务
        # 这里应该从年报中提取，暂时用占位符
        sources.append({
            'product': '主营产品',  # TODO: 从年报提取
            'revenue_share': 1.0,  # TODO: 计算实际占比
            'profit_share': None,  # TODO: 从分部报告提取
            'customer_type': '待确认',  # TODO: 分析客户群体
            'purchase_reason': '待分析',  # 核心分析点
            'system_layer': '待确认',  # 核心/关键/重要/辅助
            'criticality': '待确认',  # 对客户的重要性
            'unit_value': None,  # 单位价值
            'switching_cost': '待评估',  # 转换成本
            'competitive_advantage': '待分析',  # 竞争优势
            'source': 'placeholder',
        })

        return sources

    def _analyze_customer_value(self, stock_data: Dict) -> Dict:
        """
        客户价值分析

        核心问题：客户为什么买我们的产品？
        """
        financial = stock_data.get('financial', {})

        # 分析维度
        reasons = {
            'performance': None,  # 性能优势
            'cost': None,  # 成本优势
            'supply_stability': None,  # 供应保障
            'technical_support': None,  # 技术支持
            'brand': None,  # 品牌溢价
            'integration': None,  # 系统集成
            'customization': None,  # 定制化
        }

        # 基于财务数据推断
        gross_margin = financial.get('gross_margin', 0)
        roe = financial.get('roe', 0)

        # 推断逻辑
        if gross_margin > 0.4:
            reasons['brand'] = '毛利率高，可能有品牌溢价或技术优势'
        elif gross_margin < 0.15:
            reasons['cost'] = '毛利率低，可能走成本领先战略'

        if roe > 0.20:
            reasons['performance'] = 'ROE高，经营效率优秀'

        return {
            'purchase_reasons': reasons,
            'main_value_proposition': self._identify_main_value(reasons),
            'analysis_note': '基于财务数据推断，需要结合年报和研报验证',
        }

    def _identify_main_value(self, reasons: Dict) -> str:
        """识别主要价值主张"""
        # 简单推断逻辑
        for key, value in reasons.items():
            if value:
                return f'初步推断：{key}'
        return '需要进一步分析'

    def _analyze_moat(self, stock_data: Dict, industry_analysis: Dict = None) -> Dict:
        """
        护城河分析

        分析公司的竞争优势是否可持续
        """
        financial = stock_data.get('financial', {})

        moat_types = []
        moat_strength = 'unknown'

        roe = financial.get('roe', 0)
        gross_margin = financial.get('gross_margin', 0)
        net_margin = financial.get('net_margin', 0)

        # 判断护城河类型
        if roe > 0.20 and gross_margin > 0.30:
            moat_types.append('品牌/技术优势')
            moat_strength = '强'
        elif roe > 0.15:
            moat_types.append('规模效应')
            moat_strength = '中'

        # 从行业对比看护城河
        if industry_analysis:
            # TODO: 与行业对比
            pass

        return {
            'types': moat_types if moat_types else ['待确认'],
            'strength': moat_strength,
            'sustainability': '需要结合行业分析',
            'switching_cost': '待评估',
            'network_effect': False,  # 大多数制造业没有网络效应
            'scale_advantage': roe > 0.15,
            'analysis_basis': '基于财务指标初步判断',
        }

    def _analyze_pricing_power(self, stock_data: Dict, industry_analysis: Dict = None) -> Dict:
        """
        定价能力分析

        回答：公司能不能涨价？成本上涨能否传导？
        """
        financial = stock_data.get('financial', {})

        gross_margin = financial.get('gross_margin', 0)

        # 推断定价能力
        if gross_margin > 0.50:
            power_level = '强'
            description = '毛利率极高，有很强的定价权'
        elif gross_margin > 0.30:
            power_level = '中'
            description = '有一定定价能力'
        elif gross_margin > 0.15:
            power_level = '弱'
            description = '定价能力较弱，可能是价格接受者'
        else:
            power_level = '极弱'
            description = '几乎没有定价权，激烈竞争'

        return {
            'power_level': power_level,
            'description': description,
            'can_pass_cost': power_level in ['强', '中'],
            'pricing_model': self._identify_pricing_model(gross_margin),
            'analysis_note': '基于毛利率推断，需要结合行业动态验证',
        }

    def _identify_pricing_model(self, gross_margin: float) -> str:
        """识别定价模式"""
        if gross_margin > 0.50:
            return '品牌/技术定价'
        elif gross_margin > 0.30:
            return '价值定价'
        elif gross_margin > 0.15:
            return '市场定价'
        else:
            return '成本加成'

    def _analyze_profit_model(self, stock_data: Dict) -> Dict:
        """
        盈利模式分析

        回答：怎么赚钱？现金流特征？
        """
        financial = stock_data.get('financial', {})
        stock_info = stock_data.get('stock_info', {})

        industry = stock_info.get('industry', '未知')

        # 根据行业推断盈利模式
        if '白酒' in industry or '食品' in industry:
            earning_method = '卖产品（消费品）'
            cash_flow_model = '预收款或短账期'
        elif '软件' in industry or 'SaaS' in industry:
            earning_method = '卖服务（订阅制）'
            cash_flow_model = '预收款'
        elif '制造' in industry or '设备' in industry:
            earning_method = '卖产品（工业品）'
            cash_flow_model = '有账期'
        else:
            earning_method = '待确认'
            cash_flow_model = '待确认'

        return {
            'earning_method': earning_method,
            'cash_flow_model': cash_flow_model,
            'capital_intensity': self._assess_capital_intensity(financial),
            'analysis_basis': '基于行业特征推断',
        }

    def _assess_capital_intensity(self, financial: Dict) -> str:
        """评估资本密集度"""
        debt_ratio = financial.get('debt_ratio', 0)

        if debt_ratio > 0.6:
            return '高（重资产）'
        elif debt_ratio > 0.4:
            return '中等'
        else:
            return '低（轻资产）'

    def _from_ceo_perspective(self, stock_data: Dict) -> Dict:
        """
        从CEO视角看公司

        CEO的核心任务：
        1. 找到好生意（选赛道）
        2. 建立护城河（建壁垒）
        3. 持续投入（保领先）
        4. 管理风险（活下来）
        """
        financial = stock_data.get('financial', {})
        stock_info = stock_data.get('stock_info', {})

        roe = financial.get('roe', 0)
        gross_margin = financial.get('gross_margin', 0)
        debt_ratio = financial.get('debt_ratio', 0)

        # 评估CEO的各项任务
        tasks = {
            'choose_track': {
                'score': self._score_track(roe, gross_margin),
                'comment': self._comment_track(roe, gross_margin),
            },
            'build_moat': {
                'score': self._score_moat(roe, gross_margin),
                'comment': self._comment_moat(roe, gross_margin),
            },
            'continuous_investment': {
                'score': 'unknown',
                'comment': '需要查看资本开支数据',
            },
            'risk_management': {
                'score': self._score_risk(debt_ratio),
                'comment': self._comment_risk(debt_ratio),
            },
        }

        return {
            'tasks_evaluation': tasks,
            'overall_assessment': self._overall_ceo_assessment(tasks),
        }

    def _score_track(self, roe: float, margin: float) -> str:
        """评估赛道选择"""
        if roe > 0.15 and margin > 0.20:
            return '优秀'
        elif roe > 0.10:
            return '良好'
        else:
            return '一般'

    def _comment_track(self, roe: float, margin: float) -> str:
        """评论赛道选择"""
        if roe > 0.15:
            return '选择了盈利能力强的赛道'
        elif roe > 0.10:
            return '赛道盈利能力中等'
        else:
            return '赛道盈利能力较弱，或处于周期底部'

    def _score_moat(self, roe: float, margin: float) -> str:
        """评估护城河建设"""
        if roe > 0.20:
            return '强'
        elif roe > 0.15:
            return '中'
        else:
            return '弱'

    def _comment_moat(self, roe: float, margin: float) -> str:
        """评论护城河"""
        if roe > 0.20:
            return '建立了较强的竞争优势'
        elif roe > 0.15:
            return '有一定竞争优势'
        else:
            return '竞争优势不明显'

    def _score_risk(self, debt_ratio: float) -> str:
        """评估风险管理"""
        if debt_ratio < 0.4:
            return '优秀'
        elif debt_ratio < 0.6:
            return '良好'
        else:
            return '需关注'

    def _comment_risk(self, debt_ratio: float) -> str:
        """评论风险管理"""
        if debt_ratio < 0.4:
            return '财务稳健，抗风险能力强'
        elif debt_ratio < 0.6:
            return '财务健康，风险可控'
        else:
            return '负债率较高，周期底部有压力'

    def _overall_ceo_assessment(self, tasks: Dict) -> str:
        """CEO整体评估"""
        # 简单汇总
        return '基于财务数据的初步评估，完整评估需要结合战略和执行细节'

    def _from_shareholder_perspective(self, stock_data: Dict) -> Dict:
        """
        从股东视角看投资回报

        股东关心：
        1. 利润增长（业务扩张）
        2. 估值提升（市场认可）
        3. 分红（现金回报）
        """
        financial = stock_data.get('financial', {})
        stock_info = stock_data.get('stock_info', {})

        roe = financial.get('roe', 0)
        pe = stock_info.get('pe_ratio', 0)

        return {
            'profit_growth_potential': self._assess_growth_potential(roe),
            'valuation_room': self._assess_valuation_room(pe, roe),
            'dividend_policy': self._assess_dividend(financial),
            'total_return_sources': self._identify_return_sources(roe, pe),
            'investment_logic': self._summarize_investment_logic(roe, pe),
        }

    def _assess_growth_potential(self, roe: float) -> str:
        """评估利润增长潜力"""
        if roe > 0.20:
            return '高（高ROE可快速扩张）'
        elif roe > 0.15:
            return '中等'
        else:
            return '低（盈利能力弱）'

    def _assess_valuation_room(self, pe: float, roe: float) -> str:
        """评估估值提升空间"""
        if pe <= 0 or roe <= 0:
            return '待确认'

        if pe < 15 and roe > 0.15:
            return '大（低估值+高ROE）'
        elif pe < 20:
            return '中等'
        else:
            return '小（估值已较高）'

    def _assess_dividend(self, financial: Dict) -> str:
        """评估分红政策"""
        # TODO: 需要分红数据
        return '需要查看历史分红数据'

    def _identify_return_sources(self, roe: float, pe: float) -> List[str]:
        """识别回报来源"""
        sources = []

        if roe > 0.15:
            sources.append('利润增长')

        if pe < 15:
            sources.append('估值修复')

        if not sources:
            sources.append('需依赖周期反转或特殊事件')

        return sources

    def _summarize_investment_logic(self, roe: float, pe: float) -> str:
        """总结投资逻辑"""
        if roe > 0.20 and pe < 20:
            return '优质公司+合理估值'
        elif roe > 0.15:
            return '成长型投资'
        elif pe < 10:
            return '价值型投资（困境反转）'
        else:
            return '需要更深入分析'


# 测试代码
if __name__ == "__main__":
    analyzer = BusinessModelAnalyzer()

    # 测试数据
    test_data = {
        'stock_info': {
            'stock_code': '600438',
            'stock_name': '通威股份',
            'industry': '光伏设备',
            'pe_ratio': 12.5,
        },
        'financial': {
            'roe': 0.075,
            'gross_margin': 0.15,
            'net_margin': 0.036,
            'debt_ratio': 0.55,
        }
    }

    report = analyzer.analyze(test_data)

    print("=" * 60)
    print("商业模式分析测试")
    print("=" * 60)
    print(f"\n公司：{report['stock_name']}")
    print(f"\n1. 盈利来源：{len(report['earnings_sources'])}个产品/业务")
    print(f"\n2. 客户价值主张：{report['customer_value']['main_value_proposition']}")
    print(f"\n3. 护城河类型：{report['moat']['types']}")
    print(f"   护城河强度：{report['moat']['strength']}")
    print(f"\n4. 定价能力：{report['pricing_power']['power_level']}")
    print(f"   {report['pricing_power']['description']}")
    print(f"\n5. CEO视角评估：")
    for task, evaluation in report['ceo_perspective']['tasks_evaluation'].items():
        print(f"   {task}: {evaluation['score']} - {evaluation['comment']}")
    print(f"\n6. 股东回报来源：{', '.join(report['shareholder_perspective']['total_return_sources'])}")
    print(f"   投资逻辑：{report['shareholder_perspective']['investment_logic']}")
