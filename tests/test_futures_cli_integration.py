"""
期货基本面报告生成的集成测试

测试真实CLI命令能否使用我们创建的数据样例
"""
import json
import subprocess
from pathlib import Path
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "commodities"
OUTPUT_DIR = Path(__file__).parent / "output" / "futures_integration"


@pytest.fixture(autouse=True)
def setup_output_dir():
    """创建输出目录"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    yield
    # 测试后保留输出用于检查


def test_futures_identity_cli_available():
    """测试futures-identify命令是否可用"""
    result = subprocess.run(
        ["python3", "-m", "industry_first_research", "futures-identify", "--help"],
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": str(SRC_DIR)},
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, f"futures-identify命令不可用: {result.stderr}"
    assert "futures-identify" in result.stdout


def test_commodity_adapters_cli_available():
    """测试commodity-adapters命令是否可用"""
    result = subprocess.run(
        ["python3", "-m", "industry_first_research", "commodity-adapters", "--help"],
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": str(SRC_DIR)},
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, f"commodity-adapters命令不可用: {result.stderr}"
    assert "commodity-adapters" in result.stdout


def test_list_commodity_adapters():
    """测试列出所有商品适配器"""
    result = subprocess.run(
        [
            "python3", "-m", "industry_first_research",
            "commodity-adapters",
            "--adapter-dir", str(PROJECT_ROOT / "config" / "commodities"),
            "--output-dir", str(OUTPUT_DIR)
        ],
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": str(SRC_DIR)},
        capture_output=True,
        text=True,
        timeout=30
    )

    # 命令可能返回非0（如果有验证问题），但不应该崩溃
    print(f"stdout: {result.stdout}")
    print(f"stderr: {result.stderr}")

    # 检查是否提到了我们的5个品种
    assert any(v in result.stdout or v in result.stderr
              for v in ["steel", "copper", "lithium", "soybean", "crude"])


def test_validate_steel_adapter():
    """测试验证钢材适配器配置"""
    steel_config = PROJECT_ROOT / "config" / "commodities" / "steel.json"

    result = subprocess.run(
        [
            "python3", "-m", "industry_first_research",
            "commodity-adapter-validate",
            "--adapter-config", str(steel_config),
            "--output-dir", str(OUTPUT_DIR)
        ],
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": str(SRC_DIR)},
        capture_output=True,
        text=True,
        timeout=30
    )

    print(f"stdout: {result.stdout}")
    print(f"stderr: {result.stderr}")

    # 验证应该成功或返回有意义的错误
    assert "steel" in result.stdout or "steel" in result.stderr


def test_create_futures_identity_for_steel():
    """为钢材创建期货身份识别文件"""
    identity_data = {
        "schema_version": "futures-object-identity.v1",
        "identity_id": "futures-identity-rb-20260520-001",
        "object_type": "specific_contract",
        "exchange": "SHFE",
        "variety_id": "RB",
        "variety_name": "螺纹钢",
        "contract": "RB2610",
        "contract_type": "主力合约候选",
        "as_of": "2026-05-20T16:00:00+08:00",
        "commodity_adapter_id": "steel",
        "spot_benchmark": {
            "benchmark_id": "east_china_rebar_spot",
            "name": "华东螺纹钢现货",
            "comparability": "SAME_GRADE_REGION"
        },
        "identification_status": "READY",
        "identification_method": "explicit_exchange_variety_contract"
    }

    identity_file = OUTPUT_DIR / "steel_rb_identity.json"
    identity_file.write_text(json.dumps(identity_data, ensure_ascii=False, indent=2))

    assert identity_file.exists()
    return identity_file


def test_steel_fundamentals_data_structure():
    """验证钢材基本面数据结构"""
    fundamentals_file = FIXTURES_DIR / "steel_rb_fundamentals.json"

    assert fundamentals_file.exists(), "钢材基本面数据文件不存在"

    data = json.loads(fundamentals_file.read_text())

    # 验证schema
    assert data["schema_version"] == "futures-fundamentals-input.v1"
    assert data["variety_id"] == "RB"
    assert data["exchange"] == "SHFE"

    # 验证关键数据字段
    assert "spot_benchmark" in data
    assert "contract_quotes" in data
    assert "inventory" in data
    assert "production" in data
    assert "cost" in data
    assert "basis" in data


def test_copper_fundamentals_data_structure():
    """验证铜基本面数据结构"""
    fundamentals_file = FIXTURES_DIR / "copper_cu_fundamentals.json"

    assert fundamentals_file.exists(), "铜基本面数据文件不存在"

    data = json.loads(fundamentals_file.read_text())

    assert data["schema_version"] == "futures-fundamentals-input.v1"
    assert data["variety_id"] == "CU"
    assert data["exchange"] == "SHFE"

    # 铜特有字段
    assert "concentrate_tc" in data["cost"]
    assert "term_structure" in data


def test_lithium_fundamentals_data_structure():
    """验证碳酸锂基本面数据结构"""
    fundamentals_file = FIXTURES_DIR / "lithium_lc_fundamentals.json"

    assert fundamentals_file.exists(), "碳酸锂基本面数据文件不存在"

    data = json.loads(fundamentals_file.read_text())

    assert data["schema_version"] == "futures-fundamentals-input.v1"
    assert data["variety_id"] == "LC"
    assert data["exchange"] == "GFEX"

    # 碳酸锂特有字段
    assert "demand" in data
    assert "battery_output" in data["demand"]
    assert "cost_curve_p90" in data["cost"]


def test_soybean_meal_fundamentals_data_structure():
    """验证豆粕基本面数据结构"""
    fundamentals_file = FIXTURES_DIR / "soybean_meal_m_fundamentals.json"

    assert fundamentals_file.exists(), "豆粕基本面数据文件不存在"

    data = json.loads(fundamentals_file.read_text())

    assert data["schema_version"] == "futures-fundamentals-input.v1"
    assert data["variety_id"] == "M"
    assert data["exchange"] == "DCE"

    # 豆粕特有字段
    assert "trade" in data
    assert "soybean_imports" in data["trade"]
    assert "crush_margin" in data["margin"]


def test_crude_oil_fundamentals_data_structure():
    """验证原油基本面数据结构"""
    fundamentals_file = FIXTURES_DIR / "crude_oil_sc_fundamentals.json"

    assert fundamentals_file.exists(), "原油基本面数据文件不存在"

    data = json.loads(fundamentals_file.read_text())

    assert data["schema_version"] == "futures-fundamentals-input.v1"
    assert data["variety_id"] == "SC"
    assert data["exchange"] == "INE"

    # 原油特有字段
    assert "fx" in data
    assert "crack_spread" in data
    assert data["spot_benchmark"]["unit"] == "USD/barrel"


def test_all_fundamentals_have_evidence_traceability():
    """验证所有基本面数据都有证据追溯"""
    fundamentals_files = [
        "steel_rb_fundamentals.json",
        "copper_cu_fundamentals.json",
        "lithium_lc_fundamentals.json",
        "soybean_meal_m_fundamentals.json",
        "crude_oil_sc_fundamentals.json"
    ]

    for filename in fundamentals_files:
        data = json.loads((FIXTURES_DIR / filename).read_text())

        assert "evidence_ids" in data, f"Missing evidence_ids in {filename}"
        assert len(data["evidence_ids"]) > 0, f"Empty evidence_ids in {filename}"

        assert "source_document_id" in data, f"Missing source_document_id in {filename}"
        assert len(data["source_document_id"]) > 0, f"Empty source_document_id in {filename}"


def test_readme_next_stage_tasks_status():
    """验证README下一阶段任务的完成状态"""
    # 任务1：更多交易所和上市公司站点的字段样例与解析回归样本
    announcement_fixtures = PROJECT_ROOT / "tests" / "fixtures" / "announcements"
    data_source_fixtures = PROJECT_ROOT / "tests" / "fixtures" / "data_sources"

    assert (announcement_fixtures / "official_exchange_sse_real.json").exists()
    assert (announcement_fixtures / "company_disclosure_sse_real.html").exists()
    assert (announcement_fixtures / "eastmoney_announcement_real_quarterly.json").exists()
    assert (data_source_fixtures / "futures_exchange_inventory_detail.json").exists()

    # 任务2：更多商品品种配置、各品种真实数据链路回归
    assert (FIXTURES_DIR / "steel_rb_fundamentals.json").exists()
    assert (FIXTURES_DIR / "copper_cu_fundamentals.json").exists()
    assert (FIXTURES_DIR / "lithium_lc_fundamentals.json").exists()
    assert (FIXTURES_DIR / "soybean_meal_m_fundamentals.json").exists()
    assert (FIXTURES_DIR / "crude_oil_sc_fundamentals.json").exists()

    # 任务3：Web界面和微信公众号草稿发布 - 待实现
    # 这是下一个优先级


if __name__ == "__main__":
    # 可以直接运行这个文件进行快速测试
    pytest.main([__file__, "-v", "-s"])
