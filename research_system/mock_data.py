"""
模拟数据模块 - 当API不可用时使用
"""

from datetime import datetime
import pandas as pd


MOCK_DATA = {
    '600438': {
        'stock_info': {
            'stock_code': '600438',
            'stock_name': '通威股份',
            'industry': '光伏设备',
            'total_market_cap': 1050.5,
            'circulating_market_cap': 980.2,
            'pe_ratio': 18.5,
            'pb_ratio': 2.3,
            'total_shares': 4500000000,
            'circulating_shares': 4200000000,
            'fetch_time': datetime.now().isoformat(),
        },
        'realtime_price': {
            'stock_code': '600438',
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
            'stock_code': '600438',
            'report_date': '2024-09-30',
            'revenue': 68500000000,
            'net_profit': 2500000000,
            'gross_margin': 0.15,
            'net_margin': 0.036,
            'roe': 0.075,
            'total_assets': 120000000000,
            'total_liabilities': 66000000000,
            'debt_ratio': 0.55,
            'current_ratio': 1.8,
            'operating_cash_flow': 8500000000,
            'fetch_time': datetime.now().isoformat(),
        },
        'balance_sheet': {
            'stock_code': '600438',
            'report_date': '2024-09-30',
            'cash': 10000000000,
            'accounts_receivable': 8500000000,
            'inventory': 12000000000,
            'total_current_assets': 45000000000,
            'fixed_assets': 55000000000,
            'total_assets': 120000000000,
            'short_term_debt': 15000000000,
            'long_term_debt': 25000000000,
            'total_liabilities': 66000000000,
            'shareholders_equity': 54000000000,
            'fetch_time': datetime.now().isoformat(),
        },
        'cash_flow': {
            'stock_code': '600438',
            'report_date': '2024-09-30',
            'operating_cash_flow': 8500000000,
            'investing_cash_flow': -6000000000,
            'financing_cash_flow': -1500000000,
            'capex': 6000000000,
            'free_cash_flow': 2500000000,
            'fetch_time': datetime.now().isoformat(),
        },
        'income_statement': {
            'stock_code': '600438',
            'report_date': '2024-09-30',
            'revenue': 68500000000,
            'operating_cost': 58225000000,
            'gross_profit': 10275000000,
            'operating_profit': 3200000000,
            'total_profit': 3000000000,
            'net_profit': 2500000000,
            'interest_expense': 800000000,
            'ebit': 4000000000,
            'fetch_time': datetime.now().isoformat(),
        },
        'dividend_history': [
            {'year': '2023', 'dividend_per_share': 0.35, 'dividend_ratio': 0.40},
            {'year': '2022', 'dividend_per_share': 0.80, 'dividend_ratio': 0.45},
            {'year': '2021', 'dividend_per_share': 1.20, 'dividend_ratio': 0.50},
            {'year': '2020', 'dividend_per_share': 0.65, 'dividend_ratio': 0.42},
            {'year': '2019', 'dividend_per_share': 0.50, 'dividend_ratio': 0.38},
        ],
    },
    '600809': {
        'stock_info': {
            'stock_code': '600809',
            'stock_name': '山西汾酒',
            'industry': '白酒',
            'total_market_cap': 4250.0,
            'circulating_market_cap': 4100.0,
            'pe_ratio': 28.5,
            'pb_ratio': 6.8,
            'total_shares': 1250000000,
            'circulating_shares': 1200000000,
            'fetch_time': datetime.now().isoformat(),
        },
        'realtime_price': {
            'stock_code': '600809',
            'current_price': 245.80,
            'change_pct': 0.8,
            'change_amount': 1.95,
            'volume': 2500000,
            'turnover': 614500000,
            'high': 248.50,
            'low': 243.20,
            'open': 244.00,
            'prev_close': 243.85,
            'fetch_time': datetime.now().isoformat(),
        },
        'financial': {
            'stock_code': '600809',
            'report_date': '2024-09-30',
            'revenue': 28500000000,
            'net_profit': 12800000000,
            'gross_margin': 0.68,
            'net_margin': 0.45,
            'roe': 0.28,
            'total_assets': 65000000000,
            'total_liabilities': 18000000000,
            'debt_ratio': 0.28,
            'current_ratio': 3.2,
            'operating_cash_flow': 13500000000,
            'fetch_time': datetime.now().isoformat(),
        },
        'balance_sheet': {
            'stock_code': '600809',
            'report_date': '2024-09-30',
            'cash': 25000000000,
            'accounts_receivable': 1200000000,
            'inventory': 12000000000,
            'total_current_assets': 42000000000,
            'fixed_assets': 8000000000,
            'total_assets': 65000000000,
            'short_term_debt': 2000000000,
            'long_term_debt': 5000000000,
            'total_liabilities': 18000000000,
            'shareholders_equity': 47000000000,
            'fetch_time': datetime.now().isoformat(),
        },
        'cash_flow': {
            'stock_code': '600809',
            'report_date': '2024-09-30',
            'operating_cash_flow': 13500000000,
            'investing_cash_flow': -2000000000,
            'financing_cash_flow': -8000000000,
            'capex': 1800000000,
            'free_cash_flow': 11700000000,
            'fetch_time': datetime.now().isoformat(),
        },
        'income_statement': {
            'stock_code': '600809',
            'report_date': '2024-09-30',
            'revenue': 28500000000,
            'operating_cost': 9120000000,
            'gross_profit': 19380000000,
            'operating_profit': 15200000000,
            'total_profit': 15000000000,
            'net_profit': 12800000000,
            'interest_expense': 150000000,
            'ebit': 15350000000,
            'fetch_time': datetime.now().isoformat(),
        },
        'dividend_history': [
            {'year': '2023', 'dividend_per_share': 12.50, 'dividend_ratio': 0.60},
            {'year': '2022', 'dividend_per_share': 10.80, 'dividend_ratio': 0.58},
            {'year': '2021', 'dividend_per_share': 8.50, 'dividend_ratio': 0.55},
            {'year': '2020', 'dividend_per_share': 6.20, 'dividend_ratio': 0.52},
            {'year': '2019', 'dividend_per_share': 5.00, 'dividend_ratio': 0.50},
        ],
    },
}


def get_mock_data(stock_code: str) -> dict:
    """
    获取模拟数据

    Args:
        stock_code: 股票代码

    Returns:
        模拟的股票数据，如果没有该股票的模拟数据则返回None
    """
    data = MOCK_DATA.get(stock_code)

    if data:
        # 添加历史价格（简单模拟）
        dates = pd.date_range(end=datetime.now(), periods=252, freq='D')
        base_price = data['realtime_price']['current_price']
        data['historical_prices'] = pd.DataFrame({
            'date': dates,
            'close': [base_price * (1 + (i - 126) * 0.002) for i in range(252)],
            'volume': [data['realtime_price']['volume'] * 0.8 for _ in range(252)],
        })

    return data


def get_available_mock_stocks() -> list:
    """获取可用的模拟股票列表"""
    return list(MOCK_DATA.keys())
