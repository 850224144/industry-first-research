"""
周期判断增强模块 - 基于多维度信号判断行业周期位置
"""

import pandas as pd
from typing import Dict, List, Tuple


class CycleAnalyzer:
    """行业周期分析器"""

    def __init__(self):
        self.signals = []
        self.position = None
        self.confidence = 'low'

    def analyze_cycle(self, stock_data: Dict, industry_comparison: Dict, historical_trends: Dict, valuation: Dict) -> Dict:
        """
        综合分析行业周期位置

        基于5个信号：
        1. 估值信号（PB历史分位数）
        2. 盈利信号（ROE趋势）
        3. 景气度信号（毛利率趋势）
        4. 股价信号（相对历史位置）
        5. 行业对比信号（相对行业表现）
        """
        self.signals = []
        signal_count = {'bottom': 0, 'top': 0, 'up': 0, 'down': 0}

        # 信号1：估值信号（PB分位数）
        valuation_signal = self._analyze_valuation_signal(stock_data, valuation)
        self.signals.append(valuation_signal)
        if valuation_signal['position']:
            signal_count[valuation_signal['position']] += 1

        # 信号2：盈利信号（ROE趋势）
        profitability_signal = self._analyze_profitability_signal(stock_data, historical_trends)
        self.signals.append(profitability_signal)
        if profitability_signal['position']:
            signal_count[profitability_signal['position']] += 1

        # 信号3：景气度信号（毛利率趋势）
        prosperity_signal = self._analyze_prosperity_signal(historical_trends)
        self.signals.append(prosperity_signal)
        if prosperity_signal['position']:
            signal_count[prosperity_signal['position']] += 1

        # 信号4：股价信号（历史位置）
        price_signal = self._analyze_price_signal(stock_data)
        self.signals.append(price_signal)
        if price_signal['position']:
            signal_count[price_signal['position']] += 1

        # 信号5：行业对比信号
        industry_signal = self._analyze_industry_signal(industry_comparison, historical_trends)
        self.signals.append(industry_signal)
        if industry_signal['position']:
            signal_count[industry_signal['position']] += 1

        # 综合判断
        position, confidence = self._综合判断(signal_count)

        # 预测反转时间
        reversal_time = self._estimate_reversal_time(position, self.signals)

        return {
            'position': position,
            'confidence': confidence,
            'signals': self.signals,
            'signal_summary': signal_count,
            'reversal_estimate': reversal_time,
            'description': self._generate_description(position, confidence, signal_count),
        }

    def _analyze_valuation_signal(self, stock_data: Dict, valuation: Dict) -> Dict:
        """
        信号1：估值信号

        基于PB判断估值位置
        - PB < 1.5 且低于行业平均 → 底部信号
        - PB > 5 且高于行业平均 → 顶部信号
        """
        stock_info = stock_data.get('stock_info', {})
        pb = stock_info.get('pb_ratio', 0)

        signal = {
            'name': '估值信号',
            'indicator': 'PB',
            'value': pb,
            'position': None,
            'strength': 'weak',
            'description': '',
        }

        if pb <= 0:
            signal['description'] = '数据不足'
            return signal

        # 与行业对比
        if valuation.get('success'):
            avg_pb = valuation.get('avg_pb', 0)
            pb_premium = valuation.get('pb_premium', 0)

            if pb < 1.5 and pb_premium < -20:
                signal['position'] = 'bottom'
                signal['strength'] = 'strong'
                signal['description'] = f'PB {pb:.2f}，低于净资产且折价{-pb_premium:.0f}%，估值底部'
            elif pb < 2.0 and pb_premium < 0:
                signal['position'] = 'bottom'
                signal['strength'] = 'medium'
                signal['description'] = f'PB {pb:.2f}，折价{-pb_premium:.0f}%，估值偏低'
            elif pb > 5.0 and pb_premium > 30:
                signal['position'] = 'top'
                signal['strength'] = 'strong'
                signal['description'] = f'PB {pb:.2f}，溢价{pb_premium:.0f}%，估值顶部'
            elif pb > 3.5 and pb_premium > 20:
                signal['position'] = 'top'
                signal['strength'] = 'medium'
                signal['description'] = f'PB {pb:.2f}，溢价{pb_premium:.0f}%，估值偏高'
            else:
                signal['description'] = f'PB {pb:.2f}，估值合理区间'
        else:
            # 没有行业对比，用绝对值判断
            if pb < 1.5:
                signal['position'] = 'bottom'
                signal['strength'] = 'medium'
                signal['description'] = f'PB {pb:.2f}，接近或低于净资产'
            elif pb > 5.0:
                signal['position'] = 'top'
                signal['strength'] = 'medium'
                signal['description'] = f'PB {pb:.2f}，估值较高'
            else:
                signal['description'] = f'PB {pb:.2f}，估值中等'

        return signal

    def _analyze_profitability_signal(self, stock_data: Dict, historical_trends: Dict) -> Dict:
        """
        信号2：盈利信号

        基于ROE趋势判断盈利拐点
        - ROE连续改善 → 上行信号
        - ROE连续恶化 → 下行信号
        - ROE极低(<5%) → 底部信号
        - ROE极高(>20%) → 顶部信号
        """
        financial = stock_data.get('financial', {})
        current_roe = financial.get('roe', 0)

        signal = {
            'name': '盈利信号',
            'indicator': 'ROE趋势',
            'value': current_roe,
            'position': None,
            'strength': 'weak',
            'description': '',
        }

        if current_roe <= 0:
            signal['description'] = 'ROE为负，盈利能力差'
            signal['position'] = 'bottom'
            signal['strength'] = 'strong'
            return signal

        # 分析趋势
        if historical_trends.get('success'):
            trend_analysis = historical_trends.get('trend_analysis', {})
            roe_trend = trend_analysis.get('roe_trend', '')

            if roe_trend == '改善':
                if current_roe < 0.08:
                    signal['position'] = 'bottom'
                    signal['strength'] = 'strong'
                    signal['description'] = f'ROE {current_roe*100:.1f}%，从低点回升，底部拐点信号'
                else:
                    signal['position'] = 'up'
                    signal['strength'] = 'medium'
                    signal['description'] = f'ROE {current_roe*100:.1f}%，持续改善，上行周期'
            elif roe_trend == '恶化':
                if current_roe > 0.20:
                    signal['position'] = 'top'
                    signal['strength'] = 'strong'
                    signal['description'] = f'ROE {current_roe*100:.1f}%，从高点回落，顶部拐点信号'
                else:
                    signal['position'] = 'down'
                    signal['strength'] = 'medium'
                    signal['description'] = f'ROE {current_roe*100:.1f}%，持续下滑，下行周期'
            else:
                signal['description'] = f'ROE {current_roe*100:.1f}%，保持稳定'
        else:
            # 只看绝对值
            if current_roe < 0.05:
                signal['position'] = 'bottom'
                signal['strength'] = 'medium'
                signal['description'] = f'ROE {current_roe*100:.1f}%，极低水平，可能处于底部'
            elif current_roe > 0.25:
                signal['position'] = 'top'
                signal['strength'] = 'medium'
                signal['description'] = f'ROE {current_roe*100:.1f}%，极高水平，可能处于顶部'
            else:
                signal['description'] = f'ROE {current_roe*100:.1f}%，中等水平'

        return signal

    def _analyze_prosperity_signal(self, historical_trends: Dict) -> Dict:
        """
        信号3：景气度信号

        基于毛利率趋势判断行业景气度
        - 毛利率改善 → 行业景气上行
        - 毛利率恶化 → 行业景气下行
        """
        signal = {
            'name': '景气度信号',
            'indicator': '毛利率趋势',
            'value': None,
            'position': None,
            'strength': 'weak',
            'description': '',
        }

        if not historical_trends.get('success'):
            signal['description'] = '数据不足'
            return signal

        trend_analysis = historical_trends.get('trend_analysis', {})
        margin_trend = trend_analysis.get('gross_margin_trend', '')
        trends = historical_trends.get('trends', {})
        margins = trends.get('gross_margin', [])

        if margins:
            current_margin = margins[0]
            signal['value'] = current_margin

            if margin_trend == '改善':
                signal['position'] = 'up'
                signal['strength'] = 'medium'
                signal['description'] = f'毛利率回升，行业景气度改善'
            elif margin_trend == '恶化':
                signal['position'] = 'down'
                signal['strength'] = 'medium'
                signal['description'] = f'毛利率下降，行业竞争加剧或需求疲软'
            else:
                signal['description'] = f'毛利率稳定'

        return signal

    def _analyze_price_signal(self, stock_data: Dict) -> Dict:
        """
        信号4：股价信号

        基于历史价格判断当前位置
        """
        signal = {
            'name': '股价信号',
            'indicator': '股价位置',
            'value': None,
            'position': None,
            'strength': 'weak',
            'description': '需要历史价格数据',
        }

        realtime = stock_data.get('realtime_price', {})
        historical = stock_data.get('historical_prices')

        if not realtime or historical is None or historical.empty:
            return signal

        current_price = realtime.get('current_price', 0)
        if current_price <= 0:
            return signal

        # 计算52周高低点
        if len(historical) > 0:
            high_52w = historical['close'].max()
            low_52w = historical['close'].min()

            position_pct = (current_price - low_52w) / (high_52w - low_52w) if high_52w > low_52w else 0.5

            signal['value'] = position_pct

            if position_pct < 0.2:
                signal['position'] = 'bottom'
                signal['strength'] = 'medium'
                signal['description'] = f'股价接近52周低点（底部{position_pct*100:.0f}%位置）'
            elif position_pct < 0.4:
                signal['position'] = 'bottom'
                signal['strength'] = 'weak'
                signal['description'] = f'股价偏低（{position_pct*100:.0f}%位置）'
            elif position_pct > 0.8:
                signal['position'] = 'top'
                signal['strength'] = 'medium'
                signal['description'] = f'股价接近52周高点（顶部{position_pct*100:.0f}%位置）'
            elif position_pct > 0.6:
                signal['position'] = 'top'
                signal['strength'] = 'weak'
                signal['description'] = f'股价偏高（{position_pct*100:.0f}%位置）'
            else:
                signal['description'] = f'股价中等位置（{position_pct*100:.0f}%）'

        return signal

    def _analyze_industry_signal(self, industry_comparison: Dict, historical_trends: Dict) -> Dict:
        """
        信号5：行业对比信号

        看公司相对行业的表现
        """
        signal = {
            'name': '行业对比信号',
            'indicator': '相对表现',
            'value': None,
            'position': None,
            'strength': 'weak',
            'description': '',
        }

        if not industry_comparison.get('success'):
            signal['description'] = '数据不足'
            return signal

        # 分析整体趋势
        overall = historical_trends.get('overall', '') if historical_trends.get('success') else ''

        comparison_texts = industry_comparison.get('comparison', [])

        # 统计正面/负面信号
        positive_count = sum(1 for c in comparison_texts if '✓' in c)
        negative_count = sum(1 for c in comparison_texts if '✗' in c)

        if positive_count > negative_count and '改善' in overall:
            signal['position'] = 'up'
            signal['strength'] = 'medium'
            signal['description'] = '强于行业且趋势改善，相对优势扩大'
        elif positive_count > negative_count:
            signal['description'] = '强于行业平均'
        elif negative_count > positive_count and '恶化' in overall:
            signal['position'] = 'down'
            signal['strength'] = 'medium'
            signal['description'] = '弱于行业且趋势恶化，相对劣势加大'
        elif negative_count > positive_count:
            signal['description'] = '弱于行业平均'
        else:
            signal['description'] = '与行业平均接近'

        return signal

    def _综合判断(self, signal_count: Dict) -> Tuple[str, str]:
        """综合判断周期位置"""

        # 计算主要信号
        max_signal = max(signal_count, key=signal_count.get)
        max_count = signal_count[max_signal]
        total_signals = sum(signal_count.values())

        # 如果有3个以上信号指向同一方向，置信度高
        if max_count >= 3:
            confidence = 'high'
        elif max_count >= 2:
            confidence = 'medium'
        else:
            confidence = 'low'

        # 确定位置
        if signal_count['bottom'] >= 2:
            position = '周期底部'
        elif signal_count['top'] >= 2:
            position = '周期顶部'
        elif signal_count['up'] >= 2:
            position = '上行周期'
        elif signal_count['down'] >= 2:
            position = '下行周期'
        else:
            position = '周期中部（不明确）'

        return position, confidence

    def _estimate_reversal_time(self, position: str, signals: List[Dict]) -> str:
        """预测反转时间"""

        if '底部' in position:
            # 看盈利信号和景气度信号
            roe_improving = any(s['name'] == '盈利信号' and s.get('position') in ['bottom', 'up'] for s in signals)
            margin_improving = any(s['name'] == '景气度信号' and s.get('position') == 'up' for s in signals)

            if roe_improving and margin_improving:
                return '拐点已现，预计6-12个月反转向上'
            elif roe_improving or margin_improving:
                return '预计1-2年内反转向上'
            else:
                return '预计2-3年内反转，需观察拐点信号'

        elif '顶部' in position:
            return '预计1-2年内进入下行周期'

        elif '上行' in position:
            return '处于上行周期中，继续观察顶部信号'

        elif '下行' in position:
            return '处于下行周期中，等待底部信号出现'

        else:
            return '周期位置不明确，需持续跟踪'

    def _generate_description(self, position: str, confidence: str, signal_count: Dict) -> str:
        """生成周期描述"""

        desc = f"综合判断：{position}（置信度：{confidence}）\n"
        desc += f"信号统计：底部{signal_count['bottom']}个，顶部{signal_count['top']}个，"
        desc += f"上行{signal_count['up']}个，下行{signal_count['down']}个"

        return desc


# 测试代码
if __name__ == "__main__":
    analyzer = CycleAnalyzer()

    # 模拟数据
    mock_stock_data = {
        'stock_info': {'pb_ratio': 1.8},
        'financial': {'roe': 0.08},
        'realtime_price': {'current_price': 15.5},
        'historical_prices': pd.DataFrame({
            'close': [20.0, 18.5, 17.0, 16.0, 15.0, 14.5, 15.5]
        })
    }

    mock_industry = {
        'success': True,
        'comparison': ['✓ ROE高于行业', '✓ 毛利率高于行业']
    }

    mock_trends = {
        'success': True,
        'trend_analysis': {'roe_trend': '改善', 'gross_margin_trend': '改善'},
        'overall': '✓ 财务指标整体改善',
        'trends': {'gross_margin': [0.15, 0.13, 0.12]}
    }

    mock_valuation = {
        'success': True,
        'avg_pb': 2.5,
        'pb_premium': -28
    }

    result = analyzer.analyze_cycle(mock_stock_data, mock_industry, mock_trends, mock_valuation)

    print("周期判断结果:")
    print(f"位置: {result['position']}")
    print(f"置信度: {result['confidence']}")
    print(f"\n信号明细:")
    for signal in result['signals']:
        print(f"  {signal['name']}: {signal['description']}")
    print(f"\n反转预测: {result['reversal_estimate']}")
