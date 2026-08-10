#!/usr/bin/env python3
"""
运行上海电力的完整研究管道

展示从补充证据数据 → 完整分析管道 → 研究报告的流程
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from industry_first_research.research_pipeline import build_research_pipeline


def run_shanghai_electric_power_pipeline():
    """运行上海电力研究管道"""
    print("="*80)
    print("  上海电力（600021）完整研究管道")
    print("="*80)

    # 加载补充证据数据
    supplemental_file = PROJECT_ROOT / "tests/fixtures/companies/shanghai_electric_power_600021_supplemental.json"

    if not supplemental_file.exists():
        print("❌ 错误：找不到上海电力补充证据数据")
        return False

    print("\n1️⃣  加载补充证据数据...")
    with open(supplemental_file) as f:
        supplemental_report = json.load(f)

    print(f"✅ 数据加载成功")
    print(f"   - 公司: {supplemental_report['display_name']}")
    print(f"   - 覆盖状态: {supplemental_report['coverage_state']}")
    print(f"   - 字段覆盖: {supplemental_report['coverage_summary']['verified_fields']}/{supplemental_report['coverage_summary']['total_fields']}")

    # 运行研究管道
    print("\n2️⃣  运行研究管道...")
    print("   阶段:")

    try:
        pipeline_result = build_research_pipeline(
            supplemental_report,
            snapshot_id="shanghai-electric-power-pipeline-20260810"
        )

        print("   ✓ product_profile - 产品画像")
        print("   ✓ application_mapping - 应用映射")
        print("   ✓ demand_transmission - 需求传导")
        print("   ✓ industry_situation - 行业处境")
        print("   ✓ cycle_reversal - 周期反转")
        print("   ✓ competitive_position - 竞争位置")
        print("   ✓ survival_analysis - 生存分析")
        print("   ✓ valuation_scenarios - 估值情景")
        print("   ✓ adversarial_review - 对抗审查")
        print("   ✓ research_report - 研究报告")

        print(f"\n✅ 研究管道执行成功")

        # 显示最终状态
        print("\n3️⃣  分析结果:")
        final_state = pipeline_result.get("final_state", {})
        print(f"   - 最终状态: {final_state.get('pipeline_state', 'UNKNOWN')}")

        # 显示研究报告状态
        research_report = pipeline_result.get("stages", {}).get("research_report", {})
        report_state = research_report.get("report_state", "UNKNOWN")
        print(f"   - 报告状态: {report_state}")

        # 保存结果
        output_dir = PROJECT_ROOT / "data/company_research_pipelines"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "shanghai-electric-power-pipeline-20260810.json"

        with open(output_file, "w") as f:
            json.dump(pipeline_result, f, ensure_ascii=False, indent=2)

        print(f"\n4️⃣  结果已保存:")
        print(f"   {output_file}")

        return True

    except Exception as e:
        print(f"\n❌ 管道执行失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_shanghai_electric_power_pipeline()
    sys.exit(0 if success else 1)
