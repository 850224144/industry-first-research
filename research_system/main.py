#!/usr/bin/env python
"""
投研系统主程序 - CLI入口
用"西红柿炒鸡蛋"的逻辑分析上市公司投资价值
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict

from .data_collector import DataCollector
from .analyzer import InvestmentAnalyzer
from .report_generator import ReportGenerator


class InvestmentResearchSystem:
    """投研系统主类"""

    def __init__(self):
        self.collector = DataCollector()
        self.analyzer = InvestmentAnalyzer()
        self.reporter = ReportGenerator()

    def analyze_stock(self, stock_code: str, output_path: str = None, format: str = 'console') -> Dict:
        """
        分析股票

        Args:
            stock_code: 股票代码
            output_path: 输出路径（可选）
            format: 输出格式（console/markdown）

        Returns:
            分析报告
        """
        print(f"\n{'='*60}")
        print(f"  投研分析系统 - \"西红柿炒鸡蛋\"逻辑")
        print(f"{'='*60}\n")

        # 1. 数据采集
        print("📡 阶段1：数据采集")
        stock_data = self.collector.get_all_data(stock_code)

        # 检查是否有基本数据
        if not stock_data.get('stock_info') and not stock_data.get('realtime_price'):
            print("\n❌ 错误：无法获取股票数据，请检查股票代码是否正确")
            return None

        # 2. 分析
        print("\n🔬 阶段2：投资分析")
        report = self.analyzer.analyze(stock_data)
        print("  ✓ 产品分析完成")
        print("  ✓ 市场地位分析完成")
        print("  ✓ 财务健康度分析完成")
        print("  ✓ 周期分析完成")
        print("  ✓ 生存能力分析完成")
        print("  ✓ 回本周期计算完成")
        print("  ✓ 投资建议生成完成")

        # 3. 生成报告
        print("\n📄 阶段3：报告生成")
        if format == 'console' and not output_path:
            # 直接打印到终端
            print("\n" + self.reporter.generate_console(report))
        else:
            # 保存到文件
            if not output_path:
                # 默认输出路径
                output_dir = Path("reports")
                output_dir.mkdir(exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = output_dir / f"{stock_code}_{timestamp}.md"

            success = self.reporter.save_report(report, str(output_path), format='markdown')
            if success:
                print(f"  ✓ 报告已保存到：{output_path}")
            else:
                print(f"  ✗ 报告保存失败")

        return report


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='投研分析系统 - 用"西红柿炒鸡蛋"的逻辑分析上市公司',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 分析股票并显示在终端
  python -m research_system.main analyze 600438

  # 分析并保存Markdown报告
  python -m research_system.main analyze 600438 -o report.md

  # 分析多个股票
  python -m research_system.main analyze 600438 601012 002594

关键输出：
  1. 产品在产业链的重要性（A/B/C/D级）
  2. 市场地位（龙头判断）
  3. 财务健康度
  4. 生存能力分析
  5. 回本周期预测（三种情景）
  6. 明确投资建议
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='命令')

    # analyze命令
    analyze_parser = subparsers.add_parser('analyze', help='分析股票')
    analyze_parser.add_argument('stock_codes', nargs='+', help='股票代码（如：600438）')
    analyze_parser.add_argument('-o', '--output', help='输出文件路径')
    analyze_parser.add_argument('-f', '--format', choices=['console', 'markdown'],
                               default='console', help='输出格式')

    # version命令
    version_parser = subparsers.add_parser('version', help='显示版本信息')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == 'version':
        print("投研分析系统 v2.0.0")
        print("基于\"西红柿炒鸡蛋\"产业链逻辑")
        return

    if args.command == 'analyze':
        system = InvestmentResearchSystem()

        for stock_code in args.stock_codes:
            try:
                # 如果有多个股票，自动为每个生成独立文件
                output_path = None
                if args.output and len(args.stock_codes) == 1:
                    output_path = args.output
                elif args.format == 'markdown':
                    output_dir = Path("reports")
                    output_dir.mkdir(exist_ok=True)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_path = str(output_dir / f"{stock_code}_{timestamp}.md")

                system.analyze_stock(stock_code, output_path, args.format)

                if len(args.stock_codes) > 1:
                    print("\n" + "="*60 + "\n")

            except KeyboardInterrupt:
                print("\n\n用户中断")
                sys.exit(1)
            except Exception as e:
                print(f"\n❌ 分析失败：{e}")
                import traceback
                traceback.print_exc()


if __name__ == "__main__":
    main()
