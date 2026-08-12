"""
数据采集模块 - 使用AKShare API实时获取数据
"""

import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import time
from functools import wraps

# 尝试导入模拟数据
try:
    from .mock_data import get_mock_data, get_available_mock_stocks
    MOCK_AVAILABLE = True
except ImportError:
    MOCK_AVAILABLE = False

# 全局标志：是否使用模拟数据
USE_MOCK_DATA = False


def retry_on_error(max_retries=3, delay=2):
    """装饰器：失败时重试"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt < max_retries - 1:
                        # print(f"  重试 {attempt + 1}/{max_retries}: {func.__name__}")
                        time.sleep(delay * (attempt + 1))  # 递增延迟
                    else:
                        # print(f"  ✗ {func.__name__} 失败: {str(e)[:100]}")
                        return None
        return wrapper
    return decorator


class DataCollector:
    """数据采集器 - 从AKShare获取股票、财务、行业数据"""

    def __init__(self):
        self.cache = {}  # 简单的内存缓存
        self.cache_ttl = 3600  # 缓存1小时

    def _get_cache_key(self, func_name: str, *args) -> str:
        """生成缓存键"""
        return f"{func_name}:{':'.join(map(str, args))}"

    def _get_from_cache(self, key: str) -> Optional[any]:
        """从缓存获取数据"""
        if key in self.cache:
            data, timestamp = self.cache[key]
            if time.time() - timestamp < self.cache_ttl:
                return data
        return None

    def _set_cache(self, key: str, data: any):
        """设置缓存"""
        self.cache[key] = (data, time.time())

    @retry_on_error(max_retries=2, delay=1)
    def get_stock_info(self, stock_code: str) -> Dict:
        """
        获取股票基本信息

        Args:
            stock_code: 股票代码，如 "600438"

        Returns:
            包含股票基本信息的字典
        """
        cache_key = self._get_cache_key("stock_info", stock_code)
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        # 获取股票基本信息
        stock_info_df = ak.stock_individual_info_em(symbol=stock_code)

        if stock_info_df is None or stock_info_df.empty:
            return {}

        # 转换为字典
        info = {}
        for _, row in stock_info_df.iterrows():
            info[row['item']] = row['value']

        result = {
            'stock_code': stock_code,
            'stock_name': info.get('股票简称', ''),
            'industry': info.get('行业', ''),
            'total_market_cap': self._parse_number(info.get('总市值', '0')),
            'circulating_market_cap': self._parse_number(info.get('流通市值', '0')),
            'pe_ratio': self._parse_number(info.get('市盈率-动态', '0')),
            'pb_ratio': self._parse_number(info.get('市净率', '0')),
            'total_shares': self._parse_number(info.get('总股本', '0')),
            'circulating_shares': self._parse_number(info.get('流通股', '0')),
            'fetch_time': datetime.now().isoformat(),
        }

        self._set_cache(cache_key, result)
        return result

    @retry_on_error(max_retries=2, delay=1)
    def get_realtime_price(self, stock_code: str) -> Dict:
        """
        获取实时行情

        Args:
            stock_code: 股票代码

        Returns:
            包含实时价格信息的字典
        """
        # 获取实时行情
        df = ak.stock_zh_a_spot_em()

        if df is None or df.empty:
            return {}

        stock_data = df[df['代码'] == stock_code]

        if stock_data.empty:
            return {}

        row = stock_data.iloc[0]

        return {
            'stock_code': stock_code,
            'current_price': float(row['最新价']),
            'change_pct': float(row['涨跌幅']),
            'change_amount': float(row['涨跌额']),
            'volume': float(row['成交量']),
            'turnover': float(row['成交额']),
            'high': float(row['最高']),
            'low': float(row['最低']),
            'open': float(row['今开']),
            'prev_close': float(row['昨收']),
            'fetch_time': datetime.now().isoformat(),
        }

    def get_financial_data(self, stock_code: str) -> Dict:
        """
        获取财务数据（最近一期）

        Args:
            stock_code: 股票代码

        Returns:
            包含财务数据的字典
        """
        cache_key = self._get_cache_key("financial", stock_code)
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        try:
            # 获取主要财务指标
            df = ak.stock_financial_analysis_indicator(symbol=stock_code)

            if df.empty:
                return {}

            # 取最新一期数据
            latest = df.iloc[0]

            result = {
                'stock_code': stock_code,
                'report_date': str(latest['截止日期']),
                'revenue': self._parse_number(latest.get('营业总收入', 0)),
                'net_profit': self._parse_number(latest.get('净利润', 0)),
                'gross_margin': self._parse_number(latest.get('销售毛利率', 0)),
                'net_margin': self._parse_number(latest.get('销售净利率', 0)),
                'roe': self._parse_number(latest.get('净资产收益率', 0)),
                'total_assets': self._parse_number(latest.get('资产总计', 0)),
                'total_liabilities': self._parse_number(latest.get('负债合计', 0)),
                'debt_ratio': self._parse_number(latest.get('资产负债率', 0)),
                'current_ratio': self._parse_number(latest.get('流动比率', 0)),
                'operating_cash_flow': self._parse_number(latest.get('经营活动产生的现金流量净额', 0)),
                'fetch_time': datetime.now().isoformat(),
            }

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            print(f"获取财务数据失败: {e}")
            return {}

    def get_balance_sheet(self, stock_code: str) -> Dict:
        """
        获取资产负债表数据

        Args:
            stock_code: 股票代码

        Returns:
            包含资产负债表关键数据的字典
        """
        cache_key = self._get_cache_key("balance_sheet", stock_code)
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        try:
            # 获取资产负债表
            df = ak.stock_balance_sheet_by_report_em(symbol=stock_code)

            if df is None or df.empty:
                return {}

            # 取最新一期
            latest = df.iloc[0]

            result = {
                'stock_code': stock_code,
                'report_date': str(latest.get('REPORT_DATE', '')),
                'cash': self._parse_number(latest.get('MONETARYFUND', 0)),
                'accounts_receivable': self._parse_number(latest.get('ACCOUNTSRECE', 0)),
                'inventory': self._parse_number(latest.get('INVENTORY', 0)),
                'total_current_assets': self._parse_number(latest.get('TOTALCURRENTASSETS', 0)),
                'fixed_assets': self._parse_number(latest.get('FIXEDASSETS', 0)),
                'total_assets': self._parse_number(latest.get('TOTALASSETS', 0)),
                'short_term_debt': self._parse_number(latest.get('SHORTBORR', 0)),
                'long_term_debt': self._parse_number(latest.get('LONGBORR', 0)),
                'total_liabilities': self._parse_number(latest.get('TOTALLIABILITIES', 0)),
                'shareholders_equity': self._parse_number(latest.get('TOTALSE', 0)),
                'fetch_time': datetime.now().isoformat(),
            }

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            print(f"获取资产负债表失败: {e}")
            return {}

    def get_cash_flow(self, stock_code: str) -> Dict:
        """
        获取现金流量表数据

        Args:
            stock_code: 股票代码

        Returns:
            包含现金流量数据的字典
        """
        cache_key = self._get_cache_key("cash_flow", stock_code)
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        try:
            # 获取现金流量表
            df = ak.stock_cash_flow_sheet_by_report_em(symbol=stock_code)

            if df is None or df.empty:
                return {}

            # 取最新一期
            latest = df.iloc[0]

            result = {
                'stock_code': stock_code,
                'report_date': str(latest.get('REPORT_DATE', '')),
                'operating_cash_flow': self._parse_number(latest.get('NETOPERATECASHFLOW', 0)),
                'investing_cash_flow': self._parse_number(latest.get('NETINVCASHFLOW', 0)),
                'financing_cash_flow': self._parse_number(latest.get('NETFINACASHFLOW', 0)),
                'capex': self._parse_number(latest.get('PURCHCONASSETPAY', 0)),
                'free_cash_flow': 0,
                'fetch_time': datetime.now().isoformat(),
            }

            # 计算自由现金流
            result['free_cash_flow'] = result['operating_cash_flow'] - result['capex']

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            print(f"获取现金流量表失败: {e}")
            return {}

    def get_income_statement(self, stock_code: str) -> Dict:
        """
        获取利润表数据

        Args:
            stock_code: 股票代码

        Returns:
            包含利润表数据的字典
        """
        cache_key = self._get_cache_key("income", stock_code)
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        try:
            # 获取利润表
            df = ak.stock_profit_sheet_by_report_em(symbol=stock_code)

            if df is None or df.empty:
                return {}

            # 取最新一期
            latest = df.iloc[0]

            result = {
                'stock_code': stock_code,
                'report_date': str(latest.get('REPORT_DATE', '')),
                'revenue': self._parse_number(latest.get('TOTALOPERATEREVE', 0)),
                'operating_cost': self._parse_number(latest.get('TOTALOPERATEEXP', 0)),
                'gross_profit': 0,
                'operating_profit': self._parse_number(latest.get('OPERATEPROFIT', 0)),
                'total_profit': self._parse_number(latest.get('TOTALPROFIT', 0)),
                'net_profit': self._parse_number(latest.get('NETPROFIT', 0)),
                'interest_expense': self._parse_number(latest.get('INTEXP', 0)),
                'ebit': 0,
                'fetch_time': datetime.now().isoformat(),
            }

            # 计算毛利
            result['gross_profit'] = result['revenue'] - result['operating_cost']
            # 计算EBIT
            result['ebit'] = result['operating_profit'] + result['interest_expense']

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            print(f"获取利润表失败: {e}")
            return {}

    def get_dividend_history(self, stock_code: str) -> List[Dict]:
        """
        获取分红历史

        Args:
            stock_code: 股票代码

        Returns:
            分红历史列表
        """
        cache_key = self._get_cache_key("dividend", stock_code)
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        try:
            # 获取分红数据
            df = ak.stock_dividend_cninfo(symbol=stock_code)

            if df.empty:
                return []

            result = []
            for _, row in df.head(5).iterrows():  # 取最近5年
                result.append({
                    'year': str(row.get('报告期', '')),
                    'dividend_per_share': self._parse_number(row.get('分红金额', 0)),
                    'dividend_ratio': self._parse_number(row.get('分红率', 0)),
                })

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            print(f"获取分红历史失败: {e}")
            return []

    def get_industry_pe(self, industry: str) -> float:
        """
        获取行业平均市盈率

        Args:
            industry: 行业名称

        Returns:
            行业平均市盈率
        """
        # 这个功能需要行业数据，暂时返回0，后续可以扩展
        return 0.0

    def get_historical_prices(self, stock_code: str, days: int = 365) -> pd.DataFrame:
        """
        获取历史价格数据

        Args:
            stock_code: 股票代码
            days: 历史天数

        Returns:
            历史价格DataFrame
        """
        cache_key = self._get_cache_key("history", stock_code, days)
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        try:
            # 计算开始日期
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

            # 获取历史数据
            df = ak.stock_zh_a_hist(
                symbol=stock_code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"  # 前复权
            )

            if df.empty:
                return pd.DataFrame()

            # 重命名列
            df = df.rename(columns={
                '日期': 'date',
                '开盘': 'open',
                '收盘': 'close',
                '最高': 'high',
                '最低': 'low',
                '成交量': 'volume',
                '成交额': 'turnover',
                '涨跌幅': 'change_pct',
            })

            self._set_cache(cache_key, df)
            return df

        except Exception as e:
            print(f"获取历史价格失败: {e}")
            return pd.DataFrame()

    def get_all_data(self, stock_code: str) -> Dict:
        """
        获取股票的所有数据（一站式）

        Args:
            stock_code: 股票代码

        Returns:
            包含所有数据的字典
        """
        global USE_MOCK_DATA

        print(f"\n正在获取 {stock_code} 的数据...")
        print("=" * 50)

        # 如果已经标记使用模拟数据，直接返回
        if USE_MOCK_DATA and MOCK_AVAILABLE:
            print("📦 使用模拟数据模式")
            mock_data = get_mock_data(stock_code)
            if mock_data:
                print(f"✓ 找到 {stock_code} 的模拟数据")
                return mock_data
            else:
                print(f"✗ 没有 {stock_code} 的模拟数据")
                print(f"可用的模拟股票: {', '.join(get_available_mock_stocks())}")
                return {}

        data = {}

        # 尝试获取真实数据
        print("📊 基本信息...", end=" ")
        info = self.get_stock_info(stock_code)
        data['stock_info'] = info or {}
        print("✓" if info else "✗")

        print("💰 实时行情...", end=" ")
        price = self.get_realtime_price(stock_code)
        data['realtime_price'] = price or {}
        print("✓" if price else "✗")

        print("📈 财务指标...", end=" ")
        financial = self.get_financial_data(stock_code)
        data['financial'] = financial or {}
        print("✓" if financial else "✗")

        print("📋 资产负债表...", end=" ")
        balance = self.get_balance_sheet(stock_code)
        data['balance_sheet'] = balance or {}
        print("✓" if balance else "✗")

        print("💵 现金流量表...", end=" ")
        cash = self.get_cash_flow(stock_code)
        data['cash_flow'] = cash or {}
        print("✓" if cash else "✗")

        print("📊 利润表...", end=" ")
        income = self.get_income_statement(stock_code)
        data['income_statement'] = income or {}
        print("✓" if income else "✗")

        print("💎 分红历史...", end=" ")
        dividend = self.get_dividend_history(stock_code)
        data['dividend_history'] = dividend or []
        print("✓" if dividend else "✗")

        print("📉 历史价格...", end=" ")
        history = self.get_historical_prices(stock_code, days=365)
        data['historical_prices'] = history if not history.empty else pd.DataFrame()
        print("✓" if not history.empty else "✗")

        print("=" * 50)
        success_count = sum([
            bool(data['stock_info']),
            bool(data['realtime_price']),
            bool(data['financial']),
            bool(data['balance_sheet']),
            bool(data['cash_flow']),
            bool(data['income_statement']),
            bool(data['dividend_history']),
            not data['historical_prices'].empty,
        ])

        # 如果完全失败，自动切换到模拟数据
        if success_count == 0 and MOCK_AVAILABLE:
            print("\n⚠️ API完全不可用，自动切换到模拟数据模式")
            USE_MOCK_DATA = True
            mock_data = get_mock_data(stock_code)
            if mock_data:
                print(f"✓ 使用 {stock_code} 的模拟数据")
                return mock_data
            else:
                print(f"✗ 没有 {stock_code} 的模拟数据")
                print(f"💡 可用的模拟股票: {', '.join(get_available_mock_stocks())}")
                return data

        print(f"数据获取完成！成功 {success_count}/8 项\n")
        return data

    @staticmethod
    def _parse_number(value) -> float:
        """解析数值，处理各种格式"""
        if pd.isna(value) or value == '' or value == '--':
            return 0.0

        try:
            # 如果是字符串，移除逗号和单位
            if isinstance(value, str):
                value = value.replace(',', '').replace('亿', '').replace('万', '')
                # 处理百分号
                if '%' in value:
                    return float(value.replace('%', '')) / 100

            return float(value)
        except:
            return 0.0


# 测试代码
if __name__ == "__main__":
    collector = DataCollector()

    # 测试通威股份
    print("测试获取通威股份(600438)数据...")
    data = collector.get_all_data("600438")

    print("\n=== 股票基本信息 ===")
    print(data['stock_info'])

    print("\n=== 实时行情 ===")
    print(data['realtime_price'])

    print("\n=== 财务数据 ===")
    print(data['financial'])

    print("\n=== 资产负债表 ===")
    print(data['balance_sheet'])

    print("\n=== 现金流量表 ===")
    print(data['cash_flow'])

    print("\n=== 利润表 ===")
    print(data['income_statement'])

    print("\n=== 分红历史 ===")
    for dividend in data['dividend_history']:
        print(dividend)

    print("\n=== 历史价格（最近5天）===")
    if not data['historical_prices'].empty:
        print(data['historical_prices'].tail())
