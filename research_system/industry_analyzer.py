"""
行业对比分析模块 - 基于AKShare API实时数据
"""

import akshare as ak
import pandas as pd
from typing import Dict, List, Optional
import time


class IndustryComparator:
    """行业对比分析器"""

    def __init__(self):
        self.cache = {}
        self.cache_ttl = 3600

    def get_industry_companies(self, industry: str) -> List[Dict]:
        """
        获取同行业所有公司

        Args:
            industry: 行业名称

        Returns:
            公司列表
        """
        cache_key = f"industry_companies:{industry}"
        if cache_key in self.cache:
            data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_ttl:
                return data

        try:
            # 获取行业板块成分股
            industry_cons = ak.stock_board_industry_cons_em(symbol=industry)

            companies = []
            for _, row in industry_cons.iterrows():
                companies.append({
                    'code': row['代码'],
                    'name': row['名称'],
                    'price': float(row['最新价']),
                    'change_pct': float(row['涨跌幅']),
                    'market_cap': float(row.get('总市值', 0)),
                })

            self.cache[cache_key] = (companies, time.time())
            return companies

        except Exception as e:
            print(f"  获取行业成分股失败: {e}")
            return []

    def compare_with_peers(self, stock_code: str, stock_data: Dict) -> Dict:
        """
        与同行业公司对比

        Args:
            stock_code: 股票代码
            stock_data: 股票数据（从DataCollector获取）

        Returns:
            对比结果
        """
        stock_info = stock_data.get('stock_info', {})
        financial = stock_data.get('financial', {})

        industry = stock_info.get('industry', '')
        if not industry:
            return {
                'success': False,
                'message': '无法获取行业信息',
            }

        print(f"  正在对比行业: {industry}...")

        # 获取同行业公司
        peers = self.get_industry_companies(industry)
        if not peers:
            return {
                'success': False,
                'message': '无法获取同行业公司',
            }

        print(f"  找到 {len(peers)} 家同行业公司")

        # 获取同行业公司的财务数据（采样前10家）
        peer_financials = []
        for peer in peers[:10]:
            try:
                peer_financial = ak.stock_financial_analysis_indicator(symbol=peer['code'])
                if not peer_financial.empty:
                    latest = peer_financial.iloc[0]
                    peer_financials.append({
                        'code': peer['code'],
                        'name': peer['name'],
                        'market_cap': peer['market_cap'],
                        'roe': self._parse_number(latest.get('净资产收益率', 0)),
                        'gross_margin': self._parse_number(latest.get('销售毛利率', 0)),
                        'net_margin': self._parse_number(latest.get('销售净利率', 0)),
                        'debt_ratio': self._parse_number(latest.get('资产负债率', 0)),
                        'revenue': self._parse_number(latest.get('营业总收入', 0)),
                    })
            except:
                continue
            time.sleep(0.2)  # 避免请求过快

        if len(peer_financials) < 3:
            return {
                'success': False,
                'message': '同行业财务数据不足',
            }

        # 当前公司数据
        current = {
            'market_cap': stock_info.get('total_market_cap', 0),
            'roe': financial.get('roe', 0),
            'gross_margin': financial.get('gross_margin', 0),
            'net_margin': financial.get('net_margin', 0),
            'debt_ratio': financial.get('debt_ratio', 0),
            'revenue': financial.get('revenue', 0) / 100000000,  # 转成亿
        }

        # 计算行业平均值和排名
        df = pd.DataFrame(peer_financials)

        industry_avg = {
            'roe': df['roe'].mean(),
            'gross_margin': df['gross_margin'].mean(),
            'net_margin': df['net_margin'].mean(),
            'debt_ratio': df['debt_ratio'].mean(),
        }

        # 排名（市值、营收、ROE）
        rankings = {
            'market_cap': self._calculate_rank(current['market_cap'], df['market_cap'].tolist()),
            'revenue': self._calculate_rank(current['revenue'], df['revenue'].tolist()),
            'roe': self._calculate_rank(current['roe'], df['roe'].tolist()),
            'gross_margin': self._calculate_rank(current['gross_margin'], df['gross_margin'].tolist()),
        }

        # 找出龙头企业（市值最大或营收最大）
        leader_by_market_cap = df.nlargest(1, 'market_cap').iloc[0]
        leader_by_revenue = df.nlargest(1, 'revenue').iloc[0]

        return {
            'success': True,
            'industry': industry,
            'peer_count': len(peers),
            'analyzed_count': len(peer_financials),
            'current_company': current,
            'industry_average': industry_avg,
            'rankings': rankings,
            'leader_by_market_cap': {
                'name': leader_by_market_cap['name'],
                'market_cap': leader_by_market_cap['market_cap'],
            },
            'leader_by_revenue': {
                'name': leader_by_revenue['name'],
                'revenue': leader_by_revenue['revenue'],
            },
            'comparison': self._generate_comparison_text(current, industry_avg, rankings),
            'top_peers': peer_financials[:5],  # 前5名同行
        }

    def _calculate_rank(self, value: float, peer_values: List[float]) -> int:
        """计算排名（值越大排名越高）"""
        peer_values_sorted = sorted([v for v in peer_values if v > 0], reverse=True)
        if value <= 0 or not peer_values_sorted:
            return 999

        # 找到比当前值大的数量
        rank = sum(1 for v in peer_values_sorted if v > value) + 1
        return rank

    def _generate_comparison_text(self, current: Dict, avg: Dict, rankings: Dict) -> List[str]:
        """生成对比文本"""
        comparisons = []

        # ROE对比
        if current['roe'] > avg['roe'] * 1.2:
            comparisons.append(f"✓ ROE显著高于行业平均 ({current['roe']*100:.1f}% vs {avg['roe']*100:.1f}%)")
        elif current['roe'] < avg['roe'] * 0.8:
            comparisons.append(f"✗ ROE低于行业平均 ({current['roe']*100:.1f}% vs {avg['roe']*100:.1f}%)")
        else:
            comparisons.append(f"○ ROE接近行业平均 ({current['roe']*100:.1f}% vs {avg['roe']*100:.1f}%)")

        # 毛利率对比
        if current['gross_margin'] > avg['gross_margin'] * 1.1:
            comparisons.append(f"✓ 毛利率高于行业平均 ({current['gross_margin']*100:.1f}% vs {avg['gross_margin']*100:.1f}%)")
        elif current['gross_margin'] < avg['gross_margin'] * 0.9:
            comparisons.append(f"✗ 毛利率低于行业平均 ({current['gross_margin']*100:.1f}% vs {avg['gross_margin']*100:.1f}%)")
        else:
            comparisons.append(f"○ 毛利率接近行业平均 ({current['gross_margin']*100:.1f}% vs {avg['gross_margin']*100:.1f}%)")

        # 市值排名
        rank = rankings['market_cap']
        if rank <= 3:
            comparisons.append(f"✓ 市值排名前三 (第{rank}名)")
        elif rank <= 10:
            comparisons.append(f"○ 市值排名前十 (第{rank}名)")
        else:
            comparisons.append(f"✗ 市值排名靠后 (第{rank}名)")

        return comparisons

    @staticmethod
    def _parse_number(value) -> float:
        """解析数值"""
        if pd.isna(value) or value == '' or value == '--':
            return 0.0
        try:
            if isinstance(value, str):
                value = value.replace(',', '').replace('亿', '').replace('万', '')
                if '%' in value:
                    return float(value.replace('%', '')) / 100
            return float(value)
        except:
            return 0.0


class HistoricalTrendAnalyzer:
    """历史趋势分析器"""

    def analyze_trends(self, stock_code: str) -> Dict:
        """
        分析历史趋势

        Args:
            stock_code: 股票代码

        Returns:
            趋势分析结果
        """
        try:
            print(f"  正在分析历史趋势...")

            # 获取多期财务数据
            financial_df = ak.stock_financial_analysis_indicator(symbol=stock_code)

            if financial_df.empty or len(financial_df) < 4:
                return {
                    'success': False,
                    'message': '历史数据不足',
                }

            # 取最近4个季度
            recent_periods = financial_df.head(4)

            # 提取关键指标
            trends = {
                'roe': [self._parse_number(row['净资产收益率']) for _, row in recent_periods.iterrows()],
                'gross_margin': [self._parse_number(row['销售毛利率']) for _, row in recent_periods.iterrows()],
                'net_margin': [self._parse_number(row['销售净利率']) for _, row in recent_periods.iterrows()],
                'revenue': [self._parse_number(row['营业总收入']) for _, row in recent_periods.iterrows()],
                'periods': [str(row['截止日期']) for _, row in recent_periods.iterrows()],
            }

            # 判断趋势
            trend_analysis = {
                'roe_trend': self._analyze_trend(trends['roe']),
                'gross_margin_trend': self._analyze_trend(trends['gross_margin']),
                'net_margin_trend': self._analyze_trend(trends['net_margin']),
                'revenue_trend': self._analyze_trend(trends['revenue']),
            }

            # 综合评价
            improving_count = sum(1 for t in trend_analysis.values() if t == '改善')
            declining_count = sum(1 for t in trend_analysis.values() if t == '恶化')

            if improving_count >= 3:
                overall = '✓ 财务指标整体改善'
            elif declining_count >= 3:
                overall = '✗ 财务指标整体恶化'
            else:
                overall = '○ 财务指标总体稳定'

            return {
                'success': True,
                'periods': trends['periods'],
                'trends': trends,
                'trend_analysis': trend_analysis,
                'overall': overall,
                'details': self._generate_trend_details(trends, trend_analysis),
            }

        except Exception as e:
            print(f"  历史趋势分析失败: {e}")
            return {
                'success': False,
                'message': str(e),
            }

    def _analyze_trend(self, values: List[float]) -> str:
        """分析单个指标趋势（最近的在前面）"""
        if len(values) < 2:
            return '数据不足'

        # 计算最近两期的变化
        latest = values[0]
        previous = values[1]

        if latest == 0 and previous == 0:
            return '数据不足'

        change_pct = (latest - previous) / previous if previous != 0 else 0

        if change_pct > 0.1:  # 改善超过10%
            return '改善'
        elif change_pct < -0.1:  # 恶化超过10%
            return '恶化'
        else:
            return '稳定'

    def _generate_trend_details(self, trends: Dict, analysis: Dict) -> List[str]:
        """生成趋势详情"""
        details = []

        # ROE
        if len(trends['roe']) >= 2:
            latest = trends['roe'][0] * 100
            prev = trends['roe'][1] * 100
            details.append(f"ROE: {prev:.1f}% → {latest:.1f}% ({analysis['roe_trend']})")

        # 毛利率
        if len(trends['gross_margin']) >= 2:
            latest = trends['gross_margin'][0] * 100
            prev = trends['gross_margin'][1] * 100
            details.append(f"毛利率: {prev:.1f}% → {latest:.1f}% ({analysis['gross_margin_trend']})")

        # 净利率
        if len(trends['net_margin']) >= 2:
            latest = trends['net_margin'][0] * 100
            prev = trends['net_margin'][1] * 100
            details.append(f"净利率: {prev:.1f}% → {latest:.1f}% ({analysis['net_margin_trend']})")

        return details

    @staticmethod
    def _parse_number(value) -> float:
        """解析数值"""
        if pd.isna(value) or value == '' or value == '--':
            return 0.0
        try:
            if isinstance(value, str):
                value = value.replace(',', '').replace('亿', '').replace('万', '')
                if '%' in value:
                    return float(value.replace('%', '')) / 100
            return float(value)
        except:
            return 0.0


class CommodityPriceMonitor:
    """大宗商品价格监控"""

    def get_silicon_price(self) -> Dict:
        """获取硅料价格"""
        try:
            # AKShare可能有硅料价格数据
            # 这里先返回框架，具体API需要查找
            return {
                'success': False,
                'message': '硅料价格API待集成',
            }
        except Exception as e:
            return {
                'success': False,
                'message': str(e),
            }

    def get_lithium_price(self) -> Dict:
        """获取锂价格"""
        try:
            # 碳酸锂价格
            df = ak.spot_hist_sge(symbol="碳酸锂")
            if df.empty:
                return {'success': False}

            latest = df.iloc[-1]
            prev = df.iloc[-30] if len(df) > 30 else df.iloc[0]  # 30天前

            return {
                'success': True,
                'product': '碳酸锂',
                'latest_price': float(latest['收盘价']),
                'date': str(latest['日期']),
                'change_30d': ((float(latest['收盘价']) - float(prev['收盘价'])) / float(prev['收盘价']) * 100),
            }
        except Exception as e:
            return {
                'success': False,
                'message': str(e),
            }

    def analyze_commodity_cycle(self, industry: str) -> Dict:
        """
        分析商品周期

        Args:
            industry: 行业名称

        Returns:
            周期分析
        """
        results = {}

        # 根据行业选择相关商品
        if '锂' in industry or '电池' in industry:
            results['lithium'] = self.get_lithium_price()

        if '光伏' in industry or '硅' in industry:
            results['silicon'] = self.get_silicon_price()

        return results


class ValuationComparator:
    """估值对比分析器"""

    def compare_valuation(self, stock_code: str, stock_data: Dict, industry_comparison: Dict) -> Dict:
        """
        估值对比分析

        Args:
            stock_code: 股票代码
            stock_data: 股票数据
            industry_comparison: 行业对比数据

        Returns:
            估值对比结果
        """
        if not industry_comparison.get('success'):
            return {
                'success': False,
                'message': '需要行业对比数据',
            }

        print(f"  正在进行估值对比...")

        stock_info = stock_data.get('stock_info', {})
        financial = stock_data.get('financial', {})

        # 当前公司估值
        current_pe = stock_info.get('pe_ratio', 0)
        current_pb = stock_info.get('pb_ratio', 0)
        current_roe = financial.get('roe', 0)

        # 获取同行业公司的PE/PB
        top_peers = industry_comparison.get('top_peers', [])
        if len(top_peers) < 3:
            return {
                'success': False,
                'message': '同行业数据不足',
            }

        # 计算行业平均PE/PB（需要重新获取）
        peer_pe_list = []
        peer_pb_list = []

        for peer in top_peers:
            try:
                # 获取同行PE/PB
                peer_info = ak.stock_individual_info_em(symbol=peer['code'])
                pe_value = 0
                pb_value = 0

                for _, row in peer_info.iterrows():
                    if row['item'] == '市盈率-动态':
                        pe_value = self._parse_number(row['value'])
                    elif row['item'] == '市净率':
                        pb_value = self._parse_number(row['value'])

                if 0 < pe_value < 100:  # 过滤异常值
                    peer_pe_list.append(pe_value)
                if 0 < pb_value < 20:
                    peer_pb_list.append(pb_value)

            except:
                continue
            time.sleep(0.2)

        if not peer_pe_list:
            return {
                'success': False,
                'message': '无法获取同行业估值数据',
            }

        # 计算行业平均
        avg_pe = sum(peer_pe_list) / len(peer_pe_list)
        avg_pb = sum(peer_pb_list) / len(peer_pb_list) if peer_pb_list else 0

        # 计算相对估值
        pe_premium = ((current_pe - avg_pe) / avg_pe * 100) if avg_pe > 0 else 0
        pb_premium = ((current_pb - avg_pb) / avg_pb * 100) if avg_pb > 0 else 0

        # PEG（PE/增长率）
        # 简化：用ROE作为增长率代理
        peg = current_pe / (current_roe * 100) if current_roe > 0 else 999

        # 估值判断
        valuation_level = self._judge_valuation(current_pe, avg_pe, peg)

        return {
            'success': True,
            'current_pe': current_pe,
            'current_pb': current_pb,
            'avg_pe': avg_pe,
            'avg_pb': avg_pb,
            'pe_premium': pe_premium,
            'pb_premium': pb_premium,
            'peg': peg,
            'valuation_level': valuation_level,
            'analysis': self._generate_valuation_analysis(
                current_pe, avg_pe, current_pb, avg_pb, peg, pe_premium
            ),
        }

    def _judge_valuation(self, pe: float, avg_pe: float, peg: float) -> str:
        """判断估值水平"""
        if pe <= 0:
            return '无法判断（亏损）'

        # PEG判断
        if peg < 1:
            return '相对低估'
        elif peg > 2:
            return '相对高估'

        # PE相对值判断
        if pe < avg_pe * 0.7:
            return '相对低估'
        elif pe > avg_pe * 1.3:
            return '相对高估'
        else:
            return '合理估值'

    def _generate_valuation_analysis(
        self, pe: float, avg_pe: float, pb: float, avg_pb: float, peg: float, premium: float
    ) -> List[str]:
        """生成估值分析文本"""
        analysis = []

        # PE对比
        if pe > 0:
            if premium > 30:
                analysis.append(f'✗ PE显著高于行业 ({pe:.1f} vs {avg_pe:.1f}，溢价{premium:.0f}%)')
            elif premium > 10:
                analysis.append(f'⚠ PE略高于行业 ({pe:.1f} vs {avg_pe:.1f}，溢价{premium:.0f}%)')
            elif premium < -30:
                analysis.append(f'✓ PE显著低于行业 ({pe:.1f} vs {avg_pe:.1f}，折价{-premium:.0f}%)')
            elif premium < -10:
                analysis.append(f'✓ PE略低于行业 ({pe:.1f} vs {avg_pe:.1f}，折价{-premium:.0f}%)')
            else:
                analysis.append(f'○ PE接近行业平均 ({pe:.1f} vs {avg_pe:.1f})')

        # PEG判断
        if peg < 999:
            if peg < 1:
                analysis.append(f'✓ PEG<1 ({peg:.2f})，估值相对成长性较低')
            elif peg > 2:
                analysis.append(f'✗ PEG>2 ({peg:.2f})，估值相对成长性较高')
            else:
                analysis.append(f'○ PEG合理 ({peg:.2f})')

        # PB对比
        if pb > 0 and avg_pb > 0:
            pb_premium = ((pb - avg_pb) / avg_pb * 100)
            if pb_premium > 20:
                analysis.append(f'⚠ PB高于行业平均 ({pb:.2f} vs {avg_pb:.2f})')
            elif pb_premium < -20:
                analysis.append(f'✓ PB低于行业平均 ({pb:.2f} vs {avg_pb:.2f})')

        return analysis

    @staticmethod
    def _parse_number(value) -> float:
        """解析数值"""
        if pd.isna(value) or value == '' or value == '--':
            return 0.0
        try:
            if isinstance(value, str):
                value = value.replace(',', '').replace('亿', '').replace('万', '')
                if '%' in value:
                    return float(value.replace('%', '')) / 100
            return float(value)
        except:
            return 0.0


# 测试代码
if __name__ == "__main__":
    # 测试行业对比
    comparator = IndustryComparator()

    # 模拟数据
    mock_data = {
        'stock_info': {
            'industry': '光伏设备',
            'total_market_cap': 1050,
        },
        'financial': {
            'roe': 0.08,
            'gross_margin': 0.15,
            'net_margin': 0.05,
            'debt_ratio': 0.55,
            'revenue': 68500000000,
        }
    }

    print("测试行业对比功能...")
    result = comparator.compare_with_peers('600438', mock_data)

    if result['success']:
        print(f"\n✓ 行业: {result['industry']}")
        print(f"  同行业公司: {result['peer_count']} 家")
        print(f"  对比分析:")
        for comp in result['comparison']:
            print(f"    {comp}")
