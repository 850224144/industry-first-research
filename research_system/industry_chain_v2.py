"""
产业链知识库 V2 - 结构化数据模型
参考腾讯产业链知识图谱方案
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime


class IndustryChainV2:
    """产业链知识库 V2 - 支持结构化关系"""

    def __init__(self, data_dir='data/industry_chains'):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 加载数据
        self.products = self._load_json('products.json', [])
        self.product_relations = self._load_json('product_relations.json', [])
        self.company_products = self._load_json('company_products.json', [])
        self.metadata = self._load_json('metadata.json', {})

    def _load_json(self, filename: str, default: any) -> any:
        """加载JSON文件"""
        file_path = self.data_dir / filename
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return default

    def _save_json(self, filename: str, data: any):
        """保存JSON文件"""
        file_path = self.data_dir / filename
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_product(self, product_name: str) -> Optional[Dict]:
        """获取产品信息"""
        for product in self.products:
            if product['name'] == product_name:
                return product
        return None

    def get_upstream_products(self, product_name: str) -> List[Dict]:
        """获取上游产品"""
        upstream = []
        for relation in self.product_relations:
            if relation['to'] == product_name and relation['relation'] == 'upstream':
                from_product = self.get_product(relation['from'])
                if from_product:
                    upstream.append({
                        'product': from_product,
                        'strength': relation.get('strength', 'medium'),
                        'confidence': relation.get('confidence', 0.8),
                    })
        return upstream

    def get_downstream_products(self, product_name: str) -> List[Dict]:
        """获取下游产品"""
        downstream = []
        for relation in self.product_relations:
            if relation['from'] == product_name and relation['relation'] == 'downstream':
                to_product = self.get_product(relation['to'])
                if to_product:
                    downstream.append({
                        'product': to_product,
                        'strength': relation.get('strength', 'medium'),
                        'confidence': relation.get('confidence', 0.8),
                    })
        return downstream

    def get_product_chain(self, product_name: str, max_depth: int = 3) -> Dict:
        """
        获取完整产业链

        Args:
            product_name: 产品名称
            max_depth: 递归深度

        Returns:
            完整产业链结构
        """
        def _get_chain_recursive(name: str, direction: str, depth: int) -> List:
            if depth >= max_depth:
                return []

            if direction == 'upstream':
                related = self.get_upstream_products(name)
            else:
                related = self.get_downstream_products(name)

            result = []
            for item in related:
                result.append({
                    'product': item['product'],
                    'strength': item['strength'],
                    'children': _get_chain_recursive(
                        item['product']['name'],
                        direction,
                        depth + 1
                    )
                })
            return result

        current = self.get_product(product_name)
        if not current:
            return {'error': f'产品 {product_name} 不存在'}

        return {
            'upstream': _get_chain_recursive(product_name, 'upstream', 0),
            'current': current,
            'downstream': _get_chain_recursive(product_name, 'downstream', 0),
        }

    def get_companies_by_product(self, product_name: str) -> List[Dict]:
        """获取生产该产品的公司"""
        companies = []
        for cp in self.company_products:
            if product_name in cp['products']:
                companies.append(cp)
        return companies

    def get_products_by_company(self, stock_code: str) -> Optional[Dict]:
        """获取公司的产品列表"""
        for cp in self.company_products:
            if cp['stock_code'] == stock_code:
                products = []
                for product_name in cp['products']:
                    product = self.get_product(product_name)
                    if product:
                        products.append(product)
                return {
                    'company': cp,
                    'products': products,
                }
        return None

    def add_product(self, product: Dict):
        """添加产品"""
        # 检查是否已存在
        existing = self.get_product(product['name'])
        if existing:
            # 更新
            for i, p in enumerate(self.products):
                if p['name'] == product['name']:
                    self.products[i] = product
                    break
        else:
            # 新增
            self.products.append(product)

        self._save_json('products.json', self.products)

    def add_relation(self, from_product: str, to_product: str, relation: str, **kwargs):
        """添加产品关系"""
        relation_data = {
            'from': from_product,
            'to': to_product,
            'relation': relation,
            'update_time': datetime.now().isoformat(),
            **kwargs
        }

        # 检查是否已存在
        for i, r in enumerate(self.product_relations):
            if r['from'] == from_product and r['to'] == to_product and r['relation'] == relation:
                self.product_relations[i] = relation_data
                self._save_json('product_relations.json', self.product_relations)
                return

        # 新增
        self.product_relations.append(relation_data)
        self._save_json('product_relations.json', self.product_relations)

    def add_company_product(self, stock_code: str, stock_name: str, products: List[str], **kwargs):
        """添加公司-产品映射"""
        cp_data = {
            'stock_code': stock_code,
            'stock_name': stock_name,
            'products': products,
            'update_time': datetime.now().isoformat(),
            **kwargs
        }

        # 检查是否已存在
        for i, cp in enumerate(self.company_products):
            if cp['stock_code'] == stock_code:
                self.company_products[i] = cp_data
                self._save_json('company_products.json', self.company_products)
                return

        # 新增
        self.company_products.append(cp_data)
        self._save_json('company_products.json', self.company_products)

    def visualize_chain(self, product_name: str) -> str:
        """
        可视化产业链（文本形式）

        Returns:
            产业链的文本表示
        """
        chain = self.get_product_chain(product_name)

        if 'error' in chain:
            return chain['error']

        lines = []
        lines.append(f"产业链: {product_name}")
        lines.append("=" * 60)

        # 上游
        if chain['upstream']:
            lines.append("\n【上游】")
            for item in chain['upstream']:
                p = item['product']
                lines.append(f"  ← {p['name']} ({p['level']}级, {p['importance_score']}分)")
                if item['children']:
                    for child in item['children']:
                        cp = child['product']
                        lines.append(f"    ← {cp['name']} ({cp['level']}级)")

        # 当前
        current = chain['current']
        lines.append(f"\n【当前】")
        lines.append(f"  ● {current['name']} ({current['level']}级, {current['importance_score']}分)")
        lines.append(f"    {current.get('analogy', '')}")

        # 下游
        if chain['downstream']:
            lines.append("\n【下游】")
            for item in chain['downstream']:
                p = item['product']
                lines.append(f"  → {p['name']} ({p['level']}级, {p['importance_score']}分)")
                if item['children']:
                    for child in item['children']:
                        cp = child['product']
                        lines.append(f"    → {cp['name']} ({cp['level']}级)")

        return '\n'.join(lines)

    def get_statistics(self) -> Dict:
        """获取统计信息"""
        industries = set()
        for product in self.products:
            industries.add(product.get('industry', '未知'))

        companies_set = set()
        for cp in self.company_products:
            companies_set.add(cp['stock_code'])

        return {
            'product_count': len(self.products),
            'relation_count': len(self.product_relations),
            'company_count': len(companies_set),
            'industry_count': len(industries),
            'industries': list(industries),
        }


# 测试代码
if __name__ == "__main__":
    chain = IndustryChainV2()

    print("产业链知识库 V2 测试")
    print("=" * 60)

    # 统计信息
    stats = chain.get_statistics()
    print(f"\n当前数据:")
    print(f"  产品数: {stats['product_count']}")
    print(f"  关系数: {stats['relation_count']}")
    print(f"  公司数: {stats['company_count']}")
    print(f"  行业数: {stats['industry_count']}")

    if stats['product_count'] > 0:
        # 测试查询
        product_name = chain.products[0]['name']
        print(f"\n测试: 查询产品 '{product_name}'")
        print(chain.visualize_chain(product_name))
    else:
        print("\n⚠️ 数据文件为空，需要先导入数据")
        print("提示: 运行 tools/migrate_to_v2.py 迁移现有数据")
