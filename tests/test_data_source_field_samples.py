"""
测试数据源真实字段样例的解析回归
包含：
1. 期货交易所数据（库存、结算价）
2. 东方财富数据（财务数据、公司资料）
3. 交易所行情数据（上交所、深交所）
4. 上市公司官网数据（投资者关系、产品信息）
"""
import json
from pathlib import Path
import pytest


FIXTURES = Path(__file__).parent / "fixtures" / "data_sources"


def test_futures_exchange_inventory_detail_structure():
    """测试期货交易所库存仓单详细数据结构"""
    data = json.loads((FIXTURES / "futures_exchange_inventory_detail.json").read_text())

    assert data["code"] == 0
    assert data["msg"] == "查询成功"

    detail = data["data"]
    assert detail["exchange"] == "DCE"
    assert detail["variety"] == "M"
    assert detail["variety_name"] == "豆粕"
    assert detail["report_date"] == "2026-03-10"
    assert "warehouse_receipts" in detail
    assert len(detail["warehouse_receipts"]) > 0

    # 验证仓单明细字段
    warehouse = detail["warehouse_receipts"][0]
    assert "warehouse_name" in warehouse
    assert "region" in warehouse
    assert "prev_receipts" in warehouse
    assert "curr_receipts" in warehouse
    assert "change" in warehouse
    assert "unit" in warehouse

    # 验证汇总字段
    assert detail["total_prev"] == 36970
    assert detail["total_curr"] == 37450
    assert detail["total_change"] == 480
    assert detail["source_document_id"]


def test_futures_exchange_daily_settlement_structure():
    """测试期货交易所日结算数据结构"""
    data = json.loads((FIXTURES / "futures_exchange_daily_settlement.json").read_text())

    assert data["code"] == 0
    settlement = data["data"]

    # 验证合约基本信息
    assert settlement["exchange"] == "SHFE"
    assert settlement["variety"] == "CU"
    assert settlement["contract"] == "CU2607"
    assert settlement["trade_date"] == "2026-05-20"

    # 验证价格字段
    assert "pre_settlement" in settlement
    assert "open" in settlement
    assert "high" in settlement
    assert "low" in settlement
    assert "close" in settlement
    assert "settlement" in settlement

    # 验证交易字段
    assert "volume" in settlement
    assert "open_interest" in settlement
    assert "turnover" in settlement

    # 验证合约规格
    assert settlement["multiplier"] == "5"
    assert settlement["tick_size"] == "10"
    assert settlement["margin_ratio"] == "0.08"
    assert settlement["trading_unit"] == "吨"

    # 验证交割信息
    assert "last_trading_date" in settlement
    assert "delivery_date" in settlement
    assert settlement["source_document_id"]


def test_eastmoney_financial_summary_structure():
    """测试东方财富财务数据结构"""
    data = json.loads((FIXTURES / "eastmoney_financial_summary.json").read_text())

    assert data["code"] == 0
    financial = data["data"]

    # 验证基本信息
    assert financial["security_code"] == "600438"
    assert financial["security_name"] == "通威股份"
    assert financial["report_date"] == "2025-12-31"
    assert financial["report_type"] == "年报"

    # 验证盈利能力指标
    assert "basic_eps" in financial
    assert "total_revenue" in financial
    assert "net_profit" in financial
    assert "gross_profit_margin" in financial
    assert "net_profit_margin" in financial
    assert "roe" in financial

    # 验证资产负债指标
    assert "total_assets" in financial
    assert "total_liabilities" in financial
    assert "net_assets" in financial
    assert "asset_liability_ratio" in financial

    # 验证现金流指标
    assert "operating_cash_flow" in financial
    assert "cash_flow_per_share" in financial

    # 验证运营效率指标
    assert "current_ratio" in financial
    assert "inventory_turnover" in financial
    assert "receivable_turnover" in financial

    assert financial["source_document_id"]


def test_eastmoney_company_profile_structure():
    """测试东方财富公司资料结构"""
    data = json.loads((FIXTURES / "eastmoney_company_profile.json").read_text())

    assert data["code"] == 0
    profile = data["data"]

    # 验证基本信息
    assert profile["security_code"] == "300750"
    assert profile["security_name"] == "宁德时代"
    assert profile["listing_market"] == "SZ"
    assert profile["company_name"] == "宁德时代新能源科技股份有限公司"

    # 验证公司详情
    assert "registered_capital" in profile
    assert "legal_representative" in profile
    assert "established_date" in profile
    assert "registered_address" in profile
    assert "business_scope" in profile
    assert "main_business" in profile

    # 验证行业分类
    assert "industry" in profile
    assert "industry_code" in profile

    # 验证股本结构
    assert "total_shares" in profile
    assert "float_shares" in profile

    # 验证管理层
    assert "chairman" in profile
    assert "secretary" in profile

    # 验证其他信息
    assert "employees" in profile
    assert "website" in profile
    assert profile["source_document_id"]


def test_official_exchange_quote_structure():
    """测试交易所行情数据结构"""
    # 测试深交所行情
    szse_data = json.loads((FIXTURES / "official_exchange_szse_quote.json").read_text())
    assert szse_data["code"] == "0"
    szse_quote = szse_data["data"]

    assert szse_quote["code"] == "000858"
    assert szse_quote["name"] == "五粮液"
    assert szse_quote["market"] == "sz"

    # 验证价格字段
    assert "open" in szse_quote
    assert "high" in szse_quote
    assert "low" in szse_quote
    assert "close" in szse_quote
    assert "pre_close" in szse_quote

    # 验证交易量字段
    assert "volume" in szse_quote
    assert "amount" in szse_quote
    assert "turnover" in szse_quote

    # 验证估值字段
    assert "pe_ttm" in szse_quote
    assert "pb" in szse_quote
    assert "total_market_value" in szse_quote

    # 测试上交所行情
    sse_data = json.loads((FIXTURES / "official_exchange_sse_quote.json").read_text())
    assert sse_data["code"] == 0
    sse_quote = sse_data["data"]

    assert sse_quote["symbol"] == "600519.SH"
    assert sse_quote["name"] == "贵州茅台"
    assert "close" in sse_quote
    assert "market_cap" in sse_quote
    assert sse_quote["source_document_id"]


def test_company_website_investor_relations_structure():
    """测试上市公司官网投资者关系数据结构"""
    data = json.loads((FIXTURES / "company_website_investor_relations.json").read_text())

    assert data["code"] == 0
    assert data["source"] == "company_official_website"
    ir_data = data["data"]

    # 验证基本信息
    assert ir_data["company_code"] == "601012"
    assert ir_data["company_name"] == "隆基绿能科技股份有限公司"
    assert "company_name_en" in ir_data
    assert "website" in ir_data

    # 验证投资者关系联系信息
    assert "ir_contact" in ir_data
    contact = ir_data["ir_contact"]
    assert "department" in contact
    assert "secretary" in contact
    assert "email" in contact
    assert "phone" in contact
    assert "address" in contact

    # 验证公司简介
    assert "company_profile" in ir_data
    profile = ir_data["company_profile"]
    assert "brief" in profile
    assert "established" in profile
    assert "listing_date" in profile
    assert "listing_market" in profile
    assert "main_business" in profile
    assert "core_products" in profile
    assert "production_bases" in profile

    # 验证最新公告
    assert "latest_announcement" in ir_data
    assert ir_data["source_document_id"]


def test_company_website_product_info_structure():
    """测试上市公司官网产品信息数据结构"""
    data = json.loads((FIXTURES / "company_website_product_info.json").read_text())

    assert data["code"] == 0
    assert data["source"] == "company_official_website"
    product_data = data["data"]

    # 验证基本信息
    assert product_data["company_code"] == "002594"
    assert product_data["company_name"] == "比亚迪股份有限公司"
    assert "website" in product_data

    # 验证产品分类
    assert "product_categories" in product_data
    assert len(product_data["product_categories"]) > 0

    category = product_data["product_categories"][0]
    assert "category_id" in category
    assert "category_name" in category

    # 验证新能源汽车产品
    assert category["category_id"] == "new_energy_vehicles"
    assert "sub_categories" in category

    sub_category = category["sub_categories"][0]
    assert "name" in sub_category
    assert "products" in sub_category

    # 验证具体产品信息
    product = sub_category["products"][0]
    assert "model" in product
    assert "type" in product
    assert "price_range" in product

    assert product_data["source_document_id"]


def test_data_source_field_completeness():
    """测试所有数据源样例的字段完整性"""
    test_files = [
        ("futures_exchange_inventory_detail.json", ["code", "data", "data.exchange", "data.variety", "data.warehouse_receipts"]),
        ("futures_exchange_daily_settlement.json", ["code", "data", "data.contract", "data.settlement", "data.volume"]),
        ("eastmoney_financial_summary.json", ["code", "data", "data.security_code", "data.total_revenue", "data.net_profit"]),
        ("eastmoney_company_profile.json", ["code", "data", "data.company_name", "data.main_business"]),
        ("official_exchange_szse_quote.json", ["code", "data", "data.code", "data.close", "data.volume"]),
        ("official_exchange_sse_quote.json", ["code", "data", "data.symbol", "data.close"]),
        ("company_website_investor_relations.json", ["code", "data", "data.company_code", "data.ir_contact"]),
        ("company_website_product_info.json", ["code", "data", "data.company_code", "data.product_categories"]),
    ]

    for filename, required_fields in test_files:
        data = json.loads((FIXTURES / filename).read_text())

        for field_path in required_fields:
            parts = field_path.split(".")
            current = data
            for part in parts:
                assert part in current, f"Missing field '{field_path}' in {filename}"
                current = current[part]


def test_data_source_document_id_consistency():
    """测试所有数据源样例都包含source_document_id"""
    json_files = [
        "futures_exchange_inventory_detail.json",
        "futures_exchange_daily_settlement.json",
        "eastmoney_financial_summary.json",
        "eastmoney_company_profile.json",
        "official_exchange_szse_quote.json",
        "official_exchange_sse_quote.json",
        "company_website_investor_relations.json",
        "company_website_product_info.json",
    ]

    for filename in json_files:
        data = json.loads((FIXTURES / filename).read_text())
        assert "data" in data, f"Missing 'data' field in {filename}"
        assert "source_document_id" in data["data"], f"Missing 'source_document_id' in {filename}"
        assert data["data"]["source_document_id"], f"Empty 'source_document_id' in {filename}"


def test_numeric_field_types():
    """测试数值类型字段的一致性"""
    # 期货结算数据中的数值字段
    settlement = json.loads((FIXTURES / "futures_exchange_daily_settlement.json").read_text())
    data = settlement["data"]

    # 价格字段应为字符串（保留精度）
    assert isinstance(data["pre_settlement"], str)
    assert isinstance(data["settlement"], str)

    # 数量字段应为字符串
    assert isinstance(data["volume"], str)
    assert isinstance(data["open_interest"], str)

    # 财务数据中的数值字段
    financial = json.loads((FIXTURES / "eastmoney_financial_summary.json").read_text())
    fin_data = financial["data"]

    # 财务金额字段应为字符串（保留精度）
    assert isinstance(fin_data["total_revenue"], str)
    assert isinstance(fin_data["net_profit"], str)
    assert isinstance(fin_data["total_assets"], str)


def test_timestamp_format_consistency():
    """测试时间戳格式的一致性"""
    files_with_timestamps = [
        ("futures_exchange_inventory_detail.json", "data.publish_time"),
        ("futures_exchange_daily_settlement.json", "data.timestamp"),
        ("official_exchange_sse_quote.json", "data.timestamp"),
        ("company_website_investor_relations.json", "data.crawl_time"),
        ("company_website_product_info.json", "data.crawl_time"),
    ]

    for filename, timestamp_path in files_with_timestamps:
        data = json.loads((FIXTURES / filename).read_text())

        parts = timestamp_path.split(".")
        current = data
        for part in parts:
            current = current[part]

        # 验证时间戳格式为 ISO 8601
        assert "T" in current or ":" in current, f"Invalid timestamp format in {filename}: {current}"
        assert "2026" in current, f"Invalid year in timestamp in {filename}: {current}"
