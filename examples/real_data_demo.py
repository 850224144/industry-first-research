"""
真实数据采集模块 - 简化版，使用更稳定的AKShare接口

重点：展示系统如何从真实API获取数据，而不是使用静态JSON
"""

import akshare as ak
import time
from datetime import datetime
from typing import Dict, Any
import json


class RealDataCollector:
    """真实数据采集器 - 简化版"""

    def __init__(self):
        self.data_source = "akshare"

    def get_stock_spot_data(self, symbol: str = "600021") -> Dict[str, Any]:
        """获取股票实时数据 - 更稳定的接口"""
        try:
            print(f"正在获取 {symbol} 实时数据...")

            # 使用更简单稳定的接口
            df = ak.stock_zh_a_spot_em()

            # 筛选目标股票
            stock = df[df['代码'] == symbol]

            if stock.empty:
                return {"error": f"未找到股票 {symbol}"}

            data = stock.iloc[0]

            result = {
                "stock_code": symbol,
                "name": str(data['名称']),
                "price": float(data['最新价']),
                "change_pct": float(data['涨跌幅']),
                "change_amount": float(data['涨跌额']),
                "volume": float(data['成交量']),
                "turnover": float(data['成交额']),
                "amplitude": float(data['振幅']),
                "high": float(data['最高']),
                "low": float(data['最低']),
                "open": float(data['今开']),
                "prev_close": float(data['昨收']),
                "data_source": "akshare",
                "collected_at": datetime.now().isoformat()
            }

            print(f"✓ 成功获取 {data['名称']} 数据")
            return result

        except Exception as e:
            print(f"✗ 获取失败: {e}")
            return {"error": str(e)}

    def get_market_overview(self) -> Dict[str, Any]:
        """获取市场概况"""
        try:
            print("正在获取市场概况...")

            # 获取A股实时数据
            df = ak.stock_zh_a_spot_em()

            # 统计
            total_stocks = len(df)
            rising = len(df[df['涨跌幅'] > 0])
            falling = len(df[df['涨跌幅'] < 0])
            flat = total_stocks - rising - falling

            result = {
                "total_stocks": total_stocks,
                "rising_stocks": rising,
                "falling_stocks": falling,
                "flat_stocks": flat,
                "rising_pct": round(rising / total_stocks * 100, 2),
                "data_source": "akshare",
                "collected_at": datetime.now().isoformat()
            }

            print(f"✓ 市场概况: 上涨{rising} 下跌{falling}")
            return result

        except Exception as e:
            print(f"✗ 获取失败: {e}")
            return {"error": str(e)}

    def get_index_data(self, index_code: str = "sh000001") -> Dict[str, Any]:
        """获取指数数据"""
        try:
            print(f"正在获取指数 {index_code} 数据...")

            # 获取实时指数
            df = ak.stock_zh_index_spot_em()

            # 上证指数代码
            index = df[df['代码'] == index_code]

            if index.empty:
                return {"error": f"未找到指数 {index_code}"}

            data = index.iloc[0]

            result = {
                "index_code": index_code,
                "name": str(data['名称']),
                "value": float(data['最新价']),
                "change_pct": float(data['涨跌幅']),
                "change_amount": float(data['涨跌额']),
                "volume": float(data['成交量']),
                "turnover": float(data['成交额']),
                "data_source": "akshare",
                "collected_at": datetime.now().isoformat()
            }

            print(f"✓ 上证指数: {data['最新价']} ({data['涨跌幅']}%)")
            return result

        except Exception as e:
            print(f"✗ 获取失败: {e}")
            return {"error": str(e)}

    def demo_real_data_collection(self):
        """演示真实数据采集流程"""
        print("="*80)
        print("  真实数据采集演示 - 这才是投研系统的核心价值")
        print("="*80)
        print()

        results = {}

        # 1. 获取上证指数
        print("【1/3】获取上证指数")
        print("-" * 80)
        results['index'] = self.get_index_data("sh000001")
        print()
        time.sleep(1)  # 避免请求过快

        # 2. 获取市场概况
        print("【2/3】获取市场概况")
        print("-" * 80)
        results['market'] = self.get_market_overview()
        print()
        time.sleep(1)

        # 3. 获取上海电力数据
        print("【3/3】获取上海电力(600021)数据")
        print("-" * 80)
        results['shanghai_power'] = self.get_stock_spot_data("600021")
        print()

        # 总结
        print("="*80)
        print("  采集结果总结")
        print("="*80)

        if 'error' not in results['index']:
            print(f"✓ 上证指数: {results['index']['value']:.2f} ({results['index']['change_pct']:+.2f}%)")

        if 'error' not in results['market']:
            print(f"✓ 市场涨跌: 上涨{results['market']['rising_stocks']}只 下跌{results['market']['falling_stocks']}只")

        if 'error' not in results['shanghai_power']:
            sp = results['shanghai_power']
            print(f"✓ 上海电力: {sp['price']:.2f}元 ({sp['change_pct']:+.2f}%)")

        print()
        print("="*80)
        print("💡 关键点：")
        print("  1. 数据来自AKShare真实API，不是静态JSON")
        print("  2. 每次运行都获取最新数据")
        print("  3. 这才是投研系统的自动化价值")
        print("="*80)

        return results


if __name__ == "__main__":
    collector = RealDataCollector()
    results = collector.demo_real_data_collection()

    # 保存结果
    output_file = "data/real_data_sample.json"
    import os
    os.makedirs("data", exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_file}")
