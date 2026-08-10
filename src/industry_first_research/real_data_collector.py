"""
真实数据采集模块 - 从AKShare获取数据

这才是系统的真正价值：自动化数据采集
"""

import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import json


class DataCollector:
    """真实数据采集器"""

    def __init__(self):
        self.data_source = "akshare"
        self.version = "1.0"

    def get_stock_info(self, stock_code: str) -> Dict[str, Any]:
        """获取股票基本信息"""
        try:
            # 获取股票信息
            stock_info = ak.stock_individual_info_em(symbol=stock_code)

            result = {
                "stock_code": stock_code,
                "company_name": stock_info[stock_info['item'] == '股票简称']['value'].values[0] if len(stock_info[stock_info['item'] == '股票简称']) > 0 else "",
                "industry": stock_info[stock_info['item'] == '行业']['value'].values[0] if len(stock_info[stock_info['item'] == '行业']) > 0 else "",
                "listing_date": stock_info[stock_info['item'] == '上市时间']['value'].values[0] if len(stock_info[stock_info['item'] == '上市时间']) > 0 else "",
                "data_source": self.data_source,
                "collected_at": datetime.now().isoformat()
            }

            return result

        except Exception as e:
            print(f"获取股票信息失败: {e}")
            return {"error": str(e)}

    def get_stock_financial_summary(self, stock_code: str) -> Dict[str, Any]:
        """获取股票财务概要"""
        try:
            # 获取主要财务指标
            df = ak.stock_financial_analysis_indicator(symbol=stock_code)

            if df.empty:
                return {"error": "无财务数据"}

            # 获取最近一期数据
            latest = df.iloc[0]

            result = {
                "stock_code": stock_code,
                "report_date": str(latest.get('报告日', '')),
                "revenue": float(latest.get('营业收入', 0)),
                "net_profit": float(latest.get('净利润', 0)),
                "roe": float(latest.get('净资产收益率', 0)),
                "debt_to_asset": float(latest.get('资产负债率', 0)),
                "gross_margin": float(latest.get('销售毛利率', 0)),
                "data_source": self.data_source,
                "collected_at": datetime.now().isoformat()
            }

            return result

        except Exception as e:
            print(f"获取财务数据失败: {e}")
            return {"error": str(e)}

    def get_stock_realtime_quote(self, stock_code: str) -> Dict[str, Any]:
        """获取股票实时行情"""
        try:
            # 获取实时行情
            df = ak.stock_zh_a_spot_em()
            stock_data = df[df['代码'] == stock_code]

            if stock_data.empty:
                return {"error": "未找到股票"}

            data = stock_data.iloc[0]

            result = {
                "stock_code": stock_code,
                "name": data.get('名称', ''),
                "price": float(data.get('最新价', 0)),
                "change_pct": float(data.get('涨跌幅', 0)),
                "volume": float(data.get('成交量', 0)),
                "turnover": float(data.get('成交额', 0)),
                "pe_ratio": float(data.get('市盈率-动态', 0)),
                "pb_ratio": float(data.get('市净率', 0)),
                "market_cap": float(data.get('总市值', 0)),
                "data_source": self.data_source,
                "collected_at": datetime.now().isoformat()
            }

            return result

        except Exception as e:
            print(f"获取实时行情失败: {e}")
            return {"error": str(e)}

    def get_futures_realtime_quote(self, variety_code: str) -> Dict[str, Any]:
        """获取期货实时行情"""
        try:
            # 获取期货实时行情
            df = ak.futures_zh_spot()

            # 根据品种代码筛选
            futures_data = df[df['symbol'].str.contains(variety_code, case=False)]

            if futures_data.empty:
                return {"error": "未找到期货品种"}

            # 获取主力合约（通常是成交量最大的）
            main_contract = futures_data.iloc[0]

            result = {
                "variety_code": variety_code,
                "contract": main_contract.get('symbol', ''),
                "name": main_contract.get('name', ''),
                "price": float(main_contract.get('trade', 0)),
                "change_pct": float(main_contract.get('pct_change', 0)),
                "volume": float(main_contract.get('volume', 0)),
                "open_interest": float(main_contract.get('hold', 0)),
                "data_source": self.data_source,
                "collected_at": datetime.now().isoformat()
            }

            return result

        except Exception as e:
            print(f"获取期货行情失败: {e}")
            return {"error": str(e)}

    def get_industry_index(self, industry_name: str) -> Dict[str, Any]:
        """获取行业指数数据"""
        try:
            # 获取行业板块指数
            df = ak.stock_board_industry_index_em()

            industry_data = df[df['板块名称'].str.contains(industry_name, case=False)]

            if industry_data.empty:
                return {"error": "未找到行业"}

            data = industry_data.iloc[0]

            result = {
                "industry_name": industry_name,
                "index_value": float(data.get('最新价', 0)),
                "change_pct": float(data.get('涨跌幅', 0)),
                "leading_stocks": int(data.get('上涨家数', 0)),
                "declining_stocks": int(data.get('下跌家数', 0)),
                "total_stocks": int(data.get('上涨家数', 0)) + int(data.get('下跌家数', 0)),
                "data_source": self.data_source,
                "collected_at": datetime.now().isoformat()
            }

            return result

        except Exception as e:
            print(f"获取行业指数失败: {e}")
            return {"error": str(e)}

    def collect_shanghai_power_data(self) -> Dict[str, Any]:
        """采集上海电力完整数据"""
        print("正在采集上海电力数据...")

        stock_code = "600021"

        result = {
            "company_id": stock_code,
            "basic_info": self.get_stock_info(stock_code),
            "financial_summary": self.get_stock_financial_summary(stock_code),
            "realtime_quote": self.get_stock_realtime_quote(stock_code),
            "industry_info": self.get_industry_index("电力"),
            "collected_at": datetime.now().isoformat(),
            "data_source": self.data_source
        }

        return result

    def collect_rubber_data(self) -> Dict[str, Any]:
        """采集天然橡胶数据"""
        print("正在采集天然橡胶数据...")

        result = {
            "variety_code": "RU",
            "realtime_quote": self.get_futures_realtime_quote("RU"),
            "collected_at": datetime.now().isoformat(),
            "data_source": self.data_source
        }

        return result


if __name__ == "__main__":
    print("="*80)
    print("  真实数据采集演示")
    print("="*80)

    collector = DataCollector()

    # 采集上海电力数据
    print("\n1. 采集上海电力(600021)数据:")
    print("-" * 80)
    shanghai_power_data = collector.collect_shanghai_power_data()
    print(json.dumps(shanghai_power_data, ensure_ascii=False, indent=2))

    # 采集天然橡胶数据
    print("\n2. 采集天然橡胶(RU)数据:")
    print("-" * 80)
    rubber_data = collector.collect_rubber_data()
    print(json.dumps(rubber_data, ensure_ascii=False, indent=2))

    print("\n" + "="*80)
    print("✅ 数据采集完成！这才是真正的投研系统！")
    print("="*80)
