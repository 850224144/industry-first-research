"""
验证真实CLI命令能否使用我们创建的数据样例

测试完整链路：identity + fundamentals → futures-fundamentals CLI → report
"""
import json
import subprocess
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "commodities"
OUTPUT_DIR = Path(__file__).parent / "output" / "cli_verification"

# 使用正确的Python路径
PYTHON = sys.executable


def test_steel_full_cli_pipeline():
    """测试钢材的完整CLI链路"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    identity_file = FIXTURES_DIR / "identities" / "steel_rb2610_identity.json"
    fundamentals_file = FIXTURES_DIR / "steel_rb_fundamentals.json"

    print(f"✓ Identity文件存在: {identity_file.exists()}")
    print(f"✓ Fundamentals文件存在: {fundamentals_file.exists()}")

    # 验证文件内容
    identity = json.loads(identity_file.read_text())
    fundamentals = json.loads(fundamentals_file.read_text())

    print(f"✓ Identity: {identity['variety_id']} {identity['contract']}")
    print(f"✓ Fundamentals: {fundamentals['variety_id']} as_of={fundamentals['as_of']}")

    # 运行futures-fundamentals命令
    result = subprocess.run(
        [
            PYTHON, "-m", "industry_first_research",
            "futures-fundamentals",
            "--identity", str(identity_file),
            "--input", str(fundamentals_file),
            "--output-dir", str(OUTPUT_DIR)
        ],
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": str(PROJECT_ROOT / "src")},
        capture_output=True,
        text=True,
        timeout=60
    )

    print(f"\n返回码: {result.returncode}")
    print(f"STDOUT:\n{result.stdout}")
    if result.stderr:
        print(f"STDERR:\n{result.stderr}")

    # 检查输出
    if result.returncode == 0:
        print("✓ CLI命令执行成功")
        # 查找生成的报告文件
        report_files = list(OUTPUT_DIR.glob("*steel*.json"))
        if report_files:
            print(f"✓ 生成报告文件: {report_files[0].name}")
            report = json.loads(report_files[0].read_text())
            print(f"✓ 报告schema: {report.get('schema_version')}")
            return True
    else:
        print(f"✗ CLI命令失败")
        return False


def test_copper_full_cli_pipeline():
    """测试铜的完整CLI链路"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    identity_file = FIXTURES_DIR / "identities" / "copper_cu2607_identity.json"
    fundamentals_file = FIXTURES_DIR / "copper_cu_fundamentals.json"

    print(f"\n--- 铜 CLI链路测试 ---")
    print(f"✓ Identity文件存在: {identity_file.exists()}")
    print(f"✓ Fundamentals文件存在: {fundamentals_file.exists()}")

    identity = json.loads(identity_file.read_text())
    fundamentals = json.loads(fundamentals_file.read_text())

    print(f"✓ Identity: {identity['variety_id']} {identity['contract']}")
    print(f"✓ Fundamentals: {fundamentals['variety_id']} as_of={fundamentals['as_of']}")

    result = subprocess.run(
        [
            PYTHON, "-m", "industry_first_research",
            "futures-fundamentals",
            "--identity", str(identity_file),
            "--input", str(fundamentals_file),
            "--output-dir", str(OUTPUT_DIR)
        ],
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": str(PROJECT_ROOT / "src")},
        capture_output=True,
        text=True,
        timeout=60
    )

    print(f"\n返回码: {result.returncode}")
    if result.returncode == 0:
        print("✓ CLI命令执行成功")
        report_files = list(OUTPUT_DIR.glob("*copper*.json"))
        if report_files:
            print(f"✓ 生成报告文件: {report_files[0].name}")
            return True
    else:
        print(f"✗ CLI命令失败: {result.stderr[:500]}")
        return False


def test_historical_data_structure_consistency():
    """测试历史数据结构一致性"""
    print(f"\n--- 历史数据结构一致性测试 ---")

    historical_dir = FIXTURES_DIR / "historical"
    historical_files = list(historical_dir.glob("*.json"))

    print(f"✓ 找到 {len(historical_files)} 个历史数据文件")

    for file in historical_files:
        data = json.loads(file.read_text())

        # 验证必需字段
        assert data["schema_version"] == "futures-fundamentals-input.v1"
        assert "variety_id" in data
        assert "as_of" in data
        assert "market_phase" in data
        assert "spot_benchmark" in data
        assert "market_narrative" in data

        print(f"✓ {file.name}: {data['variety_id']} {data['market_phase']}")

    print(f"✓ 所有历史数据文件结构一致")
    return True


def test_identity_files_completeness():
    """测试identity文件完整性"""
    print(f"\n--- Identity文件完整性测试 ---")

    identities_dir = FIXTURES_DIR / "identities"
    identity_files = list(identities_dir.glob("*.json"))

    print(f"✓ 找到 {len(identity_files)} 个identity文件")

    expected_varieties = {"RB", "CU", "LC", "M", "SC"}
    found_varieties = set()

    for file in identity_files:
        identity = json.loads(file.read_text())

        # 验证必需字段
        assert identity["schema_version"] == "futures-object-identity.v1"
        assert "variety_id" in identity
        assert "commodity_adapter_id" in identity
        assert "identification_status" in identity

        variety_id = identity["variety_id"]
        found_varieties.add(variety_id)

        print(f"✓ {file.name}: {variety_id} -> {identity['commodity_adapter_id']}")

    missing = expected_varieties - found_varieties
    if missing:
        print(f"⚠ 缺少品种: {missing}")
    else:
        print(f"✓ 所有5个品种都有identity文件")

    return len(missing) == 0


def test_data_traceability():
    """测试数据可追溯性"""
    print(f"\n--- 数据可追溯性测试 ---")

    # 测试当前数据
    current_files = [
        "steel_rb_fundamentals.json",
        "copper_cu_fundamentals.json",
        "lithium_lc_fundamentals.json",
        "soybean_meal_m_fundamentals.json",
        "crude_oil_sc_fundamentals.json"
    ]

    for filename in current_files:
        data = json.loads((FIXTURES_DIR / filename).read_text())

        # 验证证据追溯
        assert "evidence_ids" in data
        assert len(data["evidence_ids"]) > 0
        assert "source_document_id" in data
        assert len(data["source_document_id"]) > 0

        print(f"✓ {filename}: {len(data['evidence_ids'])} 个证据ID")

    # 测试历史数据
    historical_dir = FIXTURES_DIR / "historical"
    for file in historical_dir.glob("*.json"):
        data = json.loads(file.read_text())
        assert "evidence_ids" in data
        assert "source_document_id" in data
        print(f"✓ {file.name}: 证据追溯完整")

    print(f"✓ 所有数据都有完整的证据追溯")
    return True


def main():
    """运行所有验证测试"""
    print("=" * 80)
    print("CLI链路验证测试")
    print("=" * 80)

    results = {}

    # 测试1: 数据结构一致性
    try:
        results["historical_consistency"] = test_historical_data_structure_consistency()
    except Exception as e:
        print(f"✗ 历史数据一致性测试失败: {e}")
        results["historical_consistency"] = False

    # 测试2: Identity文件完整性
    try:
        results["identity_completeness"] = test_identity_files_completeness()
    except Exception as e:
        print(f"✗ Identity完整性测试失败: {e}")
        results["identity_completeness"] = False

    # 测试3: 数据可追溯性
    try:
        results["data_traceability"] = test_data_traceability()
    except Exception as e:
        print(f"✗ 数据可追溯性测试失败: {e}")
        results["data_traceability"] = False

    # 测试4: 钢材CLI链路
    print(f"\n--- 钢材 CLI链路测试 ---")
    try:
        results["steel_cli"] = test_steel_full_cli_pipeline()
    except Exception as e:
        print(f"✗ 钢材CLI链路测试失败: {e}")
        results["steel_cli"] = False

    # 测试5: 铜CLI链路
    try:
        results["copper_cli"] = test_copper_full_cli_pipeline()
    except Exception as e:
        print(f"✗ 铜CLI链路测试失败: {e}")
        results["copper_cli"] = False

    # 总结
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)
    for test_name, passed in results.items():
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"{test_name:30s}: {status}")

    passed_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    print(f"\n总计: {passed_count}/{total_count} 个测试通过")

    return passed_count == total_count


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
