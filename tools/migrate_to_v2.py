"""
数据迁移工具：从V1硬编码迁移到V2结构化数据
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from research_system.industry_chain_knowledge import INDUSTRY_CHAINS
from research_system.industry_chain_v2 import IndustryChainV2


def migrate_v1_to_v2():
    """将V1硬编码数据迁移到V2结构"""

    print("=" * 60)
    print("数据迁移: V1 → V2")
    print("=" * 60)

    chain_v2 = IndustryChainV2()

    total_products = 0
    total_relations = 0
    total_companies = 0

    # 遍历所有行业
    for industry_name, chain_v1 in INDUSTRY_CHAINS.items():
        print(f"\n处理行业: {industry_name}")

        # 1. 迁移产品
        print("  - 迁移产品...")
        for product_name, product_config in chain_v1.products.items():
            chain_v2.add_product({
                'id': f"prod_{industry_name}_{product_name}".replace(' ', '_'),
                'name': product_name,
                'industry': industry_name,
                'level': product_config['level'],
                'level_name': product_config['level_name'],
                'importance_score': product_config['importance_score'],
                'reason': product_config['reason'],
                'value_ratio': product_config['value_ratio'],
                'value_ratio_desc': product_config['value_ratio_desc'],
                'substitutability': product_config['substitutability'],
                'substitutability_desc': product_config['substitutability_desc'],
                'tech_barrier': product_config['tech_barrier'],
                'tech_barrier_desc': product_config['tech_barrier_desc'],
                'market_concentration': product_config['market_concentration'],
                'market_concentration_desc': product_config['market_concentration_desc'],
                'analogy': product_config['analogy'],
                'source': 'v1_migration',
                'confidence': 0.95,
                'version': 'v1.0',
            })
            total_products += 1

        # 2. 解析产业链流程，生成关系
        print("  - 生成产品关系...")
        flow = chain_v1.chain_flow
        if flow:
            # 简单解析：按 "→" 分割
            segments = [s.strip() for s in flow.split('→')]

            # 生成上下游关系
            for i in range(len(segments) - 1):
                from_product = segments[i]
                to_product = segments[i + 1]

                # 检查产品是否存在于配置中
                if from_product in chain_v1.products and to_product in chain_v1.products:
                    chain_v2.add_relation(
                        from_product=from_product,
                        to_product=to_product,
                        # A relation is a directed supply edge: from -> to.
                        # The label describes the role of ``from`` relative to
                        # ``to`` and is not a second direction to be queried.
                        relation='upstream',
                        strength='strong',
                        source='v1_chain_flow',
                        confidence=0.9,
                    )
                    total_relations += 1

        # 3. 迁移公司
        print("  - 迁移公司...")
        for stock_code, company_info in chain_v1.companies.items():
            chain_v2.add_company_product(
                stock_code=stock_code,
                stock_name=company_info['name'],
                products=company_info['products'],
                position=company_info['position'],
                source='v1_migration',
                confidence=0.95,
            )
            total_companies += 1

        print(f"    ✓ 完成: {len(chain_v1.products)}个产品, {len(chain_v1.companies)}家公司")

    # 统计
    print("\n" + "=" * 60)
    print("迁移完成!")
    print("=" * 60)
    print(f"  产品: {total_products}")
    print(f"  关系: {total_relations}")
    print(f"  公司: {total_companies}")

    chain_v2._save_json('metadata.json', {
        'schema_version': 'industry-chain.v2',
        'relation_semantics': 'directed_supply_edge',
        'relation_definition': 'from is upstream of to',
        'source': 'v1_migration',
        'source_status': 'configuration_only',
        'license_status': 'UNVERIFIED',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'counts': {
            'products': len(chain_v2.products),
            'relations': len(chain_v2.product_relations),
            'companies': len(chain_v2.company_products),
        },
        'notes': [
            'Migrated from manually maintained V1 configuration.',
            'Verify company-product and product-product claims against primary sources before commercial use.',
        ],
    })

    # 验证
    print("\n验证数据...")
    stats = chain_v2.get_statistics()
    print(f"  实际保存: {stats['product_count']}个产品, {stats['company_count']}家公司")

    # 测试查询
    if stats['product_count'] > 0:
        print("\n测试查询第一个产品:")
        first_product = chain_v2.products[0]['name']
        print(chain_v2.visualize_chain(first_product))


if __name__ == "__main__":
    migrate_v1_to_v2()
