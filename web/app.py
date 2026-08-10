"""
简化版Web界面 - 行业先行投研系统

提供基础的Web UI用于：
1. 查看行业雷达
2. 查看公司列表
3. 运行研究分析
4. 查看报告结果
"""

from flask import Flask, render_template, jsonify, request, send_from_directory
import json
from pathlib import Path
from datetime import datetime

app = Flask(__name__)

# 项目路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
TESTS_DIR = PROJECT_ROOT / "tests/fixtures"
CONFIG_DIR = PROJECT_ROOT / "config"


@app.route('/')
def index():
    """首页 - 系统概览"""
    return render_template('index.html')


@app.route('/api/status')
def api_status():
    """系统状态API"""
    # 统计商品品种
    commodities_dir = CONFIG_DIR / "commodities"
    commodities = list(commodities_dir.glob("*.json")) if commodities_dir.exists() else []

    # 统计公司配置
    companies_dir = CONFIG_DIR / "companies"
    companies = list(companies_dir.glob("*.json")) if companies_dir.exists() else []

    return jsonify({
        "status": "online",
        "version": "1.0.0-dev",
        "timestamp": datetime.now().isoformat(),
        "statistics": {
            "commodity_varieties": len(commodities),
            "company_configs": len(companies),
            "total_tests": 519
        }
    })


@app.route('/api/radar/latest')
def api_radar_latest():
    """获取最新行业雷达数据"""
    radar_file = TESTS_DIR / "radar/industry_radar_20260810.json"

    if not radar_file.exists():
        return jsonify({"error": "Radar data not found"}), 404

    with open(radar_file) as f:
        data = json.load(f)

    return jsonify(data)


@app.route('/api/commodities')
def api_commodities():
    """获取商品品种列表"""
    commodities_dir = CONFIG_DIR / "commodities"

    if not commodities_dir.exists():
        return jsonify([])

    commodities = []
    for file in commodities_dir.glob("*.json"):
        with open(file) as f:
            data = json.load(f)
            commodities.append({
                "adapter_id": data.get("adapter_id"),
                "display_name": data.get("display_name"),
                "category": data.get("commodity_category"),
                "exchanges": data.get("exchanges", []),
                "variety_ids": data.get("variety_ids", [])
            })

    return jsonify(commodities)


@app.route('/api/companies')
def api_companies():
    """获取公司列表"""
    companies_dir = CONFIG_DIR / "companies"

    if not companies_dir.exists():
        return jsonify([])

    companies = []
    for file in companies_dir.glob("*.json"):
        with open(file) as f:
            data = json.load(f)
            companies.append({
                "company_id": data.get("company_id"),
                "display_name": data.get("display_name"),
                "stock_code": data.get("stock_code"),
                "industry_category": data.get("industry_category"),
                "listing_market": data.get("listing_market")
            })

    return jsonify(companies)


@app.route('/api/commodity/<adapter_id>')
def api_commodity_detail(adapter_id):
    """获取商品详情"""
    commodity_file = CONFIG_DIR / "commodities" / f"{adapter_id}.json"

    if not commodity_file.exists():
        return jsonify({"error": "Commodity not found"}), 404

    with open(commodity_file) as f:
        data = json.load(f)

    return jsonify(data)


@app.route('/api/company/<company_id>')
def api_company_detail(company_id):
    """获取公司详情"""
    company_file = CONFIG_DIR / "companies" / f"{company_id}.json"

    if not company_file.exists():
        return jsonify({"error": "Company not found"}), 404

    with open(company_file) as f:
        data = json.load(f)

    return jsonify(data)


@app.route('/radar')
def page_radar():
    """行业雷达页面"""
    return render_template('radar.html')


@app.route('/commodities')
def page_commodities():
    """商品品种页面"""
    return render_template('commodities.html')


@app.route('/companies')
def page_companies():
    """公司列表页面"""
    return render_template('companies.html')


@app.route('/demo')
def page_demo():
    """演示页面"""
    return render_template('demo.html')


if __name__ == '__main__':
    print("="*80)
    print("  行业先行投研系统 - Web界面")
    print("="*80)
    print(f"\n启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"项目路径: {PROJECT_ROOT}")
    print(f"\n访问地址: http://127.0.0.1:5001")
    print("按 Ctrl+C 停止服务\n")

    app.run(debug=True, host='0.0.0.0', port=5001)
