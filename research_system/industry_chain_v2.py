"""
产业链知识库 V2 - 结构化数据模型
参考腾讯产业链知识图谱方案
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


_RELATION_TYPE = "upstream"


class IndustryChainV2:
    """产业链知识库 V2 - 支持结构化关系"""

    def __init__(self, data_dir: str | Path | None = None):
        # Resolve the bundled data relative to the repository, not the caller's
        # working directory.  Explicit directories remain useful for tests and
        # isolated imports.
        self.data_dir = Path(data_dir) if data_dir is not None else (
            Path(__file__).resolve().parents[1] / 'data' / 'industry_chains'
        )
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 加载数据
        self.products = self._load_json('products.json', [])
        self.product_relations = self._load_json('product_relations.json', [])
        self.company_products = self._load_json('company_products.json', [])
        self.metadata = self._load_json('metadata.json', {})
        self.validation = self.validate()

    def _load_json(self, filename: str, default: Any) -> Any:
        """加载JSON文件"""
        file_path = self.data_dir / filename
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return default

    def _save_json(self, filename: str, data: Any):
        """保存JSON文件"""
        file_path = self.data_dir / filename
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _refresh_metadata_counts(self) -> None:
        """Persist record counts after graph mutations when metadata exists."""
        if not isinstance(self.metadata, dict) or not self.metadata:
            return
        self.metadata["counts"] = {
            "products": len(self.products),
            "relations": len(self.product_relations),
            "companies": len(self.company_products),
        }
        self.metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save_json("metadata.json", self.metadata)

    def get_product(self, product_name: str) -> Optional[Dict]:
        """获取产品信息"""
        for product in self.products:
            if product['name'] == product_name:
                return product
        return None

    def validate(self) -> Dict[str, Any]:
        """Validate the graph without mutating it.

        The report is intentionally conservative: migrated/manual records are
        usable for research display, but missing evidence or unknown relation
        endpoints are surfaced instead of silently treated as facts.
        """
        errors: List[str] = []
        warnings: List[str] = []
        product_names = set()
        for index, product in enumerate(self.products):
            if not isinstance(product, dict):
                errors.append(f"products[{index}] must be an object")
                continue
            name = str(product.get("name") or "").strip()
            if not name:
                errors.append(f"products[{index}] missing name")
            elif name in product_names:
                errors.append(f"duplicate product name: {name}")
            product_names.add(name)
            if not product.get("source"):
                warnings.append(f"product {name or index} has no source")
            if not product.get("evidence") and product.get("source") == "v1_migration":
                warnings.append(f"product {name or index} is migrated without evidence")

        company_codes = set()
        for index, company in enumerate(self.company_products):
            if not isinstance(company, dict):
                errors.append(f"company_products[{index}] must be an object")
                continue
            code = str(company.get("stock_code") or "").strip()
            if not code:
                errors.append(f"company_products[{index}] missing stock_code")
            elif code in company_codes:
                errors.append(f"duplicate stock_code: {code}")
            company_codes.add(code)
            for product in company.get("products") or []:
                if product not in product_names:
                    errors.append(f"company {code} references unknown product: {product}")

        for index, relation in enumerate(self.product_relations):
            if not isinstance(relation, dict):
                errors.append(f"product_relations[{index}] must be an object")
                continue
            source = str(relation.get("from") or "").strip()
            target = str(relation.get("to") or "").strip()
            if source not in product_names or target not in product_names:
                errors.append(f"relation[{index}] references unknown product: {source}->{target}")
            if relation.get("relation") != _RELATION_TYPE:
                errors.append(f"relation[{index}] has unsupported relation type")
            if not relation.get("source"):
                warnings.append(f"relation[{index}] has no source")

        actual_counts = {
            "products": len(self.products),
            "relations": len(self.product_relations),
            "companies": len(self.company_products),
        }
        if not isinstance(self.metadata, dict):
            errors.append("metadata must be an object")
        else:
            if self.metadata.get("schema_version") != "industry-chain.v2":
                warnings.append("metadata does not declare industry-chain.v2 schema")
            if self.metadata.get("relation_semantics") != "directed_supply_edge":
                warnings.append("metadata does not declare directed_supply_edge semantics")
            declared_counts = self.metadata.get("counts")
            if declared_counts is None:
                warnings.append("metadata does not declare record counts")
            elif not isinstance(declared_counts, dict):
                errors.append("metadata counts must be an object")
            else:
                for key, actual in actual_counts.items():
                    if declared_counts.get(key) != actual:
                        errors.append(
                            f"metadata count mismatch for {key}: "
                            f"declared={declared_counts.get(key)} actual={actual}"
                        )
            if self.metadata.get("license_status") == "UNVERIFIED":
                warnings.append("dataset license is unverified")

        return {
            "status": "VALID" if not errors else "INVALID",
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors,
            "warnings": warnings,
            "actual_counts": actual_counts,
        }

    def get_upstream_products(self, product_name: str) -> List[Dict]:
        """获取上游产品。

        Relations are stored as directed supply edges: ``from -> to`` means
        that ``from`` is upstream of ``to``. The label therefore must be
        ``upstream`` and cannot redefine the edge direction.
        """
        upstream = []
        for relation in self.product_relations:
            if (
                relation.get('to') == product_name
                and relation.get('relation') == _RELATION_TYPE
            ):
                from_product = self.get_product(relation['from'])
                if from_product:
                    upstream.append({
                        'product': from_product,
                        'strength': relation.get('strength', 'medium'),
                        'confidence': relation.get('confidence', 0.8),
                        'relation': relation.get('relation', 'upstream'),
                    })
        return upstream

    def get_downstream_products(self, product_name: str) -> List[Dict]:
        """获取下游产品 using the directed edge ``from -> to``."""
        downstream = []
        for relation in self.product_relations:
            if (
                relation.get('from') == product_name
                and relation.get('relation') == _RELATION_TYPE
            ):
                to_product = self.get_product(relation['to'])
                if to_product:
                    downstream.append({
                        'product': to_product,
                        'strength': relation.get('strength', 'medium'),
                        'confidence': relation.get('confidence', 0.8),
                        'relation': relation.get('relation', 'upstream'),
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
        if not isinstance(max_depth, int) or isinstance(max_depth, bool) or max_depth < 0:
            raise ValueError("max_depth must be a non-negative integer")

        def _get_chain_recursive(
            name: str, direction: str, depth: int, path: tuple[str, ...]
        ) -> List:
            if depth >= max_depth:
                return []

            if direction == 'upstream':
                related = self.get_upstream_products(name)
            else:
                related = self.get_downstream_products(name)

            result = []
            for item in related:
                child_name = item['product']['name']
                if child_name in path:
                    continue
                result.append({
                    'product': item['product'],
                    'strength': item['strength'],
                    'confidence': item.get('confidence', 0.8),
                    'children': _get_chain_recursive(
                        child_name,
                        direction,
                        depth + 1,
                        path + (child_name,)
                    )
                })
            return result

        current = self.get_product(product_name)
        if not current:
            return {'error': f'产品 {product_name} 不存在'}

        return {
            'data_version': self.metadata.get('schema_version', 'industry-chain.v2'),
            'source': self.metadata.get('source', 'unknown'),
            'source_status': self.metadata.get('source_status', 'UNKNOWN'),
            'license_status': self.metadata.get('license_status', 'UNVERIFIED'),
            'upstream': _get_chain_recursive(product_name, 'upstream', 0, (product_name,)),
            'current': current,
            'downstream': _get_chain_recursive(product_name, 'downstream', 0, (product_name,)),
            'validation_status': self.validation['status'],
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
        normalized_code = str(stock_code or '').strip().upper().split('.', 1)[0]
        for cp in self.company_products:
            company_code = str(cp.get('stock_code') or '').strip().upper().split('.', 1)[0]
            if company_code == normalized_code:
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
        if not isinstance(product, dict):
            raise ValueError("product must be an object")
        product_name = str(product.get('name') or '').strip()
        if not product_name:
            raise ValueError("product name is required")
        if not str(product.get('source') or '').strip():
            raise ValueError("product source is required")
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
        self._refresh_metadata_counts()
        self.validation = self.validate()

    def add_relation(self, from_product: str, to_product: str, relation: str, **kwargs):
        """添加产品关系，方向固定为上游 ``from -> to``。"""
        if relation != _RELATION_TYPE:
            raise ValueError(f"unsupported relation type: {relation}")
        if not self.get_product(from_product) or not self.get_product(to_product):
            raise ValueError("relation endpoints must reference existing products")
        if from_product == to_product:
            raise ValueError("self-referential product relations are not allowed")
        if not str(kwargs.get('source') or '').strip():
            raise ValueError("relation source is required")
        relation_data = {
            'from': from_product,
            'to': to_product,
            'relation': relation,
            'update_time': datetime.now(timezone.utc).isoformat(),
            **kwargs
        }

        # 检查是否已存在
        for i, r in enumerate(self.product_relations):
            if r['from'] == from_product and r['to'] == to_product and r['relation'] == relation:
                self.product_relations[i] = relation_data
                self._save_json('product_relations.json', self.product_relations)
                self._refresh_metadata_counts()
                self.validation = self.validate()
                return

        # 新增
        self.product_relations.append(relation_data)
        self._save_json('product_relations.json', self.product_relations)
        self._refresh_metadata_counts()
        self.validation = self.validate()

    def add_company_product(self, stock_code: str, stock_name: str, products: List[str], **kwargs):
        """添加公司-产品映射"""
        if not str(stock_code or '').strip():
            raise ValueError("stock_code is required")
        if not str(kwargs.get('source') or '').strip():
            raise ValueError("company-product source is required")
        unknown_products = [name for name in products if not self.get_product(name)]
        if unknown_products:
            raise ValueError(
                f"company references unknown products: {', '.join(unknown_products)}"
            )
        cp_data = {
            'stock_code': stock_code,
            'stock_name': stock_name,
            'products': products,
            'update_time': datetime.now(timezone.utc).isoformat(),
            **kwargs
        }

        # 检查是否已存在
        for i, cp in enumerate(self.company_products):
            if cp['stock_code'] == stock_code:
                self.company_products[i] = cp_data
                self._save_json('company_products.json', self.company_products)
                self._refresh_metadata_counts()
                self.validation = self.validate()
                return

        # 新增
        self.company_products.append(cp_data)
        self._save_json('company_products.json', self.company_products)
        self._refresh_metadata_counts()
        self.validation = self.validate()

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
