"""
AKShare增强数据采集模块
深度利用AKShare API，补充行业分类和公司主营业务数据
"""

import akshare as ak
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional
import json
from pathlib import Path


class AKShareEnhanced:
    """增强的AKShare数据采集器"""

    def __init__(self, cache_dir='data/cache'):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_all_industries(self) -> Dict[str, pd.DataFrame]:
        """
        获取所有行业分类标准

        Returns:
            包含多套行业分类的字典
        """
        print("正在获取行业分类数据...")

        industries = {}

        # 1. 东方财富行业板块（市场实时板块，不等同于申万）
        try:
            print("  - 东方财富行业分类...")
            em_industries = ak.stock_board_industry_name_em()
            industries['eastmoney'] = em_industries
            print(f"    ✓ 获取到 {len(em_industries)} 个行业")
        except Exception as e:
            print(f"    ✗ 失败: {e}")
            industries['eastmoney'] = pd.DataFrame()

        # 2. 证监会/巨潮/申万等分类标准（巨潮公开接口）
        for key, symbol in {
            'csrc': '证监会行业分类标准',
            'cninfo': '巨潮行业分类标准',
            'shenwan': '申银万国行业分类标准',
        }.items():
            try:
                print(f"  - {symbol}...")
                industries[key] = ak.stock_industry_category_cninfo(symbol=symbol)
                print(f"    ✓ 获取到 {len(industries[key])} 个分类")
            except Exception as e:
                print(f"    ✗ 失败: {e}")
                industries[key] = pd.DataFrame()

        # 3. 概念板块（补充维度）
        try:
            print("  - 概念板块...")
            concept = ak.stock_board_concept_name_em()
            industries['concept'] = concept
            print(f"    ✓ 获取到 {len(concept)} 个概念")
        except Exception as e:
            print(f"    ✗ 失败: {e}")
            industries['concept'] = pd.DataFrame()

        return industries

    def get_industry_companies(self, industry_name: str) -> pd.DataFrame:
        """
        获取指定行业的所有成分股

        Args:
            industry_name: 行业名称（如"光伏设备"）

        Returns:
            该行业的所有公司数据
        """
        try:
            print(f"正在获取 {industry_name} 行业成分股...")
            companies = ak.stock_board_industry_cons_em(symbol=industry_name)
            print(f"  ✓ 获取到 {len(companies)} 家公司")
            return companies
        except Exception as e:
            print(f"  ✗ 失败: {e}")
            return pd.DataFrame()

    def get_company_main_business(self, stock_code: str) -> Dict:
        """
        获取公司主营业务信息

        Args:
            stock_code: 股票代码

        Returns:
            主营业务数据
        """
        try:
            # 尝试获取同花顺主营业务
            business = ak.stock_zyjs_ths(symbol=stock_code)

            if business is not None and not business.empty:
                return {
                    'stock_code': stock_code,
                    'main_business': business.to_dict('records'),
                    'source': 'ths',
                    'update_time': datetime.now().isoformat(),
                }
        except Exception as e:
            pass

        # 如果失败，尝试从个股信息获取
        try:
            info = ak.stock_individual_info_em(symbol=stock_code)
            business_desc = ''
            for _, row in info.iterrows():
                if row['item'] == '经营范围' or row['item'] == '主营业务':
                    business_desc = row['value']
                    break

            return {
                'stock_code': stock_code,
                'main_business_desc': business_desc,
                'source': 'eastmoney',
                'update_time': datetime.now().isoformat(),
            }
        except Exception as e:
            return {
                'stock_code': stock_code,
                'error': str(e),
                'update_time': datetime.now().isoformat(),
            }

    def generate_security_master(self, sample_size: Optional[int] = None) -> List[Dict]:
        """
        生成全A股公司主表快照

        Args:
            sample_size: 样本数量（测试用，None表示全部）

        Returns:
            公司主表数据列表
        """
        print("=" * 60)
        print("生成全A股公司主表快照")
        print("=" * 60)

        # 1. 获取所有A股
        print("\n1. 获取所有A股列表...")
        try:
            all_stocks = ak.stock_zh_a_spot_em()
            print(f"   ✓ 获取到 {len(all_stocks)} 只股票")
        except Exception as e:
            print(f"   ✗ 失败: {e}")
            return []

        # 测试模式：只取样本
        if sample_size:
            all_stocks = all_stocks.head(sample_size)
            print(f"   测试模式：只处理前 {sample_size} 只")

        # 2. 获取行业分类
        print("\n2. 获取行业分类...")
        industries = self.get_all_industries()

        # Build one reverse index from industry constituents.  The old
        # implementation queried every industry for every stock, which could
        # create hundreds of thousands of requests.
        print("\n3. 建立行业成分反向索引...")
        industry_membership = self._build_industry_membership_index(industries.get('eastmoney'))

        # 4. 逐个获取公司详细信息
        print(f"\n4. 获取公司详细信息 (共{len(all_stocks)}只)...")
        master = []

        for idx, (_, stock) in enumerate(all_stocks.iterrows(), 1):
            code = self._normalize_stock_code(stock['代码'])
            name = stock['名称']

            print(f"   [{idx}/{len(all_stocks)}] {name}({code})...", end=" ")

            # 获取行业归属
            industry_em = industry_membership.get(code, "未知")

            # 获取主营业务
            main_business = self.get_company_main_business(code)

            master.append({
                'code': code,
                'name': name,
                'industry_em': industry_em,
                'market_cap': float(stock.get('总市值', 0)) / 100000000,  # 转为亿
                'pe': float(stock.get('市盈率-动态', 0)),
                'main_business': main_business,
                'update_time': datetime.now().isoformat(),
            })

            print("✓")

        # 4. 保存快照
        output_file = self.cache_dir / f'security_master_{datetime.now().strftime("%Y%m%d")}.json'
        self._save_json(output_file, master)
        print(f"\n✓ 保存到: {output_file}")
        print(f"✓ 共 {len(master)} 家公司")

        return master

    def _build_industry_membership_index(self, industry_df: pd.DataFrame) -> Dict[str, str]:
        """Fetch each board once and map stock code to its first board."""
        membership: Dict[str, str] = {}
        if industry_df is None or industry_df.empty:
            return membership
        for _, industry in industry_df.iterrows():
            industry_name = industry.get('板块名称', industry.get('name', ''))
            if not industry_name:
                continue
            try:
                companies = ak.stock_board_industry_cons_em(symbol=industry_name)
                for code in companies.get('代码', []):
                    normalized_code = self._normalize_stock_code(code)
                    if normalized_code:
                        membership.setdefault(normalized_code, industry_name)
            except Exception:
                continue
        return membership

    def _find_industry(self, stock_code: str, industry_df: pd.DataFrame) -> str:
        """Backward-compatible single-code lookup."""
        code = self._normalize_stock_code(stock_code)
        return self._build_industry_membership_index(industry_df).get(code, "未知")

    @staticmethod
    def _normalize_stock_code(value: object) -> str:
        """Normalize common AKShare code representations to six digits."""
        code = str(value or '').strip().upper()
        if code.endswith('.0') and code[:-2].isdigit():
            code = code[:-2]
        parts = code.split('.')
        if len(parts) == 2:
            if parts[0] in {'SH', 'SZ', 'BJ'}:
                code = parts[1]
            elif parts[1] in {'SH', 'SZ', 'BJ'}:
                code = parts[0]
        return code.zfill(6) if code.isdigit() else code

    def _save_json(self, file_path: Path, data: any):
        """保存JSON文件"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_industry_chain_info(self, industry_name: str) -> Dict:
        """
        获取行业产业链相关信息（辅助功能）

        从行业成分股中分析：
        - 主要上市公司
        - 市值分布
        - 龙头企业

        Args:
            industry_name: 行业名称

        Returns:
            产业链相关信息
        """
        companies = self.get_industry_companies(industry_name)

        if companies.empty:
            return {'error': '无法获取行业数据'}

        # 按市值排序
        companies_sorted = companies.sort_values('总市值', ascending=False)

        # 前5大公司
        top5 = companies_sorted.head(5)[['名称', '代码', '总市值', '市盈率-动态']].to_dict('records')

        # 市值集中度
        total_cap = companies_sorted['总市值'].sum()
        top5_cap = companies_sorted.head(5)['总市值'].sum()
        concentration = top5_cap / total_cap if total_cap > 0 else 0

        return {
            'industry': industry_name,
            'company_count': len(companies),
            'total_market_cap': total_cap / 100000000,  # 亿元
            'top5_companies': top5,
            'concentration': f'{concentration*100:.1f}%',
            'leader': top5[0] if top5 else None,
        }


# 测试代码
if __name__ == "__main__":
    enhancer = AKShareEnhanced()

    print("测试1: 获取行业分类")
    print("=" * 60)
    industries = enhancer.get_all_industries()
    for source, df in industries.items():
        print(f"{source}: {len(df)} 个分类")

    print("\n测试2: 获取光伏设备行业信息")
    print("=" * 60)
    info = enhancer.get_industry_chain_info("光伏设备")
    print(json.dumps(info, ensure_ascii=False, indent=2))

    print("\n测试3: 生成公司主表快照（前10只）")
    print("=" * 60)
    master = enhancer.generate_security_master(sample_size=10)
    print(f"\n样本数据:")
    print(json.dumps(master[:2], ensure_ascii=False, indent=2))
