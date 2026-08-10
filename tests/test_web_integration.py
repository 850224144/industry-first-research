"""
Web界面集成测试

测试web服务器启动和API响应
"""
import subprocess
import time
import requests
import json
from pathlib import Path

from tests.subprocess_helpers import PYTHON, subprocess_environment


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path(__file__).parent / "output"


def test_web_server_health():
    """测试web服务器健康检查"""
    # 启动web服务器
    print("启动web服务器...")
    proc = subprocess.Popen(
        [PYTHON, "-m", "industry_first_research", "web", "--port", "8765"],
        cwd=PROJECT_ROOT,
        env=subprocess_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # 等待服务器启动
    time.sleep(3)

    try:
        # 测试健康检查端点
        response = requests.get("http://127.0.0.1:8765/api/health", timeout=5)
        print(f"✓ Health endpoint响应: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✓ 服务器版本: {data.get('schema_version')}")
            print(f"✓ 执行模式: execution_enabled={data.get('execution_enabled')}")
            return True

    except requests.exceptions.ConnectionError:
        print("✗ 无法连接到web服务器")
        return False

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False

    finally:
        # 停止服务器
        proc.terminate()
        proc.wait(timeout=5)
        print("✓ 服务器已停止")


def test_web_api_summary():
    """测试摘要API"""
    print("\n--- 测试摘要API ---")

    proc = subprocess.Popen(
        [PYTHON, "-m", "industry_first_research", "web", "--port", "8766"],
        cwd=PROJECT_ROOT,
        env=subprocess_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    time.sleep(3)

    try:
        response = requests.get("http://127.0.0.1:8766/api/summary", timeout=5)
        print(f"✓ Summary endpoint响应: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✓ 快照数量: {data.get('snapshot_count', 0)}")
            print(f"✓ Schema统计: {len(data.get('schema_counts', {}))}")
            print(f"✓ 状态统计: {len(data.get('status_counts', {}))}")
            print(f"✓ execution_enabled: {data.get('execution_enabled')}")
            return True

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False

    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_web_static_files():
    """测试静态文件访问"""
    print("\n--- 测试静态文件访问 ---")

    proc = subprocess.Popen(
        [PYTHON, "-m", "industry_first_research", "web", "--port", "8767"],
        cwd=PROJECT_ROOT,
        env=subprocess_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    time.sleep(3)

    try:
        response = requests.get("http://127.0.0.1:8767/", timeout=5)
        print(f"✓ 根路径响应: {response.status_code}")

        if response.status_code == 200:
            html = response.text
            if "研究控制台" in html or "industry-first-research" in html.lower():
                print("✓ HTML内容包含预期标题")
                return True
            else:
                print("⚠ HTML内容可能不完整")
                return False

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False

    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_web_policy_compliance():
    """测试web界面遵循项目原则"""
    print("\n--- 测试项目原则遵循 ---")

    proc = subprocess.Popen(
        [PYTHON, "-m", "industry_first_research", "web", "--port", "8768"],
        cwd=PROJECT_ROOT,
        env=subprocess_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    time.sleep(3)

    try:
        # 检查健康接口
        response = requests.get("http://127.0.0.1:8768/api/health", timeout=5)
        data = response.json()

        checks = {
            "execution_enabled必须为false": data.get("execution_enabled") == False,
            "read_only必须为true": data.get("read_only") == True,
            "review_only必须为true": data.get("review_only") == True,
        }

        for check_name, passed in checks.items():
            status = "✓" if passed else "✗"
            print(f"{status} {check_name}")

        return all(checks.values())

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False

    finally:
        proc.terminate()
        proc.wait(timeout=5)


def create_test_summary():
    """创建测试总结"""
    print("\n" + "=" * 80)
    print("Web界面测试总结")
    print("=" * 80)

    tests = [
        ("Web服务器健康检查", test_web_server_health),
        ("摘要API功能", test_web_api_summary),
        ("静态文件访问", test_web_static_files),
        ("项目原则遵循", test_web_policy_compliance),
    ]

    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"✗ {test_name}执行失败: {e}")
            results[test_name] = False
        time.sleep(1)

    print("\n" + "=" * 80)
    print("测试结果")
    print("=" * 80)

    for test_name, passed in results.items():
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"{test_name:30s}: {status}")

    passed_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    print(f"\n总计: {passed_count}/{total_count} 个测试通过")

    return passed_count == total_count


if __name__ == "__main__":
    import sys
    success = create_test_summary()
    sys.exit(0 if success else 1)
