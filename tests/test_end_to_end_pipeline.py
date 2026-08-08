"""
端到端研究流程示例

完整流程：行业雷达 → 行业公司池 → 公司LIGHT筛选 → 1家公司深研 → 报告 → 研究版本 → 跟踪

测试场景：以通威股份（600438.SH）为例，走通完整研究链路
"""
import json
from pathlib import Path
from datetime import datetime


# ============================================================================
# 第一步：行业雷达 - 发现光伏行业
# ============================================================================

def step1_industry_radar():
    """
    行业雷达：发现光伏行业信号

    数据来源：同花顺、东方财富行业涨幅榜
    输出：industry-radar.v1.json
    """
    radar_data = {
        "schema_version": "industry-radar.v1",
        "scan_id": "radar-scan-20260520-001",
        "scan_date": "2026-05-20",
        "source": "cross_validation",
        "industries": [
            {
                "industry_id": "881143",
                "industry_name": "光伏设备",
                "source": "tonghuashun",
                "rank": 2,
                "score": 8.5,
                "price_change_1d": 3.2,
                "price_change_5d": 12.5,
                "price_change_20d": 28.7,
                "volume_ratio": 1.85,
                "leading_stocks": ["通威股份", "隆基绿能", "TCL中环"],
                "signal_strength": "STRONG",
                "cross_validated": True,
                "validation_sources": ["tonghuashun", "eastmoney"],
                "observation_status": "CROSS_VALIDATED"
            }
        ],
        "metadata": {
            "radar_limit": 50,
            "filters": ["price_change_20d > 15%", "volume_ratio > 1.5"],
            "execution_mode": "LOCAL_ONLY"
        }
    }

    print("=" * 80)
    print("第1步：行业雷达 - 发现光伏设备行业")
    print("=" * 80)
    print(f"行业名称：{radar_data['industries'][0]['industry_name']}")
    print(f"行业代码：{radar_data['industries'][0]['industry_id']}")
    print(f"20日涨幅：{radar_data['industries'][0]['price_change_20d']}%")
    print(f"信号强度：{radar_data['industries'][0]['signal_strength']}")
    print(f"交叉验证：{radar_data['industries'][0]['cross_validated']}")
    print(f"龙头股票：{', '.join(radar_data['industries'][0]['leading_stocks'])}")
    print()

    return radar_data


# ============================================================================
# 第二步：行业公司池 - 加载光伏行业公司
# ============================================================================

def step2_company_pool(radar_data):
    """
    行业公司池：加载光伏设备行业的代表公司

    数据来源：同花顺行业成份股
    输出：tonghuashun-company-pool-881143.json
    """
    company_pool = {
        "schema_version": "tonghuashun-company-pool.v1",
        "industry_id": "881143",
        "industry_name": "光伏设备",
        "as_of": "2026-05-20",
        "pool_size": 10,
        "companies": [
            {
                "stock_code": "600438",
                "stock_name": "通威股份",
                "listing_market": "SH",
                "market_cap": 2156789012345,
                "pe_ttm": 18.5,
                "industry": "光伏设备",
                "main_business": "高纯晶硅、太阳能电池片等光伏产品",
                "pool_rank": 1
            },
            {
                "stock_code": "601012",
                "stock_name": "隆基绿能",
                "listing_market": "SH",
                "market_cap": 1987654321098,
                "pe_ttm": 16.2,
                "industry": "光伏设备",
                "main_business": "单晶硅棒、硅片、电池、组件",
                "pool_rank": 2
            },
            {
                "stock_code": "002129",
                "stock_name": "TCL中环",
                "listing_market": "SZ",
                "market_cap": 987654321098,
                "pe_ttm": 22.3,
                "industry": "光伏设备",
                "main_business": "半导体材料、光伏硅片",
                "pool_rank": 3
            }
        ],
        "source": "tonghuashun_industry_constituents",
        "with_light_data": True
    }

    print("=" * 80)
    print("第2步：行业公司池 - 加载光伏设备公司")
    print("=" * 80)
    print(f"行业名称：{company_pool['industry_name']}")
    print(f"公司数量：{company_pool['pool_size']}")
    print(f"加载LIGHT数据：{company_pool['with_light_data']}")
    print()
    print("公司列表：")
    for company in company_pool['companies'][:3]:
        print(f"  {company['stock_code']} {company['stock_name']}")
        print(f"    市值：{company['market_cap'] / 1e9:.1f}亿")
        print(f"    主营：{company['main_business']}")
    print()

    return company_pool


# ============================================================================
# 第三步：公司LIGHT筛选 - 完整度检查
# ============================================================================

def step3_company_screening(company_pool):
    """
    公司LIGHT筛选：检查数据完整度

    验证：listing_market, main_business, industry等字段
    输出：筛选后的候选公司
    """
    screening_result = {
        "schema_version": "company-screening-result.v1",
        "screening_date": "2026-05-20",
        "input_pool_size": len(company_pool['companies']),
        "expected_industry": "光伏设备",
        "screened_companies": []
    }

    for company in company_pool['companies']:
        completeness_score = 0
        missing_fields = []

        # 检查必需字段
        if company.get('listing_market'):
            completeness_score += 1
        else:
            missing_fields.append('listing_market')

        if company.get('main_business'):
            completeness_score += 1
        else:
            missing_fields.append('main_business')

        if company.get('industry'):
            completeness_score += 1
        else:
            missing_fields.append('industry')

        status = "READY" if completeness_score == 3 else "PARTIAL"

        screening_result['screened_companies'].append({
            "stock_code": company['stock_code'],
            "stock_name": company['stock_name'],
            "completeness_score": completeness_score,
            "status": status,
            "missing_fields": missing_fields
        })

    print("=" * 80)
    print("第3步：公司LIGHT筛选 - 数据完整度检查")
    print("=" * 80)
    print(f"输入公司数：{screening_result['input_pool_size']}")
    print()
    print("筛选结果：")
    for result in screening_result['screened_companies'][:3]:
        print(f"  {result['stock_code']} {result['stock_name']}: {result['status']}")
        if result['missing_fields']:
            print(f"    缺失字段：{', '.join(result['missing_fields'])}")
    print()

    # 选择通威股份进行深研
    selected_company = next(c for c in company_pool['companies'] if c['stock_code'] == '600438')
    print(f"选择进行深研：{selected_company['stock_code']} {selected_company['stock_name']}")
    print()

    return selected_company, screening_result


# ============================================================================
# 第四步：公司深研 - 通威股份完整研究
# ============================================================================

def step4_deep_research(company):
    """
    公司深研：通威股份完整研究

    包含：公司边界、产品画像、财务分析、估值框架、对抗审查
    输出：company-research-report.v1.json
    """
    research_report = {
        "schema_version": "company-research-report.v1",
        "report_id": "research-600438-20260520-001",
        "company_code": company['stock_code'],
        "company_name": company['stock_name'],
        "research_date": "2026-05-20",
        "research_cutoff": "2026-05-20",
        "research_depth": "STANDARD",

        # 公司边界
        "company_scope": {
            "listed_entity": "通威股份有限公司",
            "consolidated_group": True,
            "main_subsidiaries": [
                "四川永祥股份有限公司",
                "通威太阳能（合肥）有限公司",
                "通威太阳能（成都）有限公司"
            ],
            "scope_status": "READY"
        },

        # 产品画像
        "product_profile": {
            "core_products": [
                {
                    "product_name": "高纯晶硅",
                    "product_type": "光伏材料",
                    "revenue_contribution": 45.2,
                    "capacity": "320000吨/年",
                    "market_position": "国内第一",
                    "lifecycle_stage": "MATURE"
                },
                {
                    "product_name": "太阳能电池片",
                    "product_type": "光伏组件",
                    "revenue_contribution": 42.8,
                    "capacity": "75GW/年",
                    "market_position": "全球第一",
                    "lifecycle_stage": "GROWING"
                }
            ],
            "profile_status": "READY"
        },

        # 财务分析
        "financial_analysis": {
            "report_period": "2025-12-31",
            "total_revenue": 128567890000,
            "revenue_yoy": 15.68,
            "net_profit": 18923456000,
            "net_profit_yoy": 22.45,
            "roe": 21.34,
            "gross_margin": 18.56,
            "net_margin": 14.72,
            "operating_cash_flow": 23456789000,
            "analysis_status": "READY"
        },

        # 估值框架
        "valuation_scenarios": {
            "pessimistic": {
                "pe": 12.0,
                "target_eps": 2.85,
                "scenario": "行业产能过剩，硅料价格暴跌"
            },
            "base": {
                "pe": 18.0,
                "target_eps": 3.85,
                "scenario": "行业稳定增长，公司维持市场地位"
            },
            "optimistic": {
                "pe": 25.0,
                "target_eps": 4.50,
                "scenario": "光伏装机超预期，公司产能持续扩张"
            },
            "framework_status": "READY"
        },

        # 对抗审查
        "adversarial_review": {
            "review_result": "PASS",
            "concerns": [],
            "review_date": "2026-05-20"
        },

        # 最终状态
        "final_status": "REVIEWABLE",
        "report_version": "1.0.0"
    }

    print("=" * 80)
    print("第4步：公司深研 - 通威股份完整研究报告")
    print("=" * 80)
    print(f"公司名称：{research_report['company_name']}")
    print(f"研究深度：{research_report['research_depth']}")
    print(f"研究截止：{research_report['research_cutoff']}")
    print()

    print("核心产品：")
    for product in research_report['product_profile']['core_products']:
        print(f"  - {product['product_name']}")
        print(f"    收入占比：{product['revenue_contribution']}%")
        print(f"    市场地位：{product['market_position']}")
    print()

    print("财务表现（2025年）：")
    fa = research_report['financial_analysis']
    print(f"  营业收入：{fa['total_revenue'] / 1e9:.1f}亿元（同比+{fa['revenue_yoy']:.1f}%）")
    print(f"  净利润：{fa['net_profit'] / 1e9:.1f}亿元（同比+{fa['net_profit_yoy']:.1f}%）")
    print(f"  ROE：{fa['roe']:.1f}%")
    print(f"  净利率：{fa['net_margin']:.1f}%")
    print()

    print("估值框架：")
    for scenario_name, scenario in research_report['valuation_scenarios'].items():
        if scenario_name.endswith('_status'):
            continue
        print(f"  {scenario_name}: PE {scenario['pe']}x, EPS {scenario['target_eps']}")
    print()

    print(f"对抗审查：{research_report['adversarial_review']['review_result']}")
    print(f"最终状态：{research_report['final_status']}")
    print()

    return research_report


# ============================================================================
# 第五步：研究版本 - 生成不可变版本记录
# ============================================================================

def step5_research_version(research_report):
    """
    研究版本：生成不可变版本记录

    记录：研究时点、证据引用、内容哈希、受影响模块
    输出：research-version.v1.json
    """
    import hashlib

    # 计算内容哈希
    report_content = json.dumps(research_report, sort_keys=True)
    content_hash = hashlib.sha256(report_content.encode()).hexdigest()[:16]

    research_version = {
        "schema_version": "research-version.v1",
        "version_id": f"version-600438-20260520-{content_hash}",
        "company_code": research_report['company_code'],
        "company_name": research_report['company_name'],
        "research_date": research_report['research_date'],
        "research_cutoff": research_report['research_cutoff'],
        "version_number": "1.0.0",
        "previous_version": None,

        "references": {
            "research_report_id": research_report['report_id'],
            "evidence_bundle_id": "evidence-600438-20260520-001",
            "market_data_snapshot_id": "market-600438-20260520-001"
        },

        "content_hashes": {
            "report_hash": content_hash,
            "evidence_hash": "abc123",
            "market_data_hash": "def456"
        },

        "affected_modules": [
            "product_profile",
            "financial_analysis",
            "valuation_scenarios",
            "adversarial_review"
        ],

        "execution_mode": "LOCAL_ONLY",
        "model_calls": 0,
        "token_usage": 0,

        "status": "LOCKED",
        "locked_at": "2026-05-20T18:00:00+08:00"
    }

    print("=" * 80)
    print("第5步：研究版本 - 生成不可变版本记录")
    print("=" * 80)
    print(f"版本ID：{research_version['version_id']}")
    print(f"版本号：{research_version['version_number']}")
    print(f"研究截止：{research_version['research_cutoff']}")
    print(f"内容哈希：{research_version['content_hashes']['report_hash']}")
    print()

    print("引用对象：")
    for ref_name, ref_id in research_version['references'].items():
        print(f"  {ref_name}: {ref_id}")
    print()

    print("受影响模块：")
    for module in research_version['affected_modules']:
        print(f"  - {module}")
    print()

    print(f"执行模式：{research_version['execution_mode']}")
    print(f"版本状态：{research_version['status']}")
    print()

    return research_version


# ============================================================================
# 第六步：持续跟踪 - 监控变化
# ============================================================================

def step6_tracking(research_version):
    """
    持续跟踪：监控研究对象变化

    跟踪：公告、财务数据、市场数据、行业动态
    输出：tracking-plan.v1.json
    """
    tracking_plan = {
        "schema_version": "tracking-plan.v1",
        "plan_id": "tracking-600438-20260520-001",
        "company_code": "600438",
        "company_name": "通威股份",
        "base_version": research_version['version_id'],
        "tracking_start": "2026-05-21",

        "tracking_items": [
            {
                "item_type": "announcement",
                "item_name": "公司公告",
                "frequency": "daily",
                "sources": ["sse", "eastmoney"],
                "triggers": ["年报", "季报", "业绩预告", "重大合同"]
            },
            {
                "item_type": "financial_data",
                "item_name": "财务数据",
                "frequency": "quarterly",
                "sources": ["eastmoney", "wind"],
                "triggers": ["营收变化>10%", "净利润变化>15%"]
            },
            {
                "item_type": "market_data",
                "item_name": "市场行情",
                "frequency": "weekly",
                "sources": ["sse"],
                "triggers": ["股价变化>20%", "成交量异常"]
            },
            {
                "item_type": "industry_data",
                "item_name": "行业动态",
                "frequency": "monthly",
                "sources": ["pv_infolink", "solarzoom"],
                "triggers": ["硅料价格变化>15%", "组件价格变化>10%"]
            },
            {
                "item_type": "commodity_futures",
                "item_name": "多晶硅现货",
                "frequency": "weekly",
                "sources": ["pv_infolink"],
                "triggers": ["价格变化>10%"]
            }
        ],

        "review_schedule": {
            "quick_review": "monthly",
            "standard_review": "quarterly",
            "deep_review": "annually"
        },

        "alert_conditions": [
            "公告中出现'业绩预警'或'风险提示'",
            "季度财务数据与预期偏离>20%",
            "硅料或电池片价格单周跌幅>15%",
            "重大产能扩张或收购公告"
        ],

        "plan_status": "ACTIVE"
    }

    print("=" * 80)
    print("第6步：持续跟踪 - 监控研究对象变化")
    print("=" * 80)
    print(f"跟踪对象：{tracking_plan['company_name']}")
    print(f"基准版本：{tracking_plan['base_version']}")
    print(f"跟踪开始：{tracking_plan['tracking_start']}")
    print()

    print("跟踪项目：")
    for item in tracking_plan['tracking_items']:
        print(f"  - {item['item_name']} ({item['frequency']})")
        print(f"    来源：{', '.join(item['sources'])}")
    print()

    print("复查计划：")
    for review_type, frequency in tracking_plan['review_schedule'].items():
        print(f"  {review_type}: {frequency}")
    print()

    print("预警条件：")
    for condition in tracking_plan['alert_conditions'][:2]:
        print(f"  - {condition}")
    print()

    print(f"计划状态：{tracking_plan['plan_status']}")
    print()

    return tracking_plan


# ============================================================================
# 主流程
# ============================================================================

def run_end_to_end_pipeline():
    """运行完整的端到端研究流程"""
    print("\n")
    print("*" * 80)
    print("*" + " " * 78 + "*")
    print("*" + " " * 20 + "端到端研究流程示例" + " " * 38 + "*")
    print("*" + " " * 10 + "行业雷达 → 公司池 → 筛选 → 深研 → 版本 → 跟踪" + " " * 16 + "*")
    print("*" + " " * 78 + "*")
    print("*" * 80)
    print("\n")

    # 第1步：行业雷达
    radar_data = step1_industry_radar()

    # 第2步：行业公司池
    company_pool = step2_company_pool(radar_data)

    # 第3步：公司筛选
    selected_company, screening_result = step3_company_screening(company_pool)

    # 第4步：公司深研
    research_report = step4_deep_research(selected_company)

    # 第5步：研究版本
    research_version = step5_research_version(research_report)

    # 第6步：持续跟踪
    tracking_plan = step6_tracking(research_version)

    # 总结
    print("=" * 80)
    print("端到端流程完成总结")
    print("=" * 80)
    print(f"✓ 第1步：行业雷达 - 发现光伏设备行业（行业代码：881143）")
    print(f"✓ 第2步：行业公司池 - 加载10家公司，选择3家展示")
    print(f"✓ 第3步：公司筛选 - 完整度检查，选定通威股份深研")
    print(f"✓ 第4步：公司深研 - 完成STANDARD深度研究，状态：REVIEWABLE")
    print(f"✓ 第5步：研究版本 - 生成不可变版本记录，状态：LOCKED")
    print(f"✓ 第6步：持续跟踪 - 建立跟踪计划，包含5类跟踪项")
    print()
    print("研究对象：600438.SH 通威股份")
    print("研究日期：2026-05-20")
    print("研究深度：STANDARD")
    print("执行模式：LOCAL_ONLY（无模型调用）")
    print("=" * 80)
    print()

    return {
        "radar_data": radar_data,
        "company_pool": company_pool,
        "screening_result": screening_result,
        "selected_company": selected_company,
        "research_report": research_report,
        "research_version": research_version,
        "tracking_plan": tracking_plan
    }


if __name__ == "__main__":
    results = run_end_to_end_pipeline()

    # 保存结果到文件（可选）
    output_dir = Path(__file__).parent / "output" / "end_to_end_example"
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / "pipeline_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"流程结果已保存到: {output_dir / 'pipeline_results.json'}")
